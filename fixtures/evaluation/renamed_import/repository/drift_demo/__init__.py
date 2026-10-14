"""Owned v2 API with a renamed imported class."""

from collections.abc import Iterable


class TokenJoiner:
    """Join exact token strings with a vertical-bar separator."""

    def join(self, words: Iterable[str]) -> str:
        return "|".join(words)
