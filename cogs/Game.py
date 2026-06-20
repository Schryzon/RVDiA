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
        Show a user's profile in Re:Volution ~ The Dream World!
        """
        await execute_profile(ctx, self.bot)

    @game.command(description='Register yourself to Re:Volution!')
    @app_commands.describe(name='The name of your dream character.')
    @check_blacklist()
    async def register(self, ctx: commands.Context, name: str = None):
        """
        Register yourself to Re:Volution!
        """
        await execute_register(ctx, name)

    @game.command(description='View the leaderboard of the strongest players!')
    @check_blacklist()
    async def leaderboard(self, ctx: commands.Context):
        """
        View the leaderboard of the strongest players!
        """
        await execute_leaderboard(ctx)

    @game.command(description='Guidebook for playing Re:Volution.')
    @check_blacklist()
    async def guide(self, ctx: commands.Context):
        """
        Guidebook for playing Re:Volution.
        """
        await execute_guide(ctx, self.bot)

    @game.command(description='Latest update list of Re:Volution.')
    @check_blacklist()
    async def changelog(self, ctx: commands.Context):
        """
        Latest update list of Re:Volution.
        """
        await execute_changelog(ctx, self.bot)

    @game.command(description='Delete your Re:Volution account.')
    @has_registered()
    @check_blacklist()
    async def resign(self, ctx: commands.Context):
        """
        Delete your Re:Volution account.
        """
        await execute_resign(ctx)

    @game.command(description='Claim your daily reward!')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def daily(self, ctx: commands.Context):
        """
        Claim your daily reward!
        """
        await execute_daily(ctx, self.bot)

    @game.command(description='View your profile or another user\'s profile.')
    @app_commands.describe(user='Whose profile do you want to view?')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def profile(self, ctx: commands.Context, *, user: discord.User = None):
        """
        View your profile or another user's profile.
        """
        await execute_profile(ctx, self.bot, user)

    @game.command(description='Fix your account data structure.')
    @has_registered()
    @check_blacklist()
    async def fix_account(self, ctx: commands.Context):
        """
        Use this if your account has data structure issues or items do not appear in the correct place.
        """
        await execute_fix_account(ctx)

    @game.command(description="Buy items or battle equipment!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def shop(self, ctx: commands.Context):
        """
        Buy items or battle equipment!
        """
        await execute_shop(ctx)

    @game.command(description="Explore the dream world!")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def adventure(self, ctx: commands.Context):
        """
        Explore the dream world!
        """
        await execute_adventure(ctx)

    @game.command(description='Challenge someone to a duel!')
    @app_commands.describe(member='Who do you want to fight?')
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def fight(self, ctx: commands.Context, *, member: discord.Member):
        """
        Challenge someone to a duel!
        """
        await execute_fight(ctx, self.bot, member)

    @game.command(description='Fight enemies in Re:Volution!')
    @app_commands.describe(enemy_tier='What level of enemy do you want to fight?')
    @app_commands.describe(enemy_name='The name of the enemy you want to fight?')
    @app_commands.choices(enemy_tier=[
        app_commands.Choice(name='BOSS', value='boss'),
        app_commands.Choice(name='BONUS', value='bonus'),
        app_commands.Choice(name='ELITE', value='elite'),
        app_commands.Choice(name='High', value='high'),
        app_commands.Choice(name="Normal", value='normal'),
        app_commands.Choice(name='Low', value='low')
    ])
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def battle(self, ctx: commands.Context, enemy_tier: app_commands.Choice[str], enemy_name: str = None):
        """
        Fight enemies in Re:Volution ~ The Dream World!
        """
        await execute_battle(ctx, self.bot, enemy_tier.value, enemy_name)

    @game.command(description='View the list of enemies in Re:Volution!', aliases=['enemy'])
    @has_registered()
    async def enemies(self, ctx: commands.Context):
        """
        View the list of enemies in Re:Volution ~ The Dream World!
        """
        await execute_enemies(ctx)

    @game.command(description='Request account data transfer.')
    @app_commands.describe(old_acc="Your old Discord account or Discord account ID.")
    @app_commands.describe(reason="Reason for the account transfer request.")
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def transfer(self, ctx: commands.Context, old_acc: discord.User, *, reason: str):
        """
        Request account data transfer.
        """
        await execute_transfer(ctx, self.bot, old_acc, reason)

    @game.command(description='Let\'s play a number guessing game with me!')
    @app_commands.describe(level='Which difficulty level will you choose?')
    @app_commands.choices(level=[
        app_commands.Choice(name='SUPER', value='SUPER'),
        app_commands.Choice(name='HARD', value='HARD'),
        app_commands.Choice(name="NORMAL", value='NORMAL'),
        app_commands.Choice(name='EASY', value='EASY')
    ])
    @check_blacklist()
    async def guess(self, ctx: commands.Context, level: app_commands.Choice[str]):
        """
        Let's play a number guessing game with me!
        """
        await execute_guess(ctx, level.value)

    @game.command(description="Use an item or equipment!")
    @app_commands.describe(type='The type of item you want to use.')
    @app_commands.choices(type=[
        app_commands.Choice(name='Item (Consumable)', value='item'),
        app_commands.Choice(name='Equipment', value='equipment')
    ])
    @has_registered()
    @check_compatible()
    @check_blacklist()
    async def use(self, ctx: commands.Context, type: app_commands.Choice[str]):
        """
        Use an item or equipment!
        """
        await execute_use(ctx, type.value)

    # ── Guild Commands ────────────────────────────────────────

    @commands.hybrid_group(name="guild", description="Re:Volution Guild System", fallback="info")
    @check_blacklist()
    async def guild(self, ctx: commands.Context):
        """
        View your guild info or another guild's info.
        """
        await execute_guild_info(ctx)

    @guild.command(name="create", description="Create a new guild! (Cost: 5000 Coins)")
    @app_commands.describe(name="Your dream guild name")
    @check_blacklist()
    async def guild_create(self, ctx: commands.Context, name: str):
        """
        Create a new guild for your community!
        """
        await execute_guild_create(ctx, name)

    @guild.command(name="edit", description="Edit your guild details (Owner only)")
    @app_commands.describe(
        name="New guild name",
        tagline="Your guild's cool tagline",
        icon_url="Image URL for the guild icon"
    )
    @check_blacklist()
    async def guild_edit(self, ctx: commands.Context, name: str = None, tagline: str = None, icon_url: str = None):
        """
        Edit your guild details to make it look cooler!
        """
        await execute_guild_edit(ctx, name, tagline, icon_url)

    @guild.command(name="invite", description="Invite someone to your guild")
    @app_commands.describe(user="The user to invite")
    @check_blacklist()
    async def guild_invite(self, ctx: commands.Context, user: discord.Member):
        """
        Invite a friend to join the guild!
        """
        await execute_guild_invite(ctx, user)

    @guild.command(name="leave", description="Leave your current guild")
    @check_blacklist()
    async def guild_leave(self, ctx: commands.Context):
        """
        Leave the guild. If you are the Owner, the guild will be disbanded!
        """
        await execute_guild_leave(ctx)

    @guild.command(name="leaderboard", aliases=["lb"], description="View the strongest guilds in Re:Volution!")
    @check_blacklist()
    async def guild_leaderboard(self, ctx: commands.Context):
        """
        Guild leaderboard based on member count.
        """
        await execute_guild_leaderboard(ctx)

    @guild.command(name="icon", description="View or change your guild icon!")
    @app_commands.describe(url="Image URL for the new guild icon (Leave empty to view current icon)")
    @check_blacklist()
    async def guild_icon(self, ctx: commands.Context, url: str = None):
        """
        View or change your guild icon to make it look grander!
        """
        await execute_guild_icon(ctx, url)

    # ── Premium Commands ──────────────────────────────────────

    @commands.hybrid_group(name="premium", description="Re:Volution Premium features", fallback="info")
    @check_blacklist()
    async def premium(self, ctx: commands.Context):
        """
        View status and benefits of becoming a Dream Weaver.
        """
        await execute_premium_info(ctx)

    @premium.command(name="buy", description="How to become a Dream Weaver (15k IDR / 30 Days)")
    @check_blacklist()
    async def premium_buy(self, ctx: commands.Context):
        """
        Premium subscription instructions.
        """
        await execute_premium_buy(ctx, self.bot)

    @premium.command(name="claim", description="Claim Premium status by uploading payment proof!")
    @app_commands.describe(bukti="Screenshot of your Saweria payment proof")
    @check_blacklist()
    async def premium_claim(self, ctx: commands.Context, bukti: discord.Attachment):
        """
        Submit your payment proof to be verified by an admin!
        """
        await execute_premium_claim(ctx, self.bot, bukti)

    @commands.command(name="approve_premium", description="[ADMIN] Approve premium claim for a user")
    @commands.is_owner()
    async def approve_premium(self, ctx: commands.Context, user: discord.User):
        """
        [ADMIN] Approve premium claim for a user.
        """
        await execute_approve_premium(ctx, user)


async def setup(bot):
    await bot.add_cog(Game(bot))