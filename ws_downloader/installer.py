"""Install downloaded Workshop content and track file ownership."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


INSTALL_MODE_INHERIT = "inherit"
INSTALL_MODE_SUBFOLDER = "subfolder"
INSTALL_MODE_DIRECT = "direct"
GAME_INSTALL_MODES = (INSTALL_MODE_SUBFOLDER, INSTALL_MODE_DIRECT)
MOD_INSTALL_MODES = (INSTALL_MODE_INHERIT, *GAME_INSTALL_MODES)


@dataclass(frozen=True)
class InstallConflict:
    """A destination file already owned by another mod or the user."""

    relative_path: str
    owners: tuple[str, ...]


class ModInstaller:
    """Copy Workshop files and persist ownership manifests per game and mod."""

    def __init__(self, manifests_dir: Path):
        self.manifests_dir = manifests_dir

    @staticmethod
    def effective_mode(game_mode: str, mod_mode: str) -> str:
        """Resolve a per-mod override against the game's default mode."""

        normalized_game_mode = game_mode if game_mode in GAME_INSTALL_MODES else INSTALL_MODE_SUBFOLDER
        if mod_mode == INSTALL_MODE_INHERIT or mod_mode not in MOD_INSTALL_MODES:
            return normalized_game_mode
        return mod_mode

    def find_direct_conflicts(
        self,
        source_path: Path,
        mods_path: Path,
        game_id: str,
        workshop_item_id: str,
    ) -> list[InstallConflict]:
        """Return files a direct install would overwrite outside its own manifest."""

        own_manifest = self._manifest_for_mods_path(
            self._load_manifest(game_id, workshop_item_id),
            mods_path,
        )
        own_files = self._manifest_files(own_manifest)
        other_owners = self._other_file_owners(game_id, workshop_item_id, mods_path)
        conflicts: list[InstallConflict] = []
        for _source_file, relative_path in self._candidate_files(source_path, INSTALL_MODE_DIRECT, ""):
            key = self._path_key(relative_path)
            destination = self._safe_destination(mods_path, relative_path)
            if destination is None:
                conflicts.append(InstallConflict(relative_path, ("unsafe",)))
                continue
            owners = sorted(other_owners.get(key, set()))
            if owners:
                conflicts.append(InstallConflict(relative_path, tuple(owners)))
            elif destination.exists() and key not in own_files:
                conflicts.append(InstallConflict(relative_path, ("existing",)))
        return conflicts

    def install(
        self,
        source_path: Path,
        mods_path: Path,
        game_id: str,
        workshop_item_id: str,
        mode: str,
        target_folder_name: str,
    ) -> Path:
        """Install one downloaded item and update its ownership manifest."""

        if mode not in GAME_INSTALL_MODES:
            raise ValueError(f"Unsupported install mode: {mode}")
        if not source_path.is_dir():
            raise FileNotFoundError(f"Downloaded workshop folder not found: {source_path}")
        if mode == INSTALL_MODE_SUBFOLDER and not target_folder_name.strip():
            raise ValueError("A target folder is required for subfolder installation")

        mods_path.mkdir(parents=True, exist_ok=True)
        candidates = self._candidate_files(source_path, mode, target_folder_name)
        candidate_keys = {self._path_key(relative_path) for _source, relative_path in candidates}
        previous_manifest = self._manifest_for_mods_path(
            self._load_manifest(game_id, workshop_item_id),
            mods_path,
        )
        other_owners = self._other_file_owners(game_id, workshop_item_id, mods_path)
        target_path = mods_path if mode == INSTALL_MODE_DIRECT else mods_path / target_folder_name
        if mode == INSTALL_MODE_SUBFOLDER and not previous_manifest and target_path.exists():
            if target_path.is_dir():
                shutil.rmtree(target_path)
            else:
                target_path.unlink()
        self._remove_stale_files(mods_path, previous_manifest, candidate_keys, other_owners)

        for source_file, relative_path in candidates:
            destination = self._safe_destination(mods_path, relative_path)
            if destination is None:
                raise ValueError(f"Install path escapes the configured mods directory: {relative_path}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)

        manifest = {
            "game_id": game_id,
            "workshop_item_id": workshop_item_id,
            "mods_path": str(mods_path.resolve(strict=False)),
            "mode": mode,
            "target_folder_name": target_folder_name if mode == INSTALL_MODE_SUBFOLDER else "",
            "files": [relative_path for _source, relative_path in candidates],
        }
        self._write_manifest(game_id, workshop_item_id, manifest)
        if mode == INSTALL_MODE_DIRECT:
            return mods_path
        return mods_path / target_folder_name

    def has_manifest(self, game_id: str, workshop_item_id: str, mods_path: Path) -> bool:
        """Return whether this mod has an ownership manifest for the current path."""

        manifest = self._manifest_for_mods_path(self._load_manifest(game_id, workshop_item_id), mods_path)
        return bool(manifest)

    def uninstall(self, game_id: str, workshop_item_id: str, mods_path: Path) -> int:
        """Remove files exclusively owned by this mod and delete its manifest."""

        manifest_path = self._manifest_path(game_id, workshop_item_id)
        manifest = self._manifest_for_mods_path(self._read_manifest_file(manifest_path), mods_path)
        if not manifest:
            return 0
        other_owners = self._other_file_owners(game_id, workshop_item_id, mods_path)
        removed = 0
        for relative_path in manifest.get("files", []):
            relative_path = str(relative_path)
            if self._path_key(relative_path) in other_owners:
                continue
            destination = self._safe_destination(mods_path, relative_path)
            if destination is None:
                continue
            if destination.is_file() or destination.is_symlink():
                destination.unlink()
                removed += 1
                self._remove_empty_parents(destination.parent, mods_path)
        manifest_path.unlink(missing_ok=True)
        try:
            manifest_path.parent.rmdir()
        except OSError:
            pass
        return removed

    def _candidate_files(self, source_path: Path, mode: str, target_folder_name: str) -> list[tuple[Path, str]]:
        candidates: list[tuple[Path, str]] = []
        for source_file in sorted(path for path in source_path.rglob("*") if path.is_file()):
            source_relative = source_file.relative_to(source_path)
            if mode == INSTALL_MODE_SUBFOLDER:
                destination_relative = Path(target_folder_name) / source_relative
            else:
                destination_relative = source_relative
            candidates.append((source_file, destination_relative.as_posix()))
        return candidates

    def _other_file_owners(self, game_id: str, workshop_item_id: str, mods_path: Path) -> dict[str, set[str]]:
        owners: dict[str, set[str]] = {}
        expected_root = str(mods_path.resolve(strict=False)).casefold()
        for manifest_path in self._game_manifest_dir(game_id).glob("*.json"):
            if manifest_path.stem == workshop_item_id:
                continue
            manifest = self._read_manifest_file(manifest_path)
            if str(manifest.get("mods_path", "")).casefold() != expected_root:
                continue
            owner = str(manifest.get("workshop_item_id", manifest_path.stem))
            for relative_path in manifest.get("files", []):
                owners.setdefault(self._path_key(str(relative_path)), set()).add(owner)
        return owners

    def _remove_stale_files(
        self,
        mods_path: Path,
        previous_manifest: dict,
        candidate_keys: set[str],
        other_owners: dict[str, set[str]],
    ) -> None:
        previous_files = [str(path) for path in previous_manifest.get("files", [])]
        for relative_path in previous_files:
            key = self._path_key(relative_path)
            if key in candidate_keys or key in other_owners:
                continue
            destination = self._safe_destination(mods_path, relative_path)
            if destination is None:
                continue
            if destination.is_file() or destination.is_symlink():
                destination.unlink()
                self._remove_empty_parents(destination.parent, mods_path)

    @staticmethod
    def _remove_empty_parents(directory: Path, root: Path) -> None:
        root = root.resolve(strict=False)
        current = directory
        while current.resolve(strict=False) != root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _load_manifest(self, game_id: str, workshop_item_id: str) -> dict:
        return self._read_manifest_file(self._manifest_path(game_id, workshop_item_id))

    @staticmethod
    def _manifest_for_mods_path(manifest: dict, mods_path: Path) -> dict:
        expected_root = str(mods_path.resolve(strict=False)).casefold()
        if str(manifest.get("mods_path", "")).casefold() != expected_root:
            return {}
        return manifest

    @staticmethod
    def _read_manifest_file(path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_manifest(self, game_id: str, workshop_item_id: str, manifest: dict) -> None:
        path = self._manifest_path(game_id, workshop_item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temporary_path.replace(path)

    @staticmethod
    def _manifest_files(manifest: dict) -> set[str]:
        return {ModInstaller._path_key(str(path)) for path in manifest.get("files", [])}

    @staticmethod
    def _path_key(relative_path: str) -> str:
        return relative_path.replace("\\", "/").casefold()

    @staticmethod
    def _safe_destination(mods_path: Path, relative_path: str) -> Path | None:
        root = mods_path.resolve(strict=False)
        destination = (mods_path / Path(relative_path)).resolve(strict=False)
        try:
            destination.relative_to(root)
        except ValueError:
            return None
        return destination

    def _game_manifest_dir(self, game_id: str) -> Path:
        return self.manifests_dir / game_id

    def _manifest_path(self, game_id: str, workshop_item_id: str) -> Path:
        return self._game_manifest_dir(game_id) / f"{workshop_item_id}.json"
