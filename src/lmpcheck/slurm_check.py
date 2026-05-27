import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

from .models import Finding, ParseResult


@dataclass
class SlurmInfo:
    source: Path
    nodes: int = 0
    tasks_per_node: int = 0
    binary: str = ""
    cd_path: Optional[PurePosixPath] = None
    modules: list[str] = field(default_factory=list)
    time_limit: str = ""
    mail_user: str = ""


_SBATCH_NODES = re.compile(r"#SBATCH\s+--nodes[=\s]+(\d+)")
_SBATCH_TPN = re.compile(r"#SBATCH\s+--tasks-per-node[=\s]+(\d+)")
_SBATCH_TIME = re.compile(r"#SBATCH\s+--time[=\s]+(\S+)")
_SBATCH_MAIL = re.compile(r"#SBATCH\s+--mail-user[=\s]+(\S+)")
_MODULE_LOAD = re.compile(r"^\s*module\s+load\s+(\S+)")
_LMP_BINARY = re.compile(r"\b(lmp(?:_\w+)?)\b")
_CD = re.compile(r"^\s*cd\s+(\S+)")


def parse_slurm(path: Path) -> SlurmInfo:
    info = SlurmInfo(source=path)
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m = _SBATCH_NODES.search(line)
        if m:
            info.nodes = int(m.group(1))
        m = _SBATCH_TPN.search(line)
        if m:
            info.tasks_per_node = int(m.group(1))
        m = _SBATCH_TIME.search(line)
        if m:
            info.time_limit = m.group(1)
        m = _SBATCH_MAIL.search(line)
        if m:
            info.mail_user = m.group(1)
        m = _MODULE_LOAD.match(line)
        if m:
            info.modules.append(m.group(1))
        m = _CD.match(line)
        if m and info.cd_path is None:
            info.cd_path = PurePosixPath(m.group(1))
        # Detect binary from mpirun/srun line
        if not line.strip().startswith("#") and ("mpirun" in line or "srun" in line or "lmp" in line):
            bm = _LMP_BINARY.search(line)
            if bm and not info.binary:
                info.binary = bm.group(1)
    return info


def _is_prime_heavy(n: int) -> bool:
    if n <= 1:
        return False
    factors: list[int] = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return any(f > 5 for f in factors)


def check_slurm(slurm: SlurmInfo, result: ParseResult, lmp_binary: str) -> list[Finding]:
    findings: list[Finding] = []
    local_binary = Path(lmp_binary).name

    # Binary mismatch
    if slurm.binary and slurm.binary != local_binary:
        findings.append(Finding(
            severity="warning",
            category="slurm_binary_mismatch",
            file=slurm.source,
            line=0,
            message=f"SLURM script invokes `{slurm.binary}` but local sandbox uses `{local_binary}`",
            suggestion="Ensure you're testing with the same binary variant used on the cluster",
        ))

    # Rank count sanity
    total_ranks = slurm.nodes * slurm.tasks_per_node
    if total_ranks > 0 and _is_prime_heavy(total_ranks):
        findings.append(Finding(
            severity="warning",
            category="slurm_rank_count",
            file=slurm.source,
            line=0,
            message=f"Total MPI ranks ({slurm.nodes} x {slurm.tasks_per_node} = {total_ranks}) has large prime factors — may cause poor kspace decomposition",
            suggestion="Prefer rank counts that are products of small primes (2, 3, 5) for pppm/disp efficiency",
        ))

    # CD path vs data file
    if slurm.cd_path:
        for cmd in result.commands:
            if cmd.name == "read_data" and cmd.args:
                from .static_checks import _expand_string_vars
                fname = _expand_string_vars(cmd.args[0], result.variables)
                if "$" not in fname:
                    cluster_dat = slurm.cd_path / fname
                    findings.append(Finding(
                        severity="info",
                        category="slurm_data_path",
                        file=slurm.source,
                        line=0,
                        message=f"SLURM `cd` to `{slurm.cd_path}` — verify `{fname}` exists there before submission",
                        suggestion=f"Expected on cluster: {cluster_dat}",
                    ))
                break

    # Modules
    if not slurm.modules:
        findings.append(Finding(
            severity="info",
            category="slurm_no_modules",
            file=slurm.source,
            line=0,
            message="No `module load` lines found in SLURM script",
            suggestion="Add `module load lammps/...` and MPI module lines if needed on your cluster",
        ))

    # Surface mail and time limit as info
    if slurm.mail_user:
        findings.append(Finding(
            severity="info",
            category="slurm_meta",
            file=slurm.source,
            line=0,
            message=f"Job notifications sent to: {slurm.mail_user}",
        ))
    if slurm.time_limit:
        findings.append(Finding(
            severity="info",
            category="slurm_meta",
            file=slurm.source,
            line=0,
            message=f"Time limit: {slurm.time_limit}",
        ))

    return findings
