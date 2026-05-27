# Project: `lmpcheck` — A Pre-flight Runner POC for LAMMPS Jobs

## Context

I'm a mechanical engineering grad student running LAMMPS molecular dynamics simulations on a SLURM-managed HPC cluster. A recurring frustration: I submit a job, wait 20–40 minutes in the queue, and it fails immediately on a preventable error — a typo in a variable name, a missing data file, a non-integer step count because I forgot `floor()`, output files silently overwriting because I hardcoded a run number instead of using `${Run}`. The wasted time per failed job is real, and during prototyping phases this happens often.

I want to build a **pre-flight runner**: a Python CLI that, given a `.lmp` script (and optionally a SLURM submission script), runs cheap static checks AND a sandboxed LAMMPS invocation that catches almost every error LAMMPS itself would catch — but in seconds on my laptop instead of after a long queue wait on the cluster.

This is a POC. Build the smallest thing that demonstrably catches my real error classes on my real scripts. Working > comprehensive > clever.

## The Key Insight

Don't reimplement LAMMPS's own validation logic. Wrap LAMMPS itself.

The approach: copy the input script into a temp directory, rewrite all `run N` commands to `run 0` (which makes LAMMPS perform one force computation but no time integration), shorten `minimize` iteration limits to 1, then invoke `lmp -in script.lmp -echo screen` in that temp dir. LAMMPS will parse every command, resolve every variable, instantiate every fix and compute, allocate neighbor lists, read the data file, and surface any errors — but exit in seconds. We capture stdout/stderr and present errors with rich context.

On top of that, layer light static checks for things LAMMPS doesn't catch fast or doesn't catch at all (filename collisions, missing data files reported clearly, SLURM resource mismatches).

## What to Build (v0 Scope)

A Python 3.11 CLI tool named `lmpcheck`, distributed as a `pyproject.toml`-based package, runnable as:

```bash
lmpcheck path/to/script.lmp                              # script-only check
lmpcheck path/to/script.lmp --slurm path/to/submit.sub   # with SLURM cross-check
lmpcheck path/to/script.lmp --json                       # machine-readable output
lmpcheck path/to/script.lmp --no-sandbox                 # static checks only (skip LAMMPS invocation)
lmpcheck path/to/script.lmp --lmp-binary /path/to/lmp    # override binary path
```

Pipeline stages:

1. **Parse** the `.lmp` script into a list of commands with line numbers and variable references.
2. **Static checks** (cheap, run always): undefined variables, missing files referenced by `read_data` / `read_restart` / `include`, hardcoded output filenames that should probably use `${Run}` or similar (heuristic), missing `floor()` on expressions used as step counts.
3. **Sandbox run** (skippable via `--no-sandbox`): rewrite `run N` → `run 0`, shorten `minimize` args, run LAMMPS in a tempdir, capture errors.
4. **SLURM cross-check** (when `--slurm` is passed): parse the submission script, verify binary, resources, paths, modules.
5. **Report** with severity levels (`error`, `warning`, `info`), file paths, line numbers, and suggested fixes.

Exit codes: `0` clean, `1` warnings only, `2` errors found.

## Error Classes to Catch

These are drawn from real failure modes I've hit. The POC must catch all six on the synthetic test script (see "Test Cases" below).

### 1. Undefined or misspelled variable references

LAMMPS variables are referenced with `${name}` or `v_name`. If a script does `run ${nstps}` but only `nsteps` is defined, LAMMPS dies with a cryptic error after parsing dozens of preceding lines. The static checker should build a symbol table of defined variables (anything from `variable NAME ...`) and flag every `${...}` or `v_...` reference whose name doesn't appear in the table at the point of use.

### 2. Non-integer step counts (missing `floor()`)

A real bug pattern I hit. When dividing nanoseconds by a timestep in fs, the result is often non-integer:

```
variable nsteps equal 5000/(${dt}/1000)        # BAD: 5000/0.003 = 1666666.666...
variable nsteps equal floor(5000/(${dt}/1000)) # GOOD
```

LAMMPS errors out at the `run ${nsteps}` line many minutes into a queue wait. Static heuristic: when a `variable X equal EXPR` expression contains division and `X` is later used as the argument to `run`, `fix ave/chunk`, or anything that requires an integer, warn unless the expression is wrapped in `floor()`, `ceil()`, or `round()`.

