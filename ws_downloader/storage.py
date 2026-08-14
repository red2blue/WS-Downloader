"""Local persistence for games, mods, settings, and download history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .models import Game, Mod


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class GameStore:
    """JSON-backed storage for the list of configured games."""

    def __init__(self, games_path: Path):
        self.games_path = games_path

    def ensure_file(self) -> None:
        """Create the games file with an empty payload if needed."""

        self.games_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.games_path.exists():
            self.games_path.write_text(json.dumps({"games": []}, indent=2), encoding="utf-8")

    def load_games(self) -> list[Game]:
        """Load all games from disk, returning an empty list on malformed input."""

        self.ensure_file()
        try:
            data = json.loads(self.games_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        games = []
        for item in data.get("games", []):
            games.append(
                Game(
                    id=str(item["id"]),
                    steam_app_id=int(item["steam_app_id"]),
                    game_name=str(item.get("game_name", "")),
                    workshop_url=str(item.get("workshop_url", "")),
                    mods_path=str(item.get("mods_path", "")),
                    created_at=str(item.get("created_at", utc_now())),
                    updated_at=str(item.get("updated_at", utc_now())),
                )
            )
        return sorted(games, key=lambda g: g.id.lower())

    def save_games(self, games: list[Game]) -> None:
        """Write the complete game list back to disk."""

        self.ensure_file()
        payload = {
            "games": [
                {
                    "id": game.id,
                    "steam_app_id": game.steam_app_id,
                    "game_name": game.game_name,
                    "workshop_url": game.workshop_url,
                    "mods_path": game.mods_path,
                    "created_at": game.created_at,
                    "updated_at": game.updated_at,
                }
                for game in games
            ]
        }
        self.games_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert_game(self, game: Game) -> None:
        """Insert a new game or replace an existing one with the same ID."""

        games = self.load_games()
        replaced = False
        for index, existing in enumerate(games):
            if existing.id == game.id:
                games[index] = game
                replaced = True
                break
        if not replaced:
            games.append(game)
        self.save_games(games)

    def delete_game(self, game_id: str) -> None:
        """Remove a game from the JSON store."""

        games = [game for game in self.load_games() if game.id != game_id]
        self.save_games(games)

    def get_game(self, game_id: str) -> Optional[Game]:
        """Return a single game by ID if it exists."""

        for game in self.load_games():
            if game.id == game_id:
                return game
        return None


class Database:
    """SQLite-backed application database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a database connection and commit automatically on success."""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialize(self) -> None:
        """Create required tables and default pragmas."""

        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = MEMORY")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    workshop_item_id TEXT NOT NULL,
                    install_folder_name TEXT NOT NULL DEFAULT '',
                    mod_name TEXT NOT NULL,
                    mod_url TEXT NOT NULL,
                    mod_version TEXT NOT NULL DEFAULT '',
                    compatible_game_version TEXT NOT NULL DEFAULT '',
                    new_version_available INTEGER NOT NULL DEFAULT 0,
                    remote_updated_at TEXT NOT NULL DEFAULT '',
                    last_downloaded_at TEXT NOT NULL DEFAULT '',
                    download_status TEXT NOT NULL DEFAULT 'new',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(game_id, workshop_item_id)
                )
                """
            )
            mod_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(mods)").fetchall()}
            if "install_folder_name" not in mod_columns:
                conn.execute("ALTER TABLE mods ADD COLUMN install_folder_name TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    mod_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    command TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    output TEXT NOT NULL
                )
                """
            )

    def get_setting(self, key: str, default: str = "") -> str:
        """Read a string setting by key."""

        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            return str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        """Store a string setting by key."""

        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def list_mods(self, game_id: str) -> list[Mod]:
        """Return all mods for a game, newest first."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM mods
                WHERE game_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                """,
                (game_id,),
            ).fetchall()
        return [self._row_to_mod(row) for row in rows]

    def get_mod(self, mod_id: int) -> Optional[Mod]:
        """Return a mod by its numeric database ID."""

        with self.connect() as conn:
            row = conn.execute("SELECT * FROM mods WHERE id = ?", (mod_id,)).fetchone()
        return self._row_to_mod(row) if row else None

    def get_mod_by_key(self, game_id: str, workshop_item_id: str) -> Optional[Mod]:
        """Return a mod by its natural key of game ID plus workshop item ID."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM mods WHERE game_id = ? AND workshop_item_id = ?",
                (game_id, workshop_item_id),
            ).fetchone()
        return self._row_to_mod(row) if row else None

    def upsert_mod(self, mod: Mod) -> int:
        """Insert or update a mod identified by game ID and workshop item ID."""

        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id, created_at FROM mods WHERE game_id = ? AND workshop_item_id = ?",
                (mod.game_id, mod.workshop_item_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE mods
                    SET mod_name = ?,
                        install_folder_name = ?,
                        mod_url = ?,
                        mod_version = ?,
                        compatible_game_version = ?,
                        new_version_available = ?,
                        remote_updated_at = ?,
                        last_downloaded_at = ?,
                        download_status = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        mod.mod_name,
                        mod.install_folder_name,
                        mod.mod_url,
                        mod.mod_version,
                        mod.compatible_game_version,
                        int(mod.new_version_available),
                        mod.remote_updated_at,
                        mod.last_downloaded_at,
                        mod.download_status,
                        mod.last_error,
                        now,
                        existing["id"],
                    ),
                )
                return int(existing["id"])
            cursor = conn.execute(
                """
                INSERT INTO mods(
                    game_id, workshop_item_id, install_folder_name, mod_name, mod_url, mod_version,
                    compatible_game_version, new_version_available, remote_updated_at,
                    last_downloaded_at, download_status, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mod.game_id,
                    mod.workshop_item_id,
                    mod.install_folder_name,
                    mod.mod_name,
                    mod.mod_url,
                    mod.mod_version,
                    mod.compatible_game_version,
                    int(mod.new_version_available),
                    mod.remote_updated_at,
                    mod.last_downloaded_at,
                    mod.download_status,
                    mod.last_error,
                    mod.created_at or now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def update_mod_download_result(
        self,
        mod_id: int,
        *,
        mod_version: str,
        remote_updated_at: str,
        last_downloaded_at: str,
        download_status: str,
        new_version_available: bool,
        last_error: str = "",
    ) -> None:
        """Store the result of a download attempt for a mod."""

        with self.connect() as conn:
            conn.execute(
                """
                UPDATE mods
                SET mod_version = ?,
                    remote_updated_at = ?,
                    last_downloaded_at = ?,
                    download_status = ?,
                    new_version_available = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    mod_version,
                    remote_updated_at,
                    last_downloaded_at,
                    download_status,
                    int(new_version_available),
                    last_error,
                    utc_now(),
                    mod_id,
                ),
            )

    def update_mod_metadata(
        self,
        mod_id: int,
        *,
        mod_name: str,
        mod_version: str,
        remote_updated_at: str,
        compatible_game_version: str = "",
        new_version_available: Optional[bool] = None,
        last_error: str = "",
    ) -> None:
        """Update metadata fields after a Steam Workshop refresh."""

        fields = [
            "mod_name = ?",
            "mod_version = ?",
            "remote_updated_at = ?",
            "compatible_game_version = ?",
            "last_error = ?",
            "updated_at = ?",
        ]
        params: list[object] = [
            mod_name,
            mod_version,
            remote_updated_at,
            compatible_game_version,
            last_error,
            utc_now(),
        ]
        if new_version_available is not None:
            fields.insert(4, "new_version_available = ?")
            params.insert(4, int(new_version_available))
        params.append(mod_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE mods SET {', '.join(fields)} WHERE id = ?", params)

    def update_mod_by_id(self, mod: Mod) -> None:
        """Persist all fields of a mod row identified by its numeric ID."""

        if mod.id is None:
            raise ValueError("mod.id is required")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE mods
                SET game_id = ?,
                    workshop_item_id = ?,
                    install_folder_name = ?,
                    mod_name = ?,
                    mod_url = ?,
                    mod_version = ?,
                    compatible_game_version = ?,
                    new_version_available = ?,
                    remote_updated_at = ?,
                    last_downloaded_at = ?,
                    download_status = ?,
                    last_error = ?,
                    created_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    mod.game_id,
                    mod.workshop_item_id,
                    mod.install_folder_name,
                    mod.mod_name,
                    mod.mod_url,
                    mod.mod_version,
                    mod.compatible_game_version,
                    int(mod.new_version_available),
                    mod.remote_updated_at,
                    mod.last_downloaded_at,
                    mod.download_status,
                    mod.last_error,
                    mod.created_at,
                    mod.updated_at,
                    mod.id,
                ),
            )

    def delete_mod(self, mod_id: int) -> None:
        """Delete a single mod entry."""

        with self.connect() as conn:
            conn.execute("DELETE FROM mods WHERE id = ?", (mod_id,))

    def delete_mods_for_game(self, game_id: str) -> None:
        """Delete every mod associated with a game."""

        with self.connect() as conn:
            conn.execute("DELETE FROM mods WHERE game_id = ?", (game_id,))

    def insert_download_record(
        self,
        *,
        game_id: str,
        mod_id: int,
        started_at: str,
        finished_at: str,
        command: str,
        exit_code: int,
        success: bool,
        output: str,
    ) -> None:
        """Append a download history row."""

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO downloads(game_id, mod_id, started_at, finished_at, command, exit_code, success, output)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (game_id, mod_id, started_at, finished_at, command, exit_code, int(success), output),
            )

    def _row_to_mod(self, row: sqlite3.Row | None) -> Mod:
        """Convert a SQLite row into a :class:`Mod` instance."""

        if row is None:
            raise ValueError("row is required")
        return Mod(
            id=int(row["id"]),
            game_id=str(row["game_id"]),
            workshop_item_id=str(row["workshop_item_id"]),
            install_folder_name=str(row["install_folder_name"]),
            mod_name=str(row["mod_name"]),
            mod_url=str(row["mod_url"]),
            mod_version=str(row["mod_version"]),
            compatible_game_version=str(row["compatible_game_version"]),
            new_version_available=bool(row["new_version_available"]),
            remote_updated_at=str(row["remote_updated_at"]),
            last_downloaded_at=str(row["last_downloaded_at"]),
            download_status=str(row["download_status"]),
            last_error=str(row["last_error"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def create_mod(
    *,
    game_id: str,
    workshop_item_id: str,
    install_folder_name: str = "",
    mod_url: str,
    mod_name: str,
    mod_version: str = "",
    compatible_game_version: str = "",
    new_version_available: bool = False,
    remote_updated_at: str = "",
    last_downloaded_at: str = "",
    download_status: str = "new",
    last_error: str = "",
    created_at: str = "",
) -> Mod:
    """Create a new unsaved mod object with sensible defaults."""

    return Mod(
        id=None,
        game_id=game_id,
        workshop_item_id=workshop_item_id,
        install_folder_name=install_folder_name,
        mod_name=mod_name,
        mod_url=mod_url,
        mod_version=mod_version,
        compatible_game_version=compatible_game_version,
        new_version_available=new_version_available,
        remote_updated_at=remote_updated_at,
        last_downloaded_at=last_downloaded_at,
        download_status=download_status,
        last_error=last_error,
        created_at=created_at or utc_now(),
        updated_at=utc_now(),
    )


def game_id_from_appid(steam_app_id: int) -> str:
    """Derive the stable game ID used in storage from a Steam AppID."""

    return f"app-{steam_app_id}"


def random_game_id(steam_app_id: int) -> str:
    """Generate a temporary game ID when a random identifier is needed."""

    return f"game-{steam_app_id}-{uuid.uuid4().hex[:6]}"
