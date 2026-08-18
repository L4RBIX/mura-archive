from __future__ import annotations

import re
from typing import Any, TypeVar, cast

from mura.claim_semantics import relationship_is_active_candidate
from mura.domain.models import (
    AssertionMode,
    ClaimObjectType,
    ClaimProvenance,
    CleanerResult,
    ConflictSet,
    CoreferenceLink,
    CoreferenceStatus,
    EvidenceBackedObject,
    EvidenceClass,
    EvidencePurpose,
    EvidenceSourceLayer,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    NameVariant,
    NameVariantType,
    PersonCategory,
    PersonDescription,
    PersonMention,
    ProvenanceActivity,
    ProvenanceStage,
    RelationshipClaim,
    Story,
    TranscriptEnvelope,
    UnresolvedQuestion,
    VerificationStatus,
)
from mura.extraction_issues import (
    ExtractionIssue,
    ExtractionIssueCode,
    IssueSeverity,
    IssueStage,
)
from mura.linguistics.multilingual import find_known_name_matches
from mura.relationship_evidence import (
    analyze_relationship_evidence,
    contains_exact_surface,
    contains_surface,
    has_first_person_reference,
    joined_segment_text,
    normalize_evidence,
    person_name_surfaces,
)
from mura.versioning import get_pipeline_versions

ObjectT = TypeVar("ObjectT", bound=EvidenceBackedObject)

_AUTO_ACCEPTABLE_EVIDENCE_CLASSES = {
    EvidenceClass.A_EXPLICIT,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT,
    EvidenceClass.C_SPEAKER_ANCHORED,
}

_EVIDENCE_CLASS_RANK = {
    EvidenceClass.A_EXPLICIT: 0,
    EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT: 1,
    EvidenceClass.C_SPEAKER_ANCHORED: 2,
    EvidenceClass.D_CONTEXT_RESOLVED: 3,
    EvidenceClass.E_INFERRED: 4,
    EvidenceClass.U_UNCERTAIN: 5,
}


ClaimModelIssue = ExtractionIssue


def is_auto_acceptable_evidence_class(evidence_class: EvidenceClass) -> bool:
    return evidence_class in _AUTO_ACCEPTABLE_EVIDENCE_CLASSES


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
    return normalized or "unknown"


def _ordered_segment_ids(segment_ids: list[str], transcript: TranscriptEnvelope) -> list[str]:
    requested = set(segment_ids)
    return [
        segment.segment_id for segment in transcript.segments if segment.segment_id in requested
    ]


def _object_identity(item: EvidenceBackedObject) -> tuple[ClaimObjectType, str]:
    for object_type, field_name in (
        (ClaimObjectType.PERSON_MENTION, "mention_id"),
        (ClaimObjectType.RELATIONSHIP, "relationship_id"),
        (ClaimObjectType.EVENT, "event_id"),
        (ClaimObjectType.DESCRIPTION, "description_id"),
        (ClaimObjectType.STORY, "story_id"),
        (ClaimObjectType.QUESTION, "question_id"),
    ):
        value = getattr(item, field_name, None)
        if isinstance(value, str) and value:
            return object_type, value
    raise ValueError(f"unsupported evidence-backed object {type(item).__name__}")


def _objects(result: ExtractionResult) -> list[EvidenceBackedObject]:
    return [
        *result.people_mentions,
        *result.relationship_claims,
        *result.events,
        *result.descriptions,
        *result.stories,
        *result.unresolved_questions,
    ]


def _authoritative_activities(
    transcript: TranscriptEnvelope,
) -> tuple[list[ProvenanceActivity], str, str]:
    suffix = _safe_id(transcript.recording_id)
    versions = get_pipeline_versions()
    extractor_activity_id = f"activity_extractor_{suffix}"
    sanitizer_activity_id = f"activity_sanitizer_{suffix}"
    return (
        [
            ProvenanceActivity(
                activity_id=f"activity_asr_{suffix}",
                stage=ProvenanceStage.ASR,
                system=transcript.asr_model,
                version=transcript.asr_revision,
                model_name=transcript.asr_model,
                metadata={"chunker_version": transcript.chunker_version},
            ),
            ProvenanceActivity(
                activity_id=extractor_activity_id,
                stage=ProvenanceStage.EXTRACTOR,
                system="deepseek",
                version=versions.extractor_prompt,
                prompt_version=versions.extractor_prompt,
                metadata={"pipeline": versions.pipeline},
            ),
            ProvenanceActivity(
                activity_id=sanitizer_activity_id,
                stage=ProvenanceStage.SANITIZER,
                system="mura",
                version=versions.evidence_rules,
                metadata={"domain_schema": versions.domain_schema},
            ),
        ],
        extractor_activity_id,
        sanitizer_activity_id,
    )


def _validate_candidate_evidence(
    evidence: EvidenceSpan,
    *,
    transcript: TranscriptEnvelope,
    mention_ids: set[str],
    cleaned: CleanerResult | None,
) -> ExtractionIssueCode | None:
    raw_by_id = {segment.segment_id: segment.text for segment in transcript.segments}
    if evidence.segment_id not in raw_by_id:
        return ExtractionIssueCode.EVIDENCE_UNKNOWN_SEGMENT
    readable_by_id = (
        {segment.segment_id: segment.text for segment in cleaned.readable_segments}
        if cleaned is not None
        else {}
    )
    source_text: str | None
    opposite_text: str | None
    if evidence.source_layer is EvidenceSourceLayer.RAW_TRANSCRIPT:
        source_text = raw_by_id[evidence.segment_id]
        opposite_text = readable_by_id.get(evidence.segment_id)
    else:
        source_text = readable_by_id.get(evidence.segment_id)
        opposite_text = raw_by_id[evidence.segment_id]
        if source_text is None:
            return ExtractionIssueCode.EVIDENCE_WRONG_SOURCE_LAYER
    if evidence.text not in source_text:
        if opposite_text is not None and evidence.text in opposite_text:
            return ExtractionIssueCode.EVIDENCE_WRONG_SOURCE_LAYER
        return ExtractionIssueCode.EVIDENCE_TEXT_NOT_IN_SOURCE
    if evidence.start_char is None or evidence.end_char is None:
        return ExtractionIssueCode.EVIDENCE_OFFSETS_UNRECOVERABLE
    if source_text[evidence.start_char : evidence.end_char] != evidence.text:
        return ExtractionIssueCode.EVIDENCE_OFFSETS_UNRECOVERABLE
    if set(evidence.mention_ids) - mention_ids:
        return ExtractionIssueCode.EVIDENCE_UNKNOWN_MENTION
    return None


