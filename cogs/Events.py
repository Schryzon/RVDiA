import discord
import random
from discord.ext import commands
from datetime import datetime
from scripts.main import connectdb

class Events(commands.Cog):
    """
    Events handler, duh.
    """
    def __init__(self, bot):
        self.bot = bot

    greetings = ["Hello there,", "Greetings,", "Welcome to CyroN,", "Why hello there,", "Thanks for joining,", "Heya hee ho,", 
    "Welcome,", "A new member joined,", "Yokoso,", "Hi~", "Konnichiwa,", "Heya,", "Ara~ara,"
    ]
    ending = [". I hope you have a fantastic day at CyroN!", ". I sure hope you brought me some food... just kidding!",
    ". I hope you get along with the others!", ". Don't forget to read the rules, okay?", ". Enjoy your stay!",
    ". Don't cause any ruckus, alrighty?", ". I bet Xefnir is happy to see another member! :D", ". Please don't cause any trouble, sweetie.",
    ". I'm so glad you joined!", "? Sorry, I'm kind of sleepy right now but anyways, welcome."
    ]
    left = ["Did they do something bad?", "Were you feeling uncomfortable? :(", "See you on the other side!",
    "I'll miss you...", "I hope the best for them.", "\n...", "One member lost.", "Goodbye!", "I'll never forget this day...",
    "\*Sobbing intensifies\*", "\*Sigh\*"
    ]

    @commands.Cog.listener()
    async def on_member_join(self, user:discord.Member):
        if user.bot is True: return
        if user.guild.id == 997500206511833128:
            channel = user.guild.get_channel(997500206981591082) #welcome
            await channel.send(f'**`{user}`** telah bergabung. Selamat datang di G-Tech!')
        elif user.guild.id == 877009215271604275:
            channel = user.guild.get_channel(882778878655991858) #hello-bye
            await channel.send(f"{random.choice(self.greetings)} **`{user}`**{random.choice(self.ending)}")
        else: return

    @commands.Cog.listener()
    async def on_member_remove(self, user:discord.Member):
        if user.bot is True: return
        if user.guild.id == 872815705450483732: return
        elif user.guild.id == 877009215271604275:
            channel = user.guild.get_channel(882778878655991858)
            await channel.send(f"**`{user}`** has left CyroN. {random.choice(self.left)}")
        else: return

    @commands.Cog.listener()
    async def on_guild_join(self, guild:discord.Guild):
        channel = self.bot.get_channel(1094157780606267502) #join-logs
        embed = discord.Embed(title='Joined a new Server!', color=0x03ac13, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        embed.add_field(name='ID', value=guild.id, inline=False)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild:discord.Guild):
        channel = self.bot.get_channel(1094157780606267502) #join-logs
        embed = discord.Embed(title='Left a Server!', color=0xff0000, timestamp=datetime.now())
        embed.add_field(name='Name', value=guild.name, inline=False)
        embed.add_field(name='Members', value=guild.member_count, inline=False)
        embed.add_field(name='ID', value=guild.id, inline=False)
        await channel.send(embed=embed)
        database = connectdb('Prefixes')
        try:
            database.find_one_and_delete({'_id': guild.id})
        except:
            return

    
async def setup(bot):
    await bot.add_cog(Events(bot))