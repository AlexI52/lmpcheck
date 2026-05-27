from pathlib import Path
import tempfile
from lmpcheck.data_file import parse_data_header


_HEADER = """\
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
"""


def _dat(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".dat", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_parses_counts():
    p = _dat(_HEADER)
    h = parse_data_header(p)
    assert h.atoms == 147552
    assert h.atom_types == 2
    assert h.bond_types == 1


def test_parses_box():
    p = _dat(_HEADER)
    h = parse_data_header(p)
    assert h.xlo == 0.0
    assert h.xhi == 750.0
    assert h.ylo == 0.0
    assert h.yhi == 150.0


def test_stops_before_atoms_section():
    # Add a huge Atoms section; parser should not read into it
    content = _HEADER + "\nAtoms\n\n" + "1 1 1 0.0 0.0 0.0\n" * 100
    p = _dat(content)
    h = parse_data_header(p)  # should complete quickly without reading Atoms section
    assert h.atom_types == 2


def test_source_path_stored():
    p = _dat(_HEADER)
    h = parse_data_header(p)
    assert h.source == p
