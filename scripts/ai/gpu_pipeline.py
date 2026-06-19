"""
RVDiA Local GPU Pipeline Server
Runs on the user's laptop (with GPU) to generate images.
Exposes a secure API on a certain port.

Instructions to Run:
1. Make sure you have PyTorch with CUDA installed on your laptop.
2. Install dependencies:
   pip install flask Pillow diffusers transformers accelerate winotify python-dotenv
3. Create a local '.env' file in the bot root or run this script with env variables:
   LAPTOP_API_KEY=your_secure_shared_key
   LAPTOP_PORT=XXXXX
   MODEL_ID_OR_PATH=Meina/MeinaMix_V11
4. Run:
   python312 scripts/gpu_pipeline_server.py
5. Start your tunnel:
   ngrok http XXXXX   (or cloudflared tunnel --url http://localhost:XXXXX)
6. Copy the public tunnel URL and set it as LAPTOP_API_URL in Railway!
"""

import os
import io
import uuid
import logging
import threading
import hmac
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_file

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

load_dotenv()

# Strict environment requirements (No default fallbacks for key and port)
PORT_ENV = os.getenv("LAPTOP_PORT")
API_KEY = os.getenv("LAPTOP_API_KEY")

if not PORT_ENV:
    raise ValueError("ERROR: Environment variable 'LAPTOP_PORT' is not set! Please define it in your .env file.")
if not API_KEY:
    raise ValueError("ERROR: Environment variable 'LAPTOP_API_KEY' is not set! Please define it in your .env file.")

PORT = int(PORT_ENV)
MODEL_ID = os.getenv("MODEL_ID_OR_PATH", "Meina/MeinaMix_V11")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../scratch/gpu_outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)

# In-memory request registry
# Schema: { request_id: { "prompt": str, "username": str, "status": str, "image_path": str, "error": str } }
REQUESTS = {}

# Stable Diffusion Pipeline (Loaded lazily on first approved request)
pipe = None
pipe_lock = threading.Lock()

