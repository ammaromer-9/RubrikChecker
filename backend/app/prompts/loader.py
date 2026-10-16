"""Versioned prompt templates.

Templates live next to this file as `<name>.v<N>.txt` and use `$placeholder`
substitution (so JSON braces in prompts need no escaping). The loader picks the
highest version and exposes a version string like `rubric_parse.v2`, which is
stored with every LLM call and grading so results can be traced to a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^(?P<name>.+)\.v(?P<version>\d+)\.txt$")


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str  # e.g. "rubric_parse.v2"
    template: Template

    def render(self, **values: str) -> str:
        return self.template.substitute(**values)


def load_prompt(name: str, directory: Path = PROMPTS_DIR) -> PromptTemplate:
    best: tuple[int, Path] | None = None
    for path in directory.glob(f"{name}.v*.txt"):
        match = _VERSION_RE.match(path.name)
        if match and match["name"] == name:
            version = int(match["version"])
            if best is None or version > best[0]:
                best = (version, path)
    if best is None:
        raise FileNotFoundError(f"No prompt template named {name!r} in {directory}")
    version, path = best
    return PromptTemplate(
        name=name, version=f"{name}.v{version}", template=Template(path.read_text(encoding="utf-8"))
    )
