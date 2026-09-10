"""Which languages a transcript is actually written in.

Whisper reports one language per request. A MURA recording is routinely two:
«Менің әжем Алматыда тұрды, потом мы поехали к ней летом» is one sentence in
two languages, and a single `language` field cannot describe it.

This module therefore does not guess and does not ask a model. It reads the
text that was actually produced and reports what is demonstrably present:

  * nine graphemes exist in Kazakh Cyrillic and not in Russian, so any of them
    is direct evidence of Kazakh;
  * closed-class function words are the densest, least ambiguous marker of
    either language, and appear in essentially every real sentence.

Both signals are observable in the string. Nothing here is inferred from a
confidence score the recogniser never reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Present in the Kazakh alphabet, absent from the Russian one. Their presence
#: is evidence; their absence is not evidence of absence, because plenty of
#: Kazakh words are spelled entirely with shared letters.
KAZAKH_GRAPHEMES = frozenset("әғқңөұүһі")

#: Closed-class Russian words. Chosen because they are function words: they
#: carry no topic, cannot be borrowed wholesale into a Kazakh clause without
#: bringing Russian grammar with them, and occur constantly.
RUSSIAN_MARKERS = frozenset(
    {
        "и", "в", "на", "с", "со", "что", "как", "я", "мы", "он", "она", "они",
        "но", "потом", "же", "к", "по", "у", "за", "от", "до", "это", "был",
        "была", "были", "было", "не", "мне", "нас", "нам", "там", "тогда",
        "когда", "очень", "ещё", "еще", "уже", "его", "её", "ее", "их", "тоже",
    }
)

#: The Kazakh equivalents, including the postpositions and question clitics
#: that attach to almost every spoken clause.
KAZAKH_MARKERS = frozenset(
    {
        "мен", "бен", "пен", "және", "бірақ", "сол", "бұл", "ол", "біз", "олар",
        "үшін", "кейін", "содан", "сосын", "ма", "ме", "ба", "бе", "па", "пе",
        "ғой", "қой", "да", "де", "та", "те", "деп", "керек", "бар", "жоқ",
        "менің", "оның", "біздің", "сонда", "қазір",
    }
)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class LanguageReading:
    """What the transcript text demonstrably contains."""

    #: Sorted ISO-639-1 codes with positive evidence, e.g. ["kk", "ru"].
    languages: tuple[str, ...]
    #: True when more than one language is present in the same transcript.
    mixed: bool
    #: "kk", "ru", "mixed", or "unknown" when the text carries no marker at all.
    detected: str

    @property
    def as_metadata(self) -> dict[str, str | int | bool]:
        """Flat, primitive-only, for TranscriptEnvelope.asr_metadata."""

        return {
            "detected_language": self.detected,
            "transcript_languages": ",".join(self.languages),
            "mixed_language": self.mixed,
        }


def read_languages(text: str) -> LanguageReading:
    """Report the languages present in `text` without translating or guessing."""

    lowered = text.casefold()
    words = {match.group(0) for match in _WORD.finditer(lowered)}

    kazakh = bool(KAZAKH_GRAPHEMES & set(lowered)) or bool(KAZAKH_MARKERS & words)
    russian = bool(RUSSIAN_MARKERS & words)

    # The two marker sets are disjoint by construction, so a word can support
    # at most one language and nothing is double-counted.
    present = tuple(code for code, seen in (("kk", kazakh), ("ru", russian)) if seen)

    if len(present) > 1:
        return LanguageReading(languages=present, mixed=True, detected="mixed")
    if present:
        return LanguageReading(languages=present, mixed=False, detected=present[0])
    return LanguageReading(languages=(), mixed=False, detected="unknown")