def _claim_issue(
    *,
    object_type: str,
    object_id: str | None,
    stage: IssueStage,
    code: ExtractionIssueCode,
    severity: IssueSeverity = IssueSeverity.ERROR,
    recoverable: bool = False,
    related_ids: list[str] | None = None,
) -> ClaimModelIssue:
    return ExtractionIssue.create(
        object_type=object_type,
        object_id=object_id,
        stage=stage,
        code=code,
        severity=severity,
        recoverable=recoverable,
        related_ids=related_ids,
    )


def _infer_person_evidence_class(
    person: PersonMention,
    *,
    transcript: TranscriptEnvelope,
    speaker_name: str,
) -> EvidenceClass:
    if person.uncertainty is not None:
        return EvidenceClass.U_UNCERTAIN
    source_text = joined_segment_text(person.source_segment_ids, transcript)
    surfaces = person_name_surfaces(person)
    if any(contains_exact_surface(source_text, surface) for surface in surfaces):
        return EvidenceClass.A_EXPLICIT
    if any(contains_surface(source_text, surface) for surface in surfaces):
        return EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT
    if normalize_evidence(person.name) == normalize_evidence(speaker_name):
        if has_first_person_reference(source_text):
            return EvidenceClass.C_SPEAKER_ANCHORED
    if person.assertion_mode is AssertionMode.INFERRED:
        return EvidenceClass.E_INFERRED
    return EvidenceClass.U_UNCERTAIN


def _infer_relationship_evidence_class(
    relationship: RelationshipClaim,
    *,
    transcript: TranscriptEnvelope,
    people: list[PersonMention],
    speaker_name: str,
    coreference_by_id: dict[str, CoreferenceLink],
) -> EvidenceClass:
    if not relationship_is_active_candidate(relationship):
        return EvidenceClass.U_UNCERTAIN
    analysis = analyze_relationship_evidence(
        relationship=relationship,
        transcript=transcript,
        people=people,
        speaker_name=speaker_name,
    )
    if analysis.evidence_class in {
        EvidenceClass.A_EXPLICIT.value,
        EvidenceClass.B_MORPHOLOGICALLY_EXPLICIT.value,
        EvidenceClass.C_SPEAKER_ANCHORED.value,
    }:
        return EvidenceClass(analysis.evidence_class)

    resolved_antecedents = {
        mention_id
        for coreference_id in relationship.coreference_link_ids
        if (link := coreference_by_id.get(coreference_id)) is not None
        and link.status is CoreferenceStatus.RESOLVED
        for mention_id in link.antecedent_mention_ids
    }
    if analysis.unsupported_endpoint_ids and set(analysis.unsupported_endpoint_ids).issubset(
        resolved_antecedents
    ):
        return EvidenceClass.D_CONTEXT_RESOLVED
    if relationship.assertion_mode is AssertionMode.INFERRED:
        return EvidenceClass.E_INFERRED
    return EvidenceClass.U_UNCERTAIN


def _infer_generic_evidence_class(item: EvidenceBackedObject) -> EvidenceClass:
    if item.uncertainty is not None:
        return EvidenceClass.U_UNCERTAIN
    assertion_mode = getattr(item, "assertion_mode", None)
    if assertion_mode is AssertionMode.EXPLICIT:
        return EvidenceClass.A_EXPLICIT
    if assertion_mode is AssertionMode.INFERRED:
        return EvidenceClass.E_INFERRED
    return EvidenceClass.U_UNCERTAIN


def _mention_ids_for_object(
    object_type: ClaimObjectType,
    object_id: str,
    item: EvidenceBackedObject,
) -> list[str]:
    if object_type is ClaimObjectType.PERSON_MENTION:
        return [object_id]
    if isinstance(item, RelationshipClaim):
        return [item.subject_mention_id, item.object_mention_id]
    if isinstance(item, FamilyEvent):
        return list(item.participant_mention_ids)
    if isinstance(item, PersonDescription):
        return [item.person_mention_id]
    if isinstance(item, Story):
        return list(item.person_mention_ids)
    if isinstance(item, UnresolvedQuestion):
        return list(item.related_mention_ids)
    raise ValueError(f"unsupported evidence-backed object {type(item).__name__}")


def _generated_evidence(
    *,
    object_type: ClaimObjectType,
    object_id: str,
    item: EvidenceBackedObject,
    evidence_class: EvidenceClass,
    transcript: TranscriptEnvelope,
    sanitizer_activity_id: str,
) -> list[EvidenceSpan]:
    segment_by_id = {segment.segment_id: segment for segment in transcript.segments}
    purpose = (
        EvidencePurpose.IDENTITY
        if object_type is ClaimObjectType.PERSON_MENTION
        else EvidencePurpose.CLAIM
    )
    mention_ids = _mention_ids_for_object(object_type, object_id, item)
    generated: list[EvidenceSpan] = []
    for segment_id in _ordered_segment_ids(item.source_segment_ids, transcript):
        segment = segment_by_id[segment_id]
        generated.append(
            EvidenceSpan(
                evidence_id=(
                    f"evidence_{object_type.value}_{_safe_id(object_id)}_{_safe_id(segment_id)}"
                ),
                segment_id=segment_id,
                text=segment.text,
                source_layer=EvidenceSourceLayer.RAW_TRANSCRIPT,
                start_char=0,
                end_char=len(segment.text),
                evidence_class=evidence_class,
                purposes=[purpose],
                mention_ids=list(dict.fromkeys(mention_ids)),
                created_by_activity_id=sanitizer_activity_id,
                confidence=cast(float, getattr(item, "confidence", 1.0)),
            )
        )
    return generated


def _weakest_evidence_class(
    evidence_ids: list[str],
    evidence_by_id: dict[str, EvidenceSpan],
    fallback: EvidenceClass,
) -> EvidenceClass:
    classes = [
        evidence_by_id[item].evidence_class for item in evidence_ids if item in evidence_by_id
    ]
    classes.append(fallback)
    return max(classes, key=_EVIDENCE_CLASS_RANK.__getitem__)


def _raw_supported_surface(surface: str, evidence_text: str) -> str | None:
    target = normalize_evidence(surface)
    if not target:
        return None
    for match in re.finditer(r"[\w-]+", evidence_text, flags=re.UNICODE):
        candidate = match.group(0)
        if normalize_evidence(candidate) == target:
            return candidate
    return None


_ALIAS_CUE_PATTERN = re.compile(
    r"(?:по\s+прозвищу|прозвище|также\s+звал(?:и|ся|ась)|называл(?:и|ся|ась)|"
    r"лақап\s+ат(?:ы|ы)?|деп\s+атайтын|екінші\s+аты|also\s+known\s+as|"
    r"nicknamed|called)",
    flags=re.IGNORECASE | re.UNICODE,
)

