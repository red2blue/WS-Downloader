"""Shared data models for games and workshop mods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Game:
    """Persisted metadata for a game entry."""

    id: str
    steam_app_id: int
    game_name: str
    workshop_url: str
    mods_path: str
    created_at: str
    updated_at: str


@dataclass
class Mod:
    """Persisted metadata for a Steam Workshop mod entry."""

    id: Optional[int]
    game_id: str
    workshop_item_id: str
    install_folder_name: str
    mod_name: str
    mod_url: str
    mod_version: str
    compatible_game_version: str
    new_version_available: bool
    remote_updated_at: str
    last_downloaded_at: str
    download_status: str
    last_error: str
    created_at: str
    updated_at: str
