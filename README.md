# File Renamer Pro

A clean, safe desktop app for **batch-renaming files and folders** with intelligent
case conversion — `camelCase`, `PascalCase`, `snake_case`, and `kebab-case`. Built
with Python and [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).

> Preview every change before it happens, undo any rename, and keep your files
> safe with built-in protection for system files and folders.

---

## ✨ Features

- **Smart case conversion** — converts names between `camelCase`, `PascalCase`,
  `snake_case`, and `kebab-case`. Detects word boundaries, separators, and
  acronyms automatically (e.g. `HTMLParser` → `html_parser`).
- **Files *and* folders** — rename files only, or whole folder trees. Folders are
  renamed bottom-up so nested paths never break.
- **Preview before apply** — nothing is changed until you review the plan and hit
  Apply.
- **Undo / Redo** — full history of rename operations within a session.
- **Safety protection** — system files (`.exe`, `.dll`, `.sys`, `.ini`) and system
  folders (Windows, System32, Program Files, …) are skipped automatically.
- **Recursive option** — include or exclude subfolders.
- **Appearance** — light/dark theme, plus adjustable **font size** and
  **font style** that update the whole UI instantly.
- **Categorized file formats** — choose which extensions to rename, grouped by
  type (Music, Video, Documents, Images, Data, Archives, Other).
- **Save Log** *(optional)* — writes a `log.txt` into the folder you worked in,
  showing each item's **original name → final name** (intermediate retries in a
  session are collapsed). Plain ASCII.
- **Privacy-friendly** — the last-used folder path is cleared automatically when
  you close the app.
- **Portable** — ships as a single `.exe`; no Python install needed.

---

## 📥 Download & Run

### Option A — Portable executable (Windows, easiest)
1. Go to the [**Releases**](../../releases) page.
2. Download **`FileRenamerPro_Portable.exe`**.
3. Double-click to run. No installation required.

> **Note on the SmartScreen warning:** because the app is not code-signed,
> Windows may show *"Windows protected your PC."* Click **More info → Run anyway**.
> This is normal for free, unsigned apps.

### Option B — Run from source (Windows / macOS / Linux)
```bash
# 1. Get the code
git clone https://github.com/<your-username>/FileRenamerPro.git
cd FileRenamerPro

# 2. (Recommended) create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```
Requires **Python 3.8+**.

---

## 🖱️ How to use

1. **Browse** to the folder you want to work in.
2. Pick a **case format** (`camelCase` / `PascalCase` / `snake_case` / `kebab-case`).
3. Optionally tick **Include subfolders** and/or **Rename Folders**.
4. Click **🚀 START** to preview every rename in the log.
5. Click **✓** to apply, or **↶ / ↷** to undo / redo.

---

## ⚙️ Settings

Open the **⚙️** button (top-right). Settings are saved automatically.

| Tab | What it does |
|-----|--------------|
| **Appearance** | Dark/Light theme, font size, and font style. |
| **File Formats** | Toggle which extensions are eligible, grouped by category. |
| **Safety** | Enable/disable protection for system files and folders. |
| **History** | Store undo/redo history, clear all history, and toggle **Save Log**. |

---

## 🔨 Building the portable .exe yourself

```bash
pip install pyinstaller customtkinter
```
Then run the helper script (Windows):
```bash
build_portable.bat
```
…or the equivalent command directly:
```bash
python -m PyInstaller --onefile --windowed --name FileRenamerPro_Portable --collect-all customtkinter --noconfirm app.py
```
The result appears in `dist/FileRenamerPro_Portable.exe`.

---

## 📁 Project structure

```
FileRenamerPro/
├── app.py               # The entire application (single file)
├── requirements.txt     # Python dependencies
├── build_portable.bat   # One-click portable-exe build script (Windows)
├── README.md            # This file
├── LICENSE              # MIT license
└── .gitignore           # Excludes build artifacts and user config
```

`config.json` (your saved settings) and `log.txt` are created at runtime and are
intentionally **not** committed to the repository.

---

## 🏗️ Under the hood

A clean object-oriented design, all in `app.py`:

- **`Settings` / `SettingsManager`** — persistent config (`config.json`).
- **`ConversionUtils`** — word-splitting and case conversion.
- **`VersionHistory`** — undo/redo state tracking.
- **`FileRenamerApp`** — the main window (Main + embedded Settings views).

Only dependency: **CustomTkinter** (plus the Python standard library).

---

## 🔐 Privacy & safety

- Renames are **previewed** and **reversible**.
- **Safety Protection** prevents touching system files/folders.
- The remembered folder path is **wiped on exit**.
- The optional log is a plain local `.txt`; nothing is ever sent anywhere.

---

## 📝 License

Released under the [MIT License](LICENSE). Free for personal and commercial use.
