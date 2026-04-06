# PSux

PSux is a lightweight native Windows desktop terminal for developers moving from Ubuntu or Linux to Windows. It accepts common Linux-style commands, translates them to PowerShell or native Windows execution, and runs them without WSL, Git Bash, or Cygwin.

## Terminal UI

PSux uses a terminal-style continuous flow layout instead of a form-style output box and separate input box.

- Each pane looks like an independent terminal session.
- The active prompt is always visible at the bottom of the pane.
- The current path is shown directly in the prompt.
- Windows paths are displayed in a Linux-like form by default, for example `D:\Project\PSux` becomes `/d/Project/PSux`.
- Command history, output, and the next prompt all appear in a single scrollable transcript.

## Tabs

PSux now supports top-level terminal workspaces with tabs.

- Each tab is an independent terminal workspace.
- Each tab keeps its own:
  - current working directory state
  - command history
  - environment variables
  - output transcript
  - split pane layout
- New tab: toolbar `New Tab` button or `Ctrl+T`
- Close current tab: `Ctrl+W`
- Rename tab: double-click the tab label
- At least one tab is always kept alive, so closing tabs will not leave the UI in a broken state.

### Tab State Management

- Data structure: each tab is a `TerminalWorkspace` widget defined in `ui/workspace_tabs.py`.
- Each `TerminalWorkspace` owns one `PaneManager`.
- Each `PaneManager` owns its own pane tree, split layout, and per-pane `SessionState`.
- Because each tab contains a different `PaneManager` instance, tab switching naturally preserves independent workspace state without global mutation.

## PowerShell Native Commands

PSux supports both Linux-style compatibility commands and native PowerShell commands.

Execution priority:

1. Internal special commands such as `cd`, `export`, `history`, `clear`, and `Set-Location`
2. Linux compatibility commands that PSux translates
3. `git ...` passthrough and local `./xxx.bat` / `./xxx.exe`
4. Everything else runs as a native PowerShell command

Examples that now run directly as PowerShell:

```powershell
Get-ChildItem
Get-Location
Set-Location ui
Get-Process
Select-String "PSux" README.md
Test-Path README.md
New-Item demo.txt
Remove-Item demo.txt
```

This design keeps Linux muscle memory for common commands while still letting Windows developers use real PowerShell without fighting the translator.

## Quick Commands

PSux includes a lightweight Quick Commands palette for long, high-frequency commands such as Unreal build commands, complex Git flows, and PowerShell or Python scripts.

- Open from the top `Quick Commands` button or with `Ctrl+Shift+P`.
- The main window stays terminal-first because the palette is a popup dialog instead of a permanent side panel.
- Commands are always inserted into or executed in the current active pane.
- Each quick command stores:
  - name
  - category
  - full command content
  - optional note
- Supported actions:
  - insert into current pane input
  - run immediately in current pane
  - copy to clipboard
  - create
  - edit
  - delete

### Quick Commands Data Structure

```json
{
  "id": "5f5b1ff7cf2b428dbd54de43cfb9f6bd",
  "name": "UE5 Editor Build",
  "category": "Unreal Build",
  "command": "RunUAT.bat BuildCookRun -project=\"D:\\Projects\\Game\\Game.uproject\" -platform=Win64",
  "note": "Local editor build for Win64"
}
```

### JSON Storage Format

Quick commands are persisted locally in:

```text
%APPDATA%\PSux\quick_commands.json
```

Stored JSON format:

```json
{
  "version": 1,
  "commands": [
    {
      "id": "5f5b1ff7cf2b428dbd54de43cfb9f6bd",
      "name": "UE5 Editor Build",
      "category": "Unreal Build",
      "command": "RunUAT.bat BuildCookRun -project=\"D:\\Projects\\Game\\Game.uproject\" -platform=Win64",
      "note": "Local editor build for Win64"
    }
  ]
}
```

### Why This UI Stays Simple

- The terminal remains the main visual surface.
- Quick Commands is hidden until needed, so it does not compete with the Ubuntu-style terminal experience.
- The list view only shows compact name and category rows.
- Full command content and note are shown only for the selected item.
- Insert and run actions are scoped to the current active pane, which keeps split-pane behavior intuitive.

## Project Structure

```text
PSux/
├── main.py
├── quick_commands/
│   ├── __init__.py
│   ├── dialog.py
│   ├── manager.py
│   ├── models.py
│   └── storage.py
├── requirements.txt
├── README.md
├── executor/
│   ├── __init__.py
│   └── command_executor.py
├── history/
│   ├── __init__.py
│   └── command_history.py
├── session/
│   ├── __init__.py
│   └── session_state.py
├── translator/
│   ├── __init__.py
│   ├── command_translator.py
│   ├── models.py
│   └── parser.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── pane_manager.py
│   ├── terminal_pane.py
│   ├── workspace_tabs.py
│   └── widgets.py
└── utils/
    ├── __init__.py
    ├── errors.py
    ├── path_utils.py
    └── text.py
```

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Package to EXE

