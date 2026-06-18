"""
REST API endpoints for the RVDiA Web Dashboard.
Protected by session-based authentication.
"""

import time
import logging
from aiohttp import web
from scripts.api_auth import require_auth, get_session
from scripts.main import db
from scripts.chat_service import chat_service


# ── User Profile ─────────────────────────────────────────────

@require_auth
async def handle_user_profile(request: web.Request):
    """GET /api/v1/user/profile — Returns RPG profile for the logged-in user."""
    session = request["session"]
    user_id = session["user_id"]

    user = await db.user.find_unique(
        where={"id": user_id},
        include={"guild": True}
    )

    if not user:
        return web.json_response({
            "registered": False,
            "message": "No Re:Volution account found. Use /game register in Discord to create one."
        })

    data = user.data
    guild_info = None
    if user.guild:
        guild_info = {
            "id": user.guild.id,
            "name": user.guild.name,
            "tagline": user.guild.tagline,
            "icon_url": user.guild.iconUrl,
        }

    return web.json_response({
        "registered": True,
        "profile": {
            "name": data.get("name", "Player"),
            "level": data.get("level", 1),
            "exp": data.get("exp", 0),
            "next_exp": data.get("next_exp", 50),
            "coins": data.get("coins", 0),
            "karma": data.get("karma", 0),
            "hp": user.hp,
            "max_hp": user.max_hp,
            "attack": data.get("attack", 10),
            "defense": data.get("defense", 7),
            "agility": data.get("agility", 8),
            "premium_until": user.premiumUntil.isoformat() if user.premiumUntil else None,
        },
        "guild": guild_info,
    })


# ── Inventory ────────────────────────────────────────────────

@require_auth
async def handle_user_inventory(request: web.Request):
    """GET /api/v1/user/inventory — Returns inventory for the logged-in user."""
    session = request["session"]
    user_id = session["user_id"]

    user = await db.user.find_unique(
        where={"id": user_id},
        include={"inventory": True}
    )

    if not user:
        return web.json_response({"registered": False})

    if not user.inventory:
        return web.json_response({
            "registered": True,
            "inventory": {"items": {}, "skills": {}, "equipments": []}
        })

    return web.json_response({
        "registered": True,
        "inventory": {
            "items": user.inventory.items or {},
            "skills": user.inventory.skills or {},
            "equipments": user.inventory.equipments or [],
        }
    })


# ── Bot Stats ────────────────────────────────────────────────

async def handle_bot_stats(request: web.Request):
    """GET /api/v1/stats — Public endpoint returning bot-wide statistics."""
    bot = request.app.get("bot")

    server_count = len(bot.guilds) if bot else 0
    user_count = sum(g.member_count for g in bot.guilds) if bot else 0
    uptime_seconds = int(time.time() - bot.runtime) if bot else 0

    # count memories and messages
    try:
        memory_count = await db.memory.count()
        message_count = await db.message.count()
    except Exception as e:
        logging.warning(f"Failed to count memories/messages: {e}")
        memory_count = 0
        message_count = 0

    return web.json_response({
        "servers": server_count,
        "users": user_count,
        "uptime_seconds": uptime_seconds,
        "memories": memory_count,
        "messages": message_count,
        "version": bot.__version__ if bot else "Unknown",
    })


# ── Web Chat ─────────────────────────────────────────────────

@require_auth
async def handle_web_chat(request: web.Request):
    """POST /api/v1/chat — Send a message to RVDiA and get a response."""
    session = request["session"]
    user_id = session["user_id"]
    username = session["username"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body."}, status=400)

    message = body.get("message", "").strip()
    lang = body.get("lang", "en")

    if not message:
        return web.json_response({"error": "Message cannot be empty."}, status=400)

    if len(message) > 2000:
        return web.json_response({"error": "Message too long (max 2000 chars)."}, status=400)

    try:
        result = await chat_service.generate_chat_response(
            user_id=user_id,
            user_name=username,
            message=message,
            lang=lang,
        )
        return web.json_response({
            "response": result["response"],
            "image_url": result.get("image_url"),
        })
    except Exception as e:
        logging.error(f"Web chat error for user {user_id}: {e}", exc_info=True)
        return web.json_response({"error": "Failed to generate response."}, status=500)


# ── Route Registration ───────────────────────────────────────

def setup_api_routes(app: web.Application):
    """Register all API routes onto the app."""
    app.router.add_get("/api/v1/user/profile", handle_user_profile)
    app.router.add_get("/api/v1/user/inventory", handle_user_inventory)
    app.router.add_get("/api/v1/stats", handle_bot_stats)
    app.router.add_post("/api/v1/chat", handle_web_chat)
