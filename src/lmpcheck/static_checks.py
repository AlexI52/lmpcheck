import re
from pathlib import Path
from typing import Optional
from .models import Command, Finding, ParseResult

_VAR_REF = re.compile(r"\$\{(\w+)\}|(?<!\w)v_(\w+)")


def _find_var_refs(text: str) -> list[str]:
    return [m.group(1) or m.group(2) for m in _VAR_REF.finditer(text)]


def check_undefined_variables(result: ParseResult) -> list[Finding]:
    findings: list[Finding] = []
    defined: set[str] = set()
    for cmd in result.commands:
        if cmd.name == "variable" and cmd.args:
            defined.add(cmd.args[0])
        else:
            for ref in _find_var_refs(cmd.raw):
                if ref not in defined:
                    suggestion = None
                    close = _closest(ref, defined)
                    if close:
                        suggestion = f"Did you mean ${{{close}}}?"
                    findings.append(Finding(
                        severity="error",
                        category="undefined_variable",
                        file=cmd.file,
                        line=cmd.line,
                        message=f"Undefined variable: ${{{ref}}}",
                        suggestion=suggestion,
                    ))
    return findings


def _closest(name: str, candidates: set[str]) -> Optional[str]:
    if not candidates:
        return None
    return min(candidates, key=lambda c: _edit_distance(name.lower(), c.lower()))


def _edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        ndp = [i + 1]
        for j, cb in enumerate(b):
            ndp.append(min(dp[j] + (ca != cb), dp[j + 1] + 1, ndp[j] + 1))
        dp = ndp
    return dp[-1]


_INT_ROUNDING = re.compile(r"\b(floor|ceil|round)\b")


def check_non_integer_steps(result: ParseResult) -> list[Finding]:
    # Collect variables defined as equal with division but no floor/ceil/round
    div_vars: dict[str, Command] = {}
    for cmd in result.commands:
        if cmd.name == "variable" and len(cmd.args) >= 3 and cmd.args[1] == "equal":
            expr = " ".join(cmd.args[2:])
            if "/" in expr and not _INT_ROUNDING.search(expr):
                div_vars[cmd.args[0]] = cmd

    findings: list[Finding] = []
    for cmd in result.commands:
        if cmd.name == "run":
            for ref in _find_var_refs(cmd.raw):
                if ref in div_vars:
                    src = div_vars[ref]
                    expr = " ".join(src.args[2:])
                    findings.append(Finding(
                        severity="warning",
                        category="non_integer_steps",
                        file=cmd.file,
                        line=cmd.line,
                        message=f"`${{{ref}}}` may be non-integer: defined as `{expr}` (line {src.line}) without floor()",
                        suggestion=f"variable {ref} equal floor({expr})",
                    ))
    return findings


_OUTPUT_NAMES = {"log", "write_restart", "write_data"}
_VAR_IN_FILENAME = re.compile(r"\$\{(\w+)\}")
_NUMERIC_LITERAL = re.compile(r"\d+")


def _collect_outputs(commands: list[Command]) -> list[tuple[Command, str]]:
    """Return (command, filename_token) for every output-producing command."""
    out: list[tuple[Command, str]] = []
    for cmd in commands:
        if cmd.name in _OUTPUT_NAMES and cmd.args:
            out.append((cmd, cmd.args[0]))
        elif cmd.name == "dump" and len(cmd.args) >= 5:
            out.append((cmd, cmd.args[4]))
        elif cmd.name == "fix":
            try:
                idx = cmd.args.index("file")
                if idx + 1 < len(cmd.args):
                    out.append((cmd, cmd.args[idx + 1]))
            except ValueError:
                pass
    return out


def check_hardcoded_filenames(result: ParseResult) -> list[Finding]:
    outputs = _collect_outputs(result.commands)
    if not outputs:
        return []

    # Count variable references in output filenames
    var_counts: dict[str, int] = {}
    for _, fname in outputs:
        for var in _VAR_IN_FILENAME.findall(fname):
            var_counts[var] = var_counts.get(var, 0) + 1

    if not var_counts:
        return []

    # The most-used variable in output filenames is the "run variable"
    run_var = max(var_counts, key=lambda v: var_counts[v])
    if var_counts[run_var] < max(2, len(outputs) * 0.4):
        return []  # not consistent enough to apply heuristic

    run_var_value = result.variables.get(run_var)
    run_val = run_var_value.value if run_var_value else None

    findings: list[Finding] = []
    for cmd, fname in outputs:
        if f"${{{run_var}}}" in fname:
            continue  # uses the run variable — OK
        # Warn if the filename contains a numeric literal matching the run variable's value
        literals = _NUMERIC_LITERAL.findall(fname)
        if literals and run_val and run_val.strip() in literals:
            findings.append(Finding(
                severity="warning",
                category="hardcoded_filename",
                file=cmd.file,
                line=cmd.line,
                message=f"Output filename `{fname}` hardcodes `{run_val}` instead of `${{{run_var}}}`",
                suggestion=f"Replace `{run_val}` with `${{{run_var}}}` to avoid silent overwrites on re-runs",
            ))
        elif literals and not run_val:
            findings.append(Finding(
                severity="warning",
                category="hardcoded_filename",
                file=cmd.file,
                line=cmd.line,
                message=f"Output filename `{fname}` appears hardcoded while other outputs use `${{{run_var}}}`",
                suggestion=f"Consider using `${{{run_var}}}` as the run prefix",
            ))
    return findings


_FILE_COMMANDS = {"read_data", "read_restart", "include"}


def _expand_string_vars(text: str, variables: dict) -> str:
    def replace(m: re.Match) -> str:
        name = m.group(1)
        v = variables.get(name)
        if v and v.style == "string":
            return v.value
        return m.group(0)
    return re.sub(r"\$\{(\w+)\}", replace, text)


def check_missing_files(result: ParseResult, script_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for cmd in result.commands:
        if cmd.name in _FILE_COMMANDS and cmd.args:
            raw_fname = cmd.args[0]
            fname = _expand_string_vars(raw_fname, result.variables)
            if "$" in fname:
                # Still has unexpanded vars — skip (can't resolve)
                continue
            path = script_dir / fname
            if not path.exists():
                findings.append(Finding(
                    severity="error",
                    category="missing_file",
                    file=cmd.file,
                    line=cmd.line,
                    message=f"`{cmd.name}` references missing file: {fname}",
                    suggestion=f"Expected at: {path.resolve()}",
                ))
    return findings
