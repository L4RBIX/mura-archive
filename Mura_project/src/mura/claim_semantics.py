from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from mura.domain.models import (
    AssertionMode,
    ClaimObjectType,
    ClaimReference,
    ClaimUncertainty,
    CleanerResult,
    ConflictDetectionMethod,
    ConflictSet,
    ConflictStatus,
    ConflictType,
    CorrectionKind,
    EpistemicStatus,
    EventDate,
    EvidenceBackedObject,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    PersonDescription,
    PersonMention,
    RelationshipClaim,
    RelationshipState,
    TemporalKind,
    TemporalPrecision,
    TemporalRelation,
    TranscriptEnvelope,
    VerificationStatus,
)
from mura.extraction_issues import (
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
    IssueStage,
)

CLAIM_SEMANTICS_RULES_VERSION = "claim-semantics-v1"
TEMPORAL_RULES_VERSION = "temporal-normalizer-v1"
RELATIONSHIP_STATE_RULES_VERSION = "relationship-state-v1"

EvidenceObjectT = TypeVar("EvidenceObjectT", bound=EvidenceBackedObject)


@dataclass(frozen=True)
class Marker:
    surface: str
    start: int
    end: int
    status: EpistemicStatus
    reason_code: str


@dataclass(frozen=True)
class Clause:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class TemporalNormalization:
    value: EventDate | None
    issues: tuple[ExtractionIssueCode, ...]


