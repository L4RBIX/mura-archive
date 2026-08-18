from mura.linguistics.common import ScriptBucket, detect_script
from mura.linguistics.multilingual import find_known_name_matches


def test_script_detection_distinguishes_cyrillic_latin_and_mixed() -> None:
    assert detect_script("Ерлан") is ScriptBucket.CYRILLIC
    assert detect_script("Erlan") is ScriptBucket.LATIN
    assert detect_script("ЕрланErlan") is ScriptBucket.MIXED


def test_kazakh_context_does_not_emit_russian_or_english_name_rules() -> None:
    matches = find_known_name_matches("Сапардың інісі Нұрғали.", "Нұрғали")

    assert [(match.language, match.rule_id) for match in matches] == [("kk", "kk.name.exact.v1")]


def test_russian_context_uses_russian_name_inflection() -> None:
    matches = find_known_name_matches("Жена Ерлана — Динара.", "Ерлан")

    assert [(match.language, match.rule_id) for match in matches] == [
        ("ru", "ru.name.audited_inflection.v1")
    ]


def test_latin_name_routes_only_to_english_rules() -> None:
    matches = find_known_name_matches("Erlan's wife is Dinara.", "Erlan")

    assert [(match.language, match.rule_id) for match in matches] == [
        ("en", "en.name.possessive.v1")
    ]
