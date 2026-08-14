"""Tkinter user interface for WS Downloader."""

from __future__ import annotations

import queue
import locale as py_locale
import shutil
import threading
import traceback
import uuid
import webbrowser
import tkinter.font as tkfont
from dataclasses import replace
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Label, StringVar, Tk, Toplevel, filedialog, messagebox
from tkinter import ttk

from .config import APP_NAME, APP_VERSION, get_app_paths
from .i18n import DEFAULT_LANGUAGE, TranslationManager
from .metadata import derive_workshop_item_url, derive_workshop_url, fetch_public_app_name, fetch_workshop_metadata
from .models import Game, Mod
from .steamcmd import SteamCMDManager
from .storage import Database, GameStore, create_mod, game_id_from_appid, utc_now


LANGUAGE_CODES = ("de", "en")
INVALID_WINDOWS_FOLDER_CHARS = set('<>:"/\\|?*')


def center_window_over_parent(parent: Tk, window: Toplevel) -> None:
    """Center a child window over its parent when possible."""

    window.update_idletasks()
    parent.update_idletasks()
    window_width = max(window.winfo_reqwidth(), window.winfo_width())
    window_height = max(window.winfo_reqheight(), window.winfo_height())
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    if parent_width > 1 and parent_height > 1:
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        x = parent_x + max(0, (parent_width - window_width) // 2)
        y = parent_y + max(0, (parent_height - window_height) // 2)
    else:
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
    if x + window_width > screen_width:
        x = max(0, screen_width - window_width)
    if y + window_height > screen_height:
        y = max(0, screen_height - window_height)
    window.geometry(f"{window_width}x{window_height}+{x}+{y}")


def show_modal_window(parent: Tk, window: Toplevel) -> None:
    """Make a modal window visible, centered, and focused."""

    window.deiconify()
    window.wait_visibility()
    window.update_idletasks()
    center_window_over_parent(parent, window)
    window.lift()
    window.focus_force()
    window.grab_set()


def validate_install_folder_name(folder_name: str) -> str | None:
    """Validate an optional Windows folder name for a local mod install target."""

    normalized = folder_name.strip()
    if not normalized:
        return None
    if any(char in INVALID_WINDOWS_FOLDER_CHARS for char in normalized):
        return "invalid_chars"
    if normalized.endswith((" ", ".")):
        return "invalid_suffix"
    return None


class Tooltip:
    """Small hover tooltip for Tkinter widgets."""

    def __init__(self, widget, text_factory, delay_ms: int = 250):
        self.widget = widget
        self.text_factory = text_factory
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._window: Toplevel | None = None
        self._label = None
        self.widget.bind("<Enter>", self._schedule_show, add=True)
        self.widget.bind("<Leave>", self._hide, add=True)
        self.widget.bind("<ButtonPress>", self._hide, add=True)

    def _schedule_show(self, _event=None) -> None:
        self._cancel_pending()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None:
            return
        text = self.text_factory()
        if not text:
            return
        window = Toplevel(self.widget)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#1f1f1f")
        try:
            x = self.widget.winfo_pointerx() + 16
            y = self.widget.winfo_pointery() + 16
        except Exception:
            x = self.widget.winfo_rootx() + 16
            y = self.widget.winfo_rooty() + 16
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        tooltip_width = 320
        tooltip_height = 0
        if x + tooltip_width > screen_width:
            x = max(0, screen_width - tooltip_width - 12)
        if y + 80 > screen_height:
            y = max(0, screen_height - 80 - 12)
        window.geometry(f"+{x}+{y}")
        container = ttk.Frame(window, padding=1)
        container.pack()
        label = Label(
            container,
            text=text,
            justify="left",
            wraplength=tooltip_width,
            padx=8,
            pady=5,
            bg="#1f1f1f",
            fg="#f2f2f2",
            relief="solid",
            borderwidth=1,
        )
        label.pack()
        self._window = window
        self._label = label

    def _hide(self, _event=None) -> None:
        self._cancel_pending()
        if self._window is not None:
            self._window.destroy()
            self._window = None
            self._label = None


class GameDialog:
    """Dialog for creating or editing a game entry."""

    def __init__(self, parent, title: str, game: Game | None = None):
        self.parent = parent
        self.tr = parent.i18n.translate
        self.is_edit = game is not None
        self.result: dict[str, str] | None = None
        self._tooltips: list[Tooltip] = []
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.resizable(False, False)

        self.appid_var = StringVar(value=str(game.steam_app_id) if game else "")
        self.mods_path_var = StringVar(value=game.mods_path if game else "")

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)

        rows = [
            (self.tr("dialog.game.appid"), self.appid_var, False),
            (self.tr("dialog.game.mods_path"), self.mods_path_var, False),
        ]

        for idx, (label, variable, readonly) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            entry = ttk.Entry(frame, textvariable=variable, width=48)
            entry.grid(row=idx, column=1, sticky="ew", pady=4)
            if label == self.tr("dialog.game.mods_path"):
                browse_button = ttk.Button(frame, text=self.tr("buttons.browse"), command=self._browse_path)
                browse_button.grid(row=idx, column=2, padx=(8, 0))
                self._tooltips.append(Tooltip(browse_button, lambda: self.tr("tooltip.browse_mods_path")))
            if readonly and self.is_edit:
                entry.state(["readonly"])

        ttk.Label(frame, text=self.tr("dialog.game.derived_info")).grid(
            row=len(rows), column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(button_row, text=self.tr("buttons.cancel"), command=self._cancel).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(button_row, text=self.tr("buttons.save"), command=self._save).pack(side=RIGHT)
        frame.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        show_modal_window(self.parent, self.window)

    def _browse_path(self) -> None:
        folder = filedialog.askdirectory(parent=self.window, title=self.tr("dialog.game.mods_path_title"))
        if folder:
            self.mods_path_var.set(folder)

    def _save(self) -> None:
        app_id_text = self.appid_var.get().strip()
        mods_path = self.mods_path_var.get().strip()
        if not app_id_text.isdigit():
            messagebox.showerror(APP_NAME, self.tr("message.appid_numeric"), parent=self.window)
            return
        if not mods_path:
            messagebox.showerror(APP_NAME, self.tr("message.mods_path_required"), parent=self.window)
            return
        self.result = {"steam_app_id": app_id_text, "mods_path": mods_path}
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


class ModDialog:
    """Dialog for creating or editing a workshop item entry."""

    def __init__(self, parent, title: str, mod: Mod | None = None):
        self.parent = parent
        self.mod = mod
        self.tr = parent.i18n.translate
        self.result: dict[str, str] | None = None
        self._tooltips: list[Tooltip] = []
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.resizable(False, False)

        self.item_id_var = StringVar(value=mod.workshop_item_id if mod else "")
        self.install_folder_name_var = StringVar(value=mod.install_folder_name if mod else "")
        self.install_folder_mode_var = StringVar()

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text=self.tr("dialog.mod.item_id")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.item_id_var, width=54).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text=self.tr("dialog.mod.install_folder_name")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.install_folder_name_var, width=54).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text=self.tr("buttons.use_file_name"), command=self._use_file_name).grid(
            row=1, column=2, padx=(8, 0), pady=4
        )
        ttk.Label(frame, text=self.tr("dialog.mod.install_folder_help"), justify="left").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(2, 0)
        )
        ttk.Label(frame, textvariable=self.install_folder_mode_var).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=4, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(button_row, text=self.tr("buttons.cancel"), command=self._cancel).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(button_row, text=self.tr("buttons.save"), command=self._save).pack(side=RIGHT)
        frame.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        self.install_folder_name_var.trace_add("write", self._refresh_install_folder_mode)
        self._refresh_install_folder_mode()
        show_modal_window(self.parent, self.window)

    def _use_file_name(self) -> None:
        dialog_options = {
            "parent": self.window,
            "title": self.tr("dialog.mod.select_file_title"),
        }
        initialdir = self._initial_file_dialog_dir()
        if initialdir is not None:
            dialog_options["initialdir"] = str(initialdir)
        path = filedialog.askopenfilename(**dialog_options)
        if path:
            self.install_folder_name_var.set(Path(path).stem)

    def _initial_file_dialog_dir(self) -> Path | None:
        current_game = getattr(self.parent, "current_game", None)
        if current_game is None:
            return None
        mods_path = Path(current_game.mods_path)
        if self.mod is not None:
            candidate_names = [self.mod.install_folder_name.strip(), self.mod.workshop_item_id]
            for candidate_name in candidate_names:
                if not candidate_name:
                    continue
                candidate_path = mods_path / candidate_name
                if candidate_path.exists() and candidate_path.is_dir():
                    return candidate_path
        if mods_path.exists() and mods_path.is_dir():
            return mods_path
        return None

    def _refresh_install_folder_mode(self, *_args) -> None:
        folder_name = self.install_folder_name_var.get().strip()
        if folder_name:
            mode_text = self.tr("dialog.mod.install_folder_mode_custom", folder_name=folder_name)
        else:
            mode_text = self.tr("dialog.mod.install_folder_mode_default")
        self.install_folder_mode_var.set(mode_text)

    def _save(self) -> None:
        item_id = self.item_id_var.get().strip()
        install_folder_name = self.install_folder_name_var.get().strip()
        if not item_id.isdigit():
            messagebox.showerror(APP_NAME, self.tr("message.modid_numeric"), parent=self.window)
            return
        validation_error = validate_install_folder_name(install_folder_name)
        if validation_error == "invalid_chars":
            messagebox.showerror(APP_NAME, self.tr("message.install_folder_invalid_chars"), parent=self.window)
            return
        if validation_error == "invalid_suffix":
            messagebox.showerror(APP_NAME, self.tr("message.install_folder_invalid_suffix"), parent=self.window)
            return
        self.result = {
            "workshop_item_id": item_id,
            "install_folder_name": install_folder_name,
        }
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


