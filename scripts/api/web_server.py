import json
import os
import aiohttp_jinja2
import jinja2
import hmac
import hashlib
import re
from datetime import datetime, timedelta
from aiohttp import web
from discord.ext import commands
from scripts.main import db
from scripts.api.auth import setup_auth_routes, get_session
from scripts.api.routes import setup_api_routes

def load_locales():
    locales = {}
    locales_dir = os.path.join(os.path.dirname(__file__), '../../website/locales')
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

def _get_user_ctx(request):
    """Build user context dict for templates (logged-in state)."""
    session = get_session(request)
    if session:
        return {
            "logged_in": True,
            "username": session["username"],
            "avatar_url": session["avatar_url"],
            "user_id": session["user_id"],
        }
    return {"logged_in": False}

async def handle_home(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('index.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': _get_user_ctx(request),
    })

async def handle_commands(request):
    i18n, lang = get_i18n(request)
    bot = request.app['bot']
    
    # Extract dynamic commands grouped by category
    categories = {}
    
    # Process prefix commands
    for cmd in bot.commands:
        if cmd.hidden:
            continue
            
        cog_name = cmd.cog_name or 'Uncategorized'
        if cog_name not in categories:
            categories[cog_name] = []
            
        cmd_info = {
            'name': cmd.name,
            'description': cmd.help.strip() if cmd.help else None,
            'aliases': cmd.aliases,
            'subcommands': []
        }
        
        if isinstance(cmd, commands.Group):
            for sub in cmd.commands:
                if not sub.hidden:
                    cmd_info['subcommands'].append({
                        'name': sub.name,
                        'description': sub.help.strip() if sub.help else None,
                        'aliases': sub.aliases
                    })
        
        categories[cog_name].append(cmd_info)
            
    # Sort categories and commands within them
    sorted_categories = []
    for cat_name in sorted(categories.keys()):
        cmds = sorted(categories[cat_name], key=lambda x: x['name'])
        sorted_categories.append({
            'name': cat_name,
            'commands': cmds
        })

    return aiohttp_jinja2.render_template('commands.html', request, {
        'i18n': i18n,
        'lang': lang,
        'categories': sorted_categories,
        'user': _get_user_ctx(request),
    })

async def handle_privacy(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('privacy.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': _get_user_ctx(request),
    })

async def handle_terms(request):
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('terms.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': _get_user_ctx(request),
    })

async def handle_license(request):
    i18n, lang = get_i18n(request)
    
    # Read the LICENSE file
    license_path = os.path.join(os.path.dirname(__file__), '../../LICENSE')
    try:
        with open(license_path, 'r', encoding='utf-8') as f:
            license_content = f.read()
    except:
        license_content = "License file not found."

    return aiohttp_jinja2.render_template('license.html', request, {
        'i18n': i18n,
        'lang': lang,
        'license_content': license_content,
        'user': _get_user_ctx(request),
    })

async def handle_saweria(request):
    # (Leaving placeholder or removing as per previous turn)
    return web.Response(text="OK")

async def handle_internal_dm(request):
    internal_key = request.headers.get("X-Internal-Key")
    expected_key = os.getenv("INTERNAL_API_KEY")
    if not expected_key or not internal_key or not hmac.compare_digest(internal_key, expected_key):
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
        import logging
        logging.error(f"Error in handle_internal_dm: {e}", exc_info=True)
        return web.Response(text="Internal Server Error", status=500)


# ── Dashboard Pages ──────────────────────────────────────────

async def handle_login_page(request):
    """Render the login page."""
    i18n, lang = get_i18n(request)
    user_ctx = _get_user_ctx(request)

    # already logged in? redirect to dashboard
    if user_ctx.get("logged_in"):
        raise web.HTTPFound(f"/dashboard?lang={lang}")

    return aiohttp_jinja2.render_template('login.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': user_ctx,
    })

async def handle_dashboard(request):
    """Render the dashboard page (requires login)."""
    i18n, lang = get_i18n(request)
    user_ctx = _get_user_ctx(request)

    # not logged in? redirect to login
    if not user_ctx.get("logged_in"):
        raise web.HTTPFound(f"/login?lang={lang}")

    return aiohttp_jinja2.render_template('dashboard.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': user_ctx,
    })


async def handle_widget_demo(request):
    """Render the chat widget demo page."""
    i18n, lang = get_i18n(request)
    return aiohttp_jinja2.render_template('widget_demo.html', request, {
        'i18n': i18n,
        'lang': lang,
        'user': _get_user_ctx(request),
    })


@web.middleware
async def security_headers_middleware(request: web.Request, handler):
    # CORS preflight handling for cross-origin integration
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Internal-Key, Authorization"
        return response
        
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex
        
    # Apply baseline security headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Configure Content Security Policy (CSP) for HTML pages
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://cdn.discordapp.com; "
            "connect-src 'self' https://cdn.tailwindcss.com;"
        )
        response.headers["Content-Security-Policy"] = csp
        
    # Apply CORS to public API endpoints
    path = request.path
    if path.startswith("/api/v1/chat") or path.startswith("/api/v1/public/") or path.startswith("/api/v1/stats"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Internal-Key, Authorization"
        
    return response


async def start_web_server(bot):
    app = web.Application(middlewares=[security_headers_middleware])
    app['bot'] = bot
    
    # Setup Jinja2 templating
    templates_dir = os.path.join(os.path.dirname(__file__), '../../website/templates')
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(templates_dir))
    
    # Setup Static Files serving
    static_dir = os.path.join(os.path.dirname(__file__), '../../website/static')
    app.router.add_static('/static/', path=static_dir, name='static')
    
    # Setup Auth & API Routes
    setup_auth_routes(app)
    setup_api_routes(app)

    # Setup Page Routes
    app.router.add_get('/', handle_home)
    app.router.add_get('/commands', handle_commands)
    app.router.add_get('/privacy', handle_privacy)
    app.router.add_get('/terms', handle_terms)
    app.router.add_get('/license', handle_license)
    app.router.add_get('/login', handle_login_page)
    app.router.add_get('/dashboard', handle_dashboard)
    app.router.add_get('/widget-demo', handle_widget_demo)
    app.router.add_post('/internal/dm', handle_internal_dm)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🚀 Web server started on port {port}")
