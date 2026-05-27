from pathlib import Path
import textwrap
import tempfile
import pytest
from lmpcheck.parser import parse


def _script(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".lmp", delete=False)
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def test_strips_comment_lines():
    p = _script("# this is a comment\nvariable x equal 1\n")
    result = parse(p)
    assert len(result.commands) == 1
    assert result.commands[0].name == "variable"


def test_strips_inline_comments():
    p = _script("variable x equal 1  # inline comment\n")
    result = parse(p)
    assert result.commands[0].args == ["x", "equal", "1"]


def test_line_continuation():
    p = _script("variable x &\n  equal 1\n")
    result = parse(p)
    assert result.commands[0].name == "variable"
    assert "equal" in result.commands[0].args


def test_variable_parsed_into_symbol_table():
    p = _script("variable Run equal 1\nvariable Data string myfile.dat\n")
    result = parse(p)
    assert "Run" in result.variables
    assert result.variables["Run"].style == "equal"
    assert result.variables["Run"].value == "1"
    assert result.variables["Data"].style == "string"
    assert result.variables["Data"].value == "myfile.dat"


def test_command_line_numbers():
    p = _script("# comment\nvariable x equal 1\nrun 100\n")
    result = parse(p)
    names = [c.name for c in result.commands]
    assert names == ["variable", "run"]
    assert result.commands[1].line == 3


def test_blank_lines_skipped():
    p = _script("\n\nvariable x equal 1\n\n")
    result = parse(p)
    assert len(result.commands) == 1


def test_all_variables_preserves_order():
    p = _script("variable a equal 1\nvariable b equal 2\nvariable a equal 3\n")
    result = parse(p)
    assert len(result.all_variables) == 3
    assert result.all_variables[0].name == "a"
    assert result.variables["a"].value == "3"  # last definition wins
