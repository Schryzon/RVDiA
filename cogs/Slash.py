import discord
from discord.ext import commands
from discord import app_commands
from scripts.main import client

class Slash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    """
    Versi "Slash" dari command yang ada.
    """

    @app_commands.command(name="ping", 
    description= "Menampilkan latency ke Discord API dan MongoDB Atlas",
    )
    async def ping(self, interaction:discord.Interaction) -> None:
        mongoping = client.admin.command('ping')
        if mongoping['ok'] == 1:
            mongoping = 'GOOD - STATUS CODE 1'
        else:
            mongoping = 'ERROR - STATUS CODE 0'
        embed= discord.Embed(title= "Ping--Pong!", color=0x964b00, timestamp=interaction.created_at)
        embed.description = f"**Discord API:** `{round(self.bot.latency*1000)} ms`\n**MongoDB:** `{mongoping}`"
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar",
    description="Lihat avatar pengguna Discord."
    )
    async def avatar(self, interaction:discord.Interaction, pengguna:discord.Member = None, id:str = None):
        """Lihat avatar pengguna Discord."""
        if not id is None:
            id = await self.bot.fetch_user(int(id))
        global_user = pengguna or id or interaction.user
        png = global_user.avatar.with_format("png").url
        jpg = global_user.avatar.with_format("jpg").url
        webp = global_user.avatar.with_format("webp").url
        embed=discord.Embed(title=f"{global_user}'s Avatar", url = global_user.avatar.with_format("png").url, color= 0xff4df0)
        if global_user.avatar.is_animated():
            gif = global_user.avatar.with_format("gif").url
            embed.set_image(url = global_user.avatar.with_format("gif").url)
            embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp}) | [gif]({gif})"
        else:
            embed.description = f"[png]({png}) | [jpg]({jpg}) | [webp]({webp})"
            embed.set_image(url = global_user.avatar.with_format("png").url)
        embed.set_footer(text=f"Requested by: {interaction.user}", icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)

    
async def setup(bot:commands.Bot):
    await bot.add_cog(Slash(bot), guilds = [discord.Object(id=997500206511833128)])