_FAMILY_CUE_PATTERN = re.compile(
    r"(?:отец|мать|папа|мама|сын|дочь|брат|сестра|муж|жена|супруг|супруга|"
    r"әке|ана|апа|аға|іні|әпке|қарындас|сіңлі|ұл|қыз|күйеу|әйел|"
    r"father|mother|son|daughter|brother|sister|husband|wife|spouse)",
    flags=re.IGNORECASE | re.UNICODE,
)
_NON_FAMILY_CUES: dict[PersonCategory, re.Pattern[str]] = {
    PersonCategory.FRIEND: re.compile(r"(?:друг|подруга|дос|құрбы|friend)", re.I),
    PersonCategory.ROOMMATE: re.compile(r"(?:сосед\s+по\s+комнате|бөлмелес|roommate)", re.I),
    PersonCategory.ACQUAINTANCE: re.compile(r"(?:знаком(?:ый|ая)|таныс|acquaintance)", re.I),
}


def _alias_link_supported(alias: str, primary_name: str, evidence_text: str) -> bool:
    supported_alias = _raw_supported_surface(alias, evidence_text)
    if supported_alias is None:
        return False
    alias_matches = list(
        re.finditer(re.escape(supported_alias), evidence_text, flags=re.IGNORECASE)
    )
    cue_matches = list(_ALIAS_CUE_PATTERN.finditer(evidence_text))
    if not alias_matches or not cue_matches:
        return False

    def directly_linked(alias_match: re.Match[str], cue_match: re.Match[str]) -> bool:
        if cue_match.end() <= alias_match.start():
            between = evidence_text[cue_match.end() : alias_match.start()]
        elif alias_match.end() <= cue_match.start():
            between = evidence_text[alias_match.end() : cue_match.start()]
        else:
            return True
        # Alias cues license only the immediately adjacent surface, never another name later in
        # the same sentence or segment.
        words = re.findall(r"[\w-]+", between, flags=re.UNICODE)
        return len(between) <= 32 and len(words) <= 1

    if not any(
        directly_linked(alias_match, cue_match)
        for alias_match in alias_matches
        for cue_match in cue_matches
    ):
        return False
    return contains_surface(evidence_text, primary_name) or normalize_evidence(
        primary_name
    ) == normalize_evidence(alias)


def _person_has_grounded_family_link(
    person: PersonMention,
    *,
    relationships: list[RelationshipClaim],
    speaker_name: str,
    people_by_id: dict[str, PersonMention],
) -> bool:
    speaker_ids = {
        candidate.mention_id
        for candidate in people_by_id.values()
        if normalize_evidence(candidate.name) == normalize_evidence(speaker_name)
    }
    for relationship in relationships:
        endpoints = {relationship.subject_mention_id, relationship.object_mention_id}
        if person.mention_id in endpoints and endpoints.intersection(speaker_ids):
            return True
    return False


def _harden_person_fields(
    people: list[PersonMention],
    *,
    relationships: list[RelationshipClaim],
    evidence_by_id: dict[str, EvidenceSpan],
    speaker_name: str,
) -> tuple[list[PersonMention], list[ClaimModelIssue]]:
    people_by_id = {person.mention_id: person for person in people}
    hardened: list[PersonMention] = []
    issues: list[ClaimModelIssue] = []
    for person in people:
        evidence_text = " ".join(
            evidence_by_id[evidence_id].text
            for evidence_id in person.evidence_ids
            if evidence_id in evidence_by_id
        )
        is_speaker = normalize_evidence(person.name) == normalize_evidence(speaker_name)
        speaker_family_link = _person_has_grounded_family_link(
            person,
            relationships=relationships,
            speaker_name=speaker_name,
            people_by_id=people_by_id,
        )
        any_family_link = any(
            person.mention_id in {relationship.subject_mention_id, relationship.object_mention_id}
            for relationship in relationships
        )
        relation_supported = (
            person.relation_to_speaker is None
            or (
                person.relation_to_speaker.casefold() == "self"
                and is_speaker
                and has_first_person_reference(evidence_text)
            )
            or speaker_family_link
        )
        relation = person.relation_to_speaker if relation_supported else None
        if person.relation_to_speaker is not None and relation is None:
            issues.append(
                _claim_issue(
                    object_type=ClaimObjectType.PERSON_MENTION.value,
                    object_id=person.mention_id,
                    stage=IssueStage.SEMANTIC,
                    code=ExtractionIssueCode.PERSON_RELATION_REMOVED,
                    severity=IssueSeverity.WARNING,
                    recoverable=True,
                )
            )

        category_supported = person.category is PersonCategory.UNKNOWN
        if person.category is PersonCategory.FAMILY_MEMBER:
            category_supported = (
                is_speaker or any_family_link or bool(_FAMILY_CUE_PATTERN.search(evidence_text))
            )
        elif person.category in _NON_FAMILY_CUES:
            category_supported = bool(_NON_FAMILY_CUES[person.category].search(evidence_text))
        elif person.category is PersonCategory.OTHER_NON_FAMILY:
            category_supported = any(
                pattern.search(evidence_text) for pattern in _NON_FAMILY_CUES.values()
            )
        category = person.category if category_supported else PersonCategory.UNKNOWN
        if category is not person.category:
            issues.append(
                _claim_issue(
                    object_type=ClaimObjectType.PERSON_MENTION.value,
                    object_id=person.mention_id,
                    stage=IssueStage.SEMANTIC,
                    code=ExtractionIssueCode.PERSON_CATEGORY_DOWNGRADED,
                    severity=IssueSeverity.WARNING,
                    recoverable=True,
                )
            )
        hardened.append(
            person.model_copy(update={"relation_to_speaker": relation, "category": category})
        )
    return hardened, issues


def _raw_inflected_surface(surface: str, evidence_text: str) -> str | None:
    matches = find_known_name_matches(evidence_text, surface)
    if not matches:
        return None
    selected = min(matches, key=lambda item: (item.start < 0, item.start, item.end))
    if 0 <= selected.start < selected.end <= len(evidence_text):
        return evidence_text[selected.start : selected.end]
    return selected.token


