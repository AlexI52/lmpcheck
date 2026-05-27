from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from .models import Finding, ParseResult


@dataclass
class SlurmInfo:
    source: Path
    nodes: int = 0
    tasks_per_node: int = 0
    binary: str = ""
    cd_path: Optional[Path] = None
    modules: list[str] = field(default_factory=list)
    time_limit: str = ""
    mail_user: str = ""


def parse_slurm(path: Path) -> SlurmInfo:
    return SlurmInfo(source=path)


def check_slurm(slurm: SlurmInfo, result: ParseResult, lmp_binary: str) -> list[Finding]:
    return []
