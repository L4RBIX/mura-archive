# Resource policy

This runs on a personal Windows dev machine. Optimize for minimal SSD writes, disk
use, CPU and background activity — **without sacrificing correctness**.

## Reuse, never recreate

- `MURA-app/node_modules` and `Mura_project/.venv` already exist. Use them.
- Never run `npm install`, `npm ci`, `pip install`, or recreate a virtualenv without
  asking first. `npm ci` in particular rebuilds `node_modules` from scratch.
- Preserve `.next/cache`, npm cache, pip cache and build caches. Deleting caches is
  **not** a normal troubleshooting step.

## Prefer the smallest sufficient check

| Cost | Use |
| --- | --- |
| Cheap | `npx vitest run`; targeted `pytest tests/test_x.py`; targeted lint/typecheck |
| Checkpoint only | full `pytest` (87 modules); `npm run build` |

Run targeted tests for the files you changed while iterating. Full verification is
expected once, at a meaningful checkpoint or before declaring a task finished — not
after every edit.

## Do not run without asking

`git clean -fdx` · recursive deletion/recreation of dependency directories · repeated
clean builds · repeated full-repo formatting · mass file generation · huge recursive
copies · Docker builds or non-trivial pulls · lockfile regeneration.

## No local ML, ever

No GigaAM download or execution. No Cog build or `cog push`. No CUDA stack. No
Hugging Face, pyannote, torch or Common Voice downloads. No local inference. GigaAM
runs **remotely on Replicate** only.

Confirmed clean as of 2026-08-18: no GigaAM weights exist locally;
`services/replicate_gigaam/` is 20 KB of source. The ~11 GB Hugging Face cache in
`~/.cache/huggingface` belongs to **unrelated** projects (gpt2, mistral, clip, bge-m3,
docling, sam2) — leave it alone.

## Searching

Use `rg`, `git grep`, or targeted Glob/Grep. Always exclude `.git`, `node_modules`,
`.next`, `.venv`, `dist`, `build` and caches. Read only the relevant files; do not
brute-force scan the drive.

## Output and processes

- Keep command output bounded. No verbose/debug logging unless actively
  investigating; no dumping large logs to disk. Use tails and filters.
- No uncontrolled background work: don't leave duplicate dev servers, watchers or
  Docker builds running. Reuse a running server; stop what you started.
- Bound potentially long-running commands with timeouts. If something produces
  enormous output or disk usage, stop it and investigate.
- Ask before generating, downloading or duplicating anything over ~250 MB.

## The point

This eliminates *wasted* work, not necessary verification. Never skip an important
test or security check just to save writes. If an expensive operation is genuinely
required for confidence, explain why and run it **once**.
