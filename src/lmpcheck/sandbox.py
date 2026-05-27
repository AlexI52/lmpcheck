import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import Finding
from .parser import parse
from .static_checks import _expand_string_vars

_RUN_RE = re.compile(r"^(\s*run\s+)\S+(.*)$", re.IGNORECASE)
_MINIMIZE_RE = re.compile(r"^(\s*minimize\s+)\S+\s+\S+\s+\S+\s+\S+(.*)$", re.IGNORECASE)
_ERROR_RE = re.compile(r"^ERROR(?: on proc \d+)?:\s*(.+?)(?:\s*\(.+\))?$")


def run_sandbox(script: Path, lmp_binary: str = "lmp", timeout: int = 60) -> list[Finding]:
    binary = shutil.which(lmp_binary)
    if not binary:
        return [Finding(
            severity="warning",
            category="sandbox_skipped",
            file=script,
            line=0,
            message=f"lmp binary `{lmp_binary}` not found in PATH; skipping sandbox stage",
            suggestion="Install LAMMPS locally or use --lmp-binary to specify the path, or --no-sandbox to suppress this warning",
        )]

    result = parse(script)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        rewritten = _rewrite_script(script, tmp)

        # Copy referenced data files into tmpdir
        for cmd in result.commands:
            if cmd.name == "read_data" and cmd.args:
                fname = _expand_string_vars(cmd.args[0], result.variables)
                if "$" not in fname:
                    src = script.parent / fname
                    if src.exists():
                        shutil.copy2(src, tmp / fname)

        try:
            proc = subprocess.run(
                [binary, "-in", rewritten.name, "-echo", "screen", "-log", "none"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return [Finding(
                severity="error",
                category="sandbox_timeout",
                file=script,
                line=0,
                message=f"LAMMPS sandbox timed out after {timeout}s",
                suggestion="Increase --timeout or check for infinite loops in the script",
            )]

        return _parse_lammps_output(proc.stdout + proc.stderr, script)


def _rewrite_script(script: Path, tmpdir: Path) -> Path:
    lines = script.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _RUN_RE.match(stripped):
            line = _RUN_RE.sub(r"\g<1>0\2", line)
        elif _MINIMIZE_RE.match(stripped):
            line = _MINIMIZE_RE.sub(r"\g<1>1.0e-4 1.0e-6 1 1\2", line)
        out.append(line)
    out_path = tmpdir / script.name
    out_path.write_text("".join(out), encoding="utf-8")
    return out_path


def _parse_lammps_output(output: str, script: Path) -> list[Finding]:
    findings: list[Finding] = []
    lines = output.splitlines()
    last_echo = ""
    for line in lines:
        m = _ERROR_RE.match(line.strip())
        if m:
            msg = m.group(1)
            suggestion = f"Last echoed command: {last_echo.strip()}" if last_echo.strip() else None
            findings.append(Finding(
                severity="error",
                category="lammps_error",
                file=script,
                line=0,
                message=f"LAMMPS error: {msg}",
                suggestion=suggestion,
            ))
        elif line.strip() and not line.startswith("LAMMPS") and not line.startswith("  "):
            last_echo = line
    return findings
