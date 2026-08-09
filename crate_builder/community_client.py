"""Publish/browse crate track lists on the Crate Builder Community feed.

A separate, optional, anonymous web app — see
https://github.com/jpgion18/crate-builder-community. Only artist/title
metadata ever leaves your machine: no audio, no file paths, no library
contents beyond what you explicitly publish from a built crate.
"""

from __future__ import annotations

import os

import requests


class CommunityNotConfigured(RuntimeError):
    pass


class CommunityRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _api_url() -> str:
    api_url = os.environ.get("COMMUNITY_API_URL", "").strip().rstrip("/")
    if not api_url:
        raise CommunityNotConfigured(
            "COMMUNITY_API_URL is not set. Copy .env.example to .env and fill it "
            "in with your Crate Builder Community deployment's URL."
        )
    return api_url


def _request(method: str, path: str, **kwargs) -> dict:
    try:
        response = requests.request(method, f"{_api_url()}{path}", timeout=10, **kwargs)
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