def _materialize_name_variants(
    person: PersonMention,
    *,
    evidence_ids: list[str],
    evidence_by_id: dict[str, EvidenceSpan],
    speaker_name: str,
) -> list[NameVariant]:
    variants: list[NameVariant] = []
    seen: set[tuple[str, NameVariantType]] = set()
    person_segments = set(person.source_segment_ids)
    evidence_text = " ".join(
        evidence_by_id[item].text for item in evidence_ids if item in evidence_by_id
    )
    speaker_primary = normalize_evidence(person.name) == normalize_evidence(speaker_name)

    def append_variant(
        *,
        variant_id: str,
        surface: str,
        variant_type: NameVariantType,
        source_segment_ids: list[str],
        variant_evidence_ids: list[str],
        confidence: float,
        language: str | None = None,
        script: str | None = None,
    ) -> None:
        normalized = normalize_evidence(surface)
        key = (normalized, variant_type)
        if not normalized or key in seen:
            return
        seen.add(key)
        variants.append(
            NameVariant(
                variant_id=variant_id,
                surface=surface,
                normalized=normalized,
                variant_type=variant_type,
                language=language,
                script=script,
                source_segment_ids=source_segment_ids,
                evidence_ids=variant_evidence_ids,
                confidence=confidence,
                verification_status=VerificationStatus.UNREVIEWED,
            )
        )

    for candidate in person.name_variants:
        candidate_segments = [
            item for item in candidate.source_segment_ids if item in person_segments
        ]
        candidate_evidence = [item for item in candidate.evidence_ids if item in evidence_by_id]
        if not candidate_segments or not candidate_evidence:
            continue
        cited_text = " ".join(evidence_by_id[item].text for item in candidate_evidence)
        supported_surface = _raw_supported_surface(candidate.surface, cited_text)
        if supported_surface is None:
            continue
        if candidate.variant_type in {
            NameVariantType.EXPLICIT_ALIAS,
            NameVariantType.NICKNAME,
        } and not _alias_link_supported(candidate.surface, person.name, cited_text):
            continue
        append_variant(
            variant_id=candidate.variant_id,
            surface=supported_surface,
            variant_type=candidate.variant_type,
            source_segment_ids=candidate_segments,
            variant_evidence_ids=candidate_evidence,
            confidence=candidate.confidence,
            language=candidate.language,
            script=candidate.script,
        )

    raw_primary = _raw_inflected_surface(person.name, evidence_text)
    if raw_primary is not None or speaker_primary:
        append_variant(
            variant_id=f"variant_{_safe_id(person.mention_id)}_primary",
            surface=person.name,
            variant_type=NameVariantType.PRIMARY,
            source_segment_ids=list(person.source_segment_ids),
            variant_evidence_ids=list(evidence_ids),
            confidence=person.confidence,
        )
        if raw_primary is not None and normalize_evidence(raw_primary) != normalize_evidence(
            person.name
        ):
            append_variant(
                variant_id=f"variant_{_safe_id(person.mention_id)}_inflected",
                surface=raw_primary,
                variant_type=NameVariantType.INFLECTED_FORM,
                source_segment_ids=list(person.source_segment_ids),
                variant_evidence_ids=list(evidence_ids),
                confidence=person.confidence,
            )

    for index, alias in enumerate(person.aliases, start=1):
        supported_alias = _raw_supported_surface(alias, evidence_text)
        if supported_alias is None or not _alias_link_supported(alias, person.name, evidence_text):
            continue
        append_variant(
            variant_id=f"variant_{_safe_id(person.mention_id)}_alias_{index:03d}",
            surface=supported_alias,
            variant_type=NameVariantType.EXPLICIT_ALIAS,
            source_segment_ids=list(person.source_segment_ids),
            variant_evidence_ids=list(evidence_ids),
            confidence=person.confidence,
        )
    return variants


def _filter_evidence_derivations(
    evidence_by_id: dict[str, EvidenceSpan],
) -> tuple[dict[str, EvidenceSpan], list[ClaimModelIssue]]:
    issues: list[ClaimModelIssue] = []
    invalid_ids: set[str] = set()
    all_ids = set(evidence_by_id)
    for evidence in evidence_by_id.values():
        unknown = set(evidence.derived_from_evidence_ids) - all_ids
        if unknown:
            invalid_ids.add(evidence.evidence_id)
            issues.append(
                _claim_issue(
                    object_type="evidence",
                    object_id=evidence.evidence_id,
                    stage=IssueStage.PROVENANCE,
                    code=ExtractionIssueCode.EVIDENCE_DERIVATION_UNKNOWN,
                    related_ids=sorted(unknown),
                )
            )

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(evidence_id: str) -> None:
        if evidence_id in invalid_ids:
            return
        current = state.get(evidence_id, 0)
        if current == 2:
            return
        if current == 1:
            if evidence_id in stack:
                invalid_ids.update(stack[stack.index(evidence_id) :])
            return
        state[evidence_id] = 1
        stack.append(evidence_id)
        for parent_id in evidence_by_id[evidence_id].derived_from_evidence_ids:
            if parent_id in evidence_by_id:
                visit(parent_id)
        stack.pop()
        state[evidence_id] = 2

    for evidence_id in list(evidence_by_id):
        visit(evidence_id)

    cycle_ids = {
        evidence_id
        for evidence_id in invalid_ids
        if not (set(evidence_by_id[evidence_id].derived_from_evidence_ids) - all_ids)
    }
    for evidence_id in sorted(cycle_ids):
        issues.append(
            _claim_issue(
                object_type="evidence",
                object_id=evidence_id,
                stage=IssueStage.PROVENANCE,
                code=ExtractionIssueCode.EVIDENCE_DERIVATION_CYCLE,
            )
        )
    return (
        {key: value for key, value in evidence_by_id.items() if key not in invalid_ids},
        issues,
    )


