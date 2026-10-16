from pathlib import Path

import pytest

from app.prompts.loader import load_prompt


def test_loads_highest_version_and_renders(tmp_path: Path) -> None:
    (tmp_path / "demo.v1.txt").write_text("old $x")
    (tmp_path / "demo.v2.txt").write_text('new $x {"json": true}')
    (tmp_path / "demo.v10.txt").write_text("newest $x")
    prompt = load_prompt("demo", tmp_path)
    assert prompt.version == "demo.v10"
    assert prompt.render(x="hi") == "newest hi"


def test_json_braces_need_no_escaping(tmp_path: Path) -> None:
    (tmp_path / "demo.v1.txt").write_text('Reply as {"a": 1} for $x')
    assert load_prompt("demo", tmp_path).render(x="y") == 'Reply as {"a": 1} for y'


def test_missing_prompt_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("nope", tmp_path)
