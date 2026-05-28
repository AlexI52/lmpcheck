import tempfile
from pathlib import Path
import pytest
from lmpcheck.sandbox import _rewrite_script


def _rewrite(content: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "test.lmp"
        src.write_text(content)
        out = _rewrite_script(src, Path(tmpdir))
        return out.read_text()


def test_run_rewritten_to_zero():
    assert "run 0" in _rewrite("run 5000\n")


def test_kspace_pppm_disp_accuracy_coarsened():
    result = _rewrite("kspace_style pppm/disp 0\n")
    assert "kspace_style pppm/disp 0.5" in result


def test_kspace_pppm_disp_trailing_comment_preserved():
    result = _rewrite("kspace_style pppm/disp 1e-4 # comment\n")
    assert "kspace_style pppm/disp 0.5" in result
    assert "# comment" in result


def test_kspace_plain_pppm_not_rewritten():
    result = _rewrite("kspace_style pppm 1e-4\n")
    assert "kspace_style pppm 1e-4" in result


def test_kspace_modify_lines_kept_unchanged():
    for cmd in ("kspace_modify diff ad", "kspace_modify force/disp/real 0.0001",
                "kspace_modify mix/disp pair"):
        result = _rewrite(cmd + "\n")
        assert result.strip() == cmd


def test_unrelated_line_unchanged():
    result = _rewrite("pair_modify mix arithmetic\n")
    assert result == "pair_modify mix arithmetic\n"


def test_mesh_injected_before_first_run():
    script = (
        "kspace_style pppm/disp 0\n"
        "kspace_modify mix/disp pair\n"
        "run 1000\n"
    )
    result = _rewrite(script)
    lines = result.splitlines()
    run_idx = next(i for i, l in enumerate(lines) if l.startswith("run 0"))
    assert "kspace_modify mesh 2 2 2" in lines[run_idx - 2]
    assert "kspace_modify mesh/disp 2 2 2" in lines[run_idx - 1]


def test_no_mesh_injection_without_pppm_disp():
    result = _rewrite("run 1000\n")
    assert "kspace_modify mesh" not in result


def test_full_kspace_block_rewritten():
    script = (
        "kspace_style pppm/disp 0\n"
        "kspace_modify force/disp/real 0.0001\n"
        "kspace_modify force/disp/kspace 0.002\n"
        "kspace_modify diff ad\n"
        "kspace_modify mix/disp pair\n"
        "run 5000\n"
    )
    result = _rewrite(script)
    assert "kspace_style pppm/disp 0.5" in result
    assert "kspace_modify mix/disp pair" in result
    assert "kspace_modify mesh 2 2 2" in result
    assert "kspace_modify mesh/disp 2 2 2" in result
    assert "run 0" in result
