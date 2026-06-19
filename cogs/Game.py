"""
Commands and features for her game.
Re:Volution ~ The Dream World.
Modularized router cog.
"""

import discord
from discord import app_commands
from discord.ext import commands

from scripts.main import check_blacklist, has_registered
from scripts.game.game import check_compatible

from scripts.game.profile import (
    execute_register,
    execute_leaderboard,
    execute_guide,
    execute_changelog,
    execute_resign,
    execute_daily,
    execute_profile,
    execute_fix_account,
    execute_shop,
    execute_adventure,
    execute_transfer,
    execute_use
)

from scripts.game.fight import (
    execute_fight,
    execute_battle,
    execute_enemies,
    execute_guess
)

from scripts.game.guild import (
    execute_guild_info,
    execute_guild_create,
    execute_guild_edit,
    execute_guild_invite,
    execute_guild_leave,
    execute_guild_leaderboard,
    execute_guild_icon
)

from scripts.game.premium import (
    execute_premium_info,
    execute_premium_buy,
    execute_premium_claim,
    execute_approve_premium
)


class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="game", description="Re:Volution ~ The Dream World")
    @check_blacklist()
    async def game(self, ctx: commands.Context):
        """
        Lihat profil pengguna di Re:Volution ~ The Dream World!
        """
        await execute_profile(ctx, self.bot)

    @game.command(description='Daftarkan dirimu ke Re:Volution!')
    @app_commands.describe(name='Nama karakter impianmu.')
    @check_blacklist()
    async def register(self, ctx: commands.Context, name: str = None):
        """
        Daftarkan dirimu ke Re:Volution!
        """
        await execute_register(ctx, name)

    @game.command(description='Lihat papan peringkat terkuat!')
    @check_blacklist()
    async def leaderboard(self, ctx: commands.Context):
        """
        Lihat papan peringkat terkuat!
        """
        await execute_leaderboard(ctx)

    @game.command(description='Buku panduan bermain Re:Volution.')
    @check_blacklist()
    async def guide(self, ctx: commands.Context):
        """
        Buku panduan bermain Re:Volution.
        """
        await execute_guide(ctx, self.bot)

    @game.command(description='Daftar update terbaru Re:Volution.')
    @check_blacklist()
    async def changelog(self, ctx: commands.Context):
        """
        Daftar update terbaru Re:Volution.
        """
        await execute_changelog(ctx, self.bot)

    @game.command(description='Hapus akun Re:Volution-mu.')
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx: commands.Context):
        """
        Hapus akun Re:Volution-mu.
        """
        await execute_resign(ctx)

    @game.command(description='Klaim hadiah harianmu!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def daily(self, ctx: commands.Context):
        """
        Klaim hadiah harianmu!
        """
        await execute_daily(ctx, self.bot)

    @game.command(description='Lihat profilmu atau pengguna lain.')
    @app_commands.describe(user='Siapa yang ingin kamu lihat?')
    @app_commands.rename(user='pengguna')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def profile(self, ctx: commands.Context, *, user: discord.User = None):
        """
        Lihat profilmu atau pengguna lain.
        """
        await execute_profile(ctx, self.bot, user)

    @game.command(description='Perbaiki struktur data akunmu.')
    @has_registered()
    @check_blacklist()
    async def fix_account(self, ctx: commands.Context):
        """
        Gunakan ini jika akunmu mengalami masalah struktur data atau item tidak muncul di tempatnya.
        """
        await execute_fix_account(ctx)

    @game.command(description="Beli item atau perlengkapan perang!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def shop(self, ctx: commands.Context):
        """
        Beli item atau perlengkapan perang!
        """
        await execute_shop(ctx)

    @game.command(description="Jelajahi dunia mimpi!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def adventure(self, ctx: commands.Context):
        """
        Jelajahi dunia mimpi!
        """
        await execute_adventure(ctx)

    @game.command(description='Tantang seseorang ke sebuah duel!')
    @app_commands.describe(member='Siapa yang ingin kamu lawan?')
    @app_commands.rename(member='pengguna')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def fight(self, ctx: commands.Context, *, member: discord.Member):
        """
        Tantang seseorang ke sebuah duel!
        """
        await execute_fight(ctx, self.bot, member)

    @game.command(description='Lawan musuh-musuh yang ada di Re:Volution!')
    @app_commands.describe(enemy_tier='Musuh level berapa yang ingin kamu lawan?')
    @app_commands.rename(enemy_tier='level')
    @app_commands.describe(enemy_name='Nama musuh yang ingin kamu lawan?')
    @app_commands.rename(enemy_name='nama_musuh')
    @app_commands.choices(enemy_tier=[
        app_commands.Choice(name='BOSS', value='boss'),
        app_commands.Choice(name='BONUS', value='bonus'),
        app_commands.Choice(name='ELITE', value='elite'),
        app_commands.Choice(name='High (Tinggi)', value='high'),
        app_commands.Choice(name="Normal (Sedang)", value='normal'),
        app_commands.Choice(name='Low (Rendah)', value='low')
    ])
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def battle(self, ctx: commands.Context, enemy_tier: app_commands.Choice[str], enemy_name: str = None):
        """
        Lawan musuh-musuh yang ada di Re:Volution ~ The Dream World!
        """
        await execute_battle(ctx, self.bot, enemy_tier.value, enemy_name)

    @game.command(description='Lihat daftar musuh yang muncul di Re:Volution!', aliases=['enemy'])
    @has_registered()
    async def enemies(self, ctx: commands.Context):
        """
        Lihat daftar musuh yang muncul di Re:Volution ~ The Dream World!
        """
        await execute_enemies(ctx)

    @game.command(description='Request untuk pemindahan data akun.')
    @app_commands.describe(old_acc="Akun Discord lamamu atau ID akun Discord lamamu.")
    @app_commands.describe(reason="Alasan request pemindahan data akun.")
    @app_commands.rename(reason="alasan")
    @app_commands.rename(old_acc="akun_lama")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def transfer(self, ctx: commands.Context, old_acc: discord.User, *, reason: str):
        """
        Request untuk pemindahan data akun.
        """
        await execute_transfer(ctx, self.bot, old_acc, reason)

    @game.command(description='Ayo main tebak angka bersamaku!')
    @app_commands.describe(level='Tingkat kesulitan mana yang akan kamu pilih?')
    @app_commands.choices(level=[
        app_commands.Choice(name='SUPER', value='SUPER'),
        app_commands.Choice(name='HARD', value='HARD'),
        app_commands.Choice(name="NORMAL", value='NORMAL'),
        app_commands.Choice(name='EASY', value='EASY')
    ])
    @check_blacklist()
    async def guess(self, ctx: commands.Context, level: app_commands.Choice[str]):
        """
        Ayo main tebak angka bersamaku!
        """
        await execute_guess(ctx, level.value)

    @game.command(description="Gunakan barang atau perlengkapan perang!")
    @app_commands.describe(type='Jenis barang yang ingin digunakan?')
    @app_commands.choices(type=[
        app_commands.Choice(name='Barang (Consumable)', value='item'),
        app_commands.Choice(name='Perlengkapan (Equipment)', value='equipment')
    ])
    @app_commands.rename(type='jenis')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def use(self, ctx: commands.Context, type: app_commands.Choice[str]):
        """
        Gunakan barang atau perlengkapan perang!
        """
        await execute_use(ctx, type.value)

    # ── Guild Commands ────────────────────────────────────────

    @commands.hybrid_group(name="guild", description="Sistem Guild Re:Volution", fallback="info")
    @check_blacklist()
    async def guild(self, ctx: commands.Context):
        """
        Lihat informasi guild kamu atau guild orang lain.
        """
        await execute_guild_info(ctx)

    @guild.command(name="create", description="Buat guild baru! (Biaya: 5000 Koin)")
    @app_commands.describe(name="Nama guild impianmu")
    @check_blacklist()
    async def guild_create(self, ctx: commands.Context, name: str):
        """
        Buat guild baru untuk komunitasmu!
        """
        await execute_guild_create(ctx, name)

    @guild.command(name="edit", description="Ubah identitas guildmu (Hanya Owner)")
    @app_commands.describe(
        name="Nama baru guild",
        tagline="Tagline keren guildmu",
        icon_url="URL Gambar untuk ikon guild"
    )
    @check_blacklist()
    async def guild_edit(self, ctx: commands.Context, name: str = None, tagline: str = None, icon_url: str = None):
        """
        Ubah detail guildmu agar terlihat lebih keren!
        """
        await execute_guild_edit(ctx, name, tagline, icon_url)

    @guild.command(name="invite", description="Undang seseorang ke guildmu")
    @app_commands.describe(user="User yang ingin diundang")
    @check_blacklist()
    async def guild_invite(self, ctx: commands.Context, user: discord.Member):
        """
        Undang temanmu untuk bergabung dalam guild!
        """
        await execute_guild_invite(ctx, user)

    @guild.command(name="leave", description="Keluar dari guild saat ini")
    @check_blacklist()
    async def guild_leave(self, ctx: commands.Context):
        """
        Keluar dari guild. Jika kamu Owner, guild akan dibubarkan!
        """
        await execute_guild_leave(ctx)

    @guild.command(name="leaderboard", aliases=["lb"], description="Lihat guild terkuat di Re:Volution!")
    @check_blacklist()
    async def guild_leaderboard(self, ctx: commands.Context):
        """
        Papan peringkat Guild berdasarkan jumlah anggota.
        """
        await execute_guild_leaderboard(ctx)

    @guild.command(name="icon", description="Lihat atau ubah ikon guildmu!")
    @app_commands.describe(url="URL Gambar baru untuk ikon guild (Kosongkan untuk melihat ikon saat ini)")
    @check_blacklist()
    async def guild_icon(self, ctx: commands.Context, url: str = None):
        """
        Lihat atau ubah ikon guildmu agar terlihat lebih megah!
        """
        await execute_guild_icon(ctx, url)

    # ── Premium Commands ──────────────────────────────────────

    @commands.hybrid_group(name="premium", description="Fitur Premium Re:Volution", fallback="info")
    @check_blacklist()
    async def premium(self, ctx: commands.Context):
        """
        Lihat status dan keuntungan menjadi Dream Weaver.
        """
        await execute_premium_info(ctx)

    @premium.command(name="buy", description="Cara menjadi Dream Weaver (15k IDR / 30 Hari)")
    @check_blacklist()
    async def premium_buy(self, ctx: commands.Context):
        """
        Instruksi berlangganan Premium.
        """
        await execute_premium_buy(ctx, self.bot)

    @premium.command(name="claim", description="Klaim status Premium dengan mengunggah bukti pembayaran!")
    @app_commands.describe(bukti="Screenshot bukti pembayaran Saweria-mu")
    @check_blacklist()
    async def premium_claim(self, ctx: commands.Context, bukti: discord.Attachment):
        """
        Kirim bukti pembayaranmu untuk diverifikasi oleh admin!
        """
        await execute_premium_claim(ctx, self.bot, bukti)

    @commands.command(name="approve_premium", description="[ADMIN] Setujui klaim premium seseorang")
    @commands.is_owner()
    async def approve_premium(self, ctx: commands.Context, user: discord.User):
        """
        [ADMIN] Setujui klaim premium seseorang.
        """
        await execute_approve_premium(ctx, user)


async def setup(bot):
    await bot.add_cog(Game(bot))