def _filter_coreference_links(
    links: list[CoreferenceLink],
    *,
    transcript: TranscriptEnvelope,
    people_by_id: dict[str, PersonMention],
    speaker_name: str,
    evidence_by_id: dict[str, EvidenceSpan],
) -> tuple[list[CoreferenceLink], list[ClaimModelIssue]]:
    valid_segments = {segment.segment_id for segment in transcript.segments}
    mention_ids = set(people_by_id)
    segment_text_by_id = {segment.segment_id: segment.text for segment in transcript.segments}
    accepted: list[CoreferenceLink] = []
    issues: list[ClaimModelIssue] = []
    for link in links:
        unknown_segments = set(link.source_segment_ids) - valid_segments
        unknown_evidence = set(link.evidence_ids) - set(evidence_by_id)
        unknown_mentions = (
            set(link.antecedent_mention_ids).union(link.candidate_mention_ids) - mention_ids
        )
        cited_evidence = [
            evidence_by_id[item] for item in link.evidence_ids if item in evidence_by_id
        ]
        evidence_segments = {evidence.segment_id for evidence in cited_evidence}
        anaphor_supported = any(link.anaphor_text in evidence.text for evidence in cited_evidence)
        code: ExtractionIssueCode | None = None
        if unknown_segments or unknown_evidence or unknown_mentions:
            code = ExtractionIssueCode.COREFERENCE_REFERENCE_INVALID
        elif not evidence_segments.issubset(link.source_segment_ids):
            code = ExtractionIssueCode.COREFERENCE_REFERENCE_INVALID
        elif not anaphor_supported:
            code = ExtractionIssueCode.COREFERENCE_ANAPHOR_UNSUPPORTED
        elif link.status is CoreferenceStatus.RESOLVED:
            source_text = " ".join(
                segment_text_by_id[segment_id]
                for segment_id in link.source_segment_ids
                if segment_id in segment_text_by_id
            )
            unsupported_antecedents = []
            for mention_id in link.antecedent_mention_ids:
                person = people_by_id[mention_id]
                # Coreference authority must not be bootstrapped from unvalidated model
                # aliases. At this stage person aliases/name variants have not yet passed
                # evidence-local hardening, so only the primary raw name may ground an
                # antecedent. Validated variants can be added later by deterministic
                # augmentation, never by trusting the same candidate link.
                explicitly_named = contains_surface(source_text, person.name)
                speaker_anchored = (
                    link.method.value == "speaker_anchor"
                    and normalize_evidence(person.name) == normalize_evidence(speaker_name)
                    and has_first_person_reference(source_text)
                )
                if not explicitly_named and not speaker_anchored:
                    unsupported_antecedents.append(mention_id)
            if unsupported_antecedents:
                code = ExtractionIssueCode.COREFERENCE_REFERENCE_INVALID
        if code is not None:
            issues.append(
                _claim_issue(
                    object_type="coreference",
                    object_id=link.coreference_id,
                    stage=IssueStage.COREFERENCE,
                    code=code,
                )
            )
            continue
        accepted.append(
            link.model_copy(update={"verification_status": VerificationStatus.UNREVIEWED})
        )
    return accepted, issues


def _materialize_item(
    item: ObjectT,
    *,
    evidence_class: EvidenceClass,
    transcript: TranscriptEnvelope,
    speaker_id: str,
    speaker_name: str,
    evidence_by_id: dict[str, EvidenceSpan],
    coreference_by_id: dict[str, CoreferenceLink],
    extractor_activity_id: str,
    sanitizer_activity_id: str,
) -> tuple[ObjectT | None, list[ClaimModelIssue]]:
    object_type, object_id = _object_identity(item)
    issues: list[ClaimModelIssue] = []
    valid_evidence_ids = [
        evidence_id
        for evidence_id in item.evidence_ids
        if evidence_id in evidence_by_id
        and evidence_by_id[evidence_id].segment_id in item.source_segment_ids
    ]
    invalid_evidence_ids = sorted(set(item.evidence_ids) - set(valid_evidence_ids))
    if invalid_evidence_ids:
        issues.append(
            _claim_issue(
                object_type=object_type.value,
                object_id=object_id,
                stage=IssueStage.PROVENANCE,
                code=ExtractionIssueCode.OBJECT_UNKNOWN_EVIDENCE,
                related_ids=invalid_evidence_ids,
            )
        )

    if not valid_evidence_ids:
        # Backward-compatible deterministic closure is limited to people and already-grounded
        # relationships. Generic facts are never licensed by a whole-segment fallback.
        if not isinstance(item, (PersonMention, RelationshipClaim)):
            issues.append(
                _claim_issue(
                    object_type=object_type.value,
                    object_id=object_id,
                    stage=IssueStage.PROVENANCE,
                    code=ExtractionIssueCode.OBJECT_MISSING_EVIDENCE,
                )
            )
            return None, issues
        generated = _generated_evidence(
            object_type=object_type,
            object_id=object_id,
            item=item,
            evidence_class=evidence_class,
            transcript=transcript,
            sanitizer_activity_id=sanitizer_activity_id,
        )
        valid_evidence_ids = [evidence.evidence_id for evidence in generated]
        evidence_by_id.update({evidence.evidence_id: evidence for evidence in generated})

    valid_coreference_ids = [
        link_id for link_id in item.coreference_link_ids if link_id in coreference_by_id
    ]
    invalid_coreference_ids = sorted(set(item.coreference_link_ids) - set(valid_coreference_ids))
    if invalid_coreference_ids:
        issues.append(
            _claim_issue(
                object_type=object_type.value,
                object_id=object_id,
                stage=IssueStage.COREFERENCE,
                code=ExtractionIssueCode.COREFERENCE_REFERENCE_INVALID,
                related_ids=invalid_coreference_ids,
            )
        )

    derived_claim_ids = (
        list(item.provenance.derived_from_claim_ids) if item.provenance is not None else []
    )
    if object_id in derived_claim_ids:
        derived_claim_ids = [value for value in derived_claim_ids if value != object_id]
        issues.append(
            _claim_issue(
                object_type=object_type.value,
                object_id=object_id,
                stage=IssueStage.PROVENANCE,
                code=ExtractionIssueCode.DERIVED_CLAIM_SELF_REFERENCE,
                recoverable=True,
            )
        )
    deduped_derived = list(dict.fromkeys(derived_claim_ids))
    if deduped_derived != derived_claim_ids:
        issues.append(
            _claim_issue(
                object_type=object_type.value,
                object_id=object_id,
                stage=IssueStage.PROVENANCE,
                code=ExtractionIssueCode.DERIVED_CLAIM_DUPLICATE,
                recoverable=True,
            )
        )

    final_class = _weakest_evidence_class(valid_evidence_ids, evidence_by_id, evidence_class)
    provenance = ClaimProvenance(
        recording_id=transcript.recording_id,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        generated_by_activity_id=extractor_activity_id,
        validated_by_activity_ids=[sanitizer_activity_id],
        evidence_ids=list(valid_evidence_ids),
        derived_from_claim_ids=deduped_derived,
        pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
    )
    update: dict[str, Any] = {
        "evidence_ids": valid_evidence_ids,
        "evidence_class": final_class,
        "coreference_link_ids": valid_coreference_ids,
        "provenance": provenance,
    }
    if hasattr(item, "verification_status"):
        update["verification_status"] = VerificationStatus.UNREVIEWED
    if item.uncertainty is not None:
        update["uncertainty"] = item.uncertainty.model_copy(
            update={
                "source_segment_ids": list(item.source_segment_ids),
                "evidence_ids": list(valid_evidence_ids),
            }
        )
    if isinstance(item, RelationshipClaim):
        update["state_evidence_ids"] = list(valid_evidence_ids)
    if isinstance(item, FamilyEvent) and item.date is not None:
        update["date"] = item.date.model_copy(
            update={
                "source_evidence_ids": list(valid_evidence_ids),
                "verification_status": VerificationStatus.UNREVIEWED,
            }
        )
    if isinstance(item, PersonMention):
        variants = _materialize_name_variants(
            item,
            evidence_ids=valid_evidence_ids,
            evidence_by_id=evidence_by_id,
            speaker_name=speaker_name,
        )
        supported_aliases = [
            variant.surface
            for variant in variants
            if variant.variant_type in {NameVariantType.EXPLICIT_ALIAS, NameVariantType.NICKNAME}
        ]
        if item.aliases and len(supported_aliases) < len(item.aliases):
            issues.append(
                _claim_issue(
                    object_type=object_type.value,
                    object_id=object_id,
                    stage=IssueStage.SEMANTIC,
                    code=ExtractionIssueCode.PERSON_ALIAS_UNSUPPORTED,
                    severity=IssueSeverity.WARNING,
                    recoverable=True,
                )
            )
        update["aliases"] = list(dict.fromkeys(supported_aliases))
        update["name_variants"] = variants
    return item.model_copy(update=update), issues


