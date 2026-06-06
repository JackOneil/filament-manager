"""Tests for the refactors introduced alongside this release.

Covers:
* backup path containment (3.7) — symlink + ``..`` escape attempts.
* ``movement_action_label`` i18n fallback (5.11).
* ``_compute_next_auto_backup_run`` scheduling (4.4).
* PWA service-worker cache name derivation.
* Markdown re-export backward-compat (already in test_markdown.py).
"""
import os
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import create_app


# ── 3.7 — backup path safety ──────────────────────────────────────────
class TestBackupPathSafety:
    def test_is_path_inside_accepts_subpath(self, tmp_path):
        sub = tmp_path / "sub" / "file.tar.gz"
        sub.parent.mkdir(parents=True)
        sub.write_bytes(b"x")
        from routes.backup import _is_path_inside
        assert _is_path_inside(str(sub), str(tmp_path)) is True

    def test_is_path_inside_rejects_parent_path(self, tmp_path):
        outside = tmp_path.parent / "evil.tar.gz"
        from routes.backup import _is_path_inside
        assert _is_path_inside(str(outside), str(tmp_path)) is False

    def test_is_path_inside_rejects_prefix_collision(self, tmp_path):
        # /tmp/backup vs /tmp/backup-evil  — the prefix-only check would
        # be fooled; our realpath + os.sep based check is not.
        evil = tmp_path.parent / (tmp_path.name + "-evil" + "/file.tar.gz")
        from routes.backup import _is_path_inside
        assert _is_path_inside(str(evil), str(tmp_path)) is False

    def test_is_path_inside_handles_symlink_escape(self, tmp_path):
        # Realpath: ``link -> /outside`` must not be reported as inside
        # ``tmp_path`` even though the textual path lives inside it.
        outside_dir = tmp_path.parent / "outside_secret"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.tar.gz"
        outside_file.write_bytes(b"secret")

        link_dir = tmp_path / "linkdir"
        link_dir.mkdir()
        link_file = link_dir / "secret.tar.gz"
        try:
            os.symlink(str(outside_file), str(link_file))
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unsupported on this filesystem")

        from routes.backup import _is_path_inside
        # Textual path is inside tmp_path, but realpath is not.
        assert _is_path_inside(str(link_file), str(tmp_path)) is False

    def test_backup_storage_dir_is_realpath(self, tmp_path, monkeypatch):
        # The data dir is created on demand and returned as realpath.
        from routes import backup as backup_mod
        # Re-point __file__ resolution by monkey-patching the module's
        # _BACKUP_STORAGE_DIRNAME constant and calling with our tmp dir
        # would require lots of plumbing.  Simpler: just call the helper
        # and assert it returns a realpath that exists.
        d = backup_mod._backup_storage_dir()
        assert os.path.isdir(d)
        assert os.path.realpath(d) == d


