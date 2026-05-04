from typing import Literal, Sequence, Any
import numpy as np
import cv2
import matplotlib.pyplot as plt
import os

# ═══════════════════════════════════════════════════════════════════════════════
#  GPU Backend — Automatic CuPy dispatch with CPU fallback
# ═══════════════════════════════════════════════════════════════════════════════

try:
    import cupy as cp
    _GPU_AVAILABLE = True
    _GPU_NAME = cp.cuda.runtime.getDeviceProperties(0)["name"].decode()
    _GPU_VRAM_MB = cp.cuda.Device(0).mem_info[1] // (1024 * 1024)
except (ImportError, Exception):
    cp = None
    _GPU_AVAILABLE = False
    _GPU_NAME = None
    _GPU_VRAM_MB = 0

# smart dispatch threshold — images smaller than this stay on CPU
GPU_MIN_PIXELS = 256 * 256

# force mode: None = auto, True = always GPU, False = always CPU
_FORCE_GPU: bool | None = None


def gpu_available() -> bool:
    """Check if GPU backend is available."""
    return _GPU_AVAILABLE


def gpu_info() -> None:
    """Print GPU backend status."""
    if _GPU_AVAILABLE:
        print(f"🚀 GPU backend  : CuPy + CUDA ({_GPU_NAME})")
        thr = int(GPU_MIN_PIXELS ** 0.5)
        print(f"📐 Smart dispatch: images ≥{thr}×{thr} → GPU, smaller → CPU")
        print(f"💾 VRAM          : {_GPU_VRAM_MB} MB")
    else:
        print("💤 GPU not available — using NumPy (CPU)")


def set_gpu_mode(mode: bool | None) -> None:
    """Force GPU mode. None=auto, True=always GPU, False=always CPU."""
    global _FORCE_GPU
    _FORCE_GPU = mode
    thr = int(GPU_MIN_PIXELS ** 0.5)
    if mode is True:
        print("⚡ Forced GPU mode — all images processed on GPU")
    elif mode is False:
        print("🐌 Forced CPU mode — all images processed on CPU")
    else:
        print(f"🧠 Auto mode — GPU for images ≥{thr}×{thr}")


def _should_gpu(image) -> bool:
    """Decide whether to dispatch this image to GPU."""
    if not _GPU_AVAILABLE:
        return False
    if _FORCE_GPU is True:
        return True
    if _FORCE_GPU is False:
        return False
    # auto mode: check dimensions
    if hasattr(image, "shape") and len(image.shape) >= 2:
        return image.shape[0] * image.shape[1] >= GPU_MIN_PIXELS
    return False


def _xp(arr):
    """Get the array module (numpy or cupy) for the given array."""
    if _GPU_AVAILABLE and isinstance(arr, cp.ndarray):
        return cp
    return np


def to_gpu(arr):
    """Move ndarray to GPU."""
    if _GPU_AVAILABLE and isinstance(arr, np.ndarray):
        return cp.asarray(arr)
    return arr


def to_cpu(arr):
    """Move array to CPU numpy (needed before cv2/matplotlib)."""
    if _GPU_AVAILABLE and isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return arr


def _smart(image):
    """Smart transfer — auto GPU/CPU based on image dimensions."""
    if _should_gpu(image) and isinstance(image, np.ndarray):
        return cp.asarray(image)
    return image


# print status on import
if _GPU_AVAILABLE:
    _thr = int(GPU_MIN_PIXELS ** 0.5)
    print(f"[accelerated] 🚀 GPU: {_GPU_NAME} ({_GPU_VRAM_MB} MB) | auto ≥{_thr}px")
    del _thr
else:
    print("[accelerated] 💤 CPU mode (CuPy not found)")


ArrayLike = np.ndarray
AxisMode = Literal["horizontal", "vertical"]
MatchMode = Literal["pad", "resize"]
PadMode = Literal["constant", "edge", "reflect", "symmetric", "wrap", "zero", "none"]
InterpMode = Literal["nearest", "linear", "area", "cubic", "lanczos"]
RotDir = Literal["ccw", "cw"]

# ═══════════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_image(image: ArrayLike, *, name: str = "image") -> ArrayLike:
    if _GPU_AVAILABLE and isinstance(image, cp.ndarray):
        if image.ndim not in (2, 3):
            raise ValueError(f"{name} must be 2D (grayscale) or 3D (color).")
        if image.size == 0:
            raise ValueError(f"{name} cannot be empty.")
        return image
    if not isinstance(image, np.ndarray):
        raise TypeError(f"{name} must be a numpy.ndarray (or cupy.ndarray with GPU).")
    if image.ndim not in (2, 3):
        raise ValueError(f"{name} must be 2D (grayscale) or 3D (color).")
    if image.size == 0:
        raise ValueError(f"{name} cannot be empty.")
    return image


def _match_channels(a: ArrayLike, b: ArrayLike) -> tuple[ArrayLike, ArrayLike]:
    xp_a = _xp(a)
    xp_b = _xp(b)
    if a.ndim == b.ndim:
        return a, b
    if a.ndim == 2 and b.ndim == 3:
        a = xp_a.repeat(a[..., None], b.shape[2], axis=2)
    elif a.ndim == 3 and b.ndim == 2:
        b = xp_b.repeat(b[..., None], a.shape[2], axis=2)
    return a, b


def _resize_to(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    if target_h <= 0 or target_w <= 0:
        raise ValueError("target size must be positive.")
    cpu_img = to_cpu(image)
    return cv2.resize(cpu_img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)


def _pad_to(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    xp_mod = _xp(image)
    h, w = image.shape[:2]
    if h > target_h or w > target_w:
        raise ValueError("target size must be >= image size for padding.")
    if image.ndim == 2:
        out = xp_mod.zeros((target_h, target_w), dtype=image.dtype)
        out[:h, :w] = image
    else:
        c = image.shape[2]
        out = xp_mod.zeros((target_h, target_w, c), dtype=image.dtype)
        out[:h, :w, :] = image
    return out


def _interp_flag(mode: InterpMode) -> int:
    return {
        "nearest": cv2.INTER_NEAREST,
        "linear": cv2.INTER_LINEAR,
        "area": cv2.INTER_AREA,
        "cubic": cv2.INTER_CUBIC,
        "lanczos": cv2.INTER_LANCZOS4,
    }[mode]


def _center_crop_or_pad(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    """Center-crops if larger; center-pads with zeros if smaller."""
    image = _validate_image(image)
    xp_mod = _xp(image)
    if target_h <= 0 or target_w <= 0:
        raise ValueError("target size must be positive.")
    h, w = image.shape[:2]
    if h > target_h:
        y0 = (h - target_h) // 2
        image = image[y0 : y0 + target_h, ...]
    if w > target_w:
        x0 = (w - target_w) // 2
        image = image[:, x0 : x0 + target_w, ...]
    h, w = image.shape[:2]
    if h < target_h or w < target_w:
        pad_y_total = target_h - h
        pad_x_total = target_w - w
        pad_top = pad_y_total // 2
        pad_bottom = pad_y_total - pad_top
        pad_left = pad_x_total // 2
        pad_right = pad_x_total - pad_left
        if image.ndim == 2:
            image = xp_mod.pad(image, ((pad_top, pad_bottom), (pad_left, pad_right)), mode="constant", constant_values=0)
        else:
            image = xp_mod.pad(image, ((pad_top, pad_bottom), (pad_left, pad_right), (0, 0)), mode="constant", constant_values=0)
    return image


# ═══════════════════════════════════════════════════════════════════════════════
#  Histogram
# ═══════════════════════════════════════════════════════════════════════════════

class Histogram:
    """Static helpers for histogram computation, display, and comparison."""

    @staticmethod
    def compute(image: ArrayLike, bins: int = 256, value_range: tuple[int, int] = (0, 256)) -> ArrayLike:
        """Returns raw histogram array(s). Shape (bins,) for gray, (bins, C) for color."""
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if image.ndim == 2:
            hist, _ = xp_mod.histogram(image.ravel(), bins=bins, range=value_range)
            return hist
        hists = []
        for ch in range(image.shape[2]):
            h, _ = xp_mod.histogram(image[..., ch].ravel(), bins=bins, range=value_range)
            hists.append(h)
        return xp_mod.stack(hists, axis=-1)

    @staticmethod
    def compute_cdf(image: ArrayLike) -> ArrayLike:
        """Returns the normalized CDF. Shape (256,) for gray, (256, C) for color."""
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if image.ndim == 2:
            hist, _ = xp_mod.histogram(image.ravel(), bins=256, range=(0, 256))
            cdf = xp_mod.cumsum(hist).astype(xp_mod.float64)
            return cdf / (cdf[-1] + 1e-8)
        cdfs = []
        for ch in range(image.shape[2]):
            hist, _ = xp_mod.histogram(image[..., ch].ravel(), bins=256, range=(0, 256))
            cdf = xp_mod.cumsum(hist).astype(xp_mod.float64)
            cdfs.append(cdf / (cdf[-1] + 1e-8))
        return xp_mod.stack(cdfs, axis=-1)

    @staticmethod
    def show(image: ArrayLike, title: str = "Histogram", normalize: bool = False, color: str = "black") -> None:
        """Display histogram for a single image."""
        image = to_cpu(_validate_image(image))
        plt.figure(figsize=(7, 4))
        if image.ndim == 2:
            plt.hist(image.ravel(), bins=256, range=(0, 256), color=color, density=normalize)
        else:
            colors = ["r", "g", "b"]
            for i, c in enumerate(colors[: image.shape[2]]):
                plt.hist(image[..., i].ravel(), bins=256, range=(0, 256), color=c, alpha=0.5, density=normalize)
        plt.title(title)
        plt.xlabel("Pixel value")
        plt.ylabel("Probability Density" if normalize else "Frequency")
        plt.show()

    @staticmethod
    def show_multi(
        images: Sequence[ArrayLike], *, titles: Sequence[str] | None = None,
        colors: Sequence[str | Sequence[str]] | None = None, normalize: bool = False,
        bins: int = 256, value_range: tuple[int, int] = (0, 256),
        ncols: int = 3, figsize: tuple[int, int] | None = None,
    ) -> None:
        """Show N histograms in one figure."""
        if not isinstance(images, Sequence) or len(images) == 0:
            raise ValueError("images must be a non-empty sequence of images.")
        N = len(images)
        if titles is not None and len(titles) != N:
            raise ValueError(f"titles length must match images length ({N}).")
        if colors is not None and len(colors) != N:
            raise ValueError(f"colors length must match images length ({N}).")
        if ncols < 1:
            raise ValueError("ncols must be >= 1.")
        nrows = int(np.ceil(N / ncols))
        if figsize is None:
            figsize = (5 * ncols, 3 * nrows)
        plt.figure(figsize=figsize)
        for i, img in enumerate(images):
            img = to_cpu(_validate_image(img, name=f"images[{i}]"))
            title = titles[i] if titles is not None else f"Histogram {i}"
            color_cfg = colors[i] if colors is not None else "black"
            plt.subplot(nrows, ncols, i + 1)
            plt.title(title)
            plt.xlabel("Pixel value")
            plt.ylabel("Probability Density" if normalize else "Frequency")
            if img.ndim == 2:
                c = color_cfg if isinstance(color_cfg, str) else "black"
                plt.hist(img.ravel(), bins=bins, range=value_range, color=c, density=normalize)
            else:
                if isinstance(color_cfg, (list, tuple)):
                    ch_colors = list(color_cfg)
                    for ch in range(min(img.shape[2], len(ch_colors))):
                        plt.hist(img[..., ch].ravel(), bins=bins, range=value_range, color=ch_colors[ch], alpha=0.5, density=normalize)
                else:
                    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    plt.hist(gray.ravel(), bins=bins, range=value_range, color=str(color_cfg), density=normalize)
        plt.tight_layout()
        plt.show()

    @staticmethod
    def show_cdf(image: ArrayLike, title: str = "CDF") -> None:
        """Plot the cumulative distribution function of an image."""
        image = to_cpu(_validate_image(image))
        plt.figure(figsize=(7, 4))
        if image.ndim == 2:
            cdf = to_cpu(Histogram.compute_cdf(image))
            plt.plot(np.arange(256), cdf, color="black")
        else:
            colors_list = ["r", "g", "b"]
            cdf = to_cpu(Histogram.compute_cdf(image))
            for ch in range(min(image.shape[2], 3)):
                plt.plot(np.arange(256), cdf[:, ch], color=colors_list[ch], alpha=0.7)
        plt.title(title)
        plt.xlabel("Pixel value")
        plt.ylabel("Cumulative probability")
        plt.xlim(0, 255)
        plt.ylim(0, 1)
        plt.show()

    @staticmethod
    def show_original_and_normalized(
        image: ArrayLike, title_left: str = "Histogram", title_right: str = "Histogram (Normalized)"
    ) -> None:
        image = to_cpu(_validate_image(image))
        plt.figure(figsize=(12, 5))
        for i in range(2):
            title = title_left if i == 0 else title_right
            color = "green" if i == 0 else "blue"
            normalize = i == 1
            plt.subplot(1, 2, i + 1)
            plt.title(title)
            if image.ndim == 2:
                plt.hist(image.ravel(), bins=256, range=(0, 256), color=color, density=normalize)
            else:
                colors = ["r", "g", "b"]
                for j, c in enumerate(colors[: image.shape[2]]):
                    plt.hist(image[..., j].ravel(), bins=256, range=(0, 256), color=c, alpha=0.5, density=normalize)
            plt.xlabel("Pixel value")
            plt.ylabel("Probability Density" if normalize else "Frequency")
        plt.show()

    @staticmethod
    def compare(img1: ArrayLike, img2: ArrayLike, title1: str = "Image 1", title2: str = "Image 2", normalize: bool = False) -> None:
        """Side-by-side histogram comparison of two images."""
        Histogram.show_multi([img1, img2], titles=[title1, title2], normalize=normalize, ncols=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  Convolution
# ═══════════════════════════════════════════════════════════════════════════════

class Convolution:
    """Static helpers for image convolution and preset kernels. Supports even AND odd kernels."""

    class Kernels:
        """Common convolution kernels."""
        @staticmethod
        def identity() -> ArrayLike:
            return np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]], dtype=np.float32)
        @staticmethod
        def box_blur(n: int = 3) -> ArrayLike:
            if n < 1:
                raise ValueError("n must be a positive integer.")
            return np.ones((n, n), dtype=np.float32) / (n * n)
        @staticmethod
        def gaussian(n: int = 3, sigma: float = 1.0) -> ArrayLike:
            if n < 1:
                raise ValueError("n must be a positive integer.")
            ax = np.arange(n) - (n - 1) / 2.0
            xx, yy = np.meshgrid(ax, ax)
            kernel = np.exp(-(xx**2 + yy**2) / (2 * sigma**2))
            return (kernel / kernel.sum()).astype(np.float32)
        @staticmethod
        def sharpen() -> ArrayLike:
            return np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        @staticmethod
        def laplacian() -> ArrayLike:
            return np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        @staticmethod
        def laplacian_diag() -> ArrayLike:
            return np.array([[1, 1, 1], [1, -8, 1], [1, 1, 1]], dtype=np.float32)
        @staticmethod
        def sobel_x() -> ArrayLike:
            return np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
        @staticmethod
        def sobel_y() -> ArrayLike:
            return np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
        @staticmethod
        def prewitt_x() -> ArrayLike:
            return np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], dtype=np.float32)
        @staticmethod
        def prewitt_y() -> ArrayLike:
            return np.array([[-1, -1, -1], [0, 0, 0], [1, 1, 1]], dtype=np.float32)
        @staticmethod
        def scharr_x() -> ArrayLike:
            return np.array([[-3, 0, 3], [-10, 0, 10], [-3, 0, 3]], dtype=np.float32)
        @staticmethod
        def scharr_y() -> ArrayLike:
            return np.array([[-3, -10, -3], [0, 0, 0], [3, 10, 3]], dtype=np.float32)
        @staticmethod
        def emboss() -> ArrayLike:
            return np.array([[-2, -1, 0], [-1, 1, 1], [0, 1, 2]], dtype=np.float32)
        @staticmethod
        def roberts_x() -> ArrayLike:
            return np.array([[1, 0], [0, -1]], dtype=np.float32)
        @staticmethod
        def roberts_y() -> ArrayLike:
            return np.array([[0, 1], [-1, 0]], dtype=np.float32)
        @staticmethod
        def edge_detect() -> ArrayLike:
            return np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], dtype=np.float32)

    @staticmethod
    def apply(image: ArrayLike, kernel: Sequence[Sequence[float]], clip: bool = True, pad_mode: PadMode = "zero") -> ArrayLike:
        """2D spatial convolution. Supports ANY kernel size (odd or even).

        GPU path uses cupyx.scipy.ndimage.correlate for massive speedup.
        CPU path retains the original educational loop implementation.
        """
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        k = xp_mod.array(kernel, dtype=xp_mod.float32)
        orig_dtype = image.dtype

        # --- GPU fast path: use scipy.ndimage.correlate ---
        if _GPU_AVAILABLE and xp_mod is cp:
            from cupyx.scipy.ndimage import correlate as _gpu_correlate

            def _gpu_conv2d(channel, kernel2d):
                ch_f32 = channel.astype(cp.float32)
                if pad_mode == "none":
                    return _gpu_correlate(ch_f32, kernel2d, mode="constant", cval=0.0)
                mode_map = {"zero": "constant", "constant": "constant",
                            "edge": "nearest", "reflect": "reflect",
                            "symmetric": "reflect", "wrap": "wrap"}
                scipy_mode = mode_map.get(pad_mode, "constant")
                return _gpu_correlate(ch_f32, kernel2d, mode=scipy_mode, cval=0.0)

            if image.ndim == 2:
                out = _gpu_conv2d(image, k)
            else:
                channels = [_gpu_conv2d(image[..., i], k) for i in range(image.shape[2])]
                out = cp.stack(channels, axis=-1)
            if clip:
                out = cp.clip(out, 0, 255)
            return out.astype(orig_dtype)

        # --- CPU path: original loop implementation ---
        k_cpu = np.asarray(k, dtype=np.float32)

        def _conv2d(channel: ArrayLike, kernel2d: ArrayLike) -> ArrayLike:
            kh, kw = kernel2d.shape
            ph_top, ph_bot = (kh - 1) // 2, kh // 2
            pw_left, pw_right = (kw - 1) // 2, kw // 2
            ch_f32 = channel.astype(np.float32)

            if pad_mode == "none":
                out_h = channel.shape[0] - kh + 1
                out_w = channel.shape[1] - kw + 1
                if out_h <= 0 or out_w <= 0:
                    raise ValueError("Image is too small for this kernel with 'none' padding.")
                out = np.zeros((out_h, out_w), dtype=np.float32)
                for y in range(out_h):
                    for x in range(out_w):
                        out[y, x] = np.sum(ch_f32[y:y + kh, x:x + kw] * kernel2d)
            else:
                mode = "constant" if pad_mode == "zero" else pad_mode
                padded = np.pad(ch_f32, ((ph_top, ph_bot), (pw_left, pw_right)), mode=mode)
                out = np.zeros_like(channel, dtype=np.float32)
                for y in range(channel.shape[0]):
                    for x in range(channel.shape[1]):
                        out[y, x] = np.sum(padded[y:y + kh, x:x + kw] * kernel2d)
            return out

        cpu_img = to_cpu(image)
        if cpu_img.ndim == 2:
            out = _conv2d(cpu_img, k_cpu)
        else:
            channels = [_conv2d(cpu_img[..., i], k_cpu) for i in range(cpu_img.shape[2])]
            out = np.stack(channels, axis=-1)
        if clip:
            out = np.clip(out, 0, 255)
        return out.astype(orig_dtype)

    @staticmethod
    def apply_separable(image: ArrayLike, row_kernel: Sequence[float], col_kernel: Sequence[float], clip: bool = True) -> ArrayLike:
        """Separable convolution: first convolve rows, then columns."""
        image = _validate_image(image)
        xp_mod = _xp(image)
        rk = xp_mod.array(row_kernel, dtype=xp_mod.float32).reshape(1, -1)
        ck = xp_mod.array(col_kernel, dtype=xp_mod.float32).reshape(-1, 1)
        result = Convolution.apply(image, rk, clip=False, pad_mode="zero")
        result = Convolution.apply(result, ck, clip=False, pad_mode="zero")
        if clip:
            result = xp_mod.clip(result, 0, 255)
        return result.astype(image.dtype)

    @staticmethod
    def apply_frequency(image: ArrayLike, kernel: Sequence[Sequence[float]]) -> ArrayLike:
        """Frequency-domain convolution via FFT. GPU-accelerated when available."""
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        k = xp_mod.array(kernel, dtype=xp_mod.float32)

        def _freq_conv(ch, kern):
            h, w = ch.shape
            kh, kw = kern.shape
            pad_h, pad_w = h + kh - 1, w + kw - 1
            ch_freq = xp_mod.fft.fft2(ch.astype(xp_mod.float64), s=(pad_h, pad_w))
            k_freq = xp_mod.fft.fft2(kern.astype(xp_mod.float64), s=(pad_h, pad_w))
            result = xp_mod.real(xp_mod.fft.ifft2(ch_freq * k_freq))
            start_h = (kh - 1) // 2
            start_w = (kw - 1) // 2
            return result[start_h:start_h + h, start_w:start_w + w]

        if image.ndim == 2:
            out = _freq_conv(image, k)
        else:
            out = xp_mod.stack([_freq_conv(image[..., i], k) for i in range(image.shape[2])], axis=-1)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)



