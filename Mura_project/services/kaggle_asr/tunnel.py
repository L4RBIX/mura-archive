from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from pathlib import Path

import requests

CLOUDFLARED_VERSION = "2026.5.2"
CLOUDFLARED_URL = (
    f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/"
    "cloudflared-linux-amd64"
)
CLOUDFLARED_SHA256 = "5286698547f03df745adb2355f04c12dde52ef425491e81f433642d695521886"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def ensure_cloudflared(binary_path: Path = Path("/kaggle/working/cloudflared")) -> Path:
    if binary_path.exists():
        if _sha256_file(binary_path) != CLOUDFLARED_SHA256:
            raise RuntimeError("existing cloudflared binary failed checksum verification")
        return binary_path
    response = requests.get(CLOUDFLARED_URL, timeout=(30, 300))
    response.raise_for_status()
    if _sha256_bytes(response.content) != CLOUDFLARED_SHA256:
        raise RuntimeError("downloaded cloudflared binary failed checksum verification")
    binary_path.write_bytes(response.content)
    binary_path.chmod(0o755)
    return binary_path


def start_quick_tunnel(port: int = 8000) -> tuple[subprocess.Popen[str], str]:
    binary = ensure_cloudflared()
    process = subprocess.Popen(
        [str(binary), "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    deadline = time.time() + 60
    pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
    captured: list[str] = []
    assert process.stdout is not None
    while time.time() < deadline:
        line = process.stdout.readline()
        if line:
            captured.append(line.rstrip())
            match = pattern.search(line)
            if match:
                return process, match.group(0)
        elif process.poll() is not None:
            break
        else:
            time.sleep(0.2)
    process.terminate()
    raise RuntimeError("Cloudflare Quick Tunnel URL was not produced: " + "\n".join(captured[-20:]))


def register_worker_url(public_url: str) -> None:
    backend_url = os.getenv("CORE_BACKEND_URL", "").rstrip("/")
    token = os.getenv("WORKER_REGISTRATION_TOKEN", "")
    if not backend_url or not token:
        return
    response = requests.post(
        f"{backend_url}/v1/workers/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": public_url, "status": "ready"},
        timeout=30,
    )
    response.raise_for_status()