def _claim_ref_index(
    result: ExtractionResult,
) -> dict[tuple[ClaimObjectType, str], EvidenceBackedObject]:
    return {_object_identity(item): item for item in _objects(result)}


def _filter_conflicts(
    conflicts: list[ConflictSet],
    *,
    result: ExtractionResult,
    evidence_ids: set[str],
) -> tuple[list[ConflictSet], list[ClaimModelIssue]]:
    claim_index = _claim_ref_index(result)
    accepted: list[ConflictSet] = []
    issues: list[ClaimModelIssue] = []
    for conflict in conflicts:
        unknown_claims = [
            ref.object_id
            for ref in conflict.claim_refs
            if (ref.object_type, ref.object_id) not in claim_index
        ]
        if unknown_claims:
            issues.append(
                _claim_issue(
                    object_type="conflict",
                    object_id=conflict.conflict_id,
                    stage=IssueStage.SEMANTIC,
                    code=ExtractionIssueCode.CONFLICT_REFERENCE_INVALID,
                    related_ids=unknown_claims,
                )
            )
            continue
        resolved_evidence = [item for item in conflict.evidence_ids if item in evidence_ids]
        if not resolved_evidence:
            resolved_evidence = list(
                dict.fromkeys(
                    evidence_id
                    for ref in conflict.claim_refs
                    for evidence_id in claim_index[(ref.object_type, ref.object_id)].evidence_ids
                    if evidence_id in evidence_ids
                )
            )
        if not resolved_evidence:
            issues.append(
                _claim_issue(
                    object_type="conflict",
                    object_id=conflict.conflict_id,
                    stage=IssueStage.PROVENANCE,
                    code=ExtractionIssueCode.OBJECT_MISSING_EVIDENCE,
                )
            )
            continue
        accepted.append(
            conflict.model_copy(
                update={
                    "evidence_ids": resolved_evidence,
                    "verification_status": VerificationStatus.UNREVIEWED,
                }
            )
        )
    return accepted, issues


def _attach_conflict_ids(
    items: list[ObjectT],
    mapping: dict[tuple[ClaimObjectType, str], list[str]],
) -> list[ObjectT]:
    return [
        item.model_copy(update={"conflict_ids": mapping.get(_object_identity(item), [])})
        for item in items
    ]


def _sync_conflict_ids(
    result: ExtractionResult,
    conflicts: list[ConflictSet],
) -> ExtractionResult:
    conflict_ids_by_claim: dict[tuple[ClaimObjectType, str], list[str]] = {}
    for conflict in conflicts:
        for ref in conflict.claim_refs:
            conflict_ids_by_claim.setdefault((ref.object_type, ref.object_id), []).append(
                conflict.conflict_id
            )
    return result.model_copy(
        update={
            "people_mentions": _attach_conflict_ids(
                list(result.people_mentions), conflict_ids_by_claim
            ),
            "relationship_claims": _attach_conflict_ids(
                list(result.relationship_claims), conflict_ids_by_claim
            ),
            "events": _attach_conflict_ids(list(result.events), conflict_ids_by_claim),
            "descriptions": _attach_conflict_ids(list(result.descriptions), conflict_ids_by_claim),
            "stories": _attach_conflict_ids(list(result.stories), conflict_ids_by_claim),
            "unresolved_questions": _attach_conflict_ids(
                list(result.unresolved_questions), conflict_ids_by_claim
            ),
            "conflict_sets": conflicts,
        }
    )


def _materialize_generic_items(
    items: list[ObjectT],
    *,
    transcript: TranscriptEnvelope,
    result: ExtractionResult,
    evidence_by_id: dict[str, EvidenceSpan],
    coreference_by_id: dict[str, CoreferenceLink],
    extractor_activity_id: str,
    sanitizer_activity_id: str,
) -> tuple[list[ObjectT], list[ClaimModelIssue]]:
    materialized: list[ObjectT] = []
    issues: list[ClaimModelIssue] = []
    for candidate in items:
        item, item_issues = _materialize_item(
            candidate,
            evidence_class=_infer_generic_evidence_class(candidate),
            transcript=transcript,
            speaker_id=result.speaker_id,
            speaker_name=result.speaker_name,
            evidence_by_id=evidence_by_id,
            coreference_by_id=coreference_by_id,
            extractor_activity_id=extractor_activity_id,
            sanitizer_activity_id=sanitizer_activity_id,
        )
        if item is not None:
            materialized.append(item)
        issues.extend(item_issues)
    return materialized, issues


