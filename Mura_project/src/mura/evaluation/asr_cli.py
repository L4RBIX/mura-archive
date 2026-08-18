from __future__ import annotations

import argparse
from pathlib import Path

from mura.evaluation.asr import (
    evaluate_asr_gates,
    load_asr_dataset,
    load_asr_gate_config,
    render_asr_report,
    run_asr_evaluation,
    validate_runtime_metadata,
    write_asr_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Mura ASR WER/CER and chunk safety.")
    parser.add_argument("--dataset", default="benchmarks/asr_contract_v1.json")
    parser.add_argument("--release-gates", default="benchmarks/asr_release_gates.json")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    parser.add_argument("--require-runtime-metadata", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_asr_evaluation(load_asr_dataset(Path(args.dataset)))
    gate = evaluate_asr_gates(report, load_asr_gate_config(Path(args.release_gates)))
    if args.require_runtime_metadata:
        metadata_failures = validate_runtime_metadata(report.runtime_metadata)
        gate = gate.model_copy(
            update={
                "passed": gate.passed and not metadata_failures,
                "failures": [*gate.failures, *metadata_failures],
            }
        )
    rendered = render_asr_report(report, gate)
    if args.json_output:
        write_asr_json(report, Path(args.json_output))
    if args.markdown_output:
        Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if gate.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
