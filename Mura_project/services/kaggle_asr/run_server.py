from __future__ import annotations

import subprocess
import sys
import time

import requests

from services.kaggle_asr.tunnel import register_worker_url, start_quick_tunnel


def main() -> None:
    uvicorn = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.kaggle_asr.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ]
    )
    try:
        for _ in range(180):
            try:
                if requests.get("http://127.0.0.1:8000/health", timeout=1).ok:
                    break
            except requests.RequestException:
                pass
            if uvicorn.poll() is not None:
                raise RuntimeError("Uvicorn stopped during startup")
            time.sleep(1)
        else:
            raise RuntimeError("ASR worker did not become healthy")

        tunnel_process, public_url = start_quick_tunnel(8000)
        print(f"Mura ASR worker: {public_url}", flush=True)
        register_worker_url(public_url)
        tunnel_process.wait()
    finally:
        uvicorn.terminate()


if __name__ == "__main__":
    main()
