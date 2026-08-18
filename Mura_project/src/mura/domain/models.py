from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Privacy(StrEnum):
    PRIVATE = "private"
    FAMILY = "family"
    PUBLIC = "public"


class StorySensitivity(StrEnum):
    NORMAL = "normal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


class VerificationStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AssertionMode(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"


class EpistemicStatus(StrEnum):
    ASSERTED = "asserted"
    UNCERTAIN = "uncertain"
    REMEMBERED_IMPRECISELY = "remembered_imprecisely"
    REPORTED = "reported"
    COMPETING = "competing"
    UNRESOLVED = "unresolved"


class RelationshipState(StrEnum):
    CURRENT = "current"
    FORMER = "former"
    ENDED = "ended"
    NEGATED = "negated"
    FIGURATIVE = "figurative"
    UNRESOLVED = "unresolved"


class TemporalKind(StrEnum):
    EXACT_DATE = "exact_date"
    YEAR = "year"
    MONTH_YEAR = "month_year"
    APPROXIMATE = "approximate"
    RANGE = "range"
    DECADE = "decade"
    RELATIVE = "relative"
    UNKNOWN = "unknown"


class TemporalPrecision(StrEnum):
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    DECADE = "decade"
    RANGE = "range"
    UNKNOWN = "unknown"


class TemporalRelation(StrEnum):
    BEFORE = "before"
    AFTER = "after"
    BETWEEN = "between"
    AT_AGE = "at_age"


class ResolutionStatus(StrEnum):
    NEW_PERSON = "new_person"
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"


class CorrectionKind(StrEnum):
    ASR_NORMALIZATION = "asr_normalization"
    SPEAKER_SELF_CORRECTION = "speaker_self_correction"


class PersonCategory(StrEnum):
    FAMILY_MEMBER = "family_member"
    FRIEND = "friend"
    ROOMMATE = "roommate"
    ACQUAINTANCE = "acquaintance"
    OTHER_NON_FAMILY = "other_non_family"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    PARENT_CHILD = "parent_child"
    SPOUSE = "spouse"
    SIBLING = "sibling"


class RelationshipRole(StrEnum):
    PARENT = "parent"
    CHILD = "child"
    SPOUSE = "spouse"
    OLDER_SIBLING = "older_sibling"
    YOUNGER_SIBLING = "younger_sibling"
    SIBLING = "sibling"


class EvidenceClass(StrEnum):
    """Strength and linguistic origin of support for an extracted object.

    A-C are locally grounded classes. D requires an explicit coreference link. E and U are never
    sufficient for automatic graph materialization.
    """

    A_EXPLICIT = "A_explicit"
    B_MORPHOLOGICALLY_EXPLICIT = "B_morphologically_explicit"
    C_SPEAKER_ANCHORED = "C_speaker_anchored"
    D_CONTEXT_RESOLVED = "D_context_resolved"
    E_INFERRED = "E_inferred"
    U_UNCERTAIN = "U_uncertain"


class EvidenceSourceLayer(StrEnum):
    RAW_TRANSCRIPT = "raw_transcript"
    READABLE_TRANSCRIPT = "readable_transcript"


class EvidencePurpose(StrEnum):
    IDENTITY = "identity"
    CLAIM = "claim"
    COREFERENCE = "coreference"
    CORRECTION = "correction"
    CONTEXT = "context"
    CONFLICT = "conflict"


class NameVariantType(StrEnum):
    PRIMARY = "primary"
    EXPLICIT_ALIAS = "explicit_alias"
    NICKNAME = "nickname"
    DIMINUTIVE = "diminutive"
    PATRONYMIC = "patronymic"
    SURNAME = "surname"
    MARRIED_NAME = "married_name"
    TRANSLITERATION = "transliteration"
    SCRIPT_VARIANT = "script_variant"
    ASR_VARIANT = "asr_variant"
    INFLECTED_FORM = "inflected_form"
    UNKNOWN = "unknown"


class ProvenanceStage(StrEnum):
    ASR = "asr"
    CLEANER = "cleaner"
    EXTRACTOR = "extractor"
    SANITIZER = "sanitizer"
    RESOLVER = "resolver"
    HUMAN_REVIEW = "human_review"
    MIGRATION = "migration"


class CoreferenceStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class CoreferenceMethod(StrEnum):
    EXPLICIT_NAMING = "explicit_naming"
    SPEAKER_ANCHOR = "speaker_anchor"
    MORPHOLOGICAL = "morphological"
    DETERMINISTIC_DISCOURSE = "deterministic_discourse"
    MODEL_PROPOSAL = "model_proposal"
    HUMAN_REVIEW = "human_review"


class GrammaticalNumber(StrEnum):
    SINGULAR = "singular"
    PLURAL = "plural"
    UNKNOWN = "unknown"


class ClaimObjectType(StrEnum):
    PERSON_MENTION = "person_mention"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    DESCRIPTION = "description"
    STORY = "story"
    QUESTION = "question"


class ConflictType(StrEnum):
    IDENTITY = "identity"
    RELATIONSHIP = "relationship"
    ATTRIBUTE = "attribute"
    TEMPORAL = "temporal"
    NAME = "name"
    CORRECTION = "correction"
    OTHER = "other"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ConflictDetectionMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    HUMAN = "human"


class RawSegment(StrictModel):
    segment_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)
    chunk_id: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> RawSegment:
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        return self


