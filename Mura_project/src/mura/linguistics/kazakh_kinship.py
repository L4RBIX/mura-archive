from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from mura.domain.models import RelationshipRole, RelationshipType
from mura.linguistics.common import tokenize
from mura.linguistics.kazakh import KinshipFrame

_PARENT = RelationshipRole.PARENT
_CHILD = RelationshipRole.CHILD
_OLDER = RelationshipRole.OLDER_SIBLING
_YOUNGER = RelationshipRole.YOUNGER_SIBLING
_SPOUSE = RelationshipRole.SPOUSE
_PARENT_CHILD = RelationshipType.PARENT_CHILD
_SIBLING = RelationshipType.SIBLING
_SPOUSE_TYPE = RelationshipType.SPOUSE

_NAMED_POSSESSOR_FRAMES = MappingProxyType(
    {
        "әкесі": KinshipFrame(_PARENT_CHILD, _CHILD, _PARENT),
        "анасы": KinshipFrame(_PARENT_CHILD, _CHILD, _PARENT),
        "шешесі": KinshipFrame(_PARENT_CHILD, _CHILD, _PARENT),
        "ұлы": KinshipFrame(_PARENT_CHILD, _PARENT, _CHILD),
        "қызы": KinshipFrame(_PARENT_CHILD, _PARENT, _CHILD),
        "баласы": KinshipFrame(_PARENT_CHILD, _PARENT, _CHILD),
        "ағасы": KinshipFrame(_SIBLING, _YOUNGER, _OLDER),
        "әпкесі": KinshipFrame(_SIBLING, _YOUNGER, _OLDER),
        "інісі": KinshipFrame(_SIBLING, _OLDER, _YOUNGER),
        "сіңлісі": KinshipFrame(_SIBLING, _OLDER, _YOUNGER),
        "қарындасы": KinshipFrame(_SIBLING, _OLDER, _YOUNGER),
        "әйелі": KinshipFrame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
        "күйеуі": KinshipFrame(_SPOUSE_TYPE, _SPOUSE, _SPOUSE),
    }
)


@dataclass(frozen=True)
class KazakhKinshipMatch:
    surface: str
    start: int
    end: int
    frame: KinshipFrame


def find_named_possessor_kinship_matches(text: str) -> list[KazakhKinshipMatch]:
    return [
        KazakhKinshipMatch(
            surface=token.surface,
            start=token.start,
            end=token.end,
            frame=frame,
        )
        for token in tokenize(text)
        if (frame := _NAMED_POSSESSOR_FRAMES.get(token.normalized)) is not None
    ]
