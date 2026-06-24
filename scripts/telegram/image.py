import cv2
import numpy as np
import logging

from scripts.utils.telegram import telegram_client, send_telegram_message, send_telegram_photo_bytes
from scripts.image.processing import (
    Image_Ops, Convolution, Enhancement, Edge_Detection,
    Equalization, Morphology, FreqFilter
)

async def get_telegram_image_bytes(message, telegram_user_id) -> tuple[bytes, str]:
    if not telegram_client:
        raise ValueError("Telegram client not initialized!")

    photo = message.get("photo")
    reply_to = message.get("reply_to_message")
    
    if photo:
        file_id = photo[-1]["file_id"]
        filename = "input.png"
    elif reply_to and reply_to.get("photo"):
        file_id = reply_to["photo"][-1]["file_id"]
        filename = "reply.png"
    else:
        file_id = await telegram_client.get_user_profile_photo_file_id(telegram_user_id)
        filename = "profile.png"
                        
    if not file_id:
        raise ValueError("No photo attachment or profile photo found!")

    img_bytes = await telegram_client.get_file_bytes(file_id)
    return img_bytes, filename

async def process_and_send_telegram_image(chat_id, message, telegram_user_id, lang, process_func, filename="processed.png", caption="", *args, **kwargs):
    try:
        if telegram_client:
            await telegram_client.send_chat_action(chat_id, "upload_photo")

        # 1. Download image bytes
        try:
            image_bytes, origin_filename = await get_telegram_image_bytes(message, telegram_user_id)
        except Exception as e:
            err_msg = (
                "⚠️ <b>No photo attachment or profile photo found!</b>\n\n"
                "To use your profile picture, please ensure your Profile Photo privacy is set to <b>'Everybody'</b> in Telegram settings (<i>Settings > Privacy and Security > Profile Photos</i>).\n\n"
                "Alternatively, you can upload a photo directly and use the command as a caption, or reply to an existing photo in the chat!"
            ) if lang == "en" else (
                "⚠️ <b>Tidak ada lampiran foto atau foto profil ditemukan!</b>\n\n"
                "Untuk menggunakan foto profil Anda, pastikan privasi Foto Profil Anda diatur ke <b>'Semua Orang'</b> (Everybody) di pengaturan Telegram (<i>Pengaturan > Privasi dan Keamanan > Foto Profil</i>).\n\n"
                "Alternatif lain, Anda dapat mengunggah foto secara langsung dan menggunakan command sebagai caption, atau membalas (reply) foto yang sudah ada di chat!"
            )
            return await send_telegram_message(chat_id, err_msg)

        # 2. Convert to OpenCV formats
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            err_msg = "❌ Failed to read the image file." if lang == "en" else "❌ Gagal membaca file gambar."
            return await send_telegram_message(chat_id, err_msg)

        # Convert BGR to RGB for scripts.image.processing
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 3. Process image
        result = process_func(img_rgb, *args, **kwargs)

        # Convert RGB back to BGR for saving
        if result.ndim == 3:
            if result.shape[2] == 3:
                result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
            else:
                result_bgr = result[..., :3]
        else:
            result_bgr = result

        # Encode BGR back to bytes
        _, buffer = cv2.imencode('.png', result_bgr)
        processed_bytes = buffer.tobytes()

        # 4. Send photo
        await send_telegram_photo_bytes(chat_id, processed_bytes, filename=filename, caption=caption)

    except Exception as e:
        logging.error(f"Error processing Telegram image: {e}", exc_info=True)
        err_msg = f"❌ Error processing image: {str(e)}" if lang == "en" else f"❌ Terjadi kesalahan saat memproses gambar: {str(e)}"
        await send_telegram_message(chat_id, err_msg)

