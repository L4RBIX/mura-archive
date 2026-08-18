"""Product read models over the archive.

The archive is stored the way extraction produces it: claims keyed by object
type, an evidence-gated edge table, materialized profiles, conflicts. That is
the right shape for the pipeline and the wrong shape for a browser, which would
otherwise have to reassemble a family graph out of `archive_claims` payloads
and re-derive the rules about which of them may be trusted.

So the projection happens here, once, on the server. Two things follow from
that and are worth stating because they are easy to lose:

*Nothing is invented.* Every field below comes from a persisted row. Where the
archive does not know something -- a date, a title, who someone is -- the DTO
says so with a null rather than a plausible default, because a family archive
that fills in gaps convincingly is worse than one that admits them.

*The trust rules stay in Core.* Which relationship claims are strong enough to
appear as an edge is already decided when the graph is materialized, using the
evidence-class ladder. This module reads that decision; it does not re-derive
it, and it must never introduce a confidence threshold of its own.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mura.domain.models import ClaimObjectType, StrictModel
from mura.storage.archive import (
    ArchiveClaimRow,
    ArchiveConflictRow,
    ArchivePersonRow,
    FamilyGraphEdgeRow,
)
from mura.storage.database import Database, RecordingRow

#: Claims whose object never appears in the product as a first-class thing.
STORY_PREDICATE = "story"
QUESTION_PREDICATE = "question"

#: A hard ceiling on any list endpoint. A family archive grows for years, and
#: an unbounded list would eventually return every story ever recorded to a
#: phone. Callers page with `limit`/`offset`; this is the backstop.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

#: Longest excerpt a *list* endpoint will ever return. Detail endpoints return
#: the stored summary in full; a list must not become a way to pull every
#: transcript in the family in one request.
LIST_EXCERPT_CHARS = 280


class DateView(StrictModel):
    """A date the archive actually knows, with its precision preserved.

    `precision` is the point. Rendering "1 января 1978" when the archive only
    ever heard "в семьдесят восьмом" invents a day and a month nobody said.
    """

    value: str | None = None
    precision: str = "unknown"
    original_expression: str | None = None
    approximate: bool = False


class SourceView(StrictModel):
    """Where a fact came from, in terms a person can follow.

    Deliberately not the evidence machinery: `evidence_class`, assertion mode
    and confidence stay on the row. What a family member needs is which story,
    told by whom, on what recording.
    """

    recording_id: str
    speaker_name: str
    recorded_at: datetime
    claim_ids: list[str] = Field(default_factory=list)


class PersonSummaryView(StrictModel):
    person_id: str
    display_name: str
    #: Only aliases entity resolution actually verified.
    aliases: list[str] = Field(default_factory=list)
    category: str
    #: "бабушка", "муж" — as said about the speaker, never inferred.
    relation_to_speaker: str | None = None
    story_count: int = 0
    recording_count: int = 0


class RelationshipView(StrictModel):
    """One materialized edge. Both endpoints are canonical people."""

    edge_id: str
    relationship_type: str
    subject_person_id: str
    subject_role: str
    object_person_id: str
    object_role: str
    source_claim_ids: list[str] = Field(default_factory=list)


class StorySummaryView(StrictModel):
    story_id: str
    title: str | None = None
    excerpt: str | None = None
    recording_id: str
    speaker_name: str
    recorded_at: datetime
    person_ids: list[str] = Field(default_factory=list)


class StoryDetailView(StrictModel):
    story_id: str
    title: str | None = None
    summary: str | None = None
    recording_id: str
    speaker_name: str
    recorded_at: datetime
    people: list[PersonSummaryView] = Field(default_factory=list)
    events: list[EventView] = Field(default_factory=list)
    source: SourceView
    #: True only when canonical audio is genuinely retrievable for this
    #: recording. The UI must not offer a player on the strength of a guess.
    audio_available: bool = False


class EventView(StrictModel):
    event_id: str
    title: str
    event_type: str
    description: str | None = None
    location: str | None = None
    date: DateView | None = None
    participant_person_ids: list[str] = Field(default_factory=list)


class ReviewItemView(StrictModel):
    """Something the archive cannot settle on its own.

    `kind` is the backend's classification, not a frontend heuristic. The
    product asks the question in human words; the category decides which words.
    """

    review_id: str
    kind: str
    question: str
    detail: str | None = None
    recording_id: str | None = None
    person_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class ArchiveOverviewView(StrictModel):
    family_id: str
    people_count: int = 0
    relationship_count: int = 0
    story_count: int = 0
    recording_count: int = 0
    review_count: int = 0
    open_conflict_count: int = 0
    recent_stories: list[StorySummaryView] = Field(default_factory=list)


class Page(StrictModel):
    total: int = 0
    limit: int = DEFAULT_PAGE_SIZE
    offset: int = 0


class StoryPageView(StrictModel):
    page: Page
    items: list[StorySummaryView] = Field(default_factory=list)


class ArchiveResourceNotFound(LookupError):
    """Absent, or belonging to another family. The caller is told neither."""


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= LIST_EXCERPT_CHARS:
        return collapsed
    return collapsed[: LIST_EXCERPT_CHARS - 1].rstrip() + "…"


def _date_view(payload: Any) -> DateView | None:
    if not isinstance(payload, dict):
        return None
    return DateView(
        value=payload.get("normalized_value") or payload.get("value"),
        precision=str(payload.get("precision") or "unknown"),
        original_expression=payload.get("original_expression"),
        approximate=bool(payload.get("approximate", False)),
    )


class ArchiveReadRepository:
    """Family-scoped reads. Every query is filtered by `family_id`.

    Scoping is a predicate in the query, never a fetch-then-compare: a row
    belonging to another family is not loaded and then rejected, it is never
    selected. That is what keeps a guessed id from being a timing signal.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    # ------------------------------------------------------------------ people

    def list_people(self, *, family_id: str) -> list[PersonSummaryView]:
        with self._database.session_factory() as session:
            people = list(
                session.scalars(
                    select(ArchivePersonRow)
                    .where(ArchivePersonRow.family_id == family_id)
                    .order_by(ArchivePersonRow.canonical_name)
                )
            )
            if not people:
                return []
            return self._person_views(session, family_id=family_id, rows=people)

    def get_person(self, *, family_id: str, person_id: str) -> PersonSummaryView:
        with self._database.session_factory() as session:
            row = session.scalars(
                select(ArchivePersonRow).where(
                    ArchivePersonRow.family_id == family_id,
                    ArchivePersonRow.person_id == person_id,
                )
            ).one_or_none()
            if row is None:
                raise ArchiveResourceNotFound(person_id)
            return self._person_views(session, family_id=family_id, rows=[row])[0]

    def _person_views(
        self,
        session: Session,
        *,
        family_id: str,
        rows: list[ArchivePersonRow],
    ) -> list[PersonSummaryView]:
        """One extra query for all people, not one per person.

        The obvious shape here is a story count per person, which on a family
        with a hundred people is a hundred round trips. Story claims are read
        once and counted in memory instead.
        """

        story_claims = list(
            session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.STORY.value,
                    ArchiveClaimRow.status == "active",
                )
            )
        )
        resolved = resolve_mentions(
            session,
            family_id=family_id,
            recording_ids={claim.recording_id for claim in story_claims},
        )
        stories_by_person: dict[str, int] = defaultdict(int)
        for claim in story_claims:
            for person_id in _story_person_ids(claim, resolved):
                stories_by_person[person_id] += 1

        return [
            PersonSummaryView(
                person_id=row.person_id,
                display_name=row.canonical_name,
                # Verified aliases only: an unverified variant is a guess about
                # who someone is, which is exactly what must not be presented
                # as a fact about a family member.
                aliases=list(row.verified_aliases or []),
                category=row.category,
                relation_to_speaker=_first_relation(row.relations_to_speakers),
                story_count=stories_by_person.get(row.person_id, 0),
                recording_count=len(row.source_recording_ids or []),
            )
            for row in rows
        ]

    # ----------------------------------------------------------- relationships

    def list_relationships(self, *, family_id: str) -> list[RelationshipView]:
        """The materialized graph, as decided when the archive was written.

        Only edges whose endpoints are both still canonical people are
        returned, so the frontend can render an edge without checking that the
        nodes exist.
        """

        with self._database.session_factory() as session:
            known = set(
                session.scalars(
                    select(ArchivePersonRow.person_id).where(
                        ArchivePersonRow.family_id == family_id
                    )
                )
            )
            edges = session.scalars(
                select(FamilyGraphEdgeRow)
                .where(FamilyGraphEdgeRow.family_id == family_id)
                .order_by(FamilyGraphEdgeRow.edge_id)
            )
            return [
                RelationshipView(
                    edge_id=edge.edge_id,
                    relationship_type=edge.relationship_type,
                    subject_person_id=edge.subject_person_id,
                    subject_role=edge.subject_role,
                    object_person_id=edge.object_person_id,
                    object_role=edge.object_role,
                    source_claim_ids=list(edge.source_claim_ids or []),
                )
                for edge in edges
                if edge.subject_person_id in known and edge.object_person_id in known
            ]

    # ----------------------------------------------------------------- stories

    def list_stories(
        self,
        *,
        family_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> StoryPageView:
        size = clamp_limit(limit)
        start = max(0, offset)
        with self._database.session_factory() as session:
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(ArchiveClaimRow)
                    .where(
                        ArchiveClaimRow.family_id == family_id,
                        ArchiveClaimRow.object_type == ClaimObjectType.STORY.value,
                        ArchiveClaimRow.status == "active",
                    )
                )
                or 0
            )
            claims = list(
                session.scalars(
                    select(ArchiveClaimRow)
                    .where(
                        ArchiveClaimRow.family_id == family_id,
                        ArchiveClaimRow.object_type == ClaimObjectType.STORY.value,
                        ArchiveClaimRow.status == "active",
                    )
                    # Newest first by when the memory was recorded. There is no
                    # invented chronology here: an undated story is ordered by
                    # its recording, not by a date nobody said.
                    .order_by(ArchiveClaimRow.created_at.desc(), ArchiveClaimRow.claim_id)
                    .limit(size)
                    .offset(start)
                )
            )
            recordings = self._recordings_for(session, family_id=family_id, claims=claims)
            resolved = resolve_mentions(
                session,
                family_id=family_id,
                recording_ids={claim.recording_id for claim in claims},
            )
            items = [
                self._story_summary(claim, recordings.get(claim.recording_id), resolved)
                for claim in claims
            ]
            return StoryPageView(
                page=Page(total=total, limit=size, offset=start),
                items=[item for item in items if item is not None],
            )

    def get_story(self, *, family_id: str, story_id: str) -> StoryDetailView:
        with self._database.session_factory() as session:
            claim = session.scalars(
                select(ArchiveClaimRow).where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.STORY.value,
                    ArchiveClaimRow.source_object_id == story_id,
                    ArchiveClaimRow.status == "active",
                )
            ).first()
            if claim is None:
                raise ArchiveResourceNotFound(story_id)

            recording = session.get(RecordingRow, claim.recording_id)
            if recording is None or recording.family_id != family_id:
                raise ArchiveResourceNotFound(story_id)

            payload = claim.payload if isinstance(claim.payload, dict) else {}
            person_ids = _story_person_ids(
                claim,
                resolve_mentions(
                    session,
                    family_id=family_id,
                    recording_ids={claim.recording_id},
                ),
            )

            people = (
                self._person_views(
                    session,
                    family_id=family_id,
                    rows=list(
                        session.scalars(
                            select(ArchivePersonRow).where(
                                ArchivePersonRow.family_id == family_id,
                                ArchivePersonRow.person_id.in_(person_ids),
                            )
                        )
                    ),
                )
                if person_ids
                else []
            )

            return StoryDetailView(
                story_id=story_id,
                title=_clean(payload.get("title")),
                summary=_clean(payload.get("summary")),
                recording_id=claim.recording_id,
                speaker_name=recording.speaker_name,
                recorded_at=recording.created_at,
                people=people,
                events=self._events_for(
                    session,
                    family_id=family_id,
                    event_ids=[
                        value for value in payload.get("event_ids", []) if isinstance(value, str)
                    ],
                ),
                source=SourceView(
                    recording_id=claim.recording_id,
                    speaker_name=recording.speaker_name,
                    recorded_at=recording.created_at,
                    claim_ids=[claim.claim_id],
                ),
                # A storage key is the only proof the bytes exist; a legacy row
                # with only an audio_path is not offered for playback.
                audio_available=bool(recording.storage_key),
            )

    def _recordings_for(
        self,
        session: Session,
        *,
        family_id: str,
        claims: list[ArchiveClaimRow],
    ) -> dict[str, RecordingRow]:
        ids = {claim.recording_id for claim in claims}
        if not ids:
            return {}
        rows = session.scalars(
            select(RecordingRow).where(
                RecordingRow.family_id == family_id,
                RecordingRow.recording_id.in_(ids),
            )
        )
        return {row.recording_id: row for row in rows}

    @staticmethod
    def _story_summary(
        claim: ArchiveClaimRow,
        recording: RecordingRow | None,
        resolved: dict[tuple[str, str], str],
    ) -> StorySummaryView | None:
        if recording is None:
            return None
        payload = claim.payload if isinstance(claim.payload, dict) else {}
        return StorySummaryView(
            story_id=claim.source_object_id,
            title=_clean(payload.get("title")),
            excerpt=_excerpt(_clean(payload.get("summary"))),
            recording_id=claim.recording_id,
            speaker_name=recording.speaker_name,
            recorded_at=recording.created_at,
            person_ids=_story_person_ids(claim, resolved),
        )

    def _events_for(
        self,
        session: Session,
        *,
        family_id: str,
        event_ids: list[str],
    ) -> list[EventView]:
        if not event_ids:
            return []
        claims = session.scalars(
            select(ArchiveClaimRow).where(
                ArchiveClaimRow.family_id == family_id,
                ArchiveClaimRow.object_type == ClaimObjectType.EVENT.value,
                ArchiveClaimRow.source_object_id.in_(event_ids),
                ArchiveClaimRow.status == "active",
            )
        )
        views: list[EventView] = []
        for claim in claims:
            payload = claim.payload if isinstance(claim.payload, dict) else {}
            title = _clean(payload.get("title"))
            if not title:
                continue
            views.append(
                EventView(
                    event_id=claim.source_object_id,
                    title=title,
                    event_type=str(payload.get("event_type") or "event"),
                    description=_clean(payload.get("description")),
                    location=_clean(payload.get("location")),
                    date=_date_view(payload.get("date")),
                    participant_person_ids=[],
                )
            )
        return views

    # ------------------------------------------------------------------ review

    def list_review_items(self, *, family_id: str) -> list[ReviewItemView]:
        """Everything the archive says needs a person to look at it.

        Two sources, both persisted: questions extraction could not resolve,
        and conflicts the archive detected between claims. There is no
        frontend rule deciding what counts as needing review -- that would put
        the definition of uncertainty in the client.
        """

        with self._database.session_factory() as session:
            questions = session.scalars(
                select(ArchiveClaimRow)
                .where(
                    ArchiveClaimRow.family_id == family_id,
                    ArchiveClaimRow.object_type == ClaimObjectType.QUESTION.value,
                    ArchiveClaimRow.status == "active",
                )
                .order_by(ArchiveClaimRow.created_at.desc())
            )
            items: list[ReviewItemView] = []
            for claim in questions:
                payload = claim.payload if isinstance(claim.payload, dict) else {}
                question = _clean(payload.get("question"))
                if not question:
                    continue
                items.append(
                    ReviewItemView(
                        review_id=claim.claim_id,
                        kind="open_question",
                        question=question,
                        detail=_clean(payload.get("reason")),
                        recording_id=claim.recording_id,
                        created_at=claim.created_at,
                    )
                )

            conflicts = session.scalars(
                select(ArchiveConflictRow)
                .where(
                    ArchiveConflictRow.family_id == family_id,
                    ArchiveConflictRow.status == "open",
                )
                .order_by(ArchiveConflictRow.created_at.desc())
            )
            for conflict in conflicts:
                items.append(
                    ReviewItemView(
                        review_id=conflict.conflict_id,
                        kind=f"conflict:{conflict.conflict_type}",
                        question=conflict.rationale,
                        detail=None,
                        recording_id=None,
                        created_at=conflict.created_at,
                    )
                )
            return items

    # ---------------------------------------------------------------- overview

    def overview(self, *, family_id: str) -> ArchiveOverviewView:
        stories = self.list_stories(family_id=family_id, limit=5)
        with self._database.session_factory() as session:
            people_count = (
                session.scalar(
                    select(func.count())
                    .select_from(ArchivePersonRow)
                    .where(ArchivePersonRow.family_id == family_id)
                )
                or 0
            )
            relationship_count = (
                session.scalar(
                    select(func.count())
                    .select_from(FamilyGraphEdgeRow)
                    .where(FamilyGraphEdgeRow.family_id == family_id)
                )
                or 0
            )
            recording_count = (
                session.scalar(
                    select(func.count())
                    .select_from(RecordingRow)
                    .where(RecordingRow.family_id == family_id)
                )
                or 0
            )
            open_conflicts = (
                session.scalar(
                    select(func.count())
                    .select_from(ArchiveConflictRow)
                    .where(
                        ArchiveConflictRow.family_id == family_id,
                        ArchiveConflictRow.status == "open",
                    )
                )
                or 0
            )
            open_questions = (
                session.scalar(
                    select(func.count())
                    .select_from(ArchiveClaimRow)
                    .where(
                        ArchiveClaimRow.family_id == family_id,
                        ArchiveClaimRow.object_type == ClaimObjectType.QUESTION.value,
                        ArchiveClaimRow.status == "active",
                    )
                )
                or 0
            )

        return ArchiveOverviewView(
            family_id=family_id,
            people_count=people_count,
            relationship_count=relationship_count,
            story_count=stories.page.total,
            recording_count=recording_count,
            review_count=open_questions + open_conflicts,
            open_conflict_count=open_conflicts,
            recent_stories=stories.items,
        )


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _first_relation(relations: Any) -> str | None:
    if not isinstance(relations, dict):
        return None
    for value in relations.values():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _mention_ids(claim: ArchiveClaimRow) -> list[str]:
    """The mention ids a story names.

    A mention is a string somebody said, not a person. Resolving it is entity
    resolution's job, and it already did that work: see `resolve_mentions`.
    """

    payload = claim.payload if isinstance(claim.payload, dict) else {}
    mentions = payload.get("person_mention_ids")
    if isinstance(mentions, list):
        return [value for value in mentions if isinstance(value, str) and value]
    return []


