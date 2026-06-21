import discord
import io
from discord.ext import commands
from discord import app_commands
from scripts.main import db, check_blacklist
from scripts.utils.captcha import generate_captcha_text, create_captcha_image
from scripts.utils.i18n import i18n

class CaptchaModal(discord.ui.Modal):
    def __init__(self, correct_text: str, role_name: str, lang: str):
        title = "Solve CAPTCHA" if lang == "en" else "Selesaikan CAPTCHA"
        super().__init__(title=title, timeout=60)
        self.correct_text = correct_text.upper()
        self.role_name = role_name
        self.lang = lang

        label = "Enter the CAPTCHA code:" if lang == "en" else "Masukkan kode CAPTCHA:"
        placeholder = "Type the 5-character code here..." if lang == "en" else "Ketik 5 karakter kode di sini..."
        self.captcha_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            min_length=5,
            max_length=5,
            required=True
        )
        self.add_item(self.captcha_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.captcha_input.value.strip().upper()
        if user_input == self.correct_text:
            member = interaction.user
            guild = interaction.guild
            
            # Find role by name
            role = discord.utils.get(guild.roles, name=self.role_name)
            if not role:
                for r in guild.roles:
                    if r.name.lower() == self.role_name.lower():
                        role = r
                        break
            
            # If role doesn't exist, try to create it
            if not role:
                try:
                    role = await guild.create_role(name=self.role_name, reason="Verification System Auto-Role")
                except discord.Forbidden:
                    error_msg = (
                        f"Verification successful, but I lack permissions to create the '{self.role_name}' role! "
                        "Please contact an administrator."
                    ) if self.lang == "en" else (
                        f"Verifikasi sukses, tapi aku tidak punya izin untuk membuat role '{self.role_name}'! "
                        "Silahkan hubungi administrator."
                    )
                    return await interaction.response.send_message(error_msg, ephemeral=True)
            
            # Assign role
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                error_msg = (
                    f"Verification successful, but I cannot assign the '{self.role_name}' role! "
                    "Make sure my role is placed higher than the verification role."
                ) if self.lang == "en" else (
                    f"Verifikasi sukses, tapi aku tidak bisa memberikan role '{self.role_name}'! "
                    "Pastikan role-ku berada lebih tinggi dari role verifikasi."
                )
                return await interaction.response.send_message(error_msg, ephemeral=True)

            success_msg = (
                f"✅ Verification successful! You have been granted the **{role.name}** role."
            ) if self.lang == "en" else (
                f"✅ Verifikasi berhasil! Kamu telah mendapatkan role **{role.name}**."
            )
            await interaction.response.send_message(success_msg, ephemeral=True)
        else:
            fail_msg = (
                "❌ Incorrect CAPTCHA code! Please click the button and try again."
            ) if self.lang == "en" else (
                "❌ Kode CAPTCHA salah! Silahkan klik tombol dan coba lagi."
            )
            await interaction.response.send_message(fail_msg, ephemeral=True)

class CaptchaView(discord.ui.View):
    def __init__(self, user_id: int, correct_text: str, role_name: str, lang: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.correct_text = correct_text
        self.role_name = role_name
        self.lang = lang

        solve_label = "Solve CAPTCHA" if lang == "en" else "Jawab CAPTCHA"
        self.solve_button = discord.ui.Button(label=solve_label, style=discord.ButtonStyle.green, custom_id="solve_btn")
        self.solve_button.callback = self.solve_callback
        self.add_item(self.solve_button)

        regen_label = "New CAPTCHA" if lang == "en" else "CAPTCHA Baru"
        self.regen_button = discord.ui.Button(label=regen_label, style=discord.ButtonStyle.blurple, custom_id="regen_btn")
        self.regen_button.callback = self.regen_callback
        self.add_item(self.regen_button)

    async def solve_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            msg = "This verification is not for you!" if self.lang == "en" else "Verifikasi ini bukan untukmu!"
            return await interaction.response.send_message(msg, ephemeral=True)
            
        modal = CaptchaModal(self.correct_text, self.role_name, self.lang)
        await interaction.response.send_modal(modal)

    async def regen_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            msg = "This verification is not for you!" if self.lang == "en" else "Verifikasi ini bukan untukmu!"
            return await interaction.response.send_message(msg, ephemeral=True)
            
        await interaction.response.defer()
        
        # Generate new captcha
        new_text = generate_captcha_text()
        self.correct_text = new_text
        
        img_bytes = create_captcha_image(new_text)
        new_file = discord.File(io.BytesIO(img_bytes), filename="captcha.png")
        
        embed = discord.Embed(
            title="Verification Required" if self.lang == "en" else "Verifikasi Dibutuhkan",
            description=(
                "Please solve the CAPTCHA below to gain access to the server.\n"
                "Click **Solve CAPTCHA** to input the code, or **New CAPTCHA** to refresh the image."
            ) if self.lang == "en" else (
                "Silahkan selesaikan CAPTCHA di bawah ini untuk mendapatkan akses ke server.\n"
                "Klik **Jawab CAPTCHA** untuk memasukkan kode, atau **CAPTCHA Baru** untuk memuat ulang gambar."
            ),
            color=0x7289da
        )
        embed.set_image(url="attachment://captcha.png")
        
        await interaction.message.edit(embed=embed, attachments=[new_file], view=self)

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(
        name="verify",
        description="Verify yourself to gain server access using a CAPTCHA."
    )
    @app_commands.describe(role_name="The name of the role to assign upon verification (Default: Verified)")
    @commands.guild_only()
    @check_blacklist()
    async def verify(self, ctx: commands.Context, role_name: str = "Verified"):
        """Verify yourself to gain server access using a CAPTCHA."""
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"

        # Check if the user already has the verification role
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role and role in ctx.author.roles:
            already_msg = (
                "✅ You are already verified in this server!"
            ) if lang == "en" else (
                "✅ Kamu sudah terverifikasi di server ini!"
            )
            return await ctx.reply(already_msg)

        # Defer and run typing
        try:
            await ctx.defer()
        except discord.NotFound:
            pass
            
        async with ctx.channel.typing():
            captcha_text = generate_captcha_text()
            img_bytes = create_captcha_image(captcha_text)
            
            captcha_file = discord.File(io.BytesIO(img_bytes), filename="captcha.png")
            
            embed = discord.Embed(
                title="Verification Required" if lang == "en" else "Verifikasi Dibutuhkan",
                description=(
                    "Please solve the CAPTCHA below to gain access to the server.\n"
                    "Click **Solve CAPTCHA** to input the code, or **New CAPTCHA** to refresh the image."
                ) if lang == "en" else (
                    "Silahkan selesaikan CAPTCHA di bawah ini untuk mendapatkan akses ke server.\n"
                    "Klik **Jawab CAPTCHA** untuk memasukkan kode, atau **CAPTCHA Baru** untuk memuat ulang gambar."
                ),
                color=0x7289da
            )
            embed.set_image(url="attachment://captcha.png")
            
            view = CaptchaView(ctx.author.id, captcha_text, role_name, lang)
            msg = await ctx.reply(embed=embed, file=captcha_file, view=view)
            # Store the message reference to disable view on timeout
            view.message = msg

async def setup(bot):
    await bot.add_cog(Verification(bot))
