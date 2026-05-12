import discord
import cv2
import numpy as np
import aiohttp
import matplotlib.pyplot as plt
import os
import io
from discord.ext import commands
from discord import app_commands
from scripts.main import check_blacklist, has_pfp, smart_title_case
from scripts.search import search_images
from scripts.image_processing import (
    Image_Ops, Convolution, Histogram, Equalization, 
    Enhancement, Specialization, Edge_Detection, 
    Morphology, gpu_available, gpu_info, _GPU_NAME
)

class ImageLookupView(discord.ui.View):
    """
    View for paginated image search results.
    """
    def __init__(self, query: str, results: list, author_id: int):
        super().__init__(timeout=60)
        self.query = query
        self.results = results
        self.author_id = author_id
        self.current_index = 0

    def create_embed(self):
        data = self.results[self.current_index]
        # Use smart_title_case for the query as the main title
        title = smart_title_case(self.query)
        
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_image(url=data['image'])
        
        # Truncate source title if it's too long
        source_title = data.get('title', 'Gambar')
        if len(source_title) > 60:
            source_title = source_title[:57] + "..."
            
        embed.set_footer(text=f"Hasil {self.current_index + 1}/{len(self.results)} | Sumber: {source_title}")
        return embed

    @discord.ui.button(label="Sebelumnya", style=discord.ButtonStyle.gray, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Hey! Ini bukan sesi pencarianmu!", ephemeral=True)
        
        self.current_index = (self.current_index - 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Selanjutnya", style=discord.ButtonStyle.gray, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Hey! Ini bukan sesi pencarianmu!", ephemeral=True)
        
        self.current_index = (self.current_index + 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

class Image(commands.Cog):
    """
    Kumpulan command untuk memproses gambar dan avatar.
    """
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    async def _get_image_bytes(self, ctx, user: discord.User = None, attachment: discord.Attachment = None) -> bytes:
        """Helper to get image bytes from attachment, user avatar, or author avatar."""
        if attachment:
            if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                raise ValueError("Lampiran harus berupa gambar (png, jpg, jpeg, webp)!")
            return await attachment.read()
        
        target = user or ctx.author
        if target.avatar is None:
            raise ValueError(f"{target.display_name} tidak memiliki foto profil!")
        
        return await target.display_avatar.with_format("png").read()

    async def _generate_histogram_plot(self, img_rgb, title="Histogram"):
        """Generate a histogram plot using matplotlib and return bytes."""
        plt.figure(figsize=(7, 4))
        if img_rgb.ndim == 2:
            plt.hist(img_rgb.ravel(), bins=256, range=(0, 256), color="black", alpha=0.7)
        else:
            colors = ("r", "g", "b")
            for i, col in enumerate(colors):
                hist = cv2.calcHist([img_rgb], [i], None, [256], [0, 256])
                plt.plot(hist, color=col)
                plt.xlim([0, 256])
        
        plt.title(title)
        plt.xlabel("Pixel Value")
        plt.ylabel("Frequency")
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        return buf

    async def _generate_comparison_plot(self, img1_rgb, img2_rgb, title1="Gambar 1", title2="Gambar 2"):
        """Generate a side-by-side histogram comparison plot and return bytes."""
        plt.figure(figsize=(12, 5))
        
        # Helper to plot a single histogram on a specific subplot
        def plot_hist(img, title, pos):
            plt.subplot(1, 2, pos)
            if img.ndim == 2:
                plt.hist(img.ravel(), bins=256, range=(0, 256), color="black", alpha=0.7)
            else:
                colors = ("r", "g", "b")
                for i, col in enumerate(colors):
                    hist = cv2.calcHist([img], [i], None, [256], [0, 256])
                    plt.plot(hist, color=col)
                    plt.xlim([0, 256])
            plt.title(title)
            plt.xlabel("Pixel Value")
            plt.ylabel("Frequency")

        plot_hist(img1_rgb, title1, 1)
        plot_hist(img2_rgb, title2, 2)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        return buf

    async def _process_and_reply(self, ctx, image_bytes: bytes, filename: str, process_func, *args, **kwargs):
        """Helper to process image and reply to context."""
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return await ctx.reply("Gagal membaca gambar. Pastikan formatnya benar!")

            # Convert BGR (OpenCV default) to RGB for Image_Ops
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Process
            result = process_func(img_rgb, *args, **kwargs)

            # Convert back to BGR for saving
            if result.ndim == 3:
                # If color, check channel count
                if result.shape[2] == 3:
                    result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
                else:
                    # Just pick first 3 if more, or duplicate if less (handled by image_processing usually)
                    result_bgr = result[..., :3]
            else:
                result_bgr = result

            # Encode to bytes
            _, buffer = cv2.imencode('.png', result_bgr)
            io_buf = io.BytesIO(buffer)

            await ctx.reply(file=discord.File(io_buf, filename))

        except Exception as e:
            await ctx.reply(f"Terjadi kesalahan saat memproses gambar: `{str(e)}`")

    @commands.hybrid_group(name='image')
    @check_blacklist()
    async def image_group(self, ctx: commands.Context):
        """
        Kumpulan command untuk memproses gambar. [GROUP]
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @image_group.command(description="Lihat status akselerasi GPU.")
    @check_blacklist()
    async def gpu(self, ctx: commands.Context):
        """Lihat status akselerasi GPU."""
        status = "Aktif 🚀" if gpu_available() else "Nonaktif 💤"
        device = _GPU_NAME or "N/A"
        embed = discord.Embed(title="Status GPU", color=discord.Color.blue())
        embed.add_field(name="Akselerasi", value=status, inline=True)
        embed.add_field(name="Device", value=device, inline=True)
        embed.set_footer(text="Menggunakan CuPy untuk pengolahan array skala besar.")
        await ctx.reply(embed=embed)
        
    @image_group.command(name="lookup", description="Cari gambar di internet dengan navigasi hasil.")
    @app_commands.describe(query="Query pencarian gambar")
    @check_blacklist()
    async def lookup(self, ctx: commands.Context, query: str):
        """Cari gambar di internet dan tampilkan hasilnya dengan navigasi."""
        async with ctx.typing():
            try:
                # Fetch up to 10 results for pagination
                results = await search_images(query, max_results=10)
                if not results:
                    return await ctx.reply("Waduh! Tidak ada gambar yang ditemukan untuk query tersebut.")
                
                view = ImageLookupView(query, results, ctx.author.id)
                await ctx.reply(embed=view.create_embed(), view=view)
                
            except Exception as e:
                await ctx.reply(f"Terjadi kesalahan saat mencari gambar: `{str(e)}`")

    @image_group.command(description="Ubah gambar menjadi hitam putih (grayscale).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def grayscale(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "grayscale.png", Image_Ops.to_grayscale)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Balikkan warna gambar (invert).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def invert(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "invert.png", Image_Ops.invert)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Crop gambar menjadi lingkaran.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def circle(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "circle.png", Image_Ops.crop_circle)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Buramkan gambar (blur).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", strength="Kekuatan blur (default: 5)")
    @check_blacklist()
    async def blur(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None, strength: int = 5):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                # Use box blur kernel
                def apply_blur(img, n):
                    kernel = Convolution.Kernels.box_blur(n)
                    return Convolution.apply(img, kernel)
                await self._process_and_reply(ctx, bytes_data, "blur.png", apply_blur, strength)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Tajamkan gambar (sharpen).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def sharpen(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_sharpen(img):
                    kernel = Convolution.Kernels.sharpen()
                    return Convolution.apply(img, kernel)
                await self._process_and_reply(ctx, bytes_data, "sharpen.png", apply_sharpen)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Balikkan gambar secara horizontal atau vertikal.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", axis="Sumbu balik (horizontal/vertical)")
    @check_blacklist()
    async def flip(self, ctx: commands.Context, axis: str = "horizontal", user: discord.User = None, attachment: discord.Attachment = None):
        if axis not in ["horizontal", "vertical"]:
            return await ctx.reply("Axis harus 'horizontal' atau 'vertical'!")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "flip.png", Image_Ops.flip, axis)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Putar gambar.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", angle="Sudut putar (derajat)", direction="Arah putar (ccw/cw)")
    @check_blacklist()
    async def rotate(self, ctx: commands.Context, angle: float, direction: str = "ccw", user: discord.User = None, attachment: discord.Attachment = None):
        if direction not in ["ccw", "cw"]:
            return await ctx.reply("Direction harus 'ccw' atau 'cw'!")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "rotate.png", Image_Ops.rotate, angle, direction)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Sesuaikan kecerahan dan kontras gambar.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", brightness="Faktor kecerahan (1.0 = normal)", contrast="Faktor kontras (0 = normal)")
    @check_blacklist()
    async def adjust(self, ctx: commands.Context, brightness: float = 1.0, contrast: int = 0, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "adjust.png", Enhancement.brightness_contrast, brightness, contrast)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Deteksi tepi pada gambar (edge detection).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", method="Metode deteksi (canny/sobel/laplacian/prewitt/roberts/scharr)")
    @check_blacklist()
    async def edge(self, ctx: commands.Context, method: str = "canny", user: discord.User = None, attachment: discord.Attachment = None):
        methods = {
            "canny": Edge_Detection.canny,
            "sobel": Edge_Detection.sobel,
            "laplacian": Edge_Detection.laplacian,
            "prewitt": Edge_Detection.prewitt,
            "roberts": Edge_Detection.roberts,
            "scharr": Edge_Detection.scharr
        }
        if method not in methods:
            return await ctx.reply(f"Metode tidak valid! Pilihan: {', '.join(methods.keys())}")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, f"{method}.png", methods[method])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Tambahkan noise pada gambar.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", type="Tipe noise (salt_pepper/gaussian/poisson)")
    @check_blacklist()
    async def noise(self, ctx: commands.Context, type: str = "salt_pepper", user: discord.User = None, attachment: discord.Attachment = None):
        types = {
            "salt_pepper": Image_Ops.add_salt_pepper,
            "gaussian": Enhancement.add_gaussian_noise,
            "poisson": Enhancement.add_poisson_noise
        }
        if type not in types:
            return await ctx.reply(f"Tipe noise tidak valid! Pilihan: {', '.join(types.keys())}")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "noise.png", types[type])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Normalisasi histogram gambar (equalize).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", method="Metode (global/clahe/adaptive)")
    @check_blacklist()
    async def equalize(self, ctx: commands.Context, method: str = "global", user: discord.User = None, attachment: discord.Attachment = None):
        methods = {
            "global": Equalization.equalize,
            "clahe": Equalization.clahe,
            "adaptive": Equalization.adaptive
        }
        if method not in methods:
            return await ctx.reply(f"Metode tidak valid! Pilihan: {', '.join(methods.keys())}")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "equalize.png", methods[method])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan efek emboss.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def emboss(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_emboss(img):
                    return Convolution.apply(img, Convolution.Kernels.emboss())
                await self._process_and_reply(ctx, bytes_data, "emboss.png", apply_emboss)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan filter sepia.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def sepia(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_sepia(img):
                    img_f = img.astype(np.float32)
                    sepia_matrix = np.array([[0.393, 0.769, 0.189],
                                             [0.349, 0.686, 0.168],
                                             [0.272, 0.534, 0.131]])
                    # OpenCV uses BGR, but we converted to RGB in _process_and_reply
                    # So we apply matrix to RGB
                    sepia_img = cv2.transform(img_f, sepia_matrix)
                    return np.clip(sepia_img, 0, 255).astype(np.uint8)
                await self._process_and_reply(ctx, bytes_data, "sepia.png", apply_sepia)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan efek pixelate.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", pixel_size="Ukuran pixel (default: 16)")
    @check_blacklist()
    async def pixelate(self, ctx: commands.Context, pixel_size: int = 16, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_pixelate(img, size):
                    h, w = img.shape[:2]
                    # Downsample
                    small = cv2.resize(img, (w // size, h // size), interpolation=cv2.INTER_LINEAR)
                    # Upsample
                    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                await self._process_and_reply(ctx, bytes_data, "pixelate.png", apply_pixelate, pixel_size)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan efek vignette.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", sigma="Ukuran vignette (default: 150)")
    @check_blacklist()
    async def vignette(self, ctx: commands.Context, sigma: int = 150, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_vignette(img, s):
                    h, w = img.shape[:2]
                    kernel_x = cv2.getGaussianKernel(w, s)
                    kernel_y = cv2.getGaussianKernel(h, s)
                    kernel = kernel_y * kernel_x.T
                    mask = kernel / kernel.max()
                    vignette_img = np.copy(img)
                    for i in range(3):
                        vignette_img[:, :, i] = vignette_img[:, :, i] * mask
                    return vignette_img.astype(np.uint8)
                await self._process_and_reply(ctx, bytes_data, "vignette.png", apply_vignette, sigma)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan gamma correction.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", gamma="Nilai gamma (default: 1.5)")
    @check_blacklist()
    async def gamma(self, ctx: commands.Context, gamma: float = 1.5, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "gamma.png", Enhancement.gamma_correction, gamma)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Terapkan log transform.")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def log(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "log.png", Enhancement.log_transform)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Gabungkan dua gambar (blend).")
    @app_commands.describe(user1="User pertama", user2="User kedua", attachment1="Gambar pertama", attachment2="Gambar kedua", alpha="Transparansi (0.0 - 1.0)")
    @check_blacklist()
    async def blend(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, alpha: float = 0.5):
        async with ctx.typing():
            try:
                # Determine image 1
                if attachment1:
                    img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine image 2
                if attachment2:
                    img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(f"{user2.display_name} tidak memiliki avatar!")
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else:
                    raise ValueError("Harus memberikan gambar kedua (user2 atau attachment2)!")

                # Load images
                img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
                img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
                
                img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
                img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

                # Blend
                result = Image_Ops.blend(img1_rgb, img2_rgb, alpha=alpha)

                # Save
                result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode('.png', result_bgr)
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "blend.png"))

            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @commands.hybrid_group(name='histogram')
    @check_blacklist()
    async def histogram_group(self, ctx: commands.Context):
        """Kumpulan command untuk analisis histogram."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @histogram_group.command(name="show", description="Tampilkan histogram gambar.")
    @app_commands.describe(user="User yang avatar-nya ingin dilihat histogram-nya", attachment="Gambar yang ingin dilihat histogram-nya")
    @check_blacklist()
    async def histogram_show(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                plot_buf = await self._generate_histogram_plot(img_rgb, title=f"Histogram {user.display_name if user else ctx.author.display_name}")
                await ctx.reply(file=discord.File(plot_buf, "histogram.png"))
            except ValueError as e:
                await ctx.reply(str(e))

    @histogram_group.command(name="match", description="Samakan histogram antara dua gambar (match).")
    @app_commands.describe(user1="User pertama", user2="User kedua", attachment1="Gambar pertama", attachment2="Gambar kedua")
    @check_blacklist()
    async def match(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None):
        async with ctx.typing():
            try:
                # Determine image 1
                if attachment1:
                    img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine image 2 (Reference)
                if attachment2:
                    img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(f"{user2.display_name} tidak memiliki avatar!")
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else:
                    raise ValueError("Harus memberikan gambar referensi (user2 atau attachment2)!")

                img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
                img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
                
                img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
                img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

                # Match
                result = Specialization.match(img1_rgb, img2_rgb)

                # Save
                result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode('.png', result_bgr)
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "matched.png"))

            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @histogram_group.command(name="transfer", description="Transfer warna dari satu gambar ke gambar lain.")
    @app_commands.describe(source_user="User sumber warna", ref_user="User referensi warna", source_attachment="Gambar sumber warna", ref_attachment="Gambar referensi warna")
    @check_blacklist()
    async def transfer(self, ctx: commands.Context, source_user: discord.User = None, ref_user: discord.User = None, source_attachment: discord.Attachment = None, ref_attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                # Determine source image
                if source_attachment:
                    img1_bytes = await source_attachment.read()
                else:
                    target1 = source_user or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine reference image
                if ref_attachment:
                    img2_bytes = await ref_attachment.read()
                elif ref_user:
                    if ref_user.avatar is None: raise ValueError(f"{ref_user.display_name} tidak memiliki avatar!")
                    img2_bytes = await ref_user.display_avatar.with_format("png").read()
                else:
                    raise ValueError("Harus memberikan gambar referensi warna (ref_user atau ref_attachment)!")

                img1 = cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR)
                img2 = cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR)
                
                img1_rgb = cv2.cvtColor(img1, cv2.COLOR_BGR2RGB)
                img2_rgb = cv2.cvtColor(img2, cv2.COLOR_BGR2RGB)

                # Transfer
                result = Specialization.transfer_color(img1_rgb, img2_rgb)

                # Save
                result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode('.png', result_bgr)
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "transferred.png"))

            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @image_group.command(description="Binarisasi gambar (threshold).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", threshold_value="Nilai threshold (0-255)", method="Metode (binary/otsu)")
    @check_blacklist()
    async def threshold(self, ctx: commands.Context, threshold_value: int = 127, method: str = "binary", user: discord.User = None, attachment: discord.Attachment = None):
        if method not in ["binary", "otsu"]:
            return await ctx.reply("Metode harus 'binary' atau 'otsu'!")
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                use_otsu = (method == "otsu")
                await self._process_and_reply(ctx, bytes_data, "threshold.png", Image_Ops.threshold, threshold_value, use_otsu)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Potong border hitam/putih otomatis (autocrop).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", tolerance="Toleransi warna (default: 0)")
    @check_blacklist()
    async def autocrop(self, ctx: commands.Context, tolerance: int = 0, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "autocrop.png", Image_Ops.autocrop, tolerance)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Gabungkan dua gambar dengan mode masking (composite).")
    @app_commands.describe(user1="User pertama", user2="User kedua", attachment1="Gambar pertama (background)", attachment2="Gambar kedua (overlay)", mode="Mode blend (normal/add/multiply/screen/overlay)", match_mode="Mode penyesuaian ukuran (resize/crop/pad)")
    @check_blacklist()
    async def composite(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, mode: str = "normal", match_mode: str = "resize"):
        modes = ["normal", "add", "multiply", "screen", "overlay"]
        match_modes = ["resize", "crop", "pad"]
        if mode not in modes: return await ctx.reply(f"Mode tidak valid! Pilihan: {', '.join(modes)}")
        if match_mode not in match_modes: return await ctx.reply(f"Match mode tidak valid! Pilihan: {', '.join(match_modes)}")
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(f"{user2.display_name} tidak memiliki avatar!")
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError("Harus memberikan gambar kedua (user2 atau attachment2)!")

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                result = Image_Ops.composite(img1, img2, mode=mode, match_mode=match_mode)
                _, buffer = cv2.imencode('.png', cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "composite.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @image_group.command(description="Gabungkan dua gambar secara bersebelahan (concat).")
    @app_commands.describe(user1="User pertama", user2="User kedua", attachment1="Gambar kiri/atas", attachment2="Gambar kanan/bawah", axis="Sumbu gabung (horizontal/vertical)")
    @check_blacklist()
    async def concat(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, axis: str = "horizontal"):
        if axis not in ["horizontal", "vertical"]: return await ctx.reply("Axis harus 'horizontal' atau 'vertical'!")
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(f"{user2.display_name} tidak memiliki avatar!")
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError("Harus memberikan gambar kedua (user2 atau attachment2)!")

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                result = Image_Ops.concat(img1, img2, axis=axis)
                _, buffer = cv2.imencode('.png', cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "concat.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @commands.hybrid_group(name='morph')
    @check_blacklist()
    async def morph_group(self, ctx: commands.Context):
        """Kumpulan command untuk operasi morfologi gambar."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @morph_group.command(description="Erosi gambar (menguruskan fitur).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", iterations="Jumlah iterasi (default: 1)", kernel_size="Ukuran kernel (default: 3)")
    @check_blacklist()
    async def erode(self, ctx: commands.Context, iterations: int = 1, kernel_size: int = 3, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "erode.png", Morphology.erode, kernel_size, iterations)
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @morph_group.command(description="Dilasi gambar (menebalkan fitur).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit", iterations="Jumlah iterasi (default: 1)", kernel_size="Ukuran kernel (default: 3)")
    @check_blacklist()
    async def dilate(self, ctx: commands.Context, iterations: int = 1, kernel_size: int = 3, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "dilate.png", Morphology.dilate, kernel_size, iterations)
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @morph_group.command(description="Ekstrak skeleton/kerangka gambar (hanya untuk grayscale/binary).")
    @app_commands.describe(user="User yang avatar-nya ingin diedit", attachment="Gambar yang ingin diedit")
    @check_blacklist()
    async def skeleton(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                def apply_skeleton(img):
                    # Skeleton requires binary image, so we convert it first
                    if img.ndim == 3:
                        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    else:
                        gray = img
                    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    # Use morphological skeleton
                    skel = Morphology.skeleton(binary)
                    # Convert back to RGB format for saving
                    return cv2.cvtColor(skel, cv2.COLOR_GRAY2RGB)
                await self._process_and_reply(ctx, bytes_data, "skeleton.png", apply_skeleton)
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @histogram_group.command(name="compare", description="Bandingkan dua gambar menggunakan histogram.")
    @app_commands.describe(user1="User pertama", user2="User kedua", attachment1="Gambar pertama", attachment2="Gambar kedua", method="Metode perbandingan (correl/chisqr/intersect/bhattacharyya)")
    @check_blacklist()
    async def hist_compare(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, method: str = "correl"):
        methods = ["correl", "chisqr", "intersect", "bhattacharyya"]
        if method not in methods: return await ctx.reply(f"Metode tidak valid! Pilihan: {', '.join(methods)}")
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(f"{target1.display_name} tidak memiliki avatar!")
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(f"{user2.display_name} tidak memiliki avatar!")
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError("Harus memberikan gambar referensi (user2 atau attachment2)!")

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                score = Histogram.match_score(img1, img2, method=method)
                
                # Generate visual comparison plot
                name1 = user1.display_name if user1 else "Gambar 1"
                name2 = user2.display_name if user2 else "Gambar 2"
                plot_buf = await self._generate_comparison_plot(img1, img2, title1=f"Histogram {name1}", title2=f"Histogram {name2}")

                embed = discord.Embed(title="Perbandingan Histogram", color=discord.Color.green())
                embed.add_field(name="Metode", value=method.upper(), inline=True)
                embed.add_field(name="Skor Kecocokan", value=f"`{score:.4f}`", inline=True)
                embed.set_image(url="attachment://comparison.png")
                
                await ctx.reply(embed=embed, file=discord.File(plot_buf, "comparison.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

    @histogram_group.command(name="cdf", description="Tampilkan grafik CDF (Cumulative Distribution Function).")
    @app_commands.describe(user="User yang avatar-nya ingin dilihat", attachment="Gambar yang ingin dilihat")
    @check_blacklist()
    async def hist_cdf(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                plt.figure(figsize=(10, 5))
                plt.title(f"CDF Histogram - {user.display_name if user else ctx.author.display_name}")
                colors = ('r', 'g', 'b')
                for i, color in enumerate(colors):
                    hist, bins = np.histogram(img_rgb[:, :, i].flatten(), 256, [0, 256])
                    cdf = hist.cumsum()
                    cdf_normalized = cdf * float(hist.max()) / cdf.max()
                    plt.plot(cdf_normalized, color=color, linestyle='dashed')
                plt.xlim([0, 256])
                plt.xlabel("Pixel Value")
                plt.ylabel("Cumulative Frequency")
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                plt.close()
                buf.seek(0)
                await ctx.reply(file=discord.File(buf, "cdf.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(f"Terjadi kesalahan: `{str(e)}`")

async def setup(bot: commands.Bot):
    await bot.add_cog(Image(bot))