class TranscriptEnvelope(StrictModel):
    recording_id: str
    duration_seconds: float = Field(gt=0)
    language_hints: list[str] = Field(default_factory=list)
    full_text: str
    segments: list[RawSegment] = Field(min_length=1)
    asr_model: str
    asr_revision: str
    chunker_version: str
    processing_seconds: float | None = Field(default=None, ge=0)
    asr_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_segments(self) -> TranscriptEnvelope:
        ids = [segment.segment_id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("segment IDs must be unique")
        return self


class ReadableSegment(StrictModel):
    segment_id: str
    text: str = Field(min_length=1)


class DetectedCorrection(StrictModel):
    kind: CorrectionKind
    subject: str | None = None
    original_value: str = Field(min_length=1)
    corrected_value: str = Field(min_length=1)
    source_segment_ids: list[str] = Field(min_length=1)
    explanation: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_changed_value(self) -> DetectedCorrection:
        if self.original_value.casefold() == self.corrected_value.casefold():
            raise ValueError("a correction must change the value")
        return self


class UncertainFragment(StrictModel):
    source_segment_ids: list[str] = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    possible_interpretation: None = None
    reason: str


class CleanerResult(StrictModel):
    readable_segments: list[ReadableSegment] = Field(min_length=1)
    detected_corrections: list[DetectedCorrection] = Field(default_factory=list)
    uncertain_fragments: list[UncertainFragment] = Field(default_factory=list)
    full_readable_text: str = Field(min_length=1)


class ProvenanceActivity(StrictModel):
    activity_id: str = Field(min_length=1)
    stage: ProvenanceStage
    system: str = Field(min_length=1)
    version: str = Field(min_length=1)
    prompt_version: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimProvenance(StrictModel):
    recording_id: str = Field(min_length=1)
    speaker_id: str = Field(min_length=1)
    speaker_name: str = Field(min_length=1)
    generated_by_activity_id: str = Field(min_length=1)
    validated_by_activity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    derived_from_claim_ids: list[str] = Field(default_factory=list)
    pipeline_versions: dict[str, str] = Field(default_factory=dict)


class EvidenceSpan(StrictModel):
    evidence_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_layer: EvidenceSourceLayer = EvidenceSourceLayer.RAW_TRANSCRIPT
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, gt=0)
    evidence_class: EvidenceClass = EvidenceClass.U_UNCERTAIN
    purposes: list[EvidencePurpose] = Field(default_factory=lambda: [EvidencePurpose.CLAIM])
    mention_ids: list[str] = Field(default_factory=list)
    coreference_link_ids: list[str] = Field(default_factory=list)
    derived_from_evidence_ids: list[str] = Field(default_factory=list)
    created_by_activity_id: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_offsets(self) -> EvidenceSpan:
        if (self.start_char is None) != (self.end_char is None):
            raise ValueError("evidence offsets must either both be set or both be omitted")
        if self.start_char is not None and self.end_char is not None:
            if self.end_char <= self.start_char:
                raise ValueError("evidence end_char must be greater than start_char")
            if self.end_char - self.start_char != len(self.text):
                raise ValueError("evidence offsets must span exactly evidence text length")
        if len(self.purposes) != len(set(self.purposes)):
            raise ValueError("evidence purposes must be unique")
        return self


def _normalize_name_surface(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.replace("_", " ").split())


