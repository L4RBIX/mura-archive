from __future__ import annotations

from mura.domain.models import PersonCategory, PersonMention
from mura.linguistics.kazakh import find_relationship_signals, has_speaker_anchor


def _person(mention_id: str, name: str) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category=PersonCategory.FAMILY_MEMBER,
        source_segment_ids=["seg_001"],
        confidence=1.0,
    )


def test_ambiguous_kinship_terms_do_not_prove_family_relationships() -> None:
    speaker = _person("mention_kulash", "Күләш")
    bolat = _person("mention_bolat", "Болат")

    for text in ("Жолдасым Болат.", "Бауырым Болат."):
        assert not has_speaker_anchor(text)
        assert (
            find_relationship_signals(
                text,
                [speaker, bolat],
                speaker_name="Күләш",
            )
            == []
        )
