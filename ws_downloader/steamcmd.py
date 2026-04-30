from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class DownloadResult:
    exit_code: int
    output: str


class SteamCMDManager:
    def __init__(self, saved_path: str = ""):
        self.saved_path = saved_path.strip()

    def discover(self) -> Optional[Path]:
        candidates: list[Path] = []
        if self.saved_path:
            candidates.append(Path(self.saved_path))

        which = shutil.which("steamcmd.exe") or shutil.which("steamcmd")
        if which:
            candidates.append(Path(which))

        env_candidates = []
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "PROGRAMDATA"):
            value = os.environ.get(env_name)
            if value:
                env_candidates.extend(
                    [
                        Path(value) / "SteamCMD" / "steamcmd.exe",
                        Path(value) / "steamcmd" / "steamcmd.exe",
                        Path(value) / "Steam" / "steamcmd.exe",
                    ]
                )
        candidates.extend(
            [
                Path(r"C:\SteamCMD\steamcmd.exe"),
                Path(r"C:\steamcmd\steamcmd.exe"),
                Path(r"C:\Program Files (x86)\SteamCMD\steamcmd.exe"),
                Path(r"C:\Program Files\SteamCMD\steamcmd.exe"),
            ]
        )
        candidates.extend(env_candidates)

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate
        return None

    def build_download_command(self, steamcmd_path: Path, app_id: int, workshop_item_id: str, install_dir: Path) -> list[str]:
        return [
            str(steamcmd_path),
            "+login",
            "anonymous",
            "+force_install_dir",
            str(install_dir),
            "+workshop_download_item",
            str(app_id),
            str(workshop_item_id),
            "+quit",
        ]

    def run_download(
        self,
        steamcmd_path: Path,
        app_id: int,
        workshop_item_id: str,
        install_dir: Path,
        on_output: Callable[[str], None],
    ) -> DownloadResult:
        install_dir.mkdir(parents=True, exist_ok=True)
        command = self.build_download_command(steamcmd_path, app_id, workshop_item_id, install_dir)
        on_output(f"Running: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output_parts: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            output_parts.append(line)
            on_output(line.rstrip())
        exit_code = process.wait()
        return DownloadResult(exit_code=exit_code, output="".join(output_parts))

    @staticmethod
    def downloaded_workshop_path(install_dir: Path, app_id: int, workshop_item_id: str) -> Path:
        return install_dir / "steamapps" / "workshop" / "content" / str(app_id) / str(workshop_item_id)

    @staticmethod
    def target_mod_path(mods_path: Path, workshop_item_id: str) -> Path:
        return mods_path / str(workshop_item_id)

    @classmethod
    def move_downloaded_mod(
        cls,
        install_dir: Path,
        mods_path: Path,
        app_id: int,
        workshop_item_id: str,
    ) -> Path:
        source_path = cls.downloaded_workshop_path(install_dir, app_id, workshop_item_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Downloaded workshop folder not found: {source_path}")

        target_path = cls.target_mod_path(mods_path, workshop_item_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.move(str(source_path), str(target_path))
        return target_path

    @staticmethod
    def cleanup_temp_install_dir(install_dir: Path) -> None:
        shutil.rmtree(install_dir, ignore_errors=True)
