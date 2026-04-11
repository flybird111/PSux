# Quick Command Terminal

`Quick Command Terminal` is a Windows desktop app built with Python and `CustomTkinter`.

It combines two parts:

- A PowerShell-first terminal workspace with tabs and split panes
- A separate `Quick Command` window for managing reusable command groups

The app is designed for local Windows use and stores its command data in `data.json`.

## Features

- PowerShell terminal as the main interface
- Multiple tabs
- Horizontal and vertical split panes
- Separate `Quick Command` popup window
- Three-level command organization:
  - `Group`
  - `Item`
  - `Commands`
- Local persistence in `data.json`
- Send one command or `Run All` commands into the active terminal pane
- Copy command text to clipboard
- `cd -` compatibility in the embedded terminal
- Command and path completion support via `Tab`

## Project Files

- [quick_command.py](./quick_command.py): main application
- [data.json](./data.json): saved command data
- [requirements.txt](./requirements.txt): Python dependencies

## Requirements

- Windows
- Python 3.11+ recommended
- PowerShell available on the system

## Install

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python quick_command.py
```

## How To Use

### Main Terminal

- Type directly in the terminal area
- Press `Enter` to run the current command
- Press `Tab` to complete commands and paths
- Press `Ctrl+C` to interrupt a running command

### Tabs And Splits

- `+ New Tab`: create a new terminal tab
- `Close Tab`: close the current tab
- `Split H`: split the active terminal horizontally
- `Split V`: split the active terminal vertically

### Quick Command Window

- Click the `Quick Command` button in the top-right corner
- Create `Group`
- Create `Item` under a group
- Add one or more PowerShell commands under an item
- Use:
  - `Copy` to copy a command
  - `Run` to send one command to the active terminal
  - `Run All` to send all commands in order

## Data Format

The app stores data in `data.json` using this structure:

```json
{
  "groups": [
    {
      "id": "group-id",
      "name": "Group Name",
      "items": [
        {
          "id": "item-id",
          "name": "Item Name",
          "commands": [
            {
              "id": "command-id",
              "command": "Get-ChildItem"
            }
          ]
        }
      ]
    }
  ]
}
```

## Build EXE

Install PyInstaller:

```powershell
pip install pyinstaller
```

Build a single Windows executable:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name QuickCommandTerminal quick_command.py
```

## Notes

- `data.json` is created automatically if it does not exist
- When packaged as `.exe`, the app reads and writes `data.json` next to the executable
