"""
Saweria Webhook Handler.
Receives donation events from Saweria and auto-grants premiumUntil.

Signature algorithm:
  HMAC-SHA256( SAWERIA_STREAM_KEY, f"{version}{id}{amount_raw}{donator_name}{donator_email}" )
  Compared against the `saweria-callback-signature` header.

Discord ID convention:
  Donor writes their numeric Discord ID anywhere in the donation message.
  The handler extracts it via regex `\b\d{17,20}\b`.
"""

import os
import re
import hmac
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from aiohttp import web
from prisma import Json
from scripts.main import db

log = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────

DISCORD_ID_PATTERN = re.compile(r'\b(\d{17,20})\b')

TIER_MAP = [
    (30_000, 60),   # >= 30k IDR → 60 days
    (15_000, 30),   # >= 15k IDR → 30 days
]


def _compute_signature(stream_key: str, version: str, tx_id: str, amount_raw: int, donator_name: str, donator_email: str) -> str:
    raw = f"{version}{tx_id}{amount_raw}{donator_name}{donator_email}"
    return hmac.new(stream_key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _resolve_days(amount_raw: int) -> int:
    for threshold, days in TIER_MAP:
        if amount_raw >= threshold:
            return days
    return 0


async def _grant_premium(bot, user_id: int, days: int, donator_name: str, amount_raw: int):
    """Update DB and DM the user about their new premium status."""
    user_record = await db.user.find_unique(where={'id': user_id})
    if not user_record:
        log.warning(f"Saweria: Discord ID {user_id} not found in DB (no Re:Volution account).")
        return False

    now = datetime.now(timezone.utc)
    existing = user_record.premiumUntil
    if existing and existing.tzinfo is None:
        existing = existing.replace(tzinfo=timezone.utc)

    base = existing if (existing and existing > now) else now
    new_expiry = base + timedelta(days=days)

    await db.user.update(where={'id': user_id}, data={'premiumUntil': new_expiry})

    # DM the user
    try:
        discord_user = await bot.fetch_user(user_id)
        ts = int(new_expiry.timestamp())
        await discord_user.send(
            f"💎 **Terima kasih, {donator_name}!**\n"
            f"Donasi sebesar **Rp {amount_raw:,}** kamu telah diterima.\n"
            f"Status **Dream Weaver** kamu aktif hingga <t:{ts}:F>! 🌟\n\n"
            f"Nikmati semua keuntungan premium di Re:Volution ~"
        )
    except Exception as e:
        log.warning(f"Saweria: Could not DM user {user_id}: {e}")

    return True


async def _alert_owner(bot, reason: str, donator_name: str, amount_raw: int, message: str):
    """DM the bot owner when a donation needs manual review."""
    owner_id_str = os.getenv('schryzonid')
    if not owner_id_str:
        return
    try:
        owner = await bot.fetch_user(int(owner_id_str))
        await owner.send(
            f"⚠️ **Saweria: Manual Review Needed**\n"
            f"**Donatur:** {donator_name}\n"
            f"**Jumlah:** Rp {amount_raw:,}\n"
            f"**Pesan:** {message or '(kosong)'}\n"
            f"**Alasan:** {reason}\n\n"
            f"Gunakan `approve_premium <user_id>` untuk meng-approve secara manual."
        )
    except Exception as e:
        log.error(f"Saweria: Could not DM owner: {e}")


# ── Route Handler ─────────────────────────────────────────────

async def handle_saweria_webhook(request: web.Request) -> web.Response:
    stream_key = os.getenv('SAWERIA_SECRET')
    if not stream_key:
        log.error("Saweria: SAWERIA_SECRET not set. Rejecting webhook.")
        return web.Response(status=500, text="Webhook not configured.")

    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON payload.")

    # ── Signature verification ────────────────────────────────
    received_sig = request.headers.get('saweria-callback-signature', '')
    expected_sig = _compute_signature(
        stream_key,
        payload.get('version', ''),
        payload.get('id', ''),
        int(payload.get('amount_raw', 0)),
        payload.get('donator_name', ''),
        payload.get('donator_email', '')
    )

    if not hmac.compare_digest(received_sig.lower(), expected_sig.lower()):
        log.warning("Saweria: Signature mismatch — possible fake webhook.")
        return web.Response(status=403, text="Signature mismatch.")

    event_type = payload.get('type', '')
    if event_type != 'donation':
        return web.json_response({'ok': True, 'note': 'Non-donation event ignored.'})

    amount_raw = int(payload.get('amount_raw', 0))
    donator_name = payload.get('donator_name', 'Unknown')
    message = payload.get('message', '') or ''
    bot = request.app['bot']

    # ── Tier check ────────────────────────────────────────────
    days = _resolve_days(amount_raw)
    if days == 0:
        log.info(f"Saweria: Donation from {donator_name} (Rp {amount_raw}) below minimum tier. Ignored.")
        return web.json_response({'ok': True, 'note': 'Below minimum tier.'})

    # ── Extract Discord ID ────────────────────────────────────
    match = DISCORD_ID_PATTERN.search(message)
    if not match:
        log.warning(f"Saweria: No Discord ID found in message from {donator_name}.")
        await _alert_owner(bot, "No Discord ID in donation message.", donator_name, amount_raw, message)
        return web.json_response({'ok': True, 'note': 'No Discord ID found — owner notified.'})

    discord_id = int(match.group(1))

    granted = await _grant_premium(bot, discord_id, days, donator_name, amount_raw)
    if not granted:
        await _alert_owner(bot, f"Discord ID {discord_id} has no Re:Volution account.", donator_name, amount_raw, message)

    log.info(f"Saweria: Granted {days}d premium to {discord_id} from {donator_name} (Rp {amount_raw}).")
    return web.json_response({'ok': True, 'days_granted': days})
