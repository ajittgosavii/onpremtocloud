"""Sign-in gate: account store, password hashing, session lifetime.

Deliberately dependency-free -- PBKDF2-HMAC-SHA256 from hashlib, and hmac for
every comparison, so nothing new lands in requirements.txt and nothing new can
break a hosted deploy.

Accounts come from the first of these that yields anything:

  1. ``st.secrets["auth"]["users"]``  -- Streamlit Cloud, and .streamlit/secrets.toml
  2. ``APP_USERS`` in the environment  -- a JSON object, handy in a local .env
  3. a single demo account            -- so a fresh clone runs, with a warning

Each account record accepts ``password_hash`` (produced by tools_hashpw.py) or
``password`` in the clear. Use the hash anywhere the file is not purely local.

This module holds no Streamlit output. Presentation lives in core.login_ui, and
app.py wires the two together, which keeps core/ free of import cycles.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import time

import streamlit as st

from core import brand

# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------
ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 240_000
SALT_BYTES = 16

MAX_ATTEMPTS = 5              # consecutive failures before a cool-off
LOCK_SECONDS = 300            # length of that cool-off
IDLE_MINUTES = 480            # signed-out after this long with no interaction

# Lifetime of a "stay signed in" token. Deliberately hours, not days: Streamlit
# gives no cookie API, so the token has to ride in the URL, where it is a bearer
# credential sitting in browser history, in anything pasted from the address bar,
# and in the Referer of any outbound link clicked from the app. Twelve hours
# covers a working day of reloads, which is the whole point of the feature, and
# nothing more. See the "Signing in" section of the README.
REMEMBER_HOURS = 12

DEMO_USER = "demo"
DEMO_PASSWORD = "ascend"

_TOKEN_PARAM = "k"

_K_USER = "_auth_user"
_K_SEEN = "_auth_seen"
_K_FAILS = "_auth_fails"
_K_LOCK = "_auth_lock_until"
_K_NOTICE = "_auth_notice"


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(password: str, iterations: int = ITERATIONS,
                  salt: bytes | None = None) -> str:
    """Return a self-describing PBKDF2 string safe to paste into secrets.toml."""
    salt = salt if salt is not None else os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        ALGORITHM, iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"))


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check against a PBKDF2 string, or a plaintext password.

    Plaintext is accepted so a fresh clone and a quick local demo work without a
    hashing step, and because a hash pasted into the ``password`` key by mistake
    should still verify rather than silently fail.
    """
    if not isinstance(stored, str) or not stored:
        return False
    if stored.startswith(ALGORITHM + "$"):
        try:
            _, raw_iter, raw_salt, raw_hash = stored.split("$", 3)
            expected = base64.b64decode(raw_hash)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                         base64.b64decode(raw_salt), int(raw_iter))
        except (ValueError, binascii.Error):
            return False
        return hmac.compare_digest(digest, expected)
    return hmac.compare_digest(password.encode("utf-8"), stored.encode("utf-8"))


# --------------------------------------------------------------------------
# Account store
# --------------------------------------------------------------------------
def _secrets() -> dict:
    """``st.secrets['auth']`` as a plain dict, or {} when there is no secrets file.

    Reading st.secrets raises rather than returns empty when no file exists, and
    that must not be fatal: a fresh clone has no secrets and still has to run.
    """
    try:
        block = st.secrets["auth"]
    except Exception:
        return {}
    try:
        return dict(block)
    except Exception:
        return {}


def _normalise(raw: dict) -> dict:
    users = {}
    for username, record in raw.items():
        if isinstance(record, str):                 # users = { ajit = "password" }
            record = {"password": record}
        try:
            record = dict(record)
        except Exception:
            continue
        secret = record.get("password_hash") or record.get("password") or ""
        if not secret:
            continue
        users[str(username)] = {
            "username": str(username),
            "name": str(record.get("name") or username),
            "role": str(record.get("role") or "Consultant"),
            "secret": str(secret),
        }
    return users


def load_users() -> dict:
    """Every configured account, keyed by username. Never empty."""
    users = _normalise(_secrets().get("users") or {})
    if users:
        return users

    raw_env = os.environ.get("APP_USERS", "").strip()
    if raw_env:
        try:
            users = _normalise(json.loads(raw_env))
        except (ValueError, AttributeError):
            users = {}
        if users:
            return users

    return {DEMO_USER: {"username": DEMO_USER, "name": "Demo account",
                        "role": "Demo", "secret": DEMO_PASSWORD}}


def using_demo_account() -> bool:
    """True when nothing is configured and the built-in demo login is live."""
    return not _normalise(_secrets().get("users") or {}) and not os.environ.get("APP_USERS")


