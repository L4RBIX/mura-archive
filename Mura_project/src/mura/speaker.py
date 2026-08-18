"""Speaker identity for the recording contract.

Two identifier namespaces meet here and must never be confused.

``person_<32 lowercase hex>``
    A canonical archive person. Only entity resolution mints these, and one is
    trustworthy only after a database lookup proves it exists *and* belongs to
    the requested family. Syntax alone proves nothing.

``narrator_<recording_id>``
    A reserved internal reference for a narrator who is not canonical yet. It
    exists solely because the pipeline needs a non-null speaker handle. It is
    never written to ``archive_people`` as an already-resolved person, and it is
    never returned to a client as ``person_id``: the public speaker view reports
    ``person_id: null`` until entity resolution materialises a real person.

``RecordingRow.speaker_id`` stores whichever of the two applies. The column name
is historical and deliberately not migrated; the public API field is
``speaker_person_id`` and only ever carries a canonical value.
"""

from __future__ import annotations

import re

CANONICAL_PERSON_PATTERN = re.compile(r"\Aperson_[0-9a-f]{32}\Z")
NARRATOR_PREFIX = "narrator_"


class SpeakerSyntaxError(ValueError):
    """The supplied speaker_person_id is not a canonical person identifier."""


def is_canonical_person_id(value: str) -> bool:
    """Syntactic check only. Never sufficient to establish identity."""

    return bool(CANONICAL_PERSON_PATTERN.fullmatch(value))


def internal_narrator_reference(recording_id: str) -> str:
    """Reserved non-canonical speaker handle for a narrator with no archive person."""

    return f"{NARRATOR_PREFIX}{recording_id}"


def is_internal_narrator_reference(value: str) -> bool:
    return value.startswith(NARRATOR_PREFIX)


def validate_speaker_person_id(value: str) -> str:
    """Reject anything that is not canonical *syntax* before touching the database."""

    candidate = value.strip()
    if not is_canonical_person_id(candidate):
        raise SpeakerSyntaxError("speaker_person_id must be a canonical person identifier")
    return candidate


def public_person_id(stored_speaker_id: str) -> str | None:
    """The canonical person id to show a client, or None for an internal narrator."""

    if is_internal_narrator_reference(stored_speaker_id):
        return None
    return stored_speaker_id if is_canonical_person_id(stored_speaker_id) else None
