"""Which Xero scopes a connection holds.

Writing accounts needs `accounting.settings`; `accounting.settings.read` is not
enough. Compare whole tokens, never substrings (".read" contains the write name).
"""

WRITE_SCOPE = "accounting.settings"


def granted(scopes: str) -> set[str]:
    return set((scopes or "").split())


def can_write(scopes: str) -> bool:
    return WRITE_SCOPE in granted(scopes)
