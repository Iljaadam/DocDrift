"""Small owned API used by the renamed-method documentation fixture."""

from collections.abc import Iterable


class WordCounter:
    """Count exact string values; case, whitespace, and Unicode are preserved."""

    def count(self, words: Iterable[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for word in words:
            if not isinstance(word, str):
                raise TypeError("words must contain only strings")
            counts[word] = counts.get(word, 0) + 1
        return counts
