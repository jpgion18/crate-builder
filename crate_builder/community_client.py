"""Publish/browse crate track lists on the Crate Builder Community feed.

A separate web app — see https://github.com/jpgion18/crate-builder-community.
It's a free perk for DJs with an active Showfile subscription: every
request needs an access code (from your Showfile dashboard's Settings
page), saved locally here and sent as a bearer token. Only artist/title
metadata ever leaves your machine: no audio, no file paths, no library
contents beyond what you explicitly publish from a built crate.
"""

from __future__ import annotations

import os

import requests

_CODE_PATH = os.path.join(os.path.expanduser("~"), ".crate_builder", "community_access_code")


class CommunityNotConfigured(RuntimeError):
    pass


class CommunityAccessCodeMissing(RuntimeError):
    pass


class CommunityRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def get_access_code() -> str:
    try:
        with open(_CODE_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def set_access_code(code: str) -> None:
    os.makedirs(os.path.dirname(_CODE_PATH), exist_ok=True)
    with open(_CODE_PATH, "w") as f:
        f.write(code.strip())


def _api_url() -> str:
    api_url = os.environ.get("COMMUNITY_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise CommunityNotConfigured(
            "COMMUNITY_API_URL is not set. Copy .env.example to .env and fill it "
            "in with your Crate Builder Community deployment's URL."
        )
    return api_url


def _request(method: str, path: str, **kwargs) -> dict:
    code = get_access_code()
    if not code:
        raise CommunityAccessCodeMissing(
            "No Crate Builder Community access code saved yet. Get one from your "
            "Showfile dashboard's Settings page and paste it in the Community tab."
        )

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {code}"

    try:
        response = requests.request(method, f"{_api_url()}{path}", timeout=10, headers=headers, **kwargs)
    except requests.RequestException as exc:
        raise CommunityRequestError(f"Couldn't reach the Community feed: {exc}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not response.ok:
        message = payload.get("error", f"Community feed returned HTTP {response.status_code}")
        raise CommunityRequestError(message, response.status_code)

    return payload


def publish_crate(crate_name: str, tracks: list[dict], tag: str = "", display_name: str = "") -> dict:
    """tracks: list of {"artist": str, "title": str}."""
    body = {"crate_name": crate_name, "tracks": tracks}
    if tag:
        body["tag"] = tag
    if display_name:
        body["display_name"] = display_name
    return _request("POST", "/api/crates", json=body)


def list_crates(query: str = "", limit: int = 20, offset: int = 0) -> dict:
    params = {"limit": limit, "offset": offset}
    if query:
        params["q"] = query
    return _request("GET", "/api/crates", params=params)