class SteamCMDDialog:
    """Dialog shown when SteamCMD is missing or not yet configured."""

    INSTALL_RESULT = "__install_steamcmd__"

    def __init__(self, parent, docs_url: str):
        self.parent = parent
        self.tr = parent.i18n.translate
        self.result: str | None = None
        self._tooltips: list[Tooltip] = []
        self.docs_url = docs_url
        self.window = Toplevel(parent)
        self.window.title(self.tr("dialog.steamcmd.title"))
        self.window.transient(parent)
        self.window.resizable(False, False)

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill=BOTH, expand=True)
        message = self.tr("dialog.steamcmd.message")
        ttk.Label(frame, text=message, justify="left").pack(anchor="w", fill=X)
        link = ttk.Label(frame, text=self.tr("dialog.steamcmd.link"), foreground="blue", cursor="hand2")
        link.pack(anchor="w", pady=(8, 10))
        link.bind("<Button-1>", lambda _event: webbrowser.open(self.docs_url))

        button_row = ttk.Frame(frame)
        button_row.pack(fill=X, pady=(4, 0))
        install_button = ttk.Button(button_row, text=self.tr("buttons.install_steamcmd"), command=self._install)
        install_button.pack(side=LEFT)
        select_button = ttk.Button(button_row, text=self.tr("buttons.select_steamcmd"), command=self._select_path)
        select_button.pack(side=LEFT, padx=(8, 0))
        open_docs_button = ttk.Button(button_row, text=self.tr("buttons.open_docs"), command=lambda: webbrowser.open(self.docs_url))
        open_docs_button.pack(side=LEFT, padx=8)
        later_button = ttk.Button(button_row, text=self.tr("buttons.later"), command=self._later)
        later_button.pack(side=RIGHT)
        self._tooltips.append(Tooltip(install_button, lambda: self.tr("tooltip.install_steamcmd")))
        self._tooltips.append(Tooltip(select_button, lambda: self.tr("tooltip.select_steamcmd")))
        self._tooltips.append(Tooltip(open_docs_button, lambda: self.tr("tooltip.open_docs")))
        self._tooltips.append(Tooltip(later_button, lambda: self.tr("tooltip.later")))
        self.window.protocol("WM_DELETE_WINDOW", self._later)
        show_modal_window(self.parent, self.window)

    def _select_path(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.window,
            title=self.tr("dialog.steamcmd.select_path_title"),
            filetypes=[
                (self.tr("steamcmd.filetype"), "steamcmd.exe"),
                (self.tr("dialog.steamcmd.filetype_exe"), "*.exe"),
                (self.tr("dialog.steamcmd.filetype_all"), "*.*"),
            ],
        )
        if path:
            self.result = path
            self.window.destroy()

    def _install(self) -> None:
        self.result = self.INSTALL_RESULT
        self.window.destroy()

    def _later(self) -> None:
        self.result = ""
        self.window.destroy()


