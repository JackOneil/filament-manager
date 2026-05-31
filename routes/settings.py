"""Settings, dictionary management, integrations, and theme routes."""
import logging
import re
from datetime import timedelta

import requests
from flask import render_template, request, redirect, url_for, Blueprint, flash, jsonify
from database import db
from auth import get_current_user
from models import (
    Brand, Color, Material, AppSetting, Filament, Project,
    BambuPrinter, PrusaPrinter, User,
)
from utils import (
    bambu_api_base,
    build_action_center,
    decrypt_token,
    encrypt_token,
    format_tags,
    parse_sync_status,
    prusa_test_connection,
    remove_tag,
    top_tags,
    utc_now,
    validate_printer_host,
)


def _get_or_create_settings():
    setting = AppSetting.query.first()
    if setting is None:
        setting = AppSetting()
        db.session.add(setting)
        db.session.flush()
    return setting


def _tab_for_action(action):
    dict_actions = {
        'brand', 'color', 'material',
        'edit_brand', 'edit_material', 'edit_color',
        'delete_brand', 'delete_material', 'delete_color',
    }
    printers_actions = {
        'printer_energy_settings',
        'edit_bambu_printer', 'delete_bambu_printer',
        'add_prusa_printer', 'edit_prusa_printer', 'delete_prusa_printer',
    }
    integrations_actions = {
        'bambu_cloud_settings', 'bambu_cloud_disconnect',
        'reorder_shop_settings',
        'delete_filament_tag', 'delete_project_tag',
    }
    company_actions = {'billing_settings'}
    data_actions = {'backup_auto_settings'}  # auto-backup settings go to data tab

    if action in dict_actions:
        return 'dicts'
    if action in printers_actions:
        return 'printers'
    if action in integrations_actions:
        return 'integrations'
    if action in company_actions:
        return 'company'
    if action in data_actions:
        return 'data'
    return 'general'


def _is_valid_reorder_template(url_value):
    if not url_value:
        return True
    if not re.match(r'^https://', url_value, re.IGNORECASE):
        return False
    return '{query}' in url_value





