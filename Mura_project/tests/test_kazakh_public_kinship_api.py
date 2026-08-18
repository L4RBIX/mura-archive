from __future__ import annotations

from mura.domain.models import RelationshipRole, RelationshipType
from mura.linguistics.kazakh_kinship import find_named_possessor_kinship_matches


def test_public_kazakh_kinship_api_returns_typed_exact_matches() -> None:
    text = "Олардың қызы Амина. Күләштің інісі Нұржан."

    matches = find_named_possessor_kinship_matches(text)

    assert [match.surface for match in matches] == ["қызы", "інісі"]
    assert [(match.start, match.end) for match in matches] == [
        (text.index("қызы"), text.index("қызы") + len("қызы")),
        (text.index("інісі"), text.index("інісі") + len("інісі")),
    ]
    assert matches[0].frame.relationship_type is RelationshipType.PARENT_CHILD
    assert matches[0].frame.possessor_role is RelationshipRole.PARENT
    assert matches[0].frame.relative_role is RelationshipRole.CHILD
    assert matches[1].frame.relationship_type is RelationshipType.SIBLING


def test_public_kazakh_kinship_api_ignores_unknown_tokens() -> None:
    assert find_named_possessor_kinship_matches("Олар көршілермен сөйлесті.") == []
