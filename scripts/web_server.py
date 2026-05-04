import json
import os
import aiohttp_jinja2
import jinja2
import hmac
import hashlib
import re
from datetime import datetime, timedelta
from aiohttp import web
from scripts.main import db

def load_locales():
    locales = {}
    locales_dir = os.path.join(os.path.dirname(__file__), '../website/locales')
    for filename in os.listdir(locales_dir):
        if filename.endswith('.json'):
            lang_code = filename[:-5]
            with open(os.path.join(locales_dir, filename), 'r', encoding='utf-8') as f:
                locales[lang_code] = json.load(f)
    return locales

locales_data = load_locales()

def get_i18n(request):
    lang = request.query.get('lang', 'id')
    if lang not in locales_data:
        lang = 'id'
    return locales_data[lang], lang

async def handle_home(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('index.html', request, {
        'i18n': i18n,
        'lang': lang
    })

async def handle_commands(request):
    i18n, lang = get_i18n(request)
    bot = request.app['bot']
    
    # Extract dynamic commands from discord.py bot instance
    cmd_list = []
    for cmd in bot.commands:
        if not cmd.hidden:
            cmd_list.append({
                'name': cmd.name,
                'cog_name': cmd.cog_name or 'Uncategorized',
                'help': cmd.help.strip() if cmd.help else None
            })
            
    # Sort commands by cog name then command name
    cmd_list.sort(key=lambda x: (x['cog_name'], x['name']))

    return aiohttp_jinja2.render_template('commands.html', request, {
        'i18n': i18n,
        'lang': lang,
        'commands': cmd_list
    })

async def handle_privacy(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('privacy.html', request, {
        'i18n': i18n,
        'lang': lang
    })

async def handle_terms(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('terms.html', request, {
        'i18n': i18n,
        'lang': lang
    })

async def handle_saweria(request):
    # (Leaving placeholder or removing as per previous turn)
    return web.Response(text="OK")

async def handle_internal_dm(request):
    # Only allow from localhost for security
    if request.remote != '127.0.0.1' and request.remote != 'localhost':
        return web.Response(text="Unauthorized", status=401)
        
    try:
        data = await request.json()
        user_id = data.get('user_id')
        message = data.get('message')
        
        bot = request.app['bot']
        user = await bot.fetch_user(user_id)
        if user:
            await user.send(message)
            return web.Response(text="OK")
        return web.Response(text="User not found", status=404)
    except Exception as e:
        return web.Response(text=str(e), status=500)

async def start_web_server(bot):
    app = web.Application()
    app['bot'] = bot
    
    # Setup Jinja2 templating
    templates_dir = os.path.join(os.path.dirname(__file__), '../website/templates')
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(templates_dir))
    
    # Setup Static Files serving
    static_dir = os.path.join(os.path.dirname(__file__), '../website/static')
    app.router.add_static('/static/', path=static_dir, name='static')
    
    # Setup Routes
    app.router.add_get('/', handle_home)
    app.router.add_get('/commands', handle_commands)
    app.router.add_get('/privacy', handle_privacy)
    app.router.add_get('/terms', handle_terms)
    app.router.add_post('/internal/dm', handle_internal_dm)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🚀 Web server started on port {port}")
