from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests


class DeepSeekError(RuntimeError):
    """Raised when the DeepSeek API returns an unusable response."""


@dataclass(frozen=True)
class DeepSeekUsage:
    model: str
    finish_reason: str | None
    request_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        primary_model: str = "deepseek-v4-flash",
        fallback_model: str = "deepseek-v4-pro",
        connect_timeout: int = 30,
        read_timeout: int = 600,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DeepSeek API key must not be empty")

        self.base_url = base_url.rstrip("/")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.timeout = (connect_timeout, read_timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def list_models(self) -> list[str]:
        response = self.session.get(f"{self.base_url}/models", timeout=self.timeout[0])
        self._raise_for_status(response)
        body = response.json()
        return [
            item["id"] for item in body.get("data", []) if isinstance(item, dict) and item.get("id")
        ]

    def request_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_tokens: int,
        attempts: int = 3,
    ) -> tuple[dict[str, Any], DeepSeekUsage]:
        errors: list[str] = []
        models = [self.primary_model]
        if self.fallback_model and self.fallback_model != self.primary_model:
            models.append(self.fallback_model)

        for model in models:
            try:
                return self._request_model_json(
                    model=model,
                    system_prompt=system_prompt,
                    payload=payload,
                    max_tokens=max_tokens,
                    attempts=attempts,
                )
            except DeepSeekError as exc:
                errors.append(f"{model}: {exc}")

        raise DeepSeekError("; ".join(errors))

    def _request_model_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        max_tokens: int,
        attempts: int,
    ) -> tuple[dict[str, Any], DeepSeekUsage]:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "Return exactly one valid JSON object. Do not return Markdown, "
                        "comments, or explanations.\n\nINPUT JSON:\n"
                        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "stream": False,
        }

        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                started = time.perf_counter()
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    timeout=self.timeout,
                )
                elapsed = time.perf_counter() - started

                if response.status_code == 429 or response.status_code >= 500:
                    raise DeepSeekError(self._format_api_error(response))
                self._raise_for_status(response)

                response_body = response.json()
                choices = response_body.get("choices") or []
                if not choices:
                    raise DeepSeekError("response contains no choices")

                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                if finish_reason == "length":
                    raise DeepSeekError("JSON output was truncated by max_tokens")
                if finish_reason not in (None, "stop"):
                    raise DeepSeekError(f"unexpected finish_reason={finish_reason!r}")

                content = (choice.get("message") or {}).get("content")
                parsed = self._parse_json_object(content)
                usage = response_body.get("usage") or {}

                return parsed, DeepSeekUsage(
                    model=response_body.get("model", model),
                    finish_reason=finish_reason,
                    request_seconds=round(elapsed, 3),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                    prompt_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
                    prompt_cache_miss_tokens=usage.get("prompt_cache_miss_tokens"),
                )
            except (requests.Timeout, requests.ConnectionError, DeepSeekError) as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(2**attempt, 10))

        raise DeepSeekError(f"request failed after {attempts} attempts: {last_error}")

    @staticmethod
    def _parse_json_object(content: str | None) -> dict[str, Any]:
        if not content or not content.strip():
            raise DeepSeekError("empty JSON content")

        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(
                f"invalid JSON object at line {exc.lineno}, column {exc.colno}"
            ) from exc

        if not isinstance(parsed, dict):
            raise DeepSeekError(f"expected JSON object, got {type(parsed).__name__}")
        return parsed

    @staticmethod
    def _safe_error_token(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        token = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_")
        return token[:80] or None

    @classmethod
    def _format_api_error(cls, response: requests.Response) -> str:
        parts = [f"HTTP {response.status_code}"]
        try:
            body = response.json()
        except ValueError:
            return parts[0]
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            for key in ("type", "code"):
                token = cls._safe_error_token(error.get(key))
                if token is not None:
                    parts.append(f"{key}={token}")
        return " ".join(parts)

    def _raise_for_status(self, response: requests.Response) -> None:
        if not response.ok:
            raise DeepSeekError(self._format_api_error(response))
