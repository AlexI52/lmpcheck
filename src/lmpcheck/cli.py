import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lmpcheck",
        description="Pre-flight checker for LAMMPS input scripts",
    )
    parser.add_argument("script", help="Path to .lmp script")
    parser.add_argument("--slurm", metavar="FILE", help="SLURM submission script for cross-check")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--no-sandbox", action="store_true", dest="no_sandbox", help="Skip LAMMPS sandbox invocation")
    parser.add_argument("--lmp-binary", default="lmp", metavar="PATH", dest="lmp_binary", help="LAMMPS binary (default: lmp)")
    parser.add_argument("--timeout", type=int, default=60, help="Sandbox timeout in seconds (default: 60)")
    parser.parse_args()
    print("lmpcheck: not yet implemented")
    sys.exit(0)


if __name__ == "__main__":
    main()
