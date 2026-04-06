# PSux

PSux is a lightweight native Windows desktop terminal for developers moving from Ubuntu or Linux to Windows. It accepts common Linux-style commands, translates them to PowerShell or native Windows execution, and runs them without WSL, Git Bash, or Cygwin.

## Terminal UI

PSux uses a terminal-style continuous flow layout instead of a form-style output box and separate input box.

- Each pane looks like an independent terminal session.
- The active prompt is always visible at the bottom of the pane.
- The current path is shown directly in the prompt.
- Windows paths are displayed in a Linux-like form by default, for example `D:\Project\PSux` becomes `/d/Project/PSux`.
- Command history, output, and the next prompt all appear in a single scrollable transcript.

## Project Structure

```text
PSux/
├── main.py
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
- Multi-pane split view
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
