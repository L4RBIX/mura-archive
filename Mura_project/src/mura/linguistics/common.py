from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

_WORD_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


class ScriptBucket(StrEnum):
    CYRILLIC = "cyrillic"
    LATIN = "latin"
    MIXED = "mixed"
    OTHER = "other"


@dataclass(frozen=True)
class TextToken:
    surface: str
    normalized: str
    start: int
    end: int


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.replace("_", " ").split())


def tokenize(value: str) -> list[TextToken]:
    return [
        TextToken(
            surface=match.group(0),
            normalized=normalize_text(match.group(0)),
            start=match.start(),
            end=match.end(),
        )
        for match in _WORD_RE.finditer(value)
    ]


def detect_script(value: str) -> ScriptBucket:
    scripts: set[ScriptBucket] = set()
    for character in unicodedata.normalize("NFKC", value):
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if "CYRILLIC" in name:
            scripts.add(ScriptBucket.CYRILLIC)
        elif "LATIN" in name:
            scripts.add(ScriptBucket.LATIN)
        else:
            scripts.add(ScriptBucket.OTHER)
    if not scripts:
        return ScriptBucket.OTHER
    if len(scripts) == 1:
        return next(iter(scripts))
    return ScriptBucket.MIXED


def contains_normalized_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "
