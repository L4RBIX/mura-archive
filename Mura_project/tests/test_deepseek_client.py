import pytest

from mura.deepseek.client import DeepSeekClient, DeepSeekError


def test_parse_json_strips_markdown_fence() -> None:
    parsed = DeepSeekClient._parse_json_object('```json\n{"status":"ok"}\n```')
    assert parsed == {"status": "ok"}


def test_parse_json_rejects_empty_content() -> None:
    with pytest.raises(DeepSeekError):
        DeepSeekClient._parse_json_object("   ")
