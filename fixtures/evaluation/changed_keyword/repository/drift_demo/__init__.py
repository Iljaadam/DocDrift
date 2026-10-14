"""Owned v2 API with a changed keyword parameter."""

from collections.abc import Iterable


class TokenOrderer:
    """Sort exact token values in Python string order."""

    def sort(self, words: Iterable[str], *, descending: bool = False) -> list[str]:
        return sorted(words, reverse=descending)