# ═══════════════════════════════════════════════════════════════════════════════
#  Image_Ops
# ═══════════════════════════════════════════════════════════════════════════════

class Image_Ops:
    """Static helpers for I/O, geometric transforms, color, pixel, and arithmetic operations."""

    # --- I/O ---
    @staticmethod
    def read(path: str, grayscale: bool = False) -> ArrayLike:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string.")
        flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        img = cv2.imread(path, flag)
        if img is None:
            raise FileNotFoundError(f"Could not read image from path: {path}")
        if not grayscale:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img

    @staticmethod
    def show(image: ArrayLike, title: str = "Image", show_axis: bool = False) -> None:
        """Display an image. Set show_axis=True to see pixel coordinates."""
        image = to_cpu(_validate_image(image))
        plt.figure(figsize=(6, 6))
        plt.imshow(image, cmap="gray" if image.ndim == 2 else None)
        plt.title(title)
        if not show_axis:
            plt.axis("off")
        plt.show()

    @staticmethod
    def save(image: ArrayLike, filename: str, is_split: bool = False, base_dir: str = "Results", gray: bool = False) -> str:
        """Saves an image. If is_split is True, saves to [base_dir]/Split."""
        image = to_cpu(_validate_image(image))
        target_dir = os.path.join(base_dir, "Split") if is_split else base_dir
        os.makedirs(target_dir, exist_ok=True)
        out_path = os.path.join(target_dir, filename)
        if image.ndim == 3 and not gray:
            to_save = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        else:
            to_save = image
        cv2.imwrite(out_path, to_save)
        return out_path

    @staticmethod
    def create_blank(width: int, height: int, channels: int = 3, color: int | tuple[int, ...] = 0, dtype: Any = np.uint8) -> ArrayLike:
        """Creates a solid-color image of specified size.
        
        Parameters
        ----------
        width, height : int
            Spatial dimensions.
        channels : int
            Number of color channels (1 for grayscale, 3 for RGB).
        color : int | tuple[int, ...]
            Fill color. Can be a scalar for all channels or a tuple (e.g. (255, 0, 0)).
        dtype : type
            Data type (default: np.uint8).
        """
        shape = (height, width) if channels == 1 else (height, width, channels)
        return np.full(shape, color, dtype=dtype)

    @staticmethod
    def create_blank_like(image: ArrayLike, color: int | tuple[int, ...] = 0) -> ArrayLike:
        """Creates a solid-color image with the same properties as the reference image."""
        image = _validate_image(image)
        return np.full(image.shape, color, dtype=image.dtype)

    @staticmethod
    def create_blanks_like(images: Sequence[ArrayLike], color: int | tuple[int, ...] = 0) -> list[ArrayLike]:
        """Creates a list of blank images matching a sequence of input images."""
        return [Image_Ops.create_blank_like(img, color=color) for img in images]

    @staticmethod
    def show_pair(original: ArrayLike, processed: ArrayLike, title_left: str = "Before", title_right: str = "After", show_axis: bool = False) -> None:
        original = to_cpu(_validate_image(original, name="original"))
        processed = to_cpu(_validate_image(processed, name="processed"))
        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        plt.title(title_left)
        if not show_axis:
            plt.axis("off")
        plt.imshow(original, cmap="gray" if original.ndim == 2 else None)
        plt.subplot(1, 2, 2)
        plt.title(title_right)
        if not show_axis:
            plt.axis("off")
        plt.imshow(processed, cmap="gray" if processed.ndim == 2 else None)
        plt.show()

    # --- Interactive Pixel Inspector ---
    @staticmethod
    def inspect(
        image: ArrayLike, title: str = "Pixel Inspector",
        show_grid: bool = False, colorbar: bool = True,
        figsize: tuple[int, int] = (10, 8),
    ) -> None:
        """Interactive pixel inspector with zoom/pan and hover coordinate readout.

        Hover over the image to see pixel (x, y) and value in the toolbar.
        Use the matplotlib toolbar buttons to zoom and pan.

        Tip: In Jupyter, use ``%matplotlib widget`` (requires ipympl) for
        full interactive zoom/pan. The default inline backend shows a static image.

        Parameters
        ----------
        image : ArrayLike
            Image to inspect.
        title : str
            Window / figure title.
        show_grid : bool
            Draw pixel-boundary grid lines (best on small images or when zoomed in).
        colorbar : bool
            Show a colorbar for grayscale images.
        figsize : tuple[int, int]
            Figure size in inches.
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        fig, ax = plt.subplots(figsize=figsize)

        kw = dict(interpolation="nearest")
        if image.ndim == 2:
            im = ax.imshow(image, cmap="gray", vmin=0, vmax=255, **kw)
            if colorbar:
                fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        else:
            ax.imshow(image, **kw)

        # Hover readout -------------------------------------------------------
        def _fmt(x, y):
            col, row = int(x + 0.5), int(y + 0.5)
            if 0 <= col < w and 0 <= row < h:
                if image.ndim == 2:
                    return f"x={col}  y={row}  val={image[row, col]}"
                px = image[row, col]
                if image.shape[2] == 3:
                    return f"x={col}  y={row}  R={px[0]} G={px[1]} B={px[2]}"
                return f"x={col}  y={row}  ch={list(px)}"
            return f"x={col}  y={row}"

        ax.format_coord = _fmt
        ax.set_title(f"{title}  ({w}\u00d7{h})")

        if show_grid:
            ax.set_xticks(np.arange(-0.5, w, 1), minor=True)
            ax.set_yticks(np.arange(-0.5, h, 1), minor=True)
            ax.grid(which="minor", color="#888888", linewidth=0.3, alpha=0.6)
            ax.tick_params(which="minor", size=0)

        plt.tight_layout()
        plt.show()

    @staticmethod
    def inspect_multi(
        images: Sequence[ArrayLike], *,
        titles: Sequence[str] | str | None = None,
        ncols: int | None = None,
        share_zoom: bool = True,
        show_grid: bool = False,
        figsize: tuple[int, int] | None = None,
    ) -> None:
        """Interactive multi-image inspector with optional shared zoom/pan.

        Useful for inspecting split_grid tiles, channel splits, or before/after
        comparisons at the pixel level.

        Parameters
        ----------
        images : Sequence[ArrayLike]
            List of images to display.
        titles : Sequence[str] | str | None
            If a list, used as per-image titles.
            If a string, used as a prefix (e.g. "grid" becomes "grid[0]", "grid[1]", ...).
        ncols : int | None
            Number of columns in the grid. If None, auto-detected based on count.
        share_zoom : bool
            If True all subplots share the same pan/zoom viewport.
        show_grid : bool
            Draw pixel-boundary grid lines.
        figsize : tuple[int, int] | None
            Figure size.  Auto-calculated if None.
        """
        if not images:
            raise ValueError("images must be non-empty.")
        N = len(images)
        
        if ncols is None:
            if N <= 3: ncols = N
            elif N <= 8: ncols = 2
            elif N <= 12: ncols = 3
            else: ncols = 4
            
        nrows = int(np.ceil(N / ncols))
        if figsize is None:
            figsize = (5 * ncols, 5 * nrows)

        fig, axes = plt.subplots(
            nrows, ncols, figsize=figsize,
            sharex=share_zoom, sharey=share_zoom,
            squeeze=False,
        )

        def _make_fmt(im_ref, h_ref, w_ref):
            def _fmt(x, y):
                col, row = int(x + 0.5), int(y + 0.5)
                if 0 <= col < w_ref and 0 <= row < h_ref:
                    if im_ref.ndim == 2:
                        return f"x={col}  y={row}  val={im_ref[row, col]}"
                    px = im_ref[row, col]
                    if im_ref.shape[2] == 3:
                        return f"x={col}  y={row}  R={px[0]} G={px[1]} B={px[2]}"
                    return f"x={col}  y={row}  ch={list(px)}"
                return f"x={col}  y={row}"
            return _fmt

        for i in range(N):
            r, c = divmod(i, ncols)
            ax = axes[r][c]
            img = to_cpu(_validate_image(images[i], name=f"images[{i}]"))
            ih, iw = img.shape[:2]

            kw = dict(interpolation="nearest")
            if img.ndim == 2:
                ax.imshow(img, cmap="gray", vmin=0, vmax=255, **kw)
            else:
                ax.imshow(img, **kw)

            # Handle titles logic
            if isinstance(titles, str):
                t = f"{titles}[{i}]"
            elif isinstance(titles, (list, tuple, np.ndarray)) and len(titles) > i:
                t = titles[i]
            else:
                t = f"Image {i}"
            
            ax.set_title(f"{t}  ({iw}\u00d7{ih})")
            ax.format_coord = _make_fmt(img, ih, iw)

            if show_grid:
                ax.set_xticks(np.arange(-0.5, iw, 1), minor=True)
                ax.set_yticks(np.arange(-0.5, ih, 1), minor=True)
                ax.grid(which="minor", color="#888888", linewidth=0.3, alpha=0.6)
                ax.tick_params(which="minor", size=0)

        # Hide unused subplot slots
        for i in range(N, nrows * ncols):
            r, c = divmod(i, ncols)
            axes[r][c].set_visible(False)

        plt.tight_layout()
        plt.show()

    @staticmethod
    def show_collection(
        images: Sequence[ArrayLike], *,
        titles: Sequence[str] | str | None = None,
        ncols: int | None = None,
        figsize: tuple[int, int] | None = None,
        show_axis: bool = False,
        cmap: str | None = "auto"
    ) -> None:
        """Static grid display of multiple images.

        Parameters
        ----------
        images : Sequence[ArrayLike]
            List of images to display.
        titles : Sequence[str] | str | None
            If a list, used as per-image titles.
            If a string, used as a prefix (e.g. "grid" becomes "grid[0]", "grid[1]", ...).
        ncols : int | None
            Number of columns in the grid. If None, auto-detected based on count.
        figsize : tuple[int, int] | None
            Figure size. Auto-calculated if None.
        show_axis : bool
            Whether to show pixel coordinates.
        cmap : str | None
            Colormap name. "auto" uses "gray" for 2D and None for color.
        """
        if not images:
            return
        
        N = len(images)
        if ncols is None:
            if N <= 3: ncols = N
            elif N <= 8: ncols = 2
            elif N <= 12: ncols = 3
            else: ncols = 4
            
        nrows = int(np.ceil(N / ncols))
        if figsize is None:
            figsize = (4 * ncols, 4 * nrows)
        
        plt.figure(figsize=figsize)
        for i, img in enumerate(images):
            plt.subplot(nrows, ncols, i + 1)
            
            img_cpu = to_cpu(_validate_image(img, name=f"images[{i}]"))
            
            # Dynamic cmap logic
            current_cmap = cmap
            if cmap == "auto":
                current_cmap = "gray" if img_cpu.ndim == 2 else None
            
            plt.imshow(img_cpu, cmap=current_cmap)
            
            # Handle titles logic
            if isinstance(titles, str):
                plt.title(f"{titles}[{i}]")
            elif isinstance(titles, (list, tuple, np.ndarray)) and len(titles) > i:
                plt.title(titles[i])
            else:
                plt.title(f"Image {i}")
                
            if not show_axis:
                plt.axis("off")
                
        plt.tight_layout()
        plt.show()

    # --- Geometry ---
    @staticmethod
    def flip(image: ArrayLike, axis: AxisMode = "horizontal") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if axis == "horizontal":
            return np.flip(image, axis=1)
        if axis == "vertical":
            return np.flip(image, axis=0)
        raise ValueError("axis must be 'horizontal' or 'vertical'.")

    @staticmethod
    def rotate(image: ArrayLike, angle: float, direction: RotDir = "ccw") -> ArrayLike:
        """Rotates image by angle degrees. direction: 'ccw' or 'cw'."""
        image = to_cpu(_validate_image(image))
        if direction not in ("ccw", "cw"):
            raise ValueError("direction must be 'ccw' or 'cw'.")
        ang = float(angle)
        if direction == "cw":
            ang = -ang
        ang_norm = ang % 360.0
        k = int(round(ang_norm / 90.0)) % 4
        if np.isclose(ang_norm, k * 90.0):
            if k == 0:
                return np.copy(image)
            return np.ascontiguousarray(np.rot90(image, k))
        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)
        M = cv2.getRotationMatrix2D(center, ang, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        M[0, 2] += (new_w / 2.0) - center[0]
        M[1, 2] += (new_h / 2.0) - center[1]
        return cv2.warpAffine(image, M, (new_w, new_h))

    @staticmethod
    def crop(image: ArrayLike, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if min(top, bottom, left, right) < 0:
            raise ValueError("Crop values must be >= 0.")
        h, w = image.shape[:2]
        y1, y2 = top, h - bottom
        x1, x2 = left, w - right
        if y1 >= y2 or x1 >= x2:
            raise ValueError("Crop removes all pixels. Reduce crop values.")
        return image[y1:y2, x1:x2]

    @staticmethod
    def crop_circle(image: ArrayLike, center: tuple[int, int] | None = None, radius: int | None = None, crop_to_box: bool = True) -> ArrayLike:
        """Crops an image into a circle. Areas outside the circle are black."""
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if center is None:
            center = (w // 2, h // 2)
        if radius is None:
            radius = min(h, w) // 2
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.circle(mask, center, radius, 255, -1)
        if image.ndim == 3:
            mask_3d = cv2.merge([mask] * image.shape[2])
            out = cv2.bitwise_and(image, mask_3d)
        else:
            out = cv2.bitwise_and(image, mask)
        if crop_to_box:
            x, y = center
            x1 = max(0, x - radius)
            x2 = min(w, x + radius)
            y1 = max(0, y - radius)
            y2 = min(h, y + radius)
            out = out[y1:y2, x1:x2, ...]
        return out

    @staticmethod
    def rotate_circle(image: ArrayLike, center: tuple[int, int] | None = None, radius: int | None = None, angle: float = 0) -> ArrayLike:
        """Rotates only the pixels within a circular region."""
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if center is None:
            center = (w // 2, h // 2)
        if radius is None:
            radius = min(h, w) // 2
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.circle(mask, center, radius, 255, -1)
        center_f = (float(center[0]), float(center[1]))
        M = cv2.getRotationMatrix2D(center_f, angle, 1.0)
        rotated_img = cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        if image.ndim == 3:
            mask_bool = cv2.merge([mask] * image.shape[2]) == 255
        else:
            mask_bool = mask == 255
        return np.where(mask_bool, rotated_img, image)

    @staticmethod
    def translate(image: ArrayLike, shift_x: int = 0, shift_y: int = 0) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        out = np.zeros_like(image)
        src_x1, src_x2 = max(0, -shift_x), min(w, w - shift_x)
        src_y1, src_y2 = max(0, -shift_y), min(h, h - shift_y)
        dst_x1, dst_x2 = max(0, shift_x), min(w, w + shift_x)
        dst_y1, dst_y2 = max(0, shift_y), min(h, h + shift_y)
        if src_x1 < src_x2 and src_y1 < src_y2:
            out[dst_y1:dst_y2, dst_x1:dst_x2, ...] = image[src_y1:src_y2, src_x1:src_x2, ...]
        return out

    @staticmethod
    def resize(image: ArrayLike, width: int | None = None, height: int | None = None, scale: float | None = None, interpolation: InterpMode = "linear") -> ArrayLike:
        """Resize by explicit dimensions or scale factor."""
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if scale is not None:
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
        elif width is not None or height is not None:
            new_w = width if width is not None else int(round(w * (height / h)))
            new_h = height if height is not None else int(round(h * (width / w)))
        else:
            raise ValueError("Provide either scale or width/height.")
        return cv2.resize(image, (new_w, new_h), interpolation=_interp_flag(interpolation))

    @staticmethod
    def pad(image: ArrayLike, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0, mode: PadMode = "constant", value: int = 0) -> ArrayLike:
        """Pad image borders."""
        image = to_cpu(_validate_image(image))
        if mode in ("zero", "constant"):
            if image.ndim == 2:
                return np.pad(image, ((top, bottom), (left, right)), mode="constant", constant_values=value)
            return np.pad(image, ((top, bottom), (left, right), (0, 0)), mode="constant", constant_values=value)
        np_mode = mode if mode != "zero" else "constant"
        if image.ndim == 2:
            return np.pad(image, ((top, bottom), (left, right)), mode=np_mode)
        return np.pad(image, ((top, bottom), (left, right), (0, 0)), mode=np_mode)

    @staticmethod
    def slice(image: ArrayLike, start: int, end: int, axis: AxisMode = "horizontal") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if axis == "horizontal":
            if not (0 <= start < end <= h):
                raise ValueError(f"For horizontal slicing, use 0 <= start < end <= {h}.")
            return image[start:end, ...]
        if axis == "vertical":
            if not (0 <= start < end <= w):
                raise ValueError(f"For vertical slicing, use 0 <= start < end <= {w}.")
            return image[:, start:end, ...]
        raise ValueError("axis must be 'horizontal' or 'vertical'.")

    @staticmethod
    def split_grid(image: ArrayLike, rows: int = 2, cols: int = 2) -> list[ArrayLike]:
        """Splits an image into a grid of rows x cols smaller images."""
        image = to_cpu(_validate_image(image))
        if rows < 1 or cols < 1:
            raise ValueError("rows and cols must be >= 1.")
        h, w = image.shape[:2]
        grid_h, grid_w = h // rows, w // cols
        if grid_h == 0 or grid_w == 0:
            raise ValueError("Image is too small to split into this many grids.")
        splits = []
        for r in range(rows):
            for c in range(cols):
                y_start = r * grid_h
                y_end = (r + 1) * grid_h if r < rows - 1 else h
                x_start = c * grid_w
                x_end = (c + 1) * grid_w if c < cols - 1 else w
                splits.append(image[y_start:y_end, x_start:x_end, ...])
        return splits

    @staticmethod
    def merge_grid(pieces: Sequence[ArrayLike], rows: int, cols: int) -> ArrayLike:
        """Inverse of split_grid (row-major)."""
        if rows < 1 or cols < 1:
            raise ValueError("rows and cols must be >= 1.")
        if len(pieces) != rows * cols:
            raise ValueError(f"Expected {rows * cols} pieces, got {len(pieces)}.")
        base = to_cpu(_validate_image(pieces[0], name="pieces[0]"))
        norm: list[ArrayLike] = [base]
        for i in range(1, len(pieces)):
            p = to_cpu(_validate_image(pieces[i], name=f"pieces[{i}]"))
            p, base2 = _match_channels(p, base)
            base = base2
            norm.append(p)
        out_rows: list[ArrayLike] = []
        idx = 0
        for r in range(rows):
            row_pieces = norm[idx: idx + cols]
            idx += cols
            target_h = max(p.shape[0] for p in row_pieces)
            padded = [_pad_to(p, target_h, p.shape[1]) if p.shape[0] != target_h else p for p in row_pieces]
            out_rows.append(np.concatenate(padded, axis=1))
        target_w = max(rr.shape[1] for rr in out_rows)
        out_rows = [_pad_to(rr, rr.shape[0], target_w) if rr.shape[1] != target_w else rr for rr in out_rows]
        return np.concatenate(out_rows, axis=0)

    @staticmethod
    def blend(image1: ArrayLike, image2: ArrayLike, alpha: float = 0.5, beta: float | None = None, gamma: float = 0.0, match: MatchMode = "resize") -> ArrayLike:
        image1 = to_cpu(_validate_image(image1, name="image1"))
        image2 = to_cpu(_validate_image(image2, name="image2"))
        if not (0.0 <= alpha <= 1.0):
            raise ValueError("alpha must be in [0, 1].")
        beta = (1.0 - alpha) if beta is None else beta
        if match not in ("resize", "pad"):
            raise ValueError("match must be 'resize' or 'pad'.")
        image1, image2 = _match_channels(image1, image2)
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]
        if (h1, w1) != (h2, w2):
            if match == "resize":
                image2 = _resize_to(image2, h1, w1)
            else:
                target_h, target_w = max(h1, h2), max(w1, w2)
                image1 = _pad_to(image1, target_h, target_w)
                image2 = _pad_to(image2, target_h, target_w)
        out = cv2.addWeighted(image1.astype(np.float32), alpha, image2.astype(np.float32), beta, gamma)
        if np.issubdtype(image1.dtype, np.integer):
            out = np.clip(out, 0, 255)
        return out.astype(image1.dtype)

    @staticmethod
    def map_translate_blend_tiles(
        dst_tiles: list[ArrayLike], src_tiles: Sequence[ArrayLike],
        mapping_src_to_dst: Sequence[int], shifts_xy: Sequence[tuple[int, int]] | None = None,
        *, alpha: float = 0.5, beta: float | None = None, gamma: float = 0.0,
    ) -> list[ArrayLike]:
        """For each src index i: dst_tiles[mapping[i]] = blend(dst_tiles[mapping[i]], translate(src_tiles[i], shifts_xy[i]))"""
        if len(mapping_src_to_dst) != len(src_tiles):
            raise ValueError("mapping_src_to_dst must have same length as src_tiles.")
        if shifts_xy is not None and len(shifts_xy) != len(src_tiles):
            raise ValueError("shifts_xy must be None or have same length as src_tiles.")
        out = list(dst_tiles)
        for i, dst_i in enumerate(mapping_src_to_dst):
            tile = to_cpu(_validate_image(src_tiles[i], name=f"src_tiles[{i}]"))
            if shifts_xy is not None:
                sx, sy = shifts_xy[i]
                tile = Image_Ops.translate(tile, shift_x=int(sx), shift_y=int(sy))
            out[dst_i] = Image_Ops.blend(out[dst_i], tile, alpha=alpha, beta=beta, gamma=gamma, match="resize")
        return out

    @staticmethod
    def concat_h(image1: ArrayLike, image2: ArrayLike, match: MatchMode = "pad") -> ArrayLike:
        image1 = to_cpu(_validate_image(image1, name="image1"))
        image2 = to_cpu(_validate_image(image2, name="image2"))
        image1, image2 = _match_channels(image1, image2)
        if match == "resize":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _resize_to(image1, target_h, image1.shape[1])
            image2 = _resize_to(image2, target_h, image2.shape[1])
        elif match == "pad":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _pad_to(image1, target_h, image1.shape[1])
            image2 = _pad_to(image2, target_h, image2.shape[1])
        else:
            raise ValueError("match must be 'pad' or 'resize'.")
        return np.concatenate([image1, image2], axis=1)

    @staticmethod
    def concat_v(image1: ArrayLike, image2: ArrayLike, match: MatchMode = "pad") -> ArrayLike:
        image1 = to_cpu(_validate_image(image1, name="image1"))
        image2 = to_cpu(_validate_image(image2, name="image2"))
        image1, image2 = _match_channels(image1, image2)
        if match == "resize":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _resize_to(image1, image1.shape[0], target_w)
            image2 = _resize_to(image2, image2.shape[0], target_w)
        elif match == "pad":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _pad_to(image1, image1.shape[0], target_w)
            image2 = _pad_to(image2, image2.shape[0], target_w)
        else:
            raise ValueError("match must be 'pad' or 'resize'.")
        return np.concatenate([image1, image2], axis=0)

    @staticmethod
    def dilate(image: ArrayLike, times: int = 2) -> ArrayLike:
        """Pixel-repeat dilation."""
        image = to_cpu(_validate_image(image))
        if times < 1:
            raise ValueError("times must be >= 1.")
        return np.repeat(np.repeat(image, times, axis=0), times, axis=1)

    @staticmethod
    def dilate_keep_resolution(image: ArrayLike, times: int = 2) -> ArrayLike:
        """Dilates then crops center to maintain original resolution."""
        image = to_cpu(_validate_image(image))
        if times < 1:
            raise ValueError("times must be >= 1.")
        if times == 1:
            return np.copy(image)
        h, w = image.shape[:2]
        dilated = np.repeat(np.repeat(image, times, axis=0), times, axis=1)
        new_h, new_w = dilated.shape[:2]
        start_y = (new_h - h) // 2
        start_x = (new_w - w) // 2
        return dilated[start_y:start_y + h, start_x:start_x + w, ...]

    @staticmethod
    def dilate_float(image: ArrayLike, scale: float = 2.0, interpolation: InterpMode = "nearest") -> ArrayLike:
        """Dilates (zooms) by a float scale factor."""
        image = to_cpu(_validate_image(image))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("scale must be a finite number > 0.")
        if scale == 1.0:
            return np.copy(image)
        h, w = image.shape[:2]
        new_h = max(1, int(round(h * scale)))
        new_w = max(1, int(round(w * scale)))
        return cv2.resize(image, (new_w, new_h), interpolation=_interp_flag(interpolation))

    @staticmethod
    def dilate_keep_resolution_float(image: ArrayLike, scale: float = 2.0, interpolation: InterpMode = "nearest") -> ArrayLike:
        """Dilates by float scale, then center crop/pad back to original resolution."""
        image = to_cpu(_validate_image(image))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("scale must be a finite number > 0.")
        if scale == 1.0:
            return np.copy(image)
        h, w = image.shape[:2]
        dilated = Image_Ops.dilate_float(image, scale=scale, interpolation=interpolation)
        return _center_crop_or_pad(dilated, h, w)

    @staticmethod
    def undilate(image: ArrayLike, times: int = 2) -> ArrayLike:
        """Integer subsampling (decimation) by taking every N-th pixel."""
        image = to_cpu(_validate_image(image))
        if times < 1:
            raise ValueError("times must be >= 1.")
        if times == 1:
            return np.copy(image)
        return np.ascontiguousarray(image[::times, ::times, ...])

    @staticmethod
    def undilate_keep_resolution(image: ArrayLike, times: int = 2) -> ArrayLike:
        """Integer subsampling then padding back to original resolution."""
        image = to_cpu(_validate_image(image))
        if times < 1:
            raise ValueError("times must be >= 1.")
        if times == 1:
            return np.copy(image)
        h, w = image.shape[:2]
        subsampled = Image_Ops.undilate(image, times=times)
        return _center_crop_or_pad(subsampled, h, w)

    @staticmethod
    def downsample(image: ArrayLike, scale: float = 0.5, interpolation: InterpMode = "linear") -> ArrayLike:
        """Downsamples (shrinks) by a float scale factor."""
        image = to_cpu(_validate_image(image))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("scale must be a finite number > 0.")
        if scale == 1.0:
            return np.copy(image)
        h, w = image.shape[:2]
        new_h = max(1, int(round(h * scale)))
        new_w = max(1, int(round(w * scale)))
        return cv2.resize(image, (new_w, new_h), interpolation=_interp_flag(interpolation))

    @staticmethod
    def downsample_keep_resolution(image: ArrayLike, scale: float = 0.5, interpolation: InterpMode = "linear") -> ArrayLike:
        """Downsamples by float scale, then pads back to original resolution."""
        image = to_cpu(_validate_image(image))
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("scale must be a finite number > 0.")
        if scale == 1.0:
            return np.copy(image)
        h, w = image.shape[:2]
        downsampled = Image_Ops.downsample(image, scale=scale, interpolation=interpolation)
        return _center_crop_or_pad(downsampled, h, w)

    # --- Color ---
    @staticmethod
    def to_grayscale(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            return image.copy()
        return cv2.cvtColor(to_cpu(image), cv2.COLOR_RGB2GRAY)

    @staticmethod
    def to_binary(image: ArrayLike, threshold: int = 127, method: Literal["fixed", "otsu"] = "fixed") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if method == "otsu":
            _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            _, binary = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY)
        return binary

    @staticmethod
    def color_quantization(image: ArrayLike, k: int = 8) -> ArrayLike:
        """Reduce image colors using K-Means clustering."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            return image.copy()
        
        h, w, c = image.shape
        data = image.reshape((-1, c))
        
        labels, centers = Machine_Learning.kmeans(data, k)
        
        # Map pixels back to centers
        xp_mod = _xp(centers)
        quantized = centers[labels].reshape((h, w, c))
        return xp_mod.clip(quantized, 0, 255).astype(xp_mod.uint8)

    @staticmethod
    def convert_colorspace(image: ArrayLike, src: str = "RGB", dst: str = "HSV") -> ArrayLike:
        """Convert between color spaces. Supported: RGB, BGR, HSV, LAB, YCrCb, GRAY, HLS."""
        image = to_cpu(_validate_image(image))
        code_name = f"COLOR_{src.upper()}2{dst.upper()}"
        code = getattr(cv2, code_name, None)
        if code is None:
            raise ValueError(f"Unsupported conversion: {src} -> {dst}. OpenCV has no {code_name}.")
        return cv2.cvtColor(image, code)

    @staticmethod
    def channel_split(image: ArrayLike) -> list[ArrayLike]:
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            return [image.copy()]
        return [image[..., i] for i in range(image.shape[2])]

    @staticmethod
    def channel_merge(channels: Sequence[ArrayLike]) -> ArrayLike:
        if len(channels) == 0:
            raise ValueError("channels must be non-empty.")
        return np.stack(channels, axis=-1)

    # --- Pixel ops ---
    @staticmethod
    def invert(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.bitwise_not(image)

    @staticmethod
    def bitwise_and(img1: ArrayLike, img2: ArrayLike) -> ArrayLike:
        img1, img2 = to_cpu(_validate_image(img1, name="img1")), to_cpu(_validate_image(img2, name="img2"))
        img1, img2 = _match_channels(img1, img2)
        return cv2.bitwise_and(img1, img2)

    @staticmethod
    def bitwise_or(img1: ArrayLike, img2: ArrayLike) -> ArrayLike:
        img1, img2 = to_cpu(_validate_image(img1, name="img1")), to_cpu(_validate_image(img2, name="img2"))
        img1, img2 = _match_channels(img1, img2)
        return cv2.bitwise_or(img1, img2)

    @staticmethod
    def bitwise_xor(img1: ArrayLike, img2: ArrayLike) -> ArrayLike:
        img1, img2 = to_cpu(_validate_image(img1, name="img1")), to_cpu(_validate_image(img2, name="img2"))
        img1, img2 = _match_channels(img1, img2)
        return cv2.bitwise_xor(img1, img2)

    @staticmethod
    def overlay_text(image: ArrayLike, text: str, position: tuple[int, int] = (10, 30), font_scale: float = 1.0, color: tuple[int, ...] = (255, 255, 255), thickness: int = 2) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        out = image.copy()
        cv2.putText(out, text, position, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
        return out

    # --- Arithmetic (GPU-accelerated) ---
    @staticmethod
    def add(image: ArrayLike, val) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if isinstance(val, (np.ndarray,)) or (_GPU_AVAILABLE and isinstance(val, cp.ndarray)):
            val = _validate_image(val, name="val")
            image, val = _match_channels(image, val)
            if image.shape[:2] != val.shape[:2]:
                raise ValueError("Image sizes must match exactly for addition.")
            out = image.astype(xp_mod.float32) + val.astype(xp_mod.float32)
        else:
            out = image.astype(xp_mod.float32) + float(val)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def subtract(image: ArrayLike, val) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if isinstance(val, (np.ndarray,)) or (_GPU_AVAILABLE and isinstance(val, cp.ndarray)):
            val = _validate_image(val, name="val")
            image, val = _match_channels(image, val)
            if image.shape[:2] != val.shape[:2]:
                raise ValueError("Image sizes must match exactly for subtraction.")
            out = image.astype(xp_mod.float32) - val.astype(xp_mod.float32)
        else:
            out = image.astype(xp_mod.float32) - float(val)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def multiply(image: ArrayLike, val) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if isinstance(val, (np.ndarray,)) or (_GPU_AVAILABLE and isinstance(val, cp.ndarray)):
            val = _validate_image(val, name="val")
            image, val = _match_channels(image, val)
            if image.shape[:2] != val.shape[:2]:
                raise ValueError("Image sizes must match exactly for multiplication.")
            out = image.astype(xp_mod.float32) * val.astype(xp_mod.float32)
        else:
            out = image.astype(xp_mod.float32) * float(val)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def divide(image: ArrayLike, val, epsilon: float = 1e-6) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if isinstance(val, (np.ndarray,)) or (_GPU_AVAILABLE and isinstance(val, cp.ndarray)):
            val = _validate_image(val, name="val")
            image, val = _match_channels(image, val)
            if image.shape[:2] != val.shape[:2]:
                raise ValueError("Image sizes must match exactly for division.")
            out = image.astype(xp_mod.float32) / (val.astype(xp_mod.float32) + epsilon)
        else:
            if float(val) == 0.0:
                raise ValueError("Cannot divide by zero.")
            out = image.astype(xp_mod.float32) / float(val)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def magnitude(dx: ArrayLike, dy: ArrayLike) -> ArrayLike:
        """Computes the gradient magnitude from horizontal (dx) and vertical (dy) components."""
        dx = _validate_image(dx, name="dx")
        dy = _validate_image(dy, name="dy")
        dx = _smart(dx)
        dy = _smart(dy)
        xp_mod = _xp(dx)
        dx, dy = _match_channels(dx, dy)
        if dx.shape[:2] != dy.shape[:2]:
            raise ValueError("dx and dy must have the same spatial dimensions.")
        out = xp_mod.sqrt(dx.astype(xp_mod.float64)**2 + dy.astype(xp_mod.float64)**2)
        return xp_mod.clip(out, 0, 255).astype(dx.dtype)

    # --- Noise ---
    @staticmethod
    def add_salt_pepper(image: ArrayLike, prob: float = 0.05) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        noisy = xp_mod.copy(image) if xp_mod is not np else np.copy(image)
        rnd = xp_mod.random.rand(*noisy.shape[:2])
        noisy[rnd < prob / 2] = 0
        noisy[rnd > 1 - prob / 2] = 255
        return noisy



# ═══════════════════════════════════════════════════════════════════════════════
#  Equalization
# ═══════════════════════════════════════════════════════════════════════════════

class Equalization:
    """Static helpers for histogram equalization variants."""

    @staticmethod
    def equalize(image: ArrayLike) -> ArrayLike:
        """Global histogram equalization."""
        image = to_cpu(_validate_image(image))
        if image.dtype != np.uint8:
            img = np.clip(image, 0, 255).astype(np.uint8)
        else:
            img = image.copy()
        if img.ndim == 2:
            return cv2.equalizeHist(img)
        ycrcb = cv2.cvtColor(img, cv2.COLOR_RGB2YCrCb)
        ycrcb[..., 0] = cv2.equalizeHist(ycrcb[..., 0])
        return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

    @staticmethod
    def clahe(image: ArrayLike, clip_limit: float = 2.0, tile_grid_size: tuple[int, int] = (8, 8)) -> ArrayLike:
        """Contrast-Limited Adaptive Histogram Equalization (CLAHE)."""
        image = to_cpu(_validate_image(image))
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        clahe_obj = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        if image.ndim == 2:
            return clahe_obj.apply(image)
        ycrcb = cv2.cvtColor(image, cv2.COLOR_RGB2YCrCb)
        ycrcb[..., 0] = clahe_obj.apply(ycrcb[..., 0])
        return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

    @staticmethod
    def equalize_per_channel(image: ArrayLike) -> ArrayLike:
        """Independent histogram equalization on each RGB channel."""
        image = to_cpu(_validate_image(image))
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        if image.ndim == 2:
            return cv2.equalizeHist(image)
        out = np.zeros_like(image)
        for ch in range(image.shape[2]):
            out[..., ch] = cv2.equalizeHist(image[..., ch])
        return out

    @staticmethod
    def adaptive(image: ArrayLike) -> ArrayLike:
        """Alias for CLAHE with sensible defaults."""
        return Equalization.clahe(image, clip_limit=2.0, tile_grid_size=(8, 8))


# ═══════════════════════════════════════════════════════════════════════════════
#  Specialization
# ═══════════════════════════════════════════════════════════════════════════════

class Specialization:
    """Static helpers for histogram specification / matching."""

    @staticmethod
    def match(image: ArrayLike, reference: ArrayLike) -> ArrayLike:
        """Histogram matching."""
        image = to_cpu(_validate_image(image, name="image"))
        reference = to_cpu(_validate_image(reference, name="reference"))

        def _match_channel(src, ref):
            src_hist, _ = np.histogram(src.ravel(), bins=256, range=(0, 256))
            ref_hist, _ = np.histogram(ref.ravel(), bins=256, range=(0, 256))
            src_cdf = np.cumsum(src_hist).astype(np.float64)
            src_cdf = src_cdf / (src_cdf[-1] + 1e-8)
            ref_cdf = np.cumsum(ref_hist).astype(np.float64)
            ref_cdf = ref_cdf / (ref_cdf[-1] + 1e-8)
            lut = np.interp(src_cdf, ref_cdf, np.arange(256))
            matched = np.interp(src.ravel(), np.arange(256), lut).reshape(src.shape)
            return np.clip(matched, 0, 255).astype(np.uint8)

        if image.ndim == 2 and reference.ndim == 2:
            return _match_channel(image, reference)
        out = np.zeros_like(image)
        image, reference = _match_channels(image, reference)
        for i in range(image.shape[2]):
            out[..., i] = _match_channel(image[..., i], reference[..., i])
        return out

    @staticmethod
    def match_manual(image: ArrayLike, reference: ArrayLike, verbose: bool = False) -> tuple[ArrayLike, ArrayLike]:
        """Step-by-step histogram specification with LUT exposed. Returns (matched_image, lut)."""
        image = to_cpu(_validate_image(image, name="image"))
        reference = to_cpu(_validate_image(reference, name="reference"))

        def _build_lut(src, ref, channel_name=""):
            src_hist, _ = np.histogram(src.ravel(), bins=256, range=(0, 256))
            ref_hist, _ = np.histogram(ref.ravel(), bins=256, range=(0, 256))
            if verbose:
                print(f"  [{channel_name}] Step 1: Computed histograms (src sum={src_hist.sum()}, ref sum={ref_hist.sum()})")
            src_cdf = np.cumsum(src_hist).astype(np.float64)
            src_cdf /= src_cdf[-1] + 1e-8
            ref_cdf = np.cumsum(ref_hist).astype(np.float64)
            ref_cdf /= ref_cdf[-1] + 1e-8
            if verbose:
                print(f"  [{channel_name}] Step 2: Computed CDFs")
            lut = np.zeros(256, dtype=np.uint8)
            for src_val in range(256):
                diff = np.abs(ref_cdf - src_cdf[src_val])
                lut[src_val] = np.argmin(diff)
            if verbose:
                print(f"  [{channel_name}] Step 3: Built LUT (sample: 0->{lut[0]}, 128->{lut[128]}, 255->{lut[255]})")
            matched = lut[src.astype(np.uint8)]
            if verbose:
                print(f"  [{channel_name}] Step 4: Applied LUT to image")
            return matched, lut

        if verbose:
            print("=== Manual Histogram Specification ===")
        if image.ndim == 2:
            if reference.ndim == 3:
                reference = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
            matched, lut = _build_lut(image, reference, "gray")
            return matched, lut
        image, reference = _match_channels(image, reference)
        out = np.zeros_like(image)
        luts = []
        ch_names = ["R", "G", "B"]
        for ch in range(image.shape[2]):
            name = ch_names[ch] if ch < 3 else f"ch{ch}"
            matched_ch, lut = _build_lut(image[..., ch], reference[..., ch], name)
            out[..., ch] = matched_ch
            luts.append(lut)
        return out, np.stack(luts, axis=-1)

    @staticmethod
    def transfer_color(source: ArrayLike, reference: ArrayLike) -> ArrayLike:
        """Color transfer via LAB color space statistics (Reinhard et al.)."""
        source = to_cpu(_validate_image(source, name="source"))
        reference = to_cpu(_validate_image(reference, name="reference"))
        if source.ndim == 2:
            source = cv2.cvtColor(source, cv2.COLOR_GRAY2RGB)
        if reference.ndim == 2:
            reference = cv2.cvtColor(reference, cv2.COLOR_GRAY2RGB)
        src_lab = cv2.cvtColor(source, cv2.COLOR_RGB2LAB).astype(np.float64)
        ref_lab = cv2.cvtColor(reference, cv2.COLOR_RGB2LAB).astype(np.float64)
        for ch in range(3):
            src_mean, src_std = src_lab[..., ch].mean(), src_lab[..., ch].std() + 1e-8
            ref_mean, ref_std = ref_lab[..., ch].mean(), ref_lab[..., ch].std() + 1e-8
            src_lab[..., ch] = (src_lab[..., ch] - src_mean) * (ref_std / src_std) + ref_mean
        src_lab = np.clip(src_lab, 0, 255).astype(np.uint8)
        return cv2.cvtColor(src_lab, cv2.COLOR_LAB2RGB)


# ═══════════════════════════════════════════════════════════════════════════════
#  Enhancement
# ═══════════════════════════════════════════════════════════════════════════════

class Enhancement:
    """Static helpers for image enhancement: brightness, contrast, sharpening, noise, denoising."""

    @staticmethod
    def brightness_contrast(image: ArrayLike, alpha: float = 1.0, beta: int = 0) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.convertScaleAbs(image, alpha=alpha, beta=beta)

    @staticmethod
    def gamma_correction(image: ArrayLike, gamma: float = 1.0) -> ArrayLike:
        """gamma<1 brightens, gamma>1 darkens."""
        image = to_cpu(_validate_image(image))
        inv_gamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)], dtype=np.uint8)
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        return cv2.LUT(image, table)

    @staticmethod
    def log_transform(image: ArrayLike, c: float = 1.0) -> ArrayLike:
        """s = c * log(1 + r). Expands dark intensities."""
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        img_f = image.astype(xp_mod.float64)
        out = c * xp_mod.log1p(img_f)
        out = out / (out.max() + 1e-8) * 255
        return xp_mod.clip(out, 0, 255).astype(xp_mod.uint8)

    @staticmethod
    def power_law(image: ArrayLike, gamma: float = 1.0, c: float = 1.0) -> ArrayLike:
        """s = c * r^gamma."""
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        img_f = image.astype(xp_mod.float64) / 255.0
        out = c * xp_mod.power(img_f, gamma) * 255.0
        return xp_mod.clip(out, 0, 255).astype(xp_mod.uint8)

    @staticmethod
    def unsharp_mask(image: ArrayLike, sigma: float = 1.0, strength: float = 1.5, kernel_size: int = 0) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if kernel_size == 0:
            kernel_size = int(np.ceil(sigma * 6)) | 1
        blurred = cv2.GaussianBlur(image, (kernel_size, kernel_size), sigma)
        sharp = cv2.addWeighted(image.astype(np.float32), 1.0 + strength, blurred.astype(np.float32), -strength, 0)
        return np.clip(sharp, 0, 255).astype(image.dtype)

    @staticmethod
    def sharpen(image: ArrayLike) -> ArrayLike:
        return Convolution.apply(image, Convolution.Kernels.sharpen(), clip=True)

    @staticmethod
    def blur_gaussian(image: ArrayLike, kernel_size: int = 5) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if kernel_size % 2 == 0:
            raise ValueError("Kernel size must be an odd number.")
        return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)

    @staticmethod
    def blur_median(image: ArrayLike, kernel_size: int = 5) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if kernel_size % 2 == 0:
            raise ValueError("kernel_size must be odd.")
        return cv2.medianBlur(image, kernel_size)

    @staticmethod
    def blur_bilateral(image: ArrayLike, d: int = 9, sigma_color: float = 75, sigma_space: float = 75) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.bilateralFilter(image, d, sigma_color, sigma_space)

    @staticmethod
    def add_gaussian_noise(image: ArrayLike, mean: float = 0.0, sigma: float = 25.0) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        noise = xp_mod.random.normal(mean, sigma, image.shape)
        out = image.astype(xp_mod.float64) + noise
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def add_poisson_noise(image: ArrayLike) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        img_f = image.astype(xp_mod.float64)
        vals = len(xp_mod.unique(image))
        vals = max(2, 2 ** int(xp_mod.ceil(xp_mod.log2(xp_mod.array(vals)))))
        noisy = xp_mod.random.poisson(img_f / 255.0 * vals) / vals * 255.0
        return xp_mod.clip(noisy, 0, 255).astype(image.dtype)

    @staticmethod
    def denoise_nlmeans(image: ArrayLike, h: float = 10, template_window: int = 7, search_window: int = 21) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        if image.ndim == 2:
            return cv2.fastNlMeansDenoising(image, None, h, template_window, search_window)
        return cv2.fastNlMeansDenoisingColored(image, None, h, h, template_window, search_window)


