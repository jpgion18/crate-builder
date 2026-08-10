""""Log in with Showfile" — a PKCE OAuth-style flow that obtains both
api_key and crate_builder_code in one step, instead of the DJ copy-pasting
each from Showfile's Settings page. Mirrors the existing Spotify login
pattern (spotify_client.py's get_login_url()/handle_callback()): a login
route redirects out, a callback route receives the result.

Manual entry isn't going away — this is a second, easier path to the same
two credentials, not a replacement.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode

import requests

from crate_builder import local_config


class ShowfileAuthError(RuntimeError):
    pass


def resolved_base_url() -> str:
    """The Showfile URL a login attempt actually uses — local_config, then
    the env var fallback, then the production default. Exposed so the
    callback route can persist this as showfile_url on success (otherwise
    a fresh install would finish login with a valid key but no saved URL,
    and still show as "not configured")."""
    url = (local_config.get("showfile_url") or os.environ.get("SHOWFILE_API_URL", "")).strip().rstrip("/")
    return url or "https://www.showfile.events"


def _showfile_base_url() -> str:
    return resolved_base_url()


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def start_login(redirect_uri: str) -> tuple[str, str, str]:
    """Returns (authorize_url, state, code_verifier).

    The caller must hold on to `state` and `code_verifier` (e.g. in a
    server-side session dict keyed by state) to validate the callback and
    complete the exchange in exchange_code().
    """
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(24)
    params = {
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{_showfile_base_url()}/crate-builder/authorize?{urlencode(params)}"
    return authorize_url, state, verifier


def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    """Returns {"api_key": ..., "crate_builder_code": ..., "business_name": ...}."""
    try:
        response = requests.post(
            f"{_showfile_base_url()}/api/crate-builder/token",
            json={"code": code, "code_verifier": code_verifier, "redirect_uri": redirect_uri},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise ShowfileAuthError(f"Couldn't reach Showfile: {exc}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not response.ok:
        raise ShowfileAuthError(payload.get("error", f"Showfile returned HTTP {response.status_code}"))

    return payload