# ── 5.11 — movement_action_label i18n ────────────────────────────────
class TestMovementActionLabelI18n(unittest.TestCase):
    """The label helper should use the i18n table; fall back to a
    title-cased neutral string when no translation is registered."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="refactor-tests-")
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{os.path.join(self.temp_dir, 'test.db')}",
            "PROJECT_UPLOAD_FOLDER": os.path.join(self.temp_dir, "uploads"),
            "WTF_CSRF_ENABLED": False,
        })
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_known_action_returns_translated(self):
        from utils import movement_action_label
        # 'add' has a registered translation in both languages; we
        # don't care which language the test app defaults to — we just
        # want something other than the raw ``add`` token.
        label = movement_action_label("add")
        assert label != "add"
        assert isinstance(label, str) and label

    def test_unknown_action_falls_back_to_titlecase(self):
        from utils import movement_action_label
        # An action not in the translation table.
        label = movement_action_label("some_unmapped_action")
        assert label == "Some Unmapped Action"

    def test_empty_action_returns_empty(self):
        from utils import movement_action_label
        assert movement_action_label("") == ""
        assert movement_action_label(None) == ""


# ── 4.4 — auto-backup scheduling ─────────────────────────────────────
class TestAutoBackupScheduling:
    """``_compute_next_auto_backup_run`` returns the next local-time
    datetime the backup should fire at.  The math must be deterministic
    and produce a target strictly in the future for valid inputs."""

    LOCAL_TZ = ZoneInfo("Europe/Prague")

    def _now(self, year, month, day, hour=12, minute=0):
        return datetime(year, month, day, hour, minute, tzinfo=self.LOCAL_TZ)

    def test_daily_future_target_today(self):
        from app import _compute_next_auto_backup_run
        # It's 02:00, target is 03:00 → next run is today at 03:00.
        now = self._now(2026, 6, 6, 2, 0)
        nxt = _compute_next_auto_backup_run(now, "daily", "03:00", 0)
        assert nxt == self._now(2026, 6, 6, 3, 0)

    def test_daily_target_already_today_past(self):
        from app import _compute_next_auto_backup_run
        # It's 04:00, target is 03:00 → next run is tomorrow 03:00.
        now = self._now(2026, 6, 6, 4, 0)
        nxt = _compute_next_auto_backup_run(now, "daily", "03:00", 0)
        assert nxt == self._now(2026, 6, 7, 3, 0)

    def test_weekly_target_in_future(self):
        from app import _compute_next_auto_backup_run
        # 2026-06-06 is a Saturday (weekday=5).  Target day=2 (Tuesday)
        # so the next run is 4 days later: 2026-06-10.
        now = self._now(2026, 6, 6, 2, 0)
        nxt = _compute_next_auto_backup_run(now, "weekly", "03:00", 2)
        assert nxt == self._now(2026, 6, 10, 3, 0)

    def test_weekly_target_is_today(self):
        from app import _compute_next_auto_backup_run
        # 2026-06-06 is a Saturday (weekday=5).  Target day=5 (Saturday).
        # Now is 02:00, target is 03:00 today.
        now = self._now(2026, 6, 6, 2, 0)
        nxt = _compute_next_auto_backup_run(now, "weekly", "03:00", 5)
        assert nxt == self._now(2026, 6, 6, 3, 0)

    def test_weekly_target_today_already_past(self):
        from app import _compute_next_auto_backup_run
        # 2026-06-06 Saturday 04:00 — target Saturday 03:00 is past, so
        # the next run is *next* Saturday.
        now = self._now(2026, 6, 6, 4, 0)
        nxt = _compute_next_auto_backup_run(now, "weekly", "03:00", 5)
        assert nxt == self._now(2026, 6, 13, 3, 0)

    def test_monthly_target_clamped_to_last_day(self):
        from app import _compute_next_auto_backup_run
        # Target day=31 in February 2026 → clamped to 28.
        now = self._now(2026, 2, 1, 2, 0)
        nxt = _compute_next_auto_backup_run(now, "monthly", "03:00", 31)
        assert nxt == self._now(2026, 2, 28, 3, 0)

    def test_monthly_target_same_day_in_future(self):
        from app import _compute_next_auto_backup_run
        # Now is the 6th at 02:00, target is the 15th.
        now = self._now(2026, 6, 6, 2, 0)
        nxt = _compute_next_auto_backup_run(now, "monthly", "03:00", 15)
        assert nxt == self._now(2026, 6, 15, 3, 0)

    def test_monthly_target_same_day_past(self):
        from app import _compute_next_auto_backup_run
        # Now is the 15th at 04:00, target is the 15th at 03:00 → next month.
        now = self._now(2026, 6, 15, 4, 0)
        nxt = _compute_next_auto_backup_run(now, "monthly", "03:00", 15)
        assert nxt == self._now(2026, 7, 15, 3, 0)

    def test_invalid_time_returns_none(self):
        from app import _compute_next_auto_backup_run
        assert _compute_next_auto_backup_run(self._now(2026, 6, 6), "daily", "25:00", 0) is None
        assert _compute_next_auto_backup_run(self._now(2026, 6, 6), "daily", "nope", 0) is None

    def test_invalid_frequency_returns_none(self):
        from app import _compute_next_auto_backup_run
        assert _compute_next_auto_backup_run(self._now(2026, 6, 6), "yearly", "03:00", 0) is None


# ── 5.12 — PWA service worker cache name ─────────────────────────────
class TestPwaServiceWorker:
    def test_cache_name_includes_version(self):
        from routes.pwa import _sw_cache_name
        from flask import Flask
        app = Flask(__name__)
        app.config["APP_VERSION"] = "9.42.1"
        with app.app_context():
            assert _sw_cache_name() == "filament-manager-v9-static"

    def test_cache_name_handles_missing_version(self):
        from routes.pwa import _sw_cache_name
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            assert _sw_cache_name() == "filament-manager-v0-static"
