"""Helpers for Steam Workshop URLs and remote metadata lookups."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


WORKSHOP_ITEM_ID_RE = re.compile(r"^\d+$")


@dataclass
class WorkshopMetadata:
    """Normalized metadata returned from Steam Workshop lookups."""

    workshop_item_id: str
    title: str
    time_updated: str
    compatible_game_version: str = ""
    description: str = ""
    url: str = ""


def derive_workshop_url(app_id: int | str) -> str:
    """Build the workshop landing page URL for a Steam app ID."""

    return f"https://steamcommunity.com/app/{int(app_id)}/workshop/"


def derive_workshop_item_url(workshop_item_id: int | str) -> str:
    """Build the detail URL for a specific Steam Workshop item."""

    return f"https://steamcommunity.com/sharedfiles/filedetails/?id={int(workshop_item_id)}"


def extract_workshop_item_id(workshop_url: str) -> str:
    """Extract a numeric Workshop item ID from a URL or path segment."""

    parsed = urlparse(workshop_url.strip())
    query = parse_qs(parsed.query)
    item_id = query.get("id", [""])[0].strip()
    if WORKSHOP_ITEM_ID_RE.match(item_id):
        return item_id
    segments = [segment for segment in parsed.path.split("/") if segment]
    for segment in reversed(segments):
        if WORKSHOP_ITEM_ID_RE.match(segment):
            return segment
    raise ValueError("Could not extract a Steam Workshop item id from the URL")


def format_unix_timestamp(value: int | float | str | None) -> str:
    """Convert a Unix timestamp to an ISO-8601 UTC string."""

    if value in (None, "", 0):
        return ""
    timestamp = int(float(value))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_workshop_metadata(workshop_item_id: str, timeout_seconds: int = 20) -> Optional[WorkshopMetadata]:
    """Fetch published file metadata from the Steam Web API."""

    endpoint = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    payload = f"itemcount=1&publishedfileids[0]={workshop_item_id}".encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    details = data.get("response", {}).get("publishedfiledetails", [])
    if not details:
        return None
    entry = details[0]
    if entry.get("result") not in (1, "1"):
        return None
    title = str(entry.get("title", "")).strip() or f"Workshop {workshop_item_id}"
    return WorkshopMetadata(
        workshop_item_id=workshop_item_id,
        title=title,
        time_updated=format_unix_timestamp(entry.get("time_updated")),
        compatible_game_version=str(entry.get("game_version", "")),
        description=str(entry.get("file_description", "")),
        url=str(entry.get("file_url", "")),
    )


def fetch_public_app_name(app_id: int, timeout_seconds: int = 20) -> str:
    """Fetch the public store name for a Steam app ID."""

    endpoint = f"https://store.steampowered.com/api/appdetails?appids={int(app_id)}&l=en"
    request = Request(endpoint, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return ""

    entry = data.get(str(int(app_id)), {})
    if not entry or not entry.get("success"):
        return ""
    details = entry.get("data", {})
    return str(details.get("name", "")).strip()