def resolve_mentions(
    session: Session,
    *,
    family_id: str,
    recording_ids: set[str],
) -> dict[tuple[str, str], str]:
    """Map (recording_id, mention_id) -> canonical person_id.

    Story claims record which mentions they involve, and the canonical person
    behind each mention is persisted on that mention's own claim, written by
    entity resolution when the archive was built. Following that link is the
    only honest way to answer "who is this story about".

    The alternative -- matching a story's mention text against person names --
    is what PR-05 left behind on the Person page and is being removed here.
    Names are not identity: two relatives share one, one relative has three
    across Russian and Kazakh spelling, and a normalised string comparison
    quietly merges people who are not the same person.

    Resolved in one query for every recording involved, so a page of stories
    costs one lookup rather than one per story.
    """

    if not recording_ids:
        return {}
    rows = session.scalars(
        select(ArchiveClaimRow).where(
            ArchiveClaimRow.family_id == family_id,
            ArchiveClaimRow.object_type == ClaimObjectType.PERSON_MENTION.value,
            ArchiveClaimRow.recording_id.in_(recording_ids),
            # An unresolved mention has no canonical person yet. It belongs in
            # review, not in a story's cast list.
            ArchiveClaimRow.status == "active",
        )
    )
    return {
        (row.recording_id, row.source_object_id): row.subject_person_id
        for row in rows
        if row.subject_person_id
    }


def _story_person_ids(
    claim: ArchiveClaimRow,
    resolved: dict[tuple[str, str], str],
) -> list[str]:
    seen: list[str] = []
    for mention_id in _mention_ids(claim):
        person_id = resolved.get((claim.recording_id, mention_id))
        if person_id and person_id not in seen:
            seen.append(person_id)
    return seen


StoryDetailView.model_rebuild()
