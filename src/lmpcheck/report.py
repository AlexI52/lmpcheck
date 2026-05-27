import json
from pathlib import Path
from rich.console import Console
from .models import Finding

_CONSOLE = Console()

_COLORS = {"error": "red", "warning": "yellow", "info": "blue"}


def render_terminal(findings: list[Finding], script: Path) -> None:
    if not findings:
        _CONSOLE.print(f"[green]OK: No issues found in {script}[/green]")
        return

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")

    _CONSOLE.print(f"\n[bold]lmpcheck[/bold] — {script}")
    _CONSOLE.print(f"  {errors} error(s), {warnings} warning(s), {infos} info(s)\n")

    for f in findings:
        color = _COLORS.get(f.severity, "white")
        loc = f"{f.file}:{f.line}" if f.line else str(f.file)
        _CONSOLE.print(f"[{color}][{f.severity.upper()}][/{color}] [{color}]{f.category}[/{color}]  {loc}")
        _CONSOLE.print(f"  {f.message}")
        if f.suggestion:
            _CONSOLE.print(f"  [dim]> {f.suggestion}[/dim]")
        _CONSOLE.print()


def render_json(findings: list[Finding]) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2)
