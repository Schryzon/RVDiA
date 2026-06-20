// FFT and Image Signal Processing helpers
function bitReverse(n, bits) {
    let r = 0;
    for (let i = 0; i < bits; i++) {
        if ((n & (1 << i)) !== 0) {
            r |= 1 << (bits - 1 - i);
        }
    }
    return r;
}

function fft1D(re, im, logN, forward) {
    const N = 1 << logN;
    for (let i = 0; i < N; i++) {
        const j = bitReverse(i, logN);
        if (i < j) {
            let temp = re[i]; re[i] = re[j]; re[j] = temp;
            temp = im[i]; im[i] = im[j]; im[j] = temp;
        }
    }
    const sign = forward ? -1 : 1;
    for (let stage = 1; stage <= logN; stage++) {
        const m = 1 << stage;
        const m2 = m >> 1;
        const angle = (sign * 2 * Math.PI) / m;
        const wFractionRe = Math.cos(angle);
        const wFractionIm = Math.sin(angle);
        
        for (let k = 0; k < N; k += m) {
            let wRe = 1;
            let wIm = 0;
            for (let j = 0; j < m2; j++) {
                const i = k + j;
                const ip = i + m2;
                const tRe = wRe * re[ip] - wIm * im[ip];
                const tIm = wRe * im[ip] + wIm * re[ip];
                
                re[ip] = re[i] - tRe;
                im[ip] = im[i] - tIm;
                re[i] += tRe;
                im[i] += tIm;
                
                const nextWRe = wRe * wFractionRe - wIm * wFractionIm;
                wIm = wRe * wFractionIm + wIm * wFractionRe;
                wRe = nextWRe;
            }
        }
    }
    if (!forward) {
        for (let i = 0; i < N; i++) {
            re[i] /= N;
            im[i] /= N;
        }
    }
}

function fft2D(re, im, logN, forward) {
    const N = 1 << logN;
    // Row FFTs
    for (let r = 0; r < N; r++) {
        const rowRe = new Float32Array(N);
        const rowIm = new Float32Array(N);
        const offset = r * N;
        for (let c = 0; c < N; c++) {
            rowRe[c] = re[offset + c];
            rowIm[c] = im[offset + c];
        }
        fft1D(rowRe, rowIm, logN, forward);
        for (let c = 0; c < N; c++) {
            re[offset + c] = rowRe[c];
            im[offset + c] = rowIm[c];
        }
    }
    // Col FFTs
    for (let c = 0; c < N; c++) {
        const colRe = new Float32Array(N);
        const colIm = new Float32Array(N);
        for (let r = 0; r < N; r++) {
            colRe[r] = re[r * N + c];
            colIm[r] = im[r * N + c];
        }
        fft1D(colRe, colIm, logN, forward);
        for (let r = 0; r < N; r++) {
            re[r * N + c] = colRe[r];
            im[r * N + c] = colIm[r];
        }
    }
}

// Shift low frequencies to the center
function fftShift(arr, N) {
    const half = N / 2;
    const result = new Float32Array(N * N);
    for (let r = 0; r < N; r++) {
        for (let c = 0; c < N; c++) {
            const nr = (r + half) % N;
            const nc = (c + half) % N;
            result[nr * N + nc] = arr[r * N + c];
        }
    }
    return result;
}