# ═══════════════════════════════════════════════════════════════════════════════
#  Edge_Detection
# ═══════════════════════════════════════════════════════════════════════════════

class Edge_Detection:
    """Static helpers for edge detection algorithms."""

    @staticmethod
    def canny(image: ArrayLike, threshold1: int = 100, threshold2: int = 200) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return cv2.Canny(image, threshold1, threshold2)

    @staticmethod
    def sobel(image: ArrayLike, dx: int = 1, dy: int = 0, ksize: int = 3, combine: bool = True) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if combine and dx == 1 and dy == 0:
            gx = cv2.Sobel(image, cv2.CV_64F, 1, 0, ksize=ksize)
            gy = cv2.Sobel(image, cv2.CV_64F, 0, 1, ksize=ksize)
            return Image_Ops.magnitude(gx, gy)
        return np.clip(np.abs(cv2.Sobel(image, cv2.CV_64F, dx, dy, ksize=ksize)), 0, 255).astype(np.uint8)

    @staticmethod
    def prewitt(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        gx = Convolution.apply(image, Convolution.Kernels.prewitt_x(), clip=False)
        gy = Convolution.apply(image, Convolution.Kernels.prewitt_y(), clip=False)
        return Image_Ops.magnitude(gx, gy)

    @staticmethod
    def laplacian(image: ArrayLike, ksize: int = 3) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return np.clip(np.abs(cv2.Laplacian(image, cv2.CV_64F, ksize=ksize)), 0, 255).astype(np.uint8)

    @staticmethod
    def laplacian_of_gaussian(image: ArrayLike, sigma: float = 1.0, ksize: int = 5) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(image, (ksize, ksize), sigma)
        return np.clip(np.abs(cv2.Laplacian(blurred, cv2.CV_64F)), 0, 255).astype(np.uint8)

    @staticmethod
    def roberts(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        gx = Convolution.apply(image, Convolution.Kernels.roberts_x(), clip=False, pad_mode="zero")
        gy = Convolution.apply(image, Convolution.Kernels.roberts_y(), clip=False, pad_mode="zero")
        return np.clip(np.sqrt(gx.astype(np.float64) ** 2 + gy.astype(np.float64) ** 2), 0, 255).astype(np.uint8)

    @staticmethod
    def scharr(image: ArrayLike, dx: int = 1, dy: int = 0, combine: bool = True) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if combine and dx == 1 and dy == 0:
            gx = cv2.Scharr(image, cv2.CV_64F, 1, 0)
            gy = cv2.Scharr(image, cv2.CV_64F, 0, 1)
            return np.clip(np.sqrt(gx ** 2 + gy ** 2), 0, 255).astype(np.uint8)
        return np.clip(np.abs(cv2.Scharr(image, cv2.CV_64F, dx, dy)), 0, 255).astype(np.uint8)

    @staticmethod
    def zero_crossing(image: ArrayLike, threshold: float = 0.0) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(image, (5, 5), 1.0)
        lap = cv2.Laplacian(blurred, cv2.CV_64F)
        h, w = lap.shape
        out = np.zeros((h, w), dtype=np.uint8)
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                patch = lap[y - 1:y + 2, x - 1:x + 2]
                if patch.min() < -threshold and patch.max() > threshold:
                    out[y, x] = 255
        return out



# ═══════════════════════════════════════════════════════════════════════════════
#  Morphology
# ═══════════════════════════════════════════════════════════════════════════════

class Morphology:
    """Static helpers for morphological operations."""

    @staticmethod
    def get_structuring_element(shape: str = "rect", ksize: int = 3) -> ArrayLike:
        shapes = {"rect": cv2.MORPH_RECT, "cross": cv2.MORPH_CROSS, "ellipse": cv2.MORPH_ELLIPSE}
        if shape not in shapes:
            raise ValueError(f"shape must be one of {list(shapes.keys())}.")
        return cv2.getStructuringElement(shapes[shape], (ksize, ksize))

    @staticmethod
    def erode(image: ArrayLike, ksize: int = 3, iterations: int = 1, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.erode(image, Morphology.get_structuring_element(element_shape, ksize), iterations=iterations)

    @staticmethod
    def dilate(image: ArrayLike, ksize: int = 3, iterations: int = 1, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.dilate(image, Morphology.get_structuring_element(element_shape, ksize), iterations=iterations)

    @staticmethod
    def opening(image: ArrayLike, ksize: int = 3, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.morphologyEx(image, cv2.MORPH_OPEN, Morphology.get_structuring_element(element_shape, ksize))

    @staticmethod
    def closing(image: ArrayLike, ksize: int = 3, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.morphologyEx(image, cv2.MORPH_CLOSE, Morphology.get_structuring_element(element_shape, ksize))

    @staticmethod
    def gradient(image: ArrayLike, ksize: int = 3, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.morphologyEx(image, cv2.MORPH_GRADIENT, Morphology.get_structuring_element(element_shape, ksize))

    @staticmethod
    def tophat(image: ArrayLike, ksize: int = 9, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.morphologyEx(image, cv2.MORPH_TOPHAT, Morphology.get_structuring_element(element_shape, ksize))

    @staticmethod
    def blackhat(image: ArrayLike, ksize: int = 9, element_shape: str = "rect") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        return cv2.morphologyEx(image, cv2.MORPH_BLACKHAT, Morphology.get_structuring_element(element_shape, ksize))

    @staticmethod
    def skeleton(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        skel = np.zeros_like(binary)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        while True:
            opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, element)
            temp = cv2.subtract(binary, opened)
            eroded = cv2.erode(binary, element)
            skel = cv2.bitwise_or(skel, temp)
            binary = eroded.copy()
            if cv2.countNonZero(binary) == 0:
                break
        return skel

    @staticmethod
    def hit_or_miss(image: ArrayLike, kernel: ArrayLike | None = None) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        if kernel is None:
            kernel = np.array([[-1, -1, -1], [-1, 1, -1], [-1, -1, -1]], dtype=np.int32)
        return cv2.morphologyEx(binary, cv2.MORPH_HITMISS, kernel)

    @staticmethod
    def thinning(image: ArrayLike, max_iterations: int = 100) -> ArrayLike:
        """Morphological thinning — reduces objects to 1-pixel-wide skeletons.

        Uses iterative hit-or-miss with 8 structuring element rotations.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        # 8 thinning structuring elements (Guo-Hall / standard rotations)
        kernels = [
            np.array([[-1, -1, -1], [0, 1, 0], [1, 1, 1]], dtype=np.int32),
            np.array([[0, -1, -1], [1, 1, -1], [0, 1, 0]], dtype=np.int32),
            np.array([[1, 0, -1], [1, 1, -1], [1, 0, -1]], dtype=np.int32),
            np.array([[0, 1, 0], [1, 1, -1], [0, -1, -1]], dtype=np.int32),
            np.array([[1, 1, 1], [0, 1, 0], [-1, -1, -1]], dtype=np.int32),
            np.array([[0, 1, 0], [-1, 1, 1], [-1, -1, 0]], dtype=np.int32),
            np.array([[-1, 0, 1], [-1, 1, 1], [-1, 0, 1]], dtype=np.int32),
            np.array([[-1, -1, 0], [-1, 1, 1], [0, 1, 0]], dtype=np.int32),
        ]
        prev = np.zeros_like(binary)
        current = binary.copy()
        for _ in range(max_iterations):
            for k in kernels:
                hitmiss = cv2.morphologyEx(current, cv2.MORPH_HITMISS, k)
                current = cv2.subtract(current, hitmiss)
            if np.array_equal(current, prev):
                break
            prev = current.copy()
        return current


# ═══════════════════════════════════════════════════════════════════════════════
#  Wavelet (manual Haar — no external dependencies)
# ═══════════════════════════════════════════════════════════════════════════════

class Wavelet:
    """2D wavelet transforms using a manual Haar filter-bank. Pure numpy."""

    @staticmethod
    def _haar_forward_1d(signal: ArrayLike) -> tuple[ArrayLike, ArrayLike]:
        n = len(signal)
        if n % 2 != 0:
            signal = np.append(signal, signal[-1])
        even = signal[0::2].astype(np.float64)
        odd = signal[1::2].astype(np.float64)
        return (even + odd) / np.sqrt(2), (even - odd) / np.sqrt(2)

    @staticmethod
    def _haar_inverse_1d(approx: ArrayLike, detail: ArrayLike) -> ArrayLike:
        even = (approx + detail) / np.sqrt(2)
        odd = (approx - detail) / np.sqrt(2)
        out = np.zeros(len(approx) * 2, dtype=np.float64)
        out[0::2] = even
        out[1::2] = odd
        return out

    @staticmethod
    def dwt2(image: ArrayLike) -> tuple[ArrayLike, ArrayLike, ArrayLike, ArrayLike]:
        """Single-level 2D Haar DWT. Returns (cA, cH, cV, cD)."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img = image.astype(np.float64)
        h, w = img.shape
        if h % 2 != 0:
            img = np.vstack([img, img[-1:, :]])
            h += 1
        if w % 2 != 0:
            img = np.hstack([img, img[:, -1:]])
            w += 1
        row_L = np.zeros((h, w // 2), dtype=np.float64)
        row_H = np.zeros((h, w // 2), dtype=np.float64)
        for i in range(h):
            row_L[i, :], row_H[i, :] = Wavelet._haar_forward_1d(img[i, :])
        half_h, half_w = h // 2, w // 2
        cA = np.zeros((half_h, half_w), dtype=np.float64)
        cV = np.zeros((half_h, half_w), dtype=np.float64)
        for j in range(half_w):
            cA[:, j], cV[:, j] = Wavelet._haar_forward_1d(row_L[:, j])
        cH = np.zeros((half_h, half_w), dtype=np.float64)
        cD = np.zeros((half_h, half_w), dtype=np.float64)
        for j in range(half_w):
            cH[:, j], cD[:, j] = Wavelet._haar_forward_1d(row_H[:, j])
        return cA, cH, cV, cD

    @staticmethod
    def idwt2(cA: ArrayLike, cH: ArrayLike, cV: ArrayLike, cD: ArrayLike) -> ArrayLike:
        """Inverse single-level 2D Haar DWT."""
        half_h, half_w = cA.shape
        h, w = half_h * 2, half_w * 2
        row_L = np.zeros((h, half_w), dtype=np.float64)
        row_H = np.zeros((h, half_w), dtype=np.float64)
        for j in range(half_w):
            row_L[:, j] = Wavelet._haar_inverse_1d(cA[:, j], cV[:, j])
            row_H[:, j] = Wavelet._haar_inverse_1d(cH[:, j], cD[:, j])
        out = np.zeros((h, w), dtype=np.float64)
        for i in range(h):
            out[i, :] = Wavelet._haar_inverse_1d(row_L[i, :], row_H[i, :])
        return out

    @staticmethod
    def wavedec2(image: ArrayLike, level: int = 2) -> list:
        """Multi-level 2D Haar DWT. Returns [cA_n, (cH_n,cV_n,cD_n), ..., (cH_1,cV_1,cD_1)]."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if level < 1:
            raise ValueError("level must be >= 1.")
        coeffs = []
        current = image.astype(np.float64)
        for _ in range(level):
            cA, cH, cV, cD = Wavelet.dwt2(current)
            coeffs.append((cH, cV, cD))
            current = cA
        coeffs.append(current)
        coeffs.reverse()
        return coeffs

    @staticmethod
    def waverec2(coeffs: list) -> ArrayLike:
        """Multi-level inverse 2D Haar DWT."""
        current = coeffs[0].astype(np.float64)
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            th, tw = cH.shape
            ch, cw = current.shape
            if ch != th or cw != tw:
                current = current[:th, :tw]
            current = Wavelet.idwt2(current, cH, cV, cD)
        return current

    @staticmethod
    def show_coefficients(coeffs: list, level: int = 1, figsize: tuple[int, int] = (12, 4)) -> None:
        if level < 1 or level >= len(coeffs):
            raise ValueError(f"level must be in [1, {len(coeffs) - 1}].")
        idx = len(coeffs) - level
        cH, cV, cD = coeffs[idx]
        cA = coeffs[0] if level == len(coeffs) - 1 else None
        titles = [f"Horizontal (level {level})", f"Vertical (level {level})", f"Diagonal (level {level})"]
        images = [cH, cV, cD]
        if cA is not None:
            titles.insert(0, "Approximation")
            images.insert(0, cA)
        n = len(images)
        plt.figure(figsize=figsize)
        for i, (img, t) in enumerate(zip(images, titles)):
            plt.subplot(1, n, i + 1)
            plt.imshow(np.abs(img), cmap="gray")
            plt.title(t)
            plt.axis("off")
        plt.tight_layout()
        plt.show()

    @staticmethod
    def denoise(image: ArrayLike, level: int = 2, threshold: float | None = None, mode: Literal["hard", "soft"] = "soft") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        coeffs = Wavelet.wavedec2(image, level=level)
        if threshold is None:
            cH1 = coeffs[-1][0]
            sigma = np.median(np.abs(cH1)) / 0.6745
            n = image.shape[0] * image.shape[1]
            threshold = sigma * np.sqrt(2 * np.log(n))
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            if mode == "hard":
                cH = np.where(np.abs(cH) < threshold, 0, cH)
                cV = np.where(np.abs(cV) < threshold, 0, cV)
                cD = np.where(np.abs(cD) < threshold, 0, cD)
            else:
                cH = np.sign(cH) * np.maximum(np.abs(cH) - threshold, 0)
                cV = np.sign(cV) * np.maximum(np.abs(cV) - threshold, 0)
                cD = np.sign(cD) * np.maximum(np.abs(cD) - threshold, 0)
            coeffs[i] = (cH, cV, cD)
        reconstructed = Wavelet.waverec2(coeffs)
        h, w = image.shape[:2]
        return np.clip(reconstructed[:h, :w], 0, 255).astype(np.uint8)

    @staticmethod
    def compress(image: ArrayLike, level: int = 3, keep_ratio: float = 0.1) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        coeffs = Wavelet.wavedec2(image, level=level)
        all_vals = [np.abs(coeffs[0]).ravel()]
        for i in range(1, len(coeffs)):
            for arr in coeffs[i]:
                all_vals.append(np.abs(arr).ravel())
        threshold = np.percentile(np.concatenate(all_vals), (1.0 - keep_ratio) * 100)
        coeffs[0] = np.where(np.abs(coeffs[0]) < threshold, 0, coeffs[0])
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            coeffs[i] = (
                np.where(np.abs(cH) < threshold, 0, cH),
                np.where(np.abs(cV) < threshold, 0, cV),
                np.where(np.abs(cD) < threshold, 0, cD),
            )
        h, w = image.shape[:2]
        return np.clip(Wavelet.waverec2(coeffs)[:h, :w], 0, 255).astype(np.uint8)

    @staticmethod
    def list_wavelets() -> None:
        print("Available wavelets: haar")
        print("  Filters: Lo=[1/sqrt2, 1/sqrt2], Hi=[1/sqrt2, -1/sqrt2]")
        print("  Properties: orthogonal, compact support, discontinuous")
        print("  Note: manual implementation using only numpy.")


# ═══════════════════════════════════════════════════════════════════════════════
#  Feature_Extraction
# ═══════════════════════════════════════════════════════════════════════════════

class Feature_Extraction:
    """Static helpers for feature detection, description, and matching."""

    @staticmethod
    def harris_corners(image: ArrayLike, block_size: int = 2, ksize: int = 3, k: float = 0.04, threshold: float = 0.01) -> tuple[ArrayLike, ArrayLike]:
        image = to_cpu(_validate_image(image))
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        response = cv2.dilate(cv2.cornerHarris(np.float32(gray), block_size, ksize, k), None)
        marked = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB) if image.ndim == 2 else image.copy()
        marked[response > threshold * response.max()] = [255, 0, 0]
        return response, marked

    @staticmethod
    def shi_tomasi_corners(image: ArrayLike, max_corners: int = 100, quality_level: float = 0.01, min_distance: float = 10) -> tuple[ArrayLike | None, ArrayLike]:
        image = to_cpu(_validate_image(image))
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        corners = cv2.goodFeaturesToTrack(gray, max_corners, quality_level, min_distance)
        marked = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB) if image.ndim == 2 else image.copy()
        if corners is not None:
            for corner in corners:
                x, y = corner.ravel().astype(int)
                cv2.circle(marked, (x, y), 5, (0, 255, 0), -1)
        return corners, marked

    @staticmethod
    def sift_detect(image: ArrayLike, n_features: int = 0) -> tuple[list, ArrayLike | None]:
        image = to_cpu(_validate_image(image))
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        try:
            sift = cv2.SIFT_create(nfeatures=n_features)
        except AttributeError:
            print("WARNING: SIFT not available in this OpenCV build. Try ORB instead.")
            return [], None
        kps, descs = sift.detectAndCompute(gray, None)
        return list(kps), descs

    @staticmethod
    def orb_detect(image: ArrayLike, n_features: int = 500) -> tuple[list, ArrayLike | None]:
        image = to_cpu(_validate_image(image))
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        kps, descs = cv2.ORB_create(nfeatures=n_features).detectAndCompute(gray, None)
        return list(kps), descs

    @staticmethod
    def hog_descriptor(image: ArrayLike, orientations: int = 9, pixels_per_cell: int = 8, cells_per_block: int = 2) -> ArrayLike:
        """Manual HOG descriptor."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img = image.astype(np.float64)
        h, w = img.shape
        gx = np.zeros_like(img)
        gy = np.zeros_like(img)
        gx[:, 1:-1] = img[:, 2:] - img[:, :-2]
        gy[1:-1, :] = img[2:, :] - img[:-2, :]
        magnitude = np.sqrt(gx ** 2 + gy ** 2)
        orientation = np.rad2deg(np.arctan2(gy, gx)) % 180
        n_cells_y = h // pixels_per_cell
        n_cells_x = w // pixels_per_cell
        cell_hists = np.zeros((n_cells_y, n_cells_x, orientations), dtype=np.float64)
        bin_width = 180.0 / orientations
        for cy in range(n_cells_y):
            for cx in range(n_cells_x):
                y0, x0 = cy * pixels_per_cell, cx * pixels_per_cell
                mag_cell = magnitude[y0:y0 + pixels_per_cell, x0:x0 + pixels_per_cell]
                ori_cell = orientation[y0:y0 + pixels_per_cell, x0:x0 + pixels_per_cell]
                for b in range(orientations):
                    mask = (ori_cell >= b * bin_width) & (ori_cell < (b + 1) * bin_width)
                    cell_hists[cy, cx, b] = np.sum(mag_cell[mask])
        blocks_y = n_cells_y - cells_per_block + 1
        blocks_x = n_cells_x - cells_per_block + 1
        if blocks_y < 1 or blocks_x < 1:
            return cell_hists.ravel()
        hog_features = []
        for by in range(blocks_y):
            for bx in range(blocks_x):
                block = cell_hists[by:by + cells_per_block, bx:bx + cells_per_block, :].ravel()
                hog_features.append(block / (np.sqrt(np.sum(block ** 2) + 1e-6)))
        return np.concatenate(hog_features)

    @staticmethod
    def lbp(image: ArrayLike, radius: int = 1, n_points: int = 8) -> ArrayLike:
        """Manual Local Binary Pattern."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        out = np.zeros((h, w), dtype=np.uint8)
        for i in range(radius, h - radius):
            for j in range(radius, w - radius):
                center = image[i, j]
                binary_val = 0
                for p in range(n_points):
                    angle = 2 * np.pi * p / n_points
                    ny = np.clip(i + int(round(radius * np.sin(angle))), 0, h - 1)
                    nx = np.clip(j + int(round(radius * np.cos(angle))), 0, w - 1)
                    if image[ny, nx] >= center:
                        binary_val |= (1 << p)
                out[i, j] = binary_val
        return out

    @staticmethod
    def match_features(desc1: ArrayLike, desc2: ArrayLike, method: Literal["bf", "flann"] = "bf", cross_check: bool = True) -> list:
        if desc1 is None or desc2 is None:
            return []
        if method == "bf":
            norm_type = cv2.NORM_HAMMING if desc1.dtype == np.uint8 else cv2.NORM_L2
            return list(cv2.BFMatcher(norm_type, crossCheck=cross_check).match(desc1, desc2))
        if desc1.dtype == np.uint8:
            index_params = dict(algorithm=6, table_number=6, key_size=12, multi_probe_level=1)
        else:
            index_params = dict(algorithm=1, trees=5)
        return list(cv2.FlannBasedMatcher(index_params, dict(checks=50)).match(desc1, desc2))

    @staticmethod
    def draw_keypoints(image: ArrayLike, keypoints: list, color: tuple[int, ...] = (0, 255, 0)) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        return cv2.drawKeypoints(image, keypoints, None, color=color, flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

    @staticmethod
    def draw_matches(img1: ArrayLike, kp1: list, img2: ArrayLike, kp2: list, matches: list, top_n: int = 50) -> ArrayLike:
        img1 = to_cpu(_validate_image(img1, name="img1"))
        img2 = to_cpu(_validate_image(img2, name="img2"))
        if img1.ndim == 2:
            img1 = cv2.cvtColor(img1, cv2.COLOR_GRAY2RGB)
        if img2.ndim == 2:
            img2 = cv2.cvtColor(img2, cv2.COLOR_GRAY2RGB)
        return cv2.drawMatches(img1, kp1, img2, kp2, sorted(matches, key=lambda m: m.distance)[:top_n], None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)

    @staticmethod
    def find_contours(image: ArrayLike, mode: str = "external", method: str = "simple") -> list:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        modes = {"external": cv2.RETR_EXTERNAL, "list": cv2.RETR_LIST, "tree": cv2.RETR_TREE, "ccomp": cv2.RETR_CCOMP}
        methods = {"none": cv2.CHAIN_APPROX_NONE, "simple": cv2.CHAIN_APPROX_SIMPLE, "tc89_l1": cv2.CHAIN_APPROX_TC89_L1, "tc89_kcos": cv2.CHAIN_APPROX_TC89_KCOS}
        contours, _ = cv2.findContours(binary, modes.get(mode, cv2.RETR_EXTERNAL), methods.get(method, cv2.CHAIN_APPROX_SIMPLE))
        return list(contours)

    @staticmethod
    def hu_moments(image: ArrayLike) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return cv2.HuMoments(cv2.moments(image)).flatten()

    @staticmethod
    def template_match(image: ArrayLike, template: ArrayLike, method: str = "ccoeff_normed") -> tuple[tuple[int, int], float, ArrayLike]:
        image = to_cpu(_validate_image(image, name="image"))
        template = to_cpu(_validate_image(template, name="template"))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if template.ndim == 3:
            template = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
        methods_map = {"sqdiff": cv2.TM_SQDIFF, "sqdiff_normed": cv2.TM_SQDIFF_NORMED, "ccorr": cv2.TM_CCORR, "ccorr_normed": cv2.TM_CCORR_NORMED, "ccoeff": cv2.TM_CCOEFF, "ccoeff_normed": cv2.TM_CCOEFF_NORMED}
        result = cv2.matchTemplate(image, template, methods_map.get(method, cv2.TM_CCOEFF_NORMED))
        if method in ("sqdiff", "sqdiff_normed"):
            _, best_score, best_loc, _ = cv2.minMaxLoc(result)
        else:
            _, best_score, _, best_loc = cv2.minMaxLoc(result)
        return best_loc, best_score, result

    @staticmethod
    def geometric_features(image: ArrayLike) -> dict:
        """Compute geometric features from a binary/grayscale image.

        Returns dict with: area, centroid_x, centroid_y, perimeter,
        compactness, roundness.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) == 0:
            return {"area": 0, "centroid_x": 0.0, "centroid_y": 0.0,
                    "perimeter": 0.0, "compactness": 0.0, "roundness": 0.0}
        cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        M = cv2.moments(cnt)
        cx = M["m10"] / (M["m00"] + 1e-8)
        cy = M["m01"] / (M["m00"] + 1e-8)
        compactness = (4 * np.pi * area) / (perimeter ** 2 + 1e-8)
        roundness = (4 * np.pi * area) / (perimeter ** 2 + 1e-8)
        return {"area": area, "centroid_x": cx, "centroid_y": cy,
                "perimeter": perimeter, "compactness": compactness,
                "roundness": roundness}

    @staticmethod
    def histogram_features(image: ArrayLike) -> dict:
        """Statistical features from the intensity histogram.

        Returns dict with: mean, std, variance, mean_square, skewness, kurtosis.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        hist, _ = np.histogram(image.ravel(), bins=256, range=(0, 256))
        prob = hist.astype(np.float64) / (hist.sum() + 1e-8)
        x = np.arange(256, dtype=np.float64)
        mean = np.sum(x * prob)
        variance = np.sum(((x - mean) ** 2) * prob)
        std = np.sqrt(variance)
        mean_sq = np.sum((x ** 2) * prob)
        skewness = np.sum(((x - mean) ** 3) * prob) / (std ** 3 + 1e-8)
        kurtosis = np.sum(((x - mean) ** 4) * prob) / (variance ** 2 + 1e-8) - 3.0
        return {"mean": mean, "std": std, "variance": variance,
                "mean_square": mean_sq, "skewness": skewness, "kurtosis": kurtosis}

    @staticmethod
    def gradient_features(image: ArrayLike) -> tuple[dict, ArrayLike]:
        """Gradient magnitude features over an image region.

        Returns (features_dict, gradient_image).
        features_dict contains: mean, variance, skewness, kurtosis.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img = image.astype(np.float64)
        gx = np.zeros_like(img)
        gy = np.zeros_like(img)
        gx[:, 1:-1] = img[:, 2:] - img[:, :-2]
        gy[1:-1, :] = img[2:, :] - img[:-2, :]
        grad = np.sqrt(gx ** 2 + gy ** 2)
        g_mean = np.mean(grad)
        g_var = np.mean((grad - g_mean) ** 2)
        g_std = np.sqrt(g_var) + 1e-8
        g_skew = np.mean(((grad - g_mean) / g_std) ** 3)
        g_kurt = np.mean(((grad - g_mean) / g_std) ** 4) - 3.0
        features = {"mean": g_mean, "variance": g_var,
                     "skewness": g_skew, "kurtosis": g_kurt}
        return features, np.clip(grad, 0, 255).astype(np.uint8)

    @staticmethod
    def fourier_features(image: ArrayLike, n_rings: int = 5, n_sectors: int = 4) -> dict:
        """Energy features from the Fourier magnitude spectrum.

        Computes ring and sector energy features as described in TM13/14.
        Returns dict with ring_energies and sector_energies arrays.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        f = np.fft.fft2(image.astype(np.float64))
        fshift = np.fft.fftshift(f)
        magnitude = np.abs(fshift) ** 2
        h, w = magnitude.shape
        cy, cx = h // 2, w // 2
        Y, X = np.ogrid[:h, :w]
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        max_r = min(cy, cx)
        # Ring features
        ring_energies = np.zeros(n_rings, dtype=np.float64)
        ring_width = max_r / n_rings
        for i in range(n_rings):
            r_lo = i * ring_width
            r_hi = (i + 1) * ring_width
            mask = (dist >= r_lo) & (dist < r_hi)
            ring_energies[i] = np.sum(magnitude[mask])
        # Sector features
        angle = np.arctan2(Y - cy, X - cx)
        sector_energies = np.zeros(n_sectors, dtype=np.float64)
        sector_width = 2 * np.pi / n_sectors
        for i in range(n_sectors):
            a_lo = -np.pi + i * sector_width
            a_hi = a_lo + sector_width
            mask = (angle >= a_lo) & (angle < a_hi)
            sector_energies[i] = np.sum(magnitude[mask])
        return {"ring_energies": ring_energies, "sector_energies": sector_energies}

    @staticmethod
    def wavelet_energy(image: ArrayLike, level: int = 2) -> dict:
        """Compute energy of each wavelet subband.

        Energy = sum(coefficients^2) / n_pixels_in_subband.
        Returns dict mapping subband names to energy values.
        """
        image = to_cpu(_validate_image(image))
        coeffs = Wavelet.wavedec2(image, level=level)
        energies: dict = {}
        cA = coeffs[0]
        energies["cA"] = float(np.sum(cA ** 2) / (cA.size + 1e-8))
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            lv = len(coeffs) - i
            energies[f"cH_L{lv}"] = float(np.sum(cH ** 2) / (cH.size + 1e-8))
            energies[f"cV_L{lv}"] = float(np.sum(cV ** 2) / (cV.size + 1e-8))
            energies[f"cD_L{lv}"] = float(np.sum(cD ** 2) / (cD.size + 1e-8))
        return energies

    @staticmethod
    def color_histogram_features(image: ArrayLike, color_space: str = "HSV",
                                  bins: int = 256) -> dict:
        """Extract dominant intensity per channel after color space conversion.

        Returns dict with per-channel dominant intensity and mean values.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        code_name = f"COLOR_RGB2{color_space.upper()}"
        code = getattr(cv2, code_name, None)
        if code is None:
            converted = image
        else:
            converted = cv2.cvtColor(image, code)
        result: dict = {}
        for ch in range(converted.shape[2]):
            channel = converted[..., ch]
            hist, bin_edges = np.histogram(channel.ravel(), bins=bins,
                                            range=(0, 256))
            dominant = int(np.argmax(hist))
            result[f"ch{ch}_dominant"] = dominant
            result[f"ch{ch}_mean"] = float(np.mean(channel))
        return result

    @staticmethod
    def gabor_features(image: ArrayLike,
                       frequencies: Sequence[float] = (0.1, 0.2, 0.3, 0.4),
                       orientations: Sequence[float] = (0, 45, 90, 135),
                       ksize: int = 31, sigma: float = 4.0) -> ArrayLike:
        """Gabor filter bank energy features.

        Applies Gabor filters at each (frequency, orientation) pair and returns
        the mean energy of each filter response as a 1D feature vector.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        features = []
        for freq in frequencies:
            wavelength = 1.0 / (freq + 1e-8)
            for theta_deg in orientations:
                theta = np.deg2rad(theta_deg)
                kernel = cv2.getGaborKernel((ksize, ksize), sigma, theta,
                                            wavelength, 0.5, 0, ktype=cv2.CV_64F)
                response = cv2.filter2D(image.astype(np.float64), cv2.CV_64F, kernel)
                features.append(np.mean(response ** 2))
        return np.array(features, dtype=np.float64)


# ═══════════════════════════════════════════════════════════════════════════════
#  GLCM (Gray-Level Co-occurrence Matrix)
# ═══════════════════════════════════════════════════════════════════════════════

class GLCM:
    """Gray-Level Co-occurrence Matrix for texture analysis.

    Implements computation, normalization, and feature extraction as described
    in the GLCM course material. Pure numpy — no extra dependencies.
    """

    @staticmethod
    def compute(image: ArrayLike, distance: int = 1,
                angle: float = 0.0, levels: int = 256,
                symmetric: bool = True) -> ArrayLike:
        """Compute the GLCM for a given distance and angle.

        Parameters
        ----------
        image : grayscale uint8 image
        distance : pixel distance d
        angle : orientation in degrees (0, 45, 90, 135)
        levels : number of gray levels (default 256)
        symmetric : if True, count (i,j) and (j,i) (as in the PDF)

        Returns
        -------
        glcm : (levels, levels) integer co-occurrence matrix
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img = image.astype(np.int32)
        h, w = img.shape
        # Compute offsets from angle
        angle_rad = np.deg2rad(angle)
        dx = int(round(distance * np.cos(angle_rad)))
        dy = int(round(-distance * np.sin(angle_rad)))
        glcm = np.zeros((levels, levels), dtype=np.int64)
        for y in range(h):
            for x in range(w):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    i_val = img[y, x]
                    j_val = img[ny, nx]
                    if i_val < levels and j_val < levels:
                        glcm[i_val, j_val] += 1
        if symmetric:
            glcm = glcm + glcm.T
        return glcm

    @staticmethod
    def normalize(glcm: ArrayLike) -> ArrayLike:
        """Normalize a GLCM so entries sum to 1."""
        total = glcm.sum()
        if total == 0:
            return glcm.astype(np.float64)
        return glcm.astype(np.float64) / total

    @staticmethod
    def features(image: ArrayLike, distances: Sequence[int] = (1,),
                 angles: Sequence[float] = (0, 45, 90, 135),
                 levels: int = 256, symmetric: bool = True) -> dict:
        """Compute GLCM texture features for multiple distances and angles.

        For each (distance, angle) pair, computes:
        contrast, dissimilarity, homogeneity, energy (ASM), entropy, correlation.

        Returns dict mapping feature names to arrays of shape (n_distances, n_angles).
        """
        nd, na = len(distances), len(angles)
        feat_names = ["contrast", "dissimilarity", "homogeneity",
                       "energy", "entropy", "correlation"]
        result = {name: np.zeros((nd, na), dtype=np.float64) for name in feat_names}
        for di, d in enumerate(distances):
            for ai, a in enumerate(angles):
                g = GLCM.compute(image, distance=d, angle=a,
                                 levels=levels, symmetric=symmetric)
                p = GLCM.normalize(g)
                feats = GLCM._compute_features(p)
                for name in feat_names:
                    result[name][di, ai] = feats[name]
        return result

    @staticmethod
    def _compute_features(p: ArrayLike) -> dict:
        """Compute texture features from a normalized GLCM matrix *p*."""
        levels = p.shape[0]
        i_idx, j_idx = np.meshgrid(np.arange(levels), np.arange(levels), indexing="ij")
        i_f = i_idx.astype(np.float64)
        j_f = j_idx.astype(np.float64)
        diff = np.abs(i_f - j_f)
        contrast = np.sum(p * diff ** 2)
        dissimilarity = np.sum(p * diff)
        homogeneity = np.sum(p / (1.0 + diff ** 2))
        energy = np.sum(p ** 2)
        log_p = np.log2(p + 1e-12)
        entropy = -np.sum(p * log_p)
        mu_i = np.sum(i_f * p)
        mu_j = np.sum(j_f * p)
        sigma_i = np.sqrt(np.sum(((i_f - mu_i) ** 2) * p) + 1e-8)
        sigma_j = np.sqrt(np.sum(((j_f - mu_j) ** 2) * p) + 1e-8)
        correlation = np.sum(((i_f - mu_i) * (j_f - mu_j) * p)) / (sigma_i * sigma_j)
        return {"contrast": contrast, "dissimilarity": dissimilarity,
                "homogeneity": homogeneity, "energy": energy,
                "entropy": entropy, "correlation": correlation}

    @staticmethod
    def show(image: ArrayLike, distance: int = 1, angle: float = 0.0,
             levels: int = 256, symmetric: bool = True,
             title: str = "GLCM") -> None:
        """Display the GLCM as a heatmap."""
        g = GLCM.compute(image, distance=distance, angle=angle,
                         levels=levels, symmetric=symmetric)
        p = GLCM.normalize(g)
        plt.figure(figsize=(6, 5))
        plt.imshow(p, cmap="hot", interpolation="nearest")
        plt.colorbar(label="Probability")
        plt.title(f"{title} (d={distance}, θ={angle}°)")
        plt.xlabel("Gray level j")
        plt.ylabel("Gray level i")
        plt.tight_layout()
        plt.show()



# ═══════════════════════════════════════════════════════════════════════════════
#  Segmentation
# ═══════════════════════════════════════════════════════════════════════════════

class Segmentation:
    """Static helpers for image segmentation."""

    @staticmethod
    def otsu_threshold(image: ArrayLike) -> tuple[int, ArrayLike]:
        """Manual implementation of Otsu's optimal global thresholding.
        
        Returns (optimal_threshold, binary_image).
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        # 1. Compute histogram
        hist, _ = np.histogram(image.ravel(), bins=256, range=(0, 256))
        total_pixels = image.size
        
        current_max = -1.0
        threshold = 0
        
        # 2. Iterate through thresholds
        # Precompute probabilities and means
        sum_total = np.sum(np.arange(256) * hist)
        weight_bg = 0.0
        sum_bg = 0.0
        
        for i in range(256):
            weight_bg += hist[i]
            if weight_bg == 0: continue
            
            weight_fg = total_pixels - weight_bg
            if weight_fg == 0: break
            
            sum_bg += i * hist[i]
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg
            
            # Between-class variance
            var_between = weight_bg * weight_fg * (mean_bg - mean_fg)**2
            
            if var_between > current_max:
                current_max = var_between
                threshold = i
                
        _, binary = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY)
        return threshold, binary

    @staticmethod
    def adaptive_threshold(image: ArrayLike, method: Literal["gaussian", "mean"] = "gaussian", 
                           block_size: int = 11, c: int = 2) -> ArrayLike:
        """Local adaptive thresholding."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        m = cv2.ADAPTIVE_THRESH_GAUSSIAN_C if method == "gaussian" else cv2.ADAPTIVE_THRESH_MEAN_C
        return cv2.adaptiveThreshold(image, 255, m, cv2.THRESH_BINARY, block_size, c)

    @staticmethod
    def region_growing(image: ArrayLike, seeds: Sequence[tuple[int, int]], tolerance: int = 10) -> ArrayLike:
        """Simple region growing from seed points."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        h, w = image.shape
        out = np.zeros_like(image)
        visited = np.zeros_like(image, dtype=bool)
        queue = list(seeds)
        
        for r, c in queue:
            out[r, c] = 255
            visited[r, c] = True
            
        idx = 0
        while idx < len(queue):
            y, x = queue[idx]
            idx += 1
            val = image[y, x]
            
            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                    if abs(int(image[ny, nx]) - int(val)) <= tolerance:
                        out[ny, nx] = 255
                        visited[ny, nx] = True
                        queue.append((ny, nx))
        return out

    @staticmethod
    def watershed(image: ArrayLike, markers: ArrayLike | None = None) -> ArrayLike:
        """Marker-based watershed segmentation."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            
        if markers is None:
            # Simple automatic marker generation
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Noise removal
            kernel = np.ones((3,3), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
            
            # Sure background
            sure_bg = cv2.dilate(opening, kernel, iterations=3)
            
            # Finding sure foreground
            dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
            _, sure_fg = cv2.threshold(dist_transform, 0.7 * dist_transform.max(), 255, 0)
            
            # Unknown region
            sure_fg = np.uint8(sure_fg)
            unknown = cv2.subtract(sure_bg, sure_fg)
            
            # Marker labelling
            _, markers = cv2.connectedComponents(sure_fg)
            markers = markers + 1
            markers[unknown == 255] = 0
            
        markers = cv2.watershed(image, markers.astype(np.int32))
        return markers


# ═══════════════════════════════════════════════════════════════════════════════
#  Transforms (Geometric & Accumulator)
# ═══════════════════════════════════════════════════════════════════════════════

class Transforms:
    """Static helpers for advanced image transforms."""

    @staticmethod
    def hough_lines(image: ArrayLike, threshold: int = 100, 
                    rho_res: float = 1.0, theta_res_deg: float = 1.0) -> tuple[ArrayLike, list]:
        """Manual implementation of the Hough Line Transform.
        
        Returns (accumulator, detected_lines_as_rho_theta_list).
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        # Edge detection if not already binary
        if len(np.unique(image)) > 2:
            edges = cv2.Canny(image, 50, 150)
        else:
            edges = image
            
        h, w = edges.shape
        diag_len = int(np.ceil(np.sqrt(h**2 + w**2)))
        rhos = np.arange(-diag_len, diag_len, rho_res)
        thetas = np.deg2rad(np.arange(0, 180, theta_res_deg))
        
        accumulator = np.zeros((len(rhos), len(thetas)), dtype=np.int32)
        
        y_idxs, x_idxs = np.nonzero(edges)
        
        cos_t = np.cos(thetas)
        sin_t = np.sin(thetas)
        
        for i in range(len(x_idxs)):
            x, y = x_idxs[i], y_idxs[i]
            for t_idx in range(len(thetas)):
                rho = x * cos_t[t_idx] + y * sin_t[t_idx]
                r_idx = np.argmin(np.abs(rhos - rho))
                accumulator[r_idx, t_idx] += 1
                
        lines = []
        best_r, best_t = np.nonzero(accumulator > threshold)
        for i in range(len(best_r)):
            lines.append((rhos[best_r[i]], thetas[best_t[i]]))
            
        return accumulator, lines

    @staticmethod
    def hough_circles(image: ArrayLike, min_radius: int, max_radius: int, 
                      threshold: int = 100) -> tuple[ArrayLike, list]:
        """Manual implementation of a simplified Hough Circle Transform."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        if len(np.unique(image)) > 2:
            edges = cv2.Canny(image, 50, 150)
        else:
            edges = image
            
        h, w = edges.shape
        accumulator = np.zeros((h, w, max_radius - min_radius + 1), dtype=np.int32)
        
        y_idxs, x_idxs = np.nonzero(edges)
        
        # Optimization: precompute sin/cos for radii
        for r in range(min_radius, max_radius + 1):
            r_idx = r - min_radius
            phi = np.deg2rad(np.arange(0, 360, 5))
            sin_phi = np.sin(phi)
            cos_phi = np.cos(phi)
            
            for i in range(len(x_idxs)):
                x, y = x_idxs[i], y_idxs[i]
                for p in range(len(phi)):
                    a = int(x - r * cos_phi[p])
                    b = int(y - r * sin_phi[p])
                    if 0 <= a < w and 0 <= b < h:
                        accumulator[b, a, r_idx] += 1
                        
        circles = []
        best_y, best_x, best_r_idx = np.nonzero(accumulator > threshold)
        for i in range(len(best_y)):
            circles.append((best_x[i], best_y[i], best_r_idx[i] + min_radius))
            
        return accumulator, circles

    @staticmethod
    def distance_transform(image: ArrayLike, dist_type: str = "l2") -> ArrayLike:
        """Compute the distance to the nearest zero pixel."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        dtype = cv2.DIST_L2 if dist_type == "l2" else cv2.DIST_L1
        return cv2.distanceTransform(image, dtype, 3)


# ═══════════════════════════════════════════════════════════════════════════════
#  Machine Learning (Pure NumPy)
# ═══════════════════════════════════════════════════════════════════════════════

class Machine_Learning:
    """Core ML algorithms for image processing implemented from scratch."""

    @staticmethod
    def kmeans(data: ArrayLike, k: int, max_iters: int = 10, epsilon: float = 1.0) -> tuple[ArrayLike, ArrayLike]:
        """Manual K-Means implementation. GPU-accelerated distance matrix.
        
        Parameters
        ----------
        data : (N, D) array of features
        k : number of clusters
        
        Returns
        -------
        labels : (N,) cluster assignments
        centers : (k, D) final cluster centroids
        """
        xp_mod = _xp(data)
        data = data.astype(xp_mod.float32)
        idx = xp_mod.random.choice(data.shape[0], k, replace=False)
        centers = data[idx]
        
        for _ in range(max_iters):
            # 1. Assignment step — GPU accelerates this distance matrix
            distances = xp_mod.sqrt(((data[:, xp_mod.newaxis, :] - centers[xp_mod.newaxis, :, :])**2).sum(axis=2))
            labels = xp_mod.argmin(distances, axis=1)
            
            # 2. Update step
            new_centers = xp_mod.array([data[labels == i].mean(axis=0) if xp_mod.any(labels == i) else centers[i] for i in range(k)])
            
            center_shift = xp_mod.sqrt(((new_centers - centers)**2).sum(axis=1)).mean()
            centers = new_centers
            if float(center_shift) < epsilon:
                break
                
        return labels, centers

    @staticmethod
    def pca(data: ArrayLike, n_components: int = 2) -> tuple[ArrayLike, ArrayLike, ArrayLike]:
        """Principal Component Analysis via SVD. GPU-accelerated.
        
        Returns (transformed_data, eigenvectors, eigenvalues).
        """
        xp_mod = _xp(data)
        data = data.astype(xp_mod.float64)
        mean = xp_mod.mean(data, axis=0)
        centered_data = data - mean
        
        # SVD: U, S, Vt — CuPy accelerates this
        u, s, vt = xp_mod.linalg.svd(centered_data, full_matrices=False)
        
        eigenvectors = vt[:n_components].T
        eigenvalues = (s**2) / (data.shape[0] - 1)
        
        transformed = xp_mod.dot(centered_data, eigenvectors)
        return transformed, eigenvectors, eigenvalues[:n_components]


# ═══════════════════════════════════════════════════════════════════════════════
#  Restoration
# ═══════════════════════════════════════════════════════════════════════════════

class Restoration:
    """Techniques for recovering degraded images."""

    @staticmethod
    def inverse_filter(image: ArrayLike, kernel: ArrayLike, epsilon: float = 1e-3) -> ArrayLike:
        """Simple inverse filtering in frequency domain. GPU-accelerated."""
        image = _validate_image(image)
        if image.ndim == 3:
            image = cv2.cvtColor(to_cpu(image), cv2.COLOR_RGB2GRAY)
        image = _smart(image)
        xp_mod = _xp(image)
        kernel = xp_mod.asarray(kernel)
            
        img_f = xp_mod.fft.fft2(image.astype(xp_mod.float64))
        h, w = image.shape
        kh, kw = kernel.shape
        
        # Pad kernel to image size
        kernel_padded = xp_mod.zeros((h, w), dtype=xp_mod.float64)
        kernel_padded[:kh, :kw] = kernel
        kernel_padded = xp_mod.fft.ifftshift(kernel_padded)
        kernel_f = xp_mod.fft.fft2(kernel_padded)
        
        # Avoid division by zero
        kernel_f_inv = xp_mod.where(xp_mod.abs(kernel_f) < epsilon, 0, 1.0 / kernel_f)
        
        result_f = img_f * kernel_f_inv
        result = xp_mod.real(xp_mod.fft.ifft2(result_f))
        return xp_mod.clip(result, 0, 255).astype(xp_mod.uint8)

    @staticmethod
    def wiener_filter(image: ArrayLike, kernel: ArrayLike, K: float = 0.01) -> ArrayLike:
        """Frequency-domain Wiener Filter. GPU-accelerated.
        
        Parameters
        ----------
        K : Noise-to-signal power ratio (SNR inverse)
        """
        image = _validate_image(image)
        if image.ndim == 3:
            image = cv2.cvtColor(to_cpu(image), cv2.COLOR_RGB2GRAY)
        image = _smart(image)
        xp_mod = _xp(image)
        kernel = xp_mod.asarray(kernel)
            
        img_f = xp_mod.fft.fft2(image.astype(xp_mod.float64))
        h, w = image.shape
        kh, kw = kernel.shape
        
        kernel_padded = xp_mod.zeros((h, w), dtype=xp_mod.float64)
        kernel_padded[:kh, :kw] = kernel
        kernel_padded = xp_mod.fft.ifftshift(kernel_padded)
        kernel_f = xp_mod.fft.fft2(kernel_padded)
        
        # G(u,v) = [H*(u,v) / (|H(u,v)|^2 + K)] * F(u,v)
        h_abs_sq = xp_mod.abs(kernel_f)**2
        wiener_g = xp_mod.conj(kernel_f) / (h_abs_sq + K)
        
        result_f = img_f * wiener_g
        result = xp_mod.real(xp_mod.fft.ifft2(result_f))
        return xp_mod.clip(result, 0, 255).astype(xp_mod.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
#  Fourier & DCT Transforms
# ═══════════════════════════════════════════════════════════════════════════════

class Fourier:
    """Static helpers for DFT, inverse DFT, DCT, and spectrum visualization.

    Uses only numpy FFT — no extra dependencies.
    """

    @staticmethod
    def dft2(image: ArrayLike) -> ArrayLike:
        """Compute the 2D DFT (shifted so DC is centered). GPU-accelerated."""
        image = _validate_image(image)
        if image.ndim == 3:
            image = cv2.cvtColor(to_cpu(image), cv2.COLOR_RGB2GRAY)
        image = _smart(image)
        xp_mod = _xp(image)
        return xp_mod.fft.fftshift(xp_mod.fft.fft2(image.astype(xp_mod.float64)))

    @staticmethod
    def idft2(freq_data: ArrayLike, clip_uint8: bool = True) -> ArrayLike:
        """Inverse 2D DFT from a shifted spectrum. GPU-accelerated."""
        xp_mod = _xp(freq_data)
        unshifted = xp_mod.fft.ifftshift(freq_data)
        result = xp_mod.real(xp_mod.fft.ifft2(unshifted))
        if clip_uint8:
            return xp_mod.clip(result, 0, 255).astype(xp_mod.uint8)
        return result

    @staticmethod
    def magnitude_spectrum(image: ArrayLike, log_scale: bool = True) -> ArrayLike:
        """Compute the magnitude spectrum of an image. GPU-accelerated."""
        dft = Fourier.dft2(image)
        xp_mod = _xp(dft)
        mag = xp_mod.abs(dft)
        if log_scale:
            mag = xp_mod.log1p(mag)
        mag = (mag / (mag.max() + 1e-8) * 255).astype(xp_mod.uint8)
        return mag

    @staticmethod
    def phase_spectrum(image: ArrayLike) -> ArrayLike:
        """Compute the phase spectrum of an image. GPU-accelerated."""
        dft = Fourier.dft2(image)
        xp_mod = _xp(dft)
        phase = xp_mod.angle(dft)
        # Normalize to 0-255
        phase = ((phase - phase.min()) / (phase.max() - phase.min() + 1e-8) * 255)
        return phase.astype(xp_mod.uint8)

    @staticmethod
    def show_spectrum(image: ArrayLike, title: str = "Fourier Spectrum") -> None:
        """Display magnitude and phase spectra side by side."""
        mag = to_cpu(Fourier.magnitude_spectrum(image))
        phase = to_cpu(Fourier.phase_spectrum(image))
        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        plt.imshow(mag, cmap="gray")
        plt.title(f"{title} — Magnitude")
        plt.axis("off")
        plt.subplot(1, 2, 2)
        plt.imshow(phase, cmap="gray")
        plt.title(f"{title} — Phase")
        plt.axis("off")
        plt.tight_layout()
        plt.show()

    @staticmethod
    def dct2(image: ArrayLike) -> ArrayLike:
        """2D Discrete Cosine Transform (Type-II) using pure numpy.

        Uses the orthonormal DCT-II definition matching scipy.fft.dctn.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img = image.astype(np.float64)
        M, N = img.shape

        def _dct1d(x):
            n = len(x)
            result = np.zeros(n, dtype=np.float64)
            for k in range(n):
                s = 0.0
                for i in range(n):
                    s += x[i] * np.cos(np.pi * k * (2 * i + 1) / (2 * n))
                alpha = np.sqrt(1.0 / n) if k == 0 else np.sqrt(2.0 / n)
                result[k] = alpha * s
            return result

        # Apply 1D DCT along rows, then columns
        temp = np.zeros_like(img)
        for i in range(M):
            temp[i, :] = _dct1d(img[i, :])
        result = np.zeros_like(img)
        for j in range(N):
            result[:, j] = _dct1d(temp[:, j])
        return result

    @staticmethod
    def idct2(coeffs: ArrayLike) -> ArrayLike:
        """Inverse 2D DCT (Type-III, orthonormal) using pure numpy."""
        coeffs = np.asarray(coeffs, dtype=np.float64)
        M, N = coeffs.shape

        def _idct1d(X):
            n = len(X)
            result = np.zeros(n, dtype=np.float64)
            for i in range(n):
                s = 0.0
                for k in range(n):
                    alpha = np.sqrt(1.0 / n) if k == 0 else np.sqrt(2.0 / n)
                    s += alpha * X[k] * np.cos(np.pi * k * (2 * i + 1) / (2 * n))
                result[i] = s
            return result

        temp = np.zeros_like(coeffs)
        for i in range(M):
            temp[i, :] = _idct1d(coeffs[i, :])
        result = np.zeros_like(coeffs)
        for j in range(N):
            result[:, j] = _idct1d(temp[:, j])
        return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Backward Compatibility Aliases
# ═══════════════════════════════════════════════════════════════════════════════

read_image = Image_Ops.read
show_image = Image_Ops.show
save_image = Image_Ops.save
show_before_after = Image_Ops.show_pair
inspect_image = Image_Ops.inspect
inspect_images = Image_Ops.inspect_multi
flip_image = Image_Ops.flip
rotate_image = Image_Ops.rotate
crop_image = Image_Ops.crop
crop_circle = Image_Ops.crop_circle
rotate_circle = Image_Ops.rotate_circle
translate_image = Image_Ops.translate
slice_image = Image_Ops.slice
save_image = Image_Ops.save
create_blank_image = Image_Ops.create_blank
create_blank_like = Image_Ops.create_blank_like
create_blanks_like = Image_Ops.create_blanks_like
split_image_grid = Image_Ops.split_grid
merge_image_grid = Image_Ops.merge_grid
map_translate_blend_tiles = Image_Ops.map_translate_blend_tiles
blend_images = Image_Ops.blend
concat_horizontal = Image_Ops.concat_h
concat_vertical = Image_Ops.concat_v
show_images = Image_Ops.show_collection
show_grid = Image_Ops.show_collection
dilate_image = Image_Ops.dilate
dilate_image_keep_resolution = Image_Ops.dilate_keep_resolution
dilate_image_float = Image_Ops.dilate_float
dilate_image_keep_resolution_float = Image_Ops.dilate_keep_resolution_float

undilate_image = Image_Ops.undilate
undilate_image_keep_resolution = Image_Ops.undilate_keep_resolution
downsample_image = Image_Ops.downsample
downsample_image_keep_resolution = Image_Ops.downsample_keep_resolution

decimate_image = Image_Ops.undilate
decimate_image_keep_resolution = Image_Ops.undilate_keep_resolution
decimate_image_float = Image_Ops.downsample
decimate_image_keep_resolution_float = Image_Ops.downsample_keep_resolution
invert_colors = Image_Ops.invert
threshold_image = Image_Ops.to_binary
add_to_image = Image_Ops.add
subtract_from_image = Image_Ops.subtract
multiply_image = Image_Ops.multiply
divide_image = Image_Ops.divide
add_salt_pepper_noise = Image_Ops.add_salt_pepper

show_histogram = Histogram.show
show_histograms = Histogram.show_multi
show_histogram_original_normalized = Histogram.show_original_and_normalized

convolve_image = Convolution.apply

equalize_histogram = Equalization.equalize
normalize_histogram = Equalization.equalize

match_histogram = Specialization.match

adjust_brightness_contrast = Enhancement.brightness_contrast
blur_image = Enhancement.blur_gaussian
erode_image = Morphology.erode

detect_edges = Edge_Detection.canny

thin_image = Morphology.thinning
glcm_features = GLCM.features
glcm_compute = GLCM.compute

otsu_threshold = Segmentation.otsu_threshold
watershed_segmentation = Segmentation.watershed
hough_lines = Transforms.hough_lines
hough_circles = Transforms.hough_circles
kmeans_clustering = Machine_Learning.kmeans
wiener_deblur = Restoration.wiener_filter

dft2 = Fourier.dft2
idft2 = Fourier.idft2
dct2 = Fourier.dct2
idct2 = Fourier.idct2
