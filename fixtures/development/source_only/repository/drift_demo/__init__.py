"""Small token-position and text-summary utilities."""

from collections import defaultdict
from collections.abc import Iterable


class OccurrenceIndex:
    """Build an inverted index of exact token values."""

    def positions(self, words: Iterable[str], *, include_empty: bool = False) -> dict[str, list[int]]:
        """Return zero-based input positions; empty tokens are omitted by default."""
        result = defaultdict(list)
        for position, word in enumerate(words):
            if word or include_empty:
                result[word].append(position)
        return dict(result)


class TokenMetrics:
    """Describe token and character counts without constructing an index."""

    def measure(self, words: Iterable[str]) -> dict[str, int]:
        values = list(words)
        return {"tokens": len(values), "characters": sum(map(len, values))}
