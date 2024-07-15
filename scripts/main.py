"""
A script file.
Contains things that may be needed for multiple files.
"""

import os
import pymongo
import discord
import aiohttp
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from discord.ui import View, Button
from discord.ext import commands
from dotenv import load_dotenv
from cogs.Handler import NotInGTechServer, NotGTechMember, NotGTechAdmin, NoProfilePicture, Blacklisted, NoEventAvailable, NotVoted
from cogs.Handler import NoGameAccount
from openai import AsyncOpenAI
load_dotenv('./secrets.env')

# New in v1.x
AIClient = AsyncOpenAI(
   api_key=os.getenv('openaikey')
)

class Url_Buttons(View):
  def __init__(self):
    super().__init__(timeout=None)

    add_me = Button(
            label='Tambahkan Aku!', 
            emoji='<:rvdia:1140812479883128862>',
            style=discord.ButtonStyle.green, 
            url=os.getenv('oauthlink')
            )
    
    github_repo = Button(
        label = "Github Repo",
        emoji = '<:githublogo:1082789555897384961>',
        style = discord.ButtonStyle.gray,
        url = 'https://github.com/Schryzon/rvdia'
    )

    support_server = Button(
        label= "Support Server",
        emoji = '<:cyron:1082789553263349851>',
        style = discord.ButtonStyle.blurple,
        url = 'https://discord.gg/QqWCnk6zxw'
    )
    self.add_item(add_me)
    self.add_item(github_repo)
    self.add_item(support_server)

async def connectdb(collection:str):
    """
    Returns data gained from database collection.
    Format: Main.<collection>
    !!WARNING!! RVDIA runs on Heroku, so an East US server is recommended for fast connection.
    """
    client = AsyncIOMotorClient(os.getenv('mongodburl'))
    db = client.Main
    coll = db[collection]
    return coll

def check_blacklist():
    async def predicate(ctx):
        blacklisted = await connectdb('Blacklist')
        check_blacklist = await blacklisted.find_one({'_id':ctx.author.id})
        if check_blacklist:
            raise Blacklisted('User is blacklisted!')
        return True
    return commands.check(predicate)

def in_gtech_server():
    async def predicate(ctx):
        if not ctx.guild.id == 997500206511833128:
            raise NotInGTechServer('Not in the G-Tech server!')
        return True
    return commands.check(predicate)

def event_available():
    async def predicate(ctx):
        if ctx.bot.event_mode == False:
            raise NoEventAvailable("No event available!")
        return True
    return commands.check(predicate)

def is_member_check():
    async def predicate(ctx):
        db = await connectdb("Gtech")
        data = await db.find_one({'_id':ctx.author.id})
        if data is None:
            raise NotGTechMember('Not a G-Tech member!')
        return True
    return commands.check(predicate)

def is_perangkat():
    async def predicate(ctx):
        perangkat = [
            893152351689527326, 919461305432305685, 877008612021661726, 632930926522925056,
            745218212689477642, 892293912964767784, 866890432038567949
            # Ayuning, Nisa, Jayananda, Ditha, Cok Is, Nanda Maharani, Richonanta
        ]
        if not ctx.author.id in perangkat:
            raise NotGTechAdmin('Not a G-Tech admin!')
        return True
    return commands.check(predicate)

def has_pfp():
    async def predicate(ctx):
        if not ctx.author.avatar:
            raise NoProfilePicture('No profile picture!')
        return True
    return commands.check(predicate)

def has_voted():
    async def predicate(ctx):
        headers = {'Authorization': os.getenv('topggtoken')}
        async with aiohttp.ClientSession(headers=headers) as session:
            response = await session.get(f'https://top.gg/api/bots/{ctx.bot.user.id}/check?userId={ctx.author.id}')
            data = await response.json()
            if data['voted'] == 1:
                return True
            else:
                raise NotVoted('User has not voted yet!')
        
    return commands.check(predicate)

async def check_vote(user_id:int):
    headers = {'Authorization': os.getenv('topggtoken')}
    async with aiohttp.ClientSession(headers=headers) as session:
        response = await session.get(f'https://top.gg/api/bots/957471338577166417/check?userId={user_id}')
        data = await response.json()
        if data['voted'] == 1:
            return True
        else:
            return False

def has_registered():
    async def predicate(ctx):
        database=await connectdb('Game')
        data=await database.find_one({'_id':ctx.author.id})
        if not data:
            raise NoGameAccount('User has no game account!')
        return True
    
    return commands.check(predicate)

# def buy_item(ctx:commands.Context):

def titlecase(word):
    if word.isupper():
        return word
    else:
        return word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()


def heading(direction:int):
        result =[]
        ranges = [
        [0, 45, "Utara"], [46, 90, "Timur Laut"],
        [91, 135, "Timur"], [136, 180, "Tenggara"],
        [181, 225, "Selatan"], [226, 270, "Barat Daya"],
        [271, 315, "Barat"], [316, 360, "Barat Laut"]
        ]

        for i in ranges:
            if direction in range(i[0], i[1] + 1):
                result.append(i[2])

        return result[0]         

async def disable_command(ctx:commands.Context):
    """
    Used for disabled commands.
    """
    await ctx.reply("Mohon maaf, command ini sedang dinonaktifkan!\nMohon sabar menunggu update terbaru, yah! ❤️")