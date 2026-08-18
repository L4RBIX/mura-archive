from __future__ import annotations

from mura.domain.models import (
    CoreferenceMethod,
    CoreferenceStatus,
    ExtractionResult,
    GrammaticalNumber,
)


def discourse_link_counters(result: ExtractionResult) -> dict[str, int]:
    counters = {
        "singular_coreference_resolved": 0,
        "plural_coreference_resolved": 0,
        "ambiguous_coreference_rejected": 0,
        "unresolved_coreference_rejected": 0,
    }
    links = {
        link.coreference_id: link
        for link in result.coreference_links
        if link.method is CoreferenceMethod.DETERMINISTIC_DISCOURSE
    }
    for link in links.values():
        if link.status is CoreferenceStatus.RESOLVED:
            key = (
                "plural_coreference_resolved"
                if link.grammatical_number is GrammaticalNumber.PLURAL
                else "singular_coreference_resolved"
            )
            counters[key] += 1
        elif link.status is CoreferenceStatus.AMBIGUOUS:
            counters["ambiguous_coreference_rejected"] += 1
        else:
            counters["unresolved_coreference_rejected"] += 1
    return counters
