"""SteamCMD discovery, execution, and file-move helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

STEAMCMD_DOWNLOAD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"


@dataclass
class DownloadResult:
    """Result returned from a SteamCMD download invocation."""

    exit_code: int
    output: str
    reported_error: str = ""


class SteamCMDManager:
    """Locate SteamCMD and run workshop downloads through it."""

    def __init__(self, saved_path: str = ""):
        self.saved_path = saved_path.strip()

    def discover(self) -> Optional[Path]:
        """Return the first usable SteamCMD executable found on the system."""

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
        """Build the command line used to download a workshop item."""

        return [
            str(steamcmd_path),
            "+force_install_dir",
            str(install_dir),
            "+login",
            "anonymous",
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
        """Run SteamCMD and stream its output to the supplied callback."""

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
        output = "".join(output_parts)
        return DownloadResult(
            exit_code=exit_code,
            output=output,
            reported_error=self.extract_workshop_download_error(output),
        )

    @staticmethod
    def extract_workshop_download_error(output: str) -> str:
        """Return SteamCMD's workshop failure even when its exit code is zero."""

        for line in output.splitlines():
            if "ERROR!" not in line or "Download item" not in line or "failed" not in line:
                continue
            error = line[line.index("ERROR!") :]
            suffix_index = error.find("Unloading Steam API")
            if suffix_index >= 0:
                error = error[:suffix_index]
            return error.strip()
        return ""

    def run_self_update(self, steamcmd_path: Path, on_output: Callable[[str], None]) -> DownloadResult:
        """Start SteamCMD once so it can apply its built-in updater."""

        command = [str(steamcmd_path), "+quit"]
        on_output(f"Running: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            cwd=str(steamcmd_path.parent),
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

    def install(self, install_dir: Path, on_output: Callable[[str], None]) -> Path:
        """Download, extract, and self-update SteamCMD for Windows."""

        install_dir.mkdir(parents=True, exist_ok=True)
        steamcmd_path = install_dir / "steamcmd.exe"
        on_output(f"Downloading SteamCMD: {STEAMCMD_DOWNLOAD_URL}")
        with tempfile.TemporaryDirectory(prefix="wsd-steamcmd-") as temp_dir:
            zip_path = Path(temp_dir) / "steamcmd.zip"
            urllib.request.urlretrieve(STEAMCMD_DOWNLOAD_URL, zip_path)
            on_output(f"Extracting SteamCMD to: {install_dir}")
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(install_dir)
        if not steamcmd_path.exists():
            raise FileNotFoundError(f"steamcmd.exe not found after extraction: {steamcmd_path}")
        result = self.run_self_update(steamcmd_path, on_output)
        if result.exit_code != 0:
            raise RuntimeError(f"SteamCMD self-update failed with exit code {result.exit_code}")
        return steamcmd_path

    @staticmethod
    def downloaded_workshop_path(install_dir: Path, app_id: int, workshop_item_id: str) -> Path:
        """Return the path SteamCMD writes for a downloaded workshop item."""

        return install_dir / "steamapps" / "workshop" / "content" / str(app_id) / str(workshop_item_id)

    @staticmethod
    def target_mod_path(mods_path: Path, folder_name: str) -> Path:
        """Return the final destination path for a downloaded mod."""

        return mods_path / str(folder_name)

    @classmethod
    def move_downloaded_mod(
        cls,
        install_dir: Path,
        mods_path: Path,
        app_id: int,
        workshop_item_id: str,
        target_folder_name: str = "",
    ) -> Path:
        """Move a completed download into the configured mods directory."""

        source_path = cls.downloaded_workshop_path(install_dir, app_id, workshop_item_id)
        if not source_path.exists():
            raise FileNotFoundError(f"Downloaded workshop folder not found: {source_path}")

        target_path = cls.target_mod_path(mods_path, target_folder_name or workshop_item_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.move(str(source_path), str(target_path))
        return target_path

    @staticmethod
    def cleanup_temp_install_dir(install_dir: Path) -> None:
        """Remove the temporary SteamCMD install directory."""

        shutil.rmtree(install_dir, ignore_errors=True)
