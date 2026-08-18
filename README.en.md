# Visor MD

[![Version](https://img.shields.io/github/v/release/PullAngel/visor-md?label=version&color=1C9E1C)](https://github.com/PullAngel/visor-md/releases/latest)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0a7d0a)](#installation)

*[Leer en español](README.md)*

A Markdown viewer and editor for Windows. Set it as the default app for `.md`
files, and they open instantly. It works offline, and it treats every document
it opens as someone else's content: opening a file makes no network request at
all.

### ▶ [Download VisorMD-portable.zip](https://github.com/PullAngel/visor-md/releases/latest/download/VisorMD-portable.zip)

Unzip and run. No installer, no dependencies. Also on the
[releases page](https://github.com/PullAngel/visor-md/releases), with the file
hash and previous versions.

![Visor MD in reading mode, with tabs and a Mermaid diagram](docs/screenshots/01-lectura.png)

## Why I built it

On Windows, a `.md` file opens in Notepad, which shows it as plain text, or
inside a code editor, which takes a while to start and is far more than you need
to read a file. I wanted the equivalent of double-clicking a PDF: something
light opens and the document is just there.

A second reason showed up later. A lot of Markdown these days isn't written by
the person reading it — it comes from someone else's repository, a PDF
converter, or an AI tool. A document of unknown origin shouldn't be able to do
anything surprising just by being opened, and that ended up being the part I
spent the most time on.

## What it does

- **Reading view** with full formatting: tables, task lists, syntax
  highlighting, GitHub alerts, Mermaid diagrams and LaTeX formulas, with a copy
  button on every code block.
- **Editing** in plain text with a formatting toolbar and shortcuts, plus a
  split view that renders as you type.
- **Tabs and windows that behave like a browser's**: drag to reorder, drop
  outside the bar to open in their own window, or onto another window to move
  them there. Opening eight files at once gives you eight tabs in one window.
- **Export to PDF** or HTML, and print.
- Opens `.txt` files too, with the option to convert them to `.md`.

<details>
<summary><b>Keyboard shortcuts</b></summary>

| Shortcut | Action |
| --- | --- |
| `Ctrl+T` / `Ctrl+W` | New tab / close tab |
| `Ctrl+Shift+N` | New window |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+R` / `Ctrl+E` | Reading / editing mode |
| `Ctrl+\` | Split view |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / Save as |
| `Ctrl+O` | Open |
| `Ctrl+F` / `Ctrl+H` | Find / Replace |
| `Ctrl+Shift+O` | Table of contents |
| `Ctrl+D` | Night or day theme |
| `Ctrl+P` | Print or save as PDF |
| `F11` | Borderless full screen |
| `Ctrl++` / `Ctrl+-` | Text size |
| `Ctrl+B` `Ctrl+I` `Ctrl+K` | Bold, italic, link |
| `Ctrl+1` to `Ctrl+3` | Headings H1 to H3 |
| `Ctrl+Shift+` `X` `C` `T` `7` `8` `.` | Strikethrough, code block, task, numbered list, list, quote |

While editing, `Enter` continues and renumbers the current list, `Tab` and
`Shift+Tab` indent the selection, and pasting a URL over selected text turns it
into a link.
</details>

<details>
<summary><b>Supported syntax and smaller features</b></summary>

Nested and numbered lists, aligned tables, code blocks inside lists and
blockquotes, inline and reference links, local images, HTML, `<details>`,
checkboxes, ATX and setext headings, escapes, four-backtick and `~~~` fences,
footnotes, autolinks, GitHub alerts (`> [!NOTE]`, `TIP`, `IMPORTANT`,
`WARNING`, `CAUTION`), LaTeX via KaTeX, Mermaid diagrams, and YAML frontmatter,
which is hidden the same way GitHub hides it.

- A context menu that changes with where you right-click: a tab, the editor, or
  the rendered document.
- Find and replace, in both reading and editing modes.
- A sidebar table of contents built from the document's headings.
- Switching from reading to editing keeps your place in the document.
- Unsaved tabs take their name from their content.
- Recent files, adjustable typeface, and detection of changes made by another
  program while the document is open.
</details>

## Security

A `.md` file is someone else's content. It can carry HTML, and that HTML can do
things nobody expects from a text document. The app assumes the file is hostile
until proven otherwise, which comes down to four properties:

1. **Opening a document makes no network request.** Not through an image,
   `srcset`, SVG, CSS, embedded media, a diagram, or a formula. A remote image
   is a tracker even without executing anything: it confirms you opened the file
   and hands over your IP. They load when you ask for them, not before.
2. **Nothing in the document executes.** All HTML goes through DOMPurify with an
   explicit protocol allowlist, and a CSP backs the sanitizer up underneath.
3. **A document can't read files it has no business reading.** Paths are
   validated after canonicalization, so the check lands on the file that will
   actually be opened rather than on the name that asked for it. Network paths
   are always rejected: resolving a `\\server\share` makes Windows hand over
   credentials without a single click.
4. **A document can't impersonate the app.** It stays contained in its own area,
   and what you copy from a code block is what you see.

The restrictions can be relaxed under **Advanced settings**, including trusted
folders for your own work. What isn't configurable is the sanitizer: you can
widen *what a document may access*, never *what it may execute*.

There's a dedicated suite, `tests/seguridad.py`, with its attack corpus in
`tests/security/`. On its first run it found three network paths I had assumed
were closed — `srcset`, inline SVG and `background-image` — and all three are
regression tests today.

The full write-up is in
[`docs/frontera-de-seguridad.md`](docs/frontera-de-seguridad.md) (Spanish).

## Installation

**Portable**: unzip
[`VisorMD-portable.zip`](https://github.com/PullAngel/visor-md/releases/latest/download/VisorMD-portable.zip)
and run `VisorMD.exe`. The folder can be moved to a USB stick or another PC;
settings live separately, in the Windows user profile.

**Installed**: run it once and pick **Instalar en este equipo** from the `···`
menu. It copies the app to `%LOCALAPPDATA%\Programs\VisorMD`, creates a Start
menu shortcut and registers `.md`, `.markdown` and `.txt`. No administrator
rights, and it uninstalls from Settings → Apps.

**As the default app**: Windows doesn't let an application set itself as the
default, so this step is always the user's. Right-click a `.md` file → **Open
with** → **Choose another app** → **Visor MD**, ticking *Always use this app*.

The executable isn't code-signed, so the first launch may show the SmartScreen
warning: **More info** → **Run anyway**.

> [!NOTE]
> The application interface is in Spanish.

## Screenshots

| | |
| --- | --- |
| ![Editing with split view](docs/screenshots/02-edicion-dividida.png) | ![Reading in the day theme](docs/screenshots/03-tema-dia.png) |
| Editing with split view and live rendering | The same document in the day theme |

![Advanced settings](docs/screenshots/04-configuracion-avanzada.png)

The restrictions are on by default, but they can be relaxed.

The documents in these screenshots are in [`examples/`](examples).

---

## Technical notes

### Architecture

| File | Contents |
| --- | --- |
| `src/main.py` | Windows, tabs, the JavaScript bridge, files and settings |
| `src/winshell.py` | Installation, file-type registration and uninstall |
| `src/web/render.js` | Markdown to HTML, sanitization and post-processing |
| `src/web/app.js` | State, tabs, shortcuts and calls into Python |
| `src/web/editor.js` | Writing aids over the textarea |
| `src/web/vendor/` | markdown-it, highlight.js, KaTeX, Mermaid and DOMPurify |

The interface runs on **WebView2**, the Edge engine Windows already ships, so
the executable doesn't bundle a browser of its own: 14 MB instead of the 150 an
Electron app would take. Python handles files, native dialogs and the Windows
registry; rendering and editing live in JavaScript, with a pywebview bridge
between them.

The editor is a native `<textarea>` rather than a third-party component: it
keeps the operating system's undo stack and avoids a dependency. Mermaid is
3.5 MB of the 4.3 MB of bundled libraries and only loads when a document
actually contains a diagram.

### Decisions worth the effort

**Files.** UTF-8, UTF-8 with BOM, UTF-16 with BOM and cp1252 are detected and
preserved on save, along with the BOM and the line ending, CRLF or LF: someone
else's file shouldn't change encoding just because you opened it. Saving is
atomic — temporary file, then replace — so a power cut can't leave it half
written. If the file changes outside the app, you're offered a reload when the
window regains focus.

**The window.** The title bar is the app's own, so tabs share a row with the
minimize and close buttons. Dropping the native frame also drops edge resizing,
Aero Snap and correct maximizing, and each piece has to be put back by hand:
[`docs/ventana-sin-marco.md`](docs/ventana-sin-marco.md) (Spanish).

**Many windows, one process.** Opening a new window is instant, and moving a tab
between windows needs no inter-process communication: the document travels
whole, with its encoding and its unsaved changes.

### Tests

Three suites, no frameworks:

- `tests/test_files.py` — reading and writing on disk: encodings, BOM, line
  endings, atomic saves and external changes.
- `tests/smoke.py` — drives the real application, not a mock, checking the
  rendering against an edge-case document, plus tabs, the context menu and the
  close dialog.
- `tests/seguridad.py` — the hostile corpus in `tests/security/`. It asserts
  properties: that no `on*` attribute survives, that no network request went
  out, that no path escaped the document's folder.

```powershell
python tests\test_files.py
python tests\smoke.py
python tests\seguridad.py
```

There's no GitHub Actions setup, deliberately: two of the three suites drive a
real WebView2 window, and a window that never paints has no measurements. A
runner without a desktop can't run them. Wiring up CI for the file suite alone
would put a green badge over a third of the coverage, which says less than no
badge at all.

### Development

```powershell
python -m pip install -r requirements.txt
python src\main.py tests\muestra.md
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

Development was AI-assisted, with the architecture, security and product
decisions reviewed and verified by hand. Several of the changes in recent
versions came out of exactly that verification: a close button that silently did
nothing, maximizing that grew the window without reflowing its contents, and
diagrams that lost their labels when the sanitizer was tightened.

## License

[GNU GPLv3](LICENSE) © 2026 [PullAngel](https://github.com/PullAngel)