class NameVariant(StrictModel):
    variant_id: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    variant_type: NameVariantType
    language: str | None = None
    script: str | None = None
    source_segment_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED

    @model_validator(mode="after")
    def validate_normalized_surface(self) -> NameVariant:
        expected = _normalize_name_surface(self.surface)
        if self.normalized != expected:
            raise ValueError(f"normalized name must equal {expected!r}")
        return self


class CoreferenceLink(StrictModel):
    coreference_id: str = Field(min_length=1)
    anaphor_text: str = Field(min_length=1)
    source_segment_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    status: CoreferenceStatus
    method: CoreferenceMethod
    grammatical_number: GrammaticalNumber = GrammaticalNumber.UNKNOWN
    antecedent_mention_ids: list[str] = Field(default_factory=list)
    candidate_mention_ids: list[str] = Field(default_factory=list)
    evidence_class: EvidenceClass = EvidenceClass.U_UNCERTAIN
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED

    @model_validator(mode="after")
    def validate_resolution_state(self) -> CoreferenceLink:
        antecedents = list(dict.fromkeys(self.antecedent_mention_ids))
        candidates = list(dict.fromkeys(self.candidate_mention_ids))
        if antecedents != self.antecedent_mention_ids:
            raise ValueError("coreference antecedent IDs must be unique")
        if candidates != self.candidate_mention_ids:
            raise ValueError("coreference candidate IDs must be unique")

        if self.status is CoreferenceStatus.RESOLVED:
            if not antecedents:
                raise ValueError("resolved coreference requires at least one antecedent")
            if self.grammatical_number is GrammaticalNumber.SINGULAR and len(antecedents) != 1:
                raise ValueError("singular resolved coreference requires exactly one antecedent")
            if candidates and not set(antecedents).issubset(candidates):
                raise ValueError("resolved antecedents must be included in candidate IDs")
        elif antecedents:
            raise ValueError("only resolved coreference may contain antecedent IDs")

        if self.status is CoreferenceStatus.AMBIGUOUS and len(candidates) < 2:
            raise ValueError("ambiguous coreference requires at least two candidates")
        return self


class ClaimReference(StrictModel):
    object_type: ClaimObjectType
    object_id: str = Field(min_length=1)


