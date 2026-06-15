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
   MODEL_ID_OR_PATH=genai-archive/anything-v5
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
MODEL_ID = os.getenv("MODEL_ID_OR_PATH", "genai-archive/anything-v5")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../scratch/gpu_outputs")
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
        
        # Save output
        filename = f"{request_id}.png"
        image_path = os.path.join(OUTPUT_DIR, filename)
        image.save(image_path)
        
        req["status"] = "completed"
        req["image_path"] = image_path
        logging.info(f"Generation successful for request {request_id}. Image saved at {image_path}")
        
    except Exception as e:
        logging.error(f"Error during Stable Diffusion generation: {str(e)}")
        req["status"] = "failed"
        req["error"] = str(e)
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

# --- Verification & Fallback Notifications ---

def generate_callback_token(request_id: str) -> str:
    """Generates a secure HMAC token to authorize callbacks."""
    return hmac.new(API_KEY.encode(), request_id.encode(), hashlib.sha256).hexdigest()

def show_notification(request_id: str, username: str, prompt: str):
    """Triggers Windows toast notification with action buttons or falls back to Tkinter dialog."""
    method = os.getenv("LAPTOP_NOTIFICATION_METHOD", "toast").lower()
    
    if method == "tkinter":
        logging.info("Bypassing toast notification. Using Tkinter dialog as requested.")
        run_tkinter_fallback(request_id, username, prompt)
        return

    # Try winotify first (native Windows Toast Notifications with Actions)
    try:
        from winotify import Notification
        
        token = generate_callback_token(request_id)
        toast = Notification(
            app_id="Windows PowerShell",
            title="Image Generation Request",
            msg=f"User: {username}\nPrompt: {prompt}",
            duration="long"
        )
        # Clicking these will launch the local callback URL in the browser
        toast.add_actions(
            label="Approve ✅", 
            launch=f"http://127.0.0.1:{PORT}/callback/approve?id={request_id}&token={token}"
        )
        toast.add_actions(
            label="Decline ❌", 
            launch=f"http://127.0.0.1:{PORT}/callback/decline?id={request_id}&token={token}"
        )
        toast.show()
        logging.info(f"Sent Winotify Toast notification for request {request_id}.")
        logging.info("Tip: If the toast did not appear, check your Windows Notification/Focus settings, or set LAPTOP_NOTIFICATION_METHOD=tkinter in .env")
        return
    except Exception as win_err:
        logging.info(f"winotify failed or not installed ({win_err}). Falling back to Tkinter dialog.")

    run_tkinter_fallback(request_id, username, prompt)

def run_tkinter_fallback(request_id: str, username: str, prompt: str):
    """Fallback: Tkinter Dialog Box in a background thread"""
    def run_tkinter():
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()  # Hide main window
            root.attributes("-topmost", True)  # Bring message box to front
            
            approved = messagebox.askyesno(
                "RVDiA Generation Gated Approval",
                f"Discord User: {username}\n\nRequested Prompt:\n\"{prompt}\"\n\nApprove this generation request?"
            )
            root.destroy()
            
            if approved:
                approve_generation(request_id)
            else:
                decline_generation(request_id)
        except Exception as tk_err:
            logging.error(f"Tkinter fallback notification failed: {tk_err}")
            # If all fails, auto-decline to prevent getting stuck
            decline_generation(request_id)

    threading.Thread(target=run_tkinter, daemon=True).start()

# --- Internal State Modifiers ---

def approve_generation(request_id: str):
    req = REQUESTS.get(request_id)
    if not req or req["status"] != "pending":
        return False
        
    req["status"] = "generating"
    # Run the Stable Diffusion generation in a background thread
    threading.Thread(target=run_stable_diffusion, args=(request_id,), daemon=True).start()
    logging.info(f"Request {request_id} has been APPROVED.")
    return True

def decline_generation(request_id: str):
    req = REQUESTS.get(request_id)
    if not req or req["status"] != "pending":
        return False
        
    req["status"] = "declined"
    logging.info(f"Request {request_id} has been DECLINED.")
    return True

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
    
    # Check if there is already an active job (pending or generating)
    active_jobs = [r for r in REQUESTS.values() if r["status"] in ("pending", "generating")]
    if active_jobs:
        return jsonify({"error": "Maaf, senimanku sedang menggambar/menunggu persetujuan untuk permintaan lain saat ini! Tolong tunggu sebentar ya. 🎨"}), 400
    
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

    # Check if there are too many pending requests (DoS protection)
    pending_count = sum(1 for req in REQUESTS.values() if req["status"] == "pending")
    if pending_count >= 10:
        return jsonify({"error": "Too many pending requests. Please wait until they are approved or processed."}), 429
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
            
    request_id = str(uuid.uuid4())
    REQUESTS[request_id] = {
        "prompt": prompt,
        "negative_prompt": data.get("negative_prompt"),
        "username": username,
        "is_nsfw": is_nsfw,
        "status": "pending",
        "image_path": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
        "width": int(data.get("width", 512)),
        "height": int(data.get("height", 512)),
        "steps": int(data.get("steps", 25)),
        "cfg_scale": float(data.get("cfg_scale", 7.0)),
        "scheduler": data.get("scheduler", "dpm++_2m_karras")
    }
    
    logging.info(f"Received generation request from {username}. Prompt: '{prompt}' | Channel NSFW: {is_nsfw}")
    
    # Trigger the Windows toast notification / dialog
    show_notification(request_id, username, prompt)
    
    return jsonify({
        "status": "pending",
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

# --- Notification Callback Endpoints ---

@app.route("/callback/approve", methods=["GET"])
def callback_approve():
    request_id = request.args.get("id")
    token = request.args.get("token")
    if not request_id or not token:
        return "Missing parameters", 400
        
    expected_token = generate_callback_token(request_id)
    if not hmac.compare_digest(token, expected_token):
        return "Unauthorized", 401
        
    success = approve_generation(request_id)
    
    if success:
        return """
        <html>
            <head><title>RVDiA Approved</title></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #1e1e2e; color: #cdd6f4;">
                <h1 style="color: #a6e3a1;">✅ Request Approved!</h1>
                <p>Starting image generation on GPU. You can close this tab now.</p>
            </body>
        </html>
        """
    else:
        return f"Request {request_id} already processed or invalid.", 400

@app.route("/callback/decline", methods=["GET"])
def callback_decline():
    request_id = request.args.get("id")
    token = request.args.get("token")
    if not request_id or not token:
        return "Missing parameters", 400
        
    expected_token = generate_callback_token(request_id)
    if not hmac.compare_digest(token, expected_token):
        return "Unauthorized", 401
        
    success = decline_generation(request_id)
    
    if success:
        return """
        <html>
            <head><title>RVDiA Declined</title></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background-color: #1e1e2e; color: #cdd6f4;">
                <h1 style="color: #f38ba8;">❌ Request Declined</h1>
                <p>The generation was cancelled. You can close this tab now.</p>
            </body>
        </html>
        """
    else:
        return f"Request {request_id} already processed or invalid.", 400

if __name__ == "__main__":
    logging.info(f"Starting RVDiA Local GPU Pipeline Server on port {PORT}...")
    app.run(host="127.0.0.1", port=PORT, debug=False)