def load_pipeline():
    global pipe
    with pipe_lock:
        if pipe is not None:
            return
        
        import torch
        from diffusers import StableDiffusionPipeline
        
        logging.info(f"Loading Stable Diffusion pipeline from: {MODEL_ID}...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load with fp16 on CUDA to save VRAM (essential for 4GB RTX 3050)
        torch_dtype = torch.float16 if device == "cuda" else torch.float32
        
        pipe = StableDiffusionPipeline.from_pretrained(
            MODEL_ID,
            torch_dtype=torch_dtype,
            safety_checker=None  # Disable safety checker to save VRAM
        )
        
        # Load initially onto CPU to keep GPU VRAM 100% clean for browsing
        pipe = pipe.to("cpu")
        
        if device == "cuda":
            # Enable memory optimizations
            pipe.enable_attention_slicing()
            try:
                pipe.enable_xformers_memory_efficient_attention()
                logging.info("Enabled xformers memory efficient attention.")
            except Exception:
                logging.info("xformers not installed, using standard attention slicing.")
                
        logging.info("Stable Diffusion Pipeline loaded and cached on CPU!")

def run_stable_diffusion(request_id: str):
    """Worker function to generate the image in a background thread."""
    req = REQUESTS.get(request_id)
    if not req:
        return
        
    try:
        # Ensure model is loaded
        load_pipeline()
        
        # Move model to CUDA (GPU) for active generation
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            pipe.to("cuda")
            logging.info("Moved pipeline to GPU (CUDA) for active generation.")
            
        prompt = req["prompt"]
        logging.info(f"Starting generation for request {request_id} with prompt: '{prompt}'")
        
        # Configure the sampler scheduler dynamically
        scheduler_name = req.get("scheduler", "dpm++_2m_karras")
        logging.info(f"Configuring noise scheduler to: {scheduler_name}")
        
        from diffusers import EulerAncestralDiscreteScheduler, DPMSolverMultistepScheduler, DDIMScheduler
        
        if scheduler_name == "euler_a":
            pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        elif scheduler_name == "dpm++_2m_karras":
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
        elif scheduler_name == "dpm++_sde_karras":
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True, algorithm_type="sde-dpmsolver++")
        elif scheduler_name == "ddim":
            pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
            
        # Set up negative prompt
        default_neg = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry"
        custom_neg = req.get("negative_prompt")
        negative_prompt = f"{default_neg}, {custom_neg}" if custom_neg else default_neg
        
        width = req.get("width", 512)
        height = req.get("height", 512)
        steps = req.get("steps", 25)
        cfg_scale = req.get("cfg_scale", 7.0)
        
        logging.info(f"Running SD inference with parameters: Width={width}, Height={height}, Steps={steps}, CFG={cfg_scale}")
        
        # Run inference
        image = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=steps,
            guidance_scale=cfg_scale,
            width=width,
            height=height
        ).images[0]
        
        # Swin2SR 2x Upscale
        if req.get("upscale", False):
            try:
                logging.info("Running Swin2SR 2x upscale...")
                from transformers import Swin2SRForImageSuperResolution, Swin2SRImageProcessor
                
                upscale_model_id = "caidas/swin2SR-lightweight-x2-64"
                upscale_model = Swin2SRForImageSuperResolution.from_pretrained(upscale_model_id)
                upscale_processor = Swin2SRImageProcessor.from_pretrained(upscale_model_id)
                
                upscale_model = upscale_model.to(device)
                if device == "cuda":
                    upscale_model = upscale_model.half()
                
                # Preprocess image
                inputs = upscale_processor(image, return_tensors="pt")
                if device == "cuda":
                    inputs = {k: v.to("cuda", dtype=torch.float16) for k, v in inputs.items()}
                else:
                    inputs = {k: v.to("cpu") for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = upscale_model(**inputs)
                
                # Postprocess image
                output_data = outputs.reconstruction.data.squeeze().float().cpu().clamp_(0, 1).numpy()
                output_data = (output_data * 255.0).round().astype("uint8")
                output_data = output_data.transpose(1, 2, 0)
                
                from PIL import Image
                image = Image.fromarray(output_data)
                logging.info("Swin2SR 2x upscale completed successfully!")
                
                del upscale_model
                del upscale_processor
            except Exception as upscale_err:
                logging.error(f"Swin2SR upscaling failed, falling back to original: {upscale_err}")
        
        # Save output
        filename = f"{request_id}.png"
        image_path = os.path.join(OUTPUT_DIR, filename)
        image.save(image_path)
        
        req["status"] = "completed"
        req["image_path"] = image_path
        logging.info(f"Generation successful for request {request_id}. Image saved at {image_path}")
        
    except Exception as e:
        import torch
        logging.error(f"Error during Stable Diffusion generation: {str(e)}")
        req["status"] = "failed"
        err_msg = str(e)
        is_oom = "out of memory" in err_msg.lower() or "cuda out of memory" in err_msg.lower()
        if is_oom:
            req["error"] = "OOM: Aduh, senimanku mendadak pingsan karena memori GPU-nya gosong/kehabisan memori! 💥 (The artist's GPU got fried)"
        else:
            req["error"] = err_msg
    finally:
        # Aggressive memory offloading and cleanup
        import gc
        import torch
        try:
            if pipe is not None:
                pipe.to("cpu")
                logging.info("Offloaded pipeline back to CPU RAM.")
        except Exception as cpu_err:
            logging.error(f"Failed to offload model to CPU: {cpu_err}")
            
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logging.info("Cleared PyTorch CUDA cache aggressively.")

# --- API Middleware (Authentication) ---

def check_auth():
    api_key = request.headers.get("X-API-Key")
    if not api_key or not hmac.compare_digest(api_key, API_KEY):
        return False
    return True

# --- Web Endpoints ---

@app.route("/ping", methods=["GET"])
def ping():
    if not check_auth():
        return jsonify({"status": "unauthorized"}), 401
    return jsonify({"status": "online", "model": MODEL_ID}), 200

@app.route("/generate", methods=["POST"])
def generate():
    if not check_auth():
        return jsonify({"status": "unauthorized"}), 401
        
    data = request.json or {}
    
    # Check if there is already an active job (generating)
    active_jobs = [r for r in REQUESTS.values() if r["status"] == "generating"]
    if active_jobs:
        return jsonify({"error": "Maaf, senimanku sedang menggambar saat ini! Tolong tunggu sebentar ya. 🎨"}), 400
    
    # Clean up old requests if registry grows too large
    if len(REQUESTS) >= 100:
        now = datetime.now()
        to_delete = []
        for req_id, req in REQUESTS.items():
            req_time = datetime.fromisoformat(req["timestamp"])
            is_done = req["status"] in ("completed", "declined", "failed")
            if (is_done and now - req_time > timedelta(minutes=30)) or (now - req_time > timedelta(hours=24)):
                to_delete.append(req_id)
        for req_id in to_delete:
            REQUESTS.pop(req_id, None)
            
        # If still too large, cap it at 100 and pop oldest
        if len(REQUESTS) >= 100:
            sorted_keys = sorted(REQUESTS.keys(), key=lambda k: REQUESTS[k]["timestamp"])
            for k in sorted_keys[:len(REQUESTS) - 99]:
                REQUESTS.pop(k, None)

    prompt = data.get("prompt")
    username = data.get("username", "Unknown User")
    is_nsfw = data.get("is_nsfw", False)
    
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
        
    # SFW channel safety check (Saves memory, extremely fast, works without VRAM safety checker)
    if not is_nsfw:
        nsfw_blacklist = [
            "nsfw", "naked", "nude", "porn", "sex", "hentai", "ecchi", "breasts", "boobs", "ass", "pussy", "dick", "xxx", "undressed",
            "telanjang", "bugil", "senggama", "ngentot", "bokep", "mesum", "tetek", "pantat", "peler", "kontol", "memek", "payudara"
        ]
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in nsfw_blacklist):
            logging.warning(f"Blocked NSFW prompt '{prompt}' from {username} in SFW channel.")
            return jsonify({"error": "Konten NSFW tidak diperbolehkan di channel SFW!"}), 400
            
    # Check free VRAM before proceeding (smart peeking)
    try:
        import torch
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            free_gb = free_bytes / (1024 ** 3)
            logging.info(f"Smart Peeking VRAM Check: Free VRAM = {free_gb:.2f} GB / {total_bytes / (1024 ** 3):.2f} GB")
            required_vram = 2.5 if bool(data.get("upscale", False)) else 2.0
            if free_gb < required_vram:
                logging.warning(f"Insufficient VRAM: {free_gb:.2f} GB < {required_vram} GB. Rejecting request.")
                return jsonify({"error": "OOM: Aduh, senimanku mendadak pingsan karena memori GPU-nya gosong/kehabisan memori! 💥 (The artist's GPU got fried/busy)"}), 400
    except Exception as peek_err:
        logging.error(f"Smart peeking check failed: {peek_err}")

    request_id = str(uuid.uuid4())
    REQUESTS[request_id] = {
        "prompt": prompt,
        "negative_prompt": data.get("negative_prompt"),
        "username": username,
        "is_nsfw": is_nsfw,
        "status": "generating",
        "image_path": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
        "width": int(data.get("width", 512)),
        "height": int(data.get("height", 512)),
        "steps": int(data.get("steps", 25)),
        "cfg_scale": float(data.get("cfg_scale", 7.0)),
        "scheduler": data.get("scheduler", "dpm++_2m_karras"),
        "upscale": bool(data.get("upscale", False))
    }
    
    logging.info(f"Received generation request from {username}. Prompt: '{prompt}' | Channel NSFW: {is_nsfw} | Upscale: {data.get('upscale', False)}")
    
    # Run the Stable Diffusion generation in a background thread immediately
    threading.Thread(target=run_stable_diffusion, args=(request_id,), daemon=True).start()
    
    return jsonify({
        "status": "generating",
        "request_id": request_id
    }), 200

DEVICE_NAME = None

def get_device_name():
    global DEVICE_NAME
    if DEVICE_NAME is None:
        try:
            import torch
            DEVICE_NAME = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        except Exception:
            DEVICE_NAME = "CPU"
    return DEVICE_NAME

@app.route("/status/<request_id>", methods=["GET"])
def status(request_id):
    if not check_auth():
        return jsonify({"status": "unauthorized"}), 401
        
    req = REQUESTS.get(request_id)
    if not req:
        return jsonify({"error": "Request not found"}), 404
        
    return jsonify({
        "status": req["status"],
        "error": req["error"],
        "device": get_device_name()
    }), 200

@app.route("/image/<request_id>", methods=["GET"])
def get_image(request_id):
    if not check_auth():
        return jsonify({"status": "unauthorized"}), 401
        
    req = REQUESTS.get(request_id)
    if not req or req["status"] != "completed" or not req["image_path"]:
        return jsonify({"error": "Image not generated yet or request not found"}), 404
        
    return send_file(req["image_path"], mimetype="image/png")



if __name__ == "__main__":
    logging.info(f"Starting RVDiA Local GPU Pipeline Server on port {PORT}...")
    app.run(host="127.0.0.1", port=PORT, debug=False)
