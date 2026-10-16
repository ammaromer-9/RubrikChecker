"""Calibrate the grader against essays with known human scores.

Run from the backend/ folder:

    python -m scripts.calibrate custom --data data/essays.csv --strategies per_criterion holistic
    python -m scripts.calibrate asap --data data/training_set_rel3.tsv --essay-set 1 \\
        --instructions-file data/set1_prompt.txt --rubric-file data/set1_rubric.txt \\
        --limit 30 --seed 0 --strategies per_criterion per_criterion:no_evidence holistic

This calls the real Anthropic API and costs money: it prints the number of calls first
and asks before spending anything (use --yes to skip the question, --dry-run to stop).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.eval import datasets
from app.eval.report import ReportMeta, render_report
from app.eval.runner import (
    ClientFactory,
    estimate_calls,
    load_done,
    prediction_to_json,
    resolve_rubrics,
    run_strategy,
)
from app.eval.strategies import StrategyError, StrategySpec, load_strategy_config, parse_strategy
from app.services.llm_client import LLMConfigError, build_llm_client
from app.services.llm_testing import InMemoryCallRecorder

BACKEND_DIR = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calibrate", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="dataset", required=True)

    custom = sub.add_parser("custom", help="CSV with instructions, rubric, draft, human_score columns")
    custom.add_argument("--data", type=Path, required=True)

    asap = sub.add_parser("asap", help="ASAP-AES training file (.tsv or .csv)")
    asap.add_argument("--data", type=Path, required=True)
    asap.add_argument("--essay-set", type=int, required=True)
    asap.add_argument("--instructions-file", type=Path, required=True, help="text file with the essay prompt")
    asap.add_argument("--rubric-file", type=Path, required=True, help="text file with the scoring rubric")
    asap.add_argument("--score-range", type=float, nargs=2, metavar=("MIN", "MAX"))

    for p in (custom, asap):
        p.add_argument("--strategies", nargs="+", default=["per_criterion"], metavar="STRATEGY",
                       help="e.g. per_criterion holistic per_criterion:no_evidence per_criterion@MODEL")
        p.add_argument("--config", type=Path, help="JSON file listing strategies (overrides --strategies)")
        p.add_argument("--runs", type=int, default=get_settings().grading_runs, help="grading runs per essay")
        p.add_argument("--limit", type=int, help="grade only this many essays")
        p.add_argument("--seed", type=int, help="with --limit, pick a reproducible random sample")
        p.add_argument("--essay-concurrency", type=int, default=2)
        p.add_argument("--call-concurrency", type=int, default=get_settings().grading_concurrency)
        p.add_argument("--out-dir", type=Path, default=BACKEND_DIR / "reports")
        p.add_argument("--cache-dir", type=Path, default=BACKEND_DIR / "data" / ".cache",
                       help="where parsed rubrics are cached between runs")
        p.add_argument("--resume", type=Path, help="reuse predictions.jsonl from an earlier run directory")
        p.add_argument("--yes", action="store_true", help="do not ask before spending money")
        p.add_argument("--dry-run", action="store_true", help="show the call estimate and stop")
    return parser


def make_saver(sink, total: int):  # type: ignore[no-untyped-def]
    """Callback that appends each finished essay to predictions.jsonl and prints progress."""
    count = 0

    def save(prediction) -> None:  # type: ignore[no-untyped-def]
        nonlocal count
        sink.write(prediction_to_json(prediction) + "\n")
        sink.flush()
        count += 1
        suffix = "" if prediction.ok else f"  FAILED: {prediction.error}"
        print(f"  {count}/{total} {prediction.example_id}{suffix}")

    return save


def real_client_factory() -> ClientFactory:
    settings = get_settings()

    def make(model: str | None, recorder):  # type: ignore[no-untyped-def]
        return build_llm_client(settings.model_copy(update={"anthropic_model": model or settings.anthropic_model}), recorder)

    return make


async def main_async(args: argparse.Namespace, make_client: ClientFactory | None = None) -> int:
    settings = get_settings()
    make_client = make_client or real_client_factory()

    try:
        specs: list[StrategySpec] = (
            load_strategy_config(args.config) if args.config else [parse_strategy(s) for s in args.strategies]
        )
        if args.dataset == "custom":
            examples = datasets.load_custom_csv(args.data)
            dataset_name = args.data.name
        else:
            examples = datasets.load_asap(
                args.data, essay_set=args.essay_set,
                instructions=args.instructions_file.read_text(encoding="utf-8"),
                rubric_text=args.rubric_file.read_text(encoding="utf-8"),
                score_range=tuple(args.score_range) if args.score_range else None,
            )
            dataset_name = f"{args.data.name} (essay set {args.essay_set})"
    except (datasets.DatasetError, StrategyError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    examples = datasets.sample_examples(examples, args.limit, args.seed)

    try:
        parse_llm = make_client(None, InMemoryCallRecorder())
        resolved = await resolve_rubrics(examples, parse_llm, args.cache_dir)
    except LLMConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    estimate = estimate_calls(specs, resolved, args.runs)
    print(f"{len(resolved)} essays, {args.runs} run(s) each. Estimated LLM calls (before retries):")
    for name, calls in estimate.items():
        print(f"  {name}: {calls}")
    print(f"  total: {sum(estimate.values())}")
    if args.dry_run:
        return 0
    if not args.yes and input("This uses your Anthropic API credits. Proceed? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return 1

    run_dir = args.resume or (args.out_dir / f"calibration-{datetime.now():%Y%m%d-%H%M%S}")
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions_file = run_dir / "predictions.jsonl"
    done = load_done(predictions_file) if args.resume else {}

    results = []
    with predictions_file.open("a", encoding="utf-8") as sink:
        for spec in specs:
            print(f"Running {spec.name}...")
            save = make_saver(sink, len(resolved))

            results.append(
                await run_strategy(
                    spec, resolved, make_client=make_client, runs=args.runs,
                    essay_concurrency=args.essay_concurrency, call_concurrency=args.call_concurrency,
                    done=done.get(spec.name), on_prediction=save,
                )
            )

    report = render_report(
        ReportMeta(
            dataset=dataset_name, examples=len(resolved), runs=args.runs,
            default_model=settings.anthropic_model or "(unset)", generated_at=datetime.now(),
            warnings=[w for r in resolved for w in r.warnings],
        ),
        results,
    )
    report_path = run_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {report_path}")
    return 0


def main() -> None:
    args = build_parser().parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
