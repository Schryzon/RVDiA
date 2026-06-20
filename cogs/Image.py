import discord
import cv2
import numpy as np
import aiohttp
import matplotlib.pyplot as plt
import os
import io
from discord.ext import commands
from discord import app_commands
from scripts.main import db, check_blacklist, has_pfp, smart_title_case
from scripts.utils.search import search_images
from scripts.image.processing import (
    Image_Ops, Convolution, Histogram, Equalization, 
    Enhancement, Specialization, Edge_Detection, 
    Morphology, gpu_available, gpu_info, _GPU_NAME,
    Wavelet, Stego, FreqFilter
)
from scripts.utils.i18n import i18n

class ImageSearchView(discord.ui.View):
    """
    View for paginated image search results.
    """
    def __init__(self, query: str, results: list, author_id: int, lang: str = "en"):
        super().__init__(timeout=60)
        self.query = query
        self.results = results
        self.author_id = author_id
        self.current_index = 0
        self.lang = lang
        self.prev_button.label = i18n.get(lang, "general.prev_page")
        self.next_button.label = i18n.get(lang, "general.next_page")

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
            
        footer_text = i18n.get(self.lang, "image.search_footer", current=self.current_index + 1, total=len(self.results), source=source_title)
        embed.set_footer(text=footer_text)
        return embed

    @discord.ui.button(style=discord.ButtonStyle.gray, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            msg = i18n.get(self.lang, "general.search_not_yours")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        self.current_index = (self.current_index - 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(style=discord.ButtonStyle.gray, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            msg = i18n.get(self.lang, "general.search_not_yours")
            return await interaction.response.send_message(msg, ephemeral=True)
        
        self.current_index = (self.current_index + 1) % len(self.results)
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

class Image(commands.Cog):
    """
    A collection of commands for image and avatar processing.
    """
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    async def _get_image_bytes(self, ctx, user: discord.User = None, attachment: discord.Attachment = None) -> bytes:
        """Helper to get image bytes from attachment, user avatar, or author avatar."""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if attachment:
            if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                raise ValueError(i18n.get(lang, "image.invalid_format"))
            return await attachment.read()
        
        target = user or ctx.author
        if target.avatar is None:
            raise ValueError(i18n.get(lang, "image.no_avatar", user=target.display_name))
        
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
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return await ctx.reply(i18n.get(lang, "image.read_failed"))

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
            await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @commands.hybrid_group(name='image')
    @check_blacklist()
    async def image_group(self, ctx: commands.Context):
        """
        A collection of commands for image processing.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @image_group.command(description="Check GPU acceleration status.")
    @check_blacklist()
    async def gpu(self, ctx: commands.Context):
        """Check GPU acceleration status."""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        status = i18n.get(lang, "image.gpu_active") if gpu_available() else i18n.get(lang, "image.gpu_inactive")
        device = _GPU_NAME or "N/A"
        embed = discord.Embed(title=i18n.get(lang, "image.gpu_title"), color=discord.Color.blue())
        embed.add_field(name="Akselerasi", value=status, inline=True)
        embed.add_field(name="Device", value=device, inline=True)
        embed.set_footer(text=i18n.get(lang, "image.gpu_footer"))
        await ctx.reply(embed=embed)
        
    @image_group.command(name="search", description="Search images on the web with result pagination.")
    @app_commands.describe(query="The keyword to search for.")
    @check_blacklist()
    async def search(self, ctx: commands.Context, query: str):
        """Search images on the web and view results with pagination."""
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                # Enable NSFW results only if the channel is NSFW
                is_nsfw = False
                channel = ctx.channel
                if ctx.guild and not hasattr(channel, 'is_nsfw'):
                    cached_channel = ctx.guild.get_channel(channel.id)
                    if cached_channel:
                        channel = cached_channel
                
                if hasattr(channel, 'is_nsfw') and callable(channel.is_nsfw):
                    is_nsfw = channel.is_nsfw()
                elif hasattr(channel, 'nsfw'):
                    is_nsfw = bool(channel.nsfw)
                safesearch = 'off' if is_nsfw else 'on'
                
                # Fetch up to 10 results for pagination
                results = await search_images(query, max_results=10, safesearch=safesearch)
                if not results:
                    return await ctx.reply(i18n.get(lang, "image.search_no_results"))
                
                view = ImageSearchView(query, results, ctx.author.id, lang=lang)
                await ctx.reply(embed=view.create_embed(), view=view)
                
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.search_error", error=str(e)))

    @image_group.command(description="Convert image to grayscale (black and white).")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
    @check_blacklist()
    async def grayscale(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "grayscale.png", Image_Ops.to_grayscale)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Invert image colors.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
    @check_blacklist()
    async def invert(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "invert.png", Image_Ops.invert)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Crop image into a circular shape.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
    @check_blacklist()
    async def circle(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "circle.png", Image_Ops.crop_circle)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Apply a blur filter to the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", strength="Blur strength kernel size (default: 5)")
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

    @image_group.command(description="Sharpen details in the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
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

    @image_group.command(description="Flip the image horizontally or vertically.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", axis="Horizontal or vertical flip direction")
    @check_blacklist()
    async def flip(self, ctx: commands.Context, axis: str = "horizontal", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if axis not in ["horizontal", "vertical"]:
            return await ctx.reply(i18n.get(lang, "image.flip_axis_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "flip.png", Image_Ops.flip, axis)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Rotate the image by a specific angle.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", angle="Rotation angle in degrees", direction="Clockwise (cw) or counter-clockwise (ccw) direction")
    @check_blacklist()
    async def rotate(self, ctx: commands.Context, angle: float, direction: str = "ccw", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if direction not in ["ccw", "cw"]:
            return await ctx.reply(i18n.get(lang, "image.rotate_dir_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "rotate.png", Image_Ops.rotate, angle, direction)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Adjust brightness and contrast of the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", brightness="Brightness multiplier factor (1.0 = normal)", contrast="Contrast factor adjustment (0 = normal)")
    @check_blacklist()
    async def adjust(self, ctx: commands.Context, brightness: float = 1.0, contrast: int = 0, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "adjust.png", Enhancement.brightness_contrast, brightness, contrast)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Perform edge detection filters.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", method="Edge detection operator (canny/sobel/laplacian/prewitt/roberts/scharr)")
    @check_blacklist()
    async def edge(self, ctx: commands.Context, method: str = "canny", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        methods = {
            "canny": Edge_Detection.canny,
            "sobel": Edge_Detection.sobel,
            "laplacian": Edge_Detection.laplacian,
            "prewitt": Edge_Detection.prewitt,
            "roberts": Edge_Detection.roberts,
            "scharr": Edge_Detection.scharr
        }
        if method not in methods:
            choices_str = ", ".join(methods.keys())
            return await ctx.reply(i18n.get(lang, "image.edge_method_error", choices=choices_str))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, f"{method}.png", methods[method])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Add artificial noise to the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", type="Noise type (salt_pepper/gaussian/poisson)")
    @check_blacklist()
    async def noise(self, ctx: commands.Context, type: str = "salt_pepper", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        types = {
            "salt_pepper": Image_Ops.add_salt_pepper,
            "gaussian": Enhancement.add_gaussian_noise,
            "poisson": Enhancement.add_poisson_noise
        }
        if type not in types:
            choices_str = ", ".join(types.keys())
            return await ctx.reply(i18n.get(lang, "image.noise_type_error", choices=choices_str))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "noise.png", types[type])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Apply histogram equalization to normalize exposure.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", method="Equalization method (global/clahe/adaptive)")
    @check_blacklist()
    async def equalize(self, ctx: commands.Context, method: str = "global", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        methods = {
            "global": Equalization.equalize,
            "clahe": Equalization.clahe,
            "adaptive": Equalization.adaptive
        }
        if method not in methods:
            choices_str = ", ".join(methods.keys())
            return await ctx.reply(i18n.get(lang, "image.equalize_method_error", choices=choices_str))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "equalize.png", methods[method])
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Apply a 3D emboss filter.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
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

    @image_group.command(description="Apply a warm sepia tone filter.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
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

    @image_group.command(description="Pixelate the image to create a retro blocky effect.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", pixel_size="Dimension of pixel blocks (default: 16)")
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

    @image_group.command(description="Apply a vignette shading filter around borders.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", sigma="Radius of the vignette center (default: 150)")
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

    @image_group.command(description="Apply gamma correction filter.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", gamma="Gamma correction factor (default: 1.5)")
    @check_blacklist()
    async def gamma(self, ctx: commands.Context, gamma: float = 1.5, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "gamma.png", Enhancement.gamma_correction, gamma)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Apply logarithmic dynamic range transform.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
    @check_blacklist()
    async def log(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "log.png", Enhancement.log_transform)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Blend two images together.")
    @app_commands.describe(user1="First user avatar source", user2="Second user avatar source", attachment1="First source image", attachment2="Second source image", alpha="Transparency ratio of the overlay (0.0 - 1.0)")
    @check_blacklist()
    async def blend(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, alpha: float = 0.5):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                # Determine image 1
                if attachment1:
                    img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine image 2
                if attachment2:
                    img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=user2.display_name))
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else:
                    raise ValueError(i18n.get(lang, "image.blend_missing_second"))

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
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @commands.hybrid_group(name='histogram')
    @check_blacklist()
    async def histogram_group(self, ctx: commands.Context):
        """Image histogram analysis tools."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @histogram_group.command(name="show", description="Show the image histogram.")
    @app_commands.describe(user="User whose avatar histogram you want to view", attachment="Image file to view the histogram of")
    @check_blacklist()
    async def histogram_show(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                img = cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                title_txt = i18n.get(lang, "image.hist_show_title", name=(user.display_name if user else ctx.author.display_name))
                plot_buf = await self._generate_histogram_plot(img_rgb, title=title_txt)
                await ctx.reply(file=discord.File(plot_buf, "histogram.png"))
            except ValueError as e:
                await ctx.reply(str(e))

    @histogram_group.command(name="match", description="Match the histogram of two images.")
    @app_commands.describe(user1="First user source", user2="Second user source", attachment1="First source image", attachment2="Second source image")
    @check_blacklist()
    async def match(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                # Determine image 1
                if attachment1:
                    img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine image 2 (Reference)
                if attachment2:
                    img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=user2.display_name))
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else:
                    raise ValueError(i18n.get(lang, "image.match_missing_ref"))

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
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @histogram_group.command(name="transfer", description="Transfer colors from one image to another.")
    @app_commands.describe(source_user="Color source user", ref_user="Color reference user", source_attachment="Color source image", ref_attachment="Color reference image")
    @check_blacklist()
    async def transfer(self, ctx: commands.Context, source_user: discord.User = None, ref_user: discord.User = None, source_attachment: discord.Attachment = None, ref_attachment: discord.Attachment = None):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                # Determine source image
                if source_attachment:
                    img1_bytes = await source_attachment.read()
                else:
                    target1 = source_user or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()

                # Determine reference image
                if ref_attachment:
                    img2_bytes = await ref_attachment.read()
                elif ref_user:
                    if ref_user.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=ref_user.display_name))
                    img2_bytes = await ref_user.display_avatar.with_format("png").read()
                else:
                    raise ValueError(i18n.get(lang, "image.transfer_missing_ref"))

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
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @image_group.command(description="Apply threshold binarization to image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", threshold_value="Binarization split cutoff value (0-255)", method="Binarization style (binary/otsu)")
    @check_blacklist()
    async def threshold(self, ctx: commands.Context, threshold_value: int = 127, method: str = "binary", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if method not in ["binary", "otsu"]:
            return await ctx.reply(i18n.get(lang, "image.threshold_method_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                use_otsu = (method == "otsu")
                await self._process_and_reply(ctx, bytes_data, "threshold.png", Image_Ops.threshold, threshold_value, use_otsu)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Auto-crop solid borders from the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", tolerance="Color difference match tolerance (default: 0)")
    @check_blacklist()
    async def autocrop(self, ctx: commands.Context, tolerance: int = 0, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "autocrop.png", Image_Ops.autocrop, tolerance)
            except ValueError as e:
                await ctx.reply(str(e))

    @image_group.command(description="Blend two images using masking overlays.")
    @app_commands.describe(user1="Background user source", user2="Overlay user source", attachment1="Background image", attachment2="Overlay image", mode="Blending mode formula (normal/add/multiply/screen/overlay)", match_mode="Dimension fitting option (resize/crop/pad)")
    @check_blacklist()
    async def composite(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, mode: str = "normal", match_mode: str = "resize"):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        modes = ["normal", "add", "multiply", "screen", "overlay"]
        match_modes = ["resize", "crop", "pad"]
        if mode not in modes: return await ctx.reply(i18n.get(lang, "image.composite_mode_error", choices=", ".join(modes)))
        if match_mode not in match_modes: return await ctx.reply(i18n.get(lang, "image.composite_match_mode_error", choices=", ".join(match_modes)))
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=user2.display_name))
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError(i18n.get(lang, "image.composite_missing_overlay"))

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                result = Image_Ops.composite(img1, img2, mode=mode, match_mode=match_mode)
                _, buffer = cv2.imencode('.png', cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "composite.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @image_group.command(description="Concatenate two images side-by-side or stacked.")
    @app_commands.describe(user1="First source user", user2="Second source user", attachment1="Left/Top image", attachment2="Right/Bottom image", axis="Join direction axis (horizontal/vertical)")
    @check_blacklist()
    async def concat(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, axis: str = "horizontal"):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if axis not in ["horizontal", "vertical"]: return await ctx.reply(i18n.get(lang, "image.concat_axis_error"))
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=user2.display_name))
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError(i18n.get(lang, "image.concat_missing_second"))

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                result = Image_Ops.concat(img1, img2, axis=axis)
                _, buffer = cv2.imencode('.png', cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
                await ctx.reply(file=discord.File(io.BytesIO(buffer), "concat.png"))
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e: await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @commands.hybrid_group(name='morph')
    @check_blacklist()
    async def morph_group(self, ctx: commands.Context):
        """Mathematical morphology operations."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @morph_group.command(description="Erode structure boundaries in the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", iterations="Repeat cycles (default: 1)", kernel_size="Neighborhood filter window size (default: 3)")
    @check_blacklist()
    async def erode(self, ctx: commands.Context, iterations: int = 1, kernel_size: int = 3, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "erode.png", Morphology.erode, kernel_size, iterations)
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e:
                user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
                lang = user_settings.lang if user_settings else "en"
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @morph_group.command(description="Dilate structure boundaries in the image.")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit", iterations="Repeat cycles (default: 1)", kernel_size="Neighborhood filter window size (default: 3)")
    @check_blacklist()
    async def dilate(self, ctx: commands.Context, iterations: int = 1, kernel_size: int = 3, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "dilate.png", Morphology.dilate, kernel_size, iterations)
            except ValueError as e: await ctx.reply(str(e))
            except Exception as e:
                user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
                lang = user_settings.lang if user_settings else "en"
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @morph_group.command(description="Extract image topological skeleton outlines (grayscale/binary only).")
    @app_commands.describe(user="User whose avatar you want to edit", attachment="Image file to edit")
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
            except Exception as e:
                user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
                lang = user_settings.lang if user_settings else "en"
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @histogram_group.command(name="compare", description="Compare similarity between two images using histograms.")
    @app_commands.describe(user1="First user avatar", user2="Second user avatar", attachment1="First image", attachment2="Second image", method="Histogram distance formula (correl/chisqr/intersect/bhattacharyya)")
    @check_blacklist()
    async def hist_compare(self, ctx: commands.Context, user1: discord.User = None, user2: discord.User = None, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, method: str = "correl"):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        methods = ["correl", "chisqr", "intersect", "bhattacharyya"]
        if method not in methods: return await ctx.reply(i18n.get(lang, "image.hist_compare_method_error", choices=", ".join(methods)))
        async with ctx.typing():
            try:
                # Load Image 1
                if attachment1: img1_bytes = await attachment1.read()
                else:
                    target1 = user1 or ctx.author
                    if target1.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=target1.display_name))
                    img1_bytes = await target1.display_avatar.with_format("png").read()
                # Load Image 2
                if attachment2: img2_bytes = await attachment2.read()
                elif user2:
                    if user2.avatar is None: raise ValueError(i18n.get(lang, "image.no_avatar", user=user2.display_name))
                    img2_bytes = await user2.display_avatar.with_format("png").read()
                else: raise ValueError(i18n.get(lang, "image.match_missing_ref"))

                img1 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img1_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                img2 = cv2.cvtColor(cv2.imdecode(np.frombuffer(img2_bytes, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)

                score = Histogram.match_score(img1, img2, method=method)
                
                # Generate visual comparison plot
                name1 = user1.display_name if user1 else "Gambar 1"
                name2 = user2.display_name if user2 else "Gambar 2"
                plot_buf = await self._generate_comparison_plot(img1, img2, title1=f"Histogram {name1}", title2=f"Histogram {name2}")

                embed = discord.Embed(title=i18n.get(lang, "image.hist_compare_title"), color=discord.Color.green())
                embed.add_field(name="Metode", value=method.upper(), inline=True)
                embed.add_field(name="Skor Kecocokan", value=f"`{score:.4f}`", inline=True)
                embed.set_image(url="attachment://comparison.png")
                
                file = discord.File(plot_buf, "comparison.png")
                await ctx.reply(file=file, embed=embed)

            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @histogram_group.command(name="cdf", description="Plot the Cumulative Distribution Function (CDF) histogram.")
    @app_commands.describe(user="User whose avatar you want to analyze", attachment="Image file to analyze")
    @check_blacklist()
    async def histogram_cdf(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
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
            except Exception as e:
                user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
                lang = user_settings.lang if user_settings else "en"
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @commands.hybrid_group(name='wavelet')
    @check_blacklist()
    async def wavelet_group(self, ctx: commands.Context):
        """
        Wavelet transform processing.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @wavelet_group.command(name="decomp", description="Perform Haar 2D discrete wavelet decomposition.")
    @app_commands.describe(user="User whose avatar you want to decompose", attachment="Image file to decompose", level="Decomposition recursion depth (1-4, default: 2)")
    @check_blacklist()
    async def wavelet_decomp(self, ctx: commands.Context, level: int = 2, user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not (1 <= level <= 4):
            return await ctx.reply(i18n.get(lang, "image.wavelet_level_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                
                def apply_wavelet(img, lvl):
                    # Convert to grayscale
                    if img.ndim == 3:
                        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
                    else:
                        gray = img
                    
                    coeffs = Wavelet.wavedec2(gray, level=lvl)
                    
                    # Normalize LL band (coeffs[0])
                    ll = coeffs[0]
                    ll_min, ll_max = ll.min(), ll.max()
                    if ll_max != ll_min:
                        ll_norm = (ll - ll_min) / (ll_max - ll_min) * 255.0
                    else:
                        ll_norm = np.zeros_like(ll)
                    
                    norm_coeffs = [ll_norm]
                    
                    # Normalize detail bands (LH, HL, HH) to be centered around 128
                    for i in range(1, len(coeffs)):
                        cH, cV, cD = coeffs[i]
                        def _map_detail(arr):
                            mx = np.max(np.abs(arr))
                            if mx == 0:
                                return np.full_like(arr, 128.0)
                            return (arr / mx) * 127.0 + 128.0
                        norm_coeffs.append((_map_detail(cH), _map_detail(cV), _map_detail(cD)))
                    
                    grid = Wavelet.assemble_wavedec2_grid(norm_coeffs)
                    return np.clip(grid, 0, 255).astype(np.uint8)

                await self._process_and_reply(ctx, bytes_data, "wavelet_decomposition.png", apply_wavelet, level)
            except ValueError as e:
                await ctx.reply(str(e))

    @wavelet_group.command(name="denoise", description="Denoise image using wavelet coefficient thresholding.")
    @app_commands.describe(user="User whose avatar you want to denoise", attachment="Image file to denoise", level="Decomposition levels (1-4, default: 2)", mode="Thresholding type (hard/soft)")
    @check_blacklist()
    async def wavelet_denoise(self, ctx: commands.Context, level: int = 2, mode: str = "soft", user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not (1 <= level <= 4):
            return await ctx.reply(i18n.get(lang, "image.wavelet_level_error"))
        if mode not in ["hard", "soft"]:
            return await ctx.reply(i18n.get(lang, "image.wavelet_mode_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "denoised.png", Wavelet.denoise, level, None, mode)
            except ValueError as e:
                await ctx.reply(str(e))

    @wavelet_group.command(name="compress", description="Compress image by pruning high-frequency wavelet details.")
    @app_commands.describe(user="User whose avatar you want to compress", attachment="Image file to compress", level="Decomposition levels (1-4, default: 3)", keep_ratio="Fraction of coefficients to preserve (0.01 - 1.0, default: 0.1)")
    @check_blacklist()
    async def wavelet_compress(self, ctx: commands.Context, level: int = 3, keep_ratio: float = 0.1, user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not (1 <= level <= 4):
            return await ctx.reply(i18n.get(lang, "image.wavelet_level_error"))
        if not (0.01 <= keep_ratio <= 1.0):
            return await ctx.reply(i18n.get(lang, "image.wavelet_keep_ratio_error"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "compressed.png", Wavelet.compress, level, keep_ratio)
            except ValueError as e:
                await ctx.reply(str(e))

    @commands.hybrid_group(name='stego')
    @check_blacklist()
    async def stego_group(self, ctx: commands.Context):
        """
        LSB Steganography tools.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @stego_group.command(name="hide", description="Hide a secret message inside an image using LSB encoding.")
    @app_commands.describe(message="Secret payload string to hide", user="User avatar source to carry payload", attachment="Carrier image file")
    @check_blacklist()
    async def stego_hide(self, ctx: commands.Context, message: str, user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        if not message:
            return await ctx.reply(i18n.get(lang, "image.stego_empty_msg"))
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                
                nparr = np.frombuffer(bytes_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    return await ctx.reply(i18n.get(lang, "image.read_failed"))
                
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                # Stego encode
                stego_img = Stego.encode(img_rgb, message)
                
                stego_bgr = cv2.cvtColor(stego_img, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode('.png', stego_bgr)
                
                await ctx.reply(content=i18n.get(lang, "image.stego_hide_success"), file=discord.File(io.BytesIO(buffer), "stego_image.png"))
            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @stego_group.command(name="reveal", description="Extract and decode secret LSB payloads hidden in images.")
    @app_commands.describe(user="User avatar containing payload", attachment="Carrier image file containing payload")
    @check_blacklist()
    async def stego_reveal(self, ctx: commands.Context, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                nparr = np.frombuffer(bytes_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    return await ctx.reply(i18n.get(lang, "image.read_failed"))
                
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
                # Stego decode
                message = Stego.decode(img_rgb)
                
                if not message:
                    await ctx.reply(i18n.get(lang, "image.stego_none_found"))
                else:
                    escaped_message = discord.utils.escape_markdown(message)
                    await ctx.reply(f"{i18n.get(lang, 'image.stego_found_title')}\n{escaped_message}")
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @commands.hybrid_group(name='fourier')
    @check_blacklist()
    async def fourier_group(self, ctx: commands.Context):
        """
        Fourier transform frequency filters.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @fourier_group.command(name="lpf", description="Apply frequency low-pass filter (LPF) to smooth image details.")
    @app_commands.describe(
        cutoff="Cutoff threshold radius (default: 30)", 
        type="Ideal, Butterworth, or Gaussian filtering style (default: gaussian)",
        order="Filter order slope for Butterworth (default: 2)",
        user="User whose avatar you want to filter", 
        attachment="Image file to filter"
    )
    @check_blacklist()
    async def fourier_lpf(self, ctx: commands.Context, cutoff: float = 30.0, type: str = "gaussian", order: int = 2, user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        types = ["ideal", "butterworth", "gaussian"]
        if type not in types:
            return await ctx.reply(i18n.get(lang, "image.fourier_type_error", choices=", ".join(types)))
        if cutoff <= 0:
            return await ctx.reply(i18n.get(lang, "image.fourier_cutoff_error"))
        
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                
                def apply_lpf(img):
                    if type == "ideal":
                        return FreqFilter.ideal_lpf(img, cutoff)
                    elif type == "butterworth":
                        return FreqFilter.butterworth_lpf(img, cutoff, order)
                    else:
                        return FreqFilter.gaussian_lpf(img, cutoff)
                        
                await self._process_and_reply(ctx, bytes_data, "lpf.png", apply_lpf)
            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @fourier_group.command(name="hpf", description="Apply frequency high-pass filter (HPF) to isolate edges.")
    @app_commands.describe(
        cutoff="Cutoff threshold radius (default: 30)", 
        type="Ideal, Butterworth, or Gaussian filtering style (default: gaussian)",
        order="Filter order slope for Butterworth (default: 2)",
        user="User whose avatar you want to filter", 
        attachment="Image file to filter"
    )
    @check_blacklist()
    async def fourier_hpf(self, ctx: commands.Context, cutoff: float = 30.0, type: str = "gaussian", order: int = 2, user: discord.User = None, attachment: discord.Attachment = None):
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        types = ["ideal", "butterworth", "gaussian"]
        if type not in types:
            return await ctx.reply(i18n.get(lang, "image.fourier_type_error", choices=", ".join(types)))
        if cutoff <= 0:
            return await ctx.reply(i18n.get(lang, "image.fourier_cutoff_error"))
        
        async with ctx.typing():
            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                
                def apply_hpf(img):
                    if type == "ideal":
                        return FreqFilter.ideal_hpf(img, cutoff)
                    elif type == "butterworth":
                        return FreqFilter.butterworth_hpf(img, cutoff, order)
                    else:
                        return FreqFilter.gaussian_hpf(img, cutoff)
                        
                await self._process_and_reply(ctx, bytes_data, "hpf.png", apply_hpf)
            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

    @fourier_group.command(name="homomorphic", description="Apply homomorphic filtering to balance shading and illumination.")
    @app_commands.describe(
        gamma_l="Low frequency gains (default: 0.5)",
        gamma_h="High frequency gains (default: 2.0)",
        cutoff="Cutoff threshold radius (default: 30)",
        user="User whose avatar you want to filter", 
        attachment="Image file to filter"
    )
    @check_blacklist()
    async def fourier_homomorphic(self, ctx: commands.Context, gamma_l: float = 0.5, gamma_h: float = 2.0, cutoff: float = 30.0, user: discord.User = None, attachment: discord.Attachment = None):
        async with ctx.typing():
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"

            try:
                bytes_data = await self._get_image_bytes(ctx, user, attachment)
                await self._process_and_reply(ctx, bytes_data, "homomorphic.png", FreqFilter.homomorphic, gamma_l, gamma_h, cutoff)
            except ValueError as e:
                await ctx.reply(str(e))
            except Exception as e:
                await ctx.reply(i18n.get(lang, "image.process_error", error=str(e)))

async def setup(bot: commands.Bot):
    await bot.add_cog(Image(bot))