def materialize_extraction_contract_v2(
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
    *,
    cleaned: CleanerResult | None = None,
) -> tuple[ExtractionResult, list[ClaimModelIssue]]:
    """Attach authoritative provenance while preserving valid model-proposed metadata."""

    issues: list[ClaimModelIssue] = []
    if result.provenance_activities:
        issues.append(
            _claim_issue(
                object_type="provenance_activity",
                object_id=None,
                stage=IssueStage.PROVENANCE,
                code=ExtractionIssueCode.MODEL_PROVENANCE_REPLACED,
                severity=IssueSeverity.WARNING,
                recoverable=True,
            )
        )

    mention_ids = {person.mention_id for person in result.people_mentions}
    activities, extractor_activity_id, sanitizer_activity_id = _authoritative_activities(transcript)
    evidence_by_id: dict[str, EvidenceSpan] = {}
    for evidence in result.evidence_spans:
        code = _validate_candidate_evidence(
            evidence,
            transcript=transcript,
            mention_ids=mention_ids,
            cleaned=cleaned,
        )
        if code is not None:
            issues.append(
                _claim_issue(
                    object_type="evidence",
                    object_id=evidence.evidence_id,
                    stage=IssueStage.PROVENANCE,
                    code=code,
                )
            )
            continue
        evidence_by_id[evidence.evidence_id] = evidence.model_copy(
            update={
                "created_by_activity_id": extractor_activity_id,
                "derived_from_evidence_ids": list(
                    dict.fromkeys(evidence.derived_from_evidence_ids)
                ),
            }
        )

    evidence_by_id, derivation_issues = _filter_evidence_derivations(evidence_by_id)
    issues.extend(derivation_issues)

    coreference_links, coreference_issues = _filter_coreference_links(
        result.coreference_links,
        transcript=transcript,
        people_by_id={person.mention_id: person for person in result.people_mentions},
        speaker_name=result.speaker_name,
        evidence_by_id=evidence_by_id,
    )
    issues.extend(coreference_issues)
    coreference_by_id = {item.coreference_id: item for item in coreference_links}

    people: list[PersonMention] = []
    for person in result.people_mentions:
        materialized_person, item_issues = _materialize_item(
            person,
            evidence_class=_infer_person_evidence_class(
                person,
                transcript=transcript,
                speaker_name=result.speaker_name,
            ),
            transcript=transcript,
            speaker_id=result.speaker_id,
            speaker_name=result.speaker_name,
            evidence_by_id=evidence_by_id,
            coreference_by_id=coreference_by_id,
            extractor_activity_id=extractor_activity_id,
            sanitizer_activity_id=sanitizer_activity_id,
        )
        if materialized_person is not None:
            people.append(materialized_person)
        issues.extend(item_issues)

    relationships: list[RelationshipClaim] = []
    for relationship in result.relationship_claims:
        materialized_relationship, item_issues = _materialize_item(
            relationship,
            evidence_class=_infer_relationship_evidence_class(
                relationship,
                transcript=transcript,
                people=list(result.people_mentions),
                speaker_name=result.speaker_name,
                coreference_by_id=coreference_by_id,
            ),
            transcript=transcript,
            speaker_id=result.speaker_id,
            speaker_name=result.speaker_name,
            evidence_by_id=evidence_by_id,
            coreference_by_id=coreference_by_id,
            extractor_activity_id=extractor_activity_id,
            sanitizer_activity_id=sanitizer_activity_id,
        )
        if materialized_relationship is not None:
            relationships.append(materialized_relationship)
        issues.extend(item_issues)

    people, person_field_issues = _harden_person_fields(
        people,
        relationships=relationships,
        evidence_by_id=evidence_by_id,
        speaker_name=result.speaker_name,
    )
    issues.extend(person_field_issues)

    events, event_issues = _materialize_generic_items(
        list(result.events),
        transcript=transcript,
        result=result,
        evidence_by_id=evidence_by_id,
        coreference_by_id=coreference_by_id,
        extractor_activity_id=extractor_activity_id,
        sanitizer_activity_id=sanitizer_activity_id,
    )
    descriptions, description_issues = _materialize_generic_items(
        list(result.descriptions),
        transcript=transcript,
        result=result,
        evidence_by_id=evidence_by_id,
        coreference_by_id=coreference_by_id,
        extractor_activity_id=extractor_activity_id,
        sanitizer_activity_id=sanitizer_activity_id,
    )
    stories, story_issues = _materialize_generic_items(
        list(result.stories),
        transcript=transcript,
        result=result,
        evidence_by_id=evidence_by_id,
        coreference_by_id=coreference_by_id,
        extractor_activity_id=extractor_activity_id,
        sanitizer_activity_id=sanitizer_activity_id,
    )
    questions, question_issues = _materialize_generic_items(
        list(result.unresolved_questions),
        transcript=transcript,
        result=result,
        evidence_by_id=evidence_by_id,
        coreference_by_id=coreference_by_id,
        extractor_activity_id=extractor_activity_id,
        sanitizer_activity_id=sanitizer_activity_id,
    )
    issues.extend(event_issues)
    issues.extend(description_issues)
    issues.extend(story_issues)
    issues.extend(question_issues)

    updated = result.model_copy(
        update={
            "schema_version": "extraction-v2",
            "provenance_activities": activities,
            "evidence_spans": list(evidence_by_id.values()),
            "coreference_links": coreference_links,
            "people_mentions": people,
            "relationship_claims": relationships,
            "events": events,
            "descriptions": descriptions,
            "stories": stories,
            "unresolved_questions": questions,
        }
    )
    conflicts, conflict_issues = _filter_conflicts(
        result.conflict_sets,
        result=updated,
        evidence_ids=set(evidence_by_id),
    )
    issues.extend(conflict_issues)
    return _sync_conflict_ids(updated, conflicts), issues


def close_extraction_conflicts(
    result: ExtractionResult,
) -> tuple[ExtractionResult, list[ClaimModelIssue]]:
    """Drop conflicts whose claim/evidence references no longer survive object quarantine."""

    conflicts, issues = _filter_conflicts(
        list(result.conflict_sets),
        result=result,
        evidence_ids={item.evidence_id for item in result.evidence_spans},
    )
    return _sync_conflict_ids(result, conflicts), issues


