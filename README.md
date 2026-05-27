# lmpcheck

Pre-flight checker for LAMMPS molecular dynamics input scripts. Catches common errors in seconds on your laptop instead of after a long HPC queue wait.

## Install

```bash
pip install -e .
lmpcheck --help
```

Requires Python 3.11+. LAMMPS installation is optional — if `lmp` is not found, static checks still run.

## Usage

```bash
lmpcheck path/to/script.lmp                          # static checks + sandbox
lmpcheck path/to/script.lmp --no-sandbox             # static checks only
lmpcheck path/to/script.lmp --slurm submit.sub       # with SLURM cross-check
lmpcheck path/to/script.lmp --json                   # machine-readable output
lmpcheck path/to/script.lmp --lmp-binary /path/lmp   # override binary
lmpcheck path/to/script.lmp --timeout 120            # sandbox timeout (seconds)
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | Clean — no findings |
| 1    | Warnings only |
| 2    | One or more errors |

## What this catches today

| Check | Category | Notes |
|-------|----------|-------|
| `${undefined}` or `v_undefined` references | `undefined_variable` | Sequential — forward references flagged |
| Division without `floor()` used as step count | `non_integer_steps` | Checks `run ${X}` where X lacks rounding |
| Hardcoded run numbers in output filenames | `hardcoded_filename` | Heuristic — fires when most outputs use a `${VAR}` prefix |
| Missing `read_data` / `read_restart` / `include` files | `missing_file` | Expands string-style variables before checking |
| `pair_coeff` / `bond_coeff` type index exceeds data file count | `atom_type_mismatch` | Requires data file to be present and parseable |
| LAMMPS errors caught by `run 0` sandbox | `lammps_error` | Requires `lmp` binary in PATH |
| SLURM binary mismatch, prime-heavy ranks, missing modules | `slurm_*` | Requires `--slurm` flag |

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```
