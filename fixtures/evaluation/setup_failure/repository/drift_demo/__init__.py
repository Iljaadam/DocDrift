"""Owned package whose declared build prerequisite is deliberately missing."""


class TokenIdentity:
    def echo(self, words: list[str]) -> list[str]:
        return list(words)
