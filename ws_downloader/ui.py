from __future__ import annotations

import queue
import threading
import uuid
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, StringVar, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk

from .config import APP_NAME, get_app_paths
from .metadata import derive_workshop_item_url, derive_workshop_url, fetch_public_app_name, fetch_workshop_metadata
from .models import Game, Mod
from .steamcmd import SteamCMDManager
from .storage import Database, GameStore, create_mod, game_id_from_appid, utc_now


def center_window_over_parent(parent: Tk, window: Toplevel) -> None:
    window.update_idletasks()
    parent.update_idletasks()
    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    window_width = window.winfo_reqwidth()
    window_height = window.winfo_reqheight()
    x = parent_x + max(0, (parent_width - window_width) // 2)
    y = parent_y + max(0, (parent_height - window_height) // 2)
    window.geometry(f"{window_width}x{window_height}+{x}+{y}")


class GameDialog:
    def __init__(self, parent, title: str, game: Game | None = None):
        self.parent = parent
        self.is_edit = game is not None
        self.result: dict[str, str] | None = None
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)

        self.appid_var = StringVar(value=str(game.steam_app_id) if game else "")
        self.mods_path_var = StringVar(value=game.mods_path if game else "")

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)

        rows = [
            ("Steam AppID", self.appid_var, False),
            ("Mods Path", self.mods_path_var, False),
        ]

        for idx, (label, variable, readonly) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, textvariable=variable, width=48)
            entry.grid(row=idx, column=1, sticky="ew", pady=4)
            if label == "Mods Path":
                ttk.Button(frame, text="Browse", command=self._browse_path).grid(row=idx, column=2, padx=(8, 0))
            if readonly and self.is_edit:
                entry.state(["readonly"])

        ttk.Label(frame, text="Game name and workshop URL are derived automatically.").grid(
            row=len(rows), column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(button_row, text="Save", command=self._save).pack(side=RIGHT)
        frame.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        center_window_over_parent(parent, self.window)

    def _browse_path(self) -> None:
        folder = filedialog.askdirectory(parent=self.window, title="Choose mods path")
        if folder:
            self.mods_path_var.set(folder)

    def _save(self) -> None:
        app_id_text = self.appid_var.get().strip()
        mods_path = self.mods_path_var.get().strip()
        if not app_id_text.isdigit():
            messagebox.showerror(APP_NAME, "Steam AppID must be numeric.", parent=self.window)
            return
        if not mods_path:
            messagebox.showerror(APP_NAME, "Mods path is required.", parent=self.window)
            return
        self.result = {"steam_app_id": app_id_text, "mods_path": mods_path}
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


class ModDialog:
    def __init__(self, parent, title: str, mod: Mod | None = None):
        self.parent = parent
        self.result: dict[str, str] | None = None
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)

        self.item_id_var = StringVar(value=mod.workshop_item_id if mod else "")

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="Mod ID").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.item_id_var, width=54).grid(row=0, column=1, sticky="ew", pady=4)

        button_row = ttk.Frame(frame)
        button_row.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(button_row, text="Cancel", command=self._cancel).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(button_row, text="Save", command=self._save).pack(side=RIGHT)
        frame.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        center_window_over_parent(parent, self.window)

    def _save(self) -> None:
        item_id = self.item_id_var.get().strip()
        if not item_id.isdigit():
            messagebox.showerror(APP_NAME, "Mod ID must be numeric.", parent=self.window)
            return
        self.result = {"workshop_item_id": item_id}
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


