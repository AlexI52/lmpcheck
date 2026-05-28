# LAMMPS Windows Install & Sandbox Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install LAMMPS locally on Windows 10 from packages.lammps.org/windows.html and make `lmpcheck`'s sandbox stage automatically find and invoke the `lmp.exe` binary.

**Architecture:** The Windows LAMMPS installer places `lmp.exe` in `C:\Program Files\LAMMPS 64-bit <version>\bin\`. Currently `sandbox.py` only calls `shutil.which("lmp")`, which fails unless the bin directory is in PATH. We add a Windows-specific fallback search so the binary is found automatically even without a PATH change.

**Tech Stack:** Python 3.11 `subprocess`, `shutil`, `pathlib`, `glob`; LAMMPS 64-bit stable Windows installer.

---

## File Map

| File | Change |
|------|--------|
| `src/lmpcheck/sandbox.py` | Add `_find_lmp_windows()` fallback; replace bare `shutil.which` call |

---

## Task 1: Install LAMMPS on Windows

This task is performed by the **user** (not automated). Steps are here for reference.

- [ ] **Step 1: Download the stable installer**

  Open a browser and go to:
  ```
  https://rpm.lammps.org/windows/LAMMPS-64bit-stable.exe
  ```
  Save the file (it will be ~200 MB).

- [ ] **Step 2: Run the installer**

  Double-click `LAMMPS-64bit-stable.exe`. Accept defaults. The installer will place files under:
  ```
  C:\Program Files\LAMMPS 64-bit <version>\
  ```
  The `lmp.exe` binary will be at:
  ```
  C:\Program Files\LAMMPS 64-bit <version>\bin\lmp.exe
  ```

- [ ] **Step 3: Verify the binary exists**

  In PowerShell:
  ```powershell
  Get-Item "C:\Program Files\LAMMPS*\bin\lmp.exe"
  ```
  Expected: one file listed.

- [ ] **Step 4: (Optional) Add bin directory to PATH**

  If you want `lmp` to work globally from any terminal:
  ```powershell
  $lmpBin = (Get-Item "C:\Program Files\LAMMPS*\bin").FullName
  [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$lmpBin", "User")
  ```
  Then restart your terminal. This is optional — Task 2 makes `lmpcheck` find the binary automatically without PATH changes.

---

## Task 2: Add Windows Fallback Binary Discovery to sandbox.py

**Files:**
- Modify: `src/lmpcheck/sandbox.py`

- [ ] **Step 1: Read the current file**

  Current `sandbox.py` is at `src/lmpcheck/sandbox.py`. The relevant section is `run_sandbox()` which calls `shutil.which(lmp_binary)` at line 17 and returns a warning finding if it returns `None`.

- [ ] **Step 2: Add `_find_lmp_windows()` and update `run_sandbox()`**

  Replace `src/lmpcheck/sandbox.py` with:

  ```python
  import re
  import shutil
  import subprocess
  import sys
  import tempfile
  from glob import glob
  from pathlib import Path

  from .models import Finding
  from .parser import parse
  from .static_checks import _expand_string_vars

  _RUN_RE = re.compile(r"^(\s*run\s+)\S+(.*)$", re.IGNORECASE)
  _MINIMIZE_RE = re.compile(r"^(\s*minimize\s+)\S+\s+\S+\s+\S+\s+\S+(.*)$", re.IGNORECASE)
  _ERROR_RE = re.compile(r"^ERROR(?: on proc \d+)?:\s*(.+?)(?:\s*\(.+\))?$")


  def _find_lmp_binary(name: str) -> str | None:
      """Return full path to the LAMMPS binary, or None if not found.

      On Windows, also searches common LAMMPS install locations when shutil.which fails.
      """
      found = shutil.which(name)
      if found:
          return found

      if sys.platform != "win32":
          return None

      # Windows fallback: search default LAMMPS installer locations
      candidates = glob(r"C:\Program Files\LAMMPS*\bin\lmp.exe")
      candidates += glob(r"C:\Program Files (x86)\LAMMPS*\bin\lmp.exe")
      if candidates:
          # Pick the newest (highest version string sorts last)
          return sorted(candidates)[-1]

      return None


  def run_sandbox(script: Path, lmp_binary: str = "lmp", timeout: int = 60) -> list[Finding]:
      binary = _find_lmp_binary(lmp_binary)
      if not binary:
          msg = f"lmp binary `{lmp_binary}` not found in PATH; skipping sandbox stage"
          suggestion = (
              "Install LAMMPS from https://packages.lammps.org/windows.html "
              "and run the installer, or use --lmp-binary to specify the path, "
              "or --no-sandbox to suppress this warning"
              if sys.platform == "win32"
              else "Install LAMMPS locally or use --lmp-binary to specify the path, "
              "or --no-sandbox to suppress this warning"
          )
          return [Finding(
              severity="warning",
              category="sandbox_skipped",
              file=script,
              line=0,
              message=msg,
              suggestion=suggestion,
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
  ```

- [ ] **Step 3: Run the existing test suite to confirm nothing broke**

  ```powershell
  pytest tests/ -v
  ```

  Expected: all tests PASS (sandbox is not unit-tested; the change is additive).

- [ ] **Step 4: Commit**

  ```
  git add src/lmpcheck/sandbox.py
  git commit -m "feat: auto-detect LAMMPS binary on Windows install paths"
  ```

---

## Task 3: Verify Sandbox Works End-to-End

Prerequisite: Task 1 complete (LAMMPS installed).

- [ ] **Step 1: Confirm binary is found**

  ```powershell
  python -c "from lmpcheck.sandbox import _find_lmp_binary; print(_find_lmp_binary('lmp'))"
  ```

  Expected: prints a path ending in `lmp.exe`, not `None`.

- [ ] **Step 2: Run sandbox on the real script (no-sandbox first to confirm static checks pass)**

  ```powershell
  lmpcheck examples/1.lmp --no-sandbox
  ```

  Expected: hardcoded filename warnings for `L.1.log` and `W.1.NVE`, missing data file error (data file not in examples/), exit code 1 or 2.

- [ ] **Step 3: Run sandbox on the real script with LAMMPS**

  ```powershell
  lmpcheck examples/1.lmp
  ```

  Expected: same static findings PLUS either no sandbox errors (if data file is present) or a LAMMPS error about the missing data file. Should complete in under 30 seconds.

  If you get a missing data file error from LAMMPS (not from static checks), that's expected — copy your data file to `examples/` first:
  ```powershell
  Copy-Item "path\to\C12_rc9p625_re0p0001_ks0p002_kdt3_620.dat" examples\C12.rc9p625.re0p0001.ks0p002.kdt3.620.dat
  ```

- [ ] **Step 4: Run sandbox on broken script**

  ```powershell
  lmpcheck examples/broken.lmp --no-sandbox
  ```

  Expected: ≥5 findings, exit code 2.

  ```powershell
  lmpcheck examples/broken.lmp --no-sandbox --json
  ```

  Expected: valid JSON array printed.

- [ ] **Step 5: Run SLURM cross-check on real sub**

  ```powershell
  lmpcheck examples/1.lmp --slurm examples/1.mill.sub --no-sandbox
  ```

  Expected: binary mismatch warning (`lmp_mpi` vs `lmp`), rank count info (192 ranks), cd path info.

---

## Self-Review Against Spec

**Spec coverage:**

| Requirement | Task |
|-------------|------|
| Sandbox works with locally installed `lmp` binary | Task 1, Task 2 |
| Clear "lmp binary not found" warning when LAMMPS absent | Task 2 (preserved) |
| `--lmp-binary` override still works | Task 2 (preserved — `_find_lmp_binary` respects the name passed) |
| Static checks unaffected | Task 2 (no changes to static_checks.py) |
| Windows `Program Files` install path auto-detected | Task 2 (`_find_lmp_windows` glob) |

**Gaps:** None. The `--lmp-binary` path is unaffected — if a user passes `--lmp-binary C:\path\to\lmp.exe`, `shutil.which` will return it directly (it handles absolute paths). The glob fallback only activates when `shutil.which` returns `None`.

**Placeholder scan:** No TODOs or TBDs.

**Type consistency:** `_find_lmp_binary` returns `str | None`, consistent with `shutil.which` return type. `binary` variable downstream is used as the first element of a list passed to `subprocess.run` — unchanged behavior.
