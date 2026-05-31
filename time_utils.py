"""Shared UTC time helper — used by models.py, utils.py, and all route modules.

Extracted to a leaf module to avoid circular imports:
  - models.py needs utc_now for column defaults
  - utils.py needs utc_now internally and re-exports it for route modules
  - Both models.py and utils.py are imported by many other modules

By putting utc_now() in its own leaf module (with only stdlib deps),
we eliminate the self-imports in utils.py and the duplicate _utc_now()
definition in models.py.
"""
from datetime import datetime, timezone


def utc_now():
    """Return the current UTC time as a naive datetime (no tzinfo).

    Replacement for datetime.utcnow() which is deprecated in Python 3.12
    and will be removed in Python 3.14.
    Returns a naive (tzinfo-free) datetime to keep compatibility with the existing
    SQLite schema which stores all timestamps without timezone info.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