def register(app):
    bp = Blueprint('settings', __name__)

    @bp.route('/settings', methods=['GET', 'POST'])
    def settings():
        if request.method == 'POST':
            action = request.form.get('action')
            success_key = 'settings_saved'
            try:
                setting = _get_or_create_settings()
                if action == 'brand':
                    brand_name = request.form.get('name', '').strip()
                    if not brand_name:
                        raise ValueError('settings_brand_required')
                    if Brand.query.filter_by(name=brand_name).first():
                        raise ValueError('settings_brand_exists')
                    db.session.add(Brand(name=brand_name))
                    app.logger.debug(f"Added brand: {brand_name}")

                elif action == 'color':
                    color_name = request.form.get('name', '').strip()
                    color_hex = request.form.get('hex_value', '').strip()
                    if not color_name:
                        raise ValueError('settings_color_required')
                    if Color.query.filter_by(name=color_name).first():
                        raise ValueError('settings_color_exists')
                    db.session.add(Color(name=color_name, hex_value=color_hex))
                    app.logger.debug(f"Added color: {color_name}")

                elif action == 'material':
                    material_name = request.form.get('name', '').strip()
                    if not material_name:
                        raise ValueError('settings_material_required')
                    if Material.query.filter_by(name=material_name).first():
                        raise ValueError('settings_material_exists')
                    db.session.add(Material(name=material_name))
                    app.logger.debug(f"Added material: {material_name}")

                elif action == 'language':
                    old = setting.lang
                    setting.lang = request.form.get('lang', setting.lang)
                    app.logger.debug(f"Language changed: {old} -> {setting.lang}")

                elif action == 'currency':
                    old = setting.currency
                    setting.currency = request.form.get('currency', setting.currency)
                    app.logger.debug(f"Currency changed: {old} -> {setting.currency}")

                elif action == 'items_per_page':
                    setting.items_per_page = request.form.get('items_per_page', setting.items_per_page, type=int)
                    app.logger.debug(f"Items per page changed to: {setting.items_per_page}")

                elif action == 'nav_palette':
                    palette = request.form.get('nav_palette', 'teal').strip().lower()
                    if palette not in {'teal', 'slate', 'ocean', 'sunset'}:
                        palette = 'teal'
                    setting.nav_palette = palette
                    app.logger.debug(f"Navigation palette changed to: {setting.nav_palette}")

                elif action == 'debug_logging':
                    setting.debug_logging = request.form.get('debug_logging') == 'on'
                    if setting.debug_logging:
                        app.logger.setLevel(logging.DEBUG)
                        app.logger.debug("Debug logging enabled.")
                    else:
                        app.logger.setLevel(logging.INFO)

                elif action == 'audit_logging':
                    setting.audit_logging_enabled = request.form.get('audit_logging_enabled') == 'on'
                    app.logger.debug(f"Audit logging {'enabled' if setting.audit_logging_enabled else 'disabled'}.")

                elif action == 'edit_brand':
                    brand = db.session.get(Brand, request.form.get('id', 0, type=int))
                    if brand:
                        old = brand.name
                        brand.name = request.form.get('name', brand.name).strip() or brand.name
                        brand.shop_url = request.form.get('shop_url', '').strip() or None
                        app.logger.debug(f"Brand edited: {old} -> {brand.name}")

                elif action == 'edit_material':
                    mat = db.session.get(Material, request.form.get('id', 0, type=int))
                    if mat:
                        old = mat.name
                        mat.name = request.form.get('name', mat.name).strip() or mat.name
                        app.logger.debug(f"Material edited: {old} -> {mat.name}")

                elif action == 'edit_color':
                    col = db.session.get(Color, request.form.get('id', 0, type=int))
                    if col:
                        col.name = request.form.get('name', col.name).strip() or col.name
                        col.hex_value = request.form.get('hex_value', col.hex_value).strip()
                        app.logger.debug(f"Color edited: {col.name}")

                elif action == 'delete_brand':
                    brand = db.session.get(Brand, request.form.get('id', 0, type=int))
                    if brand and len(brand.filaments) == 0:
                        db.session.delete(brand)
                        app.logger.debug(f"Brand deleted: {brand.name}")

                elif action == 'delete_material':
                    mat = db.session.get(Material, request.form.get('id', 0, type=int))
                    if mat and len(mat.filaments) == 0:
                        db.session.delete(mat)
                        app.logger.debug(f"Material deleted: {mat.name}")

                elif action == 'delete_color':
                    col = db.session.get(Color, request.form.get('id', 0, type=int))
                    if col and len(col.filaments) == 0:
                        db.session.delete(col)
                        app.logger.debug(f"Color deleted: {col.name}")

                elif action == 'delete_filament_tag':
                    tag_name = request.form.get('tag', '').strip()
                    if tag_name:
                        updated_count = 0
                        for filament in Filament.query.all():
                            new_tags = remove_tag(filament.tag_text, tag_name)
                            if new_tags != format_tags(filament.tag_text):
                                filament.tag_text = new_tags or None
                                updated_count += 1
                        app.logger.debug(f"Deleted filament tag '{tag_name}' from {updated_count} filaments")
                        success_key = 'settings_tags_removed'

                elif action == 'delete_project_tag':
                    tag_name = request.form.get('tag', '').strip()
                    if tag_name:
                        updated_count = 0
                        for project in Project.query.all():
                            new_tags = remove_tag(project.tag_text, tag_name)
                            if new_tags != format_tags(project.tag_text):
                                project.tag_text = new_tags or None
                                updated_count += 1
                        app.logger.debug(f"Deleted project tag '{tag_name}' from {updated_count} projects")
                        success_key = 'settings_tags_removed'

                elif action == 'bambu_cloud_settings':
                    token = request.form.get('bambu_token', '').strip()
                    region = request.form.get('bambu_region', 'global')
                    if region not in ('global', 'china'):
                        region = 'global'
                    if token:
                        setting.bambu_token = encrypt_token(token)
                    setting.bambu_region = region
                    setting.bambu_auto_sync_enabled = request.form.get('bambu_auto_sync_enabled') == 'on'
                    setting.bambu_auto_sync_interval_minutes = max(
                        request.form.get('bambu_auto_sync_interval_minutes', setting.bambu_auto_sync_interval_minutes or 60, type=int),
                        5,
                    )
                    setting.auto_filament_mapping_enabled = request.form.get('auto_filament_mapping_enabled') == 'on'
                    app.logger.debug('Bambu Cloud settings updated.')
                    success_key = 'settings_bambu_connection_saved'

                elif action == 'bambu_cloud_disconnect':
                    setting.bambu_token = None
                    app.logger.debug('Bambu Cloud token cleared.')
                    success_key = 'settings_bambu_disconnected'

                elif action == 'edit_bambu_printer':
                    printer = db.session.get(BambuPrinter, request.form.get('id', type=int))
                    if printer:
                        new_name = request.form.get('name', '').strip()
                        if new_name:
                            printer.name = new_name
                        try:
                            printer.pre_job_time_minutes = max(0, int(request.form.get('pre_job_time_minutes', 0)))
                        except (ValueError, TypeError):
                            pass
                        power_raw = request.form.get('power_draw_watts', '').strip()
                        if power_raw:
                            try:
                                printer.power_draw_watts = max(0, int(power_raw))
                            except (ValueError, TypeError):
                                pass
                        else:
                            printer.power_draw_watts = None
                        printer.notes = request.form.get('notes', '').strip() or None
                        app.logger.debug(f"Edited Bambu printer {printer.device_id}: name={printer.name}, pre_job={printer.pre_job_time_minutes}min, power={printer.power_draw_watts}W, notes={printer.notes}")

                elif action == 'delete_bambu_printer':
                    printer = db.session.get(BambuPrinter, request.form.get('id', type=int))
                    if printer:
                        db.session.delete(printer)
                        app.logger.debug(f'Deleted Bambu printer: {printer.name} ({printer.device_id})')

                elif action == 'printer_energy_settings':
                    try:
                        setting.kwh_price = float(request.form.get('kwh_price', setting.kwh_price))
                        setting.printer_power = int(request.form.get('printer_power', setting.printer_power))
                    except (ValueError, TypeError):
                        raise ValueError('settings_invalid_number')
                    app.logger.debug(f"Printer/energy settings updated: kwh={setting.kwh_price}, power={setting.printer_power}W")

                elif action == 'add_prusa_printer':
                    host_raw = request.form.get('host', '').strip()
                    host = validate_printer_host(host_raw)
                    alias = request.form.get('name', '').strip()
                    api_key_raw = request.form.get('api_key', '').strip()
                    if not host or not alias or not api_key_raw:
                        raise ValueError('settings_prusa_required_fields')
                    power_raw = request.form.get('power_draw_watts', '').strip()
                    power_val = None
                    if power_raw:
                        try:
                            power_val = max(0, int(power_raw))
                        except (ValueError, TypeError):
                            raise ValueError('settings_invalid_number')

                    if not app.config.get('TESTING'):
                        test_probe = PrusaPrinter(
                            name=alias,
                            host=host,
                            api_key=encrypt_token(api_key_raw),
                        )
                        test_result = prusa_test_connection(test_probe)
                        if not test_result.get('ok'):
                            raise ValueError('settings_prusa_test_failed')

                    db.session.add(PrusaPrinter(
                        name=alias,
                        host=host,
                        api_key=encrypt_token(api_key_raw),
                        notes=request.form.get('notes', '').strip() or None,
                        power_draw_watts=power_val,
                    ))
                    app.logger.debug(f'Added PrusaLink printer: {alias} @ {host}')
                    success_key = 'settings_prusa_test_passed_saved'

                elif action == 'edit_prusa_printer':
                    printer = db.session.get(PrusaPrinter, request.form.get('id', type=int))
                    if printer:
                        new_name = request.form.get('name', '').strip()
                        new_host = validate_printer_host(request.form.get('host', '').strip())
                        new_key = request.form.get('api_key', '').strip()
                        if new_name:
                            printer.name = new_name
                        if new_host:
                            printer.host = new_host
                        if new_key:
                            printer.api_key = encrypt_token(new_key)
                        power_raw = request.form.get('power_draw_watts', '').strip()
                        if power_raw:
                            try:
                                printer.power_draw_watts = max(0, int(power_raw))
                            except (ValueError, TypeError):
                                pass
                        else:
                            printer.power_draw_watts = None
                        printer.notes = request.form.get('notes', '').strip() or None
                        printer.enabled = request.form.get('enabled') == 'on'
                        app.logger.debug(f'Edited PrusaLink printer id={printer.id}')

                elif action == 'delete_prusa_printer':
                    printer = db.session.get(PrusaPrinter, request.form.get('id', type=int))
                    if printer:
                        db.session.delete(printer)
                        app.logger.debug(f'Deleted PrusaLink printer: {printer.name}')

                elif action == 'reorder_shop_settings':
                    url_raw = request.form.get('reorder_shop_url', '').strip()
                    if not _is_valid_reorder_template(url_raw):
                        raise ValueError('settings_reorder_url_invalid')
                    setting.reorder_shop_url = url_raw or None
                    app.logger.debug(f'Reorder shop URL updated: {setting.reorder_shop_url}')

                elif action == 'app_timezone':
                    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                    tz_raw = request.form.get('app_timezone', '').strip()
                    if tz_raw:
                        try:
                            ZoneInfo(tz_raw)  # validate the zone name
                            setting.app_timezone = tz_raw
                            app.logger.debug(f'App timezone set to: {tz_raw}')
                        except (ZoneInfoNotFoundError, KeyError):
                            raise ValueError('settings_timezone_invalid')

                elif action == 'billing_settings':
                    setting.company_name = request.form.get('company_name', '').strip() or None
                    setting.company_street = request.form.get('company_street', '').strip() or None
                    setting.company_city = request.form.get('company_city', '').strip() or None
                    setting.company_zip = request.form.get('company_zip', '').strip() or None
                    setting.company_id = request.form.get('company_id', '').strip() or None
                    setting.company_vat_id = request.form.get('company_vat_id', '').strip() or None
                    setting.company_bank_account = request.form.get('company_bank_account', '').strip() or None
                    app.logger.debug('Billing settings updated.')

                elif action == 'backup_auto_settings':
                    setting.backup_auto_enabled = request.form.get('backup_auto_enabled') == 'on'
                    freq = request.form.get('backup_auto_frequency', 'weekly').strip()
                    if freq not in ('daily', 'weekly', 'monthly'):
                        freq = 'weekly'
                    setting.backup_auto_frequency = freq
                    time_raw = request.form.get('backup_auto_time', '03:00').strip()
                    # Validate HH:MM format
                    import re as _re
                    if _re.match(r'^\d{2}:\d{2}$', time_raw):
                        setting.backup_auto_time = time_raw
                    day_raw = request.form.get('backup_auto_day', 1, type=int)
                    if freq == 'weekly':
                        # Day of week: 0=Monday ... 6=Sunday
                        setting.backup_auto_day = max(0, min(6, day_raw))
                    elif freq == 'monthly':
                        # Day of month: 1-28 (safe range)
                        setting.backup_auto_day = max(1, min(28, day_raw))
                    else:
                        # daily — not used
                        setting.backup_auto_day = 0
                    setting.backup_auto_include_files = request.form.get('backup_auto_include_files') == 'on'
                    try:
                        setting.backup_auto_keep_count = max(0, int(request.form.get('backup_auto_keep_count', 10)))
                    except (ValueError, TypeError):
                        setting.backup_auto_keep_count = 10
                    try:
                        setting.backup_auto_keep_days = max(0, int(request.form.get('backup_auto_keep_days', 0)))
                    except (ValueError, TypeError):
                        setting.backup_auto_keep_days = 0
                    app.logger.debug(
                        f"Auto-backup settings: enabled={setting.backup_auto_enabled}, "
                        f"freq={setting.backup_auto_frequency}, time={setting.backup_auto_time}, "
                        f"day={setting.backup_auto_day}, files={setting.backup_auto_include_files}, "
                        f"keep_count={setting.backup_auto_keep_count}, keep_days={setting.backup_auto_keep_days}"
                    )
                    success_key = 'backup_auto_settings_saved'

                else:
                    raise ValueError('settings_unknown_action')

                db.session.commit()
                flash(success_key, 'success')
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')
            except Exception:
                db.session.rollback()
                app.logger.exception("Settings action error (action=%s)", action)
                flash('settings_save_failed', 'error')
            tab = _tab_for_action(action)
            return redirect(url_for('settings') + f'?tab={tab}')

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        app_settings = AppSetting.query.first()
        printers = BambuPrinter.query.order_by(BambuPrinter.name).all()
        prusa_printers = PrusaPrinter.query.order_by(PrusaPrinter.name).all()
        filament_tag_cloud = top_tags(Filament.query.all())
        project_tag_cloud = top_tags(Project.query.all())
        bambu_sync_status = parse_sync_status(app_settings.bambu_last_sync_status if app_settings else None)
        prusa_sync_states = {printer.id: parse_sync_status(printer.last_sync_status) for printer in prusa_printers}

        now = utc_now()
        cutoff_24h = now - timedelta(hours=24)
        last_sync_candidates = [
            app_settings.bambu_last_sync_at if app_settings else None,
            *[p.last_sync_at for p in prusa_printers if p.last_sync_at],
        ]
        last_sync_candidates = [ts for ts in last_sync_candidates if ts is not None]
        last_sync_at = max(last_sync_candidates) if last_sync_candidates else None

        prusa_offline = [
            p for p in prusa_printers
            if not p.last_success_at or (now - p.last_success_at).total_seconds() > 2 * 3600
        ]
        bambu_stale = bool(printers) and (
            not app_settings
            or not app_settings.bambu_last_sync_at
            or (now - app_settings.bambu_last_sync_at).total_seconds() > 2 * 3600
        )
        errors_24h = sum(
            1 for p in prusa_printers
            if p.last_sync_at and p.last_sync_at >= cutoff_24h and parse_sync_status(p.last_sync_status).get('error')
        )
        if app_settings and app_settings.bambu_last_sync_at and app_settings.bambu_last_sync_at >= cutoff_24h and bambu_sync_status.get('error'):
            errors_24h += 1

        backup_last_meta = None
        if app_settings and app_settings.backup_last_export_meta:
            import json
            try:
                backup_last_meta = json.loads(app_settings.backup_last_export_meta)
            except (ValueError, TypeError):
                backup_last_meta = None

        printer_health = {
            'last_sync_at': last_sync_at,
            'errors_24h': errors_24h,
            'offline_count': len(prusa_offline) + (len(printers) if bambu_stale else 0),
            'prusa_offline_names': [p.name for p in prusa_offline[:3]],
            'bambu_stale': bambu_stale,
        }

        return render_template(
            'settings.html',
            brands=brands, colors=colors, materials=materials,
            app_settings=app_settings, printers=printers,
            prusa_printers=prusa_printers,
            filament_tag_cloud=filament_tag_cloud, project_tag_cloud=project_tag_cloud,
            bambu_sync_status=bambu_sync_status,
            prusa_sync_states=prusa_sync_states,
            printer_health=printer_health,
            backup_last_meta=backup_last_meta,
            action_center=build_action_center(),
        )

    @bp.route('/settings/bambu/test', methods=['POST'])
    def settings_bambu_test():

        setting = _get_or_create_settings()
        token_raw = request.form.get('bambu_token', '').strip()
        region = request.form.get('bambu_region', '').strip().lower()
        if region not in ('global', 'china'):
            region = setting.bambu_region if setting and setting.bambu_region in ('global', 'china') else 'global'

        token = token_raw or (decrypt_token(setting.bambu_token) if setting and setting.bambu_token else '')
        if not token:
            setting.bambu_last_test_at = utc_now()
            setting.bambu_last_test_status = 'error: token missing'
            db.session.commit()
            return jsonify({'ok': False, 'error': 'token_missing'}), 400

        base_url = bambu_api_base(region)
        try:
            resp = requests.get(
                f'{base_url}/v1/user-service/my/tasks',
                params={'limit': 1, 'offset': 0},
                headers={'Authorization': f'Bearer {token}'},
                timeout=15,
            )
            setting.bambu_last_test_at = utc_now()
            if resp.ok:
                setting.bambu_last_test_status = f'ok: HTTP {resp.status_code}'
                db.session.commit()
                return jsonify({'ok': True, 'status': f'HTTP {resp.status_code}'})

            setting.bambu_last_test_status = f'error: HTTP {resp.status_code}'
            db.session.commit()
            return jsonify({'ok': False, 'error': f'http_{resp.status_code}'}), 400
        except Exception:
            app.logger.exception("Bambu connection test failed for token %s", token[:8] + "..." if token else "None")
            db.session.rollback()  # clear failed transaction from the try block
            setting.bambu_last_test_at = utc_now()
            setting.bambu_last_test_status = 'error: request failed'
            db.session.commit()
            return jsonify({'ok': False, 'error': 'request_failed'}), 400



    @bp.route('/toggle-theme', methods=['POST'])
    def toggle_theme():
        user = get_current_user()
        # If the user has a personal theme preference, cycle that instead
        if user and user.preferred_theme:
            user.preferred_theme = {
                'light': 'dark',
                'dark': 'light',
                'auto': 'light',
            }.get(user.preferred_theme, 'light')
            db.session.commit()
            app.logger.debug(f"User theme changed to: {user.preferred_theme}")
        else:
            setting = AppSetting.query.first()
            if setting:
                new_theme = 'light' if setting.theme == 'dark' else 'dark'
                setting.theme = new_theme
                db.session.commit()
                app.logger.debug(f"Global theme changed to: {new_theme}")
        return redirect(request.referrer or url_for('index'))

    @bp.route('/onboarding/dismiss', methods=['POST'])
    def onboarding_dismiss():
        setting = AppSetting.query.first()
        if setting:
            setting.onboarding_dismissed = True
            db.session.commit()
        return redirect(request.referrer or url_for('index'))
    app.register_blueprint(bp)
