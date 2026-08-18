from __future__ import annotations

import argparse
from pathlib import Path

from mura.evaluation.e2e import (
    evaluate_e2e_gates,
    load_e2e_dataset,
    load_e2e_gate_config,
    render_e2e_report,
    run_e2e_evaluation,
    write_e2e_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Mura's deterministic offline end-to-end ML release evaluation."
    )
    parser.add_argument("--dataset", default="benchmarks/e2e_pipeline_v1.json")
    parser.add_argument("--release-gates", default="benchmarks/e2e_release_gates.json")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_e2e_evaluation(load_e2e_dataset(Path(args.dataset)))
    gate = evaluate_e2e_gates(report, load_e2e_gate_config(Path(args.release_gates)))
    rendered = render_e2e_report(report, gate)
    if args.json_output:
        write_e2e_json(report, Path(args.json_output))
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if gate.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
