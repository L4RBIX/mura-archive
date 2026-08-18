from __future__ import annotations

from dataclasses import dataclass

from mura.linguistics.common import contains_normalized_phrase, normalize_text

_DIRECT_CORRECTION_CUES = (
    "жоқ",
    "дұрыс айтсам",
    "дұрысы",
    "дәлірек айтсам",
    "нақтырақ айтсам",
    "нет",
    "точнее",
    "вернее",
    "правильнее сказать",
    "no",
    "i mean",
    "rather",
)


@dataclass(frozen=True)
class CorrectionCueMatch:
    cue: str
    rule_id: str

    def to_dict(self) -> dict[str, str]:
        return {"cue": self.cue, "rule_id": self.rule_id}


def find_explicit_correction_cues(text: str) -> list[CorrectionCueMatch]:
    matches = [
        CorrectionCueMatch(cue=cue, rule_id="correction.explicit_cue.v1")
        for cue in _DIRECT_CORRECTION_CUES
        if contains_normalized_phrase(text, cue)
    ]

    normalized = normalize_text(text)
    if " емес " in f" {normalized} " and contains_normalized_phrase(text, "болуы керек"):
        matches.append(
            CorrectionCueMatch(
                cue="емес ... болуы керек",
                rule_id="correction.kazakh_replacement_frame.v1",
            )
        )
    return matches


def has_explicit_correction_cue(text: str) -> bool:
    return bool(find_explicit_correction_cues(text))
