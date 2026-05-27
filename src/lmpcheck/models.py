from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Variable:
    name: str
    style: str        # 'equal', 'string', 'atom', 'index', etc.
    value: str        # raw expression or literal value
    line: int
    file: Path


@dataclass
class Command:
    name: str
    args: list[str]
    raw: str          # original (joined) line after continuation merge
    line: int         # line number of first token in original file
    file: Path


@dataclass
class ParseResult:
    commands: list[Command]
    variables: dict[str, Variable]        # name -> last definition
    all_variables: list[Variable]         # all definitions in order


@dataclass
class Finding:
    severity: str     # 'error' | 'warning' | 'info'
    category: str     # see check function names
    file: Path
    line: int
    message: str
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "file": str(self.file),
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
        }
