from __future__ import annotations

import argparse
import os
from pathlib import Path

from mura.deepseek.client import DeepSeekClient
from mura.deepseek.service import DeepSeekPipelineService
from mura.evaluation.e2e_live import (
    evaluate_live_e2e_gates,
    load_live_e2e_gate_config,
    render_live_e2e_report,
    run_live_e2e,
    write_live_e2e_json,
)
from mura.pipeline import MuraPipeline
from services.kaggle_asr.model import GigaAMTranscriber


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run approved audio through live GigaAM and DeepSeek E2E evaluation."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--release-gates", default="benchmarks/e2e_live_release_gates.json")
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--max-audio-seconds", type=float, default=1800.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for live E2E evaluation")
    client = DeepSeekClient(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com",
        primary_model=os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash",
        fallback_model=os.getenv("DEEPSEEK_FALLBACK_MODEL") or "deepseek-v4-pro",
    )
    report = run_live_e2e(
        manifest_path=Path(args.manifest),
        transcriber=GigaAMTranscriber(device=args.device, hf_token=os.getenv("HF_TOKEN")),
        pipeline=MuraPipeline(DeepSeekPipelineService(client, focused_extraction=True)),
        max_audio_seconds=args.max_audio_seconds,
        source_commit=os.getenv("GITHUB_SHA") or "local-uncommitted-worktree",
    )
    gate = evaluate_live_e2e_gates(
        report,
        load_live_e2e_gate_config(Path(args.release_gates)),
    )
    rendered = render_live_e2e_report(report, gate)
    write_live_e2e_json(report, Path(args.json_output))
    Path(args.markdown_output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if gate.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
