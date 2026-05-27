from pathlib import Path
import tempfile, textwrap
from lmpcheck.parser import parse
from lmpcheck.static_checks import check_undefined_variables


def _script(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".lmp", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def test_undefined_variable_flagged():
    p = _script("variable dt equal 3\nrun ${nstps}\n")
    result = parse(p)
    findings = check_undefined_variables(result)
    assert len(findings) == 1
    assert findings[0].category == "undefined_variable"
    assert "nstps" in findings[0].message


def test_defined_variable_not_flagged():
    p = _script("variable nsteps equal 100\nrun ${nsteps}\n")
    result = parse(p)
    findings = check_undefined_variables(result)
    assert findings == []


def test_forward_reference_flagged():
    p = _script("run ${nsteps}\nvariable nsteps equal 100\n")
    result = parse(p)
    findings = check_undefined_variables(result)
    assert len(findings) == 1


def test_v_prefix_reference_flagged():
    p = _script("variable dt equal 3\nfix 1 all ave/time 1 1 1 v_missing\n")
    result = parse(p)
    findings = check_undefined_variables(result)
    assert any("missing" in f.message for f in findings)


from lmpcheck.static_checks import check_non_integer_steps


def test_non_integer_steps_flagged():
    p = _script(
        "variable dt equal 3\n"
        "variable bad equal 5000/(${dt}/1000)\n"
        "run ${bad}\n"
    )
    result = parse(p)
    findings = check_non_integer_steps(result)
    assert len(findings) == 1
    assert findings[0].category == "non_integer_steps"
    assert "bad" in findings[0].message


def test_floor_suppresses_warning():
    p = _script(
        "variable dt equal 3\n"
        "variable ok equal floor(5000/(${dt}/1000))\n"
        "run ${ok}\n"
    )
    result = parse(p)
    findings = check_non_integer_steps(result)
    assert findings == []


def test_division_not_used_in_run_not_flagged():
    p = _script(
        "variable dt equal 3\n"
        "variable ratio equal 100/${dt}\n"
        "thermo ${ratio}\n"
    )
    result = parse(p)
    findings = check_non_integer_steps(result)
    assert findings == []


from lmpcheck.static_checks import check_hardcoded_filenames


def test_hardcoded_filename_flagged():
    p = _script(
        "variable Run equal 1\n"
        "log L.1.log\n"
        "dump d1 all custom 100 EQ.${Run}.lammpstrj id x y z\n"
        "dump d2 all custom 100 Prod.${Run}.lammpstrj id x y z\n"
        "write_restart W.1.NVE\n"
    )
    result = parse(p)
    findings = check_hardcoded_filenames(result)
    categories = [f.category for f in findings]
    assert "hardcoded_filename" in categories
    messages = " ".join(f.message for f in findings)
    assert "L.1.log" in messages or "W.1.NVE" in messages


def test_all_using_run_var_no_warning():
    p = _script(
        "variable Run equal 1\n"
        "log L.${Run}.log\n"
        "dump d1 all custom 100 EQ.${Run}.lammpstrj id x y z\n"
        "write_restart W.${Run}.NVE\n"
    )
    result = parse(p)
    findings = check_hardcoded_filenames(result)
    assert findings == []


from lmpcheck.static_checks import check_missing_files


def test_missing_read_data_flagged(tmp_path):
    p = tmp_path / "test.lmp"
    p.write_text("read_data missing.dat\n")
    result = parse(p)
    findings = check_missing_files(result, tmp_path)
    assert len(findings) == 1
    assert findings[0].category == "missing_file"
    assert "missing.dat" in findings[0].message


def test_existing_read_data_not_flagged(tmp_path):
    dat = tmp_path / "real.dat"
    dat.write_text("# data\n")
    p = tmp_path / "test.lmp"
    p.write_text("read_data real.dat\n")
    result = parse(p)
    findings = check_missing_files(result, tmp_path)
    assert findings == []


def test_string_variable_expanded_for_file_check(tmp_path):
    dat = tmp_path / "C12.dat"
    dat.write_text("# data\n")
    p = tmp_path / "test.lmp"
    p.write_text("variable Data string C12.dat\nread_data ${Data}\n")
    result = parse(p)
    findings = check_missing_files(result, tmp_path)
    assert findings == []


from lmpcheck.static_checks import check_atom_type_mismatches
from lmpcheck.data_file import DataHeader


def test_excess_pair_coeff_type_flagged(tmp_path):
    p = tmp_path / "test.lmp"
    p.write_text("pair_coeff 3 3 0.1 3.5 9.0\n")
    result = parse(p)
    header = DataHeader(source=tmp_path / "fake.dat", atom_types=2)
    findings = check_atom_type_mismatches(result, header)
    assert len(findings) == 1
    assert findings[0].category == "atom_type_mismatch"
    assert "3" in findings[0].message


def test_valid_pair_coeff_not_flagged(tmp_path):
    p = tmp_path / "test.lmp"
    p.write_text("pair_coeff 1 1 0.1 3.5 9.0\npair_coeff 2 2 0.2 3.7 9.0\n")
    result = parse(p)
    header = DataHeader(source=tmp_path / "fake.dat", atom_types=2)
    findings = check_atom_type_mismatches(result, header)
    assert findings == []


def test_no_data_header_skips_check(tmp_path):
    p = tmp_path / "test.lmp"
    p.write_text("pair_coeff 5 5 0.1 3.5 9.0\n")
    result = parse(p)
    findings = check_atom_type_mismatches(result, None)
    assert findings == []
