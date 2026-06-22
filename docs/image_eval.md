# ⛓️ Image Evaluation Pipeline Guide

The `/image eval` command (on Discord) and `/image_eval` / `/ieval` commands (on Telegram) allow you to apply a sequential pipeline of image processing filters to an image in a single command. By chaining multiple filters together, you can create complex, custom image effects without needing to run separate commands.

---

## 🧭 Basic Syntax

The pipeline string is a comma-separated list of operators. Operators are executed from left to right:
```
filter1,filter2:param,filter3:param1:param2
```
- **Filter Name**: The identifier of the filter (e.g., `grayscale`, `blur`).
- **Arguments**: Parameters are appended after a colon (`:`). Multiple parameters for a single filter are separated by colons (e.g., `blur:5`, `rotate:90:ccw`).

---

## 🎨 Supported Single-Image Operators

These operators modify a single image and pass the output to the next filter in the pipeline.

### 1. Basic & Color Filters
- `grayscale` — Converts the image to black & white.
- `invert` — Inverts color channels.
- `circle` — Crops the image to a circle with transparent/solid background.
- `sepia` — Applies a warm sepia tone.
- `log` — Applies a logarithmic dynamic range compression.

### 2. Convolutions & Adjustments
- `blur:strength` — Applies box blur. (Default strength: `5`).
- `sharpen` — Sharpens image details.
- `emboss` — Applies a 3D embossing effect.
- `pixelate:size` — Creates a retro blocky pixelation effect. (Default size: `16`).
- `vignette:sigma` — Applies a dark vignette border. (Default sigma: `150`).
- `gamma:value` — Performs gamma correction. (Default value: `1.5`).
- `adjust:brightness:contrast` — Adjusts brightness (multiplier) and contrast (offset). (Defaults: `1.0` and `0`).
- `flip:direction` — Flips the image. Directions: `horizontal` (or `h`), `vertical` (or `v`). (Default: `horizontal`).
- `rotate:angle:direction` — Rotates the image. Direction: `cw` (clockwise) or `ccw` (counter-clockwise). (Defaults: `90.0` and `ccw`).

### 3. Edge Detection, Noise & Equalization
- `edge:method` — Detects edges. Methods: `canny`, `sobel`, `laplacian`, `prewitt`, `roberts`, `scharr`. (Default: `canny`).
- `noise:type` — Adds noise. Types: `salt_pepper`, `gaussian`, `poisson`. (Default: `salt_pepper`).
- `equalize:method` — Normalizes contrast. Methods: `global`, `clahe`, `adaptive`. (Default: `global`).
- `threshold:val:style` — Converts the image to binary black/white. Style: `binary`, `otsu`. (Defaults: `127` and `binary`).

### 4. Mathematical Morphology
- `erode:iterations:kernel_size` — Shrinks brighter areas. (Defaults: `1` iteration, kernel size `3`).
- `dilate:iterations:kernel_size` — Expands brighter areas. (Defaults: `1` iteration, kernel size `3`).
- `skeleton` — Extracts the topological skeleton of the image.

### 5. Fourier Frequency Filtering & Spectrum Analysis
- `lpf:cutoff:type:order` — Applies Low-Pass Filtering (frequency domain smoothing). Types: `ideal`, `butterworth`, `gaussian`. (Defaults: `30.0`, `gaussian`, `2`).
- `hpf:cutoff:type:order` — Applies High-Pass Filtering (frequency domain sharpening). Types: `ideal`, `butterworth`, `gaussian`. (Defaults: `30.0`, `gaussian`, `2`).
- `homomorphic:gl:gh:cutoff` — Normalizes illumination & boosts contrast. (Defaults: `0.5`, `2.0`, `30.0`).
- `fft` — Returns the log-scaled Fast Fourier Transform (FFT) magnitude spectrum.
- `dct` — Returns the log-scaled Discrete Cosine Transform (DCT) magnitude spectrum.

### 6. Artistic Filters
- `posterize:levels` — Reduces the number of colors to create a poster-like look. (Default levels: `4`).
- `solarize:threshold` — Inverts color values above a certain threshold. (Default threshold: `128`).
- `sketch:ksize` — Creates a pencil sketch representation. (Default Gaussian blur kernel: `21`).

---

## 👥 Supported Two-Image Operators

Two-image operators allow merging the current pipeline image with a secondary image (`image2`).
> [!NOTE]
> On Discord, supply the secondary image using the `user2` or `attachment2` options.
> On Telegram, reply to an existing photo while attaching/sending a new photo to load both `image1` (replied photo) and `image2` (current caption photo).

- `blend:alpha` — Blends the current image with the secondary image using a transparency factor. `alpha` ranges from `0.0` (all current image) to `1.0` (all secondary image).
- `composite:mode` — Combines the two images using mathematical blending formulas. Modes: `normal`, `add`, `multiply`, `screen`, `overlay`.
- `concat:axis` — Stitches the two images together. Axis: `horizontal` (or `h`), `vertical` (or `v`).

---

## 💡 Practical Examples

Chaining filters together unlocks incredibly cool artistic effects! Here are some combinations to try:

### 1. Retro Blueprint Blueprint
* **Pipeline String**: `grayscale,invert,threshold:128:binary,invert`
* **Result**: Turns a standard photo into a clean blueprint-like line drawing.

### 2. High Contrast Pop-Art Poster
* **Pipeline String**: `equalize:clahe,posterize:3,adjust:1.2:10`
* **Result**: Evens out the lighting, compresses the colors into three solid steps, and boosts brightness and contrast to make colors pop.

### 3. Cyberpunk Edge Overlay
* **Pipeline String**: `edge:canny,invert,blend:0.3`
* **Result**: Detects edges using Canny, inverts them to black lines on white, and blends them at 30% transparency back over the secondary base image to create an hand-drawn edge overlay.

### 4. Frequency Domain Artistic Glow
* **Pipeline String**: `lpf:20:gaussian,adjust:1.5:-20,blend:0.5`
* **Result**: Low-pass filters the image to create a smooth, blurry glow, boosts the brightness/lowers the contrast of that glow, and blends it back onto the original reference photo at 50% opacity.
