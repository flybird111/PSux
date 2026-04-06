from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from session import SessionState
from translator.models import CommandPlan
from translator.parser import CommandParser
from utils.errors import UserFacingError
from utils.path_utils import resolve_user_path
from utils.text import expand_env_tokens, quote_powershell


_POWERSHELL_COMMAND_CACHE: list[str] | None = None
_PATH_COMMAND_CACHE: dict[tuple[str, str], list[str]] = {}


class CommandTranslator:
    def __init__(self) -> None:
        self._parser = CommandParser()
        self._special_handlers = {
            "cd": self._translate_cd,
            "clear": self._translate_clear,
            "export": self._translate_export,
            "history": self._translate_history,
            "Set-Location": self._translate_set_location,
            "sl": self._translate_set_location,
        }
        self._linux_handlers = {
            "ls": self._translate_ls,
            "pwd": self._translate_pwd,
            "mkdir": self._translate_mkdir,
            "rm": self._translate_rm,
            "cp": self._translate_cp,
            "mv": self._translate_mv,
            "cat": self._translate_cat,
            "touch": self._translate_touch,
            "grep": self._translate_grep,
            "find": self._translate_find,
            "ln": self._translate_ln,
            "echo": self._translate_echo,
            "which": self._translate_which,
            "head": self._translate_head,
            "tail": self._translate_tail,
            "less": self._translate_less,
            "wc": self._translate_wc,
            "sort": self._translate_sort,
            "uniq": self._translate_uniq,
            "tree": self._translate_tree,
            "basename": self._translate_basename,
            "dirname": self._translate_dirname,
            "realpath": self._translate_realpath,
            "ps": self._translate_ps,
            "kill": self._translate_kill,
            "open": self._translate_open,
            "env": self._translate_env,
            "vim": self._translate_vim,
        }

    def available_commands(self, session: SessionState | None = None) -> list[str]:
        commands = set(self._special_handlers) | set(self._linux_handlers) | {"git"}
        commands.update(self._powershell_command_names())
        if session is not None:
            commands.update(self._path_command_names(session))
        return sorted(commands, key=str.lower)

    def _powershell_command_names(self) -> list[str]:
        global _POWERSHELL_COMMAND_CACHE

        if _POWERSHELL_COMMAND_CACHE is not None:
            return _POWERSHELL_COMMAND_CACHE

        fallback = [
            "Compare-Object",
            "diff",
            "Get-ChildItem",
            "Get-Command",
            "Get-Location",
            "Get-Process",
            "New-Item",
            "Remove-Item",
            "Select-String",
            "Set-Location",
            "Test-Path",
        ]

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Command | Select-Object -ExpandProperty Name",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
            )
        except OSError:
            _POWERSHELL_COMMAND_CACHE = fallback
            return _POWERSHELL_COMMAND_CACHE

        command_names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        _POWERSHELL_COMMAND_CACHE = sorted(set(command_names) | set(fallback), key=str.lower)
        return _POWERSHELL_COMMAND_CACHE

    def _path_command_names(self, session: SessionState) -> list[str]:
        effective_env = session.get_effective_env()
        path_value = effective_env.get("PATH", os.environ.get("PATH", ""))
        pathext_value = effective_env.get("PATHEXT", os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"))
        cache_key = (path_value, pathext_value)
        cached = _PATH_COMMAND_CACHE.get(cache_key)
        if cached is not None:
            return cached

        extensions = {item.lower() for item in pathext_value.split(";") if item}
        names: set[str] = set()
        for raw_dir in path_value.split(os.pathsep):
            if not raw_dir:
                continue
            directory = Path(raw_dir)
            if not directory.is_dir():
                continue
            try:
                for entry in directory.iterdir():
                    if not entry.is_file():
                        continue
                    suffix = entry.suffix.lower()
                    if suffix and suffix in extensions:
                        names.add(entry.stem)
                        names.add(entry.name)
            except OSError:
                continue

        _PATH_COMMAND_CACHE[cache_key] = sorted(names, key=str.lower)
        return _PATH_COMMAND_CACHE[cache_key]

    def translate(self, command_line: str, session: SessionState) -> CommandPlan | None:
        stripped = command_line.strip()
        if not stripped:
            return None

        try:
            tokens = self._parser.parse(stripped)
        except UserFacingError:
            return self._plan_powershell(stripped, stripped, support_level="fallback_supported")
        if not tokens:
            return None

        if self._contains_unsupported_shell_operators(tokens):
            raise UserFacingError("Redirects and chained shell syntax are not supported yet. Only simple pipelines with | are currently supported.")

        if "|" in tokens:
            return self._translate_pipeline(tokens, stripped, session)

        return self._translate_single_command(tokens, stripped, session)

    def _translate_single_command(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        command = tokens[0]

        if command in self._special_handlers:
            return self._special_handlers[command](tokens, display, session)

        if command in self._linux_handlers:
            return self._linux_handlers[command](tokens, display, session)

        if command == "git":
            return self._translate_git(tokens, display, session)

        if command.startswith("./"):
            return self._translate_local_executable(tokens, display, session)

        return self._plan_powershell(display, display, support_level="fallback_supported")

    def _contains_unsupported_shell_operators(self, tokens: list[str]) -> bool:
        return any(token in {">", ">>", "<", "&&", "||", ";"} for token in tokens)

    def _translate_pipeline(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        segments: list[list[str]] = []
        current: list[str] = []

        for token in tokens:
            if token == "|":
                if not current:
                    raise UserFacingError("Invalid pipeline syntax near '|'.")
                segments.append(current)
                current = []
                continue
            current.append(token)

        if not current:
            raise UserFacingError("Invalid pipeline syntax near '|'.")
        segments.append(current)

        notes: list[str] = []
        support_level = "fully_supported"
        stage_scripts: list[str] = []

        for segment in segments:
            segment_display = " ".join(segment)
            plan = self._translate_single_command(segment, segment_display, session)
            if plan.kind == "internal":
                raise UserFacingError("Pipelines are not supported with PSux internal commands like cd, export, clear, or history.")
            stage_scripts.append(self._pipeline_stage_script(plan))
            if plan.compatibility_note:
                notes.append(plan.compatibility_note)
            support_level = self._merge_support_level(support_level, plan.support_level)

        script = " | ".join(stage_scripts)
        compatibility_note = "\n".join(dict.fromkeys(notes)) if notes else None
        return self._plan_powershell(
            display,
            script,
            support_level=support_level,
            compatibility_note=compatibility_note,
        )

    def _pipeline_stage_script(self, plan: CommandPlan) -> str:
        if plan.kind == "powershell":
            return f"& {{ {plan.powershell_script or ''} }}"
        if plan.kind == "native":
            arguments = ", ".join(quote_powershell(argument) for argument in plan.arguments)
            return f"& {quote_powershell(plan.executable or '')} @({arguments})"
        if plan.kind == "batch":
            arguments = ", ".join(quote_powershell(argument) for argument in [plan.executable or "", *plan.arguments])
            return f"& 'cmd.exe' @('/c', {arguments})"
        raise UserFacingError(f"Unsupported command kind in pipeline: {plan.kind}")

    def _merge_support_level(self, current: str, new: str) -> str:
        order = {
            "fully_supported": 0,
            "partially_supported": 1,
            "fallback_supported": 2,
        }
        return new if order.get(new, 99) > order.get(current, 99) else current

    def _plan_powershell(
        self,
        display_command: str,
        script: str,
        support_level: str = "fully_supported",
        compatibility_note: str | None = None,
    ) -> CommandPlan:
        return CommandPlan(
            kind="powershell",
            display_command=display_command,
            powershell_script=script,
            support_level=support_level,
            compatibility_note=compatibility_note,
        )

    def _plan_internal(
        self,
        display_command: str,
        action: str,
        payload: dict | None = None,
        support_level: str = "fully_supported",
        compatibility_note: str | None = None,
    ) -> CommandPlan:
        return CommandPlan(
            kind="internal",
            display_command=display_command,
            internal_action=action,
            payload=payload or {},
            support_level=support_level,
            compatibility_note=compatibility_note,
        )

    def _plan_native(
        self,
        display_command: str,
        executable: str,
        arguments: list[str] | None = None,
        support_level: str = "fully_supported",
        compatibility_note: str | None = None,
    ) -> CommandPlan:
        return CommandPlan(
            kind="native",
            display_command=display_command,
            executable=executable,
            arguments=arguments or [],
            support_level=support_level,
            compatibility_note=compatibility_note,
        )

    def _plan_batch(
        self,
        display_command: str,
        executable: str,
        arguments: list[str] | None = None,
        support_level: str = "fully_supported",
        compatibility_note: str | None = None,
    ) -> CommandPlan:
        return CommandPlan(
            kind="batch",
            display_command=display_command,
            executable=executable,
            arguments=arguments or [],
            support_level=support_level,
            compatibility_note=compatibility_note,
        )

    def _command_on_path(self, command: str, session: SessionState) -> str | None:
        return shutil.which(command, path=session.get_effective_env().get("PATH"))

    def _quote_array(self, values: list[str]) -> str:
        return ", ".join(quote_powershell(value) for value in values)

    def _parse_combined_short_flags(self, command: str, args: list[str], allowed: set[str]) -> tuple[set[str], list[str]]:
        flags: set[str] = set()
        remaining: list[str] = []
        parse_flags = True

        for token in args:
            if parse_flags and token == "--":
                parse_flags = False
                continue
            if parse_flags and token.startswith("-") and token != "-" and len(token) > 1:
                for flag in token[1:]:
                    if flag not in allowed:
                        raise UserFacingError(f"{command}: unsupported option: -{flag}")
                    flags.add(flag)
                continue
            remaining.append(token)
        return flags, remaining

    def _parse_positive_int(self, command: str, raw: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise UserFacingError(f"{command}: expected an integer, got: {raw}") from exc
        if value < 0:
            raise UserFacingError(f"{command}: expected a non-negative integer, got: {raw}")
        return value

    def _parse_count_option(self, command: str, args: list[str], default: int = 10) -> tuple[int, list[str]]:
        count = default
        remaining: list[str] = []
        index = 0

        while index < len(args):
            token = args[index]
            if token == "--":
                remaining.extend(args[index + 1 :])
                break
            if token == "-n":
                index += 1
                if index >= len(args):
                    raise UserFacingError(f"{command}: missing value for -n.")
                count = self._parse_positive_int(command, args[index])
                index += 1
                continue
            if token.startswith("-n") and len(token) > 2:
                count = self._parse_positive_int(command, token[2:])
                index += 1
                continue
            if re.fullmatch(r"-\d+", token):
                count = self._parse_positive_int(command, token[1:])
                index += 1
                continue
            remaining.append(token)
            index += 1

        return count, remaining

    def _translate_ls(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, paths = self._parse_combined_short_flags("ls", tokens[1:], {"a", "l"})
        target_expr = self._quote_array(paths or ["."])
        force_flag = " -Force" if "a" in flags else ""
        script = f"Get-ChildItem -LiteralPath @({target_expr}){force_flag}"
        return self._plan_powershell(display, script)

    def _translate_pwd(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 1:
            raise UserFacingError("pwd: this command does not accept arguments.")
        return self._plan_powershell(display, "(Get-Location).Path")

    def _translate_cd(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        target = tokens[1] if len(tokens) > 1 else "~"
        if len(tokens) > 2:
            raise UserFacingError("cd: too many arguments.")
        return self._plan_internal(display, "cd", {"path": target})

    def _translate_set_location(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        remaining = tokens[1:]
        if not remaining:
            target = "~"
        elif len(remaining) == 1:
            target = remaining[0]
        elif len(remaining) == 2 and remaining[0] in {"-Path", "-LiteralPath"}:
            target = remaining[1]
        else:
            raise UserFacingError("Set-Location: expected a path or Set-Location -Path <path>.")
        return self._plan_internal(display, "cd", {"path": target})

    def _translate_mkdir(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) < 2:
            raise UserFacingError("mkdir: missing operand.")
        paths = ", ".join(quote_powershell(path) for path in tokens[1:])
        script = f"New-Item -ItemType Directory -Path @({paths}) -Force | Out-Null"
        return self._plan_powershell(display, script)

    def _translate_rm(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, targets = self._parse_combined_short_flags("rm", tokens[1:], {"r", "R", "f"})
        if not targets:
            raise UserFacingError("rm: missing operand.")

        ps_flags: list[str] = []
        if "r" in flags or "R" in flags:
            ps_flags.append("-Recurse")
        if "f" in flags:
            ps_flags.append("-Force")
        flag_text = " " + " ".join(ps_flags) if ps_flags else ""
        paths = self._quote_array(targets)
        script = f"Remove-Item -LiteralPath @({paths}){flag_text}"
        return self._plan_powershell(display, script)

    def _translate_cp(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 3:
            raise UserFacingError("cp: expected source and destination.")
        script = (
            f"Copy-Item -LiteralPath {quote_powershell(tokens[1])} "
            f"-Destination {quote_powershell(tokens[2])}"
        )
        return self._plan_powershell(display, script)

    def _translate_mv(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 3:
            raise UserFacingError("mv: expected source and destination.")
        script = (
            f"Move-Item -LiteralPath {quote_powershell(tokens[1])} "
            f"-Destination {quote_powershell(tokens[2])}"
        )
        return self._plan_powershell(display, script)

    def _translate_cat(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) < 2:
            raise UserFacingError("cat: missing file operand.")
        paths = ", ".join(quote_powershell(path) for path in tokens[1:])
        script = f"Get-Content -LiteralPath @({paths})"
        return self._plan_powershell(display, script)

    def _translate_touch(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) < 2:
            raise UserFacingError("touch: missing file operand.")

        items = ", ".join(quote_powershell(path) for path in tokens[1:])
        script = f"""
$paths = @({items})
foreach ($path in $paths) {{
    if (Test-Path -LiteralPath $path) {{
        (Get-Item -LiteralPath $path).LastWriteTime = Get-Date
    }}
    else {{
        New-Item -ItemType File -Path $path | Out-Null
    }}
}}
""".strip()
        return self._plan_powershell(display, script)

    def _translate_grep(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, remaining = self._parse_combined_short_flags("grep", tokens[1:], {"r", "n", "i"})
        if not remaining:
            raise UserFacingError("grep: expected a pattern.")

        pattern = remaining[0]
        targets = remaining[1:]
        recursive = "r" in flags
        line_numbers = "n" in flags
        ignore_case = "i" in flags

        if recursive and not targets:
            targets = ["."]
        stdin_mode = not recursive and not targets

        formatter = (
            "\"{0}:{1}:{2}\" -f $_.Path, $_.LineNumber, $_.Line.TrimEnd()"
            if line_numbers
            else "\"{0}:{1}\" -f $_.Path, $_.Line.TrimEnd()"
        )
        empty_formatter = (
            "\"{0}:{1}:{2}\" -f $file, $lineNumber, $line.TrimEnd()"
            if line_numbers
            else "\"{0}:{1}\" -f $file, $line.TrimEnd()"
        )
        case_sensitive_flag = "" if ignore_case else "$params.CaseSensitive = $true"
        recursive_literal = "$true" if recursive else "$false"
        stdin_formatter = (
            "\"{0}:{1}\" -f $lineNumber, $line.TrimEnd()"
            if line_numbers
            else "$line.TrimEnd()"
        )
        if stdin_mode:
            script = f"""
$pattern = {quote_powershell(pattern)}
$lineNumber = 0
foreach ($line in $input) {{
    $lineNumber += 1
    if ($pattern.Length -eq 0) {{
        {stdin_formatter}
        continue
    }}
    $params = @{{
        Pattern = $pattern
        InputObject = [string]$line
    }}
    {case_sensitive_flag}
    if (Select-String @params) {{
        {stdin_formatter}
    }}
}}
""".strip()
            return self._plan_powershell(display, script)

        script = f"""
$pattern = {quote_powershell(pattern)}
$targets = @({self._quote_array(targets)})
$recursive = {recursive_literal}
$files = New-Object System.Collections.Generic.List[string]
foreach ($target in $targets) {{
    if (-not (Test-Path -LiteralPath $target)) {{
        throw "grep: path not found: $target"
    }}

    $item = Get-Item -LiteralPath $target -ErrorAction Stop
    if ($item.PSIsContainer) {{
        if (-not $recursive) {{
            throw ("grep: {0}: Is a directory" -f $target)
        }}
        Get-ChildItem -LiteralPath $target -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {{
            [void]$files.Add($_.FullName)
        }}
    }}
    else {{
        [void]$files.Add($item.FullName)
    }}
}}

if ($files.Count -eq 0) {{
    exit 0
}}

if ($pattern.Length -eq 0) {{
    foreach ($file in $files) {{
        $lineNumber = 0
        foreach ($line in Get-Content -LiteralPath $file -ErrorAction Stop) {{
            $lineNumber += 1
            {empty_formatter}
        }}
    }}
    exit 0
}}

$params = @{{
    Pattern = $pattern
    LiteralPath = $files
}}
{case_sensitive_flag}
Select-String @params | ForEach-Object {{ {formatter} }}
""".strip()
        return self._plan_powershell(display, script)

    def _translate_find(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        args = tokens[1:]
        start_path = "."
        pattern: str | None = None
        ignore_case = False
        type_filter: str | None = None
        index = 0

        while index < len(args):
            token = args[index]
            if token in {"-name", "-iname"}:
                index += 1
                if index >= len(args):
                    raise UserFacingError(f"find: missing pattern for {token}.")
                pattern = args[index]
                ignore_case = token == "-iname"
                index += 1
                continue
            if token == "-type":
                index += 1
                if index >= len(args):
                    raise UserFacingError("find: missing value for -type.")
                if args[index] not in {"f", "d"}:
                    raise UserFacingError("find: only -type f and -type d are supported.")
                type_filter = args[index]
                index += 1
                continue
            if token.startswith("-"):
                raise UserFacingError(f"find: unsupported option: {token}")
            if start_path != ".":
                raise UserFacingError("find: only one search root path is supported.")
            start_path = token
            index += 1

        if pattern is None:
            raise UserFacingError('find: expected -name <pattern> or -iname <pattern>.')

        wildcard_options = "[System.Management.Automation.WildcardOptions]::IgnoreCase" if ignore_case else "[System.Management.Automation.WildcardOptions]::None"
        type_condition = "$true"
        if type_filter == "f":
            type_condition = "-not $_.PSIsContainer"
        elif type_filter == "d":
            type_condition = "$_.PSIsContainer"

        script = f"""
$start = {quote_powershell(start_path)}
$pattern = {quote_powershell(pattern)}
if (-not (Test-Path -LiteralPath $start)) {{
    throw "find: path not found: $start"
}}
$matcher = New-Object System.Management.Automation.WildcardPattern($pattern, {wildcard_options})
$root = Get-Item -LiteralPath $start -ErrorAction Stop
if ({type_condition.replace('$_', '$root')} -and $matcher.IsMatch($root.Name)) {{
    $root.FullName
}}
if ($root.PSIsContainer) {{
    Get-ChildItem -LiteralPath $start -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {{ {type_condition} -and $matcher.IsMatch($_.Name) }} |
        ForEach-Object {{ $_.FullName }}
}}
exit 0
""".strip()
        return self._plan_powershell(display, script)

    def _translate_ln(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        symbolic = False
        remaining = tokens[1:]
        if remaining and remaining[0] == "-s":
            symbolic = True
            remaining = remaining[1:]

        if len(remaining) != 2:
            raise UserFacingError("ln: expected target and link name.")

        if symbolic:
            script = f"""
try {{
    New-Item -ItemType SymbolicLink -Path {quote_powershell(remaining[1])} -Target {quote_powershell(remaining[0])} | Out-Null
}}
catch {{
    Write-Error ("ln -s: failed to create symbolic link. On Windows this may require Developer Mode or elevated privileges. " + $_.Exception.Message)
    exit 1
}}
""".strip()
            return self._plan_powershell(
                display,
                script,
                support_level="partially_supported",
                compatibility_note="ln -s uses native Windows symbolic links and may require Developer Mode or elevated privileges.",
            )

        script = (
            f"New-Item -ItemType HardLink -Path {quote_powershell(remaining[1])} "
            f"-Target {quote_powershell(remaining[0])} | Out-Null"
        )
        return self._plan_powershell(display, script)

    def _translate_echo(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        effective_env = session.get_effective_env()
        expanded = [expand_env_tokens(token, effective_env) for token in tokens[1:]]
        content = " ".join(expanded)
        return self._plan_powershell(display, f"Write-Output {quote_powershell(content)}")

    def _translate_clear(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 1:
            raise UserFacingError("clear: this command does not accept arguments.")
        return self._plan_internal(display, "clear")

    def _translate_which(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 2:
            raise UserFacingError("which: expected a single command name.")
        script = f"""
$command = Get-Command -Name {quote_powershell(tokens[1])} -ErrorAction Stop | Select-Object -First 1
if ($command.Path) {{
    $command.Path
}}
elseif ($command.Definition) {{
    $command.Definition
}}
else {{
    $command.Source
}}
""".strip()
        return self._plan_powershell(display, script)

    def _translate_export(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 2 or "=" not in tokens[1]:
            raise UserFacingError("export: expected NAME=value.")
        name, value = tokens[1].split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise UserFacingError(f"export: invalid variable name: {name}")
        return self._plan_internal(display, "export", {"name": name, "value": value})

    def _translate_git(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        executable = self._command_on_path("git", session)
        if not executable:
            raise UserFacingError("git is not installed or not available in PATH for this pane session.")
        return self._plan_native(
            display,
            executable,
            tokens[1:],
            support_level="fallback_supported",
            compatibility_note="git is passed through directly to the system Git executable in the current pane session.",
        )

    def _translate_head(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        count, paths = self._parse_count_option("head", tokens[1:])
        if not paths:
            raise UserFacingError("head: expected at least one file.")
        script = f"Get-Content -LiteralPath @({self._quote_array(paths)}) -TotalCount {count}"
        return self._plan_powershell(display, script)

    def _translate_tail(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        count, paths = self._parse_count_option("tail", tokens[1:])
        if not paths:
            raise UserFacingError("tail: expected at least one file.")
        script = f"Get-Content -LiteralPath @({self._quote_array(paths)}) -Tail {count}"
        return self._plan_powershell(display, script)

    def _translate_less(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        targets = tokens[1:]
        if not targets:
            raise UserFacingError("less: expected at least one file.")
        script = f"""
foreach ($target in @({self._quote_array(targets)})) {{
    Start-Process -FilePath 'notepad.exe' -ArgumentList @($target)
}}
""".strip()
        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="less compatibility mode opens the target in Notepad instead of a real interactive pager.",
        )

    def _translate_wc(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, paths = self._parse_combined_short_flags("wc", tokens[1:], {"l", "w", "c"})
        if not paths:
            raise UserFacingError("wc: expected at least one file.")

        show_lines = "l" in flags or not flags
        show_words = "w" in flags or not flags
        show_bytes = "c" in flags or not flags
        script = f"""
$showLines = {'$true' if show_lines else '$false'}
$showWords = {'$true' if show_words else '$false'}
$showBytes = {'$true' if show_bytes else '$false'}
$totals = [ordered]@{{ Lines = 0; Words = 0; Bytes = 0 }}
$paths = @({self._quote_array(paths)})
foreach ($path in $paths) {{
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {{
        throw "wc: file not found: $path"
    }}
    $item = Get-Item -LiteralPath $path -ErrorAction Stop
    $content = Get-Content -LiteralPath $path -Raw -ErrorAction Stop
    $lineCount = (Get-Content -LiteralPath $path | Measure-Object -Line).Lines
    $wordCount = if ([string]::IsNullOrEmpty($content)) {{ 0 }} else {{ ([regex]::Matches($content, '\\S+')).Count }}
    $byteCount = $item.Length
    $totals.Lines += $lineCount
    $totals.Words += $wordCount
    $totals.Bytes += $byteCount
    $parts = New-Object System.Collections.Generic.List[string]
    if ($showLines) {{ [void]$parts.Add([string]$lineCount) }}
    if ($showWords) {{ [void]$parts.Add([string]$wordCount) }}
    if ($showBytes) {{ [void]$parts.Add([string]$byteCount) }}
    [void]$parts.Add($item.FullName)
    $parts -join ' '
}}
if ($paths.Count -gt 1) {{
    $parts = New-Object System.Collections.Generic.List[string]
    if ($showLines) {{ [void]$parts.Add([string]$totals.Lines) }}
    if ($showWords) {{ [void]$parts.Add([string]$totals.Words) }}
    if ($showBytes) {{ [void]$parts.Add([string]$totals.Bytes) }}
    [void]$parts.Add('total')
    $parts -join ' '
}}
""".strip()
        return self._plan_powershell(display, script)

    def _translate_sort(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, paths = self._parse_combined_short_flags("sort", tokens[1:], {"r", "u"})
        if not paths:
            raise UserFacingError("sort: expected at least one file.")
        script = f"""
$reverse = {'$true' if 'r' in flags else '$false'}
$unique = {'$true' if 'u' in flags else '$false'}
$lines = foreach ($path in @({self._quote_array(paths)})) {{
    Get-Content -LiteralPath $path -ErrorAction Stop
}}
$sorted = @($lines | Sort-Object)
if ($unique) {{
    $sorted = @($sorted | Select-Object -Unique)
}}
if ($reverse) {{
    [array]::Reverse($sorted)
}}
$sorted
""".strip()
        return self._plan_powershell(display, script)

    def _translate_uniq(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, paths = self._parse_combined_short_flags("uniq", tokens[1:], {"c"})
        if not paths:
            raise UserFacingError("uniq: expected at least one file.")
        script = f"""
$showCount = {'$true' if 'c' in flags else '$false'}
foreach ($path in @({self._quote_array(paths)})) {{
    $previous = $null
    $count = 0
    foreach ($line in Get-Content -LiteralPath $path -ErrorAction Stop) {{
        if ($count -eq 0) {{
            $previous = $line
            $count = 1
            continue
        }}
        if ($line -ceq $previous) {{
            $count += 1
            continue
        }}
        if ($showCount) {{
            "{0} {1}" -f $count, $previous
        }}
        else {{
            $previous
        }}
        $previous = $line
        $count = 1
    }}
    if ($count -gt 0) {{
        if ($showCount) {{
            "{0} {1}" -f $count, $previous
        }}
        else {{
            $previous
        }}
    }}
}}
""".strip()
        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="uniq currently supports file input and optional -c counting, without stdin pipe mode yet.",
        )

    def _translate_tree(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        flags, remaining = self._parse_combined_short_flags("tree", tokens[1:], {"d"})
        tree_executable = self._command_on_path("tree.com", session) or self._command_on_path("tree", session)
        path = remaining[0] if remaining else "."

        if tree_executable:
            args = [path]
            if "d" not in flags:
                args.append("/F")
            args.append("/A")
            return self._plan_native(
                display,
                tree_executable,
                args,
                support_level="partially_supported",
                compatibility_note="tree uses the native Windows tree command for a terminal-style directory view.",
            )

        script = f"""
Get-ChildItem -LiteralPath {quote_powershell(path)} -Recurse -Force -ErrorAction Stop |
    ForEach-Object {{ $_.FullName }}
""".strip()
        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="tree fell back to a recursive path listing because the native tree command was not found.",
        )

    def _translate_history(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 1:
            raise UserFacingError("history: this command does not accept arguments.")
        lines = [f"{index + 1:>4}  {item}" for index, item in enumerate(session.history.items)]
        text = "\n".join(lines) if lines else "history: no commands yet."
        return self._plan_internal(display, "history", {"text": text})

    def _translate_basename(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) not in {2, 3}:
            raise UserFacingError("basename: expected PATH [SUFFIX].")
        suffix_script = ""
        if len(tokens) == 3:
            suffix_script = f"""
$suffix = {quote_powershell(tokens[2])}
if ($leaf.EndsWith($suffix)) {{
    $leaf = $leaf.Substring(0, $leaf.Length - $suffix.Length)
}}
""".strip()
        script = f"""
$leaf = Split-Path -Path {quote_powershell(tokens[1])} -Leaf
{suffix_script}
$leaf
""".strip()
        return self._plan_powershell(display, script)

    def _translate_dirname(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 2:
            raise UserFacingError("dirname: expected a single path.")
        script = f"""
$path = {quote_powershell(tokens[1])}
$dir = Split-Path -Path $path -Parent
if ([string]::IsNullOrEmpty($dir)) {{ '.' }} else {{ $dir }}
""".strip()
        return self._plan_powershell(display, script)

    def _translate_realpath(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) < 2:
            raise UserFacingError("realpath: expected at least one path.")
        script = f"Resolve-Path -LiteralPath @({self._quote_array(tokens[1:])}) | ForEach-Object {{ $_.Path }}"
        return self._plan_powershell(display, script)

    def _translate_ps(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        args = tokens[1:]
        table_script = """
param($processes)
$processes |
    Sort-Object Id |
    Select-Object Id, ProcessName, @{Name='CPU';Expression={ if ($_.CPU -ne $null) { [math]::Round($_.CPU, 2) } else { '' } }}, @{Name='WorkingSetMB';Expression={ [math]::Round($_.WS / 1MB, 1) }}, Path |
    Format-Table -AutoSize |
    Out-String -Width 4096
""".strip()

        if not args or args == ["aux"] or args == ["-ef"]:
            script = f"$processes = Get-Process\n& {{ {table_script} }} $processes"
            return self._plan_powershell(
                display,
                script,
                support_level="partially_supported",
                compatibility_note="ps compatibility mode supports ps, ps aux, ps -ef, ps -p PID, and ps NAME on Windows.",
            )

        if len(args) >= 2 and args[0] == "-p":
            ids = [self._parse_positive_int("ps", raw) for raw in args[1].split(",") if raw]
            script = f"$processes = Get-Process -Id @({', '.join(str(item) for item in ids)}) -ErrorAction Stop\n& {{ {table_script} }} $processes"
            return self._plan_powershell(
                display,
                script,
                support_level="partially_supported",
                compatibility_note="ps compatibility mode supports ps, ps aux, ps -ef, ps -p PID, and ps NAME on Windows.",
            )

        if any(arg.startswith("-") for arg in args):
            raise UserFacingError("ps: unsupported option set. Supported forms are ps, ps aux, ps -ef, ps -p PID, and ps NAME.")

        script = f"$processes = Get-Process -Name @({self._quote_array(args)}) -ErrorAction Stop\n& {{ {table_script} }} $processes"
        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="ps compatibility mode supports ps, ps aux, ps -ef, ps -p PID, and ps NAME on Windows.",
        )

    def _translate_kill(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        force = False
        by_name = False
        targets: list[str] = []
        for token in tokens[1:]:
            if token == "-9":
                force = True
                continue
            if token == "-f":
                by_name = True
                continue
            if token.startswith("-"):
                raise UserFacingError(f"kill: unsupported option: {token}")
            targets.append(token)

        if not targets:
            raise UserFacingError("kill: expected a process id or process name.")

        if by_name:
            script = f"Stop-Process -Name @({self._quote_array(targets)}) {'-Force' if force else ''} -ErrorAction Stop".strip()
        else:
            ids = [str(self._parse_positive_int("kill", target)) for target in targets]
            script = f"Stop-Process -Id @({', '.join(ids)}) {'-Force' if force else ''} -ErrorAction Stop".strip()

        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="kill compatibility mode supports kill PID, kill -9 PID, and kill -f NAME on Windows.",
        )

    def _translate_open(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        targets = tokens[1:] or ["."]
        script = f"""
foreach ($target in @({self._quote_array(targets)})) {{
    Start-Process -FilePath $target
}}
""".strip()
        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="open uses Windows Start-Process to launch the default app or folder view for the target.",
        )

    def _translate_env(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        if len(tokens) != 1:
            raise UserFacingError("env: this command does not accept arguments yet.")
        script = """
Get-ChildItem Env: |
    Sort-Object Name |
    ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }
""".strip()
        return self._plan_powershell(display, script)

    def _translate_vim(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        targets = tokens[1:]
        if len(targets) > 1:
            raise UserFacingError("vim: compatibility mode currently supports at most one file.")
        if targets:
            resolved = resolve_user_path(targets[0], session.cwd)
            script = f"""
$target = {quote_powershell(str(resolved))}
if (-not (Test-Path -LiteralPath $target)) {{
    New-Item -ItemType File -Path $target | Out-Null
}}
Start-Process -FilePath 'notepad.exe' -ArgumentList @($target)
""".strip()
        else:
            script = "Start-Process -FilePath 'notepad.exe'"

        return self._plan_powershell(
            display,
            script,
            support_level="partially_supported",
            compatibility_note="vim compatibility mode opens the file in Notepad. It is not a full Vim emulator.",
        )

    def _translate_local_executable(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        raw_path = tokens[0]
        resolved = resolve_user_path(raw_path, session.cwd)
        if not resolved.exists():
            raise UserFacingError(f"Executable not found: {raw_path}")
        suffix = resolved.suffix.lower()
        if suffix not in {".bat", ".exe"}:
            raise UserFacingError("Only ./xxx.exe and ./xxx.bat are supported in this PSux version.")
        if suffix == ".bat":
            return self._plan_batch(
                display,
                str(resolved),
                tokens[1:],
                support_level="fallback_supported",
                compatibility_note="Local .bat files are executed through cmd.exe /c in the current pane working directory.",
            )
        return self._plan_native(
            display,
            str(resolved),
            tokens[1:],
            support_level="fallback_supported",
            compatibility_note="Local .exe files are executed directly in the current pane working directory.",
        )

    def _translate_fallback_executable(self, tokens: list[str], display: str, session: SessionState) -> CommandPlan:
        command = tokens[0]
        executable = self._command_on_path(command, session)

        if executable:
            suffix = Path(executable).suffix.lower()
            if suffix == ".bat":
                return self._plan_batch(
                    display,
                    executable,
                    tokens[1:],
                    support_level="fallback_supported",
                    compatibility_note=f"{command} is being passed through to the system executable found on PATH.",
                )
            return self._plan_native(
                display,
                executable,
                tokens[1:],
                support_level="fallback_supported",
                compatibility_note=f"{command} is being passed through to the system executable found on PATH.",
            )

        raise UserFacingError(f"Unsupported or unknown command: {command}")
