"""
Ko-fi Webhook Handler.
Receives donation/subscription events from Ko-fi and auto-grants premiumUntil.

Verification:
  Ko-fi sends `application/x-www-form-urlencoded` with a `data` field (JSON string).
  The parsed `verification_token` field is compared against KOFI_VERIFICATION_TOKEN env var.

Discord ID convention:
  Donor writes their numeric Discord ID anywhere in the 'message' field.
  Extracted via regex `\b\d{17,20}\b`.

Amount tiers (USD):
  >= $2.00  → 60 days
  >= $1.00  → 30 days
  < $1.00   → ignored
"""

import os
import re
import logging
from datetime import datetime, timedelta, timezone

from aiohttp import web
from scripts.main import db

log = logging.getLogger(__name__)

DISCORD_ID_PATTERN = re.compile(r'\b(\d{17,20})\b')

TIER_MAP_USD = [
    (2.00, 60),
    (1.00, 30),
]


def _resolve_days_usd(amount: float) -> int:
    for threshold, days in TIER_MAP_USD:
        if amount >= threshold:
            return days
    return 0


async def _grant_premium(bot, user_id: int, days: int, from_name: str, amount: float, currency: str):
    user_record = await db.user.find_unique(where={'id': user_id})
    if not user_record:
        log.warning(f"Ko-fi: Discord ID {user_id} not found in DB.")
        return False

    now = datetime.now(timezone.utc)
    existing = user_record.premiumUntil
    if existing and existing.tzinfo is None:
        existing = existing.replace(tzinfo=timezone.utc)

    base = existing if (existing and existing > now) else now
    new_expiry = base + timedelta(days=days)

    await db.user.update(where={'id': user_id}, data={'premiumUntil': new_expiry})

    try:
        discord_user = await bot.fetch_user(user_id)
        ts = int(new_expiry.timestamp())
        await discord_user.send(
            f"💎 **Thank you, {from_name}!**\n"
            f"Your Ko-fi support of **{currency} {amount:.2f}** has been received.\n"
            f"Your **Dream Weaver** status is active until <t:{ts}:F>! 🌟\n\n"
            f"Enjoy all the premium perks in Re:Volution ~"
        )
    except Exception as e:
        log.warning(f"Ko-fi: Could not DM user {user_id}: {e}")

    return True


async def _alert_owner(bot, reason: str, from_name: str, amount: float, currency: str, message: str):
    owner_id_str = os.getenv('schryzonid')
    if not owner_id_str:
        return
    try:
        owner = await bot.fetch_user(int(owner_id_str))
        await owner.send(
            f"⚠️ **Ko-fi: Manual Review Needed**\n"
            f"**From:** {from_name}\n"
            f"**Amount:** {currency} {amount:.2f}\n"
            f"**Message:** {message or '(empty)'}\n"
            f"**Reason:** {reason}\n\n"
            f"Use `approve_premium <user_id>` to manually approve."
        )
    except Exception as e:
        log.error(f"Ko-fi: Could not DM owner: {e}")


async def handle_kofi_webhook(request: web.Request) -> web.Response:
    verification_token = os.getenv('KOFI_VERIFICATION_TOKEN')
    if not verification_token:
        log.error("Ko-fi: KOFI_VERIFICATION_TOKEN not set. Rejecting webhook.")
        return web.Response(status=500, text="Webhook not configured.")

    # Ko-fi sends form-encoded body with a `data` JSON string
    try:
        form = await request.post()
        import json
        payload = json.loads(form.get('data', '{}'))
    except Exception:
        return web.Response(status=400, text="Invalid payload.")

    # ── Verification ──────────────────────────────────────────
    received_token = payload.get('verification_token', '')
    if received_token != verification_token:
        log.warning("Ko-fi: Verification token mismatch.")
        return web.Response(status=403, text="Invalid verification token.")

    event_type = payload.get('type', '')
    if event_type not in ('Donation', 'Subscription'):
        return web.json_response({'ok': True, 'note': f'Event type {event_type!r} ignored.'})

    from_name = payload.get('from_name', 'Anonymous')
    message = payload.get('message', '') or ''
    currency = payload.get('currency', 'USD')
    bot = request.app['bot']

    try:
        amount = float(payload.get('amount', 0))
    except (TypeError, ValueError):
        amount = 0.0

    # ── Tier check ────────────────────────────────────────────
    days = _resolve_days_usd(amount)
    if days == 0:
        log.info(f"Ko-fi: Donation from {from_name} ({currency} {amount}) below minimum tier. Ignored.")
        return web.json_response({'ok': True, 'note': 'Below minimum tier.'})

    # ── Extract Discord ID ────────────────────────────────────
    match = DISCORD_ID_PATTERN.search(message)
    if not match:
        log.warning(f"Ko-fi: No Discord ID found in message from {from_name}.")
        await _alert_owner(bot, "No Discord ID in donation message.", from_name, amount, currency, message)
        return web.json_response({'ok': True, 'note': 'No Discord ID found — owner notified.'})

    discord_id = int(match.group(1))

    granted = await _grant_premium(bot, discord_id, days, from_name, amount, currency)
    if not granted:
        await _alert_owner(bot, f"Discord ID {discord_id} has no Re:Volution account.", from_name, amount, currency, message)

    log.info(f"Ko-fi: Granted {days}d premium to {discord_id} from {from_name} ({currency} {amount}).")
    return web.json_response({'ok': True, 'days_granted': days})
