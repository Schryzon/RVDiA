import discord
import os
import asyncio
import logging
from discord.ext import commands
from pkgutil import iter_modules
from contextlib import suppress
from scripts.main import db
from scripts.game.worldboss import force_spawn_boss

class Owner(commands.Cog):
    """
    Commands specifically for the Bot Owner (Jayananda / Schryzon).
    """
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['on', 'enable'], hidden=True)
    @commands.is_owner()
    async def load(self, ctx, ext):
        """
        Manually load cogs
        """
        if ext == "__init__":
            await ctx.send("Stupid.")
            return
        try:
            await self.bot.load_extension(f"cogs.{ext}")
            await ctx.send(f"Cog `{ext}.py` sekarang aktif!")
        except commands.ExtensionAlreadyLoaded:
            await ctx.send(f"Cog `{ext}.py` sudah diaktifkan!")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog `{ext}.py` tidak ditemukan!")

    @commands.command(aliases=['off', 'disable'], hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, ext):
        """
        Manually unload cogs
        """
        if ext == "__init__":
            await ctx.send("Stupid.")
            return
        try:
            await self.bot.unload_extension(f"cogs.{ext}")
            await ctx.send(f"Cog `{ext}.py` sekarang tidak aktif!")
        except commands.ExtensionNotFound:
            await ctx.send(f"Cog `{ext}.py` tidak ditemukan!")
        except commands.ExtensionNotLoaded:
            await ctx.send(f"Cog `{ext}.py` sudah dimatikan!")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def sync(self, ctx):
        """
        Sync slash commands
        """
        synced = await self.bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} commands.")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def cogs(self, ctx):
        """
        Cogs list
        """
        cogs_list = [cogs.name for cogs in iter_modules(['cogs'], prefix='cogs.')]
        embed = discord.Embed(title="RVDIA Cog List", description="\n".join(cogs_list), color=ctx.author.colour)
        embed.set_thumbnail(url=self.bot.user.avatar)
        embed.set_footer(text='Cogs were taken from "cogs"')
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def refresh(self, ctx):
        """
        In case something went horribly wrong
        """
        dynamic_cogs = [c.name for c in iter_modules(['cogs'], prefix='cogs.')]
        results = []
        for cog in dynamic_cogs:
            if not cog == 'cogs.__init__':
                try:
                    with suppress(commands.ExtensionNotLoaded):
                        await self.bot.unload_extension(cog)
                    await self.bot.load_extension(cog)
                    results.append(f"✅ `{cog}`")
                except Exception as e:
                    results.append(f"❌ `{cog}`: {str(e)[:50]}")
                    logging.error(f"Failed to load cog {cog}: {e}")
                    
        embed = discord.Embed(title="Cogs Refresh Status", description="\n".join(results), color=self.bot.color)
        await ctx.reply(embed=embed)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def restart(self, ctx: commands.Context):
        """
        In case for timeout
        """
        await ctx.send('Restarting...')
        channel = ctx.channel
        await self.bot.close()
        await asyncio.sleep(2)
        self.bot.run(token=os.getenv('token'))
        await self.bot.wait_until_ready()
        logging.warning('RVDIA has been remotely restarted!')
        await channel.send("RVDiA telah direstart!")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def status(self, ctx: commands.Context, *, status_text):
        """
        Change presence status text
        """
        # Cancel the dynamic change status loop if running
        # (Assuming change_status loop is imported or accessible from main)
        try:
            from RVDIA import change_status
            if change_status.is_running():
                change_status.cancel()
        except Exception:
            pass

        await self.bot.change_presence(status=discord.Status.idle, activity=discord.Game(status_text))
        await ctx.reply('Changed my status!')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def blacklist(self, ctx: commands.Context, user: discord.User, *, reason: str = None):
        """
        Blacklist a user from the bot
        """
        if user.id == self.bot.owner_id:
            return await ctx.reply('Tidak bisa blacklist owner!')
        if user.id == self.bot.user.id:
            return await ctx.reply('Tidak bisa blacklist diriku sendiri!')
            
        check_blacklist = await db.blacklist.find_unique(where={'id': user.id})
        if not check_blacklist:
            await db.blacklist.create(data={'id': user.id, 'reason': reason})
            embed = discord.Embed(title='‼️ BLACKLISTED ‼️', timestamp=ctx.message.created_at, color=0xff0000)
            embed.description = f'**`{user}`** telah diblacklist dari menggunakan RVDIA!'
            embed.set_thumbnail(url=user.avatar.url if user.avatar else os.getenv('normalpfp'))
            embed.add_field(name='Alasan:', value=reason, inline=False)
            return await ctx.reply(embed=embed)
        
        await ctx.reply(f'`{user}` telah diblacklist!')

    @commands.command(hidden=True)
    @commands.is_owner()
    async def whitelist(self, ctx: commands.Context, user: discord.User):
        """
        Remove a user from the blacklist
        """
        check_blacklist = await db.blacklist.find_unique(where={'id': user.id})
        if not check_blacklist:
            return await ctx.reply(f'**`{user}`** tidak diblacklist dari menggunakan RVDIA!')
        
        await db.blacklist.delete(where={'id': user.id})
        await ctx.reply(f'`{user}` telah diwhitelist!')

    @commands.command(name="spawnboss", hidden=True)
    @commands.is_owner()
    async def spawnboss(self, ctx: commands.Context, name: str = None, tier: str = None, max_hp: int = None):
        """
        [ADMIN] Force spawn/reset the World Boss.
        """
        boss = await force_spawn_boss(name, tier, max_hp)
        await ctx.reply(f"⚔️ **World Boss spawned successfully!**\n- **Name**: `{boss.name}`\n- **Tier**: `{boss.tier}`\n- **HP**: `{boss.hp}/{boss.maxHp}`")

async def setup(bot):
    await bot.add_cog(Owner(bot))