def setup(zora):
    image_filters = [
        "/grayscale", "/invert", "/circle", "/sepia", "/blur", "/sharpen", "/emboss",
        "/pixelate", "/vignette", "/gamma", "/flip", "/rotate", "/adjust", "/edge",
        "/noise", "/equalize", "/threshold", "/erode", "/dilate", "/skeleton",
        "/lpf", "/hpf", "/homomorphic", "/fourier_modulate", "/fft", "/dct", "/posterize", "/solarize",
        "/sketch", "/image_eval", "/ieval"
    ]

    @zora.command(image_filters)
    async def handle_image_filter(zora_bot, chat_id, telegram_user_id, username, full_name, command, args, message, lang):
        cmd_name = command.lstrip("/")
        filename = "processed.png"
        caption = "🎨 Filter Applied!" if lang == "en" else "🎨 Filter Diterapkan!"
        func = None

        try:
            if cmd_name == "grayscale":
                func = Image_Ops.to_grayscale
                filename = "grayscale.png"
                caption = "🎨 Grayscale Filter Applied!" if lang == "en" else "🎨 Filter Grayscale Diterapkan!"
            elif cmd_name == "invert":
                func = Image_Ops.invert
                filename = "invert.png"
                caption = "🎨 Colors Inverted!" if lang == "en" else "🎨 Warna Dibalik!"
            elif cmd_name == "circle":
                func = Image_Ops.crop_circle
                filename = "circle.png"
                caption = "🎨 Circular Crop Applied!" if lang == "en" else "🎨 Potongan Lingkaran Diterapkan!"
            elif cmd_name == "sepia":
                def apply_sepia(img):
                    img_f = img.astype(np.float32)
                    sepia_matrix = np.array([[0.393, 0.769, 0.189],
                                             [0.349, 0.686, 0.168],
                                             [0.272, 0.534, 0.131]])
                    sepia_img = cv2.transform(img_f, sepia_matrix)
                    return np.clip(sepia_img, 0, 255).astype(np.uint8)
                func = apply_sepia
                filename = "sepia.png"
                caption = "🎨 Warm Sepia Tone Applied!" if lang == "en" else "🎨 Nada Sepia Hangat Diterapkan!"
            elif cmd_name == "blur":
                strength = 5
                if args:
                    try: strength = int(args[0])
                    except ValueError: pass
                def apply_blur(img, s=strength):
                    kernel = Convolution.Kernels.box_blur(s)
                    return Convolution.apply(img, kernel)
                func = apply_blur
                filename = "blur.png"
                caption = f"🎨 Blur Filter (strength={strength}) Applied!" if lang == "en" else f"🎨 Filter Blur (strength={strength}) Diterapkan!"
            elif cmd_name == "sharpen":
                def apply_sharpen(img):
                    kernel = Convolution.Kernels.sharpen()
                    return Convolution.apply(img, kernel)
                func = apply_sharpen
                filename = "sharpen.png"
                caption = "🎨 Image Details Sharpened!" if lang == "en" else "🎨 Detail Gambar Ditajamkan!"
            elif cmd_name == "emboss":
                def apply_emboss(img):
                    return Convolution.apply(img, Convolution.Kernels.emboss())
                func = apply_emboss
                filename = "emboss.png"
                caption = "🎨 3D Emboss Filter Applied!" if lang == "en" else "🎨 Filter Emboss 3D Diterapkan!"
            elif cmd_name == "pixelate":
                size = 16
                if args:
                    try: size = int(args[0])
                    except ValueError: pass
                def apply_pixelate(img, sz=size):
                    h, w = img.shape[:2]
                    small = cv2.resize(img, (max(1, w // sz), max(1, h // sz)), interpolation=cv2.INTER_LINEAR)
                    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                func = apply_pixelate
                filename = "pixelate.png"
                caption = f"🎨 Pixelated (size={size}) Applied!" if lang == "en" else f"🎨 Pixelated (size={size}) Diterapkan!"
            elif cmd_name == "vignette":
                sigma = 150
                if args:
                    try: sigma = int(args[0])
                    except ValueError: pass
                def apply_vignette(img, s=sigma):
                    h, w = img.shape[:2]
                    kernel_x = cv2.getGaussianKernel(w, s)
                    kernel_y = cv2.getGaussianKernel(h, s)
                    kernel = kernel_y * kernel_x.T
                    mask = kernel / kernel.max()
                    vignette_img = np.copy(img)
                    for i in range(min(3, img.ndim)):
                        if img.ndim == 3:
                            vignette_img[:, :, i] = vignette_img[:, :, i] * mask
                        else:
                            vignette_img = vignette_img * mask
                    return vignette_img.astype(np.uint8)
                func = apply_vignette
                filename = "vignette.png"
                caption = f"🎨 Vignette Filter (sigma={sigma}) Applied!" if lang == "en" else f"🎨 Filter Vignette (sigma={sigma}) Diterapkan!"
            elif cmd_name == "gamma":
                gamma_val = 1.5
                if args:
                    try: gamma_val = float(args[0])
                    except ValueError: pass
                func = lambda img: Enhancement.gamma_correction(img, gamma_val)
                filename = "gamma.png"
                caption = f"🎨 Gamma Correction (gamma={gamma_val}) Applied!" if lang == "en" else f"🎨 Koreksi Gamma (gamma={gamma_val}) Diterapkan!"
            elif cmd_name == "flip":
                axis = "horizontal"
                if args and args[0].lower() in ["horizontal", "vertical", "h", "v"]:
                    axis = "vertical" if args[0].lower() in ["vertical", "v"] else "horizontal"
                func = lambda img: Image_Ops.flip(img, axis)
                filename = "flip.png"
                caption = f"🎨 Image Flipped ({axis})!" if lang == "en" else f"🎨 Gambar Dibalik ({axis})!"
            elif cmd_name == "rotate":
                angle = 90.0
                direction = "ccw"
                if args:
                    try: angle = float(args[0])
                    except ValueError: pass
                    if len(args) > 1 and args[1].lower() in ["cw", "ccw"]:
                        direction = args[1].lower()
                func = lambda img: Image_Ops.rotate(img, angle, direction)
                filename = "rotate.png"
                caption = f"🎨 Rotated {angle}° {direction.upper()}!" if lang == "en" else f"🎨 Diputar {angle}° {direction.upper()}!"
            elif cmd_name == "adjust":
                brightness = 1.0
                contrast = 0
                if args:
                    try: brightness = float(args[0])
                    except ValueError: pass
                    if len(args) > 1:
                        try: contrast = int(args[1])
                        except ValueError: pass
                func = lambda img: Enhancement.brightness_contrast(img, brightness, contrast)
                filename = "adjust.png"
                caption = f"🎨 Adjusted (brightness={brightness}, contrast={contrast})!" if lang == "en" else f"🎨 Disesuaikan (brightness={brightness}, contrast={contrast})!"
            elif cmd_name == "edge":
                method = "canny"
                if args and args[0].lower() in ["canny", "sobel", "laplacian", "prewitt", "roberts", "scharr"]:
                    method = args[0].lower()
                def apply_edge(img):
                    if method == "canny": res = Edge_Detection.canny(img)
                    elif method == "sobel": res = Edge_Detection.sobel(img)
                    elif method == "laplacian": res = Edge_Detection.laplacian(img)
                    elif method == "prewitt": res = Edge_Detection.prewitt(img)
                    elif method == "roberts": res = Edge_Detection.roberts(img)
                    else: res = Edge_Detection.scharr(img)
                    if res.ndim == 2:
                        return cv2.cvtColor(res, cv2.COLOR_GRAY2RGB)
                    return res
                func = apply_edge
                filename = f"edge_{method}.png"
                caption = f"🎨 Edge Detection ({method.upper()}) Applied!" if lang == "en" else f"🎨 Deteksi Tepi ({method.upper()}) Diterapkan!"
            elif cmd_name == "noise":
                ntype = "salt_pepper"
                if args and args[0].lower() in ["salt_pepper", "gaussian", "poisson"]:
                    ntype = args[0].lower()
                if ntype == "salt_pepper": func = Image_Ops.add_salt_pepper
                elif ntype == "gaussian": func = Enhancement.add_gaussian_noise
                else: func = Enhancement.add_poisson_noise
                filename = "noise.png"
                caption = f"🎨 Noise Added ({ntype})!" if lang == "en" else f"🎨 Kebisingan Ditambahkan ({ntype})!"
            elif cmd_name == "equalize":
                method = "global"
                if args and args[0].lower() in ["global", "clahe", "adaptive"]:
                    method = args[0].lower()
                if method == "global": func = Equalization.equalize
                elif method == "clahe": func = Equalization.clahe
                else: func = Equalization.adaptive
                filename = "equalize.png"
                caption = f"🎨 Histogram Equalized ({method})!" if lang == "en" else f"🎨 Ekualisasi Histogram ({method})!"
            elif cmd_name == "threshold":
                val = 127
                method = "binary"
                if args:
                    try: val = int(args[0])
                    except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["binary", "otsu"]:
                    method = args[1].lower()
                func = lambda img: Image_Ops.threshold(img, val, method == "otsu")
                filename = "threshold.png"
                caption = f"🎨 Threshold Binarization ({method.upper()}, cutoff={val}) Applied!" if lang == "en" else f"🎨 Binarisasi Ambang Batas ({method.upper()}, cutoff={val}) Diterapkan!"
            elif cmd_name == "erode":
                iter_count = 1
                k_size = 3
                if args:
                    try: iter_count = int(args[0])
                    except ValueError: pass
                    if len(args) > 1:
                        try: k_size = int(args[1])
                        except ValueError: pass
                func = lambda img: Morphology.erode(img, k_size, iter_count)
                filename = "erode.png"
                caption = f"🎨 Morphological Erosion (iterations={iter_count}, kernel={k_size})!" if lang == "en" else f"🎨 Erosi Morfologis (iterations={iter_count}, kernel={k_size})!"
            elif cmd_name == "dilate":
                iter_count = 1
                k_size = 3
                if args:
                    try: iter_count = int(args[0])
                    except ValueError: pass
                    if len(args) > 1:
                        try: k_size = int(args[1])
                        except ValueError: pass
                func = lambda img: Morphology.dilate(img, k_size, iter_count)
                filename = "dilate.png"
                caption = f"🎨 Morphological Dilation (iterations={iter_count}, kernel={k_size})!" if lang == "en" else f"🎨 Dilatasi Morfologis (iterations={iter_count}, kernel={k_size})!"
            elif cmd_name == "skeleton":
                def apply_skeleton(img):
                    if img.ndim == 3:
                        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    else:
                        gray = img
                    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    skel = Morphology.skeleton(binary)
                    return cv2.cvtColor(skel, cv2.COLOR_GRAY2RGB)
                func = apply_skeleton
                filename = "skeleton.png"
                caption = "🎨 Topological Skeleton Extracted!" if lang == "en" else "🎨 Rangka Topologi Diekstrak!"
            elif cmd_name == "lpf":
                cutoff = 30.0
                ftype = "gaussian"
                order = 2
                if args:
                    try: cutoff = float(args[0])
                    except ValueError: pass
                    if len(args) > 1 and args[1].lower() in ["ideal", "butterworth", "gaussian"]:
                        ftype = args[1].lower()
                    if len(args) > 2:
                        try: order = int(args[2])
                        except ValueError: pass
                def apply_lpf(img):
                    if ftype == "ideal": return FreqFilter.ideal_lpf(img, cutoff)
                    elif ftype == "butterworth": return FreqFilter.butterworth_lpf(img, cutoff, order)
                    return FreqFilter.gaussian_lpf(img, cutoff)
                func = apply_lpf
                filename = "lpf.png"
                caption = f"🎨 Frequency Low-Pass Filter ({ftype.upper()}, cutoff={cutoff}) Applied!" if lang == "en" else f"🎨 Filter Low-Pass Frekuensi ({ftype.upper()}, cutoff={cutoff}) Diterapkan!"
            elif cmd_name == "hpf":
                cutoff = 30.0
                ftype = "gaussian"
                order = 2
                if args:
                    try: cutoff = float(args[0])
                    except ValueError: pass
                    if len(args) > 1 and args[1].lower() in ["ideal", "butterworth", "gaussian"]:
                        ftype = args[1].lower()
                    if len(args) > 2:
                        try: order = int(args[2])
                        except ValueError: pass
                def apply_hpf(img):
                    if ftype == "ideal": return FreqFilter.ideal_hpf(img, cutoff)
                    elif ftype == "butterworth": return FreqFilter.butterworth_hpf(img, cutoff, order)
                    return FreqFilter.gaussian_hpf(img, cutoff)
                func = apply_hpf
                filename = "hpf.png"
                caption = f"🎨 Frequency High-Pass Filter ({ftype.upper()}, cutoff={cutoff}) Applied!" if lang == "en" else f"🎨 Filter High-Pass Frekuensi ({ftype.upper()}, cutoff={cutoff}) Diterapkan!"
            elif cmd_name == "homomorphic":
                gamma_l = 0.5
                gamma_h = 2.0
                cutoff = 30.0
                if args:
                    try: gamma_l = float(args[0])
                    except ValueError: pass
                    if len(args) > 1:
                        try: gamma_h = float(args[1])
                        except ValueError: pass
                    if len(args) > 2:
                        try: cutoff = float(args[2])
                        except ValueError: pass
                func = lambda img: FreqFilter.homomorphic(img, gamma_l, gamma_h, cutoff)
                filename = "homomorphic.png"
                caption = f"🎨 Homomorphic Filter (gamma_l={gamma_l}, gamma_h={gamma_h}) Applied!" if lang == "en" else f"🎨 Filter Homomorfik (gamma_l={gamma_l}, gamma_h={gamma_h}) Diterapkan!"
            elif cmd_name == "fourier_modulate":
                frequency = 0.05
                angle = 45.0
                if args:
                    try: frequency = float(args[0])
                    except ValueError: pass
                    if len(args) > 1:
                        try: angle = float(args[1])
                        except ValueError: pass
                func = lambda img: FreqFilter.modulate(img, frequency, angle)
                filename = "modulation_theorem.png"
                caption = f"📐 Fourier Modulation Theorem (frequency={frequency}, angle={angle}°)" if lang == "en" else f"📐 Teorema Modulasi Fourier (frequency={frequency}, angle={angle}°)"
            elif cmd_name == "fft":
                func = FreqFilter.fft
                filename = "fft_spectrum.png"
                caption = "📊 Log-Scaled FFT Magnitude Spectrum" if lang == "en" else "📊 Spektrum Magnitudo FFT Skala Log"
            elif cmd_name == "dct":
                func = FreqFilter.dct
                filename = "dct_spectrum.png"
                caption = "📊 Log-Scaled DCT Magnitude Spectrum" if lang == "en" else "📊 Spektrum Magnitudo DCT Skala Log"
            elif cmd_name == "posterize":
                levels = 4
                if args:
                    try: levels = int(args[0])
                    except ValueError: pass
                func = lambda img: Image_Ops.posterize(img, levels)
                filename = "posterize.png"
                caption = f"🎨 Posterize Filter (levels={levels}) Applied!" if lang == "en" else f"🎨 Filter Posterisasi (levels={levels}) Diterapkan!"
            elif cmd_name == "solarize":
                threshold = 128
                if args:
                    try: threshold = int(args[0])
                    except ValueError: pass
                func = lambda img: Image_Ops.solarize(img, threshold)
                filename = "solarize.png"
                caption = f"🎨 Solarization Filter (threshold={threshold}) Applied!" if lang == "en" else f"🎨 Filter Solarisasi (threshold={threshold}) Diterapkan!"
            elif cmd_name == "sketch":
                ksize = 21
                if args:
                    try: ksize = int(args[0])
                    except ValueError: pass
                func = lambda img: Image_Ops.pencil_sketch(img, ksize)
                filename = "sketch.png"
                caption = f"🎨 Pencil Sketch Filter (ksize={ksize}) Applied!" if lang == "en" else f"🎨 Filter Sketsa Pensil (ksize={ksize}) Diterapkan!"
            elif cmd_name in ["image_eval", "ieval"]:
                if not args:
                    err_msg = "⚠️ Please specify a pipeline string (e.g. /image_eval grayscale,invert)" if lang == "en" else "⚠️ Harap tentukan string pipeline (misal: /image_eval grayscale,invert)"
                    return await send_telegram_message(chat_id, err_msg)
                pipeline_str = args[0]
                
                reply_to = message.get("reply_to_message")
                img2_bytes = None
                if reply_to and reply_to.get("photo"):
                    photo1 = reply_to["photo"]
                    file_id1 = photo1[-1]["file_id"]
                    img1_bytes = await telegram_client.get_file_bytes(file_id1)
                    
                    if message.get("photo"):
                        photo2 = message["photo"]
                        file_id2 = photo2[-1]["file_id"]
                        img2_bytes = await telegram_client.get_file_bytes(file_id2)
                else:
                    if message.get("photo"):
                        photo1 = message["photo"]
                        file_id1 = photo1[-1]["file_id"]
                        img1_bytes = await telegram_client.get_file_bytes(file_id1)
                    else:
                        file_id1 = await telegram_client.get_user_profile_photo_file_id(telegram_user_id)
                        if not file_id1:
                            err_msg = (
                                "⚠️ <b>No photo attachment or profile photo found!</b>\n\n"
                                "To use your profile picture, please ensure your Profile Photo privacy is set to <b>'Everybody'</b> in Telegram settings (<i>Settings > Privacy and Security > Profile Photos</i>).\n\n"
                                "Alternatively, you can upload a photo directly and use the command as a caption, or reply to an existing photo in the chat!"
                            ) if lang == "en" else (
                                "⚠️ <b>Tidak ada lampiran foto atau foto profil ditemukan!</b>\n\n"
                                "Untuk menggunakan foto profil Anda, pastikan privasi Foto Profil Anda diatur ke <b>'Semua Orang'</b> (Everybody) di pengaturan Telegram (<i>Pengaturan > Privasi dan Keamanan > Foto Profil</i>).\n\n"
                                "Alternatif lain, Anda dapat mengunggah foto secara langsung dan menggunakan command sebagai caption, atau membalas (reply) foto yang sudah ada di chat!"
                            )
                            return await send_telegram_message(chat_id, err_msg)
                        img1_bytes = await telegram_client.get_file_bytes(file_id1)
                        
                img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
                if img1 is None:
                    err_msg = "❌ Failed to read the image file." if lang == "en" else "❌ Gagal membaca file gambar."
                    return await send_telegram_message(chat_id, err_msg)
                img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
                
                img2_rgb = None
                if img2_bytes:
                    img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
                    if img2 is not None:
                        img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)
                        
                func = lambda img: Image_Ops.eval_pipeline(img, pipeline_str, img2_rgb)
                filename = "eval.png"
                caption = "🎨 Pipeline Evaluation Completed!" if lang == "en" else "🎨 Evaluasi Pipeline Selesai!"

            if func is None:
                return

            await process_and_send_telegram_image(chat_id, message, telegram_user_id, lang, func, filename=filename, caption=caption)

        except Exception as e:
            logging.error(f"Error handling Telegram image command: {e}", exc_info=True)
            err_msg = f"❌ Error: {str(e)}"
            await send_telegram_message(chat_id, err_msg)