```powershell
pyinstaller --noconfirm --windowed --name PSux main.py
```

The generated executable will be in `dist\PSux\PSux.exe`.

## Command Support Levels

### fully_supported

- File and directory: `ls`, `pwd`, `cd`, `mkdir`, `rm`, `cp`, `mv`, `cat`, `touch`
- Search and text:
  - `grep "abc" file.txt`
  - `grep -n "abc" file.txt`
  - `grep -r "abc" .`
  - `grep -rn "abc" .`
  - `grep -rni "abc" .`
  - `grep -irn "abc" .`
  - `grep -rin "abc" .`
  - recursive grep without a path defaults to `.`
  - empty patterns such as `grep -rni "" .`
- Find:
  - `find . -name "*.cpp"`
  - `find . -iname "*.cpp"`
  - `find . -iname "*readme*"`
  - `find . -type f -iname "*.txt"`
  - `find . -type d -name "src"`
- Environment and helpers: `echo`, `clear`, `which`, `export`, `env`, `history`
- File inspection helpers: `head`, `tail`, `wc`, `sort`, `basename`, `dirname`, `realpath`
- Links: `ln`

### partially_supported

- `ln -s`
  - Uses native Windows symbolic links and may need Developer Mode or elevation.
- `vim file.txt`
  - Opens Notepad as a compatibility editor, not full Vim.
- `less file.txt`
  - Opens Notepad as a compatibility viewer, not a true pager.
- `uniq`
  - Supports file input and optional `-c`, without pipe-based stdin mode yet.
- `tree`
  - Uses the native Windows `tree` command when available, otherwise falls back to recursive listing.
- `ps`
  - Supports `ps`, `ps aux`, `ps -ef`, `ps -p PID`, and `ps NAME`.
- `kill`
  - Supports `kill PID`, `kill -9 PID`, and `kill -f NAME`.
- `open`
  - Uses Windows `Start-Process` to open files, folders, URLs, or the current directory.

### fallback_supported

- `git ...`
  - Any `git` command is passed through to the system Git executable in the current pane session.
- Local executables:
  - `./build.bat`
  - `./tool.exe`
  - `./subdir/run.bat`
- Other PATH executables such as `python`, `node`, `npm`, `cargo`, and `kubectl`

## UI Features

- Terminal-style transcript with inline prompt
- Current prompt format: `PSux:/d/Project/PSux$`
- Tab completion for commands and paths
- Quick Commands popup via toolbar button or `Ctrl+Shift+P`
- Top tab workspaces with independent split layouts and session state
- Multi-pane split view
- New tab: `Ctrl+T`
- Horizontal split: `Ctrl+Shift+H`
- Vertical split: `Ctrl+Shift+V`
- Run current command: `Enter` or `Ctrl+Enter`
- Clear output: `Ctrl+L`
- Close pane: `Ctrl+W`
- Independent pane session state:
  - current directory
  - environment variables from `export`
  - command history
  - output content

## Test Checklist

Run these inside PSux:

```text
pwd
ls
mkdir testdir
cd testdir
pwd
touch a.txt
echo hello
cat a.txt
grep -rn hello .
grep -rni "hello"
find . -name "*.txt"
find . -iname "*readme*" -type f
export FOO=bar
echo $FOO
git status
git rebase --continue
head -n 5 README.md
tail -3 README.md
wc -l README.md
sort README.md
uniq -c README.md
history
basename README.md .md
dirname README.md
realpath README.md
env
vim test.txt
./build.bat
./tool.exe --help
```

Also verify:

- Split horizontally and vertically.
- Switch the left pane to one directory and the right pane to another.
- Set `export FOO=left` in one pane and `export FOO=right` in another pane, then run `echo $FOO`.
- Browse independent command history with arrow keys in each pane.

## Extend Command Translation

1. Open `translator/command_translator.py`.
2. Add a new handler method such as `_translate_head`.
3. Register it in `self._handlers`.
4. Return one of these execution plans:
   - `internal`: mutate pane state only, for example `cd`, `export`, `clear`
   - `powershell`: run translated PowerShell
   - `native`: run a Windows executable directly
   - `batch`: run `.bat` through `cmd.exe /c`
5. Set `support_level` to `fully_supported`, `partially_supported`, or `fallback_supported` so compatibility stays explicit.
6. Use `compatibility_note` when the command is a simplified compatibility mode such as `vim` or `less`.
7. Keep new command-specific logic inside the translator so the rest of the app stays unchanged.

## Notes

- PSux MVP does not implement full bash syntax.
- Pipelines, redirects, and chained shell expressions are intentionally deferred.
- `ln -s` may require Developer Mode or elevated privileges on Windows.
- `export` is scoped to the current pane session only.
