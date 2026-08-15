"""Tests for installation modes, manifests, and storage migration defaults."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ws_downloader.installer import (
    INSTALL_MODE_DIRECT,
    INSTALL_MODE_INHERIT,
    INSTALL_MODE_SUBFOLDER,
    ModInstaller,
)
from ws_downloader.storage import Database, GameStore, create_mod


class ModInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temporary_directory.name)
        self.mods_path = self.root / "mods"
        self.installer = ModInstaller(self.root / "manifests")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _source(self, name: str, files: dict[str, str]) -> Path:
        source = self.root / name
        for relative_path, content in files.items():
            path = source / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return source

    def test_effective_mode_uses_game_default_or_mod_override(self) -> None:
        self.assertEqual(
            self.installer.effective_mode(INSTALL_MODE_DIRECT, INSTALL_MODE_INHERIT),
            INSTALL_MODE_DIRECT,
        )
        self.assertEqual(
            self.installer.effective_mode(INSTALL_MODE_DIRECT, INSTALL_MODE_SUBFOLDER),
            INSTALL_MODE_SUBFOLDER,
        )

    def test_direct_install_copies_files_without_wrapper_folder(self) -> None:
        source = self._source("source-direct", {"descriptor.mod": "data", "common/rules.txt": "rules"})

        target = self.installer.install(
            source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "ignored",
        )

        self.assertEqual(target, self.mods_path)
        self.assertEqual((self.mods_path / "descriptor.mod").read_text(encoding="utf-8"), "data")
        self.assertTrue((self.mods_path / "common" / "rules.txt").is_file())
        self.assertFalse((self.mods_path / "100").exists())

    def test_subfolder_install_uses_configured_folder(self) -> None:
        source = self._source("source-subfolder", {"file.txt": "content"})

        target = self.installer.install(
            source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_SUBFOLDER,
            "My Mod",
        )

        self.assertEqual(target, self.mods_path / "My Mod")
        self.assertTrue((target / "file.txt").is_file())

    def test_direct_install_reports_other_mod_and_external_file_conflicts(self) -> None:
        first_source = self._source("source-first", {"shared.txt": "first"})
        self.installer.install(
            first_source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "",
        )
        (self.mods_path / "external.txt").write_text("external", encoding="utf-8")
        second_source = self._source(
            "source-second",
            {"shared.txt": "second", "external.txt": "replacement"},
        )

        conflicts = self.installer.find_direct_conflicts(
            second_source,
            self.mods_path,
            "app-1",
            "200",
        )
        conflicts_by_path = {conflict.relative_path: conflict.owners for conflict in conflicts}

        self.assertEqual(conflicts_by_path["shared.txt"], ("100",))
        self.assertEqual(conflicts_by_path["external.txt"], ("existing",))

    def test_update_removes_only_stale_files_owned_by_same_mod(self) -> None:
        first_source = self._source("source-v1", {"old.txt": "old", "keep.txt": "v1"})
        self.installer.install(
            first_source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "",
        )
        second_source = self._source("source-v2", {"keep.txt": "v2", "new.txt": "new"})

        self.installer.install(
            second_source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "",
        )

        self.assertFalse((self.mods_path / "old.txt").exists())
        self.assertEqual((self.mods_path / "keep.txt").read_text(encoding="utf-8"), "v2")
        self.assertTrue((self.mods_path / "new.txt").is_file())

    def test_manifest_from_old_mods_path_is_not_applied_to_new_path(self) -> None:
        source = self._source("source-old-path", {"shared.txt": "managed"})
        self.installer.install(
            source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "",
        )
        new_mods_path = self.root / "new-mods"
        new_mods_path.mkdir()
        (new_mods_path / "shared.txt").write_text("external", encoding="utf-8")

        conflicts = self.installer.find_direct_conflicts(
            source,
            new_mods_path,
            "app-1",
            "100",
        )

        self.assertEqual(conflicts[0].owners, ("existing",))

    def test_uninstall_keeps_files_still_owned_by_another_mod(self) -> None:
        first_source = self._source("source-owner-one", {"shared.txt": "first", "first.txt": "first"})
        second_source = self._source("source-owner-two", {"shared.txt": "second", "second.txt": "second"})
        self.installer.install(
            first_source,
            self.mods_path,
            "app-1",
            "100",
            INSTALL_MODE_DIRECT,
            "",
        )
        self.installer.install(
            second_source,
            self.mods_path,
            "app-1",
            "200",
            INSTALL_MODE_DIRECT,
            "",
        )

        removed = self.installer.uninstall("app-1", "100", self.mods_path)

        self.assertEqual(removed, 1)
        self.assertTrue((self.mods_path / "shared.txt").is_file())
        self.assertFalse((self.mods_path / "first.txt").exists())
        self.assertTrue((self.mods_path / "second.txt").is_file())

    def test_uninstall_never_deletes_path_outside_mods_directory(self) -> None:
        self.mods_path.mkdir()
        outside_file = self.root / "outside.txt"
        outside_file.write_text("keep", encoding="utf-8")
        manifest_path = self.root / "manifests" / "app-1" / "100.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "game_id": "app-1",
                    "workshop_item_id": "100",
                    "mods_path": str(self.mods_path.resolve()),
                    "mode": INSTALL_MODE_DIRECT,
                    "files": ["../outside.txt"],
                }
            ),
            encoding="utf-8",
        )

        removed = self.installer.uninstall("app-1", "100", self.mods_path)

        self.assertEqual(removed, 0)
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "keep")


class StorageModeTests(unittest.TestCase):
    def test_existing_game_defaults_to_subfolder_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            games_path = Path(temporary_directory) / "games.json"
            games_path.write_text(
                json.dumps(
                    {
                        "games": [
                            {
                                "id": "app-1",
                                "steam_app_id": 1,
                                "game_name": "Game",
                                "workshop_url": "https://example.invalid",
                                "mods_path": "C:/Mods",
                                "created_at": "2026-01-01T00:00:00Z",
                                "updated_at": "2026-01-01T00:00:00Z",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            game = GameStore(games_path).load_games()[0]

            self.assertEqual(game.install_mode, INSTALL_MODE_SUBFOLDER)

    def test_mod_mode_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database = Database(Path(temporary_directory) / "test.sqlite3")
            mod = create_mod(
                game_id="app-1",
                workshop_item_id="100",
                install_folder_name="",
                install_mode=INSTALL_MODE_DIRECT,
                mod_url="https://example.invalid",
                mod_name="Test Mod",
            )

            mod_id = database.upsert_mod(mod)

            self.assertEqual(database.get_mod(mod_id).install_mode, INSTALL_MODE_DIRECT)

    def test_existing_mod_table_is_migrated_with_inherit_default(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "legacy.sqlite3"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """
                CREATE TABLE mods (
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
            connection.commit()
            connection.close()

            Database(database_path)
            connection = sqlite3.connect(database_path)
            columns = {row[1]: row[4] for row in connection.execute("PRAGMA table_info(mods)")}
            connection.close()

            self.assertEqual(columns["install_mode"], "'inherit'")


if __name__ == "__main__":
    unittest.main()
