# File Renamer Pro

Renaming a hundred files by hand is the kind of small misery nobody should have to live through. **File Renamer Pro** does it for you — cleanly, safely, and in seconds.

Point it at a folder, pick a naming style, and watch it convert everything into tidy `camelCase`, `PascalCase`, `snake_case`, or `kebab-case`. You see every change *before* it happens, and you can undo anything. Your files are never at risk.

---

## Why you'll like it

- **It's smart about names.** It actually understands word boundaries and acronyms — `HTMLParser` becomes `html_parser`, not `h_t_m_l_parser`.
- **Nothing happens without your say-so.** Every rename is previewed first. Hit Apply when it looks right, undo if it doesn't.
- **It won't break your system.** System files (`.exe`, `.dll`, `.sys`) and protected folders (Windows, System32, …) are skipped automatically.
- **Files *and* folders.** Rename whole folder trees if you want — nested paths stay intact.
- **You're in control.** Choose which file types to include, go recursive or not, switch themes, resize the text. It remembers your settings and forgets your folder path the moment you close it.

---

## Install

### Windows — just run it
1> Download/clone the repo
2> Double-click build_portable.bat
3> Grab the finished app at dist [Folder]/FileRenamerPro_Portable.exe

> If Windows shows *"protected your PC,"* click **More info → Run anyway**. That warning just means the app isn't code-signed, which is normal for free tools.

**Want to build the .exe yourself?** Run `build_portable.bat` and find your file in `dist/`.

### Linux (or running from source)
```bash
git clone https://github.com/<your-username>/FileRenamerPro.git
cd FileRenamerPro
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Needs **Python 3.8+**. The same steps work on macOS too.

---

## Using it

1. **Browse** to your folder.
2. Pick a **case style**.
3. (Optional) tick **Include subfolders** or **Rename Folders**.
4. Hit **START** to preview, then **✓** to apply — or **↶ / ↷** to undo and redo.

The **⚙️ Settings** panel lets you tweak the theme, choose eligible file types, toggle safety protection, and turn on a plain-text log of every rename.

---

## Built with

Python and [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — that's the only dependency. The whole app lives in a single, readable `app.py`.

## License

[MIT](LICENSE) — free for personal and commercial use.
