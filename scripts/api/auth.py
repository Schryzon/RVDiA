"""
Discord OAuth2 Authentication + Session Management
Uses HMAC-signed cookies for stateless sessions.
"""

import os
import json
import hmac
import hashlib
import time
import base64
import logging
from urllib.parse import urlencode
from aiohttp import web, ClientSession


DISCORD_API = "https://discord.com/api/v10"
SESSION_COOKIE = "rvdia_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


def _get_secret():
    secret = os.getenv("SESSION_SECRET", os.getenv("INTERNAL_API_KEY", ""))
    if not secret:
        logging.warning("SESSION_SECRET is not set! Using fallback.")
        secret = "rvdia-fallback-dev-secret"
    return secret.encode()


def _sign_payload(payload: dict) -> str:
    """Sign a JSON payload with HMAC-SHA256, return base64 cookie value."""
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    sig = hmac.new(_get_secret(), raw.encode(), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{raw}|{sig}".encode()).decode()
    return token


def _verify_payload(token: str) -> dict | None:
    """Verify and decode a signed cookie. Returns None if invalid."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        raw, sig = decoded.rsplit('|', 1)
        expected = hmac.new(_get_secret(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(raw)

        # check expiry
        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def get_session(request: web.Request) -> dict | None:
    """Extract and verify the session from the request cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return _verify_payload(token)


def require_auth(handler):
    """Decorator that returns 401 if no valid session exists."""
    async def wrapper(request: web.Request):
        session = get_session(request)
        if not session:
            return web.json_response({"error": "Unauthorized"}, status=401)
        request["session"] = session
        return await handler(request)
    return wrapper


# ── OAuth Routes ─────────────────────────────────────────────

async def handle_oauth_login(request: web.Request):
    """Redirect to Discord's OAuth2 authorization page."""
    client_id = os.getenv("DISCORD_CLIENT_ID", "")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/api/auth/callback")

    params = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
    })

    raise web.HTTPFound(f"{DISCORD_API}/oauth2/authorize?{params}")


async def handle_oauth_callback(request: web.Request):
    """Exchange authorization code for access token, create session."""
    code = request.query.get("code")
    if not code:
        raise web.HTTPBadRequest(text="Missing authorization code.")

    client_id = os.getenv("DISCORD_CLIENT_ID", "")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/api/auth/callback")

    # exchange code for token
    async with ClientSession() as http:
        token_resp = await http.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_resp.status != 200:
            err_text = await token_resp.text()
            logging.error(f"OAuth token exchange failed: {err_text}")
            raise web.HTTPBadRequest(text="Failed to exchange authorization code.")

        token_data = await token_resp.json()
        access_token = token_data["access_token"]

        # fetch user info
        user_resp = await http.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status != 200:
            raise web.HTTPBadRequest(text="Failed to fetch user info.")

        user_data = await user_resp.json()

    # build session payload
    user_id = int(user_data["id"])
    avatar_hash = user_data.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size=128"
        if avatar_hash
        else f"https://cdn.discordapp.com/embed/avatars/{int(user_data.get('discriminator', '0')) % 5}.png"
    )

    session_payload = {
        "user_id": user_id,
        "username": user_data.get("global_name") or user_data["username"],
        "avatar_url": avatar_url,
        "access_token": access_token,
        "exp": int(time.time()) + SESSION_MAX_AGE,
    }

    # set signed cookie and redirect to dashboard
    lang = request.query.get("lang", "en")
    response = web.HTTPFound(f"/dashboard?lang={lang}")
    response.set_cookie(
        SESSION_COOKIE,
        _sign_payload(session_payload),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    raise response


async def handle_oauth_logout(request: web.Request):
    """Clear session cookie and redirect to home."""
    lang = request.query.get("lang", "en")
    response = web.HTTPFound(f"/?lang={lang}")
    response.del_cookie(SESSION_COOKIE, path="/")
    raise response


async def handle_auth_me(request: web.Request):
    """Return current session user info as JSON."""
    session = get_session(request)
    if not session:
        return web.json_response({"logged_in": False}, status=200)

    return web.json_response({
        "logged_in": True,
        "user_id": session["user_id"],
        "username": session["username"],
        "avatar_url": session["avatar_url"],
    })


def setup_auth_routes(app: web.Application):
    """Register all OAuth routes onto the app."""
    app.router.add_get("/api/auth/login", handle_oauth_login)
    app.router.add_get("/api/auth/callback", handle_oauth_callback)
    app.router.add_get("/api/auth/logout", handle_oauth_logout)
    app.router.add_get("/api/auth/me", handle_auth_me)