class ConflictSet(StrictModel):
    conflict_id: str = Field(min_length=1)
    conflict_type: ConflictType
    claim_refs: list[ClaimReference] = Field(min_length=2)
    status: ConflictStatus = ConflictStatus.OPEN
    detected_by: ConflictDetectionMethod
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    preferred_claim: ClaimReference | None = None
    resolution_note: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED

    @model_validator(mode="after")
    def validate_conflict_resolution(self) -> ConflictSet:
        keys = [(item.object_type, item.object_id) for item in self.claim_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("conflict claim references must be unique")
        if self.preferred_claim is not None:
            preferred_key = (self.preferred_claim.object_type, self.preferred_claim.object_id)
            if preferred_key not in keys:
                raise ValueError("preferred conflict claim must belong to the conflict set")
            if self.status is not ConflictStatus.RESOLVED:
                raise ValueError("a preferred claim is allowed only for a resolved conflict")
        if self.status is ConflictStatus.RESOLVED and not self.resolution_note:
            raise ValueError("resolved conflict requires a resolution note")
        return self


class ClaimUncertainty(StrictModel):
    status: EpistemicStatus
    markers: list[str] = Field(default_factory=list)
    source_segment_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    requires_review: bool = True

    @model_validator(mode="after")
    def validate_unique_references(self) -> ClaimUncertainty:
        if len(self.markers) != len(set(self.markers)):
            raise ValueError("uncertainty markers must be unique")
        if len(self.source_segment_ids) != len(set(self.source_segment_ids)):
            raise ValueError("uncertainty source segments must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("uncertainty evidence IDs must be unique")
        return self


class EvidenceBackedObject(StrictModel):
    source_segment_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_class: EvidenceClass = EvidenceClass.U_UNCERTAIN
    coreference_link_ids: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    uncertainty: ClaimUncertainty | None = None
    provenance: ClaimProvenance | None = None


class PersonMention(EvidenceBackedObject):
    mention_id: str
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    name_variants: list[NameVariant] = Field(default_factory=list)
    category: PersonCategory = PersonCategory.UNKNOWN
    relation_to_speaker: str | None = None
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED
    confidence: float = Field(ge=0, le=1)


class RelationshipClaim(EvidenceBackedObject):
    relationship_id: str
    relationship_type: RelationshipType
    relationship_state: RelationshipState = RelationshipState.CURRENT
    state_evidence_ids: list[str] = Field(default_factory=list)
    subject_mention_id: str
    subject_role: RelationshipRole
    object_mention_id: str
    object_role: RelationshipRole
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_relationship_roles(self) -> RelationshipClaim:
        if self.subject_mention_id == self.object_mention_id:
            raise ValueError("a relationship must connect two different mentions")

        role_pair = (self.subject_role, self.object_role)
        allowed_pairs = {
            RelationshipType.PARENT_CHILD: {
                (RelationshipRole.PARENT, RelationshipRole.CHILD),
            },
            RelationshipType.SPOUSE: {
                (RelationshipRole.SPOUSE, RelationshipRole.SPOUSE),
            },
            RelationshipType.SIBLING: {
                (RelationshipRole.OLDER_SIBLING, RelationshipRole.YOUNGER_SIBLING),
                (RelationshipRole.SIBLING, RelationshipRole.SIBLING),
            },
        }
        if role_pair not in allowed_pairs[self.relationship_type]:
            raise ValueError(f"invalid role pair {role_pair!r} for {self.relationship_type.value}")
        return self


class EventDate(StrictModel):
    value: str | None = None
    precision: TemporalPrecision = TemporalPrecision.UNKNOWN
    original_expression: str | None = None
    kind: TemporalKind = TemporalKind.UNKNOWN
    normalized_value: str | None = None
    lower_bound: str | None = None
    upper_bound: str | None = None
    approximate: bool = False
    relation: TemporalRelation | None = None
    anchor_event_id: str | None = None
    unresolved_reason: str | None = None
    source_evidence_ids: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED

    @model_validator(mode="after")
    def validate_temporal_shape(self) -> EventDate:
        if self.verification_status is not VerificationStatus.UNREVIEWED:
            raise ValueError("model temporal values must remain unreviewed")
        if (self.lower_bound is None) != (self.upper_bound is None):
            one_sided_relative = self.kind is TemporalKind.RELATIVE and (
                (
                    self.relation is TemporalRelation.BEFORE
                    and self.lower_bound is None
                    and self.upper_bound is not None
                )
                or (
                    self.relation is TemporalRelation.AFTER
                    and self.lower_bound is not None
                    and self.upper_bound is None
                )
            )
            if not one_sided_relative:
                raise ValueError("temporal ranges require both lower and upper bounds")
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError("temporal lower_bound must not exceed upper_bound")
        if self.kind is TemporalKind.RELATIVE and self.normalized_value is not None:
            if self.anchor_event_id is None:
                raise ValueError("relative temporal values need an anchor before normalization")
        if len(self.source_evidence_ids) != len(set(self.source_evidence_ids)):
            raise ValueError("temporal source evidence IDs must be unique")
        return self


class FamilyEvent(EvidenceBackedObject):
    event_id: str
    event_type: str
    title: str
    participant_mention_ids: list[str] = Field(default_factory=list)
    date: EventDate | None = None
    location: str | None = None
    description: str
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED
    confidence: float = Field(ge=0, le=1)


class PersonDescription(EvidenceBackedObject):
    description_id: str
    person_mention_id: str
    description: str
    perspective: str
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT
    verification_status: VerificationStatus = VerificationStatus.UNREVIEWED
    confidence: float = Field(ge=0, le=1)


class Story(EvidenceBackedObject):
    story_id: str
    title: str
    summary: str
    person_mention_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    privacy: Privacy = Privacy.PRIVATE
    sensitivity: StorySensitivity = StorySensitivity.NORMAL
    sensitivity_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def force_private_by_default(self) -> Story:
        self.privacy = Privacy.PRIVATE
        return self


class UnresolvedQuestion(EvidenceBackedObject):
    question_id: str
    question: str
    reason: str
    related_mention_ids: list[str] = Field(default_factory=list)


class ExtractionResult(StrictModel):
    schema_version: str = "extraction-v1"
    recording_id: str
    speaker_id: str
    speaker_name: str
    languages: list[str] = Field(default_factory=list)
    provenance_activities: list[ProvenanceActivity] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    coreference_links: list[CoreferenceLink] = Field(default_factory=list)
    conflict_sets: list[ConflictSet] = Field(default_factory=list)
    people_mentions: list[PersonMention] = Field(default_factory=list)
    relationship_claims: list[RelationshipClaim] = Field(default_factory=list)
    events: list[FamilyEvent] = Field(default_factory=list)
    descriptions: list[PersonDescription] = Field(default_factory=list)
    stories: list[Story] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_contract_ids(self) -> ExtractionResult:
        collections = {
            "provenance activity": [item.activity_id for item in self.provenance_activities],
            "evidence": [item.evidence_id for item in self.evidence_spans],
            "coreference": [item.coreference_id for item in self.coreference_links],
            "conflict": [item.conflict_id for item in self.conflict_sets],
        }
        for object_name, values in collections.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{object_name} IDs must be unique")
        return self


class KnownPerson(StrictModel):
    person_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: PersonCategory = PersonCategory.UNKNOWN
    relation_to_speaker: str | None = None


class MentionResolution(StrictModel):
    mention_id: str
    status: ResolutionStatus
    person_id: str | None = None
    candidate_person_ids: list[str] = Field(default_factory=list)
    reason: str


class AudioLanguage(StrEnum):
    """What the narrator asked Core to assume about the speech."""

    AUTO = "auto"
    RU = "ru"
    KK = "kk"
    MIXED = "mixed"


class OutputLanguage(StrEnum):
    """What the narrator asked Core to write results in."""

    SAME_AS_TRANSCRIPT = "same_as_transcript"
    RU = "ru"
    KK = "kk"


class DetectedLanguage(StrEnum):
    """Only Core-authoritative detection may set anything but UNKNOWN."""

    RU = "ru"
    KK = "kk"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LanguageContext(StrictModel):
    """Requested language intent and the behaviour Core actually delivered.

    The two are separated on purpose. GigaAM receives no language instruction
    today and the DeepSeek prompts have no output-language hook, so a request is
    durably recorded but does not change provider behaviour. The ``*_applied``
    flags say so rather than implying an effect that does not exist.
    """

    schema_version: str = "language-context-v1"

    requested_audio_language: AudioLanguage = AudioLanguage.AUTO
    #: ASR runs unconstrained, so the effective mode is always AUTO today.
    effective_audio_language: AudioLanguage = AudioLanguage.AUTO
    #: True only when an explicit request actually constrained the provider.
    audio_language_applied: bool = False

    #: UNKNOWN until Core owns an authoritative detector. A frontend heuristic
    #: must never be promoted into this field.
    detected_audio_language: DetectedLanguage = DetectedLanguage.UNKNOWN
    transcript_language: DetectedLanguage = DetectedLanguage.UNKNOWN

    requested_output_language: OutputLanguage = OutputLanguage.SAME_AS_TRANSCRIPT
    #: None while Core cannot guarantee any particular output language.
    effective_output_language: OutputLanguage | None = None
    output_language_applied: bool = False


def build_language_context(
    *,
    requested_audio_language: AudioLanguage,
    requested_output_language: OutputLanguage,
) -> LanguageContext:
    """Truthful context for the current providers.

    ``audio_language_applied`` is False for every request including AUTO: the
    flag reports whether the *request* changed provider behaviour, and nothing
    is ever sent to the recogniser. AUTO happens to match the effective mode,
    but it was not honoured — it was simply never contradicted.
    """

    return LanguageContext(
        requested_audio_language=requested_audio_language,
        effective_audio_language=AudioLanguage.AUTO,
        audio_language_applied=False,
        detected_audio_language=DetectedLanguage.UNKNOWN,
        transcript_language=DetectedLanguage.UNKNOWN,
        requested_output_language=requested_output_language,
        effective_output_language=None,
        output_language_applied=False,
    )


class PipelineRequest(StrictModel):
    transcript: TranscriptEnvelope
    speaker_id: str
    speaker_name: str
    known_people: list[KnownPerson] = Field(default_factory=list)
    #: Durable language intent. Carried through async reconstruction even though
    #: no current provider consumes it.
    requested_audio_language: AudioLanguage = AudioLanguage.AUTO
    requested_output_language: OutputLanguage = OutputLanguage.SAME_AS_TRANSCRIPT


class PipelineResult(StrictModel):
    transcript: TranscriptEnvelope
    cleaned_transcript: CleanerResult
    extraction: ExtractionResult
    resolutions: list[MentionResolution] = Field(default_factory=list)
    processing: dict[str, Any] = Field(default_factory=dict)
