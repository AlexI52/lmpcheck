import re
from pathlib import Path
from .models import Command, Variable, ParseResult

_VAR_DEF = re.compile(r"^\s*variable\s+", re.IGNORECASE)


def parse(script_path: Path, _depth: int = 0) -> ParseResult:
    commands: list[Command] = []
    variables: dict[str, Variable] = {}
    all_variables: list[Variable] = []

    raw_lines = script_path.read_text(encoding="utf-8", errors="replace").splitlines()
    logical_lines: list[tuple[int, str]] = []  # (original_line_number, merged_text)

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        start_line = i + 1  # 1-based
        # Merge continuations
        while line.rstrip().endswith("&"):
            line = line.rstrip()[:-1]
            i += 1
            if i < len(raw_lines):
                line = line + " " + raw_lines[i].lstrip()
        logical_lines.append((start_line, line))
        i += 1

    for lineno, text in logical_lines:
        # Strip inline comment (# not inside ${ })
        text = _strip_comment(text)
        text = text.strip()
        if not text:
            continue

        tokens = text.split()
        name = tokens[0].lower()
        args = tokens[1:]
        cmd = Command(name=name, args=args, raw=text, line=lineno, file=script_path)
        commands.append(cmd)

        if name == "variable" and len(args) >= 2:
            var_name = args[0]
            style = args[1]
            value = " ".join(args[2:]) if len(args) > 2 else ""
            v = Variable(name=var_name, style=style, value=value, line=lineno, file=script_path)
            variables[var_name] = v
            all_variables.append(v)

        if name == "include" and args and _depth < 2:
            inc_path = script_path.parent / args[0]
            if inc_path.exists():
                sub = parse(inc_path, _depth=_depth + 1)
                commands.extend(sub.commands)
                for vname, var in sub.variables.items():
                    variables[vname] = var
                all_variables.extend(sub.all_variables)

    return ParseResult(commands=commands, variables=variables, all_variables=all_variables)


def _strip_comment(line: str) -> str:
    # Remove # and everything after, but skip # inside ${}
    result = []
    i = 0
    while i < len(line):
        if line[i] == "$" and i + 1 < len(line) and line[i + 1] == "{":
            # scan to closing }
            j = line.index("}", i + 2) if "}" in line[i + 2:] else len(line) - 1
            result.append(line[i : j + 1])
            i = j + 1
        elif line[i] == "#":
            break
        else:
            result.append(line[i])
            i += 1
    return "".join(result)