class App(Tk):
    """Main application window and controller for the downloader."""

    def __init__(self):
        super().__init__()
        self.paths = get_app_paths()
        self.paths.base_dir.mkdir(parents=True, exist_ok=True)
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)

        self.db = Database(self.paths.db_path)
        self.i18n = TranslationManager(self._initial_language())
        self.tr = self.i18n.translate
        self.games = GameStore(self.paths.games_path)
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.current_game: Game | None = None
        self.current_game_id: str | None = self.db.get_setting("last_selected_game_id", "")
        self.checked_mod_ids: set[int] = set()
        self._pending_game_name_backfills: set[int] = set()
        self._pending_mod_name_backfills: set[int] = set()
        self._steamcmd_update_running = False
        self._steamcmd_install_running = False
        self._tooltips: list[Tooltip] = []

        saved_steamcmd = self.db.get_setting("steamcmd_path", "")
        self.steamcmd_manager = SteamCMDManager(saved_steamcmd)
        self.steamcmd_path = self.steamcmd_manager.discover()
        if self.steamcmd_path:
            self._set_steamcmd_path(self.steamcmd_path)

        self.title(self.tr("app.title"))
        self.geometry("1200x740")
        self.minsize(1040, 660)

        self._build_ui()
        self._load_games()
        self.after(120, self._poll_queue)
        self.after(300, self._ensure_steamcmd)

    def _initial_language(self) -> str:
        """Determine the initial UI language from settings or system locale."""

        saved_language = self.db.get_setting("ui_language", "").strip().lower()
        if saved_language:
            return saved_language
        locale_info = py_locale.getlocale()[0] or py_locale.getdefaultlocale()[0] or ""
        system_language = locale_info.split("_", 1)[0].lower() if locale_info else ""
        return system_language if system_language in LANGUAGE_CODES else DEFAULT_LANGUAGE

    def _build_ui(self) -> None:
        """Construct the main window layout."""

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(8, 8, 8, 3))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self.games_label = ttk.Label(top, text=self.tr("section.games"))
        self.games_label.grid(row=0, column=0, sticky="w")
        game_buttons = ttk.Frame(top)
        game_buttons.grid(row=0, column=2, sticky="e")
        self.add_game_button = ttk.Button(game_buttons, text=self.tr("buttons.add"), width=3, command=self._add_game)
        self.add_game_button.pack(side=LEFT)
        self.edit_game_button = ttk.Button(game_buttons, text=self.tr("buttons.edit"), command=self._edit_game)
        self.edit_game_button.pack(side=LEFT, padx=3)
        self.delete_game_button = ttk.Button(game_buttons, text=self.tr("buttons.delete"), command=self._delete_game)
        self.delete_game_button.pack(side=LEFT)
        self.steamcmd_button = ttk.Button(game_buttons, text=self.tr("buttons.steamcmd"), command=self._configure_steamcmd)
        self.steamcmd_button.pack(side=LEFT, padx=(8, 0))

        language_frame = ttk.Frame(top)
        language_frame.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.language_label = ttk.Label(language_frame, text=self.tr("language.label"))
        self.language_label.pack(side=LEFT, padx=(0, 4))
        self.language_var = StringVar(value=self._language_display_name(self.i18n.language))
        self.language_combo = ttk.Combobox(
            language_frame,
            textvariable=self.language_var,
            values=[self._language_display_name(code) for code in self._available_language_codes()],
            state="readonly",
            width=11,
        )
        self.language_combo.pack(side=LEFT)
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)
        self._add_tooltip(self.add_game_button, "tooltip.add_game")
        self._add_tooltip(self.edit_game_button, "tooltip.edit_game")
        self._add_tooltip(self.delete_game_button, "tooltip.delete_game")
        self._add_tooltip(self.steamcmd_button, "tooltip.steamcmd")
        self._add_tooltip(self.language_label, "tooltip.language")
        self._add_tooltip(self.language_combo, "tooltip.language")

        self.game_tree = ttk.Treeview(top, columns=("name", "appid", "mods_path"), show="headings", height=4, selectmode="browse")
        self.game_tree.column("name", width=240, anchor="w")
        self.game_tree.column("appid", width=100, anchor="w")
        self.game_tree.column("mods_path", width=600, anchor="w")
        self.game_tree.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self.game_tree.bind("<<TreeviewSelect>>", self._on_game_selected)
        self._add_tooltip(self.game_tree, "tooltip.game_table")

        game_scroll = ttk.Scrollbar(top, orient="vertical", command=self.game_tree.yview)
        self.game_tree.configure(yscrollcommand=game_scroll.set)
        game_scroll.grid(row=1, column=4, sticky="ns", pady=(6, 0))

        middle = ttk.Frame(self, padding=(8, 4, 8, 4))
        middle.grid(row=1, column=0, sticky="nsew")
        middle.columnconfigure(0, weight=1)
        middle.rowconfigure(2, weight=1)

        mod_header = ttk.Frame(middle)
        mod_header.grid(row=0, column=0, sticky="ew")
        mod_header.columnconfigure(0, weight=1)
        self.mod_title_var = StringVar(value=self.tr("mod.title.generic"))
        ttk.Label(mod_header, textvariable=self.mod_title_var).grid(row=0, column=0, sticky="w")

        mod_buttons = ttk.Frame(mod_header)
        mod_buttons.grid(row=0, column=1, sticky="e")
        self.add_mod_button = ttk.Button(mod_buttons, text=self.tr("buttons.add"), width=3, command=self._add_mod)
        self.add_mod_button.pack(side=LEFT)
        self.edit_mod_button = ttk.Button(mod_buttons, text=self.tr("buttons.edit"), command=self._edit_mod)
        self.edit_mod_button.pack(side=LEFT, padx=3)
        self.delete_mod_button = ttk.Button(mod_buttons, text=self.tr("buttons.delete"), command=self._delete_mod)
        self.delete_mod_button.pack(side=LEFT)
        self.check_updates_button = ttk.Button(mod_buttons, text=self.tr("buttons.check_updates"), command=self._check_updates)
        self.check_updates_button.pack(side=LEFT, padx=(8, 3))
        self.download_button = ttk.Button(mod_buttons, text=self.tr("buttons.download"), command=lambda: self._download_selected("download"))
        self.download_button.pack(side=LEFT, padx=3)
        self.update_button = ttk.Button(mod_buttons, text=self.tr("buttons.update"), command=lambda: self._download_selected("update"))
        self.update_button.pack(side=LEFT, padx=3)
        self._add_tooltip(self.add_mod_button, "tooltip.add_mod")
        self._add_tooltip(self.edit_mod_button, "tooltip.edit_mod")
        self._add_tooltip(self.delete_mod_button, "tooltip.delete_mod")
        self._add_tooltip(self.check_updates_button, "tooltip.check_updates")
        self._add_tooltip(self.download_button, "tooltip.download")
        self._add_tooltip(self.update_button, "tooltip.update")

        mod_select_bar = ttk.Frame(middle)
        mod_select_bar.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.select_all_mods_button = ttk.Button(
            mod_select_bar,
            text=self.tr("buttons.select_all_mods"),
            command=self._select_all_mods,
            width=5,
        )
        self.select_all_mods_button.pack(side=LEFT)
        self._add_tooltip(self.select_all_mods_button, "tooltip.select_all_mods")

        columns = (
            "selected",
            "name",
            "item_id",
            "install_folder",
            "version",
            "remote_updated",
            "compatible_game_version",
            "new_version",
            "last_downloaded",
            "status",
            "error",
        )
        self.mod_tree = ttk.Treeview(middle, columns=columns, show="headings", selectmode="browse", height=7)
        self.mod_headings = {
            "selected": "headings.selected",
            "name": "headings.mod_name",
            "item_id": "headings.item_id",
            "install_folder": "headings.install_folder",
            "version": "headings.version",
            "remote_updated": "headings.remote_updated",
            "compatible_game_version": "headings.compatible_game_version",
            "new_version": "headings.new_version",
            "last_downloaded": "headings.last_downloaded",
            "status": "headings.status",
            "error": "headings.error",
        }
        widths = {
            "selected": 48,
            "name": 210,
            "item_id": 108,
            "install_folder": 190,
            "version": 122,
            "remote_updated": 136,
            "compatible_game_version": 108,
            "new_version": 90,
            "last_downloaded": 136,
            "status": 142,
            "error": 224,
        }
        for key in columns:
            self.mod_tree.heading(key, text=self.tr(self.mod_headings[key]), anchor="center")
            self.mod_tree.column(key, width=widths[key], anchor="center", stretch=True)
        self.mod_tree.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        self.mod_tree.bind("<Button-1>", self._on_mod_click)
        self.mod_tree.bind("<Double-1>", lambda _event: self._edit_mod())
        self._add_tooltip(self.mod_tree, "tooltip.mod_table")
        self.mod_update_font = tkfont.nametofont("TkDefaultFont").copy()
        self.mod_update_font.configure(weight="bold")
        self.mod_tree.tag_configure("status_new", background="#f4f7fb")
        self.mod_tree.tag_configure("status_update", background="#ffd6d6", font=self.mod_update_font)
        self.mod_tree.tag_configure("status_downloaded", background="#e6f6ea")
        self.mod_tree.tag_configure("status_error", background="#fde8e8")

        mod_scroll = ttk.Scrollbar(middle, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=mod_scroll.set)
        mod_scroll.grid(row=2, column=1, sticky="ns", pady=(6, 0))

        legend = ttk.Frame(middle)
        legend.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Label(legend, text=self.tr("legend.title")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._legend_item(legend, 0, "#f4f7fb", self.tr("legend.new"))
        self._legend_item(legend, 1, "#ffd6d6", self.tr("legend.update_available"))
        self._legend_item(legend, 2, "#e6f6ea", self.tr("legend.downloaded"))
        self._legend_item(legend, 3, "#fde8e8", self.tr("legend.error"))

        bottom = ttk.Frame(self, padding=(8, 3, 8, 8))
        bottom.grid(row=2, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=1)
        bottom.rowconfigure(0, weight=1)

        self.log_label = ttk.Label(bottom, text=self.tr("section.log"))
        self.log_label.grid(row=0, column=0, sticky="w")
        text_frame = ttk.Frame(bottom)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        from tkinter import Text

        self.log_widget = Text(text_frame, height=8, wrap="word")
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_widget.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_widget.configure(yscrollcommand=log_scroll.set)
        self.log_widget.configure(state="disabled")

        status_bar = ttk.Frame(self)
        status_bar.grid(row=3, column=0, sticky="ew")
        status_bar.columnconfigure(0, weight=1)
        self.status_var = StringVar(value=self.tr("status.ready"))
        status = ttk.Label(status_bar, textvariable=self.status_var, relief="sunken", anchor="w")
        status.grid(row=0, column=0, sticky="ew")
        self.version_label = ttk.Label(status_bar, text=APP_VERSION, relief="sunken", anchor="e", width=8)
        self.version_label.grid(row=0, column=1, sticky="e")
        self._add_tooltip(status, "tooltip.status_bar")

        self._apply_translations()

    def _add_tooltip(self, widget, key: str) -> None:
        """Attach a localized tooltip to a widget."""

        self._tooltips.append(Tooltip(widget, lambda key=key: self.tr(key)))

    def _legend_item(self, parent, column: int, color: str, text: str) -> None:
        """Add one colored legend entry."""

        swatch = Label(parent, width=2, height=1, bg=color, relief="solid", borderwidth=1)
        swatch.grid(row=0, column=column * 2 + 1, sticky="w", padx=(0, 6))
        ttk.Label(parent, text=text).grid(row=0, column=column * 2 + 2, sticky="w", padx=(0, 14))

    def _mod_status_data(self, mod: Mod) -> tuple[str, str]:
        """Return the localized status text and Treeview tag for a mod."""

        if mod.download_status == "error":
            return self.tr("mod.status.error"), "status_error"
        if mod.new_version_available:
            return self.tr("mod.status.update_available"), "status_update"
        if mod.download_status == "downloaded":
            return self.tr("mod.status.downloaded"), "status_downloaded"
        return self.tr("mod.status.new"), "status_new"

    def _available_language_codes(self) -> list[str]:
        """Return the languages supported by the current locale files."""

        supported = self.i18n.available_languages()
        ordered = [code for code in LANGUAGE_CODES if code in supported]
        return ordered or supported

    def _language_display_name(self, language: str) -> str:
        """Return the display name shown in the language dropdown."""

        return self.tr(f"languages.{language}")

    def _language_code_from_selection(self, selection: str) -> str:
        """Map a dropdown label back to a locale code."""

        for code in self._available_language_codes():
            if selection == self._language_display_name(code):
                return code
        return DEFAULT_LANGUAGE

    def _apply_translations(self) -> None:
        """Refresh visible text after a language change."""

        self.title(self.tr("app.title"))
        self.games_label.configure(text=self.tr("section.games"))
        self.add_game_button.configure(text=self.tr("buttons.add"))
        self.edit_game_button.configure(text=self.tr("buttons.edit"))
        self.delete_game_button.configure(text=self.tr("buttons.delete"))
        self.steamcmd_button.configure(text=self.tr("buttons.steamcmd"))
        self.language_label.configure(text=self.tr("language.label"))
        self.language_combo.configure(values=[self._language_display_name(code) for code in self._available_language_codes()])
        self.language_var.set(self._language_display_name(self.i18n.language))
        self.add_mod_button.configure(text=self.tr("buttons.add"))
        self.edit_mod_button.configure(text=self.tr("buttons.edit"))
        self.delete_mod_button.configure(text=self.tr("buttons.delete"))
        self.select_all_mods_button.configure(text=self.tr("buttons.select_all_mods"))
        self.check_updates_button.configure(text=self.tr("buttons.check_updates"))
        self.download_button.configure(text=self.tr("buttons.download"))
        self.update_button.configure(text=self.tr("buttons.update"))
        self.log_label.configure(text=self.tr("section.log"))
        self.status_var.set(self.tr("status.ready"))
        self._refresh_tree_headings()
        self._refresh_mod_title()

    def _refresh_tree_headings(self) -> None:
        """Apply localized headings to the game and mod tables."""

        self.game_tree.heading("name", text=self.tr("headings.game_name"))
        self.game_tree.heading("appid", text=self.tr("headings.appid"))
        self.game_tree.heading("mods_path", text=self.tr("headings.mods_path"))
        for column, key in self.mod_headings.items():
            self.mod_tree.heading(column, text=self.tr(key), anchor="center")

    def _refresh_mod_title(self) -> None:
        """Refresh the mods section title for the active game."""

        if self.current_game:
            title = self.current_game.game_name or self.tr("game.fallback.app", app_id=self.current_game.steam_app_id)
            self.mod_title_var.set(self.tr("mod.title.single", game_name=title, app_id=self.current_game.steam_app_id))
        else:
            self.mod_title_var.set(self.tr("mod.title.generic"))

    def _on_language_selected(self, _event=None) -> None:
        """Persist and apply the selected UI language."""

        selected_code = self._language_code_from_selection(self.language_var.get())
        self.i18n.set_language(selected_code)
        self.tr = self.i18n.translate
        self.db.set_setting("ui_language", selected_code)
        self._apply_translations()
        self._load_games()
        self._refresh_mods()

    def _append_log(self, line: str) -> None:
        """Append a line to the on-screen log and the log file."""

        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", f"{line}\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")
        with self.paths.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _load_games(self) -> None:
        """Reload the game list and restore the current selection if possible."""

        loaded_games = self.games.load_games()
        for item in self.game_tree.get_children():
            self.game_tree.delete(item)
        for game in loaded_games:
            display_name = game.game_name or self.tr("game.fallback.app", app_id=game.steam_app_id)
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
        """Set the active game and refresh the mod view."""

        self.current_game = game
        self.current_game_id = game.id if game else None
        self.db.set_setting("last_selected_game_id", self.current_game_id or "")
        self._refresh_mod_title()
        self._refresh_mods()

    def _select_game_by_id(self, game_id: str) -> None:
        game = self.games.get_game(game_id)
        self._set_game(game)

    def _on_game_selected(self, _event=None) -> None:
        game = self._current_game_from_selection()
        self._set_game(game)

    def _refresh_mods(self) -> None:
        """Reload the mod list for the current game."""

        for item in self.mod_tree.get_children():
            self.mod_tree.delete(item)
        self.checked_mod_ids = set()
        if not self.current_game:
            self.status_var.set(self.tr("status.ready"))
            return
        mods = self.db.list_mods(self.current_game.id)
        self._reconcile_mod_install_paths(self.current_game, mods)
        for mod in mods:
            self._insert_mod_row(mod)
        self._schedule_mod_name_backfill(mods)
        self.status_var.set(self.tr("status.mod_count", count=len(mods)))

    def _insert_mod_row(self, mod: Mod) -> None:
        selected = self.tr("mod.selected.yes") if mod.id in self.checked_mod_ids else self.tr("mod.selected.no")
        status_text, tag = self._mod_status_data(mod)
        self.mod_tree.insert(
            "",
            "end",
            iid=str(mod.id),
            values=self._mod_row_values(mod, selected, status_text),
            tags=(tag,),
        )

    def _mod_row_values(
        self,
        mod: Mod,
        selected: str | None = None,
        status_text: str | None = None,
    ) -> tuple[str, str, str, str, str, str, str, str, str, str, str]:
        """Build the localized values tuple for a mod table row."""

        localized_status = status_text or self._mod_status_data(mod)[0]
        return (
            selected or (self.tr("mod.selected.yes") if mod.id in self.checked_mod_ids else self.tr("mod.selected.no")),
            mod.mod_name,
            mod.workshop_item_id,
            mod.install_folder_name or mod.workshop_item_id,
            mod.mod_version,
            mod.remote_updated_at,
            mod.compatible_game_version,
            self.tr("mod.boolean.yes") if mod.new_version_available else self.tr("mod.boolean.no"),
            mod.last_downloaded_at,
            localized_status,
            mod.last_error,
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

    def _select_all_mods(self) -> None:
        """Toggle selection for all visible mods."""

        if not self.current_game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        mods = self.db.list_mods(self.current_game.id)
        visible_mod_ids = {mod.id for mod in mods if mod.id is not None}
        if visible_mod_ids and visible_mod_ids.issubset(self.checked_mod_ids):
            self.checked_mod_ids.difference_update(visible_mod_ids)
        else:
            self.checked_mod_ids.update(visible_mod_ids)
        self._refresh_mod_rows()

    def _refresh_mod_rows(self) -> None:
        """Refresh existing mod rows after selection changes."""

        for row_id in self.mod_tree.get_children():
            mod = self.db.get_mod(int(row_id))
            if not mod:
                continue
            status_text, tag = self._mod_status_data(mod)
            self.mod_tree.item(row_id, values=self._mod_row_values(mod, status_text=status_text), tags=(tag,))

    def _effective_version_stamp(self, metadata, fallback: str = "") -> str:
        if metadata and getattr(metadata, "time_updated", ""):
            return metadata.time_updated
        return fallback or utc_now()

    @staticmethod
    def _effective_install_folder_name(mod: Mod) -> str:
        """Return the folder name actually used on disk for a mod."""

        return mod.install_folder_name.strip() or mod.workshop_item_id

    def _mod_install_path(self, game: Game, mod: Mod) -> Path:
        """Return the configured on-disk install path for a mod."""

        return Path(game.mods_path) / self._effective_install_folder_name(mod)

    def _rename_installed_mod_folder_if_needed(self, game: Game, old_mod: Mod, new_mod: Mod) -> None:
        """Rename an already installed mod folder when the target folder name changes."""

        old_path = self._mod_install_path(game, old_mod)
        new_path = self._mod_install_path(game, new_mod)
        if old_path == new_path or not old_path.exists():
            return
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            shutil.rmtree(new_path)
        old_path.rename(new_path)
        self._append_log(self.tr("log.mod_install_folder_renamed", old_path=old_path, new_path=new_path))

    def _reconcile_mod_install_paths(self, game: Game, mods: list[Mod]) -> None:
        """Align on-disk mod folders with configured custom target folder names."""

        for mod in mods:
            if not mod.install_folder_name.strip():
                continue
            legacy_id_mod = replace(mod, install_folder_name="")
            legacy_path = self._mod_install_path(game, legacy_id_mod)
            target_path = self._mod_install_path(game, mod)
            if legacy_path == target_path:
                continue
            if not legacy_path.exists() or target_path.exists():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.rename(target_path)
            self._append_log(self.tr("log.mod_install_folder_renamed", old_path=legacy_path, new_path=target_path))

    def _schedule_game_name_backfill(self, games: list[Game]) -> None:
        """Start background lookups for games that still lack a public name."""

        for game in games:
            if game.game_name.strip():
                continue
            if game.steam_app_id in self._pending_game_name_backfills:
                continue
            self._pending_game_name_backfills.add(game.steam_app_id)
            thread = threading.Thread(target=self._backfill_game_name_worker, args=(game,), daemon=True)
            thread.start()

    def _schedule_mod_name_backfill(self, mods: list[Mod]) -> None:
        """Start background lookups for mods that still lack a title."""

        for mod in mods:
            if mod.mod_name.strip():
                continue
            if mod.id in self._pending_mod_name_backfills:
                continue
            self._pending_mod_name_backfills.add(mod.id)
            thread = threading.Thread(target=self._backfill_mod_name_worker, args=(mod,), daemon=True)
            thread.start()

    def _backfill_game_name_worker(self, game: Game) -> None:
        """Resolve and persist a missing game name in the background."""

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
            self.output_queue.put(("log", self.tr("log.game_name_resolved", game_name=game_name)))
            self.output_queue.put(("refresh_games", game.id))
        except Exception as exc:
            self.output_queue.put(
                (
                    "log",
                    f"[backfill-game] failed for app_id={game.steam_app_id}: {exc}\n{traceback.format_exc()}",
                )
            )
        finally:
            self._pending_game_name_backfills.discard(game.steam_app_id)

    def _backfill_mod_name_worker(self, mod: Mod) -> None:
        """Resolve and persist a missing mod title in the background."""

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
            self.output_queue.put(("log", self.tr("log.mod_name_resolved", mod_name=metadata.title)))
            self.output_queue.put(("refresh", mod.game_id))
        except Exception as exc:
            self.output_queue.put(
                (
                    "log",
                    f"[backfill-mod] failed for workshop_item_id={mod.workshop_item_id}: {exc}\n{traceback.format_exc()}",
                )
            )
        finally:
            if mod.id is not None:
                self._pending_mod_name_backfills.discard(mod.id)

    def _on_mod_click(self, event) -> str | None:
        """Toggle the checkbox column for a clicked mod row."""

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
                status_text, tag = self._mod_status_data(mod)
                self.mod_tree.item(row_id, values=self._mod_row_values(mod, status_text=status_text), tags=(tag,))
            return "break"
        return None

    def _add_game(self) -> None:
        """Open the add-game flow and create a new entry."""

        dialog = GameDialog(self, self.tr("dialog.game.add.title"))
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        app_id = int(dialog.result["steam_app_id"])
        mods_path = dialog.result["mods_path"]
        game_id = game_id_from_appid(app_id)
        self._append_log(f"[add-game] requested app_id={app_id} mods_path={mods_path}")
        if self.games.get_game(game_id):
            self._append_log(f"[add-game] skipped duplicate game_id={game_id} app_id={app_id}")
            messagebox.showerror(APP_NAME, self.tr("message.game_exists"), parent=self)
            return
        self.status_var.set(self.tr("message.resolve_game_metadata"))
        try:
            game = Game(
                id=game_id,
                steam_app_id=app_id,
                game_name="",
                workshop_url=derive_workshop_url(app_id),
                mods_path=mods_path,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            self.games.upsert_game(game)
            fallback_name = self.tr("game.fallback.app", app_id=app_id)
            self._append_log(self.tr("log.game_added", game_name=fallback_name, app_id=app_id))
            self.db.set_setting("last_selected_game_id", game.id)
            self.current_game_id = game.id
            self._load_games()
            self._select_game_by_id(game.id)
            self.status_var.set(self.tr("status.game_added", game_name=fallback_name))
        except Exception as exc:
            self._append_log(f"[add-game] failed for app_id={app_id} mods_path={mods_path}: {exc}\n{traceback.format_exc()}")
            messagebox.showerror(APP_NAME, f"Could not add game: {exc}", parent=self)

    def _edit_game(self) -> None:
        """Edit the currently selected game."""

        game = self._current_game_from_selection()
        if not game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        dialog = GameDialog(self, self.tr("dialog.game.edit.title"), game)
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        app_id = int(dialog.result["steam_app_id"])
        mods_path = dialog.result["mods_path"]
        if app_id != game.steam_app_id:
            messagebox.showerror(APP_NAME, self.tr("message.change_appid_not_supported"), parent=self)
            return
        updated = replace(
            game,
            mods_path=mods_path,
            workshop_url=derive_workshop_url(app_id),
            updated_at=utc_now(),
        )
        self.games.upsert_game(updated)
        self.db.set_setting("last_selected_game_id", game.id)
        self._append_log(self.tr("log.game_updated", game_id=game.id))
        self._load_games()

    def _make_temp_install_dir(self, game: Game, mod: Mod) -> Path:
        """Return a unique temporary install directory for a download."""

        return self.paths.base_dir / "tmp_downloads" / game.id / mod.workshop_item_id / uuid.uuid4().hex

    def _delete_game(self) -> None:
        """Delete the currently selected game and its mods."""

        game = self._current_game_from_selection()
        if not game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        if not messagebox.askyesno(APP_NAME, self.tr("message.delete_game", game_id=game.id), parent=self):
            return
        self.games.delete_game(game.id)
        self.db.delete_mods_for_game(game.id)
        self._append_log(self.tr("log.game_deleted", game_id=game.id))
        self._load_games()

    def _add_mod(self) -> None:
        """Open the add-mod flow and create a new mod entry."""

        if not self.current_game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        dialog = ModDialog(self, self.tr("dialog.mod.add.title"))
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        workshop_item_id = dialog.result["workshop_item_id"]
        install_folder_name = dialog.result["install_folder_name"]
        url = derive_workshop_item_url(workshop_item_id)
        metadata = fetch_workshop_metadata(workshop_item_id)
        mod_name = metadata.title if metadata else self.tr("mod.fallback.workshop", workshop_item_id=workshop_item_id)
        remote_updated_at = self._effective_version_stamp(metadata)
        compatible_game_version = metadata.compatible_game_version if metadata else ""
        mod = create_mod(
            game_id=self.current_game.id,
            workshop_item_id=workshop_item_id,
            install_folder_name=install_folder_name,
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
        self._append_log(self.tr("log.mod_added", mod_name=mod_name, workshop_item_id=workshop_item_id))
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
        """Edit the currently selected mod."""

        mod = self._current_mod_from_selection()
        if not mod:
            messagebox.showinfo(APP_NAME, self.tr("message.select_mod"), parent=self)
            return
        dialog = ModDialog(self, self.tr("dialog.mod.edit.title"), mod)
        self.wait_window(dialog.window)
        if not dialog.result:
            return
        workshop_item_id = dialog.result["workshop_item_id"]
        install_folder_name = dialog.result["install_folder_name"]
        url = derive_workshop_item_url(workshop_item_id)
        metadata = fetch_workshop_metadata(workshop_item_id)
        mod_name = metadata.title if metadata else mod.mod_name
        remote_updated_at = self._effective_version_stamp(metadata, mod.remote_updated_at or mod.mod_version)
        compatible_game_version = metadata.compatible_game_version if metadata else mod.compatible_game_version
        updated_mod = replace(
            mod,
            workshop_item_id=workshop_item_id,
            install_folder_name=install_folder_name,
            mod_url=url,
            mod_name=mod_name,
            mod_version=mod.mod_version or remote_updated_at,
            compatible_game_version=compatible_game_version,
            remote_updated_at=remote_updated_at,
            updated_at=utc_now(),
        )
        try:
            self.db.update_mod_by_id(updated_mod)
            if self.current_game:
                self._rename_installed_mod_folder_if_needed(self.current_game, mod, updated_mod)
        except Exception as exc:
            messagebox.showerror(APP_NAME, self.tr("message.could_not_update_mod", error=exc), parent=self)
            return
        self._append_log(self.tr("log.mod_updated", mod_name=mod_name))
        self._refresh_mods()

    def _delete_mod(self) -> None:
        """Delete the currently selected mod."""

        mod = self._current_mod_from_selection()
        if not mod:
            messagebox.showinfo(APP_NAME, self.tr("message.select_mod"), parent=self)
            return
        if not messagebox.askyesno(APP_NAME, self.tr("message.delete_mod", mod_name=mod.mod_name), parent=self):
            return
        self.db.delete_mod(mod.id)
        self.checked_mod_ids.discard(mod.id)
        self._append_log(self.tr("log.mod_deleted", mod_name=mod.mod_name))
        self._refresh_mods()

    def _current_mod_from_selection(self) -> Mod | None:
        """Return the currently selected mod if it belongs to the active game."""

        selection = self.mod_tree.selection()
        if not selection:
            return None
        mod = self.db.get_mod(int(selection[0]))
        if mod and self.current_game and mod.game_id == self.current_game.id:
            return mod
        return None

    def _check_updates(self) -> None:
        """Start a background update check for all mods of the current game."""

        if not self.current_game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        mods = self.db.list_mods(self.current_game.id)
        if not mods:
            return
        self.status_var.set(self.tr("status.updating"))
        thread = threading.Thread(target=self._check_updates_worker, args=(self.current_game, mods), daemon=True)
        thread.start()

    def _check_updates_worker(self, game: Game, mods: list[Mod]) -> None:
        """Compare stored versions against remote workshop metadata."""

        for mod in mods:
            metadata = fetch_workshop_metadata(mod.workshop_item_id)
            if not metadata:
                self.output_queue.put(("log", self.tr("log.update_check_failed", mod_name=mod.mod_name)))
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
            self.output_queue.put(
                (
                    "log",
                    self.tr(
                        "log.checked_mod",
                        mod_name=metadata.title,
                        answer=self.tr("mod.boolean.yes") if new_version_available else self.tr("mod.boolean.no"),
                    ),
                )
            )
        self.output_queue.put(("refresh", game.id))
        self.output_queue.put(("status", self.tr("status.update_complete")))

    def _download_selected(self, mode: str) -> None:
        """Start a download or update run for the checked mods."""

        if not self.current_game:
            messagebox.showinfo(APP_NAME, self.tr("message.select_game"), parent=self)
            return
        if not self.steamcmd_path:
            messagebox.showerror(APP_NAME, self.tr("message.steamcmd_not_configured"), parent=self)
            return
        mods = self._selected_mods()
        if mode == "update":
            mods = [mod for mod in mods if mod.new_version_available]
        if not mods:
            if mode == "update":
                messagebox.showinfo(APP_NAME, self.tr("message.select_checked_mod_for_update"), parent=self)
            else:
                messagebox.showinfo(APP_NAME, self.tr("message.select_checked_mod_for_download"), parent=self)
            return
        thread = threading.Thread(target=self._download_worker, args=(self.current_game, mods, mode), daemon=True)
        self.status_var.set(self.tr("status.download_started", mode=self.tr(f"buttons.{mode}")))
        thread.start()

    def _download_worker(self, game: Game, mods: list[Mod], mode: str) -> None:
        """Run SteamCMD downloads in the background and persist outcomes."""

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
            self.output_queue.put(("log", self.tr("log.running_mode", mode=self.tr(f"buttons.{mode}"), mod_name=mod_name)))
            started_at = utc_now()
            try:
                result = steamcmd.run_download(
                    self.steamcmd_path,
                    game.steam_app_id,
                    mod.workshop_item_id,
                    temp_install_dir,
                    lambda line: self.output_queue.put(("log", line)),
                )
                finished_at = utc_now()
                output = result.output
                source_path = steamcmd.downloaded_workshop_path(
                    temp_install_dir,
                    game.steam_app_id,
                    mod.workshop_item_id,
                )
                if result.reported_error:
                    download_error = self.tr(
                        "error.steamcmd_download_rejected",
                        steam_error=result.reported_error,
                    )
                elif result.exit_code != 0:
                    download_error = self.tr("error.steamcmd_exit_code", exit_code=result.exit_code)
                elif not source_path.exists():
                    download_error = self.tr("error.downloaded_folder_missing", path=source_path)
                else:
                    download_error = ""
                success = not download_error
                if success:
                    target_path = steamcmd.move_downloaded_mod(
                        temp_install_dir,
                        Path(game.mods_path),
                        game.steam_app_id,
                        mod.workshop_item_id,
                        mod.install_folder_name,
                    )
                    legacy_id_path = Path(game.mods_path) / mod.workshop_item_id
                    if mod.install_folder_name and legacy_id_path != target_path and legacy_id_path.exists():
                        shutil.rmtree(legacy_id_path)
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
                    self.output_queue.put(("log", self.tr("log.completed_mod", mod_name=mod_name, path=target_path)))
                else:
                    self.db.update_mod_download_result(
                        mod.id,
                        mod_version=mod.mod_version,
                        remote_updated_at=remote_updated_at,
                        last_downloaded_at=mod.last_downloaded_at,
                        download_status="error",
                        new_version_available=mod.new_version_available,
                        last_error=download_error,
                    )
                    self.output_queue.put(("log", self.tr("log.error_mod", mod_name=mod_name, error=download_error)))
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
                self.output_queue.put(("log", self.tr("log.error_mod", mod_name=mod_name, error=exc)))
            finally:
                steamcmd.cleanup_temp_install_dir(temp_install_dir)
        self.output_queue.put(("refresh", game.id))
        self.output_queue.put(("status", self.tr("status.download_complete", mode=self.tr(f"buttons.{mode}"))))

    def _poll_queue(self) -> None:
        """Process messages from background workers on the Tk event loop."""

        try:
            while True:
                kind, payload = self.output_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "refresh":
                    self._refresh_mods()
                elif kind == "refresh_games":
                    self._load_games()
                elif kind == "select_game":
                    self.current_game_id = payload
                    self._load_games()
                elif kind == "steamcmd_path":
                    self._set_steamcmd_path(Path(payload))
                    self.status_var.set(self.tr("status.steamcmd_set", path=self.steamcmd_path))
                    self._append_log(self.tr("log.steamcmd_configured", path=self.steamcmd_path))
                elif kind == "status":
                    self.status_var.set(payload)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _ensure_steamcmd(self) -> None:
        """Make sure SteamCMD is configured before the user starts downloading."""

        if self.steamcmd_path:
            self.status_var.set(self.tr("status.steamcmd_set", path=self.steamcmd_path))
            self._start_steamcmd_update_check()
            return
        dialog = SteamCMDDialog(self, "https://developer.valvesoftware.com/wiki/SteamCMD")
        self.wait_window(dialog.window)
        if dialog.result is None:
            return
        if dialog.result == SteamCMDDialog.INSTALL_RESULT:
            self._start_steamcmd_install()
            return
        if dialog.result:
            self._set_steamcmd_path(Path(dialog.result))
            self.status_var.set(self.tr("status.steamcmd_set", path=self.steamcmd_path))
            self._append_log(self.tr("log.steamcmd_configured", path=self.steamcmd_path))
            self._start_steamcmd_update_check()
        else:
            self.status_var.set(self.tr("status.steamcmd_not_configured"))

    def _configure_steamcmd(self) -> None:
        """Configure SteamCMD or trigger a manual self-update check."""

        if self.steamcmd_path:
            self._start_steamcmd_update_check()
            return

        dialog = SteamCMDDialog(self, "https://developer.valvesoftware.com/wiki/SteamCMD")
        self.wait_window(dialog.window)
        if dialog.result == SteamCMDDialog.INSTALL_RESULT:
            self._start_steamcmd_install()
        elif dialog.result:
            self._set_steamcmd_path(Path(dialog.result))
            self.status_var.set(self.tr("status.steamcmd_set", path=self.steamcmd_path))
            self._append_log(self.tr("log.steamcmd_configured", path=self.steamcmd_path))
            self._start_steamcmd_update_check()

    def _set_steamcmd_path(self, path: Path) -> None:
        """Persist and cache the active SteamCMD executable path."""

        self.steamcmd_path = path
        self.steamcmd_manager.saved_path = str(path)
        self.db.set_setting("steamcmd_path", str(path))

    def _default_steamcmd_install_dir(self) -> Path:
        """Return the managed SteamCMD install directory."""

        return self.paths.base_dir / "SteamCMD"

    def _start_steamcmd_install(self) -> None:
        """Install SteamCMD in the managed app data directory."""

        if self._steamcmd_install_running:
            return
        self._steamcmd_install_running = True
        install_dir = self._default_steamcmd_install_dir()
        self.status_var.set(self.tr("status.steamcmd_installing"))
        self._append_log(self.tr("log.steamcmd_install_started", path=install_dir))
        thread = threading.Thread(target=self._steamcmd_install_worker, args=(install_dir,), daemon=True)
        thread.start()

    def _steamcmd_install_worker(self, install_dir: Path) -> None:
        """Download and prepare SteamCMD in the background."""

        try:
            manager = SteamCMDManager()
            steamcmd_path = manager.install(install_dir, lambda line: self.output_queue.put(("log", line)))
            self.output_queue.put(("steamcmd_path", str(steamcmd_path)))
            self.output_queue.put(("log", self.tr("log.steamcmd_install_complete", path=steamcmd_path)))
            self.output_queue.put(("status", self.tr("status.steamcmd_set", path=steamcmd_path)))
        except Exception as exc:
            self.output_queue.put(("log", self.tr("log.steamcmd_install_failed", error=exc)))
            self.output_queue.put(("status", self.tr("status.steamcmd_install_failed")))
        finally:
            self._steamcmd_install_running = False

    def _start_steamcmd_update_check(self) -> None:
        """Run SteamCMD once so its own updater can apply pending updates."""

        if not self.steamcmd_path or self._steamcmd_update_running:
            return
        self._steamcmd_update_running = True
        steamcmd_path = self.steamcmd_path
        self.status_var.set(self.tr("status.steamcmd_checking"))
        self._append_log(self.tr("log.steamcmd_update_check_started", path=steamcmd_path))
        thread = threading.Thread(target=self._steamcmd_update_worker, args=(steamcmd_path,), daemon=True)
        thread.start()

    def _steamcmd_update_worker(self, steamcmd_path: Path) -> None:
        """Run the SteamCMD self-updater in the background."""

        try:
            manager = SteamCMDManager(str(steamcmd_path))
            result = manager.run_self_update(steamcmd_path, lambda line: self.output_queue.put(("log", line)))
            if result.exit_code == 0:
                self.output_queue.put(("log", self.tr("log.steamcmd_update_check_complete", path=steamcmd_path)))
                self.output_queue.put(("status", self.tr("status.steamcmd_set", path=steamcmd_path)))
            else:
                self.output_queue.put(("log", self.tr("log.steamcmd_update_check_failed", exit_code=result.exit_code)))
                self.output_queue.put(("status", self.tr("status.steamcmd_update_failed")))
        except Exception as exc:
            self.output_queue.put(("log", self.tr("log.steamcmd_update_error", error=exc)))
            self.output_queue.put(("status", self.tr("status.steamcmd_update_failed")))
        finally:
            self._steamcmd_update_running = False


def run_app() -> None:
    """Launch the main Tkinter application."""

    app = App()
    app.mainloop()
