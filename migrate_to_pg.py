#!/usr/bin/env python3
"""
One-shot migration: SQLite → PostgreSQL.

Strategy: disable FK triggers, batch-import all rows with boolean
conversion, then re-enable FKs and reset sequences.

Quotes all table/column names to handle PostgreSQL reserved words
(e.g. ``user``, ``session``).

Usage: docker exec filament_app python3 migrate_to_pg.py
"""

import os

os.environ['DATABASE_URL'] = 'postgresql://filament:filament@postgres:5432/filament'

from sqlalchemy import create_engine, text
from flask import Flask
from database import db

pg_app = Flask(__name__)
pg_app.config['SECRET_KEY'] = 'migration'
pg_app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
pg_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
pg_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5, 'max_overflow': 10, 'pool_pre_ping': True,
}
db.init_app(pg_app)

from models import *  # noqa: F401,F403  — register models with db

TABLES = [
    'brand', 'color', 'material',
    'user', 'user_session', 'user_invite', 'notification', 'audit_log',
    'app_setting',
    'filament', 'movement_history', 'filament_undo_log',
    'storage_shelf', 'storage_placement',
    'print_history',
    'project', 'project_file', 'project_link', 'project_filament',
    'project_quote', 'project_comment', 'project_comment_reaction',
    'project_todo', 'project_template', 'project_print_item',
    'model_category', 'model_comment',
    'bambu_printer', 'bambu_print_job', 'bambu_job_material',
    'prusa_printer', 'prusa_print_job',
    'printer_maintenance',
    'waste_record', 'waste_file',
]

SQLITE_PATH = '/app/data/filament.db'
sqlite_engine = create_engine(f'sqlite:///{SQLITE_PATH}', connect_args={'timeout': 30})

# Helper that quotes identifiers to avoid reserved-word conflicts in PG.
def _q(identifier: str) -> str:
    return f'"{identifier}"'


def get_bool_cols():
    with pg_app.app_context():
        rows = db.session.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND data_type = 'boolean'
        """)).fetchall()
    bm = {}
    for tn, cn in rows:
        bm.setdefault(tn, set()).add(cn)
    return bm


def main():
    with pg_app.app_context():
        # 1. Create fresh schema
        print("Creating schema...")
        db.create_all()
        print("Schema ready.")

        # 2. Discover boolean columns + clear
        bool_cols = get_bool_cols()
        total = sum(len(v) for v in bool_cols.values())
        print(f"Detected {total} boolean columns across {len(bool_cols)} tables.")

        print("Clearing tables...")
        for tn in reversed(TABLES):
            try:
                db.session.execute(text(f'DELETE FROM {_q(tn)}'))
                db.session.commit()
            except Exception:
                db.session.rollback()

        # 3. Disable FK triggers
        print("Disabling FK triggers...")
        db.session.execute(text("SET session_replication_role = 'replica'"))
        db.session.commit()

        # 4. Read SQLite
        print(f"\nReading SQLite ({SQLITE_PATH})...")
        sqlite_data = {}
        with sqlite_engine.connect() as src:
            for tn in TABLES:
                try:
                    res = src.execute(text(f'SELECT * FROM {_q(tn)}'))
                    rows = res.fetchall()
                    cols = list(res.keys())
                    data = [dict(zip(cols, r)) for r in rows]

                    pb = bool_cols.get(tn, set())
                    for row in data:
                        for c in pb:
                            if c in row and row[c] is not None:
                                row[c] = bool(int(row[c]))

                    sqlite_data[tn] = {'columns': cols, 'rows': data}
                    print(f"  {tn}: {len(rows)} rows")
                except Exception as e:
                    print(f"  {tn}: SKIP ({e})")
                    sqlite_data[tn] = {'columns': [], 'rows': []}

        # 5. Write to PostgreSQL
        print("\nWriting to PostgreSQL...")
        errors = []
        for tn in TABLES:
            info = sqlite_data.get(tn, {'columns': [], 'rows': []})
            rows = info['rows']
            cols = info['columns']
            if not rows:
                continue
            try:
                clist = ', '.join(_q(c) for c in cols)
                phs = ', '.join(f':{c}' for c in cols)
                sql = f'INSERT INTO {_q(tn)} ({clist}) VALUES ({phs})'
                db.session.execute(text(sql), rows)
                db.session.commit()
                print(f"  {tn}: {len(rows)} rows ✓")
            except Exception as e:
                db.session.rollback()
                msg = f"  {tn}: FAILED — {e}"
                print(msg)
                errors.append(msg)

        # 6. Re-enable FK triggers
        print("\nRe-enabling FK triggers...")
        db.session.execute(text("SET session_replication_role = 'origin'"))
        db.session.commit()

        # 7. Reset sequences
        print("Resetting sequences...")
        for tn in TABLES:
            try:
                db.session.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{tn}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {_q(tn)}), 1), true)"
                ))
            except Exception:
                pass
        db.session.commit()

        # 8. Verify
        print("\n=== Verification ===")
        ok = fail = 0
        for tn in TABLES:
            try:
                pg_count = db.session.execute(
                    text(f'SELECT COUNT(*) FROM {_q(tn)}')
                ).scalar()
                sql_count = len(sqlite_data.get(tn, {}).get('rows', []))
                if pg_count == sql_count:
                    ok += 1
                    if pg_count > 0:
                        print(f"  {tn}: {pg_count} rows ✓")
                else:
                    fail += 1
                    print(f"  {tn}: PG={pg_count} SQLite={sql_count} MISMATCH")
            except Exception as e:
                fail += 1
                print(f"  {tn}: ERROR - {e}")

        print(f"\nResults: {ok} tables OK, {fail} mismatches")
        if errors:
            for e in errors:
                print(e)
        else:
            print("✅ Migration complete!")


if __name__ == '__main__':
    main()
