import argparse
import sys
from pathlib import Path

from .parser import parse
from .data_file import parse_data_header
from .static_checks import run_static_checks, _expand_string_vars
from .report import render_terminal, render_json


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="lmpcheck",
        description="Pre-flight checker for LAMMPS input scripts",
    )
    ap.add_argument("script", help="Path to .lmp script")
    ap.add_argument("--slurm", metavar="FILE", help="SLURM submission script for cross-check")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    ap.add_argument("--no-sandbox", action="store_true", dest="no_sandbox", help="Skip LAMMPS sandbox invocation")
    ap.add_argument("--lmp-binary", default="lmp", metavar="PATH", dest="lmp_binary", help="LAMMPS binary (default: lmp)")
    ap.add_argument("--timeout", type=int, default=60, help="Sandbox timeout in seconds (default: 60)")
    args = ap.parse_args()

    script = Path(args.script).resolve()
    if not script.exists():
        print(f"lmpcheck: script not found: {script}", file=sys.stderr)
        sys.exit(2)

    result = parse(script)
    script_dir = script.parent

    # Resolve data file for atom-type checks
    data_header = None
    for cmd in result.commands:
        if cmd.name == "read_data" and cmd.args:
            fname = _expand_string_vars(cmd.args[0], result.variables)
            if "$" not in fname:
                dat_path = script_dir / fname
                if dat_path.exists():
                    data_header = parse_data_header(dat_path)
            break

    findings = run_static_checks(result, script_dir, data_header)

    if not args.no_sandbox:
        from .sandbox import run_sandbox
        findings += run_sandbox(script, args.lmp_binary, args.timeout)

    if args.slurm:
        from .slurm_check import parse_slurm, check_slurm
        slurm_path = Path(args.slurm).resolve()
        if slurm_path.exists():
            slurm_info = parse_slurm(slurm_path)
            findings += check_slurm(slurm_info, result, args.lmp_binary)
        else:
            print(f"lmpcheck: SLURM file not found: {slurm_path}", file=sys.stderr)

    if args.json:
        print(render_json(findings))
    else:
        render_terminal(findings, script)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    sys.exit(2 if errors else (1 if warnings else 0))


if __name__ == "__main__":
    main()