_RU_UNCERTAINTY: tuple[tuple[str, EpistemicStatus, str], ...] = (
    ("если не ошибаюсь", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("не помню точно", EpistemicStatus.REMEMBERED_IMPRECISELY, "memory_imprecision"),
    ("точно не знаю", EpistemicStatus.UNRESOLVED, "memory_gap"),
    ("может быть", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("по-моему", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("кажется", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("вроде", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("наверное", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("возможно", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("помнится", EpistemicStatus.REMEMBERED_IMPRECISELY, "memory_imprecision"),
)
_KK_UNCERTAINTY: tuple[tuple[str, EpistemicStatus, str], ...] = (
    ("нақты білмеймін", EpistemicStatus.UNRESOLVED, "memory_gap"),
    ("есімде жоқ", EpistemicStatus.UNRESOLVED, "memory_gap"),
    ("болуы мүмкін", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("қателеспесем", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("сияқты", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("секілді", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("мүмкін", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("шамасы", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
    ("меніңше", EpistemicStatus.UNCERTAIN, "lexical_uncertainty"),
)
_UNCERTAINTY_MARKERS = _RU_UNCERTAINTY + _KK_UNCERTAINTY

# These are explicit anti-markers. They prevent substring-driven false positives.
_CERTAINTY_ANTI_PATTERNS = (
    re.compile(r"\bбез\s+сомнени[яй]\b", re.IGNORECASE),
    re.compile(r"\bточно\b", re.IGNORECASE),
    re.compile(r"\bанық\b", re.IGNORECASE),
)
_QUOTE_PATTERN = re.compile(r"[«\"]([^»\"]+)[»\"]")
_CLAUSE_BOUNDARY = re.compile(
    r"(?<=[.!?;])\s+|\s+(?:а|но|однако|бірақ|ал|дегенмен)\s+|\.{2,}",
    re.IGNORECASE,
)
_CORRECTION_CUE = re.compile(r"\b(?:нет|точнее|вернее|жоқ|дұрысы)\b", re.IGNORECASE)
_REPORTED_SPEECH_CUE = re.compile(
    r"\b(?:сказал(?:а|и)?|говорил(?:а|и)?|утверждал(?:а|и)?|айтты|деді)\b",
    re.IGNORECASE,
)
_DOUBLE_NEGATION_PATTERN = re.compile(
    r"\bне\s+не\s+(?:брат|сестра|отец|мать|муж|жена)\b",
    re.IGNORECASE,
)

_FORMER_PATTERNS = (
    re.compile(r"\bбывш(?:ий|ая|ие|его|ей)\b", re.IGNORECASE),
    re.compile(r"\bбұрынғы\b", re.IGNORECASE),
    re.compile(r"\bраньше\s+были\s+женаты\b", re.IGNORECASE),
    re.compile(r"\bбұрын\s+ерлі[-\s]?зайыпты\s+болған\b", re.IGNORECASE),
)
_ENDED_PATTERNS = (
    re.compile(r"\bразвел(?:ись|ся|ась)\b", re.IGNORECASE),
    re.compile(r"\bвдов(?:а|ец|ы|цы)\b", re.IGNORECASE),
    re.compile(r"\bжесір\b", re.IGNORECASE),
    re.compile(r"\bажыраст(?:ы|ық|ыңыз)\b", re.IGNORECASE),
    re.compile(r"\bуже\s+не\s+женаты\b", re.IGNORECASE),
    re.compile(r"\bбольше\s+не\s+супруги\b", re.IGNORECASE),
    re.compile(r"\bқазір\s+бірге\s+емес\b", re.IGNORECASE),
)
_NEGATED_PATTERNS = (
    re.compile(r"\bникогда\s+не\s+были\s+женаты\b", re.IGNORECASE),
    re.compile(r"\bне\s+является\s+(?:его\s+|её\s+|ее\s+)?(?:отцом|матерью)\b", re.IGNORECASE),
    re.compile(
        r"\bне\s+(?:мой|моя|его|её|ее|ей|ему)?\s*(?:брат|сестра|отец|мать|муж|жена)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:әкесі|анасы|ағасы|інісі|әпкесі|сіңлісі|күйеуі|әйелі)\s+емес\b", re.IGNORECASE
    ),
    re.compile(r"\bтуыс\s+емес\b", re.IGNORECASE),
    re.compile(r"\bерлі[-\s]?зайыпты\s+емес\b", re.IGNORECASE),
)
_FIGURATIVE_PATTERNS = (
    re.compile(r"\bкак\s+(?:родной\s+)?брат\b", re.IGNORECASE),
    re.compile(r"\bкак\s+(?:родная\s+)?сестра\b", re.IGNORECASE),
    re.compile(r"\bағамдай\b", re.IGNORECASE),
    re.compile(r"\bбауырдай\b", re.IGNORECASE),
)
_NON_BIOLOGICAL_PATTERN = re.compile(r"\bнеродн(?:ой|ая)\s+(?:брат|сестра)\b", re.IGNORECASE)

_RU_MONTHS = {
    "январь": 1,
    "января": 1,
    "январе": 1,
    "февраль": 2,
    "февраля": 2,
    "феврале": 2,
    "март": 3,
    "марта": 3,
    "марте": 3,
    "апрель": 4,
    "апреля": 4,
    "апреле": 4,
    "май": 5,
    "мая": 5,
    "мае": 5,
    "июнь": 6,
    "июня": 6,
    "июне": 6,
    "июль": 7,
    "июля": 7,
    "июле": 7,
    "август": 8,
    "августа": 8,
    "августе": 8,
    "сентябрь": 9,
    "сентября": 9,
    "сентябре": 9,
    "октябрь": 10,
    "октября": 10,
    "октябре": 10,
    "ноябрь": 11,
    "ноября": 11,
    "ноябре": 11,
    "декабрь": 12,
    "декабря": 12,
    "декабре": 12,
}
_KK_MONTHS = {
    "қаңтар": 1,
    "ақпан": 2,
    "наурыз": 3,
    "сәуір": 4,
    "мамыр": 5,
    "маусым": 6,
    "шілде": 7,
    "тамыз": 8,
    "қыркүйек": 9,
    "қазан": 10,
    "қараша": 11,
    "желтоқсан": 12,
}
_MONTHS = {**_RU_MONTHS, **_KK_MONTHS}

_EXACT_DATE_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{'|'.join(map(re.escape, _MONTHS))})"
    r"(?:\s+(?P<year>\d{4}))?(?:\s*(?:года|жылы))?\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
_MONTH_YEAR_RE = re.compile(
    rf"\b(?P<month>{'|'.join(map(re.escape, _MONTHS))})\s+(?P<year>\d{{4}})"
    r"(?:\s*(?:года|жылы))?\b",
    re.IGNORECASE,
)
_AMBIGUOUS_NUMERIC_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
_YEAR_RE = re.compile(r"\b(?P<year>1[5-9]\d{2}|20\d{2}|21\d{2})\b")
_RANGE_RE = re.compile(
    r"\b(?:между\s+)?(?P<start>1[5-9]\d{2}|20\d{2})\s*(?:-|–|—|и|мен)\s*"
    r"(?P<end>1[5-9]\d{2}|20\d{2})\b",
    re.IGNORECASE,
)
_APPROXIMATE_RE = re.compile(
    r"\b(?:примерно|около|приблизительно|шамамен|шамасы|сияқты)\b",
    re.IGNORECASE,
)
_BEFORE_RE = re.compile(r"\b(?:до|дейін|бұрын)\b", re.IGNORECASE)
_AFTER_RE = re.compile(r"\b(?:после|кейін|соң)\b", re.IGNORECASE)
_AGE_RELATIVE_RE = re.compile(
    r"\b(?:когда\s+(?:ему|ей)\s+было\s+(?:лет\s+)?(?P<age_ru>\d{1,3})|"
    r"(?P<age_kk>\d{1,3})\s+жасында)\b",
    re.IGNORECASE,
)
_RU_DECADE_RE = re.compile(
    r"\b(?:(?P<position>начал[ео]|середин[еа]|конц[еа])\s+)?"
    r"(?P<decade>шестидесят|семидесят|восьмидесят|девяност|двухтысяч)\w*\b",
    re.IGNORECASE,
)
_KK_DECADE_RE = re.compile(
    r"\b(?P<base>алпысыншы|жетпісінші|сексенінші|тоқсаныншы|екі\s+мыңыншы)\s+"
    r"жылдардың\s*(?P<position>басында|ортасында|соңында)?\b",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    return [match.span(1) for match in _QUOTE_PATTERN.finditer(text)]


def _inside_ranges(start: int, end: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(start >= left and end <= right for left, right in ranges)


def split_clauses(text: str) -> list[Clause]:
    clauses: list[Clause] = []
    cursor = 0
    for match in _CLAUSE_BOUNDARY.finditer(text):
        if match.start() > cursor:
            raw = text[cursor : match.start()]
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip())
            if right > left:
                clauses.append(Clause(raw[left:right], cursor + left, cursor + right))
        cursor = match.end()
    if cursor < len(text):
        raw = text[cursor:]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        if right > left:
            clauses.append(Clause(raw[left:right], cursor + left, cursor + right))
    return clauses or [Clause(text, 0, len(text))]


def find_uncertainty_markers(text: str) -> list[Marker]:
    quoted = _quoted_ranges(text)
    markers: list[Marker] = []
    lowered = text.casefold()
    for surface, status, reason in _UNCERTAINTY_MARKERS:
        for match in re.finditer(rf"(?<!\w){re.escape(surface)}(?!\w)", lowered):
            if _inside_ranges(match.start(), match.end(), quoted):
                continue
            local = text[max(0, match.start() - 16) : min(len(text), match.end() + 16)]
            if surface == "кажется" and re.search(r"\bне\s+кажется\b", local, re.IGNORECASE):
                continue
            if any(pattern.search(local) for pattern in _CERTAINTY_ANTI_PATTERNS):
                if "без сомнен" in local.casefold():
                    continue
            markers.append(
                Marker(
                    text[match.start() : match.end()], match.start(), match.end(), status, reason
                )
            )
    return sorted(markers, key=lambda item: (item.start, item.end))


def _target_clause(text: str, target_surfaces: Iterable[str]) -> Clause | None:
    clauses = split_clauses(text)
    normalized_targets = [
        _normalize(value) for value in target_surfaces if value and _normalize(value)
    ]
    matches: list[Clause] = []
    for clause in clauses:
        normalized_clause = _normalize(clause.text)
        if any(
            target in normalized_clause or normalized_clause in target
            for target in normalized_targets
        ):
            matches.append(clause)
    return matches[0] if len(matches) == 1 else None


def _reported_target_scope(text: str, target_surfaces: Iterable[str]) -> bool:
    quoted = _quoted_ranges(text)
    if not quoted or not _REPORTED_SPEECH_CUE.search(text):
        return False
    lowered = text.casefold()
    target_matches: list[tuple[int, int]] = []
    for surface in target_surfaces:
        normalized_surface = surface.strip().casefold()
        if not normalized_surface:
            continue
        target_matches.extend(
            match.span() for match in re.finditer(re.escape(normalized_surface), lowered)
        )
    return bool(target_matches) and all(
        _inside_ranges(start, end, quoted) for start, end in target_matches
    )


def infer_uncertainty(
    *,
    text: str,
    target_surfaces: Iterable[str],
    source_segment_ids: list[str],
    evidence_ids: list[str],
    existing_mode: AssertionMode,
) -> tuple[ClaimUncertainty | None, ExtractionIssueCode | None]:
    if _reported_target_scope(text, target_surfaces):
        return (
            ClaimUncertainty(
                status=EpistemicStatus.REPORTED,
                markers=[],
                source_segment_ids=list(dict.fromkeys(source_segment_ids)),
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                reason_code="reported_speech",
                requires_review=True,
            ),
            ExtractionIssueCode.REPORTED_SPEECH_REQUIRES_REVIEW,
        )

    markers = find_uncertainty_markers(text)
    if not markers and existing_mode is not AssertionMode.UNCERTAIN:
        return None, None

    clause = _target_clause(text, target_surfaces)
    if clause is None:
        if existing_mode is AssertionMode.UNCERTAIN or markers:
            return (
                ClaimUncertainty(
                    status=EpistemicStatus.UNRESOLVED,
                    markers=[item.surface for item in markers],
                    source_segment_ids=list(dict.fromkeys(source_segment_ids)),
                    evidence_ids=list(dict.fromkeys(evidence_ids)),
                    reason_code="uncertainty_scope_ambiguous",
                    requires_review=True,
                ),
                ExtractionIssueCode.UNCERTAINTY_SCOPE_AMBIGUOUS,
            )
        return None, None

    local = [item for item in markers if item.start >= clause.start and item.end <= clause.end]
    if not local:
        if existing_mode is AssertionMode.UNCERTAIN:
            return (
                ClaimUncertainty(
                    status=EpistemicStatus.UNRESOLVED,
                    markers=[],
                    source_segment_ids=list(dict.fromkeys(source_segment_ids)),
                    evidence_ids=list(dict.fromkeys(evidence_ids)),
                    reason_code="uncertainty_marker_missing",
                    requires_review=True,
                ),
                ExtractionIssueCode.UNCERTAINTY_MARKER_UNSUPPORTED,
            )
        return None, None

    status = max(
        (item.status for item in local),
        key=lambda value: {
            EpistemicStatus.UNCERTAIN: 1,
            EpistemicStatus.REMEMBERED_IMPRECISELY: 2,
            EpistemicStatus.UNRESOLVED: 3,
        }.get(value, 0),
    )
    reason = next(item.reason_code for item in local if item.status is status)
    return (
        ClaimUncertainty(
            status=status,
            markers=list(dict.fromkeys(item.surface for item in local)),
            source_segment_ids=list(dict.fromkeys(source_segment_ids)),
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            reason_code=reason,
            requires_review=True,
        ),
        None,
    )


def relationship_semantic_text(
    relationship: RelationshipClaim,
    *,
    evidence_spans: Iterable[EvidenceSpan],
    people: Iterable[PersonMention],
    fallback_text: str,
) -> str:
    evidence_by_id = {item.evidence_id: item for item in evidence_spans}
    cited = [
        evidence_by_id[evidence_id].text
        for evidence_id in relationship.evidence_ids
        if evidence_id in evidence_by_id
    ]
    text = " ".join(cited).strip() or fallback_text

    people_by_id = {person.mention_id: person for person in people}
    endpoint_surfaces: list[str] = []
    for mention_id in (relationship.subject_mention_id, relationship.object_mention_id):
        person = people_by_id.get(mention_id)
        if person is not None:
            endpoint_surfaces.extend([person.name, *person.aliases])
    normalized_surfaces = [
        _normalize(surface) for surface in endpoint_surfaces if _normalize(surface)
    ]
    if not normalized_surfaces:
        return text

    scored: list[tuple[int, Clause]] = []
    for clause in split_clauses(text):
        normalized_clause = _normalize(clause.text)
        score = sum(surface in normalized_clause for surface in normalized_surfaces)
        if score:
            scored.append((score, clause))
    if not scored:
        return text
    maximum = max(score for score, _ in scored)
    best = [clause for score, clause in scored if score == maximum]
    if len(best) != 1:
        return text

    selected = best[0]
    clauses = split_clauses(text)
    selected_index = next(
        (index for index, clause in enumerate(clauses) if clause == selected),
        None,
    )
    if selected_index is not None and selected_index + 1 < len(clauses):
        following = clauses[selected_index + 1].text
        has_state_cue = any(
            pattern.search(following)
            for pattern in (
                *_FORMER_PATTERNS,
                *_ENDED_PATTERNS,
                *_NEGATED_PATTERNS,
                *_FIGURATIVE_PATTERNS,
            )
        ) or _NON_BIOLOGICAL_PATTERN.search(following)
        if _CORRECTION_CUE.search(following) or has_state_cue:
            return f"{selected.text} {following}"
    return selected.text


def infer_relationship_state(text: str) -> RelationshipState:
    if _DOUBLE_NEGATION_PATTERN.search(text):
        return RelationshipState.UNRESOLVED
    # Figurative and explicit negation are stronger than historical cues.
    if any(
        pattern.search(text) for pattern in _FIGURATIVE_PATTERNS
    ) or _NON_BIOLOGICAL_PATTERN.search(text):
        return RelationshipState.FIGURATIVE
    if any(pattern.search(text) for pattern in _NEGATED_PATTERNS):
        return RelationshipState.NEGATED
    if any(pattern.search(text) for pattern in _ENDED_PATTERNS):
        return RelationshipState.ENDED
    if any(pattern.search(text) for pattern in _FORMER_PATTERNS):
        return RelationshipState.FORMER
    return RelationshipState.CURRENT


def _valid_calendar_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _iso(year: int, month: int | None = None, day: int | None = None) -> str:
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def _decade_bounds(base: int, position: str | None) -> tuple[str, str]:
    normalized = (position or "").casefold()
    if normalized in {"начале", "начало", "басында"}:
        return _iso(base), _iso(base + 3, 12, 31)
    if normalized in {"середине", "середина", "ортасында"}:
        return _iso(base + 3), _iso(base + 6, 12, 31)
    if normalized in {"конце", "конца", "соңында"}:
        return _iso(base + 7), _iso(base + 9, 12, 31)
    return _iso(base), _iso(base + 9, 12, 31)


def _ru_decade_base(token: str) -> int:
    normalized = token.casefold()
    if normalized.startswith("шестидесят"):
        return 1960
    if normalized.startswith("семидесят"):
        return 1970
    if normalized.startswith("восьмидесят"):
        return 1980
    if normalized.startswith("девяност"):
        return 1990
    return 2000


def _kk_decade_base(token: str) -> int:
    normalized = _normalize(token)
    if normalized.startswith("алпысыншы"):
        return 1960
    if normalized.startswith("жетпісінші"):
        return 1970
    if normalized.startswith("сексенінші"):
        return 1980
    if normalized.startswith("тоқсаныншы"):
        return 1990
    return 2000


def parse_temporal_expression(expression: str) -> TemporalNormalization:
    original = expression.strip()
    if not original:
        return TemporalNormalization(None, (ExtractionIssueCode.TEMPORAL_VALUE_INVALID,))

    if _AMBIGUOUS_NUMERIC_DATE_RE.search(original):
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.UNKNOWN,
                precision=TemporalPrecision.UNKNOWN,
                unresolved_reason="locale_ambiguous_numeric_date",
            ),
            (ExtractionIssueCode.TEMPORAL_FORMAT_AMBIGUOUS,),
        )

    match = _ISO_DATE_RE.search(original)
    if match:
        year, month, day = (int(match.group(key)) for key in ("year", "month", "day"))
        if not _valid_calendar_date(year, month, day):
            return TemporalNormalization(None, (ExtractionIssueCode.TEMPORAL_VALUE_INVALID,))
        normalized = _iso(year, month, day)
        return TemporalNormalization(
            EventDate(
                value=normalized,
                normalized_value=normalized,
                original_expression=original,
                kind=TemporalKind.EXACT_DATE,
                precision=TemporalPrecision.DAY,
            ),
            (),
        )

    match = _EXACT_DATE_RE.search(original)
    if match:
        day = int(match.group("day"))
        month = _MONTHS[match.group("month").casefold()]
        year_text = match.group("year")
        if year_text is None:
            return TemporalNormalization(
                EventDate(
                    original_expression=original,
                    kind=TemporalKind.RELATIVE,
                    precision=TemporalPrecision.DAY,
                    unresolved_reason="missing_year",
                ),
                (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
            )
        year = int(year_text)
        if not _valid_calendar_date(year, month, day):
            return TemporalNormalization(None, (ExtractionIssueCode.TEMPORAL_VALUE_INVALID,))
        normalized = _iso(year, month, day)
        return TemporalNormalization(
            EventDate(
                value=normalized,
                normalized_value=normalized,
                original_expression=original,
                kind=TemporalKind.EXACT_DATE,
                precision=TemporalPrecision.DAY,
            ),
            (),
        )

    match = _MONTH_YEAR_RE.search(original)
    if match:
        month = _MONTHS[match.group("month").casefold()]
        year = int(match.group("year"))
        normalized = _iso(year, month)
        approximate = bool(_APPROXIMATE_RE.search(original))
        if approximate:
            return TemporalNormalization(
                EventDate(
                    value=normalized,
                    normalized_value=normalized,
                    original_expression=original,
                    kind=TemporalKind.APPROXIMATE,
                    precision=TemporalPrecision.MONTH,
                    lower_bound=_iso(year, month, 1),
                    upper_bound=_iso(year, month, 31)
                    if month in {1, 3, 5, 7, 8, 10, 12}
                    else (
                        _iso(year, month, 30)
                        if month != 2
                        else _iso(year, month, 29 if _valid_calendar_date(year, 2, 29) else 28)
                    ),
                    approximate=True,
                ),
                (),
            )
        return TemporalNormalization(
            EventDate(
                value=normalized,
                normalized_value=normalized,
                original_expression=original,
                kind=TemporalKind.MONTH_YEAR,
                precision=TemporalPrecision.MONTH,
            ),
            (),
        )

    match = _RANGE_RE.search(original)
    if match:
        lower, upper = int(match.group("start")), int(match.group("end"))
        if lower > upper:
            return TemporalNormalization(None, (ExtractionIssueCode.TEMPORAL_RANGE_INVALID,))
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.RANGE,
                precision=TemporalPrecision.RANGE,
                lower_bound=_iso(lower),
                upper_bound=_iso(upper, 12, 31),
                relation=TemporalRelation.BETWEEN,
            ),
            (),
        )

    match = _RU_DECADE_RE.search(original)
    if match:
        base = _ru_decade_base(match.group("decade"))
        lower_bound, upper_bound = _decade_bounds(base, match.group("position"))
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.DECADE,
                precision=TemporalPrecision.DECADE,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                approximate=True,
            ),
            (),
        )
    match = _KK_DECADE_RE.search(original)
    if match:
        base = _kk_decade_base(match.group("base"))
        lower_bound, upper_bound = _decade_bounds(base, match.group("position"))
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.DECADE,
                precision=TemporalPrecision.DECADE,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                approximate=True,
            ),
            (),
        )

    age = _AGE_RELATIVE_RE.search(original)
    if age:
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.RELATIVE,
                precision=TemporalPrecision.UNKNOWN,
                relation=TemporalRelation.AT_AGE,
                unresolved_reason="birth_anchor_missing",
            ),
            (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
        )

    year_match = _YEAR_RE.search(original)
    approximate = bool(_APPROXIMATE_RE.search(original))
    if year_match:
        year = int(year_match.group("year"))
        if _BEFORE_RE.search(original):
            return TemporalNormalization(
                EventDate(
                    original_expression=original,
                    kind=TemporalKind.RELATIVE,
                    precision=TemporalPrecision.YEAR,
                    relation=TemporalRelation.BEFORE,
                    upper_bound=_iso(year - 1, 12, 31),
                    unresolved_reason="semantic_anchor_not_identified",
                ),
                (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
            )
        if _AFTER_RE.search(original):
            return TemporalNormalization(
                EventDate(
                    original_expression=original,
                    kind=TemporalKind.RELATIVE,
                    precision=TemporalPrecision.YEAR,
                    relation=TemporalRelation.AFTER,
                    lower_bound=_iso(year + 1),
                    unresolved_reason="semantic_anchor_not_identified",
                ),
                (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
            )
        normalized = _iso(year)
        if approximate:
            return TemporalNormalization(
                EventDate(
                    value=normalized,
                    normalized_value=normalized,
                    original_expression=original,
                    kind=TemporalKind.APPROXIMATE,
                    precision=TemporalPrecision.YEAR,
                    lower_bound=_iso(year - 1),
                    upper_bound=_iso(year + 1, 12, 31),
                    approximate=True,
                ),
                (),
            )
        return TemporalNormalization(
            EventDate(
                value=normalized,
                normalized_value=normalized,
                original_expression=original,
                kind=TemporalKind.YEAR,
                precision=TemporalPrecision.YEAR,
            ),
            (),
        )

    if _BEFORE_RE.search(original):
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.RELATIVE,
                precision=TemporalPrecision.UNKNOWN,
                relation=TemporalRelation.BEFORE,
                unresolved_reason="anchor_event_missing",
            ),
            (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
        )
    if _AFTER_RE.search(original):
        return TemporalNormalization(
            EventDate(
                original_expression=original,
                kind=TemporalKind.RELATIVE,
                precision=TemporalPrecision.UNKNOWN,
                relation=TemporalRelation.AFTER,
                unresolved_reason="anchor_event_missing",
            ),
            (ExtractionIssueCode.TEMPORAL_ANCHOR_MISSING,),
        )

    return TemporalNormalization(
        EventDate(
            original_expression=original,
            kind=TemporalKind.UNKNOWN,
            precision=TemporalPrecision.UNKNOWN,
            unresolved_reason="unsupported_temporal_expression",
        ),
        (ExtractionIssueCode.TEMPORAL_EXPRESSION_UNRESOLVED,),
    )


def normalize_event_date(candidate: EventDate, evidence_text: str) -> TemporalNormalization:
    original = (candidate.original_expression or candidate.value or "").strip()
    if not original or _normalize(original) not in _normalize(evidence_text):
        return TemporalNormalization(None, (ExtractionIssueCode.TEMPORAL_EVIDENCE_UNSUPPORTED,))
    parsed = parse_temporal_expression(original)
    if parsed.value is None:
        return parsed

    issues = list(parsed.issues)
    parsed_value = parsed.value
    proposed_exact = (
        candidate.kind is TemporalKind.EXACT_DATE or candidate.precision is TemporalPrecision.DAY
    )
    if parsed_value.approximate and proposed_exact:
        issues.append(ExtractionIssueCode.TEMPORAL_PRECISION_OVERSTATED)
    if (
        parsed_value.kind is TemporalKind.RELATIVE
        and candidate.normalized_value
        and not candidate.anchor_event_id
    ):
        issues.append(ExtractionIssueCode.TEMPORAL_PRECISION_OVERSTATED)
    return TemporalNormalization(
        parsed_value.model_copy(
            update={
                "source_evidence_ids": list(dict.fromkeys(candidate.source_evidence_ids)),
                "verification_status": VerificationStatus.UNREVIEWED,
            }
        ),
        tuple(dict.fromkeys(issues)),
    )


def _issue(
    *,
    object_type: str,
    object_id: str,
    code: ExtractionIssueCode,
    recoverable: bool = True,
    severity: IssueSeverity = IssueSeverity.WARNING,
) -> ExtractionIssue:
    return ExtractionIssue.create(
        stage=IssueStage.SEMANTIC,
        object_type=object_type,
        object_id=object_id,
        code=code,
        severity=severity,
        recoverable=recoverable,
    )


def _segments_text(segment_ids: list[str], transcript: TranscriptEnvelope) -> str:
    requested = set(segment_ids)
    return " ".join(
        segment.text for segment in transcript.segments if segment.segment_id in requested
    )


def _event_targets(event: FamilyEvent) -> list[str]:
    values = [event.title, event.description, event.location or ""]
    if event.date is not None:
        values.extend(
            [
                event.date.original_expression or "",
                event.date.value or "",
                event.date.normalized_value or "",
            ]
        )
    return [value for value in values if value]


def harden_claim_semantics(
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
    *,
    cleaned: CleanerResult | None = None,
) -> tuple[ExtractionResult, list[ExtractionIssue]]:
    issues: list[ExtractionIssue] = []

    def harden_uncertainty(
        item: EvidenceObjectT,
        targets: list[str],
        object_type: str,
        object_id: str,
    ) -> EvidenceObjectT:
        source_text = _segments_text(item.source_segment_ids, transcript)
        uncertainty, code = infer_uncertainty(
            text=source_text,
            target_surfaces=targets,
            source_segment_ids=item.source_segment_ids,
            evidence_ids=item.evidence_ids,
            existing_mode=getattr(item, "assertion_mode", AssertionMode.EXPLICIT),
        )
        if code is not None:
            issues.append(_issue(object_type=object_type, object_id=object_id, code=code))
        if uncertainty is None:
            return item
        update: dict[str, object] = {"uncertainty": uncertainty}
        if hasattr(item, "assertion_mode"):
            update["assertion_mode"] = AssertionMode.UNCERTAIN
        return item.model_copy(update=update)

    people: list[PersonMention] = []
    for person in result.people_mentions:
        # Lexical uncertainty normally scopes to a fact about a person, not to the existence of the
        # mention itself. Preserve model-declared uncertain identity, but do not infect identity
        # merely because the same segment contains an uncertain event or relationship.
        if person.assertion_mode is AssertionMode.UNCERTAIN:
            people.append(
                harden_uncertainty(
                    person,
                    [person.name, *person.aliases],
                    "person",
                    person.mention_id,
                )
            )
        else:
            people.append(person)

    relationships: list[RelationshipClaim] = []
    person_by_id = {person.mention_id: person for person in result.people_mentions}
    for relationship in result.relationship_claims:
        source_text = _segments_text(relationship.source_segment_ids, transcript)
        semantic_text = relationship_semantic_text(
            relationship,
            evidence_spans=result.evidence_spans,
            people=result.people_mentions,
            fallback_text=source_text,
        )
        state = infer_relationship_state(semantic_text)
        updated_relationship = relationship.model_copy(
            update={
                "relationship_state": state,
                "state_evidence_ids": list(relationship.evidence_ids),
            }
        )
        if state is not RelationshipState.CURRENT:
            code = {
                RelationshipState.FORMER: ExtractionIssueCode.RELATIONSHIP_FORMER_NOT_ACTIVE,
                RelationshipState.ENDED: ExtractionIssueCode.RELATIONSHIP_ENDED_NOT_ACTIVE,
                RelationshipState.NEGATED: ExtractionIssueCode.RELATIONSHIP_NEGATED,
                RelationshipState.FIGURATIVE: ExtractionIssueCode.RELATIONSHIP_FIGURATIVE,
                RelationshipState.UNRESOLVED: ExtractionIssueCode.RELATIONSHIP_STATE_CONFLICT,
            }[state]
            issues.append(
                _issue(
                    object_type="relationship",
                    object_id=relationship.relationship_id,
                    code=code,
                )
            )
        subject = person_by_id.get(relationship.subject_mention_id)
        object_person = person_by_id.get(relationship.object_mention_id)
        targets = [
            *([subject.name] if subject is not None else []),
            *([object_person.name] if object_person is not None else []),
            relationship.relationship_type.value,
        ]
        updated_relationship = harden_uncertainty(
            updated_relationship,
            targets,
            "relationship",
            relationship.relationship_id,
        )
        relationships.append(updated_relationship)

    events: list[FamilyEvent] = []
    for event in result.events:
        updated_event = harden_uncertainty(event, _event_targets(event), "event", event.event_id)
        if updated_event.date is not None:
            text = _segments_text(updated_event.source_segment_ids, transcript)
            normalized = normalize_event_date(updated_event.date, text)
            for code in normalized.issues:
                issues.append(
                    _issue(
                        object_type="event",
                        object_id=updated_event.event_id,
                        code=code,
                        severity=(
                            IssueSeverity.ERROR
                            if code
                            in {
                                ExtractionIssueCode.TEMPORAL_VALUE_INVALID,
                                ExtractionIssueCode.TEMPORAL_RANGE_INVALID,
                            }
                            else IssueSeverity.WARNING
                        ),
                        recoverable=True,
                    )
                )
            updated_event = updated_event.model_copy(update={"date": normalized.value})
        events.append(updated_event)

    descriptions: list[PersonDescription] = []
    for description in result.descriptions:
        descriptions.append(
            harden_uncertainty(
                description,
                [description.description, description.perspective],
                "description",
                description.description_id,
            )
        )

    # Explicit speaker corrections refine only claims that share the cited source segments.
    if cleaned is not None:
        self_corrections = [
            correction
            for correction in cleaned.detected_corrections
            if correction.kind is CorrectionKind.SPEAKER_SELF_CORRECTION
        ]

        corrected_relationships: list[RelationshipClaim] = []
        for relationship in relationships:
            source = _segments_text(relationship.source_segment_ids, transcript)
            semantic_text = relationship_semantic_text(
                relationship,
                evidence_spans=result.evidence_spans,
                people=result.people_mentions,
                fallback_text=source,
            )
            endpoint_names = [
                person_by_id[mention_id].name
                for mention_id in (
                    relationship.subject_mention_id,
                    relationship.object_mention_id,
                )
                if mention_id in person_by_id
            ]
            relevant = [
                correction
                for correction in self_corrections
                if set(correction.source_segment_ids) & set(relationship.source_segment_ids)
                and (
                    _normalize(correction.corrected_value) in _normalize(semantic_text)
                    or (
                        correction.subject is not None
                        and any(
                            _normalize(name) in _normalize(correction.subject)
                            for name in endpoint_names
                        )
                        and _normalize(correction.original_value) in _normalize(semantic_text)
                    )
                )
            ]
            correction_context = " ".join(
                f"{correction.original_value} {correction.corrected_value}"
                for correction in relevant
            )
            inferred = infer_relationship_state(f"{semantic_text} {correction_context}")
            if (
                inferred is not RelationshipState.CURRENT
                and relationship.relationship_state is RelationshipState.CURRENT
            ):
                relationship = relationship.model_copy(
                    update={
                        "relationship_state": inferred,
                        "state_evidence_ids": list(relationship.evidence_ids),
                    }
                )
                issues.append(
                    _issue(
                        object_type="relationship",
                        object_id=relationship.relationship_id,
                        code=ExtractionIssueCode.SELF_CORRECTION_APPLIED,
                    )
                )
            corrected_relationships.append(relationship)
        relationships = corrected_relationships

        corrected_events: list[FamilyEvent] = []
        for event in events:
            source = _segments_text(event.source_segment_ids, transcript)
            relevant = [
                correction
                for correction in self_corrections
                if set(correction.source_segment_ids) & set(event.source_segment_ids)
                and _normalize(correction.corrected_value) in _normalize(source)
            ]
            if event.date is not None:
                matching = [
                    correction
                    for correction in relevant
                    if _normalize(correction.original_value)
                    in _normalize(event.date.original_expression or event.date.value or "")
                ]
                if len(matching) == 1:
                    correction = matching[0]
                    normalized = parse_temporal_expression(correction.corrected_value)
                    if normalized.value is not None:
                        event = event.model_copy(
                            update={
                                "date": normalized.value.model_copy(
                                    update={
                                        "source_evidence_ids": list(event.date.source_evidence_ids),
                                        "verification_status": VerificationStatus.UNREVIEWED,
                                    }
                                )
                            }
                        )
                        issues.append(
                            _issue(
                                object_type="event",
                                object_id=event.event_id,
                                code=ExtractionIssueCode.SELF_CORRECTION_APPLIED,
                            )
                        )
                elif len(matching) > 1:
                    event = event.model_copy(update={"date": None})
                    issues.append(
                        _issue(
                            object_type="event",
                            object_id=event.event_id,
                            code=ExtractionIssueCode.SELF_CORRECTION_AMBIGUOUS,
                        )
                    )
            corrected_events.append(event)
        events = corrected_events

    return (
        result.model_copy(
            update={
                "people_mentions": people,
                "relationship_claims": relationships,
                "events": events,
                "descriptions": descriptions,
            }
        ),
        issues,
    )


def add_temporal_conflicts(
    result: ExtractionResult,
) -> tuple[ExtractionResult, list[ExtractionIssue]]:
    singleton_event_types = {"birth", "death"}
    grouped: dict[tuple[str, tuple[str, ...]], list[FamilyEvent]] = {}
    for event in result.events:
        event_type = event.event_type.casefold()
        if event.date is None or event_type not in singleton_event_types:
            continue
        key = (event_type, tuple(sorted(event.participant_mention_ids)))
        grouped.setdefault(key, []).append(event)

    conflicts = list(result.conflict_sets)
    issues: list[ExtractionIssue] = []
    existing_ids = {item.conflict_id for item in conflicts}
    for events in grouped.values():
        signatures: set[tuple[str, str | None, str | None, str | None]] = set()
        for event in events:
            event_date = event.date
            if event_date is None:
                continue
            signatures.add(
                (
                    event_date.kind.value,
                    event_date.normalized_value,
                    event_date.lower_bound,
                    event_date.upper_bound,
                )
            )
        if len(events) < 2 or len(signatures) <= 1:
            continue
        ids = sorted(event.event_id for event in events)
        digest = hashlib.sha256("\x1f".join(ids).encode("utf-8")).hexdigest()[:16]
        conflict_id = f"conflict_temporal_{digest}"
        if conflict_id in existing_ids:
            continue
        evidence_ids = list(
            dict.fromkeys(evidence_id for event in events for evidence_id in event.evidence_ids)
        )
        conflicts.append(
            ConflictSet(
                conflict_id=conflict_id,
                conflict_type=ConflictType.TEMPORAL,
                claim_refs=[
                    ClaimReference(object_type=ClaimObjectType.EVENT, object_id=event.event_id)
                    for event in events
                ],
                status=ConflictStatus.OPEN,
                detected_by=ConflictDetectionMethod.DETERMINISTIC,
                evidence_ids=evidence_ids,
                rationale="Supported temporal claims disagree and require review.",
                verification_status=VerificationStatus.UNREVIEWED,
            )
        )
        for event in events:
            issues.append(
                _issue(
                    object_type="event",
                    object_id=event.event_id,
                    code=ExtractionIssueCode.TEMPORAL_CONFLICT_DETECTED,
                )
            )
    return result.model_copy(update={"conflict_sets": conflicts}), issues


def relationship_is_active_candidate(relationship: RelationshipClaim) -> bool:
    return (
        relationship.relationship_state is RelationshipState.CURRENT
        and relationship.uncertainty is None
        and relationship.assertion_mode is not AssertionMode.UNCERTAIN
    )


def date_is_silently_exactified(event_date: EventDate | None) -> bool:
    if event_date is None:
        return False
    expression = event_date.original_expression or ""
    return bool(_APPROXIMATE_RE.search(expression)) and (
        event_date.kind is TemporalKind.EXACT_DATE
        or event_date.precision is TemporalPrecision.DAY
        or not event_date.approximate
    )


def date_is_invalid_calendar_value(event_date: EventDate | None) -> bool:
    if event_date is None or event_date.normalized_value is None:
        return False
    match = _ISO_DATE_RE.fullmatch(event_date.normalized_value)
    if match is None:
        return False
    return not _valid_calendar_date(
        int(match.group("year")), int(match.group("month")), int(match.group("day"))
    )
