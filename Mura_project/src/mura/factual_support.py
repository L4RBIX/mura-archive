from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from mura.relationship_evidence import normalize_evidence


class FactualSupportStatus(StrEnum):
    EXACT = "exact"
    ORDERED = "ordered"
    UNSUPPORTED = "unsupported"
    ADDS_CAUSALITY = "adds_causality"
    DROPS_NEGATION = "drops_negation"
    ROLE_ORDER_CHANGED = "role_order_changed"


@dataclass(frozen=True)
class FactualSupportResult:
    status: FactualSupportStatus
    supported: bool
    statement_tokens: tuple[str, ...]
    evidence_tokens: tuple[str, ...]


_NEGATION = frozenset(
    {"не", "ни", "нет", "никогда", "емес", "жоқ", "ешқашан", "not", "never", "no"}
)
_CAUSALITY = frozenset(
    {
        "потому",
        "поэтому",
        "ради",
        "из-за",
        "чтобы",
        "себебі",
        "сондықтан",
        "үшін",
        "because",
        "therefore",
        "so",
    }
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|[\n\r]+")


def significant_tokens(value: str) -> tuple[str, ...]:
    normalized = normalize_evidence(value)
    return tuple(token for token in normalized.split() if len(token) >= 2 or token.isdigit())


def split_factual_statements(value: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_BOUNDARY.split(value) if part.strip()]


def _is_ordered_subsequence(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if not needle:
        return False
    cursor = 0
    for token in haystack:
        if token == needle[cursor]:
            cursor += 1
            if cursor == len(needle):
                return True
    return False


def _relative_order(tokens: tuple[str, ...], anchors: Iterable[str]) -> tuple[str, ...]:
    anchor_set = set(anchors)
    return tuple(token for token in tokens if token in anchor_set)


def evaluate_factual_support(statement: str, evidence_text: str) -> FactualSupportResult:
    normalized_statement = normalize_evidence(statement)
    normalized_evidence = normalize_evidence(evidence_text)
    statement_tokens = significant_tokens(statement)
    evidence_tokens = significant_tokens(evidence_text)

    if not normalized_statement or not normalized_evidence:
        return FactualSupportResult(
            status=FactualSupportStatus.UNSUPPORTED,
            supported=False,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    if normalized_statement in normalized_evidence:
        return FactualSupportResult(
            status=FactualSupportStatus.EXACT,
            supported=True,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    statement_set = set(statement_tokens)
    evidence_set = set(evidence_tokens)
    if statement_set.intersection(_CAUSALITY) and not evidence_set.intersection(_CAUSALITY):
        return FactualSupportResult(
            status=FactualSupportStatus.ADDS_CAUSALITY,
            supported=False,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    if evidence_set.intersection(_NEGATION) and not statement_set.intersection(_NEGATION):
        return FactualSupportResult(
            status=FactualSupportStatus.DROPS_NEGATION,
            supported=False,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    if not statement_set.issubset(evidence_set):
        return FactualSupportResult(
            status=FactualSupportStatus.UNSUPPORTED,
            supported=False,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    if _is_ordered_subsequence(statement_tokens, evidence_tokens):
        return FactualSupportResult(
            status=FactualSupportStatus.ORDERED,
            supported=True,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    shared = statement_set.intersection(evidence_set)
    if len(shared) >= 2 and _relative_order(statement_tokens, shared) != _relative_order(
        evidence_tokens, shared
    ):
        return FactualSupportResult(
            status=FactualSupportStatus.ROLE_ORDER_CHANGED,
            supported=False,
            statement_tokens=statement_tokens,
            evidence_tokens=evidence_tokens,
        )

    return FactualSupportResult(
        status=FactualSupportStatus.UNSUPPORTED,
        supported=False,
        statement_tokens=statement_tokens,
        evidence_tokens=evidence_tokens,
    )


def unsupported_statement_count(value: str, evidence_text: str) -> int:
    return sum(
        not evaluate_factual_support(statement, evidence_text).supported
        for statement in split_factual_statements(value)
    )


def all_statements_supported(value: str, evidence_text: str) -> bool:
    statements = split_factual_statements(value)
    return bool(statements) and all(
        evaluate_factual_support(statement, evidence_text).supported for statement in statements
    )


_SENSITIVITY_CATEGORIES: dict[str, frozenset[str]] = {
    "health_or_death": frozenset(
        {
            "болезнь",
            "болел",
            "больница",
            "рак",
            "диагноз",
            "смерть",
            "умер",
            "умерла",
            "ауру",
            "аурухана",
            "қайтыс",
            "өлім",
            "health",
            "illness",
            "hospital",
            "death",
            "died",
        }
    ),
    "family_conflict": frozenset({"конфликт", "ссора", "развод", "жанжал", "ажырас*", "divorce"}),
    "legal_or_financial": frozenset(
        {"долг", "деньги", "суд", "тюрьма", "қарыз", "сот", "debt", "court"}
    ),
}
_HIGHLY_SENSITIVE_CATEGORIES: dict[str, frozenset[str]] = {
    "violence_or_self_harm": frozenset(
        {
            "насилие",
            "изнасил*",
            "самоубий*",
            "суицид",
            "зорлық",
            "abuse",
            "rape",
            "suicide",
        }
    ),
    "reproductive_or_addiction": frozenset(
        {
            "аборт",
            "зависимость",
            "наркот*",
            "есірткі",
            "abortion",
            "addiction",
        }
    ),
}


def _marker_matches(value: str, marker: str) -> bool:
    if marker.endswith("*"):
        stem = marker[:-1]
        return any(token.startswith(stem) for token in value.split())
    return f" {marker} " in f" {value} "


def _matched_categories(value: str, categories: dict[str, frozenset[str]]) -> list[str]:
    return sorted(
        category
        for category, markers in categories.items()
        if any(_marker_matches(value, marker) for marker in markers)
    )


def sensitivity_level(evidence_text: str) -> tuple[str, list[str]]:
    normalized = normalize_evidence(evidence_text)
    highly = _matched_categories(normalized, _HIGHLY_SENSITIVE_CATEGORIES)
    if highly:
        return "highly_sensitive", highly
    sensitive = _matched_categories(normalized, _SENSITIVITY_CATEGORIES)
    if sensitive:
        return "sensitive", sensitive
    return "normal", []
