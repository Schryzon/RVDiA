from typing import Literal, Sequence, Any
import numpy as np
import cv2
from pathlib import Path
import csv
import matplotlib.pyplot as plt
import os
import functools
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


def gpu_accelerated(func):
    """
    Decorator that auto-transfers the first argument (usually `image`) to the GPU
    if available, executes the function on GPU, and automatically transfers the result
    back to CPU (NumPy) to ensure downstream compatibility with OpenCV/Matplotlib.
    """
    @functools.wraps(func)
    def wrapper(image, *args, **kwargs):
        gpu_image = _smart(image)
        result = func(gpu_image, *args, **kwargs)
        if isinstance(result, tuple):
            return tuple(to_cpu(r) for r in result)
        return to_cpu(result)
    return wrapper


# print status on import
if _GPU_AVAILABLE:
    _thr = int(GPU_MIN_PIXELS ** 0.5)
    print(f"[accelerated] 🚀 GPU: {_GPU_NAME} ({_GPU_VRAM_MB} MB) | auto ≥{_thr}px")
    del _thr
else:
    print("[accelerated] 💤 CPU mode (CuPy not found)")


ArrayLike = np.ndarray
AxisMode = Literal["horizontal", "vertical"]
MatchMode = Literal["pad", "resize", "pad+resize", "cover", "contain", "crop", "tl-crop"]
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


def _resolve_ratio(value: int | float, dimension: int) -> int:
    """Convert a ratio (float in [0.0, 1.0]) to pixel count, or pass through raw int.

    Rules
    -----
    - int                     → returned as-is (pixel value)
    - float in [0.0, 1.0]    → int(round(value * dimension))
    - float outside [0.0,1.0]→ truncated to int (treated as a pixel value)
    """
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return int(round(value * dimension))
        return int(value)
    return int(value)


def _resolve_ratio_pair(
    x: int | float, y: int | float,
    dim_x: int, dim_y: int,
) -> tuple[int, int]:
    """Resolve a (x, y) pair where each element may be a ratio or raw pixel."""
    return _resolve_ratio(x, dim_x), _resolve_ratio(y, dim_y)


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


def _tl_crop(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    """Top-left crops an image without any centering or padding."""
    return image[:target_h, :target_w, ...]


def _fit_cover(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    """Resizes to cover the target dimensions (maintaining aspect ratio) and then center-crops."""
    h, w = image.shape[:2]
    scale = max(target_h / h, target_w / w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))
    new_h, new_w = max(new_h, target_h), max(new_w, target_w)
    resized = _resize_to(image, new_h, new_w)
    return _center_crop_or_pad(resized, target_h, target_w)


def _fit_contain(image: ArrayLike, target_h: int, target_w: int) -> ArrayLike:
    """Resizes to fit within target dimensions (maintaining aspect ratio) and then center-pads."""
    h, w = image.shape[:2]
    scale = min(target_h / h, target_w / w)
    new_h, new_w = int(round(h * scale)), int(round(w * scale))
    new_h, new_w = min(new_h, target_h), min(new_w, target_w)
    resized = _resize_to(image, new_h, new_w)
    return _center_crop_or_pad(resized, target_h, target_w)


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
    def show(image: ArrayLike, title: str = "Histogram", normalize: bool = False, color: str | list[str] = "black") -> None:
        """Display histogram for a single image."""
        image = to_cpu(_validate_image(image))
        plt.figure(figsize=(7, 4))
        if image.ndim == 2:
            plt.hist(image.ravel(), bins=256, range=(0, 256), color=color, density=normalize)
        else:
            # Handle color sequence or single color override
            if isinstance(color, (list, tuple)):
                ch_colors = color
            else:
                ch_colors = [color] * image.shape[2] if color != "black" else ["r", "g", "b"]
            
            for i in range(min(image.shape[2], len(ch_colors))):
                plt.hist(image[..., i].ravel(), bins=256, range=(0, 256), color=ch_colors[i], alpha=0.5, density=normalize)
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
                else:
                    ch_colors = [color_cfg] * img.shape[2] if color_cfg != "black" else ["r", "g", "b"]
                
                for ch in range(min(img.shape[2], len(ch_colors))):
                    plt.hist(img[..., ch].ravel(), bins=bins, range=value_range, color=ch_colors[ch], alpha=0.5, density=normalize)
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
        """Side-by-side histogram comparison of two images (plots side-by-side)."""
        Histogram.show_multi([img1, img2], titles=[title1, title2], normalize=normalize, ncols=2)

    @staticmethod
    def match_score(img1: ArrayLike, img2: ArrayLike, method: str = "correl") -> float:
        """Mathematical histogram comparison of two images and return a similarity score.
        
        Methods:
            - correl: Correlation (1.0 = perfect match)
            - chisqr: Chi-Square (0.0 = perfect match)
            - intersect: Intersection (higher = better match)
            - bhattacharyya: Bhattacharyya distance (0.0 = perfect match)
        """
        img1_cpu = to_cpu(_validate_image(img1))
        img2_cpu = to_cpu(_validate_image(img2))
        
        # Convert to grayscale for consistent 1D histogram comparison
        if img1_cpu.ndim == 3:
            img1_gray = cv2.cvtColor(img1_cpu, cv2.COLOR_RGB2GRAY)
        else:
            img1_gray = img1_cpu
            
        if img2_cpu.ndim == 3:
            img2_gray = cv2.cvtColor(img2_cpu, cv2.COLOR_RGB2GRAY)
        else:
            img2_gray = img2_cpu
            
        # Compute histograms
        hist1 = cv2.calcHist([img1_gray], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([img2_gray], [0], None, [256], [0, 256])
        
        # Normalize histograms
        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        
        # Map method string to OpenCV constants
        method_map = {
            "correl": cv2.HISTCMP_CORREL,
            "chisqr": cv2.HISTCMP_CHISQR,
            "intersect": cv2.HISTCMP_INTERSECT,
            "bhattacharyya": cv2.HISTCMP_BHATTACHARYYA
        }
        
        compare_method = method_map.get(method.lower(), cv2.HISTCMP_CORREL)
        score = cv2.compareHist(hist1, hist2, compare_method)
        
        return float(score)

    @staticmethod
    def show_combined(
        images: Sequence[ArrayLike],
        labels: Sequence[str] | None = None,
        colors: Sequence[str] | None = None,
        title: str = "Combined Histogram",
        normalize: bool = False,
        bins: int = 256,
        alpha: float = 0.5
    ) -> None:
        """Overlaps multiple histograms in the same plot area for direct comparison."""
        if not images:
            raise ValueError("images must be a non-empty sequence.")
        
        plt.figure(figsize=(10, 6))
        for i, img in enumerate(images):
            img_cpu = to_cpu(_validate_image(img, name=f"images[{i}]"))
            label = labels[i] if labels and i < len(labels) else f"Image {i}"
            color = colors[i] if colors and i < len(colors) else None
            
            # Use grayscale version for color images to keep the plot readable
            if img_cpu.ndim == 3:
                data = cv2.cvtColor(img_cpu, cv2.COLOR_RGB2GRAY).ravel()
            else:
                data = img_cpu.ravel()
                
            plt.hist(data, bins=bins, range=(0, 256), color=color, 
                     alpha=alpha, density=normalize, label=label)
        
        plt.title(title)
        plt.xlabel("Pixel Value")
        plt.ylabel("Density" if normalize else "Frequency")
        plt.legend()
        plt.grid(axis='y', alpha=0.3)
        plt.show()


class CSV:
    """Generic CSV reader with configurable header skipping.

    Designed for loading tabular data from CSV files where a variable
    number of header/metadata rows may precede the actual data.
    Also retains histogram-specific helpers from the old TargetHistogram class.
    """

    @staticmethod
    def read(
        path: str | Path,
        *,
        base_dir: str | Path | None = None,
        skip_rows: int = 0,
        has_header: bool = True,
        delimiter: str = ",",
        encoding: str = "utf-8",
        dtype: type = str,
    ) -> tuple[list[str] | None, list[list]]:
        """Read a CSV file with optional row skipping.

        Parameters
        ----------
        path : str | Path
            Path to the CSV file (absolute or relative to base_dir).
        base_dir : str | Path | None
            Base directory for relative paths. Defaults to script directory.
        skip_rows : int
            Number of leading rows to skip before the header/data (metadata, blank rows, etc.).
        has_header : bool
            If True, the first non-skipped row is treated as the column header.
        delimiter : str
            Column delimiter character.
        encoding : str
            File encoding.
        dtype : type
            Cast each cell to this type (default str, use float/int for numeric data).

        Returns
        -------
        (header, rows)
            header is a list of column names (or None if has_header=False).
            rows is a list of lists, one per data row.
        """
        base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
        p = Path(path)
        if not p.is_absolute():
            p = base / p

        with p.open("r", newline="", encoding=encoding) as f:
            # skip leading rows
            for _ in range(skip_rows):
                next(f, None)

            reader = csv.reader(f, delimiter=delimiter)
            header = None
            if has_header:
                header = next(reader, None)

            rows: list[list] = []
            for raw_row in reader:
                if dtype is str:
                    rows.append(raw_row)
                else:
                    rows.append([dtype(cell) for cell in raw_row])

        return header, rows

    @staticmethod
    def read_dict(
        path: str | Path,
        *,
        base_dir: str | Path | None = None,
        skip_rows: int = 0,
        delimiter: str = ",",
        encoding: str = "utf-8",
    ) -> list[dict[str, str]]:
        """Read a CSV file into a list of dicts (one per row).

        The first non-skipped row is always treated as the header.

        Parameters
        ----------
        skip_rows : int
            Number of leading rows to skip before the header.
        """
        base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
        p = Path(path)
        if not p.is_absolute():
            p = base / p

        with p.open("r", newline="", encoding=encoding) as f:
            for _ in range(skip_rows):
                next(f, None)

            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames is None:
                raise ValueError(f"CSV has no header row (after skipping {skip_rows} rows): {p}")
            return list(reader)

    # --- histogram-specific helpers (migrated from TargetHistogram) ---

    @staticmethod
    def load_histogram(
        path: str | Path,
        *,
        bins: int = 256,
        base_dir: str | Path | None = None,
        skip_rows: int = 0,
        intensity_col: str = "Intensity",
        count_col: str = "Sum of Pixel",
        dtype=np.float64,
        strict: bool = True,
    ) -> np.ndarray:
        """Load a histogram from a CSV file.

        Parameters
        ----------
        skip_rows : int
            Number of leading rows to skip before the header row.
        intensity_col : str
            Column name for the intensity/bin index.
        count_col : str
            Column name for the pixel count.
        """
        base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
        p = Path(path)
        if not p.is_absolute():
            p = base / p

        hist = np.zeros((bins,), dtype=dtype)

        with p.open("r", newline="", encoding="utf-8") as f:
            # skip leading metadata rows
            for _ in range(skip_rows):
                next(f, None)

            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"CSV has no header row (after skipping {skip_rows} rows): {p}")

            for row_idx, row in enumerate(reader, start=2 + skip_rows):
                try:
                    i = int(float(row[intensity_col]))
                    v = float(row[count_col])
                except KeyError as e:
                    raise KeyError(
                        f"Missing column {e} in {p}. Found columns: {reader.fieldnames}"
                    ) from e
                except Exception as e:
                    raise ValueError(f"Bad row at line {row_idx} in {p}: {row}") from e

                if 0 <= i < bins:
                    hist[i] = v
                elif strict:
                    raise ValueError(f"Intensity {i} out of range [0,{bins-1}] at line {row_idx} in {p}")

        return hist

    @staticmethod
    def normalize(hist: np.ndarray, eps: float = 1e-12) -> np.ndarray:
        hist = np.asarray(hist, dtype=np.float64)
        s = hist.sum()
        return hist / (s + eps)

    @staticmethod
    def plot_histogram(
        hist: np.ndarray,
        *,
        title: str = "Target Histogram (CSV)",
        color: str = "black",
        figsize: tuple[int, int] = (6, 4),
    ) -> None:
        """Plot histogram counts directly from a (bins,) array."""
        h = np.asarray(hist).ravel()
        x = np.arange(h.size)
        plt.figure(figsize=figsize)
        plt.bar(x, h, color=color, width=1.0)
        plt.title(title)
        plt.xlabel("Intensity")
        plt.ylabel("Sum of Pixel")
        plt.xlim(0, h.size - 1)
        plt.tight_layout()
        plt.show()

    @staticmethod
    def histogram_to_image(
        hist: np.ndarray,
        *,
        shape: tuple[int, int] | None = None,
        total_pixels: int = 256 * 256,
        bins: int = 256,
        dtype=np.uint8,
    ) -> np.ndarray:
        """
        Build a synthetic grayscale image whose histogram approximately matches `hist`.

        - If `shape` is given, uses total_pixels = shape[0]*shape[1].
        - Deterministic (no randomness).
        """
        h = np.asarray(hist, dtype=np.float64).ravel()
        if h.size != bins:
            raise ValueError(f"Expected hist with {bins} bins, got {h.size}")

        if shape is not None:
            H, W = int(shape[0]), int(shape[1])
            if H <= 0 or W <= 0:
                raise ValueError("shape must be positive")
            total_pixels = H * W
        else:
            if total_pixels <= 0:
                raise ValueError("total_pixels must be positive")
            H = int(np.sqrt(total_pixels))
            W = int(np.ceil(total_pixels / max(H, 1)))
            total_pixels = H * W

        p = CSV.normalize(h)
        expected = p * total_pixels

        base = np.floor(expected).astype(np.int64)
        remainder = int(total_pixels - base.sum())
        if remainder > 0:
            frac = expected - base
            idx = np.argsort(frac)[::-1][:remainder]
            base[idx] += 1
        elif remainder < 0:
            # remove from the largest bins first (rare, due to float issues)
            idx = np.argsort(base)[::-1][:(-remainder)]
            base[idx] = np.maximum(0, base[idx] - 1)

        values = np.repeat(np.arange(bins, dtype=np.int64), base)
        if values.size != total_pixels:
            # final safety fix (crop/pad)
            if values.size > total_pixels:
                values = values[:total_pixels]
            else:
                values = np.pad(values, (0, total_pixels - values.size), mode="edge")

        img = values.reshape(H, W).astype(dtype, copy=False)
        return img


# backward compat alias
class TargetHistogram:
    """Backward-compatible alias for CSV histogram methods."""
    load_csv = CSV.load_histogram
    normalize = CSV.normalize
    plot = CSV.plot_histogram
    to_image = CSV.histogram_to_image


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
            return np.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=np.float32)
        @staticmethod
        def prewitt_x() -> ArrayLike:
            return np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], dtype=np.float32)
        @staticmethod
        def prewitt_y() -> ArrayLike:
            return np.array([[1, 1, 1], [0, 0, 0], [-1, -1, -1]], dtype=np.float32)
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
        def identity_n(n: int = 5) -> ArrayLike:
            """NxN identity kernel (center = 1, rest = 0)."""
            if n < 1:
                raise ValueError("n must be a positive integer.")
            k = np.zeros((n, n), dtype=np.float32)
            k[n // 2, n // 2] = 1.0
            return k
        @staticmethod
        def sharpen_n(n: int = 5) -> ArrayLike:
            """NxN sharpening kernel (center = n*n, rest = -1, then normalized)."""
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            k = -np.ones((n, n), dtype=np.float32)
            k[n // 2, n // 2] = n * n
            return k
        @staticmethod
        def laplacian_n(n: int = 5) -> ArrayLike:
            """NxN laplacian kernel (center = -(n*n-1), rest = 1)."""
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            k = np.ones((n, n), dtype=np.float32)
            k[n // 2, n // 2] = -(n * n - 1)
            return k
        @staticmethod
        def high_pass(n: int = 3) -> ArrayLike:
            """NxN high-pass filter: identity minus box blur."""
            if n < 1 or n % 2 == 0:
                raise ValueError("n must be an odd positive integer.")
            lp = np.ones((n, n), dtype=np.float32) / (n * n)
            hp = -lp.copy()
            hp[n // 2, n // 2] += 1.0
            return hp
        @staticmethod
        def low_pass(n: int = 3) -> ArrayLike:
            """NxN low-pass filter (box blur). Alias for box_blur."""
            return Convolution.Kernels.box_blur(n)
        @staticmethod
        def smoothing(n: int = 3) -> ArrayLike:
            """NxN smoothing kernel (weighted center, uniform edges).

            The center pixel gets double weight relative to its neighbors.
            """
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            k = np.ones((n, n), dtype=np.float32)
            k[n // 2, n // 2] = 2.0
            return (k / k.sum()).astype(np.float32)
        @staticmethod
        def sharpening(n: int = 3) -> ArrayLike:
            """NxN sharpening kernel (center-boosted identity).

            Center = (n*n - 1) / (n*n), rest = -1/(n*n), then center += 1.
            This is original + high_pass.
            """
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            hp = Convolution.Kernels.high_pass(n)
            ident = np.zeros((n, n), dtype=np.float32)
            ident[n // 2, n // 2] = 1.0
            return ident + hp
        @staticmethod
        def diamond(n: int = 5) -> ArrayLike:
            """NxN diamond-shaped structuring element (1s form a diamond, 0s elsewhere).

            Default 5x5:
            [[0,0,1,0,0],
             [0,1,1,1,0],
             [1,1,1,1,1],
             [0,1,1,1,0],
             [0,0,1,0,0]]
            """
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            center = n // 2
            k = np.zeros((n, n), dtype=np.uint8)
            for r in range(n):
                dist = abs(r - center)
                for c in range(center - (center - dist), center + (center - dist) + 1):
                    k[r, c] = 1
            return k
        @staticmethod
        def cross(n: int = 3) -> ArrayLike:
            """NxN cross-shaped structuring element (1s on center row and column).

            Default 3x3:
            [[0,1,0],
             [1,1,1],
             [0,1,0]]
            """
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            k = np.zeros((n, n), dtype=np.uint8)
            center = n // 2
            k[center, :] = 1
            k[:, center] = 1
            return k
        @staticmethod
        def x_shape(n: int = 5) -> ArrayLike:
            """NxN X-shaped structuring element (1s on both diagonals).

            Default 5x5:
            [[1,0,0,0,1],
             [0,1,0,1,0],
             [0,0,1,0,0],
             [0,1,0,1,0],
             [1,0,0,0,1]]
            """
            if n < 3 or n % 2 == 0:
                raise ValueError("n must be an odd integer >= 3.")
            k = np.zeros((n, n), dtype=np.uint8)
            for i in range(n):
                k[i, i] = 1
                k[i, n - 1 - i] = 1
            return k

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
#  Filter (Mean / Median / Mode / Smoothing / Sharpening / LPF / HPF)
# ═══════════════════════════════════════════════════════════════════════════════

class Filter:
    """Sliding-window spatial filters and frequency-domain filter helpers.

    All sliding-window methods accept an arbitrary odd window size (3, 5, 7, 9, …).
    GPU-accelerated when CuPy is available.
    """

    # --- sliding window core ---

    @staticmethod
    def mean(image: ArrayLike, size: int = 3) -> ArrayLike:
        """Mean (average) filter using a sliding window.

        Each output pixel = average of the NxN neighborhood.
        This is equivalent to convolution with a box kernel.

        Parameters
        ----------
        image : ArrayLike
            Input image (grayscale or color).
        size : int
            Window size (must be odd, e.g. 3, 5, 7, 9).
        """
        if size < 1 or size % 2 == 0:
            raise ValueError("size must be an odd positive integer.")
        return Convolution.apply(image, Convolution.Kernels.box_blur(size), clip=True)

    @staticmethod
    def median(image: ArrayLike, size: int = 3) -> ArrayLike:
        """Median filter using a sliding window.

        Each output pixel = median of the NxN neighborhood.
        Excellent at removing salt-and-pepper noise while preserving edges.

        GPU path uses cupyx.scipy.ndimage.median_filter.
        CPU path uses a manual sliding window.

        Parameters
        ----------
        image : ArrayLike
            Input image (grayscale or color).
        size : int
            Window size (must be odd, e.g. 3, 5, 7, 9).
        """
        if size < 1 or size % 2 == 0:
            raise ValueError("size must be an odd positive integer.")
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        orig_dtype = image.dtype

        # GPU fast path
        if _GPU_AVAILABLE and xp_mod is cp:
            from cupyx.scipy.ndimage import median_filter as _gpu_median
            if image.ndim == 2:
                out = _gpu_median(image.astype(cp.float32), size=size)
            else:
                channels = [_gpu_median(image[..., i].astype(cp.float32), size=size)
                            for i in range(image.shape[2])]
                out = cp.stack(channels, axis=-1)
            return cp.clip(out, 0, 255).astype(orig_dtype)

        # CPU path — manual sliding window
        cpu_img = to_cpu(image)
        pad = size // 2

        def _median_channel(ch):
            padded = np.pad(ch.astype(np.float32), pad, mode="edge")
            h, w = ch.shape
            out = np.zeros_like(ch, dtype=np.float32)
            for y in range(h):
                for x in range(w):
                    window = padded[y:y + size, x:x + size]
                    out[y, x] = np.median(window)
            return out

        if cpu_img.ndim == 2:
            out = _median_channel(cpu_img)
        else:
            channels = [_median_channel(cpu_img[..., i]) for i in range(cpu_img.shape[2])]
            out = np.stack(channels, axis=-1)
        return np.clip(out, 0, 255).astype(orig_dtype)

    @staticmethod
    def mode(image: ArrayLike, size: int = 3) -> ArrayLike:
        """Mode (most frequent value) filter using a sliding window.

        Each output pixel = most common value in the NxN neighborhood.
        Useful for removing noise in images with few distinct intensity levels.

        Parameters
        ----------
        image : ArrayLike
            Input image (grayscale or color).
        size : int
            Window size (must be odd, e.g. 3, 5, 7, 9).
        """
        if size < 1 or size % 2 == 0:
            raise ValueError("size must be an odd positive integer.")
        image = _validate_image(image)
        cpu_img = to_cpu(image)
        orig_dtype = cpu_img.dtype
        pad = size // 2

        def _mode_channel(ch):
            padded = np.pad(ch.astype(np.uint8), pad, mode="edge")
            h, w = ch.shape
            out = np.zeros_like(ch, dtype=np.uint8)
            for y in range(h):
                for x in range(w):
                    window = padded[y:y + size, x:x + size].ravel()
                    # find mode via bincount (fast for uint8)
                    counts = np.bincount(window, minlength=256)
                    out[y, x] = np.argmax(counts)
            return out

        if cpu_img.ndim == 2:
            out = _mode_channel(cpu_img)
        else:
            channels = [_mode_channel(cpu_img[..., i]) for i in range(cpu_img.shape[2])]
            out = np.stack(channels, axis=-1)
        return out.astype(orig_dtype)

    # --- high-level filter wrappers ---

    @staticmethod
    def smooth(image: ArrayLike, size: int = 3) -> ArrayLike:
        """Smoothing filter — weighted center box kernel.

        Applies the smoothing kernel where the center pixel gets
        double weight relative to its neighbors.
        """
        if size < 3 or size % 2 == 0:
            raise ValueError("size must be an odd integer >= 3.")
        return Convolution.apply(image, Convolution.Kernels.smoothing(size), clip=True)

    @staticmethod
    def sharpen(image: ArrayLike, size: int = 3) -> ArrayLike:
        """Sharpening filter — enhances edges and fine detail.

        Uses identity + high-pass kernel of the given size.
        """
        if size < 3 or size % 2 == 0:
            raise ValueError("size must be an odd integer >= 3.")
        return Convolution.apply(image, Convolution.Kernels.sharpening(size), clip=True)

    @staticmethod
    def low_pass(image: ArrayLike, size: int = 3, method: Literal["box", "gaussian"] = "box", sigma: float = 1.0) -> ArrayLike:
        """Low-pass filter — removes high-frequency noise / smooths the image.

        Parameters
        ----------
        size : int
            Kernel size (must be odd).
        method : 'box' | 'gaussian'
            'box': uniform averaging (box blur).
            'gaussian': Gaussian-weighted averaging.
        sigma : float
            Standard deviation for Gaussian method.
        """
        if size < 1 or size % 2 == 0:
            raise ValueError("size must be an odd positive integer.")
        if method == "gaussian":
            kernel = Convolution.Kernels.gaussian(size, sigma)
        else:
            kernel = Convolution.Kernels.box_blur(size)
        return Convolution.apply(image, kernel, clip=True)

    @staticmethod
    def high_pass(image: ArrayLike, size: int = 3) -> ArrayLike:
        """High-pass filter — isolates edges and high-frequency detail.

        Computed as identity - low_pass (box blur of given size).
        """
        if size < 3 or size % 2 == 0:
            raise ValueError("size must be an odd integer >= 3.")
        return Convolution.apply(image, Convolution.Kernels.high_pass(size), clip=True)

    @staticmethod
    def band_pass(image: ArrayLike, low_size: int = 3, high_size: int = 9) -> ArrayLike:
        """Band-pass filter — keeps frequencies between low and high cutoffs.

        Applies a low-pass filter at high_size (keeps lower freqs),
        then subtracts a low-pass filter at low_size (removes lowest freqs).

        Parameters
        ----------
        low_size : int
            Smaller kernel size (removes lowest frequencies).
        high_size : int
            Larger kernel size (keeps up to these frequencies).
        """
        if low_size >= high_size:
            raise ValueError("low_size must be smaller than high_size.")
        lp_low = Filter.low_pass(image, size=low_size)
        lp_high = Filter.low_pass(image, size=high_size)
        # band = low_pass(big) - low_pass(small)
        return Image_Ops.subtract(lp_high, lp_low)


# ═══════════════════════════════════════════════════════════════════════════════
#  Image_Ops
# ═══════════════════════════════════════════════════════════════════════════════

class Image_Ops:
    """Static helpers for I/O, geometric transforms, color, pixel, and arithmetic operations."""

    # --- I/O ---
    @staticmethod
    def read(path: str, grayscale: bool = False, mode: Literal["imread", "opencv"] = "imread") -> ArrayLike:
        """Reads an image from path.
        
        Parameters
        ----------
        path : str
            Path to the image file.
        grayscale : bool
            If True, reads as grayscale.
        mode : 'imread' | 'opencv'
            'imread' (default): returns RGB (standard behavior).
            'opencv': returns BGR (OpenCV native behavior).
        """
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string.")
        flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        img = cv2.imread(path, flag)
        if img is None:
            raise FileNotFoundError(f"Could not read image from path: {path}")
        if not grayscale and mode == "imread":
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img

    @staticmethod
    def show(image: ArrayLike, title: str = "Image", show_axis: bool = False, mode: Literal["rgb", "bgr"] = "rgb", channel_color: Literal["red", "green", "blue", "gray", None] = None, keep_grays: bool = True) -> None:
        """Display an image. Set show_axis=True to see pixel coordinates.
        
        Parameters
        ----------
        image : ArrayLike
            Image to display.
        title : str
            Plot title.
        show_axis : bool
            Whether to show pixel coordinates.
        mode : 'rgb' | 'bgr'
            'rgb' (default): Standard color order for matplotlib.
            'bgr': OpenCV color order (will be converted to RGB for display).
        channel_color : 'red' | 'green' | 'blue' | 'gray' | None
            Display a 2D grayscale channel in a specific color. Grays remain gray if 'gray' or None.
        keep_grays : bool
            If True, keeps baseline gray components gray. If False, displays pure isolated channels.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3 and mode == "bgr":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
        if channel_color and image.ndim == 3 and channel_color in ("red", "green", "blue"):
            R_ch = image[:, :, 0]
            G_ch = image[:, :, 1]
            B_ch = image[:, :, 2]
            if keep_grays:
                gray_ch = np.minimum(np.minimum(R_ch, G_ch), B_ch)
            else:
                gray_ch = np.zeros_like(R_ch)
            if channel_color == "red":
                image = np.stack([R_ch, gray_ch, gray_ch], axis=-1)
            elif channel_color == "green":
                image = np.stack([gray_ch, G_ch, gray_ch], axis=-1)
            elif channel_color == "blue":
                image = np.stack([gray_ch, gray_ch, B_ch], axis=-1)
        elif channel_color and image.ndim == 2 and channel_color in ("red", "green", "blue"):
            colored = np.zeros((image.shape[0], image.shape[1], 3), dtype=image.dtype)
            if channel_color == "red":
                colored[:, :, 0] = image
            elif channel_color == "green":
                colored[:, :, 1] = image
            elif channel_color == "blue":
                colored[:, :, 2] = image
            image = colored
            
        # Auto-cast float images that use 0-255 scale to prevent matplotlib 0-1 clipping artifacts
        if image.dtype in (np.float32, np.float64) and np.max(image) > 1.0:
            image = np.clip(np.round(image), 0, 255).astype(np.uint8)
            
        plt.figure(figsize=(6, 6))
        
        # Enforce correct vmin/vmax so pure white images do not normalize to black
        kwargs = {}
        if image.ndim == 2:
            kwargs["cmap"] = "gray"
            if image.dtype == bool:
                kwargs["vmin"], kwargs["vmax"] = 0, 1
            elif image.dtype == np.uint8:
                kwargs["vmin"], kwargs["vmax"] = 0, 255
            elif image.dtype in (np.float32, np.float64):
                kwargs["vmin"], kwargs["vmax"] = 0.0, 1.0
                
        plt.imshow(image, **kwargs)
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
    def create_white_like(image: ArrayLike) -> ArrayLike:
        """Creates a pure-white image with the same shape/dtype as the reference image."""
        image = _validate_image(image)
        if image.ndim == 2:
            return np.full(image.shape, 255, dtype=image.dtype)
        # assume last dim is channels
        return np.full(image.shape, (255,) * image.shape[2], dtype=image.dtype)

    @staticmethod
    def create_blanks_like(images: Sequence[ArrayLike], color: int | tuple[int, ...] = 0) -> list[ArrayLike]:
        """Creates a list of blank images matching a sequence of input images."""
        return [Image_Ops.create_blank_like(img, color=color) for img in images]

    @staticmethod
    def show_pair(original: ArrayLike, processed: ArrayLike, title_left: str = "Before", title_right: str = "After", show_axis: bool = False, mode: Literal["rgb", "bgr"] = "rgb") -> None:
        original = to_cpu(_validate_image(original, name="original"))
        processed = to_cpu(_validate_image(processed, name="processed"))
        
        if mode == "bgr":
            if original.ndim == 3:
                original = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
            if processed.ndim == 3:
                processed = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
                
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
        mode: Literal["rgb", "bgr"] = "rgb"
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
        if image.ndim == 3 and mode == "bgr":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
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
        mode: Literal["rgb", "bgr"] = "rgb"
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
            if mode == "bgr" and img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
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
        cmap: str | None = "auto",
        mode: Literal["rgb", "bgr"] = "rgb",
        channel_colors: Sequence[str | None] | str | None = None,
        keep_grays: bool = True
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
        channel_colors : Sequence[str | None] | str | None
            Color to use for 2D images. 'red', 'green', 'blue', 'gray', or None.
        keep_grays : bool
            If True, keeps baseline gray components gray. If False, displays pure isolated channels.
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
        
        # Check if we can reconstruct the color channels to keep grays gray
        can_reconstruct = False
        if (
            keep_grays
            and isinstance(channel_colors, (list, tuple))
            and len(images) == 3
            and all(to_cpu(img).ndim == 2 for img in images)
            and set(c for c in channel_colors if c) == {"red", "green", "blue"}
        ):
            try:
                r_idx = channel_colors.index("red")
                g_idx = channel_colors.index("green")
                b_idx = channel_colors.index("blue")
                R_rec = to_cpu(images[r_idx])
                G_rec = to_cpu(images[g_idx])
                B_rec = to_cpu(images[b_idx])
                if R_rec.shape == G_rec.shape == B_rec.shape:
                    gray_rec = np.minimum(np.minimum(R_rec, G_rec), B_rec)
                    can_reconstruct = True
            except Exception:
                pass

        plt.figure(figsize=figsize)
        for i, img in enumerate(images):
            plt.subplot(nrows, ncols, i + 1)
            
            img_cpu = to_cpu(_validate_image(img, name=f"images[{i}]"))
            if mode == "bgr" and img_cpu.ndim == 3:
                img_cpu = cv2.cvtColor(img_cpu, cv2.COLOR_BGR2RGB)
            
            c_color = channel_colors[i] if isinstance(channel_colors, (list, tuple)) else channel_colors
            
            if can_reconstruct:
                if i == r_idx:
                    img_cpu = np.stack([R_rec, gray_rec, gray_rec], axis=-1)
                elif i == g_idx:
                    img_cpu = np.stack([gray_rec, G_rec, gray_rec], axis=-1)
                elif i == b_idx:
                    img_cpu = np.stack([gray_rec, gray_rec, B_rec], axis=-1)
            elif c_color and img_cpu.ndim == 3 and c_color in ("red", "green", "blue"):
                R_ch = img_cpu[:, :, 0]
                G_ch = img_cpu[:, :, 1]
                B_ch = img_cpu[:, :, 2]
                if keep_grays:
                    gray_ch = np.minimum(np.minimum(R_ch, G_ch), B_ch)
                else:
                    gray_ch = np.zeros_like(R_ch)
                if c_color == "red":
                    img_cpu = np.stack([R_ch, gray_ch, gray_ch], axis=-1)
                elif c_color == "green":
                    img_cpu = np.stack([gray_ch, G_ch, gray_ch], axis=-1)
                elif c_color == "blue":
                    img_cpu = np.stack([gray_ch, gray_ch, B_ch], axis=-1)
            elif c_color and img_cpu.ndim == 2 and c_color in ("red", "green", "blue"):
                colored = np.zeros((img_cpu.shape[0], img_cpu.shape[1], 3), dtype=img_cpu.dtype)
                if c_color == "red":
                    colored[:, :, 0] = img_cpu
                elif c_color == "green":
                    colored[:, :, 1] = img_cpu
                elif c_color == "blue":
                    colored[:, :, 2] = img_cpu
                img_cpu = colored
            
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
    def crop(image: ArrayLike, top: int | float = 0, bottom: int | float = 0, left: int | float = 0, right: int | float = 0) -> ArrayLike:
        """Crop image by removing pixels from each edge.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of that axis)
        or raw pixel counts (int).

        Examples: ``crop(img, top=0.1)`` removes the top 10% of rows.
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        top    = _resolve_ratio(top, h)
        bottom = _resolve_ratio(bottom, h)
        left   = _resolve_ratio(left, w)
        right  = _resolve_ratio(right, w)
        if min(top, bottom, left, right) < 0:
            raise ValueError("Crop values must be >= 0.")
        y1, y2 = top, h - bottom
        x1, x2 = left, w - right
        if y1 >= y2 or x1 >= x2:
            raise ValueError("Crop removes all pixels. Reduce crop values.")
        return image[y1:y2, x1:x2]

    @staticmethod
    def crop_circle(image: ArrayLike, center: tuple[int | float, int | float] | None = None, radius: int | float | None = None, crop_to_box: bool = True) -> ArrayLike:
        """Crops an image into a circle. Areas outside the circle are black.

        Parameters accept **ratios** (float 0.0–1.0):
        - center: fraction of (width, height)
        - radius: fraction of min(width, height)
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if center is None:
            center = (w // 2, h // 2)
        else:
            center = _resolve_ratio_pair(center[0], center[1], w, h)
        if radius is None:
            radius = min(h, w) // 2
        else:
            radius = _resolve_ratio(radius, min(h, w))
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
    def rotate_circle(image: ArrayLike, center: tuple[int | float, int | float] | None = None, radius: int | float | None = None, angle: float = 0) -> ArrayLike:
        """Rotates only the pixels within a circular region.

        Parameters accept **ratios** (float 0.0–1.0):
        - center: fraction of (width, height)
        - radius: fraction of min(width, height)
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if center is None:
            center = (w // 2, h // 2)
        else:
            center = _resolve_ratio_pair(center[0], center[1], w, h)
        if radius is None:
            radius = min(h, w) // 2
        else:
            radius = _resolve_ratio(radius, min(h, w))
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
    def translate(image: ArrayLike, shift_x: int | float = 0, shift_y: int | float = 0) -> ArrayLike:
        """Translate (shift) an image.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of width/height).
        Negative ratios shift left/up.
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        # resolve ratios — allow negative floats for direction
        if isinstance(shift_x, float) and -1.0 <= shift_x <= 1.0:
            shift_x = int(round(shift_x * w))
        else:
            shift_x = int(shift_x)
        if isinstance(shift_y, float) and -1.0 <= shift_y <= 1.0:
            shift_y = int(round(shift_y * h))
        else:
            shift_y = int(shift_y)
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
    def pad(image: ArrayLike, top: int | float = 0, bottom: int | float = 0, left: int | float = 0, right: int | float = 0, mode: PadMode = "constant", value: int = 0) -> ArrayLike:
        """Pad image borders.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of height/width).

        Example: ``pad(img, top=0.1)`` adds 10%-of-height padding to the top.
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        top    = _resolve_ratio(top, h)
        bottom = _resolve_ratio(bottom, h)
        left   = _resolve_ratio(left, w)
        right  = _resolve_ratio(right, w)
        if mode in ("zero", "constant"):
            if image.ndim == 2:
                return np.pad(image, ((top, bottom), (left, right)), mode="constant", constant_values=value)
            return np.pad(image, ((top, bottom), (left, right), (0, 0)), mode="constant", constant_values=value)
        np_mode = mode if mode != "zero" else "constant"
        if image.ndim == 2:
            return np.pad(image, ((top, bottom), (left, right)), mode=np_mode)
        return np.pad(image, ((top, bottom), (left, right), (0, 0)), mode=np_mode)

    @staticmethod
    def slice(image: ArrayLike, start: int | float, end: int | float, axis: AxisMode = "horizontal") -> ArrayLike:
        """Slice a horizontal or vertical strip from an image.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of that axis).

        Examples
        --------
        ``slice(img, 0.0, 0.5)``          → top half (horizontal)
        ``slice(img, 0.25, 0.75, 'vertical')`` → middle 50% columns
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        if axis == "horizontal":
            start = _resolve_ratio(start, h)
            end   = _resolve_ratio(end, h)
            if not (0 <= start < end <= h):
                raise ValueError(f"For horizontal slicing, use 0 <= start < end <= {h}. Got start={start}, end={end}.")
            return image[start:end, ...]
        if axis == "vertical":
            start = _resolve_ratio(start, w)
            end   = _resolve_ratio(end, w)
            if not (0 <= start < end <= w):
                raise ValueError(f"For vertical slicing, use 0 <= start < end <= {w}. Got start={start}, end={end}.")
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
    def add(image1: ArrayLike, image2: ArrayLike | int | float) -> ArrayLike:
        """Adds an image and another image or scalar, bounding to max values."""
        i1 = to_cpu(_validate_image(image1, name="image1"))
        
        if isinstance(image2, (int, float)):
            res = i1.astype(np.float32) + float(image2)
            if i1.dtype == np.uint8:
                return np.clip(np.round(res), 0, 255).astype(np.uint8)
            return np.clip(res, 0, None).astype(i1.dtype)
            
        i2 = to_cpu(_validate_image(image2, name="image2"))
        i1, i2 = _match_channels(i1, i2)
        if i1.shape[:2] != i2.shape[:2]:
            i2 = _resize_to(i2, i1.shape[0], i1.shape[1])
        if i1.dtype == np.uint8:
            return cv2.add(i1, i2)
        return np.clip(i1 + i2, 0, None).astype(i1.dtype)

    @staticmethod
    def subtract(image1: ArrayLike, image2: ArrayLike | int | float) -> ArrayLike:
        """Subtracts an image or scalar from image1, bounding to 0."""
        i1 = to_cpu(_validate_image(image1, name="image1"))
        
        if isinstance(image2, (int, float)):
            res = i1.astype(np.float32) - float(image2)
            if i1.dtype == np.uint8:
                return np.clip(np.round(res), 0, 255).astype(np.uint8)
            return np.clip(res, 0, None).astype(i1.dtype)
            
        i2 = to_cpu(_validate_image(image2, name="image2"))
        i1, i2 = _match_channels(i1, i2)
        if i1.shape[:2] != i2.shape[:2]:
            i2 = _resize_to(i2, i1.shape[0], i1.shape[1])
        if i1.dtype == np.uint8:
            return cv2.subtract(i1, i2)
        return np.clip(i1 - i2, 0, None).astype(i1.dtype)

    @staticmethod
    def multiply(image1: ArrayLike, image2: ArrayLike | int | float) -> ArrayLike:
        """Multiplies an image by another image or scalar."""
        i1 = to_cpu(_validate_image(image1, name="image1"))
        
        if isinstance(image2, (int, float)):
            res = i1.astype(np.float32) * float(image2)
            if i1.dtype == np.uint8:
                return np.clip(np.round(res), 0, 255).astype(np.uint8)
            return res.astype(i1.dtype)
            
        i2 = to_cpu(_validate_image(image2, name="image2"))
        i1, i2 = _match_channels(i1, i2)
        if i1.shape[:2] != i2.shape[:2]:
            i2 = _resize_to(i2, i1.shape[0], i1.shape[1])
        
        if i1.dtype == np.uint8:
            return cv2.multiply(i1, i2, scale=1/255.0)
        return np.multiply(i1, i2)

    @staticmethod
    def divide(image1: ArrayLike, image2: ArrayLike | int | float) -> ArrayLike:
        """Divides image1 by another image or scalar. Avoids division by zero."""
        i1 = to_cpu(_validate_image(image1, name="image1"))
        
        if isinstance(image2, (int, float)):
            val = float(image2)
            if val == 0.0:
                val = 1e-5
            res = i1.astype(np.float32) / val
            if i1.dtype == np.uint8:
                return np.clip(np.round(res), 0, 255).astype(np.uint8)
            return res.astype(i1.dtype)
            
        i2 = to_cpu(_validate_image(image2, name="image2"))
        i1, i2 = _match_channels(i1, i2)
        if i1.shape[:2] != i2.shape[:2]:
            i2 = _resize_to(i2, i1.shape[0], i1.shape[1])
        
        if i1.dtype == np.uint8:
            return cv2.divide(i1, i2, scale=255.0)
        
        with np.errstate(divide='ignore', invalid='ignore'):
            res = np.divide(i1, i2)
            res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
        return res.astype(i1.dtype)

    @staticmethod
    def blend(image1: ArrayLike, image2: ArrayLike, alpha: float = 0.5, beta: float | None = None, gamma: float = 0.0, match: MatchMode = "resize") -> ArrayLike:
        image1 = to_cpu(_validate_image(image1, name="image1"))
        image2 = to_cpu(_validate_image(image2, name="image2"))
        if not (0.0 <= alpha <= 1.0):
            raise ValueError("alpha must be in [0, 1].")
        beta = (1.0 - alpha) if beta is None else beta
        if match not in ("resize", "pad", "pad+resize", "cover", "contain", "crop", "tl-crop"):
            raise ValueError("match must be 'resize', 'pad', 'pad+resize', 'cover', 'contain', 'crop', or 'tl-crop'.")
        image1, image2 = _match_channels(image1, image2)
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]
        if (h1, w1) != (h2, w2):
            if match == "resize":
                image2 = _resize_to(image2, h1, w1)
            elif match == "pad+resize":
                image2 = _center_crop_or_pad(image2, h1, w1)
            elif match == "cover":
                if h1 * w1 <= h2 * w2:
                    image2 = _fit_cover(image2, h1, w1)
                else:
                    image1 = _fit_cover(image1, h2, w2)
            elif match == "crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _center_crop_or_pad(image2, h1, w1)
                else:
                    image1 = _center_crop_or_pad(image1, h2, w2)
            elif match == "tl-crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _tl_crop(image2, h1, w1)
                else:
                    image1 = _tl_crop(image1, h2, w2)
            elif match == "contain":
                image2 = _fit_contain(image2, h1, w1)
            else:
                target_h, target_w = max(h1, h2), max(w1, w2)
                image1 = _pad_to(image1, target_h, target_w)
                image2 = _pad_to(image2, target_h, target_w)
        out = cv2.addWeighted(image1.astype(np.float32), alpha, image2.astype(np.float32), beta, gamma)
        if np.issubdtype(image1.dtype, np.integer):
            out = np.clip(out, 0, 255)
        return out.astype(image1.dtype)

    @staticmethod
    def overlay(bg: ArrayLike, fg: ArrayLike, position: tuple[int | float, int | float] = (0, 0)) -> ArrayLike:
        """Slaps the foreground image on top of the background at a specific (x, y) position.
        
        Parameters
        ----------
        bg : ArrayLike
            Background image.
        fg : ArrayLike
            Foreground image to be placed on top.
        position : tuple[int | float, int | float]
            (x, y) coordinates for the top-left corner of the foreground.
            Accepts **ratios** (float 0.0–1.0 = fraction of background width/height).
        """
        bg = _validate_image(bg, name="bg")
        fg = _validate_image(fg, name="fg")
        
        # Dispatch to GPU if smart mode allows
        bg = _smart(bg)
        fg = _smart(fg)
        
        # Match channels FIRST so 'out' has the correct dimensionality
        bg, fg = _match_channels(bg, fg)
        xp_mod = _xp(bg)
        
        out = bg.copy()
        bh, bw = bg.shape[:2]
        fh, fw = fg.shape[:2]
        x, y = _resolve_ratio_pair(position[0], position[1], bw, bh)
        
        # Calculate valid intersection boundaries
        y1, y2 = max(0, y), min(bh, y + fh)
        x1, x2 = max(0, x), min(bw, x + fw)
        
        # Calculate corresponding foreground slices
        fy1, fx1 = max(0, -y), max(0, -x)
        fy2, fx2 = fy1 + (y2 - y1), fx1 + (x2 - x1)
        
        if y1 < y2 and x1 < x2:
            # Slices are already channel-matched
            out[y1:y2, x1:x2, ...] = fg[fy1:fy2, fx1:fx2, ...]
            
        return out

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
        elif match == "pad+resize":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _center_crop_or_pad(image1, target_h, image1.shape[1])
            image2 = _center_crop_or_pad(image2, target_h, image2.shape[1])
        elif match == "cover":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _fit_cover(image1, target_h, image1.shape[1])
            image2 = _fit_cover(image2, target_h, image2.shape[1])
        elif match == "contain":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _fit_contain(image1, target_h, image1.shape[1])
            image2 = _fit_contain(image2, target_h, image2.shape[1])
        elif match == "crop":
            target_h = min(image1.shape[0], image2.shape[0])
            image1 = _center_crop_or_pad(image1, target_h, image1.shape[1])
            image2 = _center_crop_or_pad(image2, target_h, image2.shape[1])
        elif match == "tl-crop":
            target_h = min(image1.shape[0], image2.shape[0])
            image1 = _tl_crop(image1, target_h, image1.shape[1])
            image2 = _tl_crop(image2, target_h, image2.shape[1])
        elif match == "pad":
            target_h = max(image1.shape[0], image2.shape[0])
            image1 = _pad_to(image1, target_h, image1.shape[1])
            image2 = _pad_to(image2, target_h, image2.shape[1])
        else:
            raise ValueError("match must be 'pad', 'resize', 'pad+resize', 'cover', 'contain', 'crop', or 'tl-crop'.")
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
        elif match == "pad+resize":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _center_crop_or_pad(image1, image1.shape[0], target_w)
            image2 = _center_crop_or_pad(image2, image2.shape[0], target_w)
        elif match == "cover":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _fit_cover(image1, image1.shape[0], target_w)
            image2 = _fit_cover(image2, image2.shape[0], target_w)
        elif match == "contain":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _fit_contain(image1, image1.shape[0], target_w)
            image2 = _fit_contain(image2, image2.shape[0], target_w)
        elif match == "crop":
            target_w = min(image1.shape[1], image2.shape[1])
            image1 = _center_crop_or_pad(image1, image1.shape[0], target_w)
            image2 = _center_crop_or_pad(image2, image2.shape[0], target_w)
        elif match == "tl-crop":
            target_w = min(image1.shape[1], image2.shape[1])
            image1 = _tl_crop(image1, image1.shape[0], target_w)
            image2 = _tl_crop(image2, image2.shape[0], target_w)
        elif match == "pad":
            target_w = max(image1.shape[1], image2.shape[1])
            image1 = _pad_to(image1, image1.shape[0], target_w)
            image2 = _pad_to(image2, image2.shape[0], target_w)
        else:
            raise ValueError("match must be 'pad', 'resize', 'pad+resize', 'cover', 'contain', 'crop', or 'tl-crop'.")
        return np.concatenate([image1, image2], axis=0)

    @staticmethod
    def concat(image1: ArrayLike, image2: ArrayLike, axis: Literal["horizontal", "vertical"] = "horizontal", match: MatchMode = "pad") -> ArrayLike:
        if axis == "vertical":
            return Image_Ops.concat_v(image1, image2, match)
        return Image_Ops.concat_h(image1, image2, match)

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

    @staticmethod
    def crop_to_content(image: ArrayLike, tolerance: int = 0) -> ArrayLike:
        """Crops the image to the bounding box of non-zero (or > tolerance) pixels.
        Useful for removing black borders."""
        image = _validate_image(image)
        xp_mod = _xp(image)
        
        if image.ndim == 3:
            gray = image.sum(axis=2)
        else:
            gray = image
            
        mask = gray > tolerance
        rows = xp_mod.any(mask, axis=1)
        cols = xp_mod.any(mask, axis=0)
        
        if not xp_mod.any(rows):
            return image
            
        rmin, rmax = int(xp_mod.where(rows)[0][0]), int(xp_mod.where(rows)[0][-1])
        cmin, cmax = int(xp_mod.where(cols)[0][0]), int(xp_mod.where(cols)[0][-1])
        
        return image[rmin:rmax+1, cmin:cmax+1, ...]

    # --- Color ---
    @staticmethod
    def to_grayscale(image: ArrayLike, method: Literal["opencv", "manual", "average"] = "opencv") -> ArrayLike:
        """Converts a color image to grayscale.
        
        Parameters
        ----------
        image : ArrayLike
            Color image to convert.
        method : 'opencv' | 'manual' | 'average'
            'opencv' (default): Uses cv2.cvtColor (standard weighted).
            'manual': Uses Gray = 0.299R + 0.587G + 0.114B.
            'average': Uses Gray = (R + G + B) / 3.
        """
        image = _validate_image(image)
        if image.ndim == 2:
            return image.copy()
        
        if method == "manual":
            xp_mod = _xp(image)
            img_f = image.astype(xp_mod.float32)
            r, g, b = img_f[..., 0], img_f[..., 1], img_f[..., 2]
            gray = 0.299 * r + 0.587 * g + 0.114 * b
            return gray.astype(image.dtype)
            
        if method == "average":
            xp_mod = _xp(image)
            img_f = image.astype(xp_mod.float32)
            gray = img_f.mean(axis=2)
            return gray.astype(image.dtype)
            
        return cv2.cvtColor(to_cpu(image), cv2.COLOR_RGB2GRAY)

    @staticmethod
    def to_color(image: ArrayLike) -> ArrayLike:
        """Converts a grayscale image to a 3-channel RGB image by replicating the channel."""
        image = _validate_image(image)
        if image.ndim == 3:
            return image.copy()
        
        # Dispatch to GPU if smart mode allows
        image = _smart(image)
        xp_mod = _xp(image)
        
        return xp_mod.repeat(image[..., None], 3, axis=2)

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
    def channel_split(image: ArrayLike, as_3d: bool = False) -> list[ArrayLike]:
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            return [image[..., np.newaxis] if as_3d else image.copy()]
        
        if as_3d:
            return [image[..., i:i+1] for i in range(image.shape[2])]
        return [image[..., i] for i in range(image.shape[2])]

    @staticmethod
    def rgb_split(image: ArrayLike, as_3d: bool = False) -> tuple[ArrayLike, ArrayLike, ArrayLike]:
        """Extracts R, G, B channels from a color image."""
        image = _validate_image(image)
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError("rgb_split requires a 3-channel color image.")
        
        if as_3d:
            return image[..., 0:1], image[..., 1:2], image[..., 2:3]
        return image[..., 0], image[..., 1], image[..., 2]

    @staticmethod
    def channel_merge(channels: Sequence[ArrayLike]) -> ArrayLike:
        if len(channels) == 0:
            raise ValueError("channels must be non-empty.")
        
        first = _validate_image(channels[0])
        xp_mod = _xp(first)
        
        processed = []
        for i, c in enumerate(channels):
            c = _validate_image(c, name=f"channels[{i}]")
            if c.ndim == 3 and c.shape[2] == 1:
                processed.append(c[..., 0])
            elif c.ndim == 2:
                processed.append(c)
            else:
                raise ValueError(f"Each channel must be 2D (H,W) or 3D single-channel (H,W,1). Got shape {c.shape}")
                
        return xp_mod.stack(processed, axis=-1)

    @staticmethod
    def rgb_merge(r: ArrayLike, g: ArrayLike, b: ArrayLike) -> ArrayLike:
        """Recombines R, G, B channels into a color image."""
        r = _validate_image(r, name="r")
        g = _validate_image(g, name="g")
        b = _validate_image(b, name="b")
        xp_mod = _xp(r)
        
        def _to_2d(ch):
            if ch.ndim == 3 and ch.shape[2] == 1:
                return ch[..., 0]
            elif ch.ndim == 2:
                return ch
            else:
                raise ValueError(f"Channel must be 2D (H,W) or 3D single-channel (H,W,1). Got shape {ch.shape}")
                
        return xp_mod.stack([_to_2d(r), _to_2d(g), _to_2d(b)], axis=-1)

    @staticmethod
    def show_rgb_channels(image: ArrayLike, title: str = "RGB Channels", figsize: tuple[int, int] = (15, 5), mode: Literal["rgb", "bgr"] = "rgb") -> None:
        """Displays the original image and its R, G, B channels side-by-side.
        
        Parameters
        ----------
        image : ArrayLike
            Color image to visualize.
        title : str
            Title for the entire plot.
        figsize : tuple[int, int]
            Figure size.
        mode : 'rgb' | 'bgr'
            Color mode of the input image.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim != 3:
            raise ValueError("show_rgb_channels requires a 3-channel color image.")
        
        # If BGR, convert to RGB for standard splitting logic
        if mode == "bgr":
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
        r, g, b = Image_Ops.rgb_split(image)
        
        titles = ["Original", "Red Channel", "Green Channel", "Blue Channel"]
        images = [image, r, g, b]
        
        Image_Ops.show_collection(images, titles=titles, ncols=4, figsize=figsize)

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
    def overlay_text(image: ArrayLike, text: str, position: tuple[int | float, int | float] = (10, 30), font_scale: float = 1.0, color: tuple[int, ...] = (255, 255, 255), thickness: int = 2) -> ArrayLike:
        """Overlay text on an image.

        position accepts **ratios** (float 0.0–1.0 = fraction of width/height).
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        pos = _resolve_ratio_pair(position[0], position[1], w, h)
        out = image.copy()
        cv2.putText(out, text, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
        return out

    # --- Arithmetic (GPU-accelerated) ---
    @staticmethod
    def add(image: ArrayLike, val) -> ArrayLike:
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        if isinstance(val, (np.ndarray,)) or (_GPU_AVAILABLE and isinstance(val, cp.ndarray)):
            val = _validate_image(val, name="val")
            if _GPU_AVAILABLE and xp_mod == cp:
                if isinstance(val, np.ndarray):
                    val = cp.asarray(val)
            else:
                val = to_cpu(val)
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
            if _GPU_AVAILABLE and xp_mod == cp:
                if isinstance(val, np.ndarray):
                    val = cp.asarray(val)
            else:
                val = to_cpu(val)
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
            if _GPU_AVAILABLE and xp_mod == cp:
                if isinstance(val, np.ndarray):
                    val = cp.asarray(val)
            else:
                val = to_cpu(val)
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
            if _GPU_AVAILABLE and xp_mod == cp:
                if isinstance(val, np.ndarray):
                    val = cp.asarray(val)
            else:
                val = to_cpu(val)
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

    @staticmethod
    @gpu_accelerated
    def pencil_sketch(image: ArrayLike, ksize: int = 21, sigma: float = 0.0) -> ArrayLike:
        image = _validate_image(image)
        xp_mod = _xp(image)
        if image.ndim == 3:
            gray = (0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]).astype(xp_mod.uint8)
        else:
            gray = image.astype(xp_mod.uint8)
            
        inv = 255 - gray
        
        inv_cpu = to_cpu(inv)
        if ksize % 2 == 0:
            ksize += 1
        blur_cpu = cv2.GaussianBlur(inv_cpu, (ksize, ksize), sigma)
        blur = to_gpu(blur_cpu) if xp_mod is not np else blur_cpu
        
        denom = 255 - blur
        denom = xp_mod.where(denom == 0, 1, denom)
        sketch = (gray.astype(xp_mod.float32) * 255) / denom.astype(xp_mod.float32)
        sketch = xp_mod.clip(sketch, 0, 255).astype(xp_mod.uint8)
        
        return xp_mod.stack([sketch, sketch, sketch], axis=-1)

    @staticmethod
    @gpu_accelerated
    def posterize(image: ArrayLike, levels: int = 4) -> ArrayLike:
        image = _validate_image(image)
        xp_mod = _xp(image)
        if levels < 2:
            levels = 2
        step = 255 / (levels - 1)
        posterized = xp_mod.round(image.astype(xp_mod.float32) / step) * step
        return xp_mod.clip(posterized, 0, 255).astype(xp_mod.uint8)

    @staticmethod
    @gpu_accelerated
    def solarize(image: ArrayLike, threshold: int = 128) -> ArrayLike:
        image = _validate_image(image)
        xp_mod = _xp(image)
        solarized = xp_mod.where(image >= threshold, 255 - image, image)
        return solarized.astype(image.dtype)

    @staticmethod
    def eval_pipeline(image1: ArrayLike, pipeline_str: str, image2: ArrayLike | None = None) -> ArrayLike:
        image1 = _validate_image(image1)
        xp_mod = _xp(image1)
        current = image1.copy() if xp_mod is not np else np.copy(image1)
        
        ops = [o.strip() for o in pipeline_str.split(",") if o.strip()]
        
        for op in ops:
            parts = op.split(":")
            name = parts[0].lower()
            args = parts[1:]
            
            if name == "grayscale":
                current = Image_Ops.to_grayscale(current)
                if current.ndim == 2 and image1.ndim == 3:
                    current = xp_mod.stack([current, current, current], axis=-1)
            elif name == "invert":
                current = Image_Ops.invert(current)
            elif name == "circle":
                current = Image_Ops.crop_circle(current)
            elif name == "sepia":
                img_f = current.astype(xp_mod.float32)
                sepia_matrix = xp_mod.array([[0.393, 0.769, 0.189],
                                             [0.349, 0.686, 0.168],
                                             [0.272, 0.534, 0.131]], dtype=xp_mod.float32)
                if xp_mod is not np:
                    sepia_img = img_f @ sepia_matrix.T
                else:
                    sepia_img = cv2.transform(img_f, sepia_matrix)
                current = xp_mod.clip(sepia_img, 0, 255).astype(xp_mod.uint8)
            elif name == "blur":
                strength = 5
                if args:
                    try: strength = int(args[0])
                    except ValueError: pass
                kernel = Convolution.Kernels.box_blur(strength)
                current = Convolution.apply(current, kernel)
            elif name == "sharpen":
                kernel = Convolution.Kernels.sharpen()
                current = Convolution.apply(current, kernel)
            elif name == "emboss":
                kernel = Convolution.Kernels.emboss()
                current = Convolution.apply(current, kernel)
            elif name == "pixelate":
                size = 16
                if args:
                    try: size = int(args[0])
                    except ValueError: pass
                current_cpu = to_cpu(current)
                h, w = current_cpu.shape[:2]
                small = cv2.resize(current_cpu, (max(1, w // size), max(1, h // size)), interpolation=cv2.INTER_LINEAR)
                res = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "vignette":
                sigma = 150
                if args:
                    try: sigma = int(args[0])
                    except ValueError: pass
                current_cpu = to_cpu(current)
                h, w = current_cpu.shape[:2]
                kernel_x = cv2.getGaussianKernel(w, sigma)
                kernel_y = cv2.getGaussianKernel(h, sigma)
                kernel = kernel_y * kernel_x.T
                mask = kernel / kernel.max()
                vignette_img = np.copy(current_cpu)
                for i in range(min(3, current_cpu.ndim)):
                    if current_cpu.ndim == 3:
                        vignette_img[:, :, i] = vignette_img[:, :, i] * mask
                    else:
                        vignette_img = vignette_img * mask
                res = vignette_img.astype(np.uint8)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "gamma":
                g = 1.5
                if args:
                    try: g = float(args[0])
                    except ValueError: pass
                current = Enhancement.gamma_correction(current, g)
            elif name == "log":
                current = Enhancement.log_transform(current)
            elif name == "posterize":
                levels = 4
                if args:
                    try: levels = int(args[0])
                    except ValueError: pass
                current = Image_Ops.posterize(current, levels)
            elif name == "solarize":
                threshold = 128
                if args:
                    try: threshold = int(args[0])
                    except ValueError: pass
                current = Image_Ops.solarize(current, threshold)
            elif name == "sketch":
                ksize = 21
                if args:
                    try: ksize = int(args[0])
                    except ValueError: pass
                current = Image_Ops.pencil_sketch(current, ksize)
            elif name == "flip":
                axis = "horizontal"
                if args and args[0].lower() in ["horizontal", "vertical"]:
                    axis = args[0].lower()
                current = Image_Ops.flip(current, axis)
            elif name == "rotate":
                angle = 90.0
                direction = "ccw"
                if args:
                    try: angle = float(args[0])
                    except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["cw", "ccw"]:
                    direction = args[1].lower()
                current = Image_Ops.rotate(current, angle, direction)
            elif name == "adjust":
                brightness = 1.0
                contrast = 0
                if args:
                    try: brightness = float(args[0])
                    except ValueError: pass
                if len(args) > 1:
                    try: contrast = int(args[1])
                    except ValueError: pass
                current = Enhancement.brightness_contrast(current, brightness, contrast)
            elif name == "edge":
                method = "canny"
                if args and args[0].lower() in ["canny", "sobel", "laplacian", "prewitt", "roberts", "scharr"]:
                    method = args[0].lower()
                current_cpu = to_cpu(current)
                if method == "canny": res = Edge_Detection.canny(current_cpu)
                elif method == "sobel": res = Edge_Detection.sobel(current_cpu)
                elif method == "laplacian": res = Edge_Detection.laplacian(current_cpu)
                elif method == "prewitt": res = Edge_Detection.prewitt(current_cpu)
                elif method == "roberts": res = Edge_Detection.roberts(current_cpu)
                else: res = Edge_Detection.scharr(current_cpu)
                if res.ndim == 2:
                    res = cv2.cvtColor(res, cv2.COLOR_GRAY2RGB)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "noise":
                ntype = "salt_pepper"
                if args and args[0].lower() in ["salt_pepper", "gaussian", "poisson"]:
                    ntype = args[0].lower()
                if ntype == "salt_pepper": current = Image_Ops.add_salt_pepper(current)
                elif ntype == "gaussian": current = Enhancement.add_gaussian_noise(current)
                else: current = Enhancement.add_poisson_noise(current)
            elif name == "equalize":
                method = "global"
                if args and args[0].lower() in ["global", "clahe", "adaptive"]:
                    method = args[0].lower()
                if method == "global": current = Equalization.equalize(current)
                elif method == "clahe": current = Equalization.clahe(current)
                else: current = Equalization.adaptive(current)
            elif name == "threshold":
                val = 127
                method = "binary"
                if args:
                    try: val = int(args[0])
                    except ValueError: pass
                if len(args) > 1 and args[1].lower() in ["binary", "otsu"]:
                    method = args[1].lower()
                current = Image_Ops.threshold(current, val, method == "otsu")
            elif name == "autocrop":
                tol = 0
                if args:
                    try: tol = int(args[0])
                    except ValueError: pass
                current = Image_Ops.autocrop(current, tol)
            elif name in ["erode", "dilate"]:
                iter_count = 1
                k_size = 3
                if args:
                    try: iter_count = int(args[0])
                    except ValueError: pass
                if len(args) > 1:
                    try: k_size = int(args[1])
                    except ValueError: pass
                if name == "erode": current = Morphology.erode(current, k_size, iter_count)
                else: current = Morphology.dilate(current, k_size, iter_count)
            elif name == "skeleton":
                current_cpu = to_cpu(current)
                if current_cpu.ndim == 3:
                    gray = cv2.cvtColor(current_cpu, cv2.COLOR_RGB2GRAY)
                else:
                    gray = current_cpu
                _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                skel = Morphology.skeleton(binary)
                res = cv2.cvtColor(skel, cv2.COLOR_GRAY2RGB)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "lpf":
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
                current_cpu = to_cpu(current)
                if ftype == "ideal": res = FreqFilter.ideal_lpf(current_cpu, cutoff)
                elif ftype == "butterworth": res = FreqFilter.butterworth_lpf(current_cpu, cutoff, order)
                else: res = FreqFilter.gaussian_lpf(current_cpu, cutoff)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "hpf":
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
                current_cpu = to_cpu(current)
                if ftype == "ideal": res = FreqFilter.ideal_hpf(current_cpu, cutoff)
                elif ftype == "butterworth": res = FreqFilter.butterworth_hpf(current_cpu, cutoff, order)
                else: res = FreqFilter.gaussian_hpf(current_cpu, cutoff)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "homomorphic":
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
                current_cpu = to_cpu(current)
                res = FreqFilter.homomorphic(current_cpu, gamma_l, gamma_h, cutoff)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "fft":
                current_cpu = to_cpu(current)
                res = FreqFilter.fft(current_cpu)
                current = to_gpu(res) if xp_mod is not np else res
            elif name == "dct":
                current_cpu = to_cpu(current)
                res = FreqFilter.dct(current_cpu)
                current = to_gpu(res) if xp_mod is not np else res
            elif image2 is not None:
                img2_val = _validate_image(image2)
                if name == "blend":
                    alpha = 0.5
                    if args:
                        try: alpha = float(args[0])
                        except ValueError: pass
                    current = Image_Ops.blend(current, img2_val, alpha=alpha)
                elif name == "composite":
                    mode = "normal"
                    match_mode = "resize"
                    if args:
                        mode = args[0].lower()
                    if len(args) > 1:
                        match_mode = args[1].lower()
                    current = Image_Ops.composite(current, img2_val, mode=mode, match_mode=match_mode)
                elif name == "concat":
                    axis = "horizontal"
                    if args and args[0].lower() in ["horizontal", "vertical"]:
                        axis = args[0].lower()
                    current = Image_Ops.concat(current, img2_val, axis=axis)
                elif name == "match":
                    current = Specialization.match(current, img2_val)
                elif name == "transfer":
                    current = Specialization.transfer_color(current, img2_val)
                    
        return current

    @staticmethod
    def intensity_threshold_mask(
        image1: ArrayLike,
        image2: ArrayLike,
        threshold: float,
        match: MatchMode = "resize",
        channel: Literal["intensity", "r", "g", "b"] = "intensity"
    ) -> ArrayLike:
        """
        Replaces elements of image1 with elements of image2 exactly at that location 
        if image1's intensity or target color channel is above the threshold.
        
        Supports both grayscale and colored images.
        
        Parameters
        ----------
        image1 : ArrayLike
            Base image. Intensity is calculated from this image.
        image2 : ArrayLike
            Replacement image.
        threshold : float
            Intensity threshold (X).
        match : MatchMode
            How to handle size mismatches ('resize' or 'pad').
        channel : Literal['intensity', 'r', 'g', 'b']
            Target channel to threshold (default is 'intensity').
        """
        image1 = _validate_image(image1, name="image1")
        image2 = _validate_image(image2, name="image2")
        
        # Dispatch to GPU if smart mode allows
        image1 = _smart(image1)
        image2 = _smart(image2)
        xp_mod = _xp(image1)
        
        # Ensure spatial dimensions match
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]
        if (h1, w1) != (h2, w2):
            if match == "resize":
                image2 = _resize_to(image2, h1, w1)
                if xp_mod is cp:
                    image2 = cp.asarray(image2)
            elif match == "pad+resize":
                image2 = _center_crop_or_pad(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            elif match == "cover":
                if h1 * w1 <= h2 * w2:
                    image2 = _fit_cover(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _fit_cover(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _center_crop_or_pad(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _center_crop_or_pad(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "tl-crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _tl_crop(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _tl_crop(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "contain":
                image2 = _fit_contain(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            else:
                image2 = _pad_to(image2, h1, w1) if (h2 <= h1 and w2 <= w1) else _resize_to(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
        
        # Match channels before processing
        image1, image2 = _match_channels(image1, image2)
        
        # Calculate comparison channel or intensity
        if image1.ndim == 2:
            val_to_compare = image1
        else:
            img_f = image1.astype(xp_mod.float32)
            if channel == "r":
                val_to_compare = img_f[..., 0] # Red channel in RGB
            elif channel == "g":
                val_to_compare = img_f[..., 1] # Green channel in RGB
            elif channel == "b":
                val_to_compare = img_f[..., 2] # Blue channel in RGB
            else:
                # Manual intensity: 0.299R + 0.587G + 0.114B (RGB standard)
                val_to_compare = 0.299 * img_f[..., 0] + 0.587 * img_f[..., 1] + 0.114 * img_f[..., 2]
            
        # Create mask
        mask = val_to_compare > threshold
        
        # Apply mask
        if image1.ndim == 3:
            mask = mask[..., xp_mod.newaxis]
            
        return xp_mod.where(mask, image2, image1)

    @staticmethod
    def color_intensity_threshold_mask(
        image1: ArrayLike,
        image2: ArrayLike,
        threshold: float,
        match: MatchMode = "resize",
        channel: Literal["intensity", "r", "g", "b"] = "intensity"
    ) -> ArrayLike:
        """
        Replaces elements of color image1 with elements of image2 if the intensity
        or target color channel (r, g, b) is above the threshold. Specifically optimized for BGR color images.
        """
        return Image_Ops.intensity_threshold_mask(image1, image2, threshold, match, channel)

    @staticmethod
    def intensity_threshold_mask_inv(
        image1: ArrayLike,
        image2: ArrayLike,
        threshold: float,
        match: MatchMode = "resize",
        channel: Literal["intensity", "r", "g", "b"] = "intensity"
    ) -> ArrayLike:
        """
        Replaces elements of image1 with elements of image2 exactly at that location
        if image1's intensity or target color channel is BELOW or equal to the threshold.

        Inverse of intensity_threshold_mask (mask = intensity <= threshold).

        Parameters
        ----------
        image1 : ArrayLike
            Base image. Intensity is calculated from this image.
        image2 : ArrayLike
            Replacement image.
        threshold : float
            Intensity threshold (X).
        match : MatchMode
            How to handle size mismatches ('resize' or 'pad').
        channel : Literal['intensity', 'r', 'g', 'b']
            Target channel to threshold (default is 'intensity').
        """
        image1 = _validate_image(image1, name="image1")
        image2 = _validate_image(image2, name="image2")

        image1 = _smart(image1)
        image2 = _smart(image2)
        xp_mod = _xp(image1)

        # ensure spatial dimensions match
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]
        if (h1, w1) != (h2, w2):
            if match == "resize":
                image2 = _resize_to(image2, h1, w1)
                if xp_mod is cp:
                    image2 = cp.asarray(image2)
            elif match == "pad+resize":
                image2 = _center_crop_or_pad(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            elif match == "cover":
                if h1 * w1 <= h2 * w2:
                    image2 = _fit_cover(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _fit_cover(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _center_crop_or_pad(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _center_crop_or_pad(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "tl-crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _tl_crop(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _tl_crop(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "contain":
                image2 = _fit_contain(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            else:
                image2 = _pad_to(image2, h1, w1) if (h2 <= h1 and w2 <= w1) else _resize_to(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)

        image1, image2 = _match_channels(image1, image2)

        # calculate comparison channel or intensity
        if image1.ndim == 2:
            val_to_compare = image1
        else:
            img_f = image1.astype(xp_mod.float32)
            if channel == "r":
                val_to_compare = img_f[..., 0] # Red channel in RGB
            elif channel == "g":
                val_to_compare = img_f[..., 1] # Green channel in RGB
            elif channel == "b":
                val_to_compare = img_f[..., 2] # Blue channel in RGB
            else:
                # Manual intensity: 0.299R + 0.587G + 0.114B (RGB standard)
                val_to_compare = 0.299 * img_f[..., 0] + 0.587 * img_f[..., 1] + 0.114 * img_f[..., 2]

        # inverted mask: val_to_compare <= threshold
        mask = val_to_compare <= threshold

        if image1.ndim == 3:
            mask = mask[..., xp_mod.newaxis]

        return xp_mod.where(mask, image2, image1)

    @staticmethod
    def intensity_range_mask(
        image1: ArrayLike,
        image2: ArrayLike,
        low: float,
        high: float,
        match: MatchMode = "resize",
        channel: Literal["intensity", "r", "g", "b"] = "intensity"
    ) -> ArrayLike:
        """
        Replaces elements of image1 with elements of image2 exactly at that location
        if image1's intensity or target color channel falls within [low, high] (inclusive).

        Parameters
        ----------
        image1 : ArrayLike
            Base image. Intensity is calculated from this image.
        image2 : ArrayLike
            Replacement image.
        low : float
            Lower bound of intensity range (inclusive).
        high : float
            Upper bound of intensity range (inclusive).
        match : MatchMode
            How to handle size mismatches ('resize' or 'pad').
        channel : Literal['intensity', 'r', 'g', 'b']
            Target channel to threshold (default is 'intensity').
        """
        if low > high:
            raise ValueError(f"low ({low}) must be <= high ({high}).")

        image1 = _validate_image(image1, name="image1")
        image2 = _validate_image(image2, name="image2")

        image1 = _smart(image1)
        image2 = _smart(image2)
        xp_mod = _xp(image1)

        # ensure spatial dimensions match
        h1, w1 = image1.shape[:2]
        h2, w2 = image2.shape[:2]
        if (h1, w1) != (h2, w2):
            if match == "resize":
                image2 = _resize_to(image2, h1, w1)
                if xp_mod is cp:
                    image2 = cp.asarray(image2)
            elif match == "pad+resize":
                image2 = _center_crop_or_pad(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            elif match == "cover":
                if h1 * w1 <= h2 * w2:
                    image2 = _fit_cover(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _fit_cover(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _center_crop_or_pad(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _center_crop_or_pad(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "tl-crop":
                if h1 * w1 <= h2 * w2:
                    image2 = _tl_crop(image2, h1, w1)
                    if xp_mod is cp and not isinstance(image2, cp.ndarray):
                        image2 = cp.asarray(image2)
                else:
                    image1 = _tl_crop(image1, h2, w2)
                    if xp_mod is cp and not isinstance(image1, cp.ndarray):
                        image1 = cp.asarray(image1)
            elif match == "contain":
                image2 = _fit_contain(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)
            else:
                image2 = _pad_to(image2, h1, w1) if (h2 <= h1 and w2 <= w1) else _resize_to(image2, h1, w1)
                if xp_mod is cp and not isinstance(image2, cp.ndarray):
                    image2 = cp.asarray(image2)

        image1, image2 = _match_channels(image1, image2)

        # calculate comparison channel or intensity
        if image1.ndim == 2:
            val_to_compare = image1
        else:
            img_f = image1.astype(xp_mod.float32)
            if channel == "r":
                val_to_compare = img_f[..., 0] # Red channel in RGB
            elif channel == "g":
                val_to_compare = img_f[..., 1] # Green channel in RGB
            elif channel == "b":
                val_to_compare = img_f[..., 2] # Blue channel in RGB
            else:
                # Manual intensity: 0.299R + 0.587G + 0.114B (RGB standard)
                val_to_compare = 0.299 * img_f[..., 0] + 0.587 * img_f[..., 1] + 0.114 * img_f[..., 2]

        # in-range mask: low <= val_to_compare <= high
        mask = (val_to_compare >= low) & (val_to_compare <= high)

        if image1.ndim == 3:
            mask = mask[..., xp_mod.newaxis]

        return xp_mod.where(mask, image2, image1)

    @staticmethod
    def fill_enclosed_from_edges(
        edge_image: ArrayLike,
        *,
        threshold: int = 1,
        close_size: int = 5,
        close_iter: int = 1,
        include_edges: bool = True,
    ) -> np.ndarray:
        """Fill enclosed regions (inside edges) with white (255), return a binary mask (0/255).

        Steps:
        1) threshold edge magnitude -> binary edges
        2) (optional) close gaps with morphology close
        3) flood-fill from border to mark background
        4) invert background-marked result => enclosed regions
        """
        edge_image = _validate_image(edge_image)
        edge_cpu = to_cpu(edge_image)

        # ensure 2D uint8
        if edge_cpu.ndim == 3:
            edge_cpu = cv2.cvtColor(edge_cpu, cv2.COLOR_BGR2GRAY)

        if edge_cpu.dtype != np.uint8:
            edge_u8 = cv2.normalize(edge_cpu, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        else:
            edge_u8 = edge_cpu

        edges = np.where(edge_u8 > threshold, 255, 0).astype(np.uint8)

        if close_size and close_size > 1:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
            edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, k, iterations=close_iter)

        h, w = edges.shape[:2]
        
        # Clear 1-pixel boundary to prevent border artifacts from blocking flood fill
        edges[0, :] = 0
        edges[-1, :] = 0
        edges[:, 0] = 0
        edges[:, -1] = 0
        
        # Pad with 1-pixel border of 0s to guarantee (0,0) is a background pixel and 
        # all border-adjacent background components are connected to it
        padded = np.pad(edges, pad_width=1, mode='constant', constant_values=0)
        hp, wp = padded.shape[:2]
        ff_mask = np.zeros((hp + 2, wp + 2), dtype=np.uint8)

        # Flood fill from the padded corner (0, 0)
        cv2.floodFill(padded, ff_mask, (0, 0), 128)

        # Crop back to the original size
        work = padded[1:-1, 1:-1]

        filled = (work == 0).astype(np.uint8) * 255  # enclosed regions remain 0, so they become white
        if include_edges:
            filled = cv2.bitwise_or(filled, edges)

        return filled

    @staticmethod
    def paint_white(image: ArrayLike, mask: ArrayLike) -> np.ndarray:
        """Paint pixels where mask>0 to pure white on the given image."""
        image = _validate_image(image)
        mask = _validate_image(mask)

        img = to_cpu(image).copy()
        m = to_cpu(mask)
        if m.ndim == 3:
            m = m[..., 0]
        m = m > 0

        if np.issubdtype(img.dtype, np.integer):
            white = np.iinfo(img.dtype).max
        else:
            white = 1.0

        if img.ndim == 2:
            img[m] = white
        else:
            img[m, :] = white

        return img

    @staticmethod
    def apply_binary_mask(
        image: ArrayLike,
        mask: ArrayLike,
        *,
        threshold: int = 0,
        background: int | tuple[int, ...] = 0,
        match: MatchMode = "resize",
    ) -> np.ndarray:
        """Apply a BW mask to an image.

        mask > threshold  -> keep original pixel
        mask <= threshold -> set to `background`

        Works for grayscale or color images. Returns CPU numpy array.
        """
        image = _validate_image(image, name="image")
        mask = _validate_image(mask, name="mask")

        img = to_cpu(image)
        m = to_cpu(mask)

        if m.ndim == 3:
            # mask might be RGB; use first channel (or you can cvtColor)
            m = m[..., 0]

        # ensure uint8-like range for thresholding
        if m.dtype != np.uint8:
            m = cv2.normalize(m, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # match spatial sizes if needed
        if img.shape[:2] != m.shape[:2]:
            h, w = img.shape[:2]
            if match == "resize":
                m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
            else:
                # fallback: resize (keeps behavior simple)
                m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)

        keep = m > threshold  # bool mask (H,W)

        out = img.copy()

        # decide background "color"
        if img.ndim == 2:
            bg = int(background) if not isinstance(background, tuple) else int(background[0])
            out[~keep] = bg
            return out

        # color image
        if isinstance(background, tuple):
            bg_tuple = background
        else:
            bg_tuple = (int(background),) * img.shape[2]

        out[~keep, :] = np.array(bg_tuple, dtype=out.dtype)
        return out
    
    @staticmethod
    def rect_mask_like(
        image: ArrayLike,
        x0: int | float,
        y0: int | float,
        x1: int | float,
        y1: int | float,
        *,
        inside_value: int = 255,
        outside_value: int = 0,
    ) -> np.ndarray:
        """Create a rectangular binary mask (H,W) for `image`.

        x/y can be ints (pixels) or floats in [0..1] meaning ratio of width/height.
        The ROI uses NumPy slicing semantics: [y0:y1, x0:x1] (end is exclusive).
        """
        img = to_cpu(_validate_image(image))
        h, w = img.shape[:2]

        # allow ratio coordinates
        def _coord(v, dim):
            if isinstance(v, float):
                return int(round(v * dim))
            return int(v)

        x0i = _coord(x0, w); x1i = _coord(x1, w)
        y0i = _coord(y0, h); y1i = _coord(y1, h)

        # normalize & clamp
        xa, xb = sorted((x0i, x1i))
        ya, yb = sorted((y0i, y1i))
        xa = max(0, min(w, xa)); xb = max(0, min(w, xb))
        ya = max(0, min(h, ya)); yb = max(0, min(h, yb))

        mask = np.full((h, w), outside_value, dtype=np.uint8)
        mask[ya:yb, xa:xb] = inside_value
        return mask

    @staticmethod
    def apply_rect_mask(
        image: ArrayLike,
        x0: int | float,
        y0: int | float,
        x1: int | float,
        y1: int | float,
        *,
        keep: Literal["inside", "outside"] = "inside",
        background: int | tuple[int, ...] = 0,
    ) -> np.ndarray:
        """Keep pixels inside/outside a rectangle; set the rest to `background`."""
        img = _validate_image(image)
        mask = Image_Ops.rect_mask_like(img, x0, y0, x1, y1)

        if keep == "outside":
            mask = 255 - mask

        # reuse your binary-mask applicator if present; otherwise do it inline
        if hasattr(Image_Ops, "apply_binary_mask"):
            return Image_Ops.apply_binary_mask(img, mask, threshold=0, background=background)

        out = to_cpu(img).copy()
        m = mask > 0

        if out.ndim == 2:
            bg = int(background) if not isinstance(background, tuple) else int(background[0])
            out[~m] = bg
            return out

        if not isinstance(background, tuple):
            bg_tuple = (int(background),) * out.shape[2]
        else:
            bg_tuple = background
        out[~m, :] = np.array(bg_tuple, dtype=out.dtype)
        return out

    # --- Mask manipulation utilities ---

    @staticmethod
    def zero_border(
        mask: ArrayLike, *,
        top: int | float = 0.0,
        bottom: int | float = 0.0,
        left: int | float = 0.0,
        right: int | float = 0.0,
    ) -> ArrayLike:
        """Zero out border regions of an image or mask.

        Useful for removing edge artifacts, boundary gradients, or
        constraining a mask to a central region of interest.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of height/width)
        or raw pixel counts (int).

        Parameters
        ----------
        mask : ArrayLike
            Input image or mask (2D or 3D).
        top, bottom : int | float
            Rows to zero from the top / bottom edge.
        left, right : int | float
            Columns to zero from the left / right edge.
        """
        mask = _validate_image(mask)
        out = to_cpu(mask).copy()
        h, w = out.shape[:2]
        t = _resolve_ratio(top, h)
        b = _resolve_ratio(bottom, h)
        l = _resolve_ratio(left, w)
        r = _resolve_ratio(right, w)
        if t > 0:
            out[:t, ...] = 0
        if b > 0:
            out[h - b:, ...] = 0
        if l > 0:
            out[:, :l, ...] = 0
        if r > 0:
            out[:, w - r:, ...] = 0
        return out

    @staticmethod
    def zero_ellipse(
        mask: ArrayLike,
        center: tuple[int | float, int | float],
        radii: tuple[int | float, int | float],
    ) -> ArrayLike:
        """Zero out pixels inside an elliptical region.

        Useful for removing isolated noise clusters or excluding
        known artifact zones from a binary mask.

        Parameters accept **ratios** (float 0.0–1.0 = fraction of height/width).

        Parameters
        ----------
        mask : ArrayLike
            Input image or mask (2D or 3D).
        center : (cy, cx)
            Ellipse center as (row, col). Ratios resolve against (height, width).
        radii : (ry, rx)
            Ellipse semi-axes as (row-radius, col-radius).
            Ratios resolve against (height, width).
        """
        mask = _validate_image(mask)
        out = to_cpu(mask).copy()
        h, w = out.shape[:2]
        cy = _resolve_ratio(center[0], h)
        cx = _resolve_ratio(center[1], w)
        ry = _resolve_ratio(radii[0], h)
        rx = _resolve_ratio(radii[1], w)
        yy, xx = np.ogrid[:h, :w]
        ellipse = ((yy - cy) ** 2 / max(ry, 1) ** 2 +
                   (xx - cx) ** 2 / max(rx, 1) ** 2) <= 1
        out[ellipse] = 0
        return out

    @staticmethod
    def fade_border(
        mask: ArrayLike, *,
        side: Literal["left", "right", "top", "bottom"] = "left",
        margin: int | float = 0.2,
        fade_width: int | float = 0.05,
    ) -> ArrayLike:
        """Apply a gradient fade from a specified edge of a mask.

        Pixels before ``margin`` are fully zeroed; between ``margin``
        and ``margin + fade_width`` they linearly ramp from 0 to 1.
        Useful for smooth boundary refinement and anti-aliasing hard
        segmentation edges.

        Parameters accept **ratios** (float 0.0–1.0).

        Parameters
        ----------
        mask : ArrayLike
            Input mask (2D grayscale, uint8).
        side : 'left' | 'right' | 'top' | 'bottom'
            Edge to fade from.
        margin : int | float
            Dead zone width (fully zeroed).
        fade_width : int | float
            Transition zone width (linear ramp).
        """
        mask = _validate_image(mask)
        out = to_cpu(mask).copy()
        h, w = out.shape[:2]

        if side in ("left", "right"):
            m = _resolve_ratio(margin, w)
            fw = _resolve_ratio(fade_width, w)
        else:
            m = _resolve_ratio(margin, h)
            fw = _resolve_ratio(fade_width, h)

        fw = max(fw, 1)  # avoid zero-length linspace

        gradient: np.ndarray
        if side == "left":
            gradient = np.ones((h, w), dtype=np.float32)
            gradient[:, :m] = 0
            gradient[:, m:m + fw] = np.linspace(0, 1, fw, dtype=np.float32)
        elif side == "right":
            gradient = np.ones((h, w), dtype=np.float32)
            gradient[:, w - m:] = 0
            end = w - m
            gradient[:, end - fw:end] = np.linspace(1, 0, fw, dtype=np.float32)
        elif side == "top":
            gradient = np.ones((h, w), dtype=np.float32)
            gradient[:m, :] = 0
            gradient[m:m + fw, :] = np.linspace(0, 1, fw, dtype=np.float32).reshape(-1, 1)
        elif side == "bottom":
            gradient = np.ones((h, w), dtype=np.float32)
            gradient[h - m:, :] = 0
            end = h - m
            gradient[end - fw:end, :] = np.linspace(1, 0, fw, dtype=np.float32).reshape(-1, 1)
        else:
            raise ValueError("side must be 'left', 'right', 'top', or 'bottom'.")

        result = (out.astype(np.float32) * gradient).astype(np.uint8)
        return result

    @staticmethod
    def seal_mask(
        mask: ArrayLike,
        size: int = 21,
        threshold_dilate: int = 50,
        threshold_erode: int = 160,
    ) -> ArrayLike:
        """Seal internal gaps in a binary mask using spatial averaging.

        Approximates a closing operation (dilate → erode) by applying
        a mean filter and re-thresholding at each step. Useful for
        filling discontinuities in segmentation masks (e.g. face gaps,
        clothing fold shadows).

        Parameters
        ----------
        mask : ArrayLike
            Binary mask (0/255).
        size : int
            Mean filter kernel size (must be odd).
        threshold_dilate : int
            Threshold after dilation step (lower = more aggressive fill).
        threshold_erode : int
            Threshold after erosion step (higher = tighter boundary).
        """
        mask = _validate_image(mask)
        # dilate step
        dilated = to_cpu(Filter.mean(mask, size=size))
        dilated = (dilated > threshold_dilate).astype(np.uint8) * 255
        # erode back
        eroded = to_cpu(Filter.mean(dilated, size=size))
        closed = (eroded > threshold_erode).astype(np.uint8) * 255
        return closed

    @staticmethod
    def prune_mask(
        mask: ArrayLike,
        size: int = 45,
        threshold_erode: int = 230,
        threshold_restore: int = 15,
    ) -> ArrayLike:
        """Remove thin protrusions from a binary mask using spatial averaging.

        Approximates an opening operation (erode → dilate) by applying
        a mean filter and re-thresholding. Preserves the primary body
        mass while eliminating small stray regions.

        Parameters
        ----------
        mask : ArrayLike
            Binary mask (0/255).
        size : int
            Mean filter kernel size (must be odd).
        threshold_erode : int
            Threshold for erosion step (higher = more aggressive pruning).
        threshold_restore : int
            Threshold for restoration step (lower = more generous restore).
        """
        mask = _validate_image(mask)
        # erode step
        eroded = to_cpu(Filter.mean(mask, size=size))
        eroded = (eroded > threshold_erode).astype(np.uint8) * 255
        # restore (dilate back)
        restored = to_cpu(Filter.mean(eroded, size=size))
        opened = (restored > threshold_restore).astype(np.uint8) * 255
        return opened


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
            src_cdf /= (src_cdf[-1] + 1e-8)
            ref_cdf = np.cumsum(ref_hist).astype(np.float64)
            ref_cdf /= (ref_cdf[-1] + 1e-8)

            # Robust mapping: Find the nearest neighbor in the reference CDF
            # We use broadcasting to create a 256x256 distance matrix
            diff = np.abs(ref_cdf[:, None] - src_cdf[None, :])
            lut = np.argmin(diff, axis=0).astype(np.uint8)

            matched = lut[src.astype(np.uint8)]
            return matched.reshape(src.shape)

        if image.ndim == 2 and reference.ndim == 2:
            return _match_channel(image, reference)
        image, reference = _match_channels(image, reference)
        out = np.zeros_like(image)
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
    def denoise_nlmeans(image: ArrayLike, h: float = 10, template_window: int = 7, search_window: int = 11) -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        if image.ndim == 2:
            return cv2.fastNlMeansDenoising(image, None, h, template_window, search_window)
        return cv2.fastNlMeansDenoisingColored(image, None, h, h, template_window, search_window)

    @staticmethod
    def contrast_stretch(image: ArrayLike, low_pct: float = 2.0, high_pct: float = 98.0) -> ArrayLike:
        """Percentile-based contrast stretching.

        Maps pixel values so that `low_pct`-th percentile → 0
        and `high_pct`-th percentile → 255.

        Parameters
        ----------
        low_pct : float
            Lower percentile (default 2%).
        high_pct : float
            Upper percentile (default 98%).
        """
        image = _validate_image(image)
        image = _smart(image)
        xp_mod = _xp(image)
        img_f = image.astype(xp_mod.float64)

        if image.ndim == 2:
            lo = float(xp_mod.percentile(img_f, low_pct))
            hi = float(xp_mod.percentile(img_f, high_pct))
            if hi - lo < 1e-6:
                return image.copy()
            out = (img_f - lo) / (hi - lo) * 255.0
            return xp_mod.clip(out, 0, 255).astype(image.dtype)

        channels = []
        for ch in range(image.shape[2]):
            ch_f = img_f[..., ch]
            lo = float(xp_mod.percentile(ch_f, low_pct))
            hi = float(xp_mod.percentile(ch_f, high_pct))
            if hi - lo < 1e-6:
                channels.append(ch_f)
            else:
                channels.append((ch_f - lo) / (hi - lo) * 255.0)
        out = xp_mod.stack(channels, axis=-1)
        return xp_mod.clip(out, 0, 255).astype(image.dtype)

    @staticmethod
    def piecewise_linear(image: ArrayLike, breakpoints: Sequence[tuple[int, int]]) -> ArrayLike:
        """Piecewise linear intensity transform via breakpoints.

        Parameters
        ----------
        breakpoints : Sequence[tuple[int, int]]
            List of (input, output) pairs defining the transfer function.
            Must be sorted by input value. Implicitly includes (0,0) and (255,255)
            if not provided.

        Example
        -------
        >>> # stretch midtones, crush shadows and highlights
        >>> Enhancement.piecewise_linear(img, [(50, 0), (100, 128), (200, 255)])
        """
        image = to_cpu(_validate_image(image))

        # build full breakpoint list
        pts = list(breakpoints)
        if pts[0][0] != 0:
            pts.insert(0, (0, 0))
        if pts[-1][0] != 255:
            pts.append((255, 255))

        # build LUT
        lut = np.zeros(256, dtype=np.uint8)
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            for x in range(x0, x1 + 1):
                if x1 == x0:
                    lut[x] = y0
                else:
                    lut[x] = int(np.clip(y0 + (y1 - y0) * (x - x0) / (x1 - x0), 0, 255))

        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        if image.ndim == 2:
            return cv2.LUT(image, lut)
        return cv2.LUT(image, lut)

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
    def sobel(image: ArrayLike, dx: int = 1, dy: int = 0, ksize: int = 3, combine: bool = True, method: str = "opencv") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        if method == "opencv":
            if combine and dx == 1 and dy == 0:
                gx = cv2.Sobel(image, cv2.CV_64F, 1, 0, ksize=ksize)
                gy = cv2.Sobel(image, cv2.CV_64F, 0, 1, ksize=ksize)
                return Image_Ops.magnitude(gx, gy).astype(np.uint8)
            return np.clip(np.abs(cv2.Sobel(image, cv2.CV_64F, dx, dy, ksize=ksize)), 0, 255).astype(np.uint8)
        elif method == "kernel":
            if ksize != 3:
                raise ValueError("Kernel method currently only supports ksize=3 for Sobel.")
            if combine and dx == 1 and dy == 0:
                gx = Convolution.apply(image, Convolution.Kernels.sobel_x(), clip=False)
                gy = Convolution.apply(image, Convolution.Kernels.sobel_y(), clip=False)
                return Image_Ops.magnitude(gx, gy)
            kernel = Convolution.Kernels.sobel_x() if dx == 1 else Convolution.Kernels.sobel_y()
            return np.clip(np.abs(Convolution.apply(image, kernel, clip=False)), 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

    @staticmethod
    def prewitt(image: ArrayLike, method: str = "kernel") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        kx, ky = Convolution.Kernels.prewitt_x(), Convolution.Kernels.prewitt_y()
        if method == "opencv":
            gx = cv2.filter2D(image.astype(np.float64), -1, kx)
            gy = cv2.filter2D(image.astype(np.float64), -1, ky)
            return Image_Ops.magnitude(gx, gy)
        elif method == "kernel":
            gx = Convolution.apply(image, kx, clip=False)
            gy = Convolution.apply(image, ky, clip=False)
            return Image_Ops.magnitude(gx, gy)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

    @staticmethod
    def laplacian(image: ArrayLike, ksize: int = 3, method: str = "opencv") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        if method == "opencv":
            return np.clip(np.abs(cv2.Laplacian(image, cv2.CV_64F, ksize=ksize)), 0, 255).astype(np.uint8)
        elif method == "kernel":
            if ksize == 3:
                kernel = Convolution.Kernels.laplacian()
            else:
                kernel = Convolution.Kernels.laplacian_n(ksize)
            return np.clip(np.abs(Convolution.apply(image, kernel, clip=False)), 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

    @staticmethod
    def laplacian_of_gaussian(image: ArrayLike, sigma: float = 1.0, ksize: int = 5, method: str = "opencv") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        if method == "opencv":
            blurred = cv2.GaussianBlur(image, (ksize, ksize), sigma)
            return np.clip(np.abs(cv2.Laplacian(blurred, cv2.CV_64F)), 0, 255).astype(np.uint8)
        elif method == "kernel":
            blurred = cv2.GaussianBlur(image, (ksize, ksize), sigma)
            kernel = Convolution.Kernels.laplacian() if ksize == 3 else Convolution.Kernels.laplacian_n(ksize)
            return np.clip(np.abs(Convolution.apply(blurred, kernel, clip=False)), 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

    @staticmethod
    def roberts(image: ArrayLike, method: str = "kernel") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        kx, ky = Convolution.Kernels.roberts_x(), Convolution.Kernels.roberts_y()
        if method == "opencv":
            gx = cv2.filter2D(image.astype(np.float64), -1, kx)
            gy = cv2.filter2D(image.astype(np.float64), -1, ky)
            return np.clip(np.sqrt(gx**2 + gy**2), 0, 255).astype(np.uint8)
        elif method == "kernel":
            gx = Convolution.apply(image, kx, clip=False, pad_mode="zero")
            gy = Convolution.apply(image, ky, clip=False, pad_mode="zero")
            return np.clip(np.sqrt(gx.astype(np.float64) ** 2 + gy.astype(np.float64) ** 2), 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

    @staticmethod
    def scharr(image: ArrayLike, dx: int = 1, dy: int = 0, combine: bool = True, method: str = "opencv") -> ArrayLike:
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        if method == "opencv":
            if combine and dx == 1 and dy == 0:
                gx = cv2.Scharr(image, cv2.CV_64F, 1, 0)
                gy = cv2.Scharr(image, cv2.CV_64F, 0, 1)
                return np.clip(np.sqrt(gx ** 2 + gy ** 2), 0, 255).astype(np.uint8)
            return np.clip(np.abs(cv2.Scharr(image, cv2.CV_64F, dx, dy)), 0, 255).astype(np.uint8)
        elif method == "kernel":
            if combine and dx == 1 and dy == 0:
                gx = Convolution.apply(image, Convolution.Kernels.scharr_x(), clip=False)
                gy = Convolution.apply(image, Convolution.Kernels.scharr_y(), clip=False)
                return np.clip(np.sqrt(gx.astype(np.float64) ** 2 + gy.astype(np.float64) ** 2), 0, 255).astype(np.uint8)
            
            kernel = Convolution.Kernels.scharr_x() if dx == 1 else Convolution.Kernels.scharr_y()
            return np.clip(np.abs(Convolution.apply(image, kernel, clip=False)), 0, 255).astype(np.uint8)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'opencv' or 'kernel'.")

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

    @staticmethod
    def double_outline(image: ArrayLike, thickness: int = 1, separation: int = 2) -> ArrayLike:
        """
        Extracts a double contour (outline of an outline) from an image.
        
        It finds the initial contours, draws them thickly, and then extracts
        the contours of that drawing to produce a crisp double-line effect.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        
        # 1. Find initial contours
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        # 2. Draw thick contours
        blank = np.zeros_like(binary)
        cv2.drawContours(blank, contours, -1, 255, thickness=thickness + separation)
        
        # 3. Find contours of the thick contours
        contours_double, _ = cv2.findContours(blank, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        # 4. Draw the final double outline
        out = np.zeros_like(binary)
        cv2.drawContours(out, contours_double, -1, 255, thickness=thickness)
        
        return out

    @staticmethod
    def silhouette_outline(
        mask: ArrayLike, 
        base_image: ArrayLike, 
        threshold: float = 10, 
        outline_color: tuple[int, ...] = (255, 255, 255), 
        background_color: tuple[int, ...] = (0, 0, 0), 
        size: int = 5
    ) -> ArrayLike:
        """
        Extracts a silhouette outline from a binary mask using gradient magnitude.
        
        Parameters
        ----------
        mask : ArrayLike
            The binary mask image to extract the outline from.
        base_image : ArrayLike
            The base image to create a similarly sized and typed blank canvas.
        threshold : float
            The gradient magnitude threshold to consider as an edge.
        outline_color : tuple[int, ...]
            The color of the drawn outline.
        background_color : tuple[int, ...]
            The background color of the new image.
        size : int
            The size of the mean filter kernel applied before edge detection.
            
        Returns
        -------
        ArrayLike
            The standalone outline image.
        """
        mask = to_cpu(_validate_image(mask))
        mask_f = mask.astype(np.float64)
        soft_mask = Filter.mean(mask_f, size=size)
        
        gx_o = Convolution.apply(soft_mask, Convolution.Kernels.sobel_x(), clip=False)
        gy_o = Convolution.apply(soft_mask, Convolution.Kernels.sobel_y(), clip=False)
        
        silhouette_outline_mask = (to_cpu(Image_Ops.magnitude(gx_o, gy_o)) > threshold).astype(bool)
        
        outline_standalone = Image_Ops.create_blank_like(base_image, color=background_color)
        outline_standalone[silhouette_outline_mask] = outline_color
        
        return outline_standalone

    @staticmethod
    def canny_gpu(
        image: ArrayLike,
        low: float = 50,
        high: float = 150,
        sigma: float = 1.4,
        ksize: int = 5,
        gradient: Literal["sobel", "scharr"] = "sobel",
    ) -> ArrayLike:
        """Full GPU-accelerated Canny edge detection via CuPy + custom CUDA kernels.

        Runs the entire 5-stage pipeline on GPU VRAM with zero CPU round-trips
        between stages.  Falls back to cv2.Canny when CuPy/CUDA is unavailable.

        Pipeline
        --------
        1. Gaussian blur            — cupyx.scipy.ndimage.correlate
        2. Gradient (Sobel/Scharr)  — cupyx.scipy.ndimage.correlate
        3. Non-Maximum Suppression  — custom CUDA RawKernel
        4. Double thresholding      — vectorized CuPy
        5. Hysteresis edge tracking — iterative CUDA RawKernel

        Parameters
        ----------
        image : ArrayLike
            Input image (grayscale or color, uint8 or float).
        low : float
            Low hysteresis threshold (gradient magnitude units, same scale as
            pixel values — typically 0–255 for uint8 images).
        high : float
            High hysteresis threshold.
        sigma : float
            Gaussian blur sigma.  Higher → more smoothing → fewer noisy edges.
        ksize : int
            Gaussian kernel size (auto-adjusted to odd if even).
        gradient : 'sobel' | 'scharr'
            Gradient operator.  'scharr' gives better rotational accuracy at
            the cost of slightly higher magnitude values.

        Returns
        -------
        ArrayLike
            Binary edge map (0 | 255), dtype uint8.
        """
        image = _validate_image(image)

        # ── CPU fallback ────────────────────────────────────────────────
        if not _GPU_AVAILABLE:
            cpu_img = to_cpu(image)
            if cpu_img.ndim == 3:
                cpu_img = cv2.cvtColor(cpu_img, cv2.COLOR_RGB2GRAY)
            return cv2.Canny(cpu_img, int(low), int(high))

        # ── GPU path ────────────────────────────────────────────────────
        from cupyx.scipy.ndimage import correlate as _gpu_correlate

        # transfer to GPU + float32 grayscale
        img = cp.asarray(to_cpu(image)) if not isinstance(image, cp.ndarray) else image
        if img.ndim == 3:
            img_f = img.astype(cp.float32)
            img = 0.299 * img_f[..., 0] + 0.587 * img_f[..., 1] + 0.114 * img_f[..., 2]
        else:
            img = img.astype(cp.float32)

        h, w = img.shape

        # ── Stage 1: Gaussian blur ──────────────────────────────────────
        if ksize % 2 == 0:
            ksize += 1
        half = ksize // 2
        ax = cp.arange(-half, half + 1, dtype=cp.float32)
        g1d = cp.exp(-(ax ** 2) / (2.0 * sigma ** 2))
        g2d = g1d[:, None] * g1d[None, :]
        g2d /= g2d.sum()

        blurred = _gpu_correlate(img, g2d, mode="reflect")

        # ── Stage 2: gradient computation ───────────────────────────────
        if gradient == "scharr":
            kx = cp.array([[-3, 0, 3], [-10, 0, 10], [-3, 0, 3]], dtype=cp.float32)
            ky = cp.array([[-3, -10, -3], [0, 0, 0], [3, 10, 3]], dtype=cp.float32)
        else:
            kx = cp.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=cp.float32)
            ky = cp.array([[1, 2, 1], [0, 0, 0], [-1, -2, -1]], dtype=cp.float32)

        gx = _gpu_correlate(blurred, kx, mode="reflect")
        gy = _gpu_correlate(blurred, ky, mode="reflect")

        mag = cp.sqrt(gx ** 2 + gy ** 2)
        direction = cp.arctan2(gy, gx) * (180.0 / cp.pi)

        # ── Stage 3: Non-Maximum Suppression (CUDA kernel) ──────────────
        nms_out = cp.zeros_like(mag)

        _nms_code = r'''
        extern "C" __global__
        void nms_kernel(
            const float* __restrict__ mag,
            const float* __restrict__ dir,
            float* __restrict__ out,
            const int H,
            const int W
        ) {
            int x = blockIdx.x * blockDim.x + threadIdx.x;
            int y = blockIdx.y * blockDim.y + threadIdx.y;
            if (x >= W || y >= H) return;

            if (x == 0 || x == W - 1 || y == 0 || y == H - 1) {
                out[y * W + x] = 0.0f;
                return;
            }

            int i = y * W + x;
            float m = mag[i];
            float a = dir[i];
            if (a < 0.0f) a += 180.0f;

            float q, r;

            if (a < 22.5f || a >= 157.5f) {
                q = mag[i + 1];     r = mag[i - 1];
            } else if (a < 67.5f) {
                q = mag[i - W + 1]; r = mag[i + W - 1];
            } else if (a < 112.5f) {
                q = mag[i - W];     r = mag[i + W];
            } else {
                q = mag[i - W - 1]; r = mag[i + W + 1];
            }

            out[i] = (m >= q && m >= r) ? m : 0.0f;
        }
        '''

        _nms_kern = cp.RawKernel(_nms_code, 'nms_kernel')
        block = (16, 16)
        grid = ((w + 15) // 16, (h + 15) // 16)
        _nms_kern(grid, block, (mag, direction, nms_out, np.int32(h), np.int32(w)))

        # ── Stage 4: double thresholding ────────────────────────────────
        edges = cp.zeros((h, w), dtype=cp.uint8)
        edges[nms_out >= high] = 255
        edges[(nms_out >= low) & (nms_out < high)] = 128

        # ── Stage 5: hysteresis edge tracking (connected components) ────
        from cupyx.scipy import ndimage as _gpu_ndimage
        
        possible_edges = edges > 0
        strong_edges = edges == 255
        
        labels, num_features = _gpu_ndimage.label(possible_edges, structure=cp.ones((3,3), dtype=bool))
        
        if int(num_features) > 0:
            has_strong = cp.zeros(int(num_features) + 1, dtype=cp.bool_)
            has_strong[labels[strong_edges]] = True
            edges = has_strong[labels].astype(cp.uint8) * 255
        else:
            edges = cp.zeros((h, w), dtype=cp.uint8)

        return edges

    @staticmethod
    def auto_canny(image: ArrayLike, sigma: float = 0.33, gpu: bool = False, **kwargs) -> ArrayLike:
        """
        Automatically calculates the lower and upper thresholds for Canny based on the median
        pixel intensity of the image, then applies Canny edge detection.

        Parameters
        ----------
        image : ArrayLike
            Input image.
        sigma : float
            Percentage variance from the median (default is 0.33, allowing 33% variance).
        gpu : bool
            If True, uses canny_gpu instead of cv2.Canny.
        kwargs : dict
            Additional arguments passed to the underlying canny function.

        Returns
        -------
        ArrayLike
            Binary edge map.
        """
        image_val = _validate_image(image)
        img_cpu = to_cpu(image_val)
        if img_cpu.ndim == 3:
            img_cpu = cv2.cvtColor(img_cpu, cv2.COLOR_RGB2GRAY)
            
        v = np.median(img_cpu)
        lower = int(max(0, (1.0 - sigma) * v))
        upper = int(min(255, (1.0 + sigma) * v))
        
        if gpu:
            # canny_gpu takes low and high
            if 'low' not in kwargs:
                kwargs['low'] = lower
            if 'high' not in kwargs:
                kwargs['high'] = upper
            return Edge_Detection.canny_gpu(image, **kwargs)
        else:
            # cv2.Canny takes threshold1 and threshold2
            if 'threshold1' not in kwargs:
                kwargs['threshold1'] = lower
            if 'threshold2' not in kwargs:
                kwargs['threshold2'] = upper
            return Edge_Detection.canny(image, **kwargs)



# ═══════════════════════════════════════════════════════════════════════════════
#  Morphology
# ═══════════════════════════════════════════════════════════════════════════════

class Morphology:
    """Static helpers for morphological operations."""

    @staticmethod
    def get_structuring_element(shape: str | ArrayLike = "rect", ksize: int = 3) -> ArrayLike:
        if not isinstance(shape, str):
            # Treat it as a custom kernel of 1s and 0s
            kernel = to_cpu(shape)
            if not isinstance(kernel, np.ndarray):
                kernel = np.array(kernel, dtype=np.uint8)
            return kernel.astype(np.uint8)
            
        shapes = {"rect": cv2.MORPH_RECT, "cross": cv2.MORPH_CROSS, "ellipse": cv2.MORPH_ELLIPSE}
        if shape not in shapes:
            raise ValueError(f"shape must be a string {list(shapes.keys())} or a custom ArrayLike kernel.")
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
    def skeleton(image: ArrayLike, gpu: bool | None = None) -> ArrayLike:
        image = _validate_image(image)
        cpu_img = to_cpu(image)
        if cpu_img.ndim == 3:
            cpu_img = cv2.cvtColor(cpu_img, cv2.COLOR_RGB2GRAY)
        _, binary_cpu = cv2.threshold(cpu_img, 127, 255, cv2.THRESH_BINARY)
        
        use_gpu = _should_gpu(binary_cpu) if gpu is None else gpu
        if use_gpu and _GPU_AVAILABLE:
            from cupyx.scipy import ndimage as _gpu_ndimage
            binary = cp.asarray(binary_cpu)
            skel = cp.zeros_like(binary)
            element = cp.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=cp.uint8)
            while True:
                eroded = _gpu_ndimage.grey_erosion(binary, footprint=element)
                opened = _gpu_ndimage.grey_dilation(eroded, footprint=element)
                # Avoid int16 allocation and clip by using bitwise operations
                temp = cp.bitwise_and(binary, cp.bitwise_not(opened))
                skel = cp.bitwise_or(skel, temp)
                binary = eroded
                if not cp.any(binary):
                    break
            return cp.asnumpy(skel)

        # CPU Fallback
        binary = binary_cpu
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
    def hit_or_miss(image: ArrayLike, kernel: ArrayLike | None = None, gpu: bool | None = None) -> ArrayLike:
        image = _validate_image(image)
        cpu_img = to_cpu(image)
        if cpu_img.ndim == 3:
            cpu_img = cv2.cvtColor(cpu_img, cv2.COLOR_RGB2GRAY)
        _, binary_cpu = cv2.threshold(cpu_img, 127, 255, cv2.THRESH_BINARY)
        
        if kernel is None:
            kernel = np.array([[-1, -1, -1], [-1, 1, -1], [-1, -1, -1]], dtype=np.int32)
            
        use_gpu = _should_gpu(binary_cpu) if gpu is None else gpu
        if use_gpu and _GPU_AVAILABLE:
            from cupyx.scipy import ndimage as _gpu_ndimage
            binary = cp.asarray(binary_cpu)
            k1 = cp.asarray(kernel == 1).astype(cp.uint8)
            k2 = cp.asarray(kernel == -1).astype(cp.uint8)
            e1 = _gpu_ndimage.grey_erosion(binary, footprint=k1) if cp.any(k1) else binary
            e2 = _gpu_ndimage.grey_erosion(cp.bitwise_not(binary), footprint=k2) if cp.any(k2) else cp.bitwise_not(binary)
            return cp.asnumpy(cp.bitwise_and(e1, e2))
            
        return cv2.morphologyEx(binary_cpu, cv2.MORPH_HITMISS, kernel)

    @staticmethod
    def thinning(image: ArrayLike, kernels: list[ArrayLike] | None = None, max_iterations: int = 100, gpu: bool | None = None) -> ArrayLike:
        """Morphological thinning — reduces objects to 1-pixel-wide skeletons.
        If `kernels` are provided, uses a custom sequence of hit-or-miss kernels."""
        image = _validate_image(image)
        cpu_img = to_cpu(image)
        if cpu_img.ndim == 3:
            cpu_img = cv2.cvtColor(cpu_img, cv2.COLOR_RGB2GRAY)
        _, binary_cpu = cv2.threshold(cpu_img, 127, 255, cv2.THRESH_BINARY)

        use_gpu = _should_gpu(binary_cpu) if gpu is None else gpu
        
        # --- Custom kernels provided ---
        if kernels is not None:
            if use_gpu and _GPU_AVAILABLE:
                from cupyx.scipy import ndimage as _gpu_ndimage
                binary = cp.asarray(binary_cpu)
                
                gpu_kernels = []
                for k in kernels:
                    k1 = cp.asarray(k == 1).astype(cp.uint8)
                    k2 = cp.asarray(k == -1).astype(cp.uint8)
                    gpu_kernels.append((k1, k2))
                    
                prev = cp.zeros_like(binary)
                for _ in range(max_iterations):
                    for k1, k2 in gpu_kernels:
                        e1 = _gpu_ndimage.grey_erosion(binary, footprint=k1) if cp.any(k1) else binary
                        e2 = _gpu_ndimage.grey_erosion(cp.bitwise_not(binary), footprint=k2) if cp.any(k2) else cp.bitwise_not(binary)
                        hitmiss = cp.bitwise_and(e1, e2)
                        binary = cp.bitwise_and(binary, cp.bitwise_not(hitmiss))
                    
                    if cp.array_equal(binary, prev):
                        break
                    prev = binary.copy()
                return cp.asnumpy(binary)
                
            # CPU Fallback for custom kernels
            binary = binary_cpu.copy()
            prev = np.zeros_like(binary)
            
            cv_kernels = [np.asarray(k, dtype=np.int32) for k in kernels]
            
            for _ in range(max_iterations):
                for k in cv_kernels:
                    hitmiss = cv2.morphologyEx(binary, cv2.MORPH_HITMISS, k)
                    binary = cv2.subtract(binary, hitmiss)
                if np.array_equal(binary, prev):
                    break
                prev = binary.copy()
            return binary

        # --- No custom kernels provided (Standard Zhang-Suen or Default CPU Kernels) ---
        if use_gpu and _GPU_AVAILABLE:
            thinning_code = r'''
            extern "C" __global__
            void zhang_suen_kernel(
                const unsigned char* __restrict__ img,
                unsigned char* __restrict__ out,
                unsigned char* __restrict__ diff,
                const int H,
                const int W,
                const int step
            ) {
                int x = blockIdx.x * blockDim.x + threadIdx.x;
                int y = blockIdx.y * blockDim.y + threadIdx.y;
                
                if (x >= W || y >= H) return;
                
                int i = y * W + x;
                out[i] = img[i]; // copy original by default
                diff[i] = 0;
                
                // Ignore boundary pixels for simplicity
                if (x == 0 || x == W - 1 || y == 0 || y == H - 1) return;
                if (img[i] == 0) return; // already background
                
                // 8-neighborhood
                int p2 = img[(y - 1) * W + x]     > 0 ? 1 : 0;
                int p3 = img[(y - 1) * W + x + 1] > 0 ? 1 : 0;
                int p4 = img[y * W + x + 1]       > 0 ? 1 : 0;
                int p5 = img[(y + 1) * W + x + 1] > 0 ? 1 : 0;
                int p6 = img[(y + 1) * W + x]     > 0 ? 1 : 0;
                int p7 = img[(y + 1) * W + x - 1] > 0 ? 1 : 0;
                int p8 = img[y * W + x - 1]       > 0 ? 1 : 0;
                int p9 = img[(y - 1) * W + x - 1] > 0 ? 1 : 0;
                
                // A(P1): number of 0->1 transitions
                int A = (p2 == 0 && p3 == 1) + (p3 == 0 && p4 == 1) + 
                        (p4 == 0 && p5 == 1) + (p5 == 0 && p6 == 1) + 
                        (p6 == 0 && p7 == 1) + (p7 == 0 && p8 == 1) + 
                        (p8 == 0 && p9 == 1) + (p9 == 0 && p2 == 1);
                        
                // B(P1): number of non-zero neighbors
                int B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
                
                int m1 = 0;
                int m2 = 0;
                
                if (step == 0) {
                    m1 = p2 * p4 * p6;
                    m2 = p4 * p6 * p8;
                } else {
                    m1 = p2 * p4 * p8;
                    m2 = p2 * p6 * p8;
                }
                
                if (A == 1 && (B >= 2 && B <= 6) && m1 == 0 && m2 == 0) {
                    out[i] = 0; // mark for deletion
                    diff[i] = 1; // something changed
                }
            }
            '''
            thin_kern = cp.RawKernel(thinning_code, 'zhang_suen_kernel')
            
            d_img = cp.asarray(binary_cpu)
            h, w = d_img.shape
            d_out = cp.empty_like(d_img)
            d_diff = cp.empty_like(d_img)
            
            block = (16, 16)
            grid = ((w + 15) // 16, (h + 15) // 16)
            
            for _ in range(max_iterations):
                thin_kern(grid, block, (d_img, d_out, d_diff, np.int32(h), np.int32(w), np.int32(0)))
                has_changes_1 = int(cp.sum(d_diff)) > 0
                
                thin_kern(grid, block, (d_out, d_img, d_diff, np.int32(h), np.int32(w), np.int32(1)))
                has_changes_2 = int(cp.sum(d_diff)) > 0
                
                if not has_changes_1 and not has_changes_2:
                    break
                    
            return cp.asnumpy(d_img)
            
        # CPU Fallback for no custom kernels
        binary = binary_cpu.copy()
        kernels_default = [
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
        for _ in range(max_iterations):
            for k in kernels_default:
                hitmiss = cv2.morphologyEx(binary, cv2.MORPH_HITMISS, k)
                binary = cv2.subtract(binary, hitmiss)
            if np.array_equal(binary, prev):
                break
            prev = binary.copy()
        return binary

    @staticmethod
    def thickening(image: ArrayLike, kernels: list[ArrayLike] | None = None, max_iterations: int = 100, gpu: bool | None = None) -> ArrayLike:
        """Morphological thickening — adds pixels to the boundaries of objects.
        If `kernels` are provided, uses a custom sequence of hit-or-miss kernels."""
        image = _validate_image(image)
        cpu_img = to_cpu(image)
        if cpu_img.ndim == 3:
            cpu_img = cv2.cvtColor(cpu_img, cv2.COLOR_RGB2GRAY)
            
        _, binary = cv2.threshold(cpu_img, 127, 255, cv2.THRESH_BINARY)
        
        # --- Custom kernels provided ---
        if kernels is not None:
            use_gpu = _should_gpu(binary) if gpu is None else gpu
            if use_gpu and _GPU_AVAILABLE:
                from cupyx.scipy import ndimage as _gpu_ndimage
                binary_gpu = cp.asarray(binary)
                
                gpu_kernels = []
                for k in kernels:
                    k1 = cp.asarray(k == 1).astype(cp.uint8)
                    k2 = cp.asarray(k == -1).astype(cp.uint8)
                    gpu_kernels.append((k1, k2))
                    
                prev = cp.zeros_like(binary_gpu)
                for _ in range(max_iterations):
                    for k1, k2 in gpu_kernels:
                        e1 = _gpu_ndimage.grey_erosion(binary_gpu, footprint=k1) if cp.any(k1) else binary_gpu
                        e2 = _gpu_ndimage.grey_erosion(cp.bitwise_not(binary_gpu), footprint=k2) if cp.any(k2) else cp.bitwise_not(binary_gpu)
                        hitmiss = cp.bitwise_and(e1, e2)
                        binary_gpu = cp.bitwise_or(binary_gpu, hitmiss)
                    
                    if cp.array_equal(binary_gpu, prev):
                        break
                    prev = binary_gpu.copy()
                return cp.asnumpy(binary_gpu)
                
            # CPU Fallback for custom kernels
            binary_cpu = binary.copy()
            prev = np.zeros_like(binary_cpu)
            cv_kernels = [np.asarray(k, dtype=np.int32) for k in kernels]
            
            for _ in range(max_iterations):
                for k in cv_kernels:
                    hitmiss = cv2.morphologyEx(binary_cpu, cv2.MORPH_HITMISS, k)
                    binary_cpu = cv2.bitwise_or(binary_cpu, hitmiss)
                if np.array_equal(binary_cpu, prev):
                    break
                prev = binary_cpu.copy()
            return binary_cpu
            
        # --- No custom kernels provided ---
        inverted = cv2.bitwise_not(binary)
        
        # apply thinning on the inverted image (relies on standard thinning)
        thinned_inverted = Morphology.thinning(inverted, kernels=None, max_iterations=max_iterations, gpu=gpu)
        
        return cv2.bitwise_not(thinned_inverted)

    @staticmethod
    def reconstruct(marker: ArrayLike, mask: ArrayLike, method: Literal["dilation", "erosion"] = "dilation", ksize: int = 3, element_shape: str = "rect") -> ArrayLike:
        """Morphological reconstruction (Geodesic).

        Reconstructs the `marker` image under the `mask` image.
        If method is "dilation" (default), marker is iteratively dilated and masked via element-wise minimum.
        If method is "erosion", marker is iteratively eroded and masked via element-wise maximum.

        Both marker and mask must be of the same shape and datatype.
        """
        marker = to_cpu(_validate_image(marker))
        mask = to_cpu(_validate_image(mask))
        
        if marker.shape != mask.shape:
            raise ValueError("Marker and mask must have the same shape.")
            
        element = Morphology.get_structuring_element(element_shape, ksize)
        current = marker.copy()
        
        while True:
            if method == "dilation":
                dilated = cv2.dilate(current, element)
                nxt = np.minimum(dilated, mask)
            elif method == "erosion":
                eroded = cv2.erode(current, element)
                nxt = np.maximum(eroded, mask)
            else:
                raise ValueError("Method must be 'dilation' or 'erosion'.")
                
            if np.array_equal(nxt, current):
                break
            current = nxt
            
        return current


# ═══════════════════════════════════════════════════════════════════════════════
#  Wavelet (manual Haar — no external dependencies)
# ═══════════════════════════════════════════════════════════════════════════════

class Wavelet:
    """2D wavelet transforms using a manual Haar filter-bank. Pure numpy."""

    @staticmethod
    def show_level(cA: ArrayLike, cH: ArrayLike, cV: ArrayLike, cD: ArrayLike, title: str = "1-Level Decomposition") -> None:
        """Visualize a single-level wavelet decomposition as a 2x2 grid."""
        def _map_to_gray(img):
            max_val = np.max(np.abs(img))
            if max_val == 0:
                return np.full_like(img, 128.0)
            return (img / max_val) * 127.0 + 128.0

        fig, axes = plt.subplots(2, 2, figsize=(10, 10))
        axes[0, 0].imshow(cA, cmap='gray')
        axes[0, 0].set_title("LL (Approximation)")
        axes[0, 1].imshow(_map_to_gray(cH), cmap='gray')
        axes[0, 1].set_title("LH (Horizontal Detail)")
        axes[1, 0].imshow(_map_to_gray(cV), cmap='gray')
        axes[1, 0].set_title("HL (Vertical Detail)")
        axes[1, 1].imshow(_map_to_gray(cD), cmap='gray')
        axes[1, 1].set_title("HH (Diagonal detail)")
        plt.tight_layout()
        plt.show()

    @staticmethod
    def show_dynamic(coeffs: list, title: str = "Dynamic Decomposition", figsize: tuple[int, int] = (10, 10)) -> None:
        """Visualize a multi-level wavelet decomposition as a single stitched image."""
        def _map_to_gray(img):
            max_val = np.max(np.abs(img))
            if max_val == 0:
                return np.full_like(img, 128.0)
            return (img / max_val) * 127.0 + 128.0

        def _map_approx(img):
            mn, mx = img.min(), img.max()
            if mx == mn:
                return np.zeros_like(img)
            return (img - mn) / (mx - mn) * 255.0

        stitched = _map_approx(coeffs[0])
        for detail in coeffs[1:]:
            cH, cV, cD = detail
            cH_n = _map_to_gray(cH)
            cV_n = _map_to_gray(cV)
            cD_n = _map_to_gray(cD)
            
            h, w = stitched.shape
            h_det, w_det = cH_n.shape
            
            if stitched.shape != (h_det, w_det):
                stitched_resized = np.zeros((h_det, w_det), dtype=np.float64)
                mh, mw = min(h, h_det), min(w, w_det)
                stitched_resized[:mh, :mw] = stitched[:mh, :mw]
                stitched = stitched_resized

            top = np.concatenate((stitched, cH_n), axis=1)
            bottom = np.concatenate((cV_n, cD_n), axis=1)
            stitched = np.concatenate((top, bottom), axis=0)

        plt.figure(figsize=figsize)
        plt.imshow(stitched, cmap='gray')
        plt.title(title)
        plt.axis("off")
        plt.show()

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
    def idwt2(cA: ArrayLike, cH: ArrayLike, cV: ArrayLike, cD: ArrayLike, match_mode: MatchMode | Literal["strict"] = "strict") -> ArrayLike:
        """Inverse single-level 2D Haar DWT.
        If match_mode is provided, detail subbands will be auto-adjusted to match cA's shape."""
        
        if match_mode != "strict":
            target_h, target_w = cA.shape
            def _match_shape(arr: ArrayLike) -> ArrayLike:
                if arr.shape == (target_h, target_w):
                    return arr
                if match_mode == "resize":
                    return _resize_to(arr, target_h, target_w)
                elif match_mode in ("crop", "pad+resize"):
                    return _center_crop_or_pad(arr, target_h, target_w)
                elif match_mode == "tl-crop":
                    return _tl_crop(arr, target_h, target_w)
                elif match_mode == "pad":
                    return _pad_to(arr, target_h, target_w)
                elif match_mode == "cover":
                    return _fit_cover(arr, target_h, target_w)
                elif match_mode == "contain":
                    return _fit_contain(arr, target_h, target_w)
                return arr
                
            cH = _match_shape(cH)
            cV = _match_shape(cV)
            cD = _match_shape(cD)
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
    def max_wavelet_level(image_shape: tuple[int, ...], min_size: int = 16) -> int:
        """Calculates the maximum wavelet decomposition level before the subband size drops below min_size."""
        h, w = image_shape[:2]
        smallest_dim = min(h, w)
        level = 0
        while smallest_dim > min_size:
            smallest_dim //= 2
            level += 1
        return max(1, level)

    @staticmethod
    def wavedec2_dynamic(image: ArrayLike, min_size: int = 16) -> list:
        """Dynamically decomposes the image using DWT until the subband size is <= min_size."""
        image_val = _validate_image(image)
        level = Wavelet.max_wavelet_level(image_val.shape, min_size=min_size)
        return Wavelet.wavedec2(image_val, level=level)

    @staticmethod
    def assemble_wavedec2_grid(coeffs: list) -> ArrayLike:
        """Assembles a multi-level DWT decomposition into a single classic 2D grid image for visualization."""
        grid = coeffs[0].copy()
        
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            
            # Ensure dimensions match before stacking (due to odd shape padding in DWT)
            h, w = grid.shape
            th, tw = cH.shape
            if h != th or w != tw:
                grid = cv2.resize(grid, (tw, th), interpolation=cv2.INTER_NEAREST)
                
            top = np.hstack([grid, cH])
            bottom = np.hstack([cV, cD])
            grid = np.vstack([top, bottom])
            
        return grid

    @staticmethod
    def high_frequency_energy(coeffs: list) -> float:
        """Calculates the total high-frequency energy across all levels using: sum(LH^2 + HL^2 + HH^2)."""
        energy = 0.0
        for i in range(1, len(coeffs)):
            cH, cV, cD = coeffs[i]
            energy += np.sum(np.square(cH)) + np.sum(np.square(cV)) + np.sum(np.square(cD))
        return float(energy)

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
    def process_rgb_wavelet(rgb_img: ArrayLike, title: str, cmap: str | None = None) -> ArrayLike:
        """Decompose & reconstruct a 3D RGB image channel-by-channel with optional colormap visualization."""
        import matplotlib.pyplot as plt
        
        rgb_img_cpu = to_cpu(rgb_img)
        cAs, cHs, cVs, cDs = [], [], [], []
        for i in range(3):
            cA, cH, cV, cD = Wavelet.dwt2(rgb_img_cpu[..., i])
            cAs.append(cA)
            cHs.append(cH)
            cVs.append(cV)
            cDs.append(cD)
        
        def norm_approx(img): return np.clip(img / np.sqrt(2), 0, 255).astype(np.uint8)
        def norm_detail(img): 
            mx = np.max(np.abs(img))
            if mx == 0: return np.full_like(img, 128, dtype=np.uint8)
            return np.clip((img / mx) * 127 + 128, 0, 255).astype(np.uint8)
            
        fig, axes = plt.subplots(2, 2, figsize=(6, 4))
        
        if cmap is not None:
            # For 2D colormap visualization, find the most active channel for details
            energies = [np.sum(np.abs(cHs[i])) for i in range(3)]
            active_ch = np.argmax(energies)
            
            # Use full RGB for LL, but use the active channel's detail for colormap display
            cA_rgb = np.stack(cAs, axis=-1)
            disp_cA = norm_approx(cA_rgb)
            
            disp_cH = norm_detail(cHs[active_ch])
            disp_cV = norm_detail(cVs[active_ch])
            disp_cD = norm_detail(cDs[active_ch])
            
            # Note: cmap is ignored by imshow if the input is RGB
            axes[0,0].imshow(disp_cA)
            axes[0,1].imshow(disp_cH, cmap=cmap)
            axes[1,0].imshow(disp_cV, cmap=cmap)
            axes[1,1].imshow(disp_cD, cmap=cmap)
        else:
            # Default RGB visualization
            cA_rgb = np.stack(cAs, axis=-1)
            cH_rgb = np.stack(cHs, axis=-1)
            cV_rgb = np.stack(cVs, axis=-1)
            cD_rgb = np.stack(cDs, axis=-1)
            
            axes[0,0].imshow(norm_approx(cA_rgb))
            axes[0,1].imshow(norm_detail(cH_rgb))
            axes[1,0].imshow(norm_detail(cV_rgb))
            axes[1,1].imshow(norm_detail(cD_rgb))
            
        axes[0,0].set_title("LL (Approximation)", fontsize=8)
        axes[0,1].set_title("LH (Horizontal Detail)", fontsize=8)
        axes[1,0].set_title("HL (Vertical Detail)", fontsize=8)
        axes[1,1].set_title("HH (Diagonal Detail)", fontsize=8)
        
        for ax in axes.flat: ax.axis('off')
        fig.suptitle(f"{title} Channel Decomposition", fontsize=12)
        plt.tight_layout()
        plt.show()
        
        recs = []
        for i in range(3):
            rec = Wavelet.idwt2(cAs[i], cHs[i], cVs[i], cDs[i])
            recs.append(rec)
            
        rec_rgb = np.clip(np.stack(recs, axis=-1), 0, 255).astype(np.uint8)
        return rec_rgb

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
    def extract_human(
        image: ArrayLike,
        clothing_lower: tuple[int, ...] | int | None = 10,
        clothing_upper: tuple[int, ...] | int | None = 90,
        clothing_color_space: int | None = None,
        detect_skin: bool = True,
        spatial_constraint: int = 81,
        cleanup_size: int = 7
    ) -> ArrayLike:
        """
        Generic human figure extraction combining skin detection and clothing color targeting.
        
        Parameters
        ----------
        image : ArrayLike
            The RGB image to process.
        clothing_lower : tuple or int or None
            The lower bound for clothing color. If int, treated as grayscale intensity.
        clothing_upper : tuple or int or None
            The upper bound for clothing color. If int, treated as grayscale intensity.
        clothing_color_space : int or None
            OpenCV conversion code (e.g. cv2.COLOR_RGB2HSV). If None, grayscale is used.
        detect_skin : bool
            If True, automatically fuses a robust YCrCb skin mask into the final extraction.
        spatial_constraint : int
            Heavy low-pass filter kernel size to spatially constrain the clothing mask (removes background noise).
        cleanup_size : int
            Median filter kernel size for cleaning the binary masks.
            
        Returns
        -------
        ArrayLike
            A unified binary mask of the detected subject.
        """
        image = to_cpu(_validate_image(image))
        h, w = image.shape[:2]
        final_mask = np.zeros((h, w), dtype=np.uint8)
        
        # 1. Skin Detection Path (Robust YCrCb method)
        if detect_skin and image.ndim == 3:
            ycrcb = cv2.cvtColor(image, cv2.COLOR_RGB2YCrCb)
            # Standard human skin bounds in YCrCb
            lower_skin = np.array([0, 133, 77], dtype=np.uint8)
            upper_skin = np.array([255, 173, 127], dtype=np.uint8)
            skin_mask = cv2.inRange(ycrcb, lower_skin, upper_skin)
            if cleanup_size > 0:
                skin_mask = to_cpu(Filter.median(skin_mask, size=cleanup_size))
            final_mask = np.maximum(final_mask, skin_mask)
            
        # 2. Clothing / Color Path
        if clothing_lower is not None and clothing_upper is not None:
            # Convert to target color space
            if clothing_color_space is not None and image.ndim == 3:
                target_img = cv2.cvtColor(image, clothing_color_space)
            else:
                target_img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
                
            # Direct thresholding
            if isinstance(clothing_lower, (int, float)):
                clothing_lower = np.array([clothing_lower], dtype=np.float64)
                clothing_upper = np.array([clothing_upper], dtype=np.float64)
            else:
                clothing_lower = np.array(clothing_lower, dtype=np.float64)
                clothing_upper = np.array(clothing_upper, dtype=np.float64)
                
            clothes_mask = cv2.inRange(target_img, clothing_lower, clothing_upper)
            
            # Spatial Constraint (Background suppression)
            if spatial_constraint > 0:
                blurred = to_cpu(Filter.low_pass(target_img, size=spatial_constraint, method='gaussian'))
                blur_mask = cv2.inRange(blurred, clothing_lower, clothing_upper)
                clothes_mask = np.minimum(clothes_mask, blur_mask)
                
            if cleanup_size > 0:
                clothes_mask = to_cpu(Filter.median(clothes_mask, size=cleanup_size + 2))
                
            final_mask = np.maximum(final_mask, clothes_mask)
            
        return final_mask

    @staticmethod
    def extract_by_shape(
        mask_or_image: ArrayLike,
        target_vertices: int = 4,
        min_aspect_ratio: float = 2.0,
        max_aspect_ratio: float = 5.0,
        min_area: int = 500
    ) -> list[tuple[ArrayLike, tuple[int, int, int, int]]]:
        """
        Extracts regions matching specific geometric properties (e.g. rectangular license plates).
        
        Parameters
        ----------
        mask_or_image : ArrayLike
            Input image or binary mask.
        target_vertices : int
            Number of vertices to look for (4 = rectangle, 3 = triangle).
        min_aspect_ratio : float
            Minimum bounding box aspect ratio (width/height).
        max_aspect_ratio : float
            Maximum bounding box aspect ratio.
        min_area : int
            Minimum contour area to consider (filters out noise).
            
        Returns
        -------
        list[tuple[ArrayLike, tuple[int, int, int, int]]]
            A list of (cropped_image, bounding_box) tuples.
        """
        img = to_cpu(_validate_image(mask_or_image))
        if img.ndim == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        else:
            thresh = img if img.dtype == np.uint8 else (img * 255).astype(np.uint8)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results = []
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
                
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            
            if len(approx) == target_vertices:
                x, y, w, h = cv2.boundingRect(approx)
                aspect_ratio = float(w) / h
                
                if min_aspect_ratio <= aspect_ratio <= max_aspect_ratio:
                    cropped = img[y:y+h, x:x+w]
                    results.append((cropped, (x, y, w, h)))
                    
        return results

    @staticmethod
    def extract_by_texture(
        image: ArrayLike,
        kernel_size: tuple[int, int] = (21, 5),
        edge_threshold: int = 50
    ) -> ArrayLike:
        """
        Extracts regions with high spatial frequency (dense edges), such as text blocks or plates.
        
        Parameters
        ----------
        image : ArrayLike
            Input image.
        kernel_size : tuple[int, int]
            Morphological closing kernel size. Wide kernels (e.g. 21x5) fuse horizontal text lines.
        edge_threshold : int
            Minimum gradient magnitude to consider as a strong edge.
            
        Returns
        -------
        ArrayLike
            A binary mask highlighting dense texture blobs.
        """
        image = to_cpu(_validate_image(image))
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        # 1. Edge Density (Scharr gives strong response to text edges)
        gx = cv2.Scharr(gray, cv2.CV_64F, 1, 0)
        gy = cv2.Scharr(gray, cv2.CV_64F, 0, 1)
        magnitude = np.clip(np.sqrt(gx**2 + gy**2), 0, 255).astype(np.uint8)
        
        _, edge_mask = cv2.threshold(magnitude, edge_threshold, 255, cv2.THRESH_BINARY)
        
        # 2. Morphological Closing to fuse dense edges into a solid blob
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
        fused = cv2.morphologyEx(edge_mask, cv2.MORPH_CLOSE, kernel)
        
        return fused

    @staticmethod
    def extract_by_template(
        image: ArrayLike,
        template: ArrayLike,
        match_threshold: float = 0.8
    ) -> list[tuple[int, int, int, int]]:
        """
        Locates exact objects (logos, signs, stationary vehicles) using Normalized Cross-Correlation.
        
        Parameters
        ----------
        image : ArrayLike
            The scene image.
        template : ArrayLike
            The template image to search for.
        match_threshold : float
            Similarity threshold (0.0 to 1.0).
            
        Returns
        -------
        list[tuple[int, int, int, int]]
            List of bounding boxes (x, y, w, h) where the template was found.
        """
        image = to_cpu(_validate_image(image))
        template = to_cpu(_validate_image(template))
        
        if image.ndim == 3:
            img_gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = image
            
        if template.ndim == 3:
            temp_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
        else:
            temp_gray = template
            
        h, w = temp_gray.shape[:2]
        res = cv2.matchTemplate(img_gray, temp_gray, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= match_threshold)
        
        results = []
        for pt in zip(*loc[::-1]): # Switch (row, col) to (x, y)
            results.append((pt[0], pt[1], w, h))
            
        # Basic Non-Maximum Suppression
        final_boxes = []
        for box in results:
            x, y, bw, bh = box
            overlap = False
            for fx, fy, fw, fh in final_boxes:
                if abs(x - fx) < bw/2 and abs(y - fy) < bh/2:
                    overlap = True
                    break
            if not overlap:
                final_boxes.append(box)
                
        return final_boxes

    @staticmethod
    def extract_by_motion(
        current_frame: ArrayLike,
        background_frame: ArrayLike,
        threshold: int = 25,
        blur_size: int = 21
    ) -> ArrayLike:
        """
        Extracts moving objects by subtracting a background frame (or T-1 frame).
        
        Parameters
        ----------
        current_frame : ArrayLike
            The current video frame.
        background_frame : ArrayLike
            The reference background model or previous frame.
        threshold : int
            Pixel difference threshold to trigger motion.
        blur_size : int
            Gaussian blur size to remove camera sensor noise before differencing.
            
        Returns
        -------
        ArrayLike
            A binary mask of moving objects.
        """
        curr = to_cpu(_validate_image(current_frame))
        bg = to_cpu(_validate_image(background_frame))
        
        if curr.ndim == 3:
            curr = cv2.cvtColor(curr, cv2.COLOR_RGB2GRAY)
        if bg.ndim == 3:
            bg = cv2.cvtColor(bg, cv2.COLOR_RGB2GRAY)
            
        # Blur to remove minor noise
        if blur_size > 0:
            if blur_size % 2 == 0:
                blur_size += 1 # Must be odd
            curr = cv2.GaussianBlur(curr, (blur_size, blur_size), 0)
            bg = cv2.GaussianBlur(bg, (blur_size, blur_size), 0)
            
        # Frame difference
        diff = cv2.absdiff(bg, curr)
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        
        # Dilate to fill holes in the moving object
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        return cv2.dilate(thresh, kernel, iterations=2)

    @staticmethod
    def apply_overlay(
        image: ArrayLike,
        mask: ArrayLike,
        outline_mask: ArrayLike | None = None,
        tint_color: tuple[int, ...] = (255, 255, 0),
        outline_color: tuple[int, ...] | None = None,
        alpha: float = 0.3
    ) -> ArrayLike:
        """
        Applies a semi-transparent colored highlight and an optional solid outline over a region.
        
        Parameters
        ----------
        image : ArrayLike
            The original color image (background).
        mask : ArrayLike
            The binary mask indicating the region to tint.
        outline_mask : ArrayLike, optional
            A boolean or binary mask of the region's outline. If None, no outline is drawn.
        tint_color : tuple[int, ...]
            The highlight tint color (e.g., yellow = (255, 255, 0)).
        outline_color : tuple[int, ...], optional
            The color of the outline. If None, defaults to tint_color.
        alpha : float
            The blending alpha (opacity) for the colored tint overlay.
            
        Returns
        -------
        ArrayLike
            The composite highlighted image.
        """
        image = to_cpu(_validate_image(image)).copy()
        mask = to_cpu(_validate_image(mask))
        
        if outline_color is None:
            outline_color = tint_color
            
        # Create the colored tint layer
        highlight_layer = Image_Ops.create_blank_like(image, color=tint_color)
        highlight_blend = to_cpu(Image_Ops.blend(image, highlight_layer, alpha=alpha))
        
        # Apply the highlight where the mask is active
        mask_bool = mask > 128
        image[mask_bool] = highlight_blend[mask_bool]
        
        # Apply outline if provided
        if outline_mask is not None:
            outline_mask = to_cpu(_validate_image(outline_mask))
            if outline_mask.dtype != bool:
                outline_mask = outline_mask > 128
            image[outline_mask] = outline_color
            
        return image

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

        ppc = pixels_per_cell
        n_cells_y = h // ppc
        n_cells_x = w // ppc
        bin_width = 180.0 / orientations

        # vectorized cell histogram: reshape into (n_cells_y, ppc, n_cells_x, ppc)
        # then transpose to (n_cells_y, n_cells_x, ppc, ppc) and flatten pixels per cell
        h_crop = n_cells_y * ppc
        w_crop = n_cells_x * ppc
        mag_cells = magnitude[:h_crop, :w_crop].reshape(n_cells_y, ppc, n_cells_x, ppc).transpose(0, 2, 1, 3).reshape(n_cells_y, n_cells_x, -1)
        ori_cells = orientation[:h_crop, :w_crop].reshape(n_cells_y, ppc, n_cells_x, ppc).transpose(0, 2, 1, 3).reshape(n_cells_y, n_cells_x, -1)

        # bin orientations and scatter-accumulate magnitudes via one-hot broadcasting
        bin_idx = np.clip((ori_cells / bin_width).astype(np.int32), 0, orientations - 1)
        one_hot = (bin_idx[..., np.newaxis] == np.arange(orientations)).astype(np.float64)
        cell_hists = np.sum(mag_cells[..., np.newaxis] * one_hot, axis=2)

        # vectorized block normalization
        cpb = cells_per_block
        blocks_y = n_cells_y - cpb + 1
        blocks_x = n_cells_x - cpb + 1
        if blocks_y < 1 or blocks_x < 1:
            return cell_hists.ravel()

        block_size = cpb * cpb * orientations
        blocks = np.zeros((blocks_y, blocks_x, block_size), dtype=np.float64)
        by_idx = np.arange(blocks_y)[:, None]
        bx_idx = np.arange(blocks_x)[None, :]
        for dy in range(cpb):
            for dx in range(cpb):
                offset = (dy * cpb + dx) * orientations
                blocks[:, :, offset:offset + orientations] = cell_hists[by_idx + dy, bx_idx + dx, :]

        norms = np.sqrt(np.sum(blocks ** 2, axis=-1, keepdims=True) + 1e-6)
        normalized = blocks / norms
        return normalized.reshape(-1)

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
        
        y_start, y_end = max(0, -dy), min(h, h - dy)
        x_start, x_end = max(0, -dx), min(w, w - dx)
        
        if y_start < y_end and x_start < x_end:
            i_vals = img[y_start:y_end, x_start:x_end].ravel()
            j_vals = img[y_start + dy:y_end + dy, x_start + dx:x_end + dx].ravel()
            
            mask = (i_vals < levels) & (j_vals < levels)
            if not mask.all():
                i_vals = i_vals[mask]
                j_vals = j_vals[mask]
                
            glcm = np.bincount(i_vals * levels + j_vals, minlength=levels * levels).reshape(levels, levels).astype(np.int64)
        else:
            glcm = np.zeros((levels, levels), dtype=np.int64)

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
                 levels: int = 256, symmetric: bool = True,
                 extract_asm: bool = True) -> dict:
        """Compute GLCM texture features for multiple distances and angles.

        For each (distance, angle) pair, computes:
        contrast, dissimilarity, homogeneity, energy, entropy, correlation.
        If extract_asm is True (default), separately provides "asm" (sum of squared probabilities)
        and defines "energy" as the square root of ASM. Otherwise "energy" is raw ASM.

        Returns dict mapping feature names to arrays of shape (n_distances, n_angles).
        """
        nd, na = len(distances), len(angles)
        feat_names = ["contrast", "dissimilarity", "homogeneity",
                       "energy", "entropy", "correlation"]
        if extract_asm:
            feat_names.append("asm")
            
        result = {name: np.zeros((nd, na), dtype=np.float64) for name in feat_names}
        for di, d in enumerate(distances):
            for ai, a in enumerate(angles):
                g = GLCM.compute(image, distance=d, angle=a,
                                 levels=levels, symmetric=symmetric)
                p = GLCM.normalize(g)
                feats = GLCM._compute_features(p, extract_asm=extract_asm)
                for name in feat_names:
                    result[name][di, ai] = feats[name]
        return result

    @staticmethod
    def _compute_features(p: ArrayLike, extract_asm: bool = True) -> dict:
        """Compute texture features from a normalized GLCM matrix *p*."""
        levels = p.shape[0]
        i_idx, j_idx = np.meshgrid(np.arange(levels), np.arange(levels), indexing="ij")
        i_f = i_idx.astype(np.float64)
        j_f = j_idx.astype(np.float64)
        diff = np.abs(i_f - j_f)
        contrast = np.sum(p * diff ** 2)
        dissimilarity = np.sum(p * diff)
        homogeneity = np.sum(p / (1.0 + diff ** 2))
        
        raw_asm = np.sum(p ** 2)
        
        log_p = np.log2(p + 1e-12)
        entropy = -np.sum(p * log_p)
        mu_i = np.sum(i_f * p)
        mu_j = np.sum(j_f * p)
        sigma_i = np.sqrt(np.sum(((i_f - mu_i) ** 2) * p) + 1e-8)
        sigma_j = np.sqrt(np.sum(((j_f - mu_j) ** 2) * p) + 1e-8)
        correlation = np.sum(((i_f - mu_i) * (j_f - mu_j) * p)) / (sigma_i * sigma_j)
        
        out = {"contrast": contrast, "dissimilarity": dissimilarity,
               "homogeneity": homogeneity, "entropy": entropy, 
               "correlation": correlation}
               
        if extract_asm:
            out["asm"] = raw_asm
            out["energy"] = np.sqrt(raw_asm)
        else:
            out["energy"] = raw_asm
            
        return out

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

    @staticmethod
    def display_matrix(image: ArrayLike, distance: int = 1, angle: float = 0.0,
                       levels: int = 8, symmetric: bool = True):
        """Compute and display the GLCM numerically as a styled Pandas DataFrame matrix.
        
        Note: It is highly recommended to use a smaller `levels` (e.g., 8 or 16) 
        when displaying the numerical matrix to avoid massive 256x256 console output.
        """
        import pandas as pd
        g = GLCM.compute(image, distance=distance, angle=angle,
                         levels=levels, symmetric=symmetric)
        df = pd.DataFrame(g)
        df.index.name = "i (Row)"
        df.columns.name = "j (Col)"
        
        try:
            from IPython.display import display
            # We apply a background gradient for better visualization in notebooks
            display(df.style.background_gradient(cmap='hot'))
        except ImportError:
            print(df)
            
        return df

    @staticmethod
    def batch_extract(image_folder: str, output_csv: str | None = None, 
                      distances: Sequence[int] = (1,), angles: Sequence[float] = (0, 45, 90, 135),
                      levels: int = 256, symmetric: bool = True, extract_asm: bool = True):
        """Batch extract GLCM features from a directory of images.
        
        Iterates over all valid images in `image_folder`, computes the specified GLCM features 
        for each image efficiently, and formats the output into a flattened Pandas DataFrame.
        If `output_csv` is provided, saves the DataFrame to the given path.
        """
        import os
        import pandas as pd
        
        all_rows = []
        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
        try:
            image_files = [f for f in os.listdir(image_folder) if f.lower().endswith(valid_exts)]
        except FileNotFoundError:
            print(f"Directory not found: {image_folder}")
            return pd.DataFrame()
        
        if not image_files:
            print(f"No valid images found in {image_folder}.")
            return pd.DataFrame()
            
        print(f"Batch extracting GLCM features for {len(image_files)} images...")
        
        feature_map = [("contrast", "Contrast"), ("homogeneity", "Homogeneity"), 
                       ("correlation", "Correlation"), ("dissimilarity", "Dissimilarity"), 
                       ("entropy", "Entropy")]
                       
        if extract_asm:
            feature_map.extend([("asm", "ASM"), ("energy", "Energy")])
        else:
            feature_map.append(("energy", "Energy"))
            
        for filename in image_files:
            filepath = os.path.join(image_folder, filename)
            img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
                
            features_dict = GLCM.features(img, distances=distances, angles=angles, 
                                          levels=levels, symmetric=symmetric, 
                                          extract_asm=extract_asm)
                                          
            row_data = {"Filename": filename}
            
            for feat, out_feat in feature_map:
                for d_idx, d in enumerate(distances):
                    for a_idx, angle in enumerate(angles):
                        # Format column names based on whether there are multiple distances
                        col_name = f"{out_feat}_d{d}_a{angle}" if len(distances) > 1 else f"{out_feat}{angle}"
                        row_data[col_name] = features_dict[feat][d_idx][a_idx]
                        
            all_rows.append(row_data)
            
        df = pd.DataFrame(all_rows)
        
        if output_csv:
            df.to_csv(output_csv, index=False)
            print(f"Successfully saved batch extraction to {output_csv}")
            
        return df

    @staticmethod
    def extract_batch(images, distances=(1,), angles=(0, 45, 90, 135), levels=256, symmetric=True):
        """Batch extract features from a list of images and return a dictionary of feature arrays."""
        import numpy as np
        n_imgs = len(images)
        feat_names = ["contrast", "dissimilarity", "homogeneity", "energy", "entropy", "correlation", "asm"]
        mapping = {
            "contrast": "Contrast",
            "homogeneity": "Homogeneity",
            "correlation": "Correlation",
            "dissimilarity": "Dissimilarity",
            "entropy": "Entropy",
            "asm": "ASM",
            "energy": "Energy"
        }
        
        results = {}
        for feat in feat_names:
            for angle in angles:
                results[f"{mapping[feat]}{angle}"] = np.zeros(n_imgs, dtype=np.float64)
                
        for i in range(n_imgs):
            img = images[i]
            feats = GLCM.features(img, distances=distances, angles=angles, levels=levels, symmetric=symmetric)
            for feat in feat_names:
                for a_idx, angle in enumerate(angles):
                    results[f"{mapping[feat]}{angle}"][i] = feats[feat][0, a_idx]
                    
        return results




# ═══════════════════════════════════════════════════════════════════════════════
#  Segmentation
# ═══════════════════════════════════════════════════════════════════════════════

class Segmentation:
    """Static helpers for image segmentation."""

    @staticmethod
    def watershed_segmentation(image: ArrayLike, markers: ArrayLike | None = None) -> tuple[ArrayLike, ArrayLike]:
        """
        Separates overlapping objects using the Watershed algorithm.
        
        Returns:
            (segmented_image, markers)
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            
        if markers is None:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            kernel = np.ones((3,3), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
            
            sure_bg = cv2.dilate(opening, kernel, iterations=3)
            
            dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
            _, sure_fg = cv2.threshold(dist_transform, 0.7*dist_transform.max(), 255, 0)
            
            sure_fg = np.uint8(sure_fg)
            unknown = cv2.subtract(sure_bg, sure_fg)
            
            _, markers = cv2.connectedComponents(sure_fg)
            markers = markers + 1
            markers[unknown == 255] = 0
            
        markers = cv2.watershed(image, markers)
        result = image.copy()
        result[markers == -1] = [255, 0, 0]
        return result, markers

    @staticmethod
    def grab_cut(image: ArrayLike, rect: tuple[int, int, int, int], iterCount: int = 5) -> ArrayLike:
        """
        Interactive foreground extraction using GrabCut algorithm.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            
        mask = np.zeros(image.shape[:2], np.uint8)
        bgdModel = np.zeros((1,65), np.float64)
        fgdModel = np.zeros((1,65), np.float64)
        
        cv2.grabCut(image, mask, rect, bgdModel, fgdModel, iterCount, cv2.GC_INIT_WITH_RECT)
        
        mask2 = np.where((mask==2)|(mask==0), 0, 1).astype('uint8')
        image = image * mask2[:,:,np.newaxis]
        return image

    @staticmethod
    def slic_superpixels(image: ArrayLike, num_segments: int = 100, compactness: float = 10.0) -> ArrayLike:
        """
        Groups pixels into larger 'superpixels' based on color and proximity using SLIC.
        Requires opencv-contrib-python.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            
        try:
            # Calculate region size based on requested segments
            region_size = int(np.sqrt((image.shape[0]*image.shape[1])/num_segments))
            slic = cv2.ximgproc.createSuperpixelSLIC(image, cv2.ximgproc.SLIC, 
                                                    region_size=region_size, 
                                                    ruler=compactness)
            slic.iterate(10)
            slic.enforceLabelConnectivity(min_element_size=10)
            
            mask = slic.getLabelContourMask()
            result = image.copy()
            result[mask == 255] = [255, 255, 0] # Highlight borders in yellow
            return result
        except AttributeError:
            raise NotImplementedError("cv2.ximgproc is required for SLIC superpixels. Install opencv-contrib-python.")

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

    @staticmethod
    def multi_otsu(image: ArrayLike, classes: int = 3) -> tuple[ArrayLike, list[int]]:
        """Multi-level Otsu thresholding for K-class segmentation.

        Parameters
        ----------
        classes : int
            Number of classes (2, 3, or 4 are typical).

        Returns
        -------
        (segmented_image, thresholds)
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        hist, _ = np.histogram(image.ravel(), bins=256, range=(0, 256))
        total = image.size
        prob = hist.astype(np.float64) / total

        # exhaustive search for optimal thresholds (brute force for small K)
        best_var = -1.0
        best_thresholds: list[int] = []
        num_thresholds = classes - 1

        if num_thresholds == 1:
            # standard Otsu
            _, result = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thresh = int(cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[0])
            return result, [thresh]

        # for 3-class (2 thresholds)
        if num_thresholds == 2:
            for t1 in range(1, 254):
                for t2 in range(t1 + 1, 255):
                    w0 = prob[:t1].sum()
                    w1 = prob[t1:t2].sum()
                    w2 = prob[t2:].sum()
                    if w0 < 1e-10 or w1 < 1e-10 or w2 < 1e-10:
                        continue
                    m0 = np.sum(np.arange(t1) * prob[:t1]) / w0
                    m1 = np.sum(np.arange(t1, t2) * prob[t1:t2]) / w1
                    m2 = np.sum(np.arange(t2, 256) * prob[t2:]) / w2
                    mt = np.sum(np.arange(256) * prob)
                    var = w0 * (m0 - mt) ** 2 + w1 * (m1 - mt) ** 2 + w2 * (m2 - mt) ** 2
                    if var > best_var:
                        best_var = var
                        best_thresholds = [t1, t2]
        else:
            # fallback: use quantiles for K > 3
            quantiles = np.linspace(0, 1, classes + 1)[1:-1]
            cdf = np.cumsum(prob)
            best_thresholds = [int(np.searchsorted(cdf, q)) for q in quantiles]

        out = np.zeros_like(image)
        thresholds = sorted(best_thresholds)
        for i, t in enumerate(thresholds):
            out[image >= t] = int(255 * (i + 1) / (len(thresholds)))
        return out, thresholds

    @staticmethod
    def iterative_threshold(image: ArrayLike, epsilon: float = 0.5) -> tuple[ArrayLike, int]:
        """Iterative optimal thresholding.

        Converges to a threshold where the mean of foreground and background
        classes are equidistant from the threshold.

        Returns (binary_image, threshold).
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        t = float(image.mean())
        while True:
            fg = image[image >= t]
            bg = image[image < t]
            m_fg = fg.mean() if fg.size > 0 else t
            m_bg = bg.mean() if bg.size > 0 else t
            t_new = (m_fg + m_bg) / 2.0
            if abs(t_new - t) < epsilon:
                break
            t = t_new
        t_int = int(round(t))
        _, result = cv2.threshold(image, t_int, 255, cv2.THRESH_BINARY)
        return result, t_int

# ═══════════════════════════════════════════════════════════════════════════════
#  Transforms (Geometric & Accumulator)
# ═══════════════════════════════════════════════════════════════════════════════

class Transforms:
    """Static helpers for advanced image transforms."""

    @staticmethod
    def find_homography(image1: ArrayLike, image2: ArrayLike, method: Literal["sift", "orb"] = "sift") -> tuple[np.ndarray | None, ArrayLike]:
        """
        Finds the homography matrix to align image1 to image2 using feature matching.
        
        Returns
        -------
        tuple[np.ndarray | None, ArrayLike]
            The 3x3 homography matrix (or None if failed), and a visualization image of the matches.
        """
        img1 = to_cpu(_validate_image(image1))
        img2 = to_cpu(_validate_image(image2))
        
        gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY) if img1.ndim == 3 else img1
        gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY) if img2.ndim == 3 else img2
        
        if method == "sift":
            detector = cv2.SIFT_create()
            # FLANN matcher
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            matcher = cv2.FlannBasedMatcher(index_params, search_params)
        else:
            detector = cv2.ORB_create()
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            
        kp1, des1 = detector.detectAndCompute(gray1, None)
        kp2, des2 = detector.detectAndCompute(gray2, None)
        
        if des1 is None or des2 is None:
            return None, img1
            
        if method == "sift":
            matches = matcher.knnMatch(des1, des2, k=2)
            good_matches = []
            for m, n in matches:
                if m.distance < 0.7 * n.distance:
                    good_matches.append(m)
        else:
            matches = matcher.match(des1, des2)
            good_matches = sorted(matches, key=lambda x: x.distance)[:50] # top 50
            
        vis = cv2.drawMatches(img1, kp1, img2, kp2, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        
        if len(good_matches) > 4:
            pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            H, _ = cv2.findHomography(pts1, pts2, cv2.RANSAC, 5.0)
            return H, vis
        return None, vis

    @staticmethod
    def warp_perspective(image: ArrayLike, H: np.ndarray, output_shape: tuple[int, int]) -> ArrayLike:
        """
        Warps an image using a given homography matrix.
        output_shape is (width, height).
        """
        image = to_cpu(_validate_image(image))
        return cv2.warpPerspective(image, H, output_shape)

    @staticmethod
    def stitch_images(image_left: ArrayLike, image_right: ArrayLike) -> ArrayLike:
        """
        Automatically aligns and stitches two overlapping images into a single panorama.
        Assumes image_right is to the right of image_left.
        """
        imgL = to_cpu(_validate_image(image_left))
        imgR = to_cpu(_validate_image(image_right))
        
        H, vis = Transforms.find_homography(imgR, imgL, method="sift")
        if H is None:
            raise ValueError("Not enough matching features found to stitch images.")
            
        # Warp right image to left image's perspective, expanding the canvas
        hL, wL = imgL.shape[:2]
        hR, wR = imgR.shape[:2]
        
        # Determine corner points of right image to find the new canvas size
        corners = np.float32([[0,0], [0,hR], [wR,hR], [wR,0]]).reshape(-1,1,2)
        warped_corners = cv2.perspectiveTransform(corners, H)
        
        all_corners = np.concatenate((warped_corners, np.float32([[0,0], [0,hL], [wL,hL], [wL,0]]).reshape(-1,1,2)), axis=0)
        [xmin, ymin] = np.int32(all_corners.min(axis=0).ravel() - 0.5)
        [xmax, ymax] = np.int32(all_corners.max(axis=0).ravel() + 0.5)
        
        # Translation matrix to shift the image into the positive coordinate space
        t = [-xmin, -ymin]
        Ht = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]])
        
        result = cv2.warpPerspective(imgR, Ht.dot(H), (xmax-xmin, ymax-ymin))
        
        # Overlay the left image
        if imgL.ndim == 3:
            result[t[1]:hL+t[1], t[0]:wL+t[0]] = imgL
        else:
            result[t[1]:hL+t[1], t[0]:wL+t[0]] = imgL
            
        return result

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
    def wiener_filter(image: ArrayLike, kernel: ArrayLike, K: float = 0.01) -> ArrayLike:
        """
        Wiener deconvolution for removing blur and noise simultaneously.
        
        Parameters
        ----------
        image : ArrayLike
            Degraded image.
        kernel : ArrayLike
            Point Spread Function (PSF) that caused the blur.
        K : float
            Noise-to-signal power ratio.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        img_f = np.fft.fft2(image)
        
        # Pad kernel
        h, w = image.shape
        kh, kw = kernel.shape
        kernel_padded = np.zeros((h, w))
        kernel_padded[:kh, :kw] = kernel
        kernel_padded = np.fft.ifftshift(kernel_padded) # Align center
        
        H = np.fft.fft2(kernel_padded)
        H_conj = np.conj(H)
        
        # Wiener filter formula
        G = H_conj / (np.abs(H)**2 + K)
        
        restored_f = img_f * G
        restored = np.real(np.fft.ifft2(restored_f))
        
        return np.clip(restored, 0, 255).astype(np.uint8)

    @staticmethod
    def lucy_richardson_deconvolution(image: ArrayLike, kernel: ArrayLike, iterations: int = 15) -> ArrayLike:
        """
        Lucy-Richardson deconvolution (iterative method) for deblurring.
        Requires skimage.restoration.
        """
        image = to_cpu(_validate_image(image))
        kernel = to_cpu(_validate_image(kernel))
        
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
        try:
            from skimage import restoration
            # skimage expects float images 0-1
            image_float = image.astype(np.float64) / 255.0
            kernel_float = kernel.astype(np.float64) / np.sum(kernel)
            
            deconvolved = restoration.richardson_lucy(image_float, kernel_float, num_iter=iterations)
            return np.clip(deconvolved * 255, 0, 255).astype(np.uint8)
        except ImportError:
            raise NotImplementedError("scikit-image is required for Lucy-Richardson deconvolution. Install scikit-image.")

    @staticmethod
    def inpaint(image: ArrayLike, mask: ArrayLike, radius: int = 3, method: Literal["telea", "ns"] = "telea") -> ArrayLike:
        """
        Removes unwanted objects or scratches from an image.
        
        Parameters
        ----------
        image : ArrayLike
            Original image.
        mask : ArrayLike
            Binary mask indicating pixels to be inpainted (white = to be removed).
        radius : int
            Radius of a circular neighborhood of each point inpainted.
        method : 'telea' | 'ns'
            Algorithm choice (Telea or Navier-Stokes).
        """
        image = to_cpu(_validate_image(image))
        mask = to_cpu(_validate_image(mask))
        
        if mask.dtype != np.uint8:
            mask = (mask * 255).astype(np.uint8) if mask.dtype == bool else mask.astype(np.uint8)
            
        if mask.ndim == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
            
        flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
        
        return cv2.inpaint(image, mask, radius, flags)

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
    @gpu_accelerated
    def dft2(image: ArrayLike) -> ArrayLike:
        """Compute the 2D DFT (shifted so DC is centered). GPU-accelerated."""
        image = _validate_image(image)
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
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

        m_k = np.arange(M)[:, None]
        m_n = np.arange(M)[None, :]
        D_M = np.cos(np.pi * m_k * (2 * m_n + 1) / (2 * M))
        D_M[0, :] *= np.sqrt(1.0 / M)
        D_M[1:, :] *= np.sqrt(2.0 / M)

        n_k = np.arange(N)[:, None]
        n_n = np.arange(N)[None, :]
        D_N = np.cos(np.pi * n_k * (2 * n_n + 1) / (2 * N))
        D_N[0, :] *= np.sqrt(1.0 / N)
        D_N[1:, :] *= np.sqrt(2.0 / N)

        return D_M @ img @ D_N.T

    @staticmethod
    def idct2(coeffs: ArrayLike) -> ArrayLike:
        """Inverse 2D DCT (Type-III, orthonormal) using pure numpy."""
        coeffs = np.asarray(coeffs, dtype=np.float64)
        M, N = coeffs.shape

        m_k = np.arange(M)[:, None]
        m_n = np.arange(M)[None, :]
        D_M = np.cos(np.pi * m_k * (2 * m_n + 1) / (2 * M))
        D_M[0, :] *= np.sqrt(1.0 / M)
        D_M[1:, :] *= np.sqrt(2.0 / M)

        n_k = np.arange(N)[:, None]
        n_n = np.arange(N)[None, :]
        D_N = np.cos(np.pi * n_k * (2 * n_n + 1) / (2 * N))
        D_N[0, :] *= np.sqrt(1.0 / N)
        D_N[1:, :] *= np.sqrt(2.0 / N)

        return D_M.T @ coeffs @ D_N


# ═══════════════════════════════════════════════════════════════════════════════
#  Channel (permutation / reorder)
# ═══════════════════════════════════════════════════════════════════════════════

class Channel:
    """Channel permutation, swapping, and reordering utilities."""

    # all 6 permutations of 3-channel images
    PERMUTATIONS_3CH = {
        "RGB": (0, 1, 2), "RBG": (0, 2, 1),
        "GRB": (1, 0, 2), "GBR": (1, 2, 0),
        "BRG": (2, 0, 1), "BGR": (2, 1, 0),
    }

    @staticmethod
    def permute(image: ArrayLike, order: str) -> ArrayLike:
        """Reorder channels by name. e.g. 'GBR', 'BRG', 'BGR', etc."""
        image = _validate_image(image)
        if image.ndim != 3:
            raise ValueError("permute requires a 3-channel color image.")
        order = order.upper()
        if order not in Channel.PERMUTATIONS_3CH:
            raise ValueError(f"Unknown order '{order}'. Must be one of {list(Channel.PERMUTATIONS_3CH.keys())}.")
        idx = Channel.PERMUTATIONS_3CH[order]
        xp_mod = _xp(image)
        return xp_mod.stack([image[..., i] for i in idx], axis=-1)

    @staticmethod
    def reorder(image: ArrayLike, indices: Sequence[int]) -> ArrayLike:
        """Reorder channels by arbitrary index tuple. e.g. (2, 0, 1)."""
        image = _validate_image(image)
        if image.ndim != 3:
            raise ValueError("reorder requires a multi-channel image.")
        xp_mod = _xp(image)
        return xp_mod.stack([image[..., i] for i in indices], axis=-1)

    @staticmethod
    def swap(image: ArrayLike, ch_a: int, ch_b: int) -> ArrayLike:
        """Swap two channels in-place. e.g. swap(img, 0, 2) swaps R and B."""
        image = _validate_image(image)
        if image.ndim != 3:
            raise ValueError("swap requires a multi-channel image.")
        xp_mod = _xp(image)
        out = image.copy()
        out[..., ch_a] = image[..., ch_b]
        out[..., ch_b] = image[..., ch_a]
        return out

    @staticmethod
    def isolate(image: ArrayLike, channel: int, as_color: bool = True) -> ArrayLike:
        """Isolate a single channel. If as_color, other channels are zeroed."""
        image = _validate_image(image)
        if image.ndim != 3:
            raise ValueError("isolate requires a multi-channel image.")
        xp_mod = _xp(image)
        if as_color:
            out = xp_mod.zeros_like(image)
            out[..., channel] = image[..., channel]
            return out
        return image[..., channel].copy()

    @staticmethod
    def complement_split(image: ArrayLike) -> tuple[ArrayLike, ArrayLike, ArrayLike]:
        """Splits an RGB image into complementary color visualizations (comp_red, comp_green, comp_blue)."""
        image = _validate_image(image)
        xp_mod = _xp(image)
        
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError("complement_split requires a 3-channel color image.")
            
        r = image[..., 0]
        g = image[..., 1]
        b = image[..., 2]
        
        r_inv = 255 - r
        g_inv = 255 - g
        b_inv = 255 - b
        
        comp_red = xp_mod.stack([xp_mod.full_like(r_inv, 255), r_inv, r_inv], axis=-1)
        comp_green = xp_mod.stack([g_inv, xp_mod.full_like(g_inv, 255), g_inv], axis=-1)
        comp_blue = xp_mod.stack([b_inv, b_inv, xp_mod.full_like(b_inv, 255)], axis=-1)
        
        return comp_red, comp_green, comp_blue

    @staticmethod
    def complement_merge(comp_red: ArrayLike, comp_green: ArrayLike, comp_blue: ArrayLike) -> ArrayLike:
        """Merges complementary color visualizations back into the original RGB image."""
        comp_red = _validate_image(comp_red, name="comp_red")
        comp_green = _validate_image(comp_green, name="comp_green")
        comp_blue = _validate_image(comp_blue, name="comp_blue")
        xp_mod = _xp(comp_red)
        
        if comp_red.ndim != 3 or comp_red.shape[2] != 3:
            raise ValueError("All input arrays must be 3-channel color images.")
            
        masked_r = 255 - comp_red[..., 1]
        masked_g = 255 - comp_green[..., 0]
        masked_b = 255 - comp_blue[..., 0]
        
        return xp_mod.stack([masked_r, masked_g, masked_b], axis=-1)

    @staticmethod
    def show_permutations(image: ArrayLike) -> None:
        """Show all 6 RGB permutations side-by-side."""
        image = to_cpu(_validate_image(image))
        if image.ndim != 3:
            raise ValueError("show_permutations requires a 3-channel image.")
        images = [Channel.permute(image, k) for k in Channel.PERMUTATIONS_3CH]
        titles = list(Channel.PERMUTATIONS_3CH.keys())
        Image_Ops.show_collection(images, titles=titles, ncols=3)


# ═══════════════════════════════════════════════════════════════════════════════
#  Info (deep image inspection)
# ═══════════════════════════════════════════════════════════════════════════════

class Info:
    """One-call deep inspection of image properties."""

    @staticmethod
    def summary(image: ArrayLike, name: str = "Image") -> dict:
        """Print and return detailed image information.

        Returns dict with: shape, dtype, channels, min, max, mean, std,
        dynamic_range, entropy, estimated_size_kb per channel.
        """
        image = to_cpu(_validate_image(image))
        info: dict = {}
        h, w = image.shape[:2]
        ch = image.shape[2] if image.ndim == 3 else 1
        info["name"] = name
        info["shape"] = image.shape
        info["height"] = h
        info["width"] = w
        info["channels"] = ch
        info["dtype"] = str(image.dtype)
        info["total_pixels"] = h * w
        info["size_bytes"] = image.nbytes
        info["size_kb"] = round(image.nbytes / 1024, 2)

        img_f = image.astype(np.float64)
        if image.ndim == 2:
            info["min"] = int(image.min())
            info["max"] = int(image.max())
            info["mean"] = round(float(img_f.mean()), 2)
            info["std"] = round(float(img_f.std()), 2)
            info["dynamic_range"] = int(image.max()) - int(image.min())
            hist, _ = np.histogram(image.ravel(), bins=256, range=(0, 256))
            prob = hist.astype(np.float64) / (hist.sum() + 1e-12)
            info["entropy"] = round(float(-np.sum(prob[prob > 0] * np.log2(prob[prob > 0]))), 4)
        else:
            ch_names = ["R", "G", "B", "A"] if ch <= 4 else [f"ch{i}" for i in range(ch)]
            for i in range(ch):
                c = image[..., i]
                cf = img_f[..., i]
                info[f"{ch_names[i]}_min"] = int(c.min())
                info[f"{ch_names[i]}_max"] = int(c.max())
                info[f"{ch_names[i]}_mean"] = round(float(cf.mean()), 2)
                info[f"{ch_names[i]}_std"] = round(float(cf.std()), 2)
            info["dynamic_range"] = int(image.max()) - int(image.min())

        # print summary
        print(f"╔══ {name} ═══════════════════════════════")
        print(f"║ Shape     : {info['shape']}  ({info['dtype']})")
        print(f"║ Pixels    : {info['total_pixels']:,}  ({info['size_kb']} KB)")
        if image.ndim == 2:
            print(f"║ Range     : [{info['min']}, {info['max']}]  (dynamic: {info['dynamic_range']})")
            print(f"║ Mean±Std  : {info['mean']} ± {info['std']}")
            print(f"║ Entropy   : {info['entropy']} bits")
        else:
            for i in range(ch):
                n = ch_names[i]
                print(f"║ {n:2s}        : [{info[f'{n}_min']}, {info[f'{n}_max']}]  mean={info[f'{n}_mean']}  std={info[f'{n}_std']}")
        print(f"╚{'═' * 42}")
        return info

    @staticmethod
    def compare(img1: ArrayLike, img2: ArrayLike, name1: str = "Image 1", name2: str = "Image 2") -> None:
        """Print side-by-side summary of two images."""
        Info.summary(img1, name=name1)
        Info.summary(img2, name=name2)


# ═══════════════════════════════════════════════════════════════════════════════
#  BitPlane (bit-plane slicing)
# ═══════════════════════════════════════════════════════════════════════════════

class BitPlane:
    """Extract, reconstruct, and visualize individual bit planes."""

    @staticmethod
    def extract(image: ArrayLike, bit: int) -> ArrayLike:
        """Extract a single bit plane (0=LSB, 7=MSB). Returns binary image."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if not 0 <= bit <= 7:
            raise ValueError("bit must be in [0, 7].")
        return ((image >> bit) & 1).astype(np.uint8) * 255

    @staticmethod
    def extract_all(image: ArrayLike) -> list[ArrayLike]:
        """Extract all 8 bit planes. Returns list[0..7] (LSB to MSB)."""
        return [BitPlane.extract(image, b) for b in range(8)]

    @staticmethod
    def reconstruct(image: ArrayLike, bits: Sequence[int]) -> ArrayLike:
        """Reconstruct image from selected bit planes only.

        Parameters
        ----------
        bits : Sequence[int]
            Which bit planes to keep (e.g. [7, 6, 5] for top 3 bits).
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        out = np.zeros_like(image, dtype=np.uint8)
        for b in bits:
            if not 0 <= b <= 7:
                raise ValueError(f"bit {b} must be in [0, 7].")
            out |= ((image >> b) & 1).astype(np.uint8) << b
        return out

    @staticmethod
    def show_all(image: ArrayLike, figsize: tuple[int, int] = (16, 8)) -> None:
        """Display all 8 bit planes in a grid."""
        planes = BitPlane.extract_all(image)
        titles = [f"Bit {i} ({'MSB' if i == 7 else 'LSB' if i == 0 else ''})" for i in range(8)]
        Image_Ops.show_collection(planes, titles=titles, ncols=4, figsize=figsize)


# ═══════════════════════════════════════════════════════════════════════════════
#  Metrics (image quality comparison)
# ═══════════════════════════════════════════════════════════════════════════════

class Metrics:
    """Image quality metrics: MSE, PSNR, SSIM, MAE."""

    @staticmethod
    def mse(img1: ArrayLike, img2: ArrayLike) -> float:
        """Mean Squared Error between two images."""
        img1 = to_cpu(_validate_image(img1)).astype(np.float64)
        img2 = to_cpu(_validate_image(img2)).astype(np.float64)
        return float(np.mean((img1 - img2) ** 2))

    @staticmethod
    def mae(img1: ArrayLike, img2: ArrayLike) -> float:
        """Mean Absolute Error between two images."""
        img1 = to_cpu(_validate_image(img1)).astype(np.float64)
        img2 = to_cpu(_validate_image(img2)).astype(np.float64)
        return float(np.mean(np.abs(img1 - img2)))

    @staticmethod
    def psnr(img1: ArrayLike, img2: ArrayLike, max_val: float = 255.0) -> float:
        """Peak Signal-to-Noise Ratio (dB). Higher = better."""
        mse_val = Metrics.mse(img1, img2)
        if mse_val < 1e-10:
            return float("inf")
        return float(10.0 * np.log10(max_val ** 2 / mse_val))

    @staticmethod
    def ssim(img1: ArrayLike, img2: ArrayLike, window_size: int = 7) -> float:
        """Structural Similarity Index (SSIM). Range [-1, 1], 1 = identical.

        Manual implementation — no external dependencies.
        """
        img1 = to_cpu(_validate_image(img1)).astype(np.float64)
        img2 = to_cpu(_validate_image(img2)).astype(np.float64)
        if img1.ndim == 3:
            img1 = cv2.cvtColor(img1.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float64)
        if img2.ndim == 3:
            img2 = cv2.cvtColor(img2.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float64)

        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2
        k = cv2.getGaussianKernel(window_size, 1.5)
        window = k @ k.T

        mu1 = cv2.filter2D(img1, -1, window)
        mu2 = cv2.filter2D(img2, -1, window)
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu12 = mu1 * mu2
        sigma1_sq = cv2.filter2D(img1 ** 2, -1, window) - mu1_sq
        sigma2_sq = cv2.filter2D(img2 ** 2, -1, window) - mu2_sq
        sigma12 = cv2.filter2D(img1 * img2, -1, window) - mu12

        num = (2 * mu12 + c1) * (2 * sigma12 + c2)
        den = (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
        ssim_map = num / den
        return float(np.mean(ssim_map))

    @staticmethod
    def report(img1: ArrayLike, img2: ArrayLike, name1: str = "Original", name2: str = "Processed") -> dict:
        """Print a full quality report comparing two images."""
        results = {
            "MSE": Metrics.mse(img1, img2),
            "MAE": Metrics.mae(img1, img2),
            "PSNR": Metrics.psnr(img1, img2),
            "SSIM": Metrics.ssim(img1, img2),
        }
        print(f"╔══ Quality Report: {name1} vs {name2} ═══")
        print(f"║ MSE  : {results['MSE']:.4f}")
        print(f"║ MAE  : {results['MAE']:.4f}")
        print(f"║ PSNR : {results['PSNR']:.2f} dB")
        print(f"║ SSIM : {results['SSIM']:.4f}")
        print(f"╚{'═' * 45}")
        return results


# ═══════════════════════════════════════════════════════════════════════════════
#  FreqFilter (frequency-domain filtering)
# ═══════════════════════════════════════════════════════════════════════════════

class FreqFilter:
    """Frequency-domain filters: Ideal, Butterworth, Gaussian LPF/HPF + Homomorphic."""

    @staticmethod
    def _make_distance_grid(h: int, w: int) -> np.ndarray:
        """Create a distance-from-center grid for frequency domain."""
        cy, cx = h // 2, w // 2
        Y, X = np.ogrid[:h, :w]
        return np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(np.float64)

    @staticmethod
    def ideal_lpf(image: ArrayLike, cutoff: float = 30) -> ArrayLike:
        """Ideal low-pass filter in frequency domain."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = (dist <= cutoff).astype(np.float64)
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def ideal_hpf(image: ArrayLike, cutoff: float = 30) -> ArrayLike:
        """Ideal high-pass filter in frequency domain."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = (dist > cutoff).astype(np.float64)
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def butterworth_lpf(image: ArrayLike, cutoff: float = 30, order: int = 2) -> ArrayLike:
        """Butterworth low-pass filter. Smoother transition than ideal."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = 1.0 / (1.0 + (dist / (cutoff + 1e-8)) ** (2 * order))
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def butterworth_hpf(image: ArrayLike, cutoff: float = 30, order: int = 2) -> ArrayLike:
        """Butterworth high-pass filter."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = 1.0 / (1.0 + ((cutoff + 1e-8) / (dist + 1e-8)) ** (2 * order))
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def gaussian_lpf(image: ArrayLike, cutoff: float = 30) -> ArrayLike:
        """Gaussian low-pass filter in frequency domain."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = np.exp(-(dist ** 2) / (2 * cutoff ** 2))
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def gaussian_hpf(image: ArrayLike, cutoff: float = 30) -> ArrayLike:
        """Gaussian high-pass filter in frequency domain."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = image.shape
        dist = FreqFilter._make_distance_grid(h, w)
        mask = 1.0 - np.exp(-(dist ** 2) / (2 * cutoff ** 2))
        dft = np.fft.fftshift(np.fft.fft2(image.astype(np.float64)))
        result = np.real(np.fft.ifft2(np.fft.ifftshift(dft * mask)))
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def homomorphic(image: ArrayLike, gamma_l: float = 0.5, gamma_h: float = 2.0,
                    cutoff: float = 30, c: float = 1.0) -> ArrayLike:
        """Homomorphic filter for illumination/reflectance separation.

        Parameters
        ----------
        gamma_l : float
            Low-frequency gain (< 1 compresses illumination).
        gamma_h : float
            High-frequency gain (> 1 enhances reflectance/edges).
        cutoff : float
            Cutoff frequency for the Gaussian filter.
        c : float
            Sharpness of the transition.
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        img_log = np.log1p(image.astype(np.float64))
        h, w = img_log.shape
        dist = FreqFilter._make_distance_grid(h, w)
        # Gaussian-based homomorphic filter
        H = (gamma_h - gamma_l) * (1 - np.exp(-c * (dist ** 2) / (cutoff ** 2 + 1e-8))) + gamma_l
        dft = np.fft.fftshift(np.fft.fft2(img_log))
        filtered = np.real(np.fft.ifft2(np.fft.ifftshift(dft * H)))
        result = np.expm1(filtered)
        # normalize to 0-255
        result = (result - result.min()) / (result.max() - result.min() + 1e-8) * 255
        return np.clip(result, 0, 255).astype(np.uint8)

    @staticmethod
    def show_filter(image: ArrayLike, title: str = "Frequency Filter") -> None:
        """Show original, magnitude spectrum, and filtered result."""
        mag = to_cpu(Fourier.magnitude_spectrum(image))
        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        plt.imshow(to_cpu(_validate_image(image)), cmap="gray")
        plt.title(f"{title} — Spatial")
        plt.axis("off")
        plt.subplot(1, 2, 2)
        plt.imshow(mag, cmap="gray")
        plt.title(f"{title} — Magnitude Spectrum")
        plt.axis("off")
        plt.tight_layout()
        plt.show()

    @staticmethod
    def modulate(image: ArrayLike, frequency: float = 0.05, angle: float = 45.0) -> ArrayLike:
        import io
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255.0
        else:
            gray = image.astype(np.float64) / 255.0
            
        h, w = gray.shape[:2]
        
        theta = np.deg2rad(angle)
        y_grid, x_grid = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
        fx = frequency * np.cos(theta)
        fy = frequency * np.sin(theta)
        
        grating = 0.5 + 0.5 * np.cos(2 * np.pi * (fx * x_grid + fy * y_grid))
        modulated = gray * grating
        
        def get_fft_spectrum(img):
            f = np.fft.fft2(img)
            fshift = np.fft.fftshift(f)
            magnitude = np.abs(fshift)
            spec = np.log1p(magnitude)
            s_min, s_max = spec.min(), spec.max()
            if s_max - s_min > 1e-6:
                spec = (spec - s_min) / (s_max - s_min) * 255.0
            else:
                spec = np.zeros_like(spec)
            return spec.astype(np.uint8)
            
        fft_orig = get_fft_spectrum(gray)
        fft_grating = get_fft_spectrum(grating)
        fft_modulated = get_fft_spectrum(modulated)
        
        fig, axes = plt.subplots(2, 3, figsize=(12, 8), dpi=100)
        
        axes[0, 0].imshow(gray, cmap="gray")
        axes[0, 0].set_title("Original (Spatial)", fontsize=11, fontweight="bold")
        axes[0, 0].axis("off")
        
        axes[0, 1].imshow(grating, cmap="gray")
        axes[0, 1].set_title("Grating (Spatial)", fontsize=11, fontweight="bold")
        axes[0, 1].axis("off")
        
        axes[0, 2].imshow(modulated, cmap="gray")
        axes[0, 2].set_title("Modulated (Spatial)", fontsize=11, fontweight="bold")
        axes[0, 2].axis("off")
        
        axes[1, 0].imshow(fft_orig, cmap="gray")
        axes[1, 0].set_title("Original (FFT Spectrum)", fontsize=11, fontweight="bold")
        axes[1, 0].axis("off")
        
        axes[1, 1].imshow(fft_grating, cmap="gray")
        axes[1, 1].set_title("Grating (FFT Spectrum)", fontsize=11, fontweight="bold")
        axes[1, 1].axis("off")
        
        axes[1, 2].imshow(fft_modulated, cmap="gray")
        axes[1, 2].set_title("Modulated (FFT Spectrum)", fontsize=11, fontweight="bold")
        axes[1, 2].axis("off")
        
        fig.text(0.36, 0.72, r"$\times$", fontsize=30, ha="center", va="center")
        fig.text(0.66, 0.72, r"$=$", fontsize=30, ha="center", va="center")
        
        fig.text(0.36, 0.28, r"$\ast$", fontsize=35, ha="center", va="center")
        fig.text(0.66, 0.28, r"$=$", fontsize=30, ha="center", va="center")
        
        fig.suptitle("Fourier Convolution Theorem: Spatial Modulation vs Frequency Convolution", fontsize=14, fontweight="bold")
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close()
        buf.seek(0)
        
        file_bytes = np.asarray(bytearray(buf.read()), dtype=np.uint8)
        out_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        return cv2.cvtColor(out_img, cv2.COLOR_BGR2RGB)

    @staticmethod
    def fft(image: ArrayLike) -> ArrayLike:
        """Calculate and return the log-scaled FFT magnitude spectrum of the image."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image
        
        dft = np.fft.fft2(gray.astype(np.float64))
        dft_shift = np.fft.fftshift(dft)
        magnitude = np.abs(dft_shift)
        spec = np.log1p(magnitude)
        
        s_min, s_max = spec.min(), spec.max()
        if s_max - s_min > 1e-6:
            spec = (spec - s_min) / (s_max - s_min) * 255.0
        else:
            spec = np.zeros_like(spec)
            
        spectrum = spec.astype(np.uint8)
        return cv2.cvtColor(spectrum, cv2.COLOR_GRAY2RGB)

    @staticmethod
    def dct(image: ArrayLike) -> ArrayLike:
        """Calculate and return the log-scaled DCT magnitude spectrum of the image."""
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image
        
        gray_f32 = gray.astype(np.float32)
        h, w = gray_f32.shape
        pad_h = h + (h % 2) - h
        pad_w = w + (w % 2) - w
        if pad_h > 0 or pad_w > 0:
            gray_f32 = np.pad(gray_f32, ((0, pad_h), (0, pad_w)), mode='edge')
            
        dct_coeffs = cv2.dct(gray_f32)
        magnitude = np.abs(dct_coeffs)
        spec = np.log1p(magnitude)
        
        s_min, s_max = spec.min(), spec.max()
        if s_max - s_min > 1e-6:
            spec = (spec - s_min) / (s_max - s_min) * 255.0
        else:
            spec = np.zeros_like(spec)
            
        if pad_h > 0 or pad_w > 0:
            spec = spec[:h, :w]
            
        spectrum = spec.astype(np.uint8)
        return cv2.cvtColor(spectrum, cv2.COLOR_GRAY2RGB)


# ═══════════════════════════════════════════════════════════════════════════════
#  Pyramid (Gaussian / Laplacian image pyramids)
# ═══════════════════════════════════════════════════════════════════════════════

class Pyramid:
    """Gaussian and Laplacian image pyramids with seamless blending."""

    @staticmethod
    def gaussian(image: ArrayLike, levels: int = 4) -> list[ArrayLike]:
        """Build a Gaussian pyramid (progressively downsampled).

        Returns list of images from original resolution to smallest.
        """
        image = to_cpu(_validate_image(image))
        pyramid = [image.copy()]
        current = image
        for _ in range(levels - 1):
            current = cv2.pyrDown(current)
            pyramid.append(current)
        return pyramid

    @staticmethod
    def laplacian(image: ArrayLike, levels: int = 4) -> list[ArrayLike]:
        """Build a Laplacian pyramid (detail at each scale).

        Returns list of detail images + the smallest approximation.
        """
        gauss = Pyramid.gaussian(image, levels)
        lap = []
        for i in range(len(gauss) - 1):
            h, w = gauss[i].shape[:2]
            expanded = cv2.pyrUp(gauss[i + 1], dstsize=(w, h))
            detail = cv2.subtract(gauss[i], expanded)
            lap.append(detail)
        lap.append(gauss[-1])  # smallest approximation
        return lap

    @staticmethod
    def reconstruct(laplacian_pyramid: list[ArrayLike]) -> ArrayLike:
        """Reconstruct image from a Laplacian pyramid."""
        current = laplacian_pyramid[-1]
        for i in range(len(laplacian_pyramid) - 2, -1, -1):
            h, w = laplacian_pyramid[i].shape[:2]
            expanded = cv2.pyrUp(current, dstsize=(w, h))
            current = cv2.add(expanded, laplacian_pyramid[i])
        return current

    @staticmethod
    def blend(img1: ArrayLike, img2: ArrayLike, mask: ArrayLike, levels: int = 6) -> ArrayLike:
        """Seamless pyramid blending of two images using a mask.

        Parameters
        ----------
        img1, img2 : ArrayLike
            Images to blend (same size).
        mask : ArrayLike
            Grayscale mask (0 = img2, 255 = img1). Same spatial dims.
        levels : int
            Number of pyramid levels.
        """
        img1 = to_cpu(_validate_image(img1))
        img2 = to_cpu(_validate_image(img2))
        mask = to_cpu(_validate_image(mask))
        if mask.ndim == 2 and img1.ndim == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
        mask_f = mask.astype(np.float64) / 255.0

        lap1 = Pyramid.laplacian(img1, levels)
        lap2 = Pyramid.laplacian(img2, levels)
        gauss_mask = Pyramid.gaussian(mask_f.astype(np.uint8), levels)

        blended_lap = []
        for l1, l2, gm in zip(lap1, lap2, gauss_mask):
            gm_f = gm.astype(np.float64) / 255.0
            if gm_f.ndim == 2 and l1.ndim == 3:
                gm_f = gm_f[..., np.newaxis]
            blended = (l1.astype(np.float64) * gm_f + l2.astype(np.float64) * (1 - gm_f))
            blended_lap.append(np.clip(blended, 0, 255).astype(np.uint8))
        return Pyramid.reconstruct(blended_lap)

    @staticmethod
    def show(pyramid: list[ArrayLike], title: str = "Pyramid") -> None:
        """Display all levels of a pyramid."""
        titles = [f"{title} L{i}" for i in range(len(pyramid))]
        Image_Ops.show_collection(pyramid, titles=titles, ncols=min(4, len(pyramid)))


# ═══════════════════════════════════════════════════════════════════════════════
#  Stego (LSB steganography)
# ═══════════════════════════════════════════════════════════════════════════════

class Stego:
    """LSB steganography — hide and extract text messages in images."""

    @staticmethod
    def encode(image: ArrayLike, message: str, delimiter: str = "###END###") -> ArrayLike:
        """Encode a text message into the LSB of an image.

        Parameters
        ----------
        image : ArrayLike
            Cover image (will be modified).
        message : str
            Secret text to hide.
        delimiter : str
            End-of-message marker.
        """
        image = to_cpu(_validate_image(image)).copy()
        msg_bin = ''.join(format(ord(c), '08b') for c in (message + delimiter))
        flat = image.ravel()
        if len(msg_bin) > len(flat):
            raise ValueError(f"Message too long ({len(msg_bin)} bits) for image ({len(flat)} pixels).")
        for i, bit in enumerate(msg_bin):
            flat[i] = (flat[i] & 0xFE) | int(bit)
        return flat.reshape(image.shape).astype(image.dtype)

    @staticmethod
    def decode(image: ArrayLike, delimiter: str = "###END###") -> str:
        """Extract a hidden text message from the LSB of an image."""
        image = to_cpu(_validate_image(image))
        flat = image.ravel()
        bits = ""
        message = ""
        for pixel in flat:
            bits += str(pixel & 1)
            if len(bits) >= 8:
                char = chr(int(bits[:8], 2))
                message += char
                bits = bits[8:]
                if message.endswith(delimiter):
                    return message[:-len(delimiter)]
        return message


# ═══════════════════════════════════════════════════════════════════════════════
#  Components (connected component labeling)
# ═══════════════════════════════════════════════════════════════════════════════

class Components:
    """Connected component labeling and region properties."""

    @staticmethod
    def label(image: ArrayLike, connectivity: int = 8) -> tuple[int, ArrayLike]:
        """Label connected components in a binary image.

        Returns (num_labels, labeled_image).
        """
        image = to_cpu(_validate_image(image))
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        num, labels = cv2.connectedComponents(binary, connectivity=connectivity)
        return num, labels

    @staticmethod
    def properties(labeled: ArrayLike) -> list[dict]:
        """Compute region properties for each labeled component.

        Returns list of dicts with: label, area, centroid, bbox.
        """
        labeled = to_cpu(labeled)
        props = []
        for lbl in range(1, labeled.max() + 1):
            mask = (labeled == lbl).astype(np.uint8)
            area = int(mask.sum())
            if area == 0:
                continue
            ys, xs = np.where(mask)
            cy = float(np.mean(ys))
            cx = float(np.mean(xs))
            y_min, y_max = int(ys.min()), int(ys.max())
            x_min, x_max = int(xs.min()), int(xs.max())
            props.append({
                "label": lbl,
                "area": area,
                "centroid": (cy, cx),
                "bbox": (y_min, x_min, y_max, x_max),
                "width": x_max - x_min + 1,
                "height": y_max - y_min + 1,
            })
        return props

    @staticmethod
    def show(image: ArrayLike, connectivity: int = 8) -> None:
        """Visualize connected components with random colors."""
        num, labels = Components.label(image, connectivity)
        colored = np.zeros((*labels.shape, 3), dtype=np.uint8)
        for lbl in range(1, num):
            colored[labels == lbl] = np.random.randint(50, 255, size=3, dtype=np.uint8)
        plt.figure(figsize=(8, 6))
        plt.imshow(colored)
        plt.title(f"Connected Components ({num - 1} found)")
        plt.axis("off")
        plt.tight_layout()
        plt.show()


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
resize_image = Image_Ops.resize
slice_image = Image_Ops.slice
pad_image = Image_Ops.pad
overlay_image = Image_Ops.overlay
intensity_threshold_mask = Image_Ops.intensity_threshold_mask
color_intensity_threshold_mask = Image_Ops.color_intensity_threshold_mask
intensity_threshold_mask_inv = Image_Ops.intensity_threshold_mask_inv
intensity_range_mask = Image_Ops.intensity_range_mask
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
to_grayscale = Image_Ops.to_grayscale
to_color = Image_Ops.to_color
rgb_split = Image_Ops.rgb_split
rgb_merge = Image_Ops.rgb_merge
show_rgb_channels = Image_Ops.show_rgb_channels
add_to_image = Image_Ops.add
subtract_from_image = Image_Ops.subtract
multiply_image = Image_Ops.multiply
divide_image = Image_Ops.divide
add_salt_pepper_noise = Image_Ops.add_salt_pepper

show_histogram = Histogram.show
show_histograms = Histogram.show_multi
show_histogram_original_normalized = Histogram.show_original_and_normalized
show_combined_histogram = Histogram.show_combined

convolve_image = Convolution.apply

equalize_histogram = Equalization.equalize
normalize_histogram = Equalization.equalize

match_histogram = Specialization.match

adjust_brightness_contrast = Enhancement.brightness_contrast
blur_image = Enhancement.blur_gaussian
erode_image = Morphology.erode

detect_edges = Edge_Detection.canny
detect_edges_gpu = Edge_Detection.canny_gpu
auto_canny = Edge_Detection.auto_canny

apply_binary_mask = Image_Ops.apply_binary_mask

thin_image = Morphology.thinning
thick_image = Morphology.thickening
reconstruct_image = Morphology.reconstruct

# --- Wavelet Aliases ---
dwt2 = Wavelet.dwt2
idwt2 = Wavelet.idwt2
wavedec2 = Wavelet.wavedec2
wavedec2_dynamic = Wavelet.wavedec2_dynamic
waverec2 = Wavelet.waverec2
assemble_wavedec2_grid = Wavelet.assemble_wavedec2_grid
high_frequency_energy = Wavelet.high_frequency_energy
process_rgb_wavelet = Wavelet.process_rgb_wavelet

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

mean_filter = Filter.mean
median_filter = Filter.median
mode_filter = Filter.mode
smooth_filter = Filter.smooth
sharpen_filter = Filter.sharpen
low_pass_filter = Filter.low_pass
high_pass_filter = Filter.high_pass
band_pass_filter = Filter.band_pass

load_csv = CSV.read
load_csv_dict = CSV.read_dict
load_histogram_csv = CSV.load_histogram

channel_permute = Channel.permute
channel_reorder = Channel.reorder
channel_swap = Channel.swap
channel_isolate = Channel.isolate

image_info = Info.summary
image_compare = Info.compare

extract_bitplane = BitPlane.extract
reconstruct_bitplane = BitPlane.reconstruct
show_bitplanes = BitPlane.show_all

compute_mse = Metrics.mse
compute_mae = Metrics.mae
compute_psnr = Metrics.psnr
compute_ssim = Metrics.ssim
quality_report = Metrics.report

ideal_lpf = FreqFilter.ideal_lpf
ideal_hpf = FreqFilter.ideal_hpf
butterworth_lpf = FreqFilter.butterworth_lpf
butterworth_hpf = FreqFilter.butterworth_hpf
gaussian_lpf = FreqFilter.gaussian_lpf
gaussian_hpf = FreqFilter.gaussian_hpf
homomorphic_filter = FreqFilter.homomorphic

gaussian_pyramid = Pyramid.gaussian
laplacian_pyramid = Pyramid.laplacian
pyramid_blend = Pyramid.blend

stego_encode = Stego.encode
stego_decode = Stego.decode

label_components = Components.label
component_properties = Components.properties

multi_otsu = Segmentation.multi_otsu
iterative_threshold = Segmentation.iterative_threshold
contrast_stretch = Enhancement.contrast_stretch
piecewise_linear = Enhancement.piecewise_linear

zero_border = Image_Ops.zero_border
zero_ellipse = Image_Ops.zero_ellipse
fade_border = Image_Ops.fade_border
seal_mask = Image_Ops.seal_mask
prune_mask = Image_Ops.prune_mask


def resize(image: ArrayLike, new_width: int, new_height: int, interpolation: InterpMode = "linear") -> ArrayLike:
    """Resize an image to the given (new_width, new_height).

    Convenience wrapper around Image_Ops.resize that takes explicit
    width and height as positional arguments.

    Parameters
    ----------
    image : ArrayLike
        Input image (grayscale or color).
    new_width : int
        Target width in pixels.
    new_height : int
        Target height in pixels.
    interpolation : InterpMode
        Interpolation method ('nearest', 'linear', 'area', 'cubic', 'lanczos').

    Returns
    -------
    ArrayLike
        Resized image.
    """
    return Image_Ops.resize(image, width=new_width, height=new_height, interpolation=interpolation)
