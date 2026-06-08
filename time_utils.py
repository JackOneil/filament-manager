"""Shared UTC time helper — used by models.py, utils.py, and all route modules.

Extracted to a leaf module to avoid circular imports:
  - models.py needs utc_now for column defaults
  - utils.py needs utc_now internally and re-exports it for route modules
  - Both models.py and utils.py are imported by many other modules

By putting utc_now() in its own leaf module (with only stdlib deps),
we eliminate the self-imports in utils.py and the duplicate _utc_now()
definition in models.py.

Two flavours are provided:
  - utc_now()          → timezone-aware UTC datetime (recommended)
  - utc_now_naive()    → naive UTC datetime (explicit legacy; prefer aware)
"""
from datetime import datetime, timezone

# Cache the UTC zone to avoid repeated allocations
_UTC = timezone.utc


def utc_now_aware():
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(_UTC)


# utc_now() is now an alias for utc_now_aware() (BUG-514 fix).
# Code that needs a naive datetime for legacy DB comparisons should
# call utc_now_naive() explicitly.
utc_now = utc_now_aware


def utc_now_naive():
    """Return the current UTC time as a naive datetime (no tzinfo).

    **Explicitly legacy.**  Used only where backward compatibility
    with pre-v1.115 database rows is required.  Prefer ``utc_now()``
    for all new code.
    """
    return datetime.now(_UTC).replace(tzinfo=None)
