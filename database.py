"""Database module — shared SQLAlchemy instance with dialect detection.

Supports SQLite (default) and PostgreSQL (via ``DATABASE_URL`` env var).
"""

from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy instance — initialized in app.py via db.init_app(app)
db = SQLAlchemy()


def detect_dialect(uri: str) -> str:
    """Return the database dialect name from a SQLAlchemy URI.

    >>> detect_dialect('sqlite:///data/filament.db')
    'sqlite'
    >>> detect_dialect('postgresql://user:pass@host/dbname')
    'postgresql'
    """
    if not uri:
        return 'sqlite'
    uri_lower = uri.lower()
    if uri_lower.startswith('postgresql://') or uri_lower.startswith('postgres://'):
        return 'postgresql'
    return 'sqlite'


def engine_options_for(dialect: str) -> dict:
    """Return optimal SQLAlchemy engine options for the given dialect.

    SQLite:
        - ``connect_args.timeout``: 30 s (busy timeout)
        - WAL journal mode, optimized cache/mmap via PRAGMA event listener

    PostgreSQL:
        - ``pool_size``: 10 (connection pool base size)
        - ``max_overflow``: 20 (extra connections allowed on peak)
        - ``pool_pre_ping``: True (validate connections before use)
        - ``pool_recycle``: 3600 (close connections older than 1 hour)
    """
    if dialect == 'postgresql':
        return {
            'pool_size': 10,
            'max_overflow': 20,
            'pool_pre_ping': True,
            'pool_recycle': 3600,
        }
    # SQLite defaults
    return {
        'connect_args': {'timeout': 30},
    }


def setup_sqlite_pragmas(dbapi_connection, _connection_record):
    """SQLite PRAGMA event listener — enables WAL, NORMAL sync, large cache, mmap.

    Attached via ``event.listens_for(engine, 'connect')`` for SQLite only.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-16000")
    cursor.execute("PRAGMA mmap_size=268435456")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()
