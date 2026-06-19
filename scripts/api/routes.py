"""
REST API endpoints for the RVDiA Web Dashboard.
Protected by session-based authentication.
"""

import time
import logging
from aiohttp import web
from scripts.api.auth import require_auth, get_session
from scripts.main import db
from scripts.ai.chat import chat_service


import random
from datetime import datetime, timedelta
from prisma import Json
from scripts.game.game import level_up, give_rewards

# Mock classes for Discord models to call give_rewards / level_up without Discord connection dependencies
class MockMember:
    def __init__(self, id_val):
        self.id = id_val

class MockChannel:
    async def send(self, *args, **kwargs):
        pass

class MockCtx:
    def __init__(self, user_id):
        self.author = MockMember(user_id)
        self.channel = MockChannel()


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


async def handle_public_web_chat(request: web.Request):
    """POST /api/v1/public/chat — Public session-based chat endpoint.
    Bypasses standard Discord OAuth authentication.
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body."}, status=400)

    session_id = body.get("session_id", "").strip()
    message = body.get("message", "").strip()
    lang = body.get("lang", "en")

    if not session_id:
        return web.json_response({"error": "Missing session_id."}, status=400)

    if len(session_id) > 100:
        return web.json_response({"error": "session_id is too long."}, status=400)

    if not message:
        return web.json_response({"error": "Message cannot be empty."}, status=400)

    if len(message) > 2000:
        return web.json_response({"error": "Message too long (max 2000 chars)."}, status=400)

    import hashlib
    sha256 = hashlib.sha256(session_id.encode("utf-8")).digest()
    virtual_user_id = int.from_bytes(sha256[:8], byteorder="big", signed=True) & 0x7FFFFFFFFFFFFFFF

    try:
        result = await chat_service.generate_chat_response(
            user_id=virtual_user_id,
            user_name="Guest",
            message=message,
            lang=lang,
        )
        return web.json_response({
            "response": result["response"],
            "image_url": result.get("image_url"),
        })
    except Exception as e:
        logging.error(f"Public web chat error for session {session_id} (virtual user {virtual_user_id}): {e}", exc_info=True)
        return web.json_response({"error": "Failed to generate response."}, status=500)



# ── RPG Actions ──────────────────────────────────────────────

@require_auth
async def handle_user_daily(request: web.Request):
    """POST /api/v1/user/daily — Claims daily reward for the logged-in user."""
    session = request["session"]
    user_id = session["user_id"]

    user_record = await db.user.find_unique(where={'id': user_id})
    if not user_record:
        return web.json_response({"error": "No RPG account found."}, status=404)

    data = user_record.data
    last_login_raw = data.get('last_login')
    if not last_login_raw:
        last_login = datetime.now() - timedelta(days=1)
    elif isinstance(last_login_raw, str):
        last_login = datetime.fromisoformat(last_login_raw)
    else:
        last_login = last_login_raw

    current_time = datetime.now()
    delta_time = current_time - last_login

    if delta_time.total_seconds() <= 24 * 60 * 60:
        next_login = last_login + timedelta(hours=24)
        next_login_unix = int(time.mktime(next_login.timetuple()))
        return web.json_response({
            "claimed": False,
            "on_cooldown": True,
            "next_claim_timestamp": next_login_unix
        })

    new_coins = random.randint(15, 25)
    new_karma = random.randint(1, 5)
    new_exp = random.randint(10, 20)

    data['coins'] += new_coins
    data['karma'] += new_karma
    data['exp'] += new_exp
    data['last_login'] = current_time.isoformat()

    await db.user.update(
        where={'id': user_id},
        data={'data': Json(data)}
    )

    mock_member = MockMember(user_id)
    leveled_up = await level_up(mock_member)

    return web.json_response({
        "claimed": True,
        "on_cooldown": False,
        "rewards": {
            "coins": new_coins,
            "karma": new_karma,
            "exp": new_exp
        },
        "leveled_up": leveled_up
    })

@require_auth
async def handle_user_adventure(request: web.Request):
    """POST /api/v1/user/adventure — Simulates an adventure and grants rewards."""
    session = request["session"]
    user_id = session["user_id"]

    user_record = await db.user.find_unique(where={'id': user_id})
    if not user_record:
        return web.json_response({"error": "No RPG account found."}, status=404)

    exp_gain = random.randint(10, 25)
    coin_gain = random.randint(15, 35)

    mock_ctx = MockCtx(user_id)
    mock_user = MockMember(user_id)
    
    await give_rewards(mock_ctx, mock_user, exp_gain, coin_gain)
    updated_user = await db.user.find_unique(where={'id': user_id})

    return web.json_response({
        "success": True,
        "rewards": {
            "exp": exp_gain,
            "coins": coin_gain
        },
        "new_level": updated_user.data.get("level", 1) if updated_user else 1
    })

@require_auth
async def handle_user_equip(request: web.Request):
    """POST /api/v1/user/equip — Equips or unequips an item."""
    session = request["session"]
    user_id = session["user_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body."}, status=400)

    item_id = body.get("item_id")
    if not item_id:
        return web.json_response({"error": "Missing item_id parameter."}, status=400)

    user_record = await db.user.find_unique(
        where={'id': user_id},
        include={'inventory': True}
    )
    if not user_record or not user_record.inventory:
        return web.json_response({"error": "User inventory not found."}, status=404)

    data = user_record.data
    inventory = user_record.inventory

    def convert_to_db_stat_key(short_stat):
        mapping = {
            'ATK': 'attack',
            'DEF': 'defense',
            'AGL': 'agility',
            'HP': 'hp'
        }
        return mapping.get(short_stat.upper(), short_stat.lower())

    equipments = inventory.equipments if isinstance(inventory.equipments, list) else []
    all_items = inventory.items if isinstance(inventory.items, list) else []

    matching = [x for x in equipments if x['_id'] == item_id]

    action = ""
    item_name = ""

    if matching:
        # Unequip
        action = "unequip"
        item_to_unequip = matching[0]
        item_name = item_to_unequip.get('name', item_id)
        func = item_to_unequip['func'].split('+')
        stat_key = convert_to_db_stat_key(func[0])
        stat_value = int(func[1])

        new_equipments = [x for x in equipments if x['_id'] != item_id]
        data[stat_key] -= stat_value

        await db.user.update(
            where={'id': user_id},
            data={
                'data': Json(data),
                'inventory': {
                    'update': {'equipments': Json(new_equipments)}
                }
            }
        )
    else:
        # Equip
        action = "equip"
        item_match = [x for x in all_items if x['_id'] == item_id]
        if not item_match:
            return web.json_response({"error": "Item not found in inventory."}, status=404)

        item_to_equip = item_match[0]
        item_name = item_to_equip.get('name', item_id)
        func = item_to_equip['func'].split('+')
        stat_key = convert_to_db_stat_key(func[0])
        stat_value = int(func[1])

        same_type = [x for x in equipments if x.get('usefor') == item_to_equip.get('usefor')]
        if same_type:
            old_item = same_type[0]
            old_func = old_item['func'].split('+')
            old_stat_key = convert_to_db_stat_key(old_func[0])
            data[old_stat_key] -= int(old_func[1])
            equipments = [x for x in equipments if x['_id'] != old_item['_id']]

        equipments.append(item_to_equip)
        data[stat_key] += stat_value

        await db.user.update(
            where={'id': user_id},
            data={
                'data': Json(data),
                'inventory': {
                    'update': {'equipments': Json(equipments)}
                }
            }
        )

    return web.json_response({
        "success": True,
        "action": action,
        "item_name": item_name,
        "stats": {
            "attack": data.get("attack"),
            "defense": data.get("defense"),
            "agility": data.get("agility")
        }
    })


def load_shop_file():
    import json
    import os
    shop_path = os.path.join(os.path.dirname(__file__), "../../src/game/shop.json")
    if os.path.exists(shop_path):
        with open(shop_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@require_auth
async def handle_shop_items(request: web.Request):
    """GET /api/v1/shop — Returns shop items with owned count for the user."""
    session = request["session"]
    user_id = session["user_id"]

    user_record = await db.user.find_unique(
        where={"id": user_id},
        include={"inventory": True}
    )
    if not user_record:
        return web.json_response({"error": "No RPG account found."}, status=404)

    inventory = user_record.inventory
    user_items = inventory.items if inventory and isinstance(inventory.items, list) else []
    user_skills = inventory.skills if inventory and isinstance(inventory.skills, list) else []
    user_equipments = inventory.equipments if inventory and isinstance(inventory.equipments, list) else []

    owned_map = {}
    for item in user_items:
        owned_map[item.get("_id")] = item.get("owned", 0)
    for skill in user_skills:
        owned_map[skill.get("_id")] = 1
    for eq in user_equipments:
        owned_map[eq.get("_id")] = 1

    from scripts.utils.i18n import i18n
    lang = request.query.get("lang", "id")
    if lang not in ["en", "id"]:
        user_settings = await db.usersettings.find_unique(where={"userId": user_id})
        lang = user_settings.lang if user_settings else "id"

    shop_items = load_shop_file()
    for item in shop_items:
        item["owned"] = owned_map.get(item["_id"], 0)
        item["name"] = i18n.get(lang, f"game.item_{item['_id']}_name", default=item.get("name", ""))
        item["desc"] = i18n.get(lang, f"game.item_{item['_id']}_desc", default="")

    return web.json_response({
        "success": True,
        "items": shop_items
    })


@require_auth
async def handle_shop_buy(request: web.Request):
    """POST /api/v1/shop/buy — Purchase an item from the shop."""
    session = request["session"]
    user_id = session["user_id"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body."}, status=400)

    item_id = body.get("item_id")
    if not item_id:
        return web.json_response({"error": "Missing item_id parameter."}, status=400)

    shop_items = load_shop_file()
    db_dict = {item["_id"]: item for item in shop_items}
    if item_id not in db_dict:
        return web.json_response({"error": "Item not found in shop."}, status=404)

    matched_item = db_dict[item_id]

    user_record = await db.user.find_unique(
        where={"id": user_id},
        include={"inventory": True}
    )
    if not user_record or not user_record.inventory:
        return web.json_response({"error": "RPG profile or inventory not found."}, status=404)

    data = user_record.data
    inventory = user_record.inventory
    
    currency_key = "coins" if matched_item["paywith"] == "Koin" else "karma"
    current_money = data.get(currency_key, 0)

    if current_money < matched_item["cost"]:
        currency_name = "coins" if currency_key == "coins" else "karma"
        return web.json_response({"error": f"Insufficient {currency_name}."}, status=400)

    user_items = inventory.items if isinstance(inventory.items, list) else []
    user_skills = inventory.skills if isinstance(inventory.skills, list) else []
    user_equipments = inventory.equipments if isinstance(inventory.equipments, list) else []

    target_field = "items"
    current_list = user_items

    if "1-" in item_id:
        target_field = "equipments"
        current_list = user_equipments
    elif "2-" in item_id:
        target_field = "skills"
        current_list = user_skills

    mongo_dict = {item["_id"]: item for item in current_list}
    if item_id in mongo_dict:
        if "1-" in item_id:
            return web.json_response({"error": "You already own this equipment."}, status=400)
        if "2-" in item_id:
            return web.json_response({"error": "You already learned this skill."}, status=400)
        
        for item in current_list:
            if item["_id"] == item_id:
                item["owned"] = item.get("owned", 0) + 1
                break
    else:
        new_item = matched_item.copy()
        new_item.pop("cost", None)
        new_item.pop("paywith", None)
        new_item["owned"] = 1
        current_list.append(new_item)

    data[currency_key] -= matched_item["cost"]

    await db.user.update(
        where={"id": user_id},
        data={
            "data": Json(data),
            "inventory": {
                "update": {target_field: Json(current_list)}
            }
        }
    )

    return web.json_response({
        "success": True,
        "item_name": matched_item["name"],
        "balance": {
            "coins": data.get("coins", 0),
            "karma": data.get("karma", 0)
        }
    })


# ── Route Registration ───────────────────────────────────────

def setup_api_routes(app: web.Application):
    """Register all API routes onto the app."""
    app.router.add_get("/api/v1/user/profile", handle_user_profile)
    app.router.add_get("/api/v1/user/inventory", handle_user_inventory)
    app.router.add_get("/api/v1/stats", handle_bot_stats)
    app.router.add_post("/api/v1/chat", handle_web_chat)
    app.router.add_post("/api/v1/public/chat", handle_public_web_chat)
    app.router.add_post("/api/v1/user/daily", handle_user_daily)
    app.router.add_post("/api/v1/user/adventure", handle_user_adventure)
    app.router.add_post("/api/v1/user/equip", handle_user_equip)
    app.router.add_get("/api/v1/shop", handle_shop_items)
    app.router.add_post("/api/v1/shop/buy", handle_shop_buy)
