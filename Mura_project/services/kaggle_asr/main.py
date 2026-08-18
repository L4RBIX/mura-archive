from __future__ import annotations

import asyncio
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status

from mura.config import WorkerSettings
from mura.domain.models import TranscriptEnvelope
from services.kaggle_asr.audio import AudioProcessingError
from services.kaggle_asr.model import GigaAMTranscriber
from services.kaggle_asr.security import verify_bearer_token

settings = WorkerSettings()  # type: ignore[call-arg]
transcriber = GigaAMTranscriber(device=settings.asr_device, hf_token=settings.hf_token)
processing_lock = asyncio.Lock()

ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".opus",
    ".webm",
    ".flac",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load once so the first public request is not a surprise cold start.
    await asyncio.to_thread(transcriber.load)
    yield


app = FastAPI(
    title="Mura Kaggle ASR Worker",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok" if transcriber.loaded else "loading",
        "service": "mura-kaggle-asr",
        "busy": processing_lock.locked(),
    }


@app.get("/model-info")
def model_info(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    verify_bearer_token(authorization, expected_token=settings.kaggle_asr_api_key)
    return {
        "model": transcriber.model_id,
        "revision": transcriber.revision,
        "variant": transcriber.model_variant,
        "device": settings.asr_device,
        "chunker": transcriber.chunker_version,
    }


@app.post("/v1/transcribe", response_model=TranscriptEnvelope)
async def transcribe(
    file: Annotated[UploadFile, File(...)],
    recording_id: Annotated[str | None, Form()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> TranscriptEnvelope:
    verify_bearer_token(authorization, expected_token=settings.kaggle_asr_api_key)

    suffix = Path(file.filename or "audio.bin").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported extension: {suffix or '<none>'}",
        )
    if processing_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="ASR worker is busy; retry later",
            headers={"Retry-After": "10"},
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    resolved_recording_id = recording_id or f"rec_{uuid.uuid4().hex[:12]}"

    async with processing_lock:
        with tempfile.TemporaryDirectory(prefix="mura-asr-") as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / f"upload{suffix}"
            total = 0
            with input_path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"file exceeds {settings.max_upload_mb} MB",
                        )
                    output.write(chunk)

            try:
                result = await asyncio.to_thread(
                    transcriber.transcribe,
                    input_path=input_path,
                    work_dir=temp_path,
                    recording_id=resolved_recording_id,
                    max_audio_seconds=settings.max_audio_seconds,
                )
            except AudioProcessingError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            return result
