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
