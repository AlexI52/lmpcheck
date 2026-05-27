from pathlib import Path
import tempfile
from lmpcheck.slurm_check import parse_slurm, check_slurm
from lmpcheck.parser import parse as parse_lmp


_SUB = """\
#!/bin/bash
#SBATCH -p requeue
#SBATCH --nodes=3
#SBATCH --tasks-per-node=64
#SBATCH --time=48:00:00
#SBATCH --mail-user=user@example.edu

cd /home/user/simulations

module load intelmpi/2023.2
module load lammps/2Aug2023

mpirun lmp_mpi -in 1.lmp > 1.log
"""


def _sub(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sub", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_parses_nodes_and_tasks():
    p = _sub(_SUB)
    info = parse_slurm(p)
    assert info.nodes == 3
    assert info.tasks_per_node == 64


def test_parses_binary():
    p = _sub(_SUB)
    info = parse_slurm(p)
    assert info.binary == "lmp_mpi"


def test_parses_cd_path():
    p = _sub(_SUB)
    info = parse_slurm(p)
    assert str(info.cd_path) == "/home/user/simulations"


def test_parses_modules():
    p = _sub(_SUB)
    info = parse_slurm(p)
    assert "intelmpi/2023.2" in info.modules
    assert "lammps/2Aug2023" in info.modules


def test_binary_mismatch_flagged(tmp_path):
    p = _sub(_SUB)
    info = parse_slurm(p)
    lmp = tmp_path / "empty.lmp"
    lmp.write_text("")
    result = parse_lmp(lmp)
    findings = check_slurm(info, result, lmp_binary="lmp")
    categories = [f.category for f in findings]
    assert "slurm_binary_mismatch" in categories


def test_no_modules_emits_info(tmp_path):
    p = _sub("#!/bin/bash\n#SBATCH --nodes=1\nmpirun lmp_mpi -in x.lmp\n")
    info = parse_slurm(p)
    lmp = tmp_path / "empty.lmp"
    lmp.write_text("")
    result = parse_lmp(lmp)
    findings = check_slurm(info, result, lmp_binary="lmp_mpi")
    assert any(f.severity == "info" and "module" in f.message.lower() for f in findings)