def _setting(key: str, default):
    value = _secrets().get(key, os.environ.get(f"APP_{key.upper()}", default))
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# "Keep me signed in" token
# --------------------------------------------------------------------------
def _token_secret() -> bytes:
    """Signing key: configured, or derived from the stored credentials.

    Deriving it means no extra configuration, the key survives a restart, and
    changing any password invalidates every outstanding token.
    """
    configured = _secrets().get("session_secret") or os.environ.get("APP_SESSION_SECRET")
    if configured:
        return str(configured).encode("utf-8")
    material = "|".join(f"{u}:{r['secret']}" for u, r in sorted(load_users().items()))
    return hashlib.sha256(("ascend-session|" + material).encode("utf-8")).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(username: str, hours: float = REMEMBER_HOURS,
                now: float | None = None) -> str:
    now = time.time() if now is None else now
    payload = f"{username}|{int(now + hours * 3600)}"
    signature = hmac.new(_token_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{_b64(payload.encode('utf-8'))}.{_b64(signature)}"


def read_token(token: str, now: float | None = None) -> str | None:
    """Username carried by a valid, unexpired, untampered token, else None."""
    now = time.time() if now is None else now
    try:
        raw_payload, raw_signature = token.split(".", 1)
        payload = _unb64(raw_payload)
        signature = _unb64(raw_signature)
    except (ValueError, binascii.Error):
        return None
    expected = hmac.new(_token_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        username, expiry = payload.decode("utf-8").rsplit("|", 1)
        if float(expiry) < now:
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return username if username in load_users() else None


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------
def is_signed_in() -> bool:
    """Session-state only, so this is safe to call before ``st.set_page_config``."""
    return bool(st.session_state.get(_K_USER))


def current_user() -> dict | None:
    return st.session_state.get(_K_USER)


def notice() -> str:
    """One-shot message for the sign-in page (a timeout, or a completed sign-out)."""
    return st.session_state.pop(_K_NOTICE, "")


def _start_session(record: dict, remember: bool) -> None:
    st.session_state[_K_USER] = dict(record, secret=None)
    st.session_state[_K_SEEN] = time.time()
    st.session_state[_K_FAILS] = 0
    st.session_state.pop(_K_LOCK, None)
    if remember:
        st.query_params[_TOKEN_PARAM] = issue_token(record["username"])


def restore_session() -> bool:
    """Sign in from a "keep me signed in" token if one is present and valid."""
    if is_signed_in():
        return True
    token = st.query_params.get(_TOKEN_PARAM)
    if not token:
        return False
    username = read_token(token)
    if not username:
        del st.query_params[_TOKEN_PARAM]
        return False
    _start_session(load_users()[username], remember=False)
    return True


def enforce_idle_timeout() -> None:
    """End the session after a long silence, and say so on the sign-in page."""
    if not is_signed_in():
        return
    limit = _setting("idle_timeout_minutes", IDLE_MINUTES) * 60
    last_seen = st.session_state.get(_K_SEEN, 0)
    if limit > 0 and time.time() - last_seen > limit:
        sign_out(f"Signed out after {int(limit // 60)} minutes without activity.")
        st.rerun()
    st.session_state[_K_SEEN] = time.time()


def lock_remaining() -> int:
    """Seconds left on the failed-attempt cool-off. Zero when not locked."""
    until = st.session_state.get(_K_LOCK, 0)
    return max(0, int(until - time.time()))


def attempt(username: str, password: str, remember: bool = False) -> tuple[bool, str]:
    """Try to sign in. Returns (signed_in, message to show on failure).

    The cool-off is per browser session, which slows a person at the keyboard
    but not a distributed attacker. Put the application behind SSO or a network
    control if it ever holds client data.
    """
    waiting = lock_remaining()
    if waiting:
        return False, f"Too many attempts. Try again in {waiting // 60 + 1} min."

    username = (username or "").strip()
    if not username or not password:
        return False, "Enter a username and password."

    record = load_users().get(username)
    # Hash regardless, so a wrong username and a wrong password take the same time.
    reference = record["secret"] if record else hash_password("no-such-account")
    if record and verify_password(password, reference):
        _start_session(record, remember)
        return True, ""

    fails = int(st.session_state.get(_K_FAILS, 0)) + 1
    st.session_state[_K_FAILS] = fails
    if fails >= MAX_ATTEMPTS:
        st.session_state[_K_LOCK] = time.time() + LOCK_SECONDS
        st.session_state[_K_FAILS] = 0
        return False, f"Too many attempts. Try again in {LOCK_SECONDS // 60} min."
    left = MAX_ATTEMPTS - fails
    return False, ("That username and password do not match. "
                   f"{left} attempt{'s' if left != 1 else ''} left before a short lock.")


def sign_out(message: str = "") -> None:
    for key in (_K_USER, _K_SEEN, _K_FAILS, _K_LOCK):
        st.session_state.pop(key, None)
    if _TOKEN_PARAM in st.query_params:
        del st.query_params[_TOKEN_PARAM]
    if message:
        st.session_state[_K_NOTICE] = message


# --------------------------------------------------------------------------
# Signed-in account block for the sidebar
# --------------------------------------------------------------------------
def account_panel() -> None:
    user = current_user()
    if not user:
        return
    initials = "".join(part[0] for part in user["name"].split()[:2]).upper() or "?"
    st.markdown(
        "<div class='acct'>"
        f"<div class='acct-mark'>{initials}</div>"
        f"<div><div class='acct-name'>{user['name']}</div>"
        f"<div class='acct-role'>{user['role']}</div></div></div>",
        unsafe_allow_html=True)
    if using_demo_account():
        st.caption("Demo account -- no accounts are configured yet.")
    if st.button("Sign out", width="stretch"):
        sign_out(f"Signed out of {brand.NAME}.")
        st.rerun()