def validate_extraction_contract_v2(
    transcript: TranscriptEnvelope,
    result: ExtractionResult,
    *,
    cleaned: CleanerResult | None = None,
) -> None:
    if result.schema_version != "extraction-v2":
        return

    activity_ids = {activity.activity_id for activity in result.provenance_activities}
    evidence_by_id = {evidence.evidence_id: evidence for evidence in result.evidence_spans}
    coreference_by_id = {item.coreference_id: item for item in result.coreference_links}
    conflict_by_id = {item.conflict_id: item for item in result.conflict_sets}
    mention_ids = {person.mention_id for person in result.people_mentions}

    if not activity_ids:
        raise ValueError("extraction-v2 requires provenance activities")
    if not evidence_by_id and _objects(result):
        raise ValueError("extraction-v2 objects require evidence spans")

    for evidence in result.evidence_spans:
        code = _validate_candidate_evidence(
            evidence,
            transcript=transcript,
            mention_ids=mention_ids,
            cleaned=cleaned,
        )
        if code is not None:
            raise ValueError(f"evidence {evidence.evidence_id} failed {code.value}")
        if evidence.created_by_activity_id not in activity_ids:
            raise ValueError(
                f"evidence {evidence.evidence_id} references an unknown provenance activity"
            )
        if set(evidence.derived_from_evidence_ids) - set(evidence_by_id):
            raise ValueError(f"evidence {evidence.evidence_id} references unknown derived evidence")

    filtered_evidence, derivation_issues = _filter_evidence_derivations(dict(evidence_by_id))
    if derivation_issues or set(filtered_evidence) != set(evidence_by_id):
        raise ValueError("evidence derivation graph is not closed and acyclic")

    for link in result.coreference_links:
        unknown_evidence = set(link.evidence_ids) - set(evidence_by_id)
        unknown_mentions = (
            set(link.antecedent_mention_ids).union(link.candidate_mention_ids) - mention_ids
        )
        if unknown_evidence:
            raise ValueError(
                f"coreference {link.coreference_id} references unknown evidence: "
                f"{sorted(unknown_evidence)}"
            )
        if unknown_mentions:
            raise ValueError(
                f"coreference {link.coreference_id} references unknown mentions: "
                f"{sorted(unknown_mentions)}"
            )
        if link.verification_status is not VerificationStatus.UNREVIEWED:
            raise ValueError(f"coreference {link.coreference_id} is not unreviewed")
        if not any(
            link.anaphor_text in evidence_by_id[evidence_id].text
            for evidence_id in link.evidence_ids
        ):
            raise ValueError(f"coreference {link.coreference_id} has synthetic anaphor evidence")

    claim_index = _claim_ref_index(result)
    for conflict in result.conflict_sets:
        for ref in conflict.claim_refs:
            if (ref.object_type, ref.object_id) not in claim_index:
                raise ValueError(
                    f"conflict {conflict.conflict_id} references unknown claim "
                    f"{ref.object_type.value}:{ref.object_id}"
                )
        unknown_evidence = set(conflict.evidence_ids) - set(evidence_by_id)
        if unknown_evidence:
            raise ValueError(
                f"conflict {conflict.conflict_id} references unknown evidence: "
                f"{sorted(unknown_evidence)}"
            )
        if not conflict.evidence_ids:
            raise ValueError(f"conflict {conflict.conflict_id} has no evidence")
        if conflict.verification_status is not VerificationStatus.UNREVIEWED:
            raise ValueError(f"conflict {conflict.conflict_id} is not unreviewed")

    for item in _objects(result):
        object_type, object_id = _object_identity(item)
        status = getattr(item, "verification_status", VerificationStatus.UNREVIEWED)
        if status is not VerificationStatus.UNREVIEWED:
            raise ValueError(f"{object_type.value} {object_id} is not unreviewed")
        if not item.evidence_ids:
            raise ValueError(f"{object_type.value} {object_id} has no evidence IDs")
        unknown_evidence = set(item.evidence_ids) - set(evidence_by_id)
        if unknown_evidence:
            raise ValueError(
                f"{object_type.value} {object_id} references unknown evidence: "
                f"{sorted(unknown_evidence)}"
            )
        evidence_segments = {evidence_by_id[item_id].segment_id for item_id in item.evidence_ids}
        if not evidence_segments.issubset(item.source_segment_ids):
            raise ValueError(
                f"{object_type.value} {object_id} evidence is outside source_segment_ids"
            )
        expected_class = _weakest_evidence_class(
            item.evidence_ids,
            evidence_by_id,
            item.evidence_class,
        )
        if item.evidence_class is not expected_class:
            raise ValueError(f"{object_type.value} {object_id} has inconsistent evidence class")
        if item.provenance is None:
            raise ValueError(f"{object_type.value} {object_id} has no provenance record")
        provenance = item.provenance
        if provenance.recording_id != result.recording_id:
            raise ValueError(f"{object_type.value} {object_id} has wrong provenance recording")
        narrator_mismatch = (
            provenance.speaker_id != result.speaker_id
            or provenance.speaker_name != result.speaker_name
        )
        if narrator_mismatch:
            raise ValueError(f"{object_type.value} {object_id} has wrong narrator provenance")
        if provenance.generated_by_activity_id not in activity_ids:
            raise ValueError(f"{object_type.value} {object_id} has unknown generation activity")
        if set(provenance.validated_by_activity_ids) - activity_ids:
            raise ValueError(f"{object_type.value} {object_id} has unknown validation activity")
        if provenance.evidence_ids != item.evidence_ids:
            raise ValueError(
                f"{object_type.value} {object_id} provenance evidence does not match claim"
            )
        if object_id in provenance.derived_from_claim_ids:
            raise ValueError(f"{object_type.value} {object_id} derives from itself")
        if len(provenance.derived_from_claim_ids) != len(set(provenance.derived_from_claim_ids)):
            raise ValueError(f"{object_type.value} {object_id} has duplicate derived claims")
        # derived_from_claim_ids may reference an immutable claim from an earlier recording.
        # This extraction can prove only local non-self-reference and uniqueness; archive-level
        # existence is validated by the archive boundary that owns historical claims.
        if set(item.coreference_link_ids) - set(coreference_by_id):
            raise ValueError(
                f"{object_type.value} {object_id} references unknown coreference links"
            )
        if set(item.conflict_ids) - set(conflict_by_id):
            raise ValueError(f"{object_type.value} {object_id} references unknown conflicts")
        for conflict_id in item.conflict_ids:
            conflict_keys = {
                (candidate.object_type, candidate.object_id)
                for candidate in conflict_by_id[conflict_id].claim_refs
            }
            if (object_type, object_id) not in conflict_keys:
                raise ValueError(
                    f"{object_type.value} {object_id} is not included in conflict {conflict_id}"
                )

    for person in result.people_mentions:
        if not person.name_variants:
            raise ValueError(f"person mention {person.mention_id} has no name variants")
        variant_ids = [variant.variant_id for variant in person.name_variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError(f"person mention {person.mention_id} has duplicate variant IDs")
        primary = [
            variant
            for variant in person.name_variants
            if variant.variant_type is NameVariantType.PRIMARY
            and variant.normalized == normalize_evidence(person.name)
        ]
        if not primary:
            raise ValueError(f"person mention {person.mention_id} has no primary name variant")
        for variant in person.name_variants:
            if not set(variant.source_segment_ids).issubset(person.source_segment_ids):
                raise ValueError(
                    f"name variant {variant.variant_id} is outside person source segments"
                )
            if set(variant.evidence_ids) - set(evidence_by_id):
                raise ValueError(f"name variant {variant.variant_id} references unknown evidence")
            if variant.verification_status is not VerificationStatus.UNREVIEWED:
                raise ValueError(f"name variant {variant.variant_id} is not unreviewed")
            cited_text = " ".join(
                evidence_by_id[evidence_id].text for evidence_id in variant.evidence_ids
            )
            speaker_primary = (
                variant.variant_type is NameVariantType.PRIMARY
                and normalize_evidence(variant.surface) == normalize_evidence(result.speaker_name)
            )
            supported = (
                contains_surface(cited_text, variant.surface)
                if variant.variant_type is NameVariantType.PRIMARY
                else variant.surface in cited_text
            )
            if not supported and not speaker_primary:
                raise ValueError(f"name variant {variant.variant_id} is unsupported")
