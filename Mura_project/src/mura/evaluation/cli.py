from __future__ import annotations

import argparse
from pathlib import Path

from mura.evaluation.release_gates import (
    evaluate_release_gates,
    load_release_gate_config,
    render_release_gate_result,
)
from mura.evaluation.reporting import (
    render_markdown_report,
    write_json_report,
    write_markdown_report,
)
from mura.evaluation.runner import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate Mura's deterministic ML core on versioned benchmark fixtures."
    )
    parser.add_argument(
        "--manifest",
        default="benchmarks/manifest.json",
        help="Path to the benchmark manifest.",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path for a machine-readable JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional path for a Markdown report.",
    )
    parser.add_argument(
        "--release-gates",
        default=None,
        help="Optional release-gate configuration. Returns exit code 2 when a gate fails.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_benchmark(Path(args.manifest))

    if args.json_output:
        write_json_report(report, args.json_output)
    if args.markdown_output:
        write_markdown_report(report, args.markdown_output)

    print(render_markdown_report(report))
    if args.release_gates:
        gate_result = evaluate_release_gates(
            report,
            load_release_gate_config(Path(args.release_gates)),
        )
        print()
        print(render_release_gate_result(gate_result))
        if not gate_result.passed:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
