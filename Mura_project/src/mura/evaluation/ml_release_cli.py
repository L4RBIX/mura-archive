from __future__ import annotations

import argparse
from pathlib import Path

from mura.evaluation.ml_release import (
    render_ml_release_report,
    run_ml_release,
    write_ml_release_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run all deterministic Mura ML release gates as one fail-closed command."
    )
    parser.add_argument("--manifest", default="benchmarks/release/ml_release_manifest.json")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_ml_release(Path(args.manifest))
    rendered = render_ml_release_report(report)
    if args.json_output:
        write_ml_release_json(report, Path(args.json_output))
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.offline_release_candidate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
