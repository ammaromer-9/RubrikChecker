"""Load essays with known human scores for calibration.

Two formats:

* **Custom CSV** (one row per essay). Columns: `instructions`, `draft`, `human_score`,
  and either `rubric` (raw text, parsed by the LLM once per distinct rubric) or
  `rubric_json` (an already structured rubric). Optional: `id`, `max_score` (top of the
  human scale; defaults to the rubric's total points), and per-criterion human scores in
  columns named `criterion_<criterion id>` (points, same scale as the rubric).
* **ASAP-AES** (Kaggle "Automated Student Assessment Prize"): `training_set_rel3.tsv`
  or a CSV with the same columns (`essay_id`, `essay_set`, `essay`, `domain1_score`).
  The data file has no prompt or rubric text, so you supply them as text files.
"""

from __future__ import annotations

import csv
import io
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.schemas.rubric import Rubric


class DatasetError(ValueError):
    """The dataset file is malformed. Messages name the row so it can be fixed."""


@dataclass(frozen=True)
class EvalExample:
    id: str
    instructions: str
    draft: str
    human_score: float
    rubric_text: str | None = None
    rubric: Rubric | None = None
    # Top and bottom of the human scoring scale. None means "use the rubric's total / 0".
    max_score: float | None = None
    min_score: float = 0.0
    # Human per-criterion points, keyed by the text after `criterion_` in the column name.
    criterion_scores: dict[str, float] = field(default_factory=dict)


# domain1_score range for each ASAP essay set, from the competition's data description.
# Verify against your copy and override with --score-range if it differs.
ASAP_SCORE_RANGES: dict[int, tuple[float, float]] = {
    1: (2, 12), 2: (1, 6), 3: (0, 3), 4: (0, 3), 5: (0, 4), 6: (0, 4), 7: (0, 30), 8: (0, 60),
}


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # the ASAP training file is latin-1
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise DatasetError(f"{path.name}: the file is empty.")
    return [name.strip() for name in reader.fieldnames], [
        {(k or "").strip(): (v or "") for k, v in row.items()} for row in reader
    ]


def _number(value: str, row: int, column: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise DatasetError(f"Row {row}: '{column}' must be a number, got {value!r}.") from None


def sample_examples(
    examples: list[EvalExample], limit: int | None, seed: int | None
) -> list[EvalExample]:
    """First `limit` examples, or a reproducible random sample when a seed is given."""
    if limit is None or limit >= len(examples):
        return examples
    if seed is None:
        return examples[:limit]
    return random.Random(seed).sample(examples, limit)


def load_custom_csv(path: Path) -> list[EvalExample]:
    fields, rows = _read_rows(path)
    required = {"instructions", "draft", "human_score"}
    if missing := sorted(required - set(fields)):
        raise DatasetError(f"{path.name}: missing column(s): {', '.join(missing)}.")
    if not {"rubric", "rubric_json"} & set(fields):
        raise DatasetError(f"{path.name}: needs a 'rubric' or 'rubric_json' column.")
    criterion_columns = [f for f in fields if f.startswith("criterion_") and len(f) > len("criterion_")]

    examples = []
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        for column in ("instructions", "draft"):
            if not row[column].strip():
                raise DatasetError(f"Row {number}: '{column}' is empty.")
        rubric = None
        rubric_text = row.get("rubric", "").strip() or None
        if row.get("rubric_json", "").strip():
            try:
                rubric = Rubric.model_validate(json.loads(row["rubric_json"]))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise DatasetError(f"Row {number}: 'rubric_json' is not a valid rubric ({exc}).") from None
        if rubric is None and rubric_text is None:
            raise DatasetError(f"Row {number}: needs 'rubric' text or 'rubric_json'.")
        max_score = (
            _number(row["max_score"], number, "max_score") if row.get("max_score", "").strip() else None
        )
        examples.append(
            EvalExample(
                id=row.get("id", "").strip() or f"row{number}",
                instructions=row["instructions"],
                draft=row["draft"],
                human_score=_number(row["human_score"], number, "human_score"),
                rubric_text=rubric_text,
                rubric=rubric,
                max_score=max_score,
                criterion_scores={
                    col.removeprefix("criterion_"): _number(row[col], number, col)
                    for col in criterion_columns
                    if row[col].strip()
                },
            )
        )
    if not examples:
        raise DatasetError(f"{path.name}: no data rows.")
    return examples


def load_asap(
    path: Path,
    *,
    essay_set: int,
    instructions: str,
    rubric_text: str,
    score_range: tuple[float, float] | None = None,
) -> list[EvalExample]:
    fields, rows = _read_rows(path)
    required = {"essay_id", "essay_set", "essay", "domain1_score"}
    if missing := sorted(required - set(fields)):
        raise DatasetError(f"{path.name}: not an ASAP file, missing column(s): {', '.join(missing)}.")
    low, high = score_range or ASAP_SCORE_RANGES.get(essay_set, (None, None))  # type: ignore[assignment]
    if low is None:
        raise DatasetError(f"Unknown essay set {essay_set}; pass --score-range MIN MAX.")

    examples = []
    for number, row in enumerate(rows, start=2):
        if row["essay_set"].strip() != str(essay_set):
            continue
        if not row["domain1_score"].strip():
            continue  # some sets leave the resolved score blank
        examples.append(
            EvalExample(
                id=f"asap{essay_set}-{row['essay_id'].strip()}",
                instructions=instructions,
                draft=row["essay"],
                human_score=_number(row["domain1_score"], number, "domain1_score"),
                rubric_text=rubric_text,
                max_score=high,
                min_score=low,
            )
        )
    if not examples:
        raise DatasetError(f"{path.name}: no scored essays found for essay set {essay_set}.")
    return examples
