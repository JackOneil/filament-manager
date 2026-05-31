"""Shared UTC time helper — used by models.py, utils.py, and all route modules.

Extracted to a leaf module to avoid circular imports:
  - models.py needs utc_now for column defaults
  - utils.py needs utc_now internally and re-exports it for route modules
  - Both models.py and utils.py are imported by many other modules

By putting utc_now() in its own leaf module (with only stdlib deps),
we eliminate the self-imports in utils.py and the duplicate _utc_now()
definition in models.py.

Two flavours are provided:
  - utc_now()          → timezone-aware UTC datetime (recommended for new code)
  - utc_now_naive()    → naive UTC datetime (legacy compatibility; for comparisons
                          against old database records that lack timezone info)
"""
from datetime import datetime, timezone

# Cache the UTC zone to avoid repeated allocations
_UTC = timezone.utc


def utc_now_aware():
    """Return the current UTC time as a timezone-aware datetime.

    This is the recommended form for all new code, column defaults in
    models.py, and any arithmetic involving time deltas.  SQLAlchemy
    serialises aware datetimes with their timezone offset into SQLite,
    so the information is preserved round-trip.
    """
    return datetime.now(_UTC)


def utc_now():
    """Return the current UTC time as a naive datetime (no tzinfo).

    **Deprecated:** kept for backward compatibility with existing database
    records that were stored without timezone information.  Prefer
    ``utc_now_aware()`` for new code and column defaults.
    """
    return datetime.now(_UTC).replace(tzinfo=None)
