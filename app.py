"""
File Renamer Pro v3.0
=====================
A standalone desktop GUI for batch-renaming files AND folders using intelligent
case conversion (camelCase, PascalCase, snake_case, kebab-case).

Single-window design: the Settings panel is embedded inside the main window as a
swappable VIEW with three tabs (Appearance / File Formats / Safety). No pop-up
window, so there is no CTkToplevel + input-grab + theme-redraw deadlock.

Key safety design:
    - "Safety Protection" skips system extensions (.exe/.dll/.sys/.ini) and known
      system directories.
    - Folder renaming is processed BOTTOM-UP (leaf folders before parents) so a
      parent is never renamed out from under its children -> no "path not found".

Architecture (clean OOP):
    - SettingsManager / Settings : persistent config (config.json)
    - ConversionUtils            : word-splitting + case conversion
    - VersionHistory             : ordered undo/redo state tracking
    - FileRenamerApp             : main window hosting Main + Settings views
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Dict
from datetime import datetime


# ============================================================================
# CONSTANTS / DESIGN LANGUAGE
# ============================================================================

# Supported file types, grouped by category. Add an extension under any group
# (or a brand-new group) and the Settings "File Formats" tab renders it under
# that heading automatically. "Other" holds everything that doesn't fit a
# specific media type.
FILE_TYPE_CATEGORIES: Dict[str, List[str]] = {
    "Music": [".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Documents & Notes": [".txt", ".md", ".pdf", ".docx", ".doc", ".rtf", ".odt"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
    "Spreadsheets & Data": [".xlsx", ".xls", ".csv", ".json", ".xml"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Other": [".html", ".css", ".js", ".py", ".log", ".epub"],
}

# Flat list of every supported extension (derived — single source of truth is
# the categorised dict above). Used for settings validation / "Select All".
SUPPORTED_FILE_TYPES: List[str] = [
    ext for exts in FILE_TYPE_CATEGORIES.values() for ext in exts
]

DEFAULT_EXTENSIONS: List[str] = [".mp3", ".pdf", ".docx", ".txt", ".jpg", ".png"]

# Safety layer: never touched while "Safety Protection" is ON.
PROTECTED_EXTENSIONS: Tuple[str, ...] = (".exe", ".dll", ".sys", ".ini")
PROTECTED_DIR_NAMES = {
    "windows", "system32", "syswow64", "program files", "program files (x86)",
    "$recycle.bin", "system volume information", "appdata", "programdata",
    "boot", "perflogs",
}

ACCENT_GREEN = "#4CAF50"
ACCENT_HOVER = "#3d8b40"

# --- Typography ------------------------------------------------------------
# Fonts are built as live CTkFont objects at runtime (see _build_fonts) so the
# Appearance tab can change family/size and have the whole UI update instantly.
# Each role is derived from a single BASE size: title = base+4, label = base+1,
# body = base, mono = base-1. The default base of 10 reproduces the original
# look exactly.
DEFAULT_FONT_FAMILY = "Helvetica"
DEFAULT_FONT_SIZE = "Medium"
MONO_FONT_FAMILY = "Courier New"  # log box stays monospace for column alignment

FONT_FAMILIES: List[str] = [
    "Helvetica", "Arial", "Verdana", "Segoe UI", "Times New Roman", "Georgia",
]
# Named size -> BASE point size.
FONT_SIZE_SCALE: Dict[str, int] = {
    "Small": 9,
    "Medium": 10,
    "Large": 12,
    "Extra Large": 14,
}

CONFIG_FILE = "config.json"

# Operation record type: (kind, old_path, new_path) where kind is FILE | FOLDER
Op = Tuple[str, str, str]


# ============================================================================
# SETTINGS & CONFIGURATION
# ============================================================================

@dataclass
class Settings:
    """Serializable application settings (persisted to config.json)."""
    dark_mode: bool = True
    selected_extensions: List[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    safety_protection: bool = True
    store_history: bool = True
    save_log: bool = False
    font_family: str = DEFAULT_FONT_FAMILY
    font_size: str = DEFAULT_FONT_SIZE
    last_folder_path: str = ""


class SettingsManager:
    """Loads and saves application settings to a local config.json file."""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = Path(config_path)
        self.settings = self.load_settings()

    def load_settings(self) -> Settings:
        """Load settings from JSON, falling back to defaults on any error."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                valid = {k: data[k] for k in Settings().__dict__ if k in data}
                return Settings(**valid)
            except (json.JSONDecodeError, OSError, TypeError) as e:
                print(f"[SettingsManager] Could not load config: {e}")
        return Settings()

    def save_settings(self) -> None:
        """Persist settings to config.json (never raises into the UI)."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.settings), f, indent=2)
        except OSError as e:
            print(f"[SettingsManager] Could not save config: {e}")


# ============================================================================
# CONVERSION UTILITIES
# ============================================================================

class ConversionUtils:
    """Intelligent word-splitting and case conversion logic."""

    @staticmethod
    def split_words(text: str) -> List[str]:
        """
        Split text into words by detecting:
          - snake_case / kebab-case separators
          - camelCase / PascalCase boundaries
          - acronym -> Word transitions (e.g. 'HTMLParser' -> 'HTML', 'Parser')
        """
        if not text:
            return []
        text = re.sub(r"[-_\s]+", " ", text)                    # explicit separators
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)     # camelCase boundary
        text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)  # acronym boundary
        return [w for w in text.split() if w]

    @staticmethod
    def to_camel_case(text: str) -> str:
        words = ConversionUtils.split_words(text)
        if not words:
            return text
        return words[0].lower() + "".join(w.capitalize() for w in words[1:])

    @staticmethod
    def to_pascal_case(text: str) -> str:
        return "".join(w.capitalize() for w in ConversionUtils.split_words(text))

    @staticmethod
    def to_snake_case(text: str) -> str:
        return "_".join(w.lower() for w in ConversionUtils.split_words(text))

    @staticmethod
    def to_kebab_case(text: str) -> str:
        return "-".join(w.lower() for w in ConversionUtils.split_words(text))

    @staticmethod
    def convert(text: str, case_format: str) -> str:
        converters = {
            "camelCase": ConversionUtils.to_camel_case,
            "PascalCase": ConversionUtils.to_pascal_case,
            "snake_case": ConversionUtils.to_snake_case,
            "kebab-case": ConversionUtils.to_kebab_case,
        }
        return converters.get(case_format, lambda x: x)(text)


# ============================================================================
# VERSION HISTORY (UNDO / REDO)
# ============================================================================

@dataclass
class HistoryState:
    """A single recorded rename operation (ORDERED list of file/folder ops)."""
    timestamp: str
    operation: str
    folder_path: str
    case_format: str
    operations: List[Op]  # ordered: files first, then folders bottom-up

    def __repr__(self):
        return f"[{self.timestamp}] {self.operation} ({len(self.operations)} items)"


class VersionHistory:
    """Stack-based undo/redo manager."""

    def __init__(self, max_history: int = 50):
        self.history: List[HistoryState] = []
        self.current_index: int = -1
        self.max_history = max_history

    def add_state(self, state: HistoryState) -> None:
        self.history = self.history[: self.current_index + 1]  # drop redo tail
        self.history.append(state)
        self.current_index += 1
        if len(self.history) > self.max_history:
            self.history.pop(0)
            self.current_index -= 1

    def undo(self) -> Optional[HistoryState]:
        if self.can_undo():
            state = self.history[self.current_index]
            self.current_index -= 1
            return state
        return None

    def redo(self) -> Optional[HistoryState]:
        if self.can_redo():
            self.current_index += 1
            return self.history[self.current_index]
        return None

    def can_undo(self) -> bool:
        return self.current_index >= 0

    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1

    def clear(self) -> None:
        self.history.clear()
        self.current_index = -1


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class FileRenamerApp(ctk.CTk):
    """Main window hosting both the Main task view and the Settings view."""

    def __init__(self):
        super().__init__()

        # --- Managers / state ----------------------------------------------
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings
        self.history = VersionHistory()
        self.current_preview: List[Op] = []
        self.current_operation: dict = {}
        self.extension_vars: Dict[str, tk.BooleanVar] = {}
        # Per-folder ORIGINAL -> LATEST rename map for the Save Log feature.
        # Key: normcased working-folder path. Value: list of {kind, orig, current}.
        self._log_chains: Dict[str, List[Dict[str, str]]] = {}

        # --- Live fonts (driven by the Appearance tab) ---------------------
        self._build_fonts()

        # --- Window --------------------------------------------------------
        self.title("File Renamer Pro v3.0")
        self.geometry("750x600")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark" if self.settings.dark_mode else "light")
        self.after(10, self.center_window)

        # --- Tk variables --------------------------------------------------
        self.case_var = tk.StringVar(value="snake_case")
        self.subfolder_var = tk.BooleanVar(value=False)
        self.rename_folders_var = tk.BooleanVar(value=False)
        self.folder_path = tk.StringVar(value=self.settings.last_folder_path)
        self.safety_var = tk.BooleanVar(value=self.settings.safety_protection)

        # --- Build UI ------------------------------------------------------
        self.create_header()
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        self.main_view = ctk.CTkFrame(self.container, fg_color="transparent")
        self.settings_view = ctk.CTkFrame(self.container, fg_color="transparent")

        self.build_main_view()
        self.build_settings_view()
        self.update_history_buttons()
        self.show_main()

        # Privacy: wipe the remembered folder path when the window is closed.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """On exit, clear the last-used folder path so no personal path is left
        in config.json, then close the window. (History is in-memory only, so it
        is discarded automatically.)"""
        try:
            self.settings.last_folder_path = ""
            self.settings_manager.save_settings()
        except Exception as e:  # never block the app from closing
            print(f"[FileRenamerApp] Cleanup on close failed: {e}")
        self.destroy()

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------ #
    # Typography (live fonts shared by every widget)
    # ------------------------------------------------------------------ #
    def _base_size(self) -> int:
        """Resolve the configured size name to a BASE point size (safe fallback)."""
        return FONT_SIZE_SCALE.get(self.settings.font_size, FONT_SIZE_SCALE[DEFAULT_FONT_SIZE])

    def _build_fonts(self):
        """Create the live CTkFont objects once. Roles scale off a single base."""
        family = self.settings.font_family or DEFAULT_FONT_FAMILY
        base = self._base_size()
        self.font_title = ctk.CTkFont(family=family, size=base + 4, weight="bold")
        self.font_label = ctk.CTkFont(family=family, size=base + 1, weight="bold")
        self.font_body = ctk.CTkFont(family=family, size=base)
        # Log box keeps a fixed monospace family so columns stay aligned; only
        # its size tracks the chosen scale.
        self.font_mono = ctk.CTkFont(family=MONO_FONT_FAMILY, size=base - 1)

    def _apply_fonts(self):
        """Reconfigure the existing font objects -> every widget updates live."""
        family = self.settings.font_family or DEFAULT_FONT_FAMILY
        base = self._base_size()
        self.font_title.configure(family=family, size=base + 4)
        self.font_label.configure(family=family, size=base + 1)
        self.font_body.configure(family=family, size=base)
        self.font_mono.configure(size=base - 1)  # family stays monospace

    # ------------------------------------------------------------------ #
    # Header + view navigation
    # ------------------------------------------------------------------ #
    def create_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(header, text="File Renamer Pro v3.0", font=self.font_title).pack(side="left")

        nav = ctk.CTkFrame(header, fg_color="transparent")
        nav.pack(side="right")
        self.main_nav_btn = ctk.CTkButton(
            nav, text="📋", width=40, height=40, font=("Helvetica", 18), command=self.show_main)
        self.main_nav_btn.pack(side="left", padx=4)
        self.settings_nav_btn = ctk.CTkButton(
            nav, text="⚙️", width=40, height=40, font=("Helvetica", 18), command=self.show_settings)
        self.settings_nav_btn.pack(side="left", padx=4)

    def show_main(self):
        self.settings_view.pack_forget()
        self.main_view.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        self._highlight_nav("main")

    def show_settings(self):
        self.main_view.pack_forget()
        self.settings_view.pack(fill="both", expand=True, padx=15, pady=(5, 15))
        self._highlight_nav("settings")

    def _highlight_nav(self, active: str):
        on, off = ACCENT_GREEN, ("gray75", "gray25")
        self.main_nav_btn.configure(fg_color=on if active == "main" else off)
        self.settings_nav_btn.configure(fg_color=on if active == "settings" else off)

    # ------------------------------------------------------------------ #
    # MAIN VIEW
    # ------------------------------------------------------------------ #
    def build_main_view(self):
        main = self.main_view

        ctk.CTkLabel(main, text="Select Folder:", font=self.font_label).pack(anchor="w", pady=(0, 5))
        folder_frame = ctk.CTkFrame(main)
        folder_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkEntry(
            folder_frame, textvariable=self.folder_path,
            placeholder_text="Browse to select a folder...", font=self.font_body,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(
            folder_frame, text="Browse", width=80, font=("Helvetica", 10, "bold"),
            command=self.browse_folder,
        ).pack(side="left")

        ctk.CTkLabel(main, text="Case Format:", font=self.font_label).pack(anchor="w", pady=(0, 8))
        case_frame = ctk.CTkFrame(main)
        case_frame.pack(fill="x", pady=(0, 12))
        for case in ["camelCase", "PascalCase", "snake_case", "kebab-case"]:
            ctk.CTkRadioButton(
                case_frame, text=case, variable=self.case_var, value=case, font=self.font_body,
            ).pack(side="left", padx=(10, 15), pady=10)

        # Operation toggles row: Include subfolders + Rename Folders
        toggles = ctk.CTkFrame(main, fg_color="transparent")
        toggles.pack(fill="x", pady=(0, 12))
        ctk.CTkCheckBox(
            toggles, text="Include subfolders", variable=self.subfolder_var, font=self.font_body,
        ).pack(side="left", padx=(0, 25))
        ctk.CTkCheckBox(
            toggles, text="Rename Folders", variable=self.rename_folders_var, font=self.font_body,
        ).pack(side="left")

        ctk.CTkLabel(main, text="Operation Log:", font=self.font_label).pack(anchor="w", pady=(0, 5))
        self.log_box = ctk.CTkTextbox(main, font=self.font_mono, border_width=1, border_color="gray30")
        self.log_box.pack(fill="both", expand=True, pady=(0, 10))
        self.refresh_log_colors()
        self.log_box.configure(state="disabled")
        self.append_log("Ready. Select a folder to begin.", is_info=True)

        # Footer: version control (Undo/Redo/Apply) + Start
        footer = ctk.CTkFrame(main)
        footer.pack(fill="x")
        left = ctk.CTkFrame(footer, fg_color="transparent")
        left.pack(side="left")
        self.undo_btn = ctk.CTkButton(
            left, text="↶", width=40, height=40, font=("Helvetica", 14, "bold"),
            command=self.undo_operation)
        self.undo_btn.pack(side="left", padx=5)
        self.redo_btn = ctk.CTkButton(
            left, text="↷", width=40, height=40, font=("Helvetica", 14, "bold"),
            command=self.redo_operation)
        self.redo_btn.pack(side="left", padx=5)
        ctk.CTkButton(
            left, text="✓", width=40, height=40, font=("Helvetica", 14, "bold"),
            fg_color=ACCENT_GREEN, hover_color=ACCENT_HOVER, command=self.apply_renaming,
        ).pack(side="left", padx=5)
        self.start_btn = ctk.CTkButton(
            footer, text="🚀 START", height=40, font=("Helvetica", 11, "bold"),
            fg_color=ACCENT_GREEN, hover_color=ACCENT_HOVER, command=self.start_preview)
        self.start_btn.pack(side="right", fill="x", expand=True, padx=(15, 0))

    # ------------------------------------------------------------------ #
    # SETTINGS VIEW (embedded — three tabbed sections)
    # ------------------------------------------------------------------ #
    def build_settings_view(self):
        view = self.settings_view
        ctk.CTkLabel(view, text="⚙️  Settings", font=self.font_title).pack(anchor="w", pady=(0, 10))

        tabs = ctk.CTkTabview(view)
        tabs.pack(fill="both", expand=True)
        tab_appearance = tabs.add("Appearance")
        tab_formats = tabs.add("File Formats")
        tab_safety = tabs.add("Safety")
        tab_history = tabs.add("History")

        # --- Tab 1: Appearance --------------------------------------------
        ctk.CTkLabel(tab_appearance, text="Theme", font=self.font_label).pack(anchor="w", pady=(12, 6))
        self.theme_switch = ctk.CTkSwitch(
            tab_appearance, text="Dark Mode", font=self.font_body, command=self.on_theme_toggle)
        if self.settings.dark_mode:
            self.theme_switch.select()
        else:
            self.theme_switch.deselect()
        self.theme_switch.pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(
            tab_appearance, text="Switches the entire app between Light and Dark instantly.",
            font=self.font_body, text_color="gray60", wraplength=600, justify="left",
        ).pack(anchor="w", pady=(0, 16))

        # Font Style (family)
        ctk.CTkLabel(tab_appearance, text="Font Style", font=self.font_label).pack(anchor="w", pady=(0, 6))
        self.font_family_menu = ctk.CTkOptionMenu(
            tab_appearance, values=FONT_FAMILIES, font=self.font_body,
            command=self.on_font_family_change)
        self.font_family_menu.set(
            self.settings.font_family if self.settings.font_family in FONT_FAMILIES
            else DEFAULT_FONT_FAMILY)
        self.font_family_menu.pack(anchor="w", pady=(0, 14))

        # Font Size (named scale -> base point size)
        ctk.CTkLabel(tab_appearance, text="Font Size", font=self.font_label).pack(anchor="w", pady=(0, 6))
        self.font_size_menu = ctk.CTkSegmentedButton(
            tab_appearance, values=list(FONT_SIZE_SCALE.keys()),
            font=self.font_body, command=self.on_font_size_change)
        self.font_size_menu.set(
            self.settings.font_size if self.settings.font_size in FONT_SIZE_SCALE
            else DEFAULT_FONT_SIZE)
        self.font_size_menu.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            tab_appearance,
            text="Font Style and Size apply to the whole app instantly and are saved.",
            font=self.font_body, text_color="gray60", wraplength=600, justify="left",
        ).pack(anchor="w")

        # --- Tab 2: File Formats (checkboxes grouped by category) ---------
        ctk.CTkLabel(
            tab_formats, text="Which file extensions should be renamed?", font=self.font_label,
        ).pack(anchor="w", pady=(12, 8))

        # Scrollable area: many extensions across several categories.
        scroll = ctk.CTkScrollableFrame(tab_formats, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        cols = 4
        for category, exts in FILE_TYPE_CATEGORIES.items():
            ctk.CTkLabel(
                scroll, text=category, font=self.font_label, text_color=ACCENT_GREEN,
            ).pack(anchor="w", pady=(8, 2))
            grid = ctk.CTkFrame(scroll, fg_color="transparent")
            grid.pack(fill="x", anchor="w")
            for idx, ext in enumerate(exts):
                var = tk.BooleanVar(value=ext in self.settings.selected_extensions)
                self.extension_vars[ext] = var
                ctk.CTkCheckBox(
                    grid, text=ext, variable=var, command=self.on_extensions_change,
                    font=self.font_body,
                ).grid(row=idx // cols, column=idx % cols, sticky="w", padx=10, pady=6)

        quick = ctk.CTkFrame(tab_formats, fg_color="transparent")
        quick.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(
            quick, text="Select All", height=30, font=self.font_body, fg_color="gray40",
            hover_color="gray30", command=lambda: self._set_all(True),
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(
            quick, text="Clear All", height=30, font=self.font_body, fg_color="gray40",
            hover_color="gray30", command=lambda: self._set_all(False),
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        # --- Tab 3: Safety Constraints ------------------------------------
        ctk.CTkLabel(
            tab_safety, text="Safety Constraints (Production Layer)", font=self.font_label,
        ).pack(anchor="w", pady=(12, 6))
        self.safety_switch = ctk.CTkSwitch(
            tab_safety, text="Enable Safety Protection", font=self.font_body,
            command=self.on_safety_toggle)
        if self.settings.safety_protection:
            self.safety_switch.select()
        else:
            self.safety_switch.deselect()
        self.safety_switch.pack(anchor="w", pady=(0, 10))
        protected = ", ".join(PROTECTED_EXTENSIONS)
        ctk.CTkLabel(
            tab_safety,
            text=(f"When ON, system files ({protected}) and system folders "
                  f"(Windows, System32, Program Files, …) are SKIPPED and never "
                  f"renamed.\n\nWhen OFF, everything matching your filters is renamed "
                  f"— use with caution."),
            font=self.font_body, text_color="gray60", wraplength=600, justify="left",
        ).pack(anchor="w")

        # --- Tab 4: History -----------------------------------------------
        ctk.CTkLabel(
            tab_history, text="Undo / Redo History", font=self.font_label,
        ).pack(anchor="w", pady=(12, 6))
        self.history_switch = ctk.CTkSwitch(
            tab_history, text="Store History", font=self.font_body,
            command=self.on_history_toggle)
        if self.settings.store_history:
            self.history_switch.select()
        else:
            self.history_switch.deselect()
        self.history_switch.pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(
            tab_history,
            text=("When ON, every applied rename is recorded so you can Undo/Redo "
                  "it. When OFF, new renames are NOT recorded (your existing history "
                  "is kept until you clear it)."),
            font=self.font_body, text_color="gray60", wraplength=600, justify="left",
        ).pack(anchor="w", pady=(0, 14))

        self.history_count_label = ctk.CTkLabel(
            tab_history, text="", font=self.font_body, text_color="gray60")
        self.history_count_label.pack(anchor="w", pady=(0, 8))
        ctk.CTkButton(
            tab_history, text="🗑  Clear All History", height=32, font=self.font_body,
            fg_color="gray40", hover_color="gray30", command=self.clear_all_history,
        ).pack(anchor="w")
        self._refresh_history_count()

        # Save Log -- write a log.txt into the folder each rename runs in.
        ctk.CTkLabel(
            tab_history, text="Log File", font=self.font_label,
        ).pack(anchor="w", pady=(18, 6))
        self.save_log_switch = ctk.CTkSwitch(
            tab_history, text="Save Log", font=self.font_body,
            command=self.on_save_log_toggle)
        if self.settings.save_log:
            self.save_log_switch.select()
        else:
            self.save_log_switch.deselect()
        self.save_log_switch.pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(
            tab_history,
            text=("When ON, a log.txt is kept in the folder you renamed in, showing "
                  "each item's ORIGINAL name -> its LATEST name (intermediate tries "
                  "in the same session are collapsed). When OFF, no log file is "
                  "created. (Saved as plain ASCII text.)"),
            font=self.font_body, text_color="gray60", wraplength=600, justify="left",
        ).pack(anchor="w")

    # ------------------------------------------------------------------ #
    # Settings handlers (auto-persist; cannot crash the UI)
    # ------------------------------------------------------------------ #
    def on_theme_toggle(self):
        """Theme flip is deferred one tick so the switch finishes its own
        redraw first (prevents any reentrant hang)."""
        self.settings.dark_mode = (self.theme_switch.get() == 1)
        self.settings_manager.save_settings()
        self.after(0, self._apply_theme)

    def _apply_theme(self):
        ctk.set_appearance_mode("dark" if self.settings.dark_mode else "light")
        self.refresh_log_colors()

    def on_font_family_change(self, choice: str):
        """Apply a new font family across the whole UI and persist it."""
        self.settings.font_family = choice
        self.settings_manager.save_settings()
        self._apply_fonts()

    def on_font_size_change(self, choice: str):
        """Apply a new font size scale across the whole UI and persist it."""
        self.settings.font_size = choice
        self.settings_manager.save_settings()
        self._apply_fonts()

    def on_extensions_change(self):
        self.settings.selected_extensions = [
            ext for ext, var in self.extension_vars.items() if var.get()
        ]
        self.settings_manager.save_settings()

    def on_safety_toggle(self):
        self.settings.safety_protection = (self.safety_switch.get() == 1)
        self.safety_var.set(self.settings.safety_protection)
        self.settings_manager.save_settings()

    def _set_all(self, value: bool):
        for var in self.extension_vars.values():
            var.set(value)
        self.on_extensions_change()

    def on_history_toggle(self):
        """Toggle whether new renames are recorded. Existing history is kept."""
        self.settings.store_history = (self.history_switch.get() == 1)
        self.settings_manager.save_settings()

    def on_save_log_toggle(self):
        """Toggle whether a log.txt is written into the working folder."""
        self.settings.save_log = (self.save_log_switch.get() == 1)
        self.settings_manager.save_settings()

    def clear_all_history(self):
        """Wipe the entire undo/redo stack instantly (no confirmation)."""
        self.history.clear()
        self.update_history_buttons()
        self._refresh_history_count()
        self.append_log("History cleared.", is_info=True)

    def _refresh_history_count(self):
        """Update the 'N recorded operation(s)' label in the History tab."""
        if hasattr(self, "history_count_label"):
            n = len(self.history.history)
            self.history_count_label.configure(
                text=f"{n} recorded operation(s) in history.")

    # ------------------------------------------------------------------ #
    # Session log file (Settings -> History -> Save Log)
    # ------------------------------------------------------------------ #
    def _resolve_log_dir(self, fallback: str) -> str:
        """Return the live working folder to drop log.txt into.

        Prefers the current root in the path box (which is kept pointing at the
        live folder even after the root itself is renamed); falls back to the
        original operation folder; returns "" if neither exists."""
        live = self.folder_path.get().strip()
        if live and os.path.isdir(live):
            return live
        if fallback and os.path.isdir(fallback):
            return fallback
        return ""

    def _record_rename_log(self, ops: List[Op], fallback_folder: str) -> None:
        """Fold `ops` into the session's ORIGINAL -> LATEST map for the work
        folder, then rewrite its log.txt.

        Intermediate renames are collapsed: if a file went A -> B earlier and now
        goes B -> C, the log shows only A -> C. Items that end up back at their
        original name are omitted. No-op unless Save Log is on and there is
        something to record."""
        if not self.settings.save_log or not ops:
            return
        log_dir = self._resolve_log_dir(fallback_folder)
        if not log_dir:
            self.append_log("Save Log: working folder not found; log not written.",
                            is_info=False)
            return

        chain = self._log_chains.setdefault(os.path.normcase(log_dir), [])
        for kind, old, new in ops:
            for entry in chain:
                # Extend an existing chain whose latest name is this op's source.
                if os.path.normcase(entry["current"]) == os.path.normcase(old):
                    entry["current"] = new
                    break
            else:
                chain.append({"kind": kind, "orig": old, "current": new})

        self._flush_log(log_dir, chain)

    def _flush_log(self, log_dir: str, chain: List[Dict[str, str]]) -> None:
        """Overwrite log_dir/log.txt with the consolidated, net-change-only list."""
        rows = [e for e in chain
                if os.path.normcase(e["orig"]) != os.path.normcase(e["current"])]
        log_path = os.path.join(log_dir, "log.txt")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "File Renamer Pro - rename log",
            f"Last updated : {ts}",
            f"Renamed items: {len(rows)}",
            "=" * 64,
        ]
        for e in rows:
            lines.append(
                f"  {e['kind']:6} {os.path.basename(e['orig'])}  ->  {os.path.basename(e['current'])}")

        try:
            # Overwrite ("w") so only ORIGINAL -> LATEST is kept, no intermediate
            # blocks. Strict ASCII by request; non-ASCII chars become '?'.
            with open(log_path, "w", encoding="ascii", errors="replace") as f:
                f.write("\n".join(lines) + "\n")
            self.append_log(f"Log updated: {log_path}", is_info=True)
        except OSError as err:
            self.append_log(f"Could not write log.txt: {err}", is_info=False)

    # ------------------------------------------------------------------ #
    # Log helpers
    # ------------------------------------------------------------------ #
    def refresh_log_colors(self):
        if not hasattr(self, "log_box"):
            return
        dark = ctk.get_appearance_mode().lower() == "dark"
        self.log_box.configure(
            text_color="white" if dark else "black",
            fg_color="gray10" if dark else "gray90",
        )

    def append_log(self, message: str, is_info: bool = False):
        self.log_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = "ℹ️" if is_info else "✓"
        self.log_box.insert("end", f"{prefix} [{ts}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Safety helpers
    # ------------------------------------------------------------------ #
    def _is_protected_file(self, name: str) -> bool:
        return self.settings.safety_protection and name.lower().endswith(PROTECTED_EXTENSIONS)

    def _is_protected_dir(self, path: str) -> bool:
        if not self.settings.safety_protection:
            return False
        return os.path.basename(os.path.normpath(path)).lower() in PROTECTED_DIR_NAMES

    # ------------------------------------------------------------------ #
    # Path-building helpers (return original path = "no-op" when unsafe/empty)
    # ------------------------------------------------------------------ #
    def _file_new_path(self, path: str, case_format: str) -> str:
        directory = os.path.dirname(path)
        stem, ext = os.path.splitext(os.path.basename(path))
        converted = ConversionUtils.convert(stem, case_format)
        if not converted:  # guard: never produce an empty filename
            return path
        return os.path.join(directory, converted + ext)

    def _folder_new_path(self, path: str, case_format: str) -> str:
        directory = os.path.dirname(path)
        converted = ConversionUtils.convert(os.path.basename(path), case_format)
        if not converted:  # guard: never produce an empty folder name
            return path
        return os.path.join(directory, converted)

    # ------------------------------------------------------------------ #
    # Core: gather ordered operations (files first, then folders bottom-up)
    # ------------------------------------------------------------------ #
    def gather_operations(self, root: str, case_format: str,
                          include_subfolders: bool, rename_folders: bool) -> List[Op]:
        """
        Build the ordered operation list according to the behaviour matrix:

          Rename Folders OFF:
              rename files (recursive if Include Subfolders else root-only)
          Rename Folders ON + Include Subfolders OFF:
              rename ONLY the root folder name
          Rename Folders ON + Include Subfolders ON:
              rename root + every subfolder + all files recursively

        Files are emitted first (renamed while the tree is intact); folders are
        emitted bottom-up (leaf folders before parents) so paths never break.
        """
        if not os.path.isdir(root):
            raise ValueError(f"Invalid folder path: {root}")

        exts = tuple(self.settings.selected_extensions)
        ops: List[Op] = []

        # ---- Decide what to collect -------------------------------------
        if rename_folders and not include_subfolders:
            collect_files = False          # Scenario A: root folder only
            files_recursive = False
        else:
            collect_files = True
            files_recursive = include_subfolders

        # ---- FILES (emitted first) --------------------------------------
        if collect_files and exts:
            file_paths: List[str] = []
            if files_recursive:
                for r, _dirs, names in os.walk(root):
                    file_paths.extend(os.path.join(r, n) for n in names)
            else:
                for n in os.listdir(root):
                    p = os.path.join(root, n)
                    if os.path.isfile(p):
                        file_paths.append(p)

            for p in sorted(file_paths):
                name = os.path.basename(p)
                if not name.lower().endswith(exts):
                    continue
                if self._is_protected_file(name):
                    continue
                new = self._file_new_path(p, case_format)
                if new != p:
                    ops.append(("FILE", p, new))

        # ---- FOLDERS (emitted bottom-up: leaves first, root last) -------
        if rename_folders:
            sub_dirs: List[str] = []
            if include_subfolders:
                for r, dirs, _names in os.walk(root):
                    sub_dirs.extend(os.path.join(r, d) for d in dirs)
                # Deepest paths first -> guarantees children before parents.
                sub_dirs.sort(key=lambda p: p.count(os.sep), reverse=True)

            for d in sub_dirs:
                if self._is_protected_dir(d):
                    continue
                new = self._folder_new_path(d, case_format)
                if new != d:
                    ops.append(("FOLDER", d, new))

            # Root last (it is the shallowest parent).
            if self._is_protected_dir(root):
                self.append_log(f"Protected system folder skipped: {root}", is_info=True)
            else:
                new_root = self._folder_new_path(root, case_format)
                if new_root != root:
                    ops.append(("FOLDER", root, new_root))

        return ops

    # ------------------------------------------------------------------ #
    # Actions: preview / apply / undo / redo
    # ------------------------------------------------------------------ #
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select a folder")
        if folder:
            self.folder_path.set(folder)
            self.settings.last_folder_path = folder
            self.settings_manager.save_settings()
            self.append_log(f"Folder selected: {folder}", is_info=True)

    def start_preview(self):
        folder = self.folder_path.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Invalid Folder", "Please select a valid folder.")
            self.append_log("Error: invalid folder path.", is_info=False)
            return

        include_sub = self.subfolder_var.get()
        rename_folders = self.rename_folders_var.get()

        if not rename_folders and not self.settings.selected_extensions:
            messagebox.showwarning(
                "No File Types",
                "No file types are enabled. Open ⚙️ Settings → File Formats to select some.",
            )
            return

        try:
            ops = self.gather_operations(folder, self.case_var.get(), include_sub, rename_folders)
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n{e}")
            self.append_log(f"Error: {e}", is_info=False)
            return

        if not ops:
            messagebox.showinfo("Nothing to Rename", "No matching files or folders were found.")
            self.append_log("Nothing to rename with the current options.", is_info=True)
            return

        self.clear_log()
        n_files = sum(1 for k, _, _ in ops if k == "FILE")
        n_dirs = sum(1 for k, _, _ in ops if k == "FOLDER")
        self.append_log(
            f"Preview: {n_files} file(s), {n_dirs} folder(s) "
            f"[Safety: {'ON' if self.settings.safety_protection else 'OFF'}]",
            is_info=True,
        )
        for kind, old, new in ops:
            self.append_log(f"[{kind}] {os.path.basename(old)} → {os.path.basename(new)}")

        self.current_preview = ops
        self.current_operation = {
            "folder": folder, "case_format": self.case_var.get(),
            "include_subfolders": include_sub, "rename_folders": rename_folders,
        }

    def apply_renaming(self):
        if not self.current_preview:
            messagebox.showwarning("Nothing to Apply", "Run 🚀 START to preview first.")
            return

        applied: List[Op] = []
        errors: List[str] = []
        for kind, old, new in self.current_preview:  # already ordered safely
            try:
                if not os.path.exists(old):
                    errors.append(f"[{kind}] Missing: {os.path.basename(old)}")
                    continue
                if os.path.exists(new) and os.path.normcase(old) != os.path.normcase(new):
                    errors.append(f"[{kind}] Target exists: {os.path.basename(new)}")
                    continue
                os.rename(old, new)
                if kind == "FOLDER" and self.folder_path.get() == old:
                    self.folder_path.set(new)  # keep the path box pointing at live root
                applied.append((kind, old, new))
                self.append_log(f"[{kind}] Renamed: {os.path.basename(old)} → {os.path.basename(new)}")
            except PermissionError:
                errors.append(f"[{kind}] Permission denied / read-only: {os.path.basename(old)}")
            except OSError as e:
                errors.append(f"[{kind}] {os.path.basename(old)}: {e}")

        if applied and self.settings.store_history:
            self.history.add_state(HistoryState(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                operation=f"Renamed {len(applied)} item(s)",
                folder_path=self.current_operation.get("folder", ""),
                case_format=self.current_operation.get("case_format", ""),
                operations=applied,
            ))
            self.update_history_buttons()
            self._refresh_history_count()

        if applied:
            self._record_rename_log(applied, self.current_operation.get("folder", ""))

        msg = f"Renamed {len(applied)} item(s)."
        if errors:
            msg += f"\n\n{len(errors)} issue(s):\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n…and {len(errors) - 10} more."
        (messagebox.showwarning if errors else messagebox.showinfo)("Rename Complete", msg)
        self.append_log(f"Applied {len(applied)} rename(s); {len(errors)} error(s).", is_info=True)

        self.current_preview = []
        self.current_operation = {}

    def undo_operation(self):
        state = self.history.undo()
        if not state:
            return
        # Reverse order so parents are restored before their children.
        errors, performed = self._run_batch(list(reversed(state.operations)), reverse=True)
        self.update_history_buttons()
        self.append_log(f"Undo: {state.operation}", is_info=True)
        self._record_rename_log(performed, state.folder_path)
        if errors:
            messagebox.showwarning("Undo Issues", "\n".join(errors[:10]))

    def redo_operation(self):
        state = self.history.redo()
        if not state:
            return
        errors, performed = self._run_batch(state.operations, reverse=False)
        self.update_history_buttons()
        self.append_log(f"Redo: {state.operation}", is_info=True)
        self._record_rename_log(performed, state.folder_path)
        if errors:
            messagebox.showwarning("Redo Issues", "\n".join(errors[:10]))

    def _run_batch(self, ops: List[Op], reverse: bool) -> Tuple[List[str], List[Op]]:
        """Execute a sequence of renames. When reverse=True, swap old/new.

        Returns (errors, performed) where `performed` lists the (kind, src, dst)
        renames that actually succeeded — used for the session log."""
        errors: List[str] = []
        performed: List[Op] = []
        for kind, old, new in ops:
            src, dst = (new, old) if reverse else (old, new)
            try:
                if not os.path.exists(src):
                    errors.append(f"[{kind}] Missing: {os.path.basename(src)}")
                    continue
                if os.path.exists(dst) and os.path.normcase(src) != os.path.normcase(dst):
                    errors.append(f"[{kind}] Target exists: {os.path.basename(dst)}")
                    continue
                os.rename(src, dst)
                if kind == "FOLDER" and self.folder_path.get() == src:
                    self.folder_path.set(dst)
                performed.append((kind, src, dst))
                self.append_log(f"[{kind}] Renamed: {os.path.basename(src)} → {os.path.basename(dst)}")
            except PermissionError:
                errors.append(f"[{kind}] Permission denied: {os.path.basename(src)}")
            except OSError as e:
                errors.append(f"[{kind}] {os.path.basename(src)}: {e}")
        return errors, performed

    def update_history_buttons(self):
        self.undo_btn.configure(state="normal" if self.history.can_undo() else "disabled")
        self.redo_btn.configure(state="normal" if self.history.can_redo() else "disabled")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = FileRenamerApp()
    app.mainloop()
