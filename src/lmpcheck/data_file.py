import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DataHeader:
    source: Path
    atoms: int = 0
    bonds: int = 0
    angles: int = 0
    dihedrals: int = 0
    impropers: int = 0
    atom_types: int = 0
    bond_types: int = 0
    angle_types: int = 0
    dihedral_types: int = 0
    improper_types: int = 0
    xlo: float = 0.0
    xhi: float = 0.0
    ylo: float = 0.0
    yhi: float = 0.0
    zlo: float = 0.0
    zhi: float = 0.0


_COUNT = re.compile(r"^\s*(\d+)\s+(atoms|bonds|angles|dihedrals|impropers|atom types|bond types|angle types|dihedral types|improper types)\s*$")
_BOX = re.compile(r"^\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+(xlo xhi|ylo yhi|zlo zhi)\s*$")
_SECTION = re.compile(r"^(Atoms|Bonds|Angles|Dihedrals|Impropers|Velocities|Pair Coeffs)", re.IGNORECASE)


def parse_data_header(path: Path) -> DataHeader:
    h = DataHeader(source=path)
    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if _SECTION.match(line) and line.lower() != "masses":
                break  # stop before large sections
            m = _COUNT.match(line)
            if m:
                n, kind = int(m.group(1)), m.group(2)
                setattr(h, kind.replace(" ", "_"), n)
                continue
            m = _BOX.match(line)
            if m:
                lo, hi, axis = float(m.group(1)), float(m.group(2)), m.group(3)
                prefix = axis.split()[0]  # 'xlo', 'ylo', 'zlo'
                setattr(h, prefix, lo)
                setattr(h, prefix.replace("lo", "hi"), hi)
    return h