### 3. Hardcoded run identifiers in output filenames (silent overwrite risk)

In my real script `1.lmp`, output files use `${Run}` as a prefix (`${Run}.Temp.Density`, `${Run}.stress`, dump files like `WarmEQ.${Run}.*lammpstrj`). But two outputs are hardcoded with `1`:

```
log L.1.log
write_restart W.1.NVE
```

If I re-run with `Run=2`, those two files silently overwrite the Run 1 outputs. Heuristic: detect when other output filenames in the script use `${Run}` (or any single variable) consistently, and warn when a small number of outputs hardcode what looks like the same value. The warning should name both the hardcoded line and the variable that seems to be the intended prefix.

### 4. Missing input files referenced by `read_data`, `read_restart`, `include`

If `read_data ${Data}` resolves to a filename that doesn't exist in the working directory (or alongside the script), warn before the sandbox run wastes time on it. Resolve `${...}` expansions using the symbol table built in step 1.

### 5. Atom-type mismatches between `.lmp` and data file

The `.lmp` script does `pair_coeff 1 1 ...` and `pair_coeff 2 2 ...`. The data file declares `2 atom types`. If a `.lmp` script references atom types not declared in the data file, LAMMPS will fail. Parse the data file header (just the counts section near the top — atoms, bonds, angles, dihedrals, impropers, atom types, bond types, etc., plus box bounds) and cross-check against `pair_coeff`, `bond_coeff`, `angle_coeff`, `dihedral_coeff` type references.

### 6. SLURM cross-check (`--slurm` flag)

