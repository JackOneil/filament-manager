import logging
from flask import Flask
from sqlalchemy import text
from database import db
from models import Brand, Material, Color, AppSetting

def run_migrations(app: Flask) -> None:
    """Create tables and run safe ALTER TABLE migrations for existing databases."""
    with app.app_context():
        db.create_all()

        # ── Schema migrations (must run before any ORM queries) ──────────────
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN min_stock_grams FLOAT NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN max_stock_grams FLOAT NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN tag_text TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_stringing TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_adhesion TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_drying TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_profile TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN quality_notes TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN recommended_nozzle_temp INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN recommended_bed_temp INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE filament ADD COLUMN reorder_alert_snoozed BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN kwh_price FLOAT NOT NULL DEFAULT 5.0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN printer_power INTEGER NOT NULL DEFAULT 150')
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN currency VARCHAR(10) NOT NULL DEFAULT 'CZK'")
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN debug_logging BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN theme VARCHAR(10) NOT NULL DEFAULT 'light'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN nav_palette VARCHAR(20) NOT NULL DEFAULT 'teal'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN view_mode VARCHAR(10) NOT NULL DEFAULT 'card'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN items_per_page INTEGER NOT NULL DEFAULT 12")
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_auto_sync_enabled BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_auto_sync_interval_minutes INTEGER NOT NULL DEFAULT 60')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_sync_at DATETIME DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_sync_status VARCHAR(255) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_test_at DATETIME DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN bambu_last_test_status VARCHAR(255) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN backup_last_export_at DATETIME DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE app_setting ADD COLUMN backup_last_export_meta TEXT DEFAULT NULL')

        # Billing details
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_name VARCHAR(200) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_street VARCHAR(200) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_city VARCHAR(200) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_zip VARCHAR(20) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_id VARCHAR(50) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_vat_id VARCHAR(50) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN company_bank_account VARCHAR(100) DEFAULT NULL")

        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_title VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_image VARCHAR(500) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN og_description TEXT DEFAULT NULL")
        _safe_alter(app, 'ALTER TABLE project ADD COLUMN tag_text TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN filament_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN project_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN bambu_job_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE movement_history ADD COLUMN note TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE project ADD COLUMN owner_user_id INTEGER DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE project ADD COLUMN owner_name VARCHAR(120) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE project ADD COLUMN created_by_user_id INTEGER DEFAULT NULL')

        # Index creations
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_status ON project (status)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_due_date ON project (due_date)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_created_at ON project (created_at)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_bambu_print_job_status ON bambu_print_job (status)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_bambu_print_job_project_id ON bambu_print_job (project_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_filament_project_id ON project_filament (project_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_filament_filament_id ON project_filament (filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_prusa_print_job_status ON prusa_print_job (status)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_prusa_print_job_printer_id ON prusa_print_job (printer_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_movement_history_project_id ON movement_history (project_id)')
        # Redundant for new DBs (columns have index=True in models.py) but kept for legacy migration compatibility
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_audit_log_created_at ON audit_log (created_at)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_audit_log_user_id ON audit_log (user_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_audit_log_endpoint ON audit_log (endpoint)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_audit_log_object ON audit_log (object_type, object_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_movement_history_action_type ON movement_history (action_type)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_movement_history_filament_name ON movement_history (filament_name)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_bambu_job_material_job_id ON bambu_job_material (job_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_bambu_print_job_filament_id ON bambu_print_job (filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_prusa_print_job_filament_id ON prusa_print_job (filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_filament_brand_color_material ON filament (brand_id, color_id, material_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_movement_history_fil_action_created ON movement_history (filament_id, action_type, created_at)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_quote_project_filament ON project_quote (project_id, filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_project_file_project_parent ON project_file (project_id, parent_file_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_storage_placement_shelf_filament ON storage_placement (shelf_id, filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_bambu_job_material_filament_id ON bambu_job_material (filament_id)')
        _safe_alter(app, 'CREATE INDEX IF NOT EXISTS ix_waste_record_filament_project ON waste_record (filament_id, project_id)')

        # Bambu Lab Cloud integration
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN bambu_token TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN bambu_region VARCHAR(10) NOT NULL DEFAULT 'global'")
        _safe_alter(app, "ALTER TABLE bambu_print_job ADD COLUMN cost_time INTEGER DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_link ADD COLUMN domain VARCHAR(100) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE filament ADD COLUMN shop_url TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN reorder_shop_url TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE brand ADD COLUMN shop_url TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE bambu_printer ADD COLUMN pre_job_time_minutes INTEGER NOT NULL DEFAULT 0")

        # PrusaLink integration
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN notes TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1")
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN last_sync_at DATETIME DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN last_success_at DATETIME DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN last_sync_status VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_print_job ADD COLUMN progress FLOAT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_print_job ADD COLUMN raw_payload TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN section_permissions TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN notify_project_created BOOLEAN NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN notify_project_status_changed BOOLEAN NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN notify_project_comment BOOLEAN NOT NULL DEFAULT 1')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN last_login_at DATETIME DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN preferred_language VARCHAR(10) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE user ADD COLUMN preferred_theme VARCHAR(10) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE user_invite ADD COLUMN email VARCHAR(255) DEFAULT NULL')
        _safe_alter(app, "ALTER TABLE user_invite ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
        _safe_alter(app, 'ALTER TABLE user_invite ADD COLUMN section_permissions TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE user_invite ADD COLUMN is_used BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE user_invite ADD COLUMN expires_at DATETIME DEFAULT NULL')
        _safe_alter(app, "ALTER TABLE notification ADD COLUMN kind VARCHAR(50) NOT NULL DEFAULT 'info'")
        _safe_alter(app, 'ALTER TABLE notification ADD COLUMN body TEXT DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE notification ADD COLUMN link VARCHAR(500) DEFAULT NULL')
        _safe_alter(app, 'ALTER TABLE notification ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0')
        _safe_alter(app, 'ALTER TABLE project_comment ADD COLUMN updated_at DATETIME DEFAULT NULL')

        # ── Invoice / document numbering ─────────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN invoice_prefix VARCHAR(20) NOT NULL DEFAULT 'FV'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN invoice_counter INTEGER NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE project_quote ADD COLUMN invoice_number VARCHAR(50) DEFAULT NULL")

        # ── Display timezone ─────────────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN app_timezone VARCHAR(50) NOT NULL DEFAULT 'Europe/Prague'")

        # ── Onboarding checklist ─────────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN onboarding_dismissed BOOLEAN NOT NULL DEFAULT 0")

        # ── Audit logging toggle ─────────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN audit_logging_enabled BOOLEAN NOT NULL DEFAULT 1")

        # ── Auto filament mapping ─────────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN auto_filament_mapping_enabled BOOLEAN NOT NULL DEFAULT 1")

        # ── Automatic backup configuration ─────────────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_enabled BOOLEAN NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_frequency VARCHAR(10) NOT NULL DEFAULT 'weekly'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_time VARCHAR(5) NOT NULL DEFAULT '03:00'")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_day INTEGER NOT NULL DEFAULT 1")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_include_files BOOLEAN NOT NULL DEFAULT 1")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_last_run_at DATETIME DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_keep_count INTEGER NOT NULL DEFAULT 10")
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN backup_auto_keep_days INTEGER NOT NULL DEFAULT 0")

        # ── Customizable waste reasons (JSON array) ──────────────────────────
        _safe_alter(app, "ALTER TABLE app_setting ADD COLUMN waste_reasons_json TEXT DEFAULT ''")

        # ── Project file versioning ──────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN parent_file_id INTEGER DEFAULT NULL")

        # ── Printer maintenance recurrence ───────────────────────────────────
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN recurrence_type VARCHAR(20) NOT NULL DEFAULT 'none'")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN recurrence_value INTEGER NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN recurrence_enabled BOOLEAN NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN notes_is_markdown BOOLEAN NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN fault_resolved BOOLEAN NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN fault_resolved_at DATETIME DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN predictive_enabled BOOLEAN NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN predictive_runtime_hours FLOAT NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN predictive_jobs_count INTEGER NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN predictive_filament_grams FLOAT NOT NULL DEFAULT 0")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN predictive_window_days INTEGER NOT NULL DEFAULT 30")
        _safe_alter(app, "ALTER TABLE printer_maintenance ADD COLUMN last_renewed_at DATETIME DEFAULT NULL")

        # ── Printer Specific Power Profile ───────────────────────────────────
        _safe_alter(app, "ALTER TABLE bambu_printer ADD COLUMN power_draw_watts INTEGER DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE prusa_printer ADD COLUMN power_draw_watts INTEGER DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_todo ADD COLUMN due_date DATE DEFAULT NULL")

        # ── Project extended fields ───────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE project ADD COLUMN priority VARCHAR(10) NOT NULL DEFAULT 'medium'")
        _safe_alter(app, "ALTER TABLE project ADD COLUMN client_email VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project ADD COLUMN client_phone VARCHAR(50) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project ADD COLUMN share_token VARCHAR(64) DEFAULT NULL")

        # ── Project File central model browser fields ─────────────────────────
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN display_name VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN file_size_bytes BIGINT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN mime_type VARCHAR(120) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN checksum_sha256 VARCHAR(64) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN thumbnail_path VARCHAR(255) DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN version_note TEXT DEFAULT NULL")
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN uploaded_by_user_id INTEGER DEFAULT NULL")

        # ── Project File share token ──────────────────────────────────────────
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN share_token VARCHAR(64)")

        # ── Project File model-level note ─────────────────────────────────────
        _safe_alter(app, "ALTER TABLE project_file ADD COLUMN model_note TEXT")

        # ── Allow project_file.project_id to be NULL (unassigned models) ─────
        _migrate_nullable_project_id(app)


        # ── Add ondelete=CASCADE to waste_record.filament_id FK ──────────────
        _migrate_waste_record_fk(app)

        # ── Add ondelete=SET NULL to movement_history and bambu_job_material ──
        # NOTE: SQLite cannot ALTER TABLE to add FK constraints. The model
        # changes (models.py lines 157-159, 516) apply to fresh databases
        # created via ``db.create_all()``.  Existing databases with FK
        # enforcement (BUG-003) will raise ``IntegrityError`` when attempting
        # to delete a parent row — which is safe (prevents data loss) but not
        # the same as SET NULL.  Table recreation is possible but skipped here
        # because ``movement_history`` is a large, frequently-written table.
        # See ``_migrate_waste_record_fk`` above for the pattern.


        # ── Seed data (only runs once on fresh database) ─────────────────────
        if not Brand.query.first():
            for name in ['Prusament', 'Hatchbox', 'eSUN', 'Sunlu', 'Polymaker', 'Overture', 'Spectrum', 'Fiberlogy']:
                db.session.add(Brand(name=name))
            for name in ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PC', 'Nylon']:
                db.session.add(Material(name=name))
            for name, hex_val in [
                ('Černá', '#000000'), ('Bílá', '#FFFFFF'), ('Šedá', '#808080'),
                ('Červená', '#FF0000'), ('Modrá', '#0000FF'), ('Zelená', '#00FF00'),
                ('Žlutá', '#FFFF00'), ('Oranžová', '#FFA500'), ('Fialová', '#800080'),
                ('Průhledná', '#edf2f7'), ('Stříbrná', '#C0C0C0'), ('Zlatá', '#FFD700'),
            ]:
                db.session.add(Color(name=name, hex_value=hex_val))
            db.session.commit()

        if not AppSetting.query.first():
            db.session.add(AppSetting(lang='cs', kwh_price=5.0, printer_power=150,
                                      currency='CZK', debug_logging=False, theme='light', nav_palette='teal', view_mode='card', items_per_page=12))
        setting = AppSetting.query.first()
        if setting and setting.debug_logging:
            app.logger.setLevel(logging.DEBUG)
        else:
            app.logger.setLevel(logging.INFO)

        # ── Backfill missing metadata for project files ──────────────────────
        from models import ProjectFile
        import os
        import hashlib
        import mimetypes
        try:
            files_to_backfill = ProjectFile.query.filter(
                (ProjectFile.file_size_bytes.is_(None)) | 
                (ProjectFile.file_size_bytes == 0) | 
                (ProjectFile.checksum_sha256.is_(None)) |
                (ProjectFile.display_name.is_(None))
            ).all()
            if files_to_backfill:
                app.logger.info(f"Backfilling metadata for {len(files_to_backfill)} project files...")
                updated_count = 0
                for f in files_to_backfill:
                    if not f.filepath:
                        continue
                    if os.path.exists(f.filepath):
                        try:
                            size = os.path.getsize(f.filepath)
                            sha = hashlib.sha256()
                            with open(f.filepath, 'rb') as fh:
                                while chunk := fh.read(8192):
                                    sha.update(chunk)
                            checksum = sha.hexdigest()
                            
                            f.file_size_bytes = size
                            if not f.checksum_sha256:
                                f.checksum_sha256 = checksum
                            if not f.display_name:
                                f.display_name = f.filename.rsplit('.', 1)[0] if '.' in f.filename else f.filename
                            if not f.mime_type:
                                f.mime_type = mimetypes.guess_type(f.filename)[0] or 'application/octet-stream'
                            updated_count += 1
                        except Exception as e:
                            app.logger.error(f"Failed to backfill metadata for file {f.id}: {e}")
                if updated_count > 0:
                    db.session.commit()
                    app.logger.info(f"Successfully backfilled metadata for {updated_count} files.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error during project files metadata backfill: {e}")



def _safe_alter(app: Flask, sql: str) -> None:
    """Run a schema migration SQL inside the already-active app context."""
    try:
        db.session.execute(text(sql))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        message = str(e).lower()
        if 'duplicate column name' in message or 'already exists' in message:
            app.logger.debug(f"Skipping existing schema change for '{sql}'")
        else:
            app.logger.error(f"Error in _safe_alter executing '{sql}': {e}")


def _migrate_nullable_project_id(app: Flask) -> None:
    """Recreate project_file table with project_id nullable (SQLite-safe)."""
    try:
        # Check if already migrated
        result = db.session.execute(text("PRAGMA table_info(project_file)"))
        for row in result:
            if row[1] == 'project_id' and row[3] == 0:  # notnull=0 means already nullable
                return
        # Recreate table: create new, copy data, drop old, rename
        db.session.execute(text("""
            CREATE TABLE project_file_new (
                id INTEGER NOT NULL,
                project_id INTEGER,
                filename VARCHAR(255) NOT NULL,
                filepath VARCHAR(255) NOT NULL,
                uploaded_at DATETIME,
                version INTEGER NOT NULL DEFAULT 1,
                parent_file_id INTEGER,
                display_name VARCHAR(255),
                file_size_bytes BIGINT,
                mime_type VARCHAR(120),
                checksum_sha256 VARCHAR(64),
                thumbnail_path VARCHAR(255),
                version_note TEXT,
                model_note TEXT,
                uploaded_by_user_id INTEGER,
                share_token VARCHAR(64),
                PRIMARY KEY (id),
                FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
                FOREIGN KEY (parent_file_id) REFERENCES project_file (id) ON DELETE CASCADE,
                FOREIGN KEY (uploaded_by_user_id) REFERENCES user (id) ON DELETE SET NULL
            )
        """))
        db.session.execute(text("""
            INSERT INTO project_file_new SELECT * FROM project_file
        """))
        db.session.execute(text("DROP TABLE project_file"))
        db.session.execute(text("ALTER TABLE project_file_new RENAME TO project_file"))
        db.session.commit()
        app.logger.info("Successfully migrated project_file.project_id to nullable.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error migrating project_file nullable project_id: {e}")


def _migrate_waste_record_fk(app: Flask) -> None:
    """Recreate waste_record table with ondelete=CASCADE on filament_id FK.

    The current model defines ``ondelete='CASCADE'`` on the FK, but legacy
    databases created before this migration have no ON DELETE clause on
    the ``filament_id`` column.  Since SQLite cannot ``ALTER TABLE … ADD
    CONSTRAINT``, we rebuild the table in place.

    We also rebuild ``waste_file`` (which has an FK pointing back to
    ``waste_record.id``) so the recreation is safe.
    """
    try:
        # Check whether the FK already includes ON DELETE CASCADE.
        result = db.session.execute(text("PRAGMA foreign_key_list(waste_record)"))
        for row in result:
            if row[3] == 'filament_id' and row[5] is not None:
                return  # already correct

        # Enable FK checks temporarily so the INSERT below validates.
        db.session.execute(text("PRAGMA foreign_keys=OFF"))

        # 1. Recreate waste_file first (depends on waste_record)
        db.session.execute(text("""
            CREATE TABLE waste_file_new (
                id INTEGER NOT NULL,
                waste_record_id INTEGER NOT NULL,
                filename VARCHAR(255) NOT NULL,
                filepath VARCHAR(255) NOT NULL,
                uploaded_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY (waste_record_id) REFERENCES waste_record (id) ON DELETE CASCADE
            )
        """))
        db.session.execute(text("INSERT INTO waste_file_new SELECT * FROM waste_file"))
        db.session.execute(text("DROP TABLE waste_file"))
        db.session.execute(text("ALTER TABLE waste_file_new RENAME TO waste_file"))

        # 2. Recreate waste_record with proper FK constraints
        db.session.execute(text("""
            CREATE TABLE waste_record_new (
                id INTEGER NOT NULL,
                filament_id INTEGER NOT NULL,
                project_id INTEGER,
                reason VARCHAR(50) NOT NULL DEFAULT 'other',
                weight_grams FLOAT NOT NULL DEFAULT 0.0,
                notes TEXT,
                created_at DATETIME NOT NULL,
                recorded_by_user_id INTEGER,
                PRIMARY KEY (id),
                FOREIGN KEY (filament_id) REFERENCES filament (id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE SET NULL,
                FOREIGN KEY (recorded_by_user_id) REFERENCES user (id) ON DELETE SET NULL
            )
        """))
        db.session.execute(text("INSERT INTO waste_record_new SELECT * FROM waste_record"))
        db.session.execute(text("DROP TABLE waste_record"))
        db.session.execute(text("ALTER TABLE waste_record_new RENAME TO waste_record"))

        db.session.execute(text("PRAGMA foreign_keys=ON"))
        db.session.commit()
        app.logger.info("Successfully migrated waste_record.filament_id FK to ON DELETE CASCADE.")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error migrating waste_record FK: {e}")
        try:
            db.session.execute(text("PRAGMA foreign_keys=ON"))
        except Exception:
            pass
