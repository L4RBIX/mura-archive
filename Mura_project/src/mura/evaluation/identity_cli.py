from __future__ import annotations

import argparse
from pathlib import Path

from mura.evaluation.identity import (
    evaluate_identity_gates,
    load_identity_gate_config,
    render_identity_report,
    run_identity_evaluation,
    write_identity_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate bounded coreference and identity safety."
    )
    parser.add_argument("--coreference", default="benchmarks/coreference_v2.json")
    parser.add_argument("--entity-resolution", default="benchmarks/entity_resolution_v2.json")
    parser.add_argument("--release-gates", default="benchmarks/identity_release_gates.json")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_identity_evaluation(
        coreference_path=Path(args.coreference),
        entity_path=Path(args.entity_resolution),
    )
    gate = evaluate_identity_gates(report, load_identity_gate_config(Path(args.release_gates)))
    rendered = render_identity_report(report, gate)
    if args.json_output:
        write_identity_json(report, Path(args.json_output))
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if gate.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
