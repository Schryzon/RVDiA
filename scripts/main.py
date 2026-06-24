"""
A script file.
Contains things that may be needed for multiple files.
"""

import os
import discord
import aiohttp
from openai import AsyncOpenAI
from discord.ext import commands
from prisma import Prisma

from discord.ui import View, Button
from discord.ext import commands
from dotenv import load_dotenv
from scripts.utils.errors import NoProfilePicture, Blacklisted, NoEventAvailable, NotVoted
from scripts.utils.errors import NoGameAccount, NoPremiumStatus
from datetime import datetime, timezone
from scripts.utils.i18n import i18n

load_dotenv()

# New in v1.x
AIClient = AsyncOpenAI(
   api_key=os.getenv('openaikey', 'not-set')
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

db = Prisma()

def check_blacklist():
    async def predicate(ctx):
        check_blacklist = await db.blacklist.find_unique(where={'id': ctx.author.id})
        if check_blacklist:
            raise Blacklisted('User is blacklisted!')
        return True
    return commands.check(predicate)

def event_available():
    async def predicate(ctx):
        if ctx.bot.event_mode == False:
            raise NoEventAvailable("No event available!")
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
        token = os.getenv('topggtoken')
        if not token:
            raise NotVoted('Top.gg API token is not configured!')
        if not token.startswith('Bearer '):
            token = f'Bearer {token}'
        headers = {'Authorization': token}
        async with aiohttp.ClientSession(headers=headers) as session:
            url = f'https://top.gg/api/v1/projects/@me/votes/{ctx.author.id}?source=discord'
            async with session.get(url) as response:
                if response.status == 200:
                    return True
                elif response.status == 404:
                    raise NotVoted('User has not voted yet!')
                else:
                    raise NotVoted('Failed to verify vote status from Top.gg API!')
        
    return commands.check(predicate)

async def check_vote(user_id: int, bot_id: int = None):
    token = os.getenv('topggtoken')
    if not token:
        return False
    if not token.startswith('Bearer '):
        token = f'Bearer {token}'
    headers = {'Authorization': token}
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            url = f'https://top.gg/api/v1/projects/@me/votes/{user_id}?source=discord'
            async with session.get(url) as response:
                return response.status == 200
        except Exception:
            return False

def has_registered():
    async def predicate(ctx):
        data = await db.user.find_unique(where={'id': ctx.author.id})
        if not data:
            raise NoGameAccount('User has no game account!')
        return True
    
    return commands.check(predicate)

def is_premium():
    async def predicate(ctx):
        try:
            user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
            lang = user_settings.lang if user_settings else "en"
        except:
            lang = "en"
        user = await db.user.find_unique(where={'id': ctx.author.id})
        if not user or not user.premiumUntil:
            raise NoPremiumStatus(i18n.get(lang, "errors.premium_exclusive"))
        if user.premiumUntil < datetime.now(timezone.utc):
            raise NoPremiumStatus(i18n.get(lang, "errors.premium_expired"))
        return True
    return commands.check(predicate)


# def buy_item(ctx:commands.Context):

def titlecase(word):
    if word.isupper():
        return word
    if len(word) == 0:
        return word
    return word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()

def smart_title_case(text: str) -> str:
    """
    Title cases a string while keeping common conjunctions and prepositions in lowercase,
    unless they are the first or last word. Always preserves "RVDiA" case-insensitively.
    """
    import re
    
    conjunctions = {
        # Indonesian
        'dan', 'atau', 'tetapi', 'namun', 'ke', 'di', 'dari', 'pada', 'untuk', 'oleh', 'dengan', 
        'sebagai', 'adalah', 'yang', 'itu', 'ini', 'oleh',
        # English
        'and', 'or', 'but', 'nor', 'the', 'a', 'an', 'of', 'to', 'in', 'on', 'for', 'by', 'with', 'as', 'is', 'at'
    }
    words = text.split()
    if not words:
        return ""
    
    result = []
    for i, word in enumerate(words):
        # Always capitalize first and last word
        if i == 0 or i == len(words) - 1:
            result.append(titlecase(word))
        elif word.lower() in conjunctions:
            result.append(word.lower())
        else:
            result.append(titlecase(word))
            
    res_str = " ".join(result)
    res_str = re.sub(r'(?i)\brvdia\b', 'RVDiA', res_str)
    return res_str


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
    try:
        user_settings = await db.usersettings.find_unique(where={'userId': ctx.author.id})
        lang = user_settings.lang if user_settings else "en"
    except:
        lang = "en"
    msg = i18n.get(lang, "errors.command_disabled")
    await ctx.reply(msg)


def get_commands_context(bot) -> str:
    """Dynamically generates a list of available commands for LLM context."""
    lines = ["[AVAILABLE BOT COMMANDS]"]
    lines.append("Berikut adalah daftar command yang tersedia untuk user. Jika user bertanya tentang cara menggunakan fitur ini atau salah ketik, arahkan mereka untuk menggunakan command ini secara langsung (gunakan format /nama_command):")
    for cmd in bot.commands:
        if cmd.hidden:
            continue
        desc = cmd.description or cmd.help or ""
        desc = desc.strip().split('\n')[0]
        aliases_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"- `/{cmd.name}`{aliases_str}: {desc}")
    return "\n".join(lines)

def clean_truncate(text: str, max_char: int = 3800) -> str:
    """Gracefully truncates text at the last complete sentence within max_char."""
    if not text or len(text) <= max_char:
        return text
    
    truncated = text[:max_char]
    # Find the last sentence-ending punctuation mark
    last_punc = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_punc != -1:
        return truncated[:last_punc + 1] + " ..."
    return truncated + " ..."