"""Grading strategies to compare, chosen by name on the command line or in a JSON file.

Shorthand: ``<mode>[:no_evidence][@<model>]`` where mode is ``per_criterion`` (one call
per criterion, as in the app) or ``holistic`` (one call grades every criterion).
Examples: ``per_criterion``, ``holistic``, ``per_criterion:no_evidence``,
``per_criterion@claude-haiku-5-5``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Mode = Literal["per_criterion", "holistic"]
MODES: tuple[str, ...] = ("per_criterion", "holistic")


class StrategyError(ValueError):
    pass


@dataclass(frozen=True)
class StrategySpec:
    name: str
    mode: Mode
    # True: the grader must justify every score with at least one quote from the draft.
    evidence: bool = True
    # None means the model from ANTHROPIC_MODEL.
    model: str | None = None


def parse_strategy(text: str) -> StrategySpec:
    body, _, model = text.strip().partition("@")
    mode, _, option = body.partition(":")
    if mode not in MODES:
        raise StrategyError(f"Unknown strategy mode {mode!r} in {text!r}; use one of {', '.join(MODES)}.")
    if option not in ("", "no_evidence"):
        raise StrategyError(f"Unknown strategy option {option!r} in {text!r}; the only option is no_evidence.")
    if "@" in text and not model.strip():
        raise StrategyError(f"Missing model name after '@' in {text!r}.")
    return StrategySpec(
        name=text.strip(), mode=mode,  # type: ignore[arg-type]
        evidence=option != "no_evidence", model=model.strip() or None,
    )


def load_strategy_config(path: Path) -> list[StrategySpec]:
    """JSON: {"strategies": ["holistic", {"name": "x", "mode": "per_criterion", "evidence": false, "model": "..."}]}"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyError(f"{path.name} is not valid JSON: {exc}") from None
    entries = data.get("strategies") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise StrategyError(f"{path.name} needs a non-empty 'strategies' list.")
    specs = []
    for entry in entries:
        if isinstance(entry, str):
            specs.append(parse_strategy(entry))
        elif isinstance(entry, dict) and "mode" in entry:
            base = parse_strategy(str(entry["mode"]))
            specs.append(
                StrategySpec(
                    name=str(entry.get("name") or entry["mode"]),
                    mode=base.mode,
                    evidence=bool(entry.get("evidence", True)),
                    model=entry.get("model") or None,
                )
            )
        else:
            raise StrategyError(f"Bad strategy entry in {path.name}: {entry!r}")
    names = [s.name for s in specs]
    if len(set(names)) != len(names):
        raise StrategyError("Strategy names must be unique.")
    return specs
