import discord
from scripts.main import connectdb
from discord.ext import commands

class Moderation(commands.Cog):
    """
    Moderation commands, just like my purpose.
    """
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(
        description="Warns a member and add them into the database."
        )
    @commands.has_permissions(ban_members = True)
    async def warn(self, ctx, member:commands.MemberConverter, *, reason = None):
        """
        Gives someone a warning.
        """
        if ctx.author == member:
            return await ctx.reply("You can't warn yourself, maybe Xefnir will.")
        if member.bot:
            return await ctx.reply("\*Sigh\* You know warning a bot is pointless, right?")
        db = connectdb("Warns")
        reason = reason or "No reason specified"
        warns = db.find_one({"_id":member.id})
        warnqty = 0 #Gee
        if warns is None:
            db.insert_one({"_id":member.id, "warns":1, "reason":[reason]})
            warnqty = 1
        else:
            db.update_one({"_id":member.id}, {'$inc':{"warns":1}, '$push':{"reason":reason}})
            warnqty = warns['warns']+1
        em = discord.Embed(title=f"Warned", description = f"{member.mention} has been warned by {ctx.author}.\nThey now have **`{warnqty}`** warning(s).",
        color = member.colour
        )
        em.add_field(name="Reason", value=reason, inline=False)
        em.set_thumbnail(url = member.avatar.url)
        await ctx.reply(embed = em)

    @commands.command(
        aliases=['wnhistory'], 
        description="View warning history of a member.",
    )
    @commands.has_permissions(ban_members = True)
    async def warnhistory(self, ctx, member:commands.MemberConverter = None):
            """View a list of warnings a user had been given."""
            member = member or ctx.author
            db = connectdb("Warns")
            doc = db.find_one({'_id':member.id})
            if doc is None:
                return await ctx.reply(f"**`{member}`** currently has 0 warnings. They're innocent if you ask me.")
            reasons = doc['reason']
            emb = discord.Embed(title = f"Warn History for {member}", color = member.colour)
            emb.add_field(name= "Warning count", value=doc['warns'], inline=False)
            if doc['warns'] > 1:
                emb.add_field(name=f"Reasons (from warning #1 to #{doc['warns']})", value="*"+"\n".join(reasons)+"*")
            else:
                emb.add_field(name=f"Reason", value="*"+"\n".join(reasons)+"*")
            emb.set_thumbnail(url = member.avatar.url)
            await ctx.reply(embed = emb)

    @commands.command(aliases=["rmwarn"], description="Remove all warnings from a user.")
    @commands.has_permissions(ban_members=True)
    async def removewarn(self, ctx, member:commands.MemberConverter):
        """
        Remove all warnings from a user.
        """
        db = connectdb("Warns")
        doc = db.find_one({"_id":member.id})
        if doc is None:
            return await ctx.reply(f"`{member}` hasn't got any warnings yet, cannot remove data.")
        db.find_one_and_delete({"_id":member.id})
        await ctx.reply(f"All warning(s) for {member.mention} have been erased. May they behave better now.")

    """@commands.command(aliases=['wnlist'])
    @commands.has_permissions(ban_members=True)
    async def warnlist(self, ctx):
        db = connectdb('Warns')
        docs = db.find({})
        print(docs)""" #Unused for the moment.

    @commands.command(description="Bans any user, even if they're outside of the server.")
    @commands.has_permissions(ban_members=True)
    async def ultban(self, ctx, user:commands.UserConverter, *, reason = None):
        """
        Bans any user, might be overpowered.
        """
        reason = reason or "No reason specified"
        await ctx.guild.ban(user)
        embed = discord.Embed(title="Ultimately Banned", color = ctx.author.colour)
        embed.description = f"**`{user}`** has been ultbanned by **`{ctx.author}`**"
        embed.add_field(name = "Reason", value = reason, inline = False)
        embed.set_thumbnail(url = user.avatar.url)
        await ctx.reply(embed = embed)

    @commands.command(description="Unbans someone using their ID.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: commands.UserConverter):
        """
        Unbans someone, duh.
        """
        try:
            await ctx.guild.unban(user_id)
            await ctx.send(f"Successfully unbanned {user_id}.")
            return
        except:
            await ctx.send(f"I can't find {user_id} in the ban list, make sure they're banned from the server.")
            return

    @commands.command(aliases = ['clean', 'purge'], description="Cleans the channel of <amount> messages.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount:int):
        """
        RVDIA becomes a maid (not really).
        """
        if amount <= 0:
            return await ctx.reply("\*Sigh\* I can't delete 0 messages! You've got to be joking to command me that.")
        amount = amount or 5
        await ctx.channel.purge(limit = amount+1)
        await ctx.send(f"Deleted {amount} messages from **`#{ctx.channel.name}`**.", delete_after = 5.0)


async def setup(bot):
    await bot.add_cog(Moderation(bot))