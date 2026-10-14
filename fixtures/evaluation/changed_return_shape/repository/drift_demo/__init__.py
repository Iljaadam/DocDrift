"""Owned v2 API that returns a statistics object instead of a scalar."""

from collections.abc import Iterable


class TokenStats:
    """Report total and distinct token counts."""

    def measure(self, words: Iterable[str]) -> dict[str, int]:
        total = 0
        distinct = set()
        for word in words:
            total += 1
            distinct.add(word)
        return {"total": total, "distinct": len(distinct)}
