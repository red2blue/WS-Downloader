"""Application-wide configuration and path helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "WS Downloader"
APP_VERSION = "v0.8"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path(
    os.environ.get(
        "WS_DOWNLOADER_DATA_DIR",
        Path(os.environ.get("LOCALAPPDATA", PACKAGE_ROOT / "app_data")) / "WS Downloader",
    )
).expanduser()


@dataclass(frozen=True)
class AppPaths:
    """Resolved filesystem locations used by the application."""

    base_dir: Path
    db_path: Path
    games_path: Path
    log_dir: Path
    log_path: Path


def get_app_paths() -> AppPaths:
    """Return the current runtime paths for data, logs, and persistence."""

    base_dir = DEFAULT_DATA_DIR
    log_dir = base_dir / "logs"
    return AppPaths(
        base_dir=base_dir,
        db_path=base_dir / "ws_downloader.sqlite3",
        games_path=base_dir / "games.json",
        log_dir=log_dir,
        log_path=log_dir / "downloads.log",
    )
