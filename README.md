# lmpcheck

Pre-flight checker for LAMMPS molecular dynamics input scripts. Catches common errors in seconds on your laptop instead of after a long queue wait on the cluster.

```
lmpcheck my_script.lmp
```

```
lmpcheck  C:\...\my_script.lmp
  0 error(s), 2 warning(s), 0 info(s)

[WARNING] hardcoded_filename  my_script.lmp:16
  Output filename `L.1.log` hardcodes `1` instead of `${Run}`
  -> Replace `1` with `${Run}` to avoid silent overwrites on re-runs

[WARNING] hardcoded_filename  my_script.lmp:134
  Output filename `W.1.NVE` hardcodes `1` instead of `${Run}`
  -> Replace `1` with `${Run}` to avoid silent overwrites on re-runs
```

---

## Requirements

- Python 3.11 or newer ([python.org/downloads](https://www.python.org/downloads/))
- LAMMPS (optional — static checks work without it; sandbox requires it)

---

## Install

```powershell
git clone https://github.com/AlexI52/lmpcheck.git
cd lmpcheck
pip install -e .
```

Verify it works:

```powershell
lmpcheck --help
```

---

## Install LAMMPS (for sandbox stage)

The sandbox runs your script with `run 0` to catch LAMMPS-specific errors. Without a local `lmp` binary the tool still runs all static checks — skip this section if you only want those.

1. Download: **[LAMMPS-64bit-stable.exe](https://rpm.lammps.org/windows/LAMMPS-64bit-stable.exe)** (~200 MB)
2. Run the installer and accept defaults
3. `lmpcheck` finds the binary automatically — no PATH changes needed

---

## Try it on the included examples

```powershell
# Static checks only (no LAMMPS needed)
lmpcheck examples\1.lmp --no-sandbox

# Full check including LAMMPS sandbox
lmpcheck examples\1.lmp

# With SLURM cross-check
lmpcheck examples\1.lmp --slurm examples\1.mill.sub
```

---

## Usage

```powershell
lmpcheck script.lmp                              # static checks + sandbox
lmpcheck script.lmp --no-sandbox                 # static checks only (no LAMMPS needed)
lmpcheck script.lmp --slurm submit.sub           # also cross-check SLURM submission script
lmpcheck script.lmp --json                       # machine-readable JSON output
lmpcheck script.lmp --lmp-binary C:\path\lmp.exe # use a specific LAMMPS binary
lmpcheck script.lmp --timeout 120                # sandbox timeout in seconds (default: 60)
```

---

## What it catches

| Check | When it fires |
|-------|--------------|
| Undefined variable (`${nstps}` when only `${nsteps}` is defined) | Always |
| Division without `floor()` used as a step count | Always |
| Hardcoded run numbers in output filenames (e.g. `L.1.log` when most outputs use `${Run}`) | Always |
| Missing files referenced by `read_data`, `read_restart`, `include` | Always |
| `pair_coeff` / `bond_coeff` type index exceeds what the data file declares | When data file is present |
| Any LAMMPS error that `run 0` would surface | When LAMMPS is installed |
| SLURM binary mismatch, unusual MPI rank count, missing `module load` | With `--slurm` flag |

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Clean |
| `1` | Warnings only |
| `2` | One or more errors |

---

## Running the tests

```powershell
pip install pytest
pytest tests\ -v
```

---

## What it does not do

- Auto-fix scripts
- Support GROMACS, NAMD, or other MD codes
- Work with PBS/LSF (SLURM only)
- Handle more than one `.lmp` + `.sub` pair at a time