class SteamCMDDialog:
    def __init__(self, parent, docs_url: str):
        self.parent = parent
        self.result: str | None = None
        self.docs_url = docs_url
        self.window = Toplevel(parent)
        self.window.title("SteamCMD required")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)
        message = (
            "SteamCMD is required for workshop downloads.\n"
            "Choose a SteamCMD path, open the documentation, or continue without configuring it."
        )
        ttk.Label(frame, text=message, justify="left").pack(anchor="w", fill=X)
        link = ttk.Label(frame, text=self.docs_url, foreground="blue", cursor="hand2")
        link.pack(anchor="w", pady=(8, 10))
        link.bind("<Button-1>", lambda _event: webbrowser.open(self.docs_url))

        button_row = ttk.Frame(frame)
        button_row.pack(fill=X, pady=(4, 0))
        ttk.Button(button_row, text="Select SteamCMD path", command=self._select_path).pack(side=LEFT)
        ttk.Button(button_row, text="Open docs", command=lambda: webbrowser.open(self.docs_url)).pack(side=LEFT, padx=8)
        ttk.Button(button_row, text="Later", command=self._later).pack(side=RIGHT)
        self.window.protocol("WM_DELETE_WINDOW", self._later)
        center_window_over_parent(parent, self.window)

    def _select_path(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window,
            title="Select steamcmd.exe",
            filetypes=[("steamcmd.exe", "steamcmd.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.result = path
            self.window.destroy()

    def _later(self) -> None:
        self.result = ""
        self.window.destroy()


class App(Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1240x780")
        self.minsize(1100, 700)

        self.paths = get_app_paths()
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)

        self.games = GameStore(self.paths.games_path)
        self.db = Database(self.paths.db_path)
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.current_game: Game | None = None
        self.current_game_id: str | None = self.db.get_setting("last_selected_game_id", "")
        self.checked_mod_ids: set[int] = set()
        self._pending_game_name_backfills: set[int] = set()
        self._pending_mod_name_backfills: set[int] = set()

        saved_steamcmd = self.db.get_setting("steamcmd_path", "")
        self.steamcmd_manager = SteamCMDManager(saved_steamcmd)
        self.steamcmd_path = self.steamcmd_manager.discover()
        if self.steamcmd_path:
            self.db.set_setting("steamcmd_path", str(self.steamcmd_path))

        self._build_ui()
        self._load_games()
        self.after(120, self._poll_queue)
        self.after(300, self._ensure_steamcmd)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Games").grid(row=0, column=0, sticky="w")
        game_buttons = ttk.Frame(top)
        game_buttons.grid(row=0, column=2, sticky="e")
        ttk.Button(game_buttons, text="+", width=3, command=self._add_game).pack(side=LEFT)
        ttk.Button(game_buttons, text="Edit", command=self._edit_game).pack(side=LEFT, padx=4)
        ttk.Button(game_buttons, text="Delete", command=self._delete_game).pack(side=LEFT)
        ttk.Button(game_buttons, text="SteamCMD", command=self._configure_steamcmd).pack(side=LEFT, padx=(12, 0))

        self.game_tree = ttk.Treeview(top, columns=("name", "appid", "mods_path"), show="headings", height=5, selectmode="browse")
        self.game_tree.heading("name", text="Spielname")
        self.game_tree.heading("appid", text="AppID")
        self.game_tree.heading("mods_path", text="Mods path")
        self.game_tree.column("name", width=240, anchor="w")
        self.game_tree.column("appid", width=100, anchor="w")
        self.game_tree.column("mods_path", width=600, anchor="w")
        self.game_tree.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.game_tree.bind("<<TreeviewSelect>>", self._on_game_selected)

        game_scroll = ttk.Scrollbar(top, orient="vertical", command=self.game_tree.yview)
        self.game_tree.configure(yscrollcommand=game_scroll.set)
        game_scroll.grid(row=1, column=3, sticky="ns", pady=(6, 0))

        middle = ttk.Frame(self, padding=(10, 6, 10, 6))
        middle.grid(row=1, column=0, sticky="nsew")
        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(1, weight=1)

        mod_header = ttk.Frame(middle)
        mod_header.grid(row=0, column=0, sticky="ew")
        mod_header.columnconfigure(0, weight=1)
        self.mod_title_var = StringVar(value="Mods")
        ttk.Label(mod_header, textvariable=self.mod_title_var).grid(row=0, column=0, sticky="w")

        mod_buttons = ttk.Frame(mod_header)
        mod_buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(mod_buttons, text="+", width=3, command=self._add_mod).pack(side=LEFT)
        ttk.Button(mod_buttons, text="Edit", command=self._edit_mod).pack(side=LEFT, padx=4)
        ttk.Button(mod_buttons, text="Delete", command=self._delete_mod).pack(side=LEFT)
        ttk.Button(mod_buttons, text="Check for Updates", command=self._check_updates).pack(side=LEFT, padx=(12, 4))
        ttk.Button(mod_buttons, text="Download", command=lambda: self._download_selected("download")).pack(side=LEFT, padx=4)
        ttk.Button(mod_buttons, text="Update", command=lambda: self._download_selected("update")).pack(side=LEFT, padx=4)

        columns = (
            "selected",
            "name",
            "item_id",
            "version",
            "remote_updated",
            "compatible_game_version",
            "new_version",
            "last_downloaded",
            "status",
            "error",
        )
        self.mod_tree = ttk.Treeview(middle, columns=columns, show="headings", selectmode="browse")
        headings = {
            "selected": "Sel",
            "name": "Mod name",
            "item_id": "Item ID",
            "version": "Version",
            "remote_updated": "Remote updated",
            "compatible_game_version": "Game version",
            "new_version": "New version",
            "last_downloaded": "Last downloaded",
            "status": "Status",
            "error": "Error",
        }
        widths = {
            "selected": 55,
            "name": 220,
            "item_id": 120,
            "version": 140,
            "remote_updated": 150,
            "compatible_game_version": 120,
            "new_version": 110,
            "last_downloaded": 150,
            "status": 110,
            "error": 260,
        }
        for key in columns:
            self.mod_tree.heading(key, text=headings[key], anchor="center")
            self.mod_tree.column(key, width=widths[key], anchor="center", stretch=True)
        self.mod_tree.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.mod_tree.bind("<Button-1>", self._on_mod_click)
        self.mod_tree.bind("<Double-1>", lambda _event: self._edit_mod())

        mod_scroll = ttk.Scrollbar(middle, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=mod_scroll.set)
        mod_scroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))

        bottom = ttk.Frame(self, padding=(10, 4, 10, 10))
        bottom.grid(row=2, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)

        ttk.Label(bottom, text="Log").grid(row=0, column=0, sticky="w")
        text_frame = ttk.Frame(bottom)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        from tkinter import Text

        self.log_widget = Text(text_frame, height=10, wrap="word")
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_widget.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_widget.configure(yscrollcommand=log_scroll.set)
        self.log_widget.configure(state="disabled")

        self.status_var = StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status.grid(row=3, column=0, sticky="ew")

    def _append_log(self, line: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", f"{line}\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")
        with self.paths.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _load_games(self) -> None:
        loaded_games = self.games.load_games()
        for item in self.game_tree.get_children():
            self.game_tree.delete(item)
        for game in loaded_games:
            display_name = game.game_name or f"App {game.steam_app_id}"
            self.game_tree.insert(
                "",
                "end",
                iid=game.id,
                values=(display_name, game.steam_app_id, game.mods_path),
            )
        self._schedule_game_name_backfill(loaded_games)
        if self.current_game_id and self.game_tree.exists(self.current_game_id):
            self.game_tree.selection_set(self.current_game_id)
            self.game_tree.focus(self.current_game_id)
            self._select_game_by_id(self.current_game_id)
        elif self.game_tree.get_children():
            first = self.game_tree.get_children()[0]
            self.game_tree.selection_set(first)
            self.game_tree.focus(first)
            self._select_game_by_id(first)
        else:
            self._set_game(None)

    def _current_game_from_selection(self) -> Game | None:
        selection = self.game_tree.selection()
        if not selection:
            return None
        return self.games.get_game(selection[0])

    def _set_game(self, game: Game | None) -> None:
        self.current_game = game
        self.current_game_id = game.id if game else None
        self.db.set_setting("last_selected_game_id", self.current_game_id or "")
        if game:
            title = game.game_name or f"App {game.steam_app_id}"
            self.mod_title_var.set(f"Mods for {title} (AppID {game.steam_app_id})")
        else:
            self.mod_title_var.set("Mods")
        self._refresh_mods()

    def _select_game_by_id(self, game_id: str) -> None:
        game = self.games.get_game(game_id)
        self._set_game(game)

    def _on_game_selected(self, _event=None) -> None:
        game = self._current_game_from_selection()
        self._set_game(game)

    def _refresh_mods(self) -> None:
        for item in self.mod_tree.get_children():
            self.mod_tree.delete(item)
        self.checked_mod_ids = set()
        if not self.current_game:
            return
        mods = self.db.list_mods(self.current_game.id)
        for mod in mods:
            self._insert_mod_row(mod)
        self._schedule_mod_name_backfill(mods)
        self.status_var.set(f"{len(mods)} mods loaded")

    def _insert_mod_row(self, mod: Mod) -> None:
        selected = "[x]" if mod.id in self.checked_mod_ids else "[ ]"
        self.mod_tree.insert(
            "",
            "end",
            iid=str(mod.id),
            values=(
                selected,
                mod.mod_name,
                mod.workshop_item_id,
                mod.mod_version,
                mod.remote_updated_at,
                mod.compatible_game_version,
                "yes" if mod.new_version_available else "no",
                mod.last_downloaded_at,
                mod.download_status,
                mod.last_error,
            ),
        )

    def _selected_mods(self) -> list[Mod]:
        if not self.current_game:
            return []
        mods = []
        for mod_id in sorted(self.checked_mod_ids):
            mod = self.db.get_mod(mod_id)
            if mod and mod.game_id == self.current_game.id:
                mods.append(mod)
        return mods

    def _effective_version_stamp(self, metadata, fallback: str = "") -> str:
        if metadata and getattr(metadata, "time_updated", ""):
            return metadata.time_updated
        return fallback or utc_now()

    def _schedule_game_name_backfill(self, games: list[Game]) -> None:
        for game in games:
            if game.game_name.strip():
                continue
            if game.steam_app_id in self._pending_game_name_backfills:
                continue
            self._pending_game_name_backfills.add(game.steam_app_id)
            thread = threading.Thread(target=self._backfill_game_name_worker, args=(game,), daemon=True)
            thread.start()

    def _schedule_mod_name_backfill(self, mods: list[Mod]) -> None:
        for mod in mods:
            if mod.mod_name.strip():
                continue
            if mod.id in self._pending_mod_name_backfills:
                continue
            self._pending_mod_name_backfills.add(mod.id)
            thread = threading.Thread(target=self._backfill_mod_name_worker, args=(mod,), daemon=True)
            thread.start()

    def _backfill_game_name_worker(self, game: Game) -> None:
        try:
            game_name = fetch_public_app_name(game.steam_app_id)
            if not game_name:
                return
            updated = replace(
                game,
                game_name=game_name,
                workshop_url=derive_workshop_url(game.steam_app_id),
                updated_at=utc_now(),
            )
            self.games.upsert_game(updated)
            self.output_queue.put(("log", f"Game name resolved: {game_name}"))
            self.output_queue.put(("refresh_games", game.id))
        finally:
            self._pending_game_name_backfills.discard(game.steam_app_id)

    def _backfill_mod_name_worker(self, mod: Mod) -> None:
        try:
            metadata = fetch_workshop_metadata(mod.workshop_item_id)
            if not metadata or not metadata.title.strip():
                return
            self.db.update_mod_metadata(
                mod.id,
                mod_name=metadata.title,
                mod_version=mod.mod_version or self._effective_version_stamp(metadata, mod.remote_updated_at),
                remote_updated_at=self._effective_version_stamp(metadata, mod.remote_updated_at),
                compatible_game_version=metadata.compatible_game_version,
                new_version_available=mod.new_version_available,
            )
            self.output_queue.put(("log", f"Mod name resolved: {metadata.title}"))
            self.output_queue.put(("refresh", mod.game_id))
        finally:
            if mod.id is not None:
                self._pending_mod_name_backfills.discard(mod.id)

    def _on_mod_click(self, event) -> str | None:
        row_id = self.mod_tree.identify_row(event.y)
        column = self.mod_tree.identify_column(event.x)
        if not row_id:
            return None
        if column == "#1":
            mod_id = int(row_id)
            if mod_id in self.checked_mod_ids:
                self.checked_mod_ids.remove(mod_id)
            else:
                self.checked_mod_ids.add(mod_id)
            mod = self.db.get_mod(mod_id)
            if mod:
                self.mod_tree.item(row_id, values=(
                    "[x]" if mod_id in self.checked_mod_ids else "[ ]",
                    mod.mod_name,
                    mod.workshop_item_id,
                    mod.mod_version,
                    mod.remote_updated_at,
                    mod.compatible_game_version,
                    "yes" if mod.new_version_available else "no",
                    mod.last_downloaded_at,
                    mod.download_status,
                    mod.last_error,
                ))
            return "break"
        return None

    def _add_game(self) -> None:
        dialog = GameDialog(self, "Add game")
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        app_id = int(dialog.result["steam_app_id"])
        mods_path = dialog.result["mods_path"]
        game_id = game_id_from_appid(app_id)
        if self.games.get_game(game_id):
            messagebox.showerror(APP_NAME, "A game with that AppID already exists.", parent=self)
            return
        self.status_var.set("Resolving game metadata...")
        thread = threading.Thread(target=self._create_game_worker, args=(app_id, mods_path), daemon=True)
        thread.start()

    def _edit_game(self) -> None:
        game = self._current_game_from_selection()
        if not game:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self)
            return
        dialog = GameDialog(self, "Edit game", game)
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        app_id = int(dialog.result["steam_app_id"])
        mods_path = dialog.result["mods_path"]
        if app_id != game.steam_app_id:
            messagebox.showerror(APP_NAME, "Changing the AppID is not supported for existing games. Delete and recreate the entry.", parent=self)
            return
        updated = replace(
            game,
            mods_path=mods_path,
            workshop_url=derive_workshop_url(app_id),
            updated_at=utc_now(),
        )
        self.games.upsert_game(updated)
        self.db.set_setting("last_selected_game_id", game.id)
        self._append_log(f"Game updated: {game.id}")
        self._load_games()

    def _create_game_worker(self, app_id: int, mods_path: str) -> None:
        game_id = game_id_from_appid(app_id)
        game_name = fetch_public_app_name(app_id) or f"App {app_id}"
        game = Game(
            id=game_id,
            steam_app_id=app_id,
            game_name=game_name,
            workshop_url=derive_workshop_url(app_id),
            mods_path=mods_path,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.games.upsert_game(game)
        self.output_queue.put(("log", f"Game added: {game_name} (AppID {app_id})"))
        self.output_queue.put(("refresh_games", game.id))
        self.output_queue.put(("status", f"Game added: {game_name}"))

    def _make_temp_install_dir(self, game: Game, mod: Mod) -> Path:
        return self.paths.base_dir / "tmp_downloads" / game.id / mod.workshop_item_id / uuid.uuid4().hex

    def _delete_game(self) -> None:
        game = self._current_game_from_selection()
        if not game:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Delete game {game.id}? This removes its mods as well.", parent=self):
            return
        self.games.delete_game(game.id)
        self.db.delete_mods_for_game(game.id)
        self._append_log(f"Game deleted: {game.id}")
        self._load_games()

    def _add_mod(self) -> None:
        if not self.current_game:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self)
            return
        dialog = ModDialog(self, "Add mod")
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        workshop_item_id = dialog.result["workshop_item_id"]
        url = derive_workshop_item_url(workshop_item_id)
        metadata = fetch_workshop_metadata(workshop_item_id)
        mod_name = metadata.title if metadata else f"Workshop {workshop_item_id}"
        remote_updated_at = self._effective_version_stamp(metadata)
        compatible_game_version = metadata.compatible_game_version if metadata else ""
        mod = create_mod(
            game_id=self.current_game.id,
            workshop_item_id=workshop_item_id,
            mod_url=url,
            mod_name=mod_name,
            mod_version=remote_updated_at,
            compatible_game_version=compatible_game_version,
            new_version_available=False,
            remote_updated_at=remote_updated_at,
            last_downloaded_at="",
            download_status="new",
        )
        mod_id = self.db.upsert_mod(mod)
        self._append_log(f"Mod added: {mod_name} ({workshop_item_id})")
        if metadata:
            self.db.update_mod_metadata(
                mod_id,
                mod_name=mod_name,
                mod_version=remote_updated_at,
                remote_updated_at=remote_updated_at,
                compatible_game_version=compatible_game_version,
                new_version_available=False,
            )
        self._refresh_mods()

    def _edit_mod(self) -> None:
        mod = self._current_mod_from_selection()
        if not mod:
            messagebox.showinfo(APP_NAME, "Select a mod first.", parent=self)
            return
        dialog = ModDialog(self, "Edit mod", mod)
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        workshop_item_id = dialog.result["workshop_item_id"]
        url = derive_workshop_item_url(workshop_item_id)
        metadata = fetch_workshop_metadata(workshop_item_id)
        mod_name = metadata.title if metadata else mod.mod_name
        remote_updated_at = self._effective_version_stamp(metadata, mod.remote_updated_at or mod.mod_version)
        compatible_game_version = metadata.compatible_game_version if metadata else mod.compatible_game_version
        updated_mod = replace(
            mod,
            workshop_item_id=workshop_item_id,
            mod_url=url,
            mod_name=mod_name,
            mod_version=mod.mod_version or remote_updated_at,
            compatible_game_version=compatible_game_version,
            remote_updated_at=remote_updated_at,
            updated_at=utc_now(),
        )
        try:
            self.db.update_mod_by_id(updated_mod)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not update mod: {exc}", parent=self)
            return
        self._append_log(f"Mod updated: {mod_name}")
        self._refresh_mods()

    def _delete_mod(self) -> None:
        mod = self._current_mod_from_selection()
        if not mod:
            messagebox.showinfo(APP_NAME, "Select a mod first.", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, f"Delete mod {mod.mod_name}?", parent=self):
            return
        self.db.delete_mod(mod.id)
        self.checked_mod_ids.discard(mod.id)
        self._append_log(f"Mod deleted: {mod.mod_name}")
        self._refresh_mods()

    def _current_mod_from_selection(self) -> Mod | None:
        selection = self.mod_tree.selection()
        if not selection:
            return None
        mod = self.db.get_mod(int(selection[0]))
        if mod and self.current_game and mod.game_id == self.current_game.id:
            return mod
        return None

    def _check_updates(self) -> None:
        if not self.current_game:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self)
            return
        mods = self.db.list_mods(self.current_game.id)
        if not mods:
            return
        self.status_var.set("Checking updates...")
        thread = threading.Thread(target=self._check_updates_worker, args=(self.current_game, mods), daemon=True)
        thread.start()

    def _check_updates_worker(self, game: Game, mods: list[Mod]) -> None:
        for mod in mods:
            metadata = fetch_workshop_metadata(mod.workshop_item_id)
            if not metadata:
                self.output_queue.put(("log", f"Update check failed for {mod.mod_name}"))
                continue
            remote_updated_at = self._effective_version_stamp(metadata, mod.remote_updated_at)
            local_version = mod.mod_version or mod.last_downloaded_at or mod.created_at
            new_version_available = bool(local_version and remote_updated_at and remote_updated_at > local_version)
            self.db.update_mod_metadata(
                mod.id,
                mod_name=metadata.title or mod.mod_name,
                mod_version=local_version or remote_updated_at,
                remote_updated_at=remote_updated_at,
                compatible_game_version=metadata.compatible_game_version,
                new_version_available=new_version_available,
            )
            self.output_queue.put(("log", f"Checked {metadata.title}: new version {'yes' if new_version_available else 'no'}"))
        self.output_queue.put(("refresh", game.id))
        self.output_queue.put(("status", "Update check complete"))

    def _download_selected(self, mode: str) -> None:
        if not self.current_game:
            messagebox.showinfo(APP_NAME, "Select a game first.", parent=self)
            return
        if not self.steamcmd_path:
            messagebox.showerror(APP_NAME, "SteamCMD is not configured.", parent=self)
            return
        mods = self._selected_mods()
        if mode == "update":
            mods = [mod for mod in mods if mod.new_version_available]
        if not mods:
            if mode == "update":
                messagebox.showinfo(APP_NAME, "Select at least one checked mod with a new version available.", parent=self)
            else:
                messagebox.showinfo(APP_NAME, "Select at least one mod by clicking its checkbox.", parent=self)
            return
        thread = threading.Thread(target=self._download_worker, args=(self.current_game, mods, mode), daemon=True)
        self.status_var.set(f"{mode.title()} started...")
        thread.start()

    def _download_worker(self, game: Game, mods: list[Mod], mode: str) -> None:
        assert self.steamcmd_path is not None
        steamcmd = SteamCMDManager(str(self.steamcmd_path))
        for mod in mods:
            metadata = fetch_workshop_metadata(mod.workshop_item_id)
            remote_updated_at = self._effective_version_stamp(metadata, mod.remote_updated_at)
            mod_name = metadata.title if metadata else mod.mod_name
            compatible_game_version = metadata.compatible_game_version if metadata else mod.compatible_game_version
            temp_install_dir = self._make_temp_install_dir(game, mod)
            if metadata:
                self.db.update_mod_metadata(
                    mod.id,
                    mod_name=mod_name,
                    mod_version=mod.mod_version or remote_updated_at,
                    remote_updated_at=remote_updated_at,
                    compatible_game_version=compatible_game_version,
                    new_version_available=bool(mod.mod_version and remote_updated_at and remote_updated_at > mod.mod_version),
                )
            self.output_queue.put(("log", f"{mode.title()} {mod_name}"))
            started_at = utc_now()
            try:
                result = steamcmd.run_download(
                    self.steamcmd_path,
                    game.steam_app_id,
                    mod.workshop_item_id,
                    temp_install_dir,
                    lambda line: self.output_queue.put(("log", line)),
                )
                success = result.exit_code == 0
                finished_at = utc_now()
                output = result.output
                if success:
                    target_path = steamcmd.move_downloaded_mod(
                        temp_install_dir,
                        Path(game.mods_path),
                        game.steam_app_id,
                        mod.workshop_item_id,
                    )
                    stored_version = remote_updated_at or finished_at or mod.mod_version
                    self.db.update_mod_download_result(
                        mod.id,
                        mod_version=stored_version,
                        remote_updated_at=remote_updated_at,
                        last_downloaded_at=finished_at,
                        download_status="downloaded",
                        new_version_available=False,
                        last_error="",
                    )
                    self.output_queue.put(("log", f"Completed: {mod_name} -> {target_path}"))
                else:
                    self.db.update_mod_download_result(
                        mod.id,
                        mod_version=mod.mod_version,
                        remote_updated_at=remote_updated_at,
                        last_downloaded_at=mod.last_downloaded_at,
                        download_status="error",
                        new_version_available=mod.new_version_available,
                        last_error=f"SteamCMD exit code {result.exit_code}",
                    )
                    self.output_queue.put(("log", f"Failed: {mod_name} (exit {result.exit_code})"))
                self.db.insert_download_record(
                    game_id=game.id,
                    mod_id=mod.id,
                    started_at=started_at,
                    finished_at=finished_at,
                    command="workshop_download_item",
                    exit_code=result.exit_code,
                    success=success,
                    output=output,
                )
            except Exception as exc:
                finished_at = utc_now()
                self.db.update_mod_download_result(
                    mod.id,
                    mod_version=mod.mod_version,
                    remote_updated_at=remote_updated_at,
                    last_downloaded_at=mod.last_downloaded_at,
                    download_status="error",
                    new_version_available=mod.new_version_available,
                    last_error=str(exc),
                )
                self.db.insert_download_record(
                    game_id=game.id,
                    mod_id=mod.id,
                    started_at=started_at,
                    finished_at=finished_at,
                    command="workshop_download_item",
                    exit_code=-1,
                    success=False,
                    output=str(exc),
                )
                self.output_queue.put(("log", f"Error: {mod_name} -> {exc}"))
            finally:
                steamcmd.cleanup_temp_install_dir(temp_install_dir)
        self.output_queue.put(("refresh", game.id))
        self.output_queue.put(("status", f"{mode.title()} complete"))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.output_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "refresh":
                    self._refresh_mods()
                elif kind == "refresh_games":
                    self._load_games()
                elif kind == "status":
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _ensure_steamcmd(self) -> None:
        if self.steamcmd_path:
            self.status_var.set(f"SteamCMD: {self.steamcmd_path}")
            return
        dialog = SteamCMDDialog(self, "https://developer.valvesoftware.com/wiki/SteamCMD")
        self.wait_window(dialog.window)
        if dialog.result is None:
            return
        if dialog.result:
            self.steamcmd_path = Path(dialog.result)
            self.db.set_setting("steamcmd_path", str(self.steamcmd_path))
            self.status_var.set(f"SteamCMD: {self.steamcmd_path}")
            self._append_log(f"SteamCMD configured: {self.steamcmd_path}")
        else:
            self.status_var.set("SteamCMD not configured")

    def _configure_steamcmd(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Select steamcmd.exe",
            filetypes=[("steamcmd.exe", "steamcmd.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.steamcmd_path = Path(path)
            self.db.set_setting("steamcmd_path", path)
            self.status_var.set(f"SteamCMD: {self.steamcmd_path}")
            self._append_log(f"SteamCMD configured: {self.steamcmd_path}")


def run_app() -> None:
    app = App()
    app.mainloop()
