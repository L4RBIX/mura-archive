from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteScope:
    scope_id: str
    malformed: bool = False


_OUTSIDE_SCOPE = QuoteScope("outside")
_OPEN_TO_CLOSE = {
    "«": "»",
    "“": "”",
    "„": "“",
}
_SYMMETRIC_QUOTES = {'"'}


def quote_scope_at(text: str, position: int) -> QuoteScope:
    """Return a deterministic quote scope for one character position.

    Malformed or nested quote structures are fail-closed: they receive a unique
    non-outside scope and therefore cannot authorize cross-boundary coreference.
    """

    bounded = max(0, min(position, len(text)))
    stack: list[tuple[str, str]] = []
    next_id = 1
    malformed = False

    for index, char in enumerate(text[:bounded]):
        if char in _OPEN_TO_CLOSE:
            stack.append((_OPEN_TO_CLOSE[char], f"quote_{next_id}"))
            next_id += 1
            continue
        if char in _SYMMETRIC_QUOTES:
            if stack and stack[-1][0] == char:
                stack.pop()
            else:
                stack.append((char, f"quote_{next_id}"))
                next_id += 1
            continue
        if char in _OPEN_TO_CLOSE.values():
            if stack and stack[-1][0] == char:
                stack.pop()
            else:
                malformed = True
                stack.append(("", f"malformed_quote_{index}"))

    if not stack:
        return QuoteScope("outside", malformed=malformed)
    return QuoteScope(stack[-1][1], malformed=malformed)


def quote_scope_for_span(text: str, start: int, end: int) -> QuoteScope:
    positions = [
        index for index in range(max(0, start), min(len(text), end)) if not text[index].isspace()
    ]
    if not positions:
        return quote_scope_at(text, start)
    scopes = {quote_scope_at(text, index).scope_id for index in positions}
    if len(scopes) != 1:
        return QuoteScope("mixed_quote_scope", malformed=True)
    scope_id = next(iter(scopes))
    malformed = any(quote_scope_at(text, index).malformed for index in positions)
    return QuoteScope(scope_id, malformed=malformed)


def is_outside_quote(scope: QuoteScope) -> bool:
    return scope.scope_id == _OUTSIDE_SCOPE.scope_id and not scope.malformed