Parse the SLURM submission script. Check:
- The LAMMPS binary invoked (e.g. `lmp_mpi`, `lmp`, `lmp_serial`). Warn if it doesn't match the local binary the sandbox is using — the user may be developing against one binary and submitting against another.
- Total MPI ranks (`#SBATCH --nodes=N` × `#SBATCH --tasks-per-node=M`). Sanity-check against the `kspace_style pppm/disp` decomposition (warn for prime-heavy rank counts that won't decompose nicely; this is heuristic).
- The `cd /some/path` line, if present. Verify the data file referenced by the `.lmp` would exist at that path (warn, not error — the user may stage files separately).
- Required modules loaded (e.g. `module load lammps/...`, `module load intelmpi/...`). If a `module load` line is missing entirely, info-level note.
- Mail-user address, time limit — parse and surface but don't validate.

## Implementation Notes

**Language and dependencies.** Python 3.11. Use the standard library wherever possible (`argparse`, `pathlib`, `subprocess`, `tempfile`, `re`, `dataclasses`, `json`). Allow `rich` as a dependency for pretty terminal output — it's worth it for the error report rendering. No other deps in v0.

**Parser approach.** A hand-written line-oriented tokenizer is appropriate. LAMMPS input files are line-oriented; each non-blank, non-comment line is a command. Variable expansion uses `${name}` or `$(expr)`. The tokenizer should:
- Strip `#` comments (but not `#` inside strings, which shouldn't occur in practice in `.lmp` files)
- Handle line continuations (`&` at end of line)
- Recognize the `variable` command and its styles (`equal`, `string`, `atom`, `index`, etc.)
- Recognize `include` directives and recursively parse them (v0 can punt on recursion depth >2 and just warn)
- Track line numbers for every command

For v0, don't try to evaluate variable arithmetic. Just track which variables are defined and where. For filename resolution, do one-pass substitution of `${name}` where `name` resolves to a string-style variable; flag `$(expr)` style as "unevaluated" without trying to compute.

**Sandbox mechanics.** Use `tempfile.TemporaryDirectory`. Copy the `.lmp` script and any files it references (`read_data` targets, etc.) into the temp dir. Rewrite the script:
- Every `run N` (or `run ${var}`) → `run 0`
- Every `minimize a b c d` → `minimize 1.0e-4 1.0e-6 1 1`
- Dump output files will be created but discarded with the tempdir

Invoke LAMMPS as `lmp -in <script> -echo screen -log none`. The `-echo screen` is critical — it makes LAMMPS print each command as it processes them, which makes error attribution to specific lines tractable. Set a timeout (default 60s, configurable via `--timeout`). Capture stdout, stderr, and the return code.

LAMMPS error output is somewhat structured but not great. Pattern-match for lines like `ERROR: ...` and `ERROR on proc 0: ...`. The line that immediately precedes such an error (the last echoed input line) is usually the culprit — use this for line-number attribution back to the original script.

**Report format.** Default: colored terminal output via `rich`, grouping by severity. Each finding includes:
- Severity: `error` (red), `warning` (yellow), `info` (blue)
- File path and line number
- A short message
- A suggestion when possible (e.g. "Did you mean `${nsteps}`? Defined on line 18.")

With `--json`, emit a list of finding objects with the same fields plus a `category` field (`undefined_variable`, `missing_file`, etc.).

## File Structure

```
lmpcheck/
├── pyproject.toml
├── README.md
├── src/
│   └── lmpcheck/
│       ├── __init__.py
│       ├── cli.py              # argparse entry point
│       ├── parser.py           # tokenize .lmp into commands + symbol table
│       ├── static_checks.py    # checks 1–5 above
│       ├── sandbox.py          # rewrite script, invoke LAMMPS, parse errors
│       ├── slurm_check.py      # check 6 above
│       ├── data_file.py        # parse data file header (atom types, etc.)
│       ├── report.py           # rich-based and JSON output
│       └── models.py           # dataclasses: Finding, Command, Variable, etc.
├── examples/
│   ├── 1.lmp                   # I will copy my real scripts here
│   ├── 1_mill.sub
│   ├── C12_rc9p625_re0p0001_ks0p002_kdt3_620.dat
│   └── broken.lmp              # synthetic broken script you generate (see below)
└── tests/
    ├── test_parser.py
    ├── test_static_checks.py
    └── test_slurm_check.py
```

Make `lmpcheck` installable as `pip install -e .` and invocable as a console script. The `pyproject.toml` should declare the entry point so `lmpcheck script.lmp` works after install.

## Generate a synthetic `broken.lmp` for testing

In `examples/broken.lmp`, generate a deliberately broken variant of `1.lmp` that embeds all six error classes above. Annotate each bug with a `# BUG: ...` comment so the test can verify the checker found each one. Minimum bugs to include:

1. A `${...}` reference to a variable that was never defined (typo)
2. A `variable X equal 5000/(${dt}/1000)` without `floor()`, used in a later `run ${X}`
3. A hardcoded `output.1.something` filename where other outputs in the same script use `${Run}`
4. A `read_data nonexistent.dat` line
5. A `pair_coeff 3 3 ...` line that references atom type 3, when the data file only declares 2 atom types

Plus the SLURM cross-check: write a `broken.sub` that uses `lmp_serial` (mismatching `lmp_mpi`) and requests an unusual rank count.

## Acceptance Criteria

The POC is done when all of these are true:

1. `pip install -e .` succeeds; `lmpcheck --help` shows usage.
2. `lmpcheck examples/1.lmp` runs on my real script and exits cleanly (or surfaces real findings about the hardcoded `L.1.log` / `W.1.NVE` lines — which would be a genuine catch).
3. `lmpcheck examples/1.lmp --slurm examples/1_mill.sub` runs the SLURM cross-check and notes the `lmp_mpi` binary, the 192-rank decomposition (3 × 64), and the `cd` path.
4. `lmpcheck examples/broken.lmp` produces findings for at least 5 of the 6 embedded bugs and exits with code 2.
5. `lmpcheck examples/broken.lmp --json` emits valid JSON.
6. `pytest tests/` passes. At least one test per static check.
7. The sandbox stage works against my locally installed `lmp` binary. If LAMMPS isn't found, the tool emits a clear "lmp binary not found; skipping sandbox stage" warning and still runs static checks.
8. Total wall-clock time for `lmpcheck examples/1.lmp` (including sandbox) is under 30 seconds on a modern laptop.

## Out of Scope (Do NOT Build Yet)

- A `--fix` mode that auto-rewrites scripts
- Watch mode / IDE integration / LSP
- Support for GROMACS, NAMD, or any other MD code
- Anything involving LLMs / AI explanations of errors
- A web UI or dashboard
- Anything beyond `slurm` for job managers (no PBS, LSF, etc.)
- Configuration files (no `.lmpcheckrc`)
- Multi-script project understanding (just one `.lmp` + one `.sub` at a time)
- Performance optimization beyond "feels fast on one script"
- Plugin architecture

If you find yourself wanting to add any of these, stop and ask.

## Workflow

1. Set up the project skeleton and `pyproject.toml`.
2. Build the parser and basic data structures first. Get `lmpcheck examples/1.lmp --no-sandbox` to at least parse without crashing and emit an empty finding list.
3. Implement the static checks one at a time, in the order listed. After each, run against `broken.lmp` to verify the relevant bug is caught.
4. Build the sandbox runner. Verify it works against `examples/1.lmp` first (clean run), then `examples/broken.lmp` (should add LAMMPS errors to the report).
5. Add the SLURM cross-check last.
6. Write the tests.
7. Write the README with usage, install instructions, and a "what this catches today" section.

Confirm the plan before starting if anything is unclear. Otherwise, proceed.

## Reference: Real `.lmp` structure (excerpts from `examples/1.lmp`)

Variables defined near the top (and used throughout):
```
variable SubFolder   string rc9p625.re0p0001.ks0p002.kdt3
variable n           equal 12
variable T           equal 620
variable Run         equal 1
variable dt          equal 3
variable Data        string C12.rc9p625.re0p0001.ks0p002.kdt3.620.dat
```

Time-based step variables (note the consistent `floor()` use):
```
variable 5ps   equal floor(5/(${dt}/1000))
variable 10ps  equal floor(10/(${dt}/1000))
...
variable PreEQ equal ${4ns}
```

Output filenames mostly use `${Run}` (but two don't — the bug to catch):
```
log L.1.log                                                    # HARDCODED — should be L.${Run}.log
dump WarmEQDump all custom ${dumpint} WarmEQ.${Run}.*lammpstrj # OK
dump EQDump all custom ${dumpint} EQ.${Run}.*lammpstrj         # OK
fix Rho all ave/chunk ... file ${Run}.Temp.Density             # OK
fix Stress all ave/chunk ... file ${Run}.stress                # OK
write_restart W.1.NVE                                          # HARDCODED — should be W.${Run}.NVE
```

`pair_coeff` lines:
```
pair_coeff 1 1 ${Epsilon_CH2CH2} ${Sigma_CH2CH2} ${LJ_Cutoff}
pair_coeff 2 2 ${Epsilon_CH3CH3} ${Sigma_CH3CH3} ${LJ_Cutoff}
```

## Reference: SLURM structure (from `examples/1_mill.sub`)

```bash
#!/bin/bash
#SBATCH -p requeue
#SBATCH --nodes=3
#SBATCH --tasks-per-node=64
#SBATCH --exclude=compute-41-13
#SBATCH -J PPPM.TraPPE.2Phase.620Thick_R1
#SBATCH --time=48:00:00

cd /home/agcxt/PPPM.TraPPE.2Phase.620Thick/T620K/re0p0001/ks0p002

module load intelmpi/2023.2
module load lammps/2Aug2023

mpirun lmp_mpi -in 1.lmp > 1.log
```

Note: the binary called is `lmp_mpi` (cluster name), but locally it's `lmp`. This is exactly the kind of binary-name mismatch the SLURM check should surface.

## Reference: Data file header (from `examples/C12_*.dat`)

```
# Collapsing slab seed at T = 620.0 K (slab along X)

147552 atoms
135256 bonds
122960 angles
110664 dihedrals
0 impropers

2 atom types
1 bond types
1 angle types
1 dihedral types

0.000000 750.000000 xlo xhi
0.000000 150.000000 ylo yhi
0.000000 150.000000 zlo zhi

Masses

1 14.026400
2 15.034200
```

The `data_file.py` module should parse this header and expose: atom count, bond count, angle count, dihedral count, atom types, bond types, angle types, dihedral types, and box bounds. Don't try to parse the `Atoms`, `Bonds`, etc. sections themselves — they're potentially huge (this file is 500k lines) and not needed for cross-checks.
