# Run the Mura ASR worker on Kaggle

Use a fresh Kaggle notebook with Internet enabled and a T4 GPU.

## 1. Add secrets

- `KAGGLE_ASR_API_KEY`: long random bearer token (minimum 32 characters)
- `HF_TOKEN`: optional for the public GigaAM model
- `CORE_BACKEND_URL`: optional core API URL
- `WORKER_REGISTRATION_TOKEN`: required only with `CORE_BACKEND_URL`

## 2. Clone and install

Always leave the repository directory before deleting or recloning it.

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

work_dir = Path("/kaggle/working")
repo_dir = work_dir / "Mura_project"
os.chdir(work_dir)

if repo_dir.exists():
    shutil.rmtree(repo_dir)

subprocess.run(
    [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        "main",
        "https://github.com/cheatplayer-code/Mura_project.git",
        str(repo_dir),
    ],
    cwd=work_dir,
    check=True,
)

os.chdir(repo_dir)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-e", ".[kaggle]"],
    cwd=repo_dir,
    check=True,
)
```

Kaggle secrets are not ordinary environment variables. Load them before starting the worker:

```python
import os
from kaggle_secrets import UserSecretsClient

secrets = UserSecretsClient()
for name in [
    "KAGGLE_ASR_API_KEY",
    "HF_TOKEN",
    "CORE_BACKEND_URL",
    "WORKER_REGISTRATION_TOKEN",
]:
    try:
        value = secrets.get_secret(name)
    except Exception:
        value = None
    if value:
        os.environ[name] = value.strip()
```

## 3. Start Uvicorn and Cloudflare Quick Tunnel

```python
!python -m services.kaggle_asr.run_server
```

The cell prints a temporary URL such as:

```text
Mura ASR worker: https://random-words.trycloudflare.com
```

Keep the cell and Kaggle session running.

## 4. Test from another machine

```bash
curl -X POST "https://YOUR_URL/v1/transcribe" \
  -H "Authorization: Bearer YOUR_KAGGLE_ASR_API_KEY" \
  -F "recording_id=rec_demo_001" \
  -F "file=@story.m4a"
```