// Alpine JS Playground Application Definition
function playgroundApp() {
    return {
        hasImage: false,
        isProcessing: false,
        activeFilter: 'none',
        stegoMode: 'encode',
        stegoText: '',
        decodedText: '',
        downloadUrl: '#',
        fourierRadius: 40,
        fourierType: 'lowpass',
        originalImgWidth: 0,
        originalImgHeight: 0,

        // Buffers for Fast 2D FFT calculation (Fixed to 128x128 grid for real-time responsiveness)
        fftSize: 128,
        fftLogSize: 7, // 2^7 = 128
        fftRe: null,
        fftIm: null,

        init() {
            // Setup blank state
            this.resetImage();
        },

        handleDrop(e) {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.loadImageFile(files[0]);
            }
        },

        handleFileSelect(e) {
            const files = e.target.files;
            if (files.length > 0) {
                this.loadImageFile(files[0]);
            }
        },

        loadImageFile(file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                this.$refs.sourceImg.src = event.target.result;
                this.$refs.sourceImg.classList.remove('hidden');
            };
            reader.readAsDataURL(file);
        },

        onSourceImageLoad() {
            const img = this.$refs.sourceImg;
            this.originalImgWidth = img.naturalWidth;
            this.originalImgHeight = img.naturalHeight;

            // Render original on original source canvas
            const srcCanvas = this.$refs.sourceCanvas;
            srcCanvas.width = img.naturalWidth;
            srcCanvas.height = img.naturalHeight;
            const ctx = srcCanvas.getContext('2d');
            ctx.drawImage(img, 0, 0);

            // Set output size
            const outCanvas = this.$refs.outputCanvas;
            outCanvas.width = img.naturalWidth;
            outCanvas.height = img.naturalHeight;

            this.hasImage = true;
            this.activeFilter = 'none';
            this.isProcessing = false;
            this.stegoText = '';
            this.decodedText = '';

            // Compute the FFT buffers from the source image
            this.initFFTData();
            this.applyFilter('none');
        },

        resetImage() {
            this.hasImage = false;
            this.activeFilter = 'none';
            this.stegoText = '';
            this.decodedText = '';
            this.fftRe = null;
            this.fftIm = null;
            if (this.$refs.fileInput) this.$refs.fileInput.value = '';
            if (this.$refs.sourceImg) {
                this.$refs.sourceImg.src = '';
                this.$refs.sourceImg.classList.add('hidden');
            }
        },

        initFFTData() {
            // Draw thumbnail representation to calculate Fourier Spectrum
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = this.fftSize;
            tempCanvas.height = this.fftSize;
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.drawImage(this.$refs.sourceImg, 0, 0, this.fftSize, this.fftSize);

            const imgData = tempCtx.getImageData(0, 0, this.fftSize, this.fftSize);
            const data = imgData.data;

            const length = this.fftSize * this.fftSize;
            this.fftRe = new Float32Array(length);
            this.fftIm = new Float32Array(length);

            // Compute luminance for FFT frequency spectrum
            for (let i = 0; i < length; i++) {
                const r = data[i * 4];
                const g = data[i * 4 + 1];
                const b = data[i * 4 + 2];
                this.fftRe[i] = 0.299 * r + 0.587 * g + 0.114 * b;
                this.fftIm[i] = 0;
            }

            // Run forward 2D FFT
            fft2D(this.fftRe, this.fftIm, this.fftLogSize, true);
            this.updateFourier();
        },

        updateFourier() {
            if (!this.hasImage || !this.fftRe) return;

            const N = this.fftSize;
            const length = N * N;

            // Copy main FFT data
            const re = new Float32Array(this.fftRe);
            const im = new Float32Array(this.fftIm);

            // Apply lowpass/highpass filter mask in frequency domain
            const radiusSq = this.fourierRadius * this.fourierRadius;
            const half = N / 2;

            // Generate magnitudes for displaying the spectrum
            const magnitudes = new Float32Array(length);
            for (let r = 0; r < N; r++) {
                for (let c = 0; c < N; c++) {
                    const idx = r * N + c;
                    
                    // Center the indices to check filter boundaries
                    const cr = r < half ? r : r - N;
                    const cc = c < half ? c : c - N;
                    const distSq = cr * cr + cc * cc;

                    let keep = true;
                    if (this.fourierType === 'lowpass') {
                        if (distSq > radiusSq) keep = false;
                    } else if (this.fourierType === 'highpass') {
                        if (distSq <= radiusSq) keep = false;
                    }

                    if (!keep) {
                        re[idx] = 0;
                        im[idx] = 0;
                    }

                    // Log-scaled magnitude for visualization
                    const mag = Math.sqrt(re[idx] * re[idx] + im[idx] * im[idx]);
                    magnitudes[idx] = Math.log(1 + mag);
                }
            }

            // Render magnitude spectrum to fftCanvas
            const fftCanvas = this.$refs.fftCanvas;
            fftCanvas.width = N;
            fftCanvas.height = N;
            const fftCtx = fftCanvas.getContext('2d');
            const fftImgData = fftCtx.createImageData(N, N);

            const shiftedMags = fftShift(magnitudes, N);

            // Find max for scaling
            let maxMag = 0;
            for (let i = 0; i < length; i++) {
                if (shiftedMags[i] > maxMag) maxMag = shiftedMags[i];
            }
            if (maxMag === 0) maxMag = 1;

            for (let i = 0; i < length; i++) {
                const val = Math.min(255, Math.round((shiftedMags[i] / maxMag) * 255));
                const pixelIdx = i * 4;
                fftImgData.data[pixelIdx] = val;     // R
                fftImgData.data[pixelIdx + 1] = val; // G
                fftImgData.data[pixelIdx + 2] = val; // B
                fftImgData.data[pixelIdx + 3] = 255; // A
            }
            fftCtx.putImageData(fftImgData, 0, 0);

            // Draw filter radius circle overlay on FFT canvas
            fftCtx.beginPath();
            fftCtx.arc(half, half, this.fourierRadius * (N / this.fftSize), 0, 2 * Math.PI);
            fftCtx.strokeStyle = 'rgba(134, 39, 61, 0.7)';
            fftCtx.lineWidth = 1.5;
            fftCtx.stroke();

            // Run Inverse FFT to reconstruct filtered spatial domain image
            fft2D(re, im, this.fftLogSize, false);

            // Map inverse FFT result to output canvas if Active Filter is set to fourier
            if (this.activeFilter === 'fourier') {
                this.renderReconstructedImage(re);
            }
        },

        renderReconstructedImage(intensity) {
            const outCanvas = this.$refs.outputCanvas;
            const ctx = outCanvas.getContext('2d');
            ctx.drawImage(this.$refs.sourceImg, 0, 0);
            
            const imgData = ctx.getImageData(0, 0, outCanvas.width, outCanvas.height);
            const data = imgData.data;

            // Interpolate the 128x128 intensity buffer back to the original size
            const w = outCanvas.width;
            const h = outCanvas.height;
            const scaleX = this.fftSize / w;
            const scaleY = this.fftSize / h;

            for (let y = 0; y < h; y++) {
                const fftY = Math.min(this.fftSize - 1, Math.floor(y * scaleY));
                for (let x = 0; x < w; x++) {
                    const fftX = Math.min(this.fftSize - 1, Math.floor(x * scaleX));
                    const intensityVal = Math.max(0, Math.min(255, intensity[fftY * this.fftSize + fftX]));
                    
                    const idx = (y * w + x) * 4;
                    // Retain color but scale by luminance adjustment
                    data[idx] = intensityVal;
                    data[idx + 1] = intensityVal;
                    data[idx + 2] = intensityVal;
                }
            }
            ctx.putImageData(imgData, 0, 0);
            this.downloadUrl = outCanvas.toDataURL();
        },

        applyFilter(filterName) {
            if (!this.hasImage) return;

            this.isProcessing = true;
            this.activeFilter = filterName;

            // If fourier, let fourier logic handle output canvas rendering
            if (filterName === 'fourier') {
                this.isProcessing = false;
                this.updateFourier();
                return;
            }

            setTimeout(() => {
                const srcCanvas = this.$refs.sourceCanvas;
                const outCanvas = this.$refs.outputCanvas;
                const ctx = outCanvas.getContext('2d');
                ctx.drawImage(this.$refs.sourceImg, 0, 0);

                const imgData = ctx.getImageData(0, 0, outCanvas.width, outCanvas.height);
                const d = imgData.data;
                const w = outCanvas.width;
                const h = outCanvas.height;

                switch (filterName) {
                    case 'grayscale':
                        for (let i = 0; i < d.length; i += 4) {
                            const val = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
                            d[i] = d[i + 1] = d[i + 2] = val;
                        }
                        break;
                    case 'sepia':
                        for (let i = 0; i < d.length; i += 4) {
                            const r = d[i], g = d[i + 1], b = d[i + 2];
                            d[i] = Math.min(255, (r * 0.393) + (g * 0.769) + (b * 0.189));
                            d[i + 1] = Math.min(255, (r * 0.349) + (g * 0.686) + (b * 0.168));
                            d[i + 2] = Math.min(255, (r * 0.272) + (g * 0.534) + (b * 0.131));
                        }
                        break;
                    case 'invert':
                        for (let i = 0; i < d.length; i += 4) {
                            d[i] = 255 - d[i];
                            d[i + 1] = 255 - d[i + 1];
                            d[i + 2] = 255 - d[i + 2];
                        }
                        break;
                    case 'vignette':
                        const cx = w / 2;
                        const cy = h / 2;
                        const maxDist = Math.sqrt(cx * cx + cy * cy);
                        for (let y = 0; y < h; y++) {
                            for (let x = 0; x < w; x++) {
                                const idx = (y * w + x) * 4;
                                const dist = Math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
                                const factor = Math.max(0, 1 - (dist / maxDist) * 0.7);
                                d[idx] *= factor;
                                d[idx + 1] *= factor;
                                d[idx + 2] *= factor;
                            }
                        }
                        break;
                    case 'pixelate':
                        const size = 16;
                        for (let y = 0; y < h; y += size) {
                            for (let x = 0; x < w; x += size) {
                                // Average color of block
                                let rTotal = 0, gTotal = 0, bTotal = 0, count = 0;
                                for (let dy = 0; dy < size && y + dy < h; dy++) {
                                    for (let dx = 0; dx < size && x + dx < w; dx++) {
                                        const idx = ((y + dy) * w + (x + dx)) * 4;
                                        rTotal += d[idx];
                                        gTotal += d[idx + 1];
                                        bTotal += d[idx + 2];
                                        count++;
                                    }
                                }
                                const rAvg = rTotal / count;
                                const gAvg = gTotal / count;
                                const bAvg = bTotal / count;
                                // Write back avg color
                                for (let dy = 0; dy < size && y + dy < h; dy++) {
                                    for (let dx = 0; dx < size && x + dx < w; dx++) {
                                        const idx = ((y + dy) * w + (x + dx)) * 4;
                                        d[idx] = rAvg;
                                        d[idx + 1] = gAvg;
                                        d[idx + 2] = bAvg;
                                    }
                                }
                            }
                        }
                        break;
                    case 'emboss':
                        const copy = new Uint8ClampedArray(d);
                        for (let y = 1; y < h - 1; y++) {
                            for (let x = 1; x < w - 1; x++) {
                                const idx = (y * w + x) * 4;
                                const idxAboveLeft = ((y - 1) * w + (x - 1)) * 4;
                                const idxBelowRight = ((y + 1) * w + (x + 1)) * 4;
                                
                                for (let c = 0; c < 3; c++) {
                                    const diff = copy[idxAboveLeft + c] - copy[idxBelowRight + c];
                                    d[idx + c] = Math.max(0, Math.min(255, 128 + diff));
                                }
                            }
                        }
                        break;
                    case 'circle':
                        const radius = Math.min(w, h) / 2;
                        const centerX = w / 2;
                        const centerY = h / 2;
                        for (let y = 0; y < h; y++) {
                            for (let x = 0; x < w; x++) {
                                const idx = (y * w + x) * 4;
                                const dist = Math.sqrt((x - centerX) * (x - centerX) + (y - centerY) * (y - centerY));
                                if (dist > radius) {
                                    d[idx + 3] = 0; // Alpha channel transparent
                                }
                            }
                        }
                        break;
                }

                ctx.putImageData(imgData, 0, 0);
                this.downloadUrl = outCanvas.toDataURL();
                this.isProcessing = false;
            }, 100);
        },

        // LSB Steganography Implementation
        encodeMessage() {
            if (!this.hasImage || !this.stegoText) return;

            this.isProcessing = true;
            this.activeFilter = 'stego-encoded';

            setTimeout(() => {
                const outCanvas = this.$refs.outputCanvas;
                const ctx = outCanvas.getContext('2d');
                ctx.drawImage(this.$refs.sourceImg, 0, 0);

                const imgData = ctx.getImageData(0, 0, outCanvas.width, outCanvas.height);
                const d = imgData.data;

                // Create bytes payload: [Magic Prefix 'RVD', 4 bytes length, UTF-8 text bytes]
                const textEncoder = new TextEncoder();
                const textBytes = textEncoder.encode(this.stegoText);
                const prefix = [82, 86, 68]; // 'RVD'
                
                const payload = new Uint8Array(prefix.length + 4 + textBytes.length);
                payload.set(prefix, 0);
                
                // Set length (4 bytes big-endian)
                const len = textBytes.length;
                payload[3] = (len >> 24) & 0xff;
                payload[4] = (len >> 16) & 0xff;
                payload[5] = (len >> 8) & 0xff;
                payload[6] = len & 0xff;
                payload.set(textBytes, 7);

                // Convert payload to bit list
                const bits = [];
                for (let i = 0; i < payload.length; i++) {
                    const byte = payload[i];
                    for (let bitIdx = 7; bitIdx >= 0; bitIdx--) {
                        bits.push((byte >> bitIdx) & 1);
                    }
                }

                // Check capacity
                if (bits.length > d.length / 4) {
                    alert('Image too small to hide this message!');
                    this.isProcessing = false;
                    return;
                }

                // Inject bits into Red Channel LSB
                for (let i = 0; i < bits.length; i++) {
                    const pixelIdx = i * 4; // R channel
                    d[pixelIdx] = (d[pixelIdx] & ~1) | bits[i];
                }

                ctx.putImageData(imgData, 0, 0);
                this.downloadUrl = outCanvas.toDataURL();
                this.isProcessing = false;
                alert('Secret message hidden successfully! Download your output image.');
            }, 100);
        },

        decodeMessage() {
            if (!this.hasImage) return;

            const outCanvas = this.$refs.outputCanvas;
            const ctx = outCanvas.getContext('2d');
            
            // To ensure we decode from current state of output canvas (where user might have loaded stego img)
            const imgData = ctx.getImageData(0, 0, outCanvas.width, outCanvas.height);
            const d = imgData.data;

            // Extract bits from Red LSB
            const bits = [];
            const bitLimit = Math.min(d.length / 4, 300000); // safety cap
            for (let i = 0; i < bitLimit; i++) {
                const pixelIdx = i * 4;
                bits.push(d[pixelIdx] & 1);
            }

            // Convert bits to bytes helper
            function bitsToBytes(bitArray) {
                const bytes = new Uint8Array(Math.floor(bitArray.length / 8));
                for (let i = 0; i < bytes.length; i++) {
                    let byte = 0;
                    for (let bitIdx = 0; bitIdx < 8; bitIdx++) {
                        byte = (byte << 1) | bitArray[i * 8 + bitIdx];
                    }
                    bytes[i] = byte;
                }
                return bytes;
            }

            const extractedBytes = bitsToBytes(bits);

            // Verify Magic Signature 'RVD'
            if (extractedBytes[0] !== 82 || extractedBytes[1] !== 86 || extractedBytes[2] !== 68) {
                this.decodedText = 'No hidden message or invalid steganographic image.';
                return;
            }

            // Parse length
            const len = (extractedBytes[3] << 24) | (extractedBytes[4] << 16) | (extractedBytes[5] << 8) | extractedBytes[6];
            if (len <= 0 || len > extractedBytes.length - 7) {
                this.decodedText = 'Invalid steganography payload metadata.';
                return;
            }

            // Decode UTF-8 string
            const textBytes = extractedBytes.slice(7, 7 + len);
            const textDecoder = new TextDecoder();
            try {
                this.decodedText = textDecoder.decode(textBytes);
            } catch (e) {
                this.decodedText = 'Failed to decode secret message.';
            }
        }
    };
}
