"""Publish/browse crate track lists on the Crate Builder Community feed.

A separate web app — see https://github.com/jpgion18/crate-builder-community.
It's a free perk for DJs with an active Showfile subscription: every
request needs an access code (from your Showfile dashboard's Settings
page, or crate-builder's own Settings page once you've saved it there),
sent as a bearer token. Only artist/title metadata ever leaves your
machine: no audio, no file paths, no library contents beyond what you
explicitly publish from a built crate.
"""

from __future__ import annotations

import os

import requests

from crate_builder import local_config


class CommunityNotConfigured(RuntimeError):
    pass


class CommunityAccessCodeMissing(RuntimeError):
    pass


class CommunityRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def get_access_code() -> str:
    return local_config.get("community_access_code")


def set_access_code(code: str) -> None:
    local_config.update_settings(community_access_code=code)


def _api_url() -> str:
    api_url = local_config.get("community_url") or os.environ.get("COMMUNITY_API_URL", "")
    api_url = api_url.strip().rstrip("/")
    if not api_url:
        raise CommunityNotConfigured(
            "Crate Builder Community isn't set up yet. Add it on the Settings page, "
            "or set COMMUNITY_API_URL in .env."
        )
    return api_url


def _request(method: str, path: str, **kwargs) -> dict:
    code = get_access_code()
    if not code:
        raise CommunityAccessCodeMissing(
            "No Crate Builder Community access code saved yet. Get one from your "
            "Showfile dashboard's Settings page and paste it into crate-builder's "
            "own Settings page."
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
