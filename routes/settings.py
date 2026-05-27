"""Settings, export/import, and theme routes."""
import base64
import gzip
import io
import json
import logging
import os
import tarfile
import uuid
from flask import render_template, request, redirect, url_for, Response, Blueprint
from werkzeug.utils import secure_filename
from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, MovementHistory,
    PrintHistory, Project, ProjectFile, ProjectLink, ProjectFilament, ProjectQuote,
    BambuPrinter, BambuPrintJob, BambuJobMaterial, StoragePlacement, StorageShelf,
    PrusaPrinter, PrusaPrintJob, ProjectComment, ProjectTodo, User, UserInvite, Notification,
)
from utils import build_action_center, decrypt_token, encrypt_token, format_tags, parse_sync_status, remove_tag, top_tags, utc_now





def register(app):
    bp = Blueprint('settings', __name__)

    @bp.route('/settings', methods=['GET', 'POST'])
    def settings():
        if request.method == 'POST':
            action = request.form.get('action')
            try:
                if action == 'brand':
                    brand_name = request.form.get('name', '').strip()
                    if not brand_name:
                        raise ValueError('Brand name is required')
                    db.session.add(Brand(name=brand_name))
                    app.logger.debug(f"Added brand: {brand_name}")

                elif action == 'color':
                    color_name = request.form.get('name', '').strip()
                    color_hex = request.form.get('hex_value', '').strip()
                    if not color_name:
                        raise ValueError('Color name is required')
                    db.session.add(Color(name=color_name, hex_value=color_hex))
                    app.logger.debug(f"Added color: {color_name}")

                elif action == 'material':
                    material_name = request.form.get('name', '').strip()
                    if not material_name:
                        raise ValueError('Material name is required')
                    db.session.add(Material(name=material_name))
                    app.logger.debug(f"Added material: {material_name}")

                elif action == 'language':
                    setting = AppSetting.query.first()
                    old = setting.lang
                    setting.lang = request.form.get('lang', setting.lang)
                    app.logger.debug(f"Language changed: {old} -> {setting.lang}")

                elif action == 'currency':
                    setting = AppSetting.query.first()
                    old = setting.currency
                    setting.currency = request.form.get('currency', setting.currency)
                    app.logger.debug(f"Currency changed: {old} -> {setting.currency}")

                elif action == 'items_per_page':
                    setting = AppSetting.query.first()
                    setting.items_per_page = request.form.get('items_per_page', setting.items_per_page, type=int)
                    app.logger.debug(f"Items per page changed to: {setting.items_per_page}")

                elif action == 'nav_palette':
                    setting = AppSetting.query.first()
                    palette = request.form.get('nav_palette', 'teal').strip().lower()
                    if palette not in {'teal', 'slate', 'ocean', 'sunset'}:
                        palette = 'teal'
                    setting.nav_palette = palette
                    app.logger.debug(f"Navigation palette changed to: {setting.nav_palette}")

                elif action == 'debug_logging':
                    setting = AppSetting.query.first()
                    setting.debug_logging = request.form.get('debug_logging') == 'on'
                    if setting.debug_logging:
                        app.logger.setLevel(logging.DEBUG)
                        app.logger.debug("Debug logging enabled.")
                    else:
                        app.logger.setLevel(logging.INFO)

                elif action == 'audit_logging':
                    setting = AppSetting.query.first()
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

                elif action == 'bambu_cloud_settings':
                    setting = AppSetting.query.first()
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

                elif action == 'bambu_cloud_disconnect':
                    setting = AppSetting.query.first()
                    setting.bambu_token = None
                    app.logger.debug('Bambu Cloud token cleared.')

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
                    setting = AppSetting.query.first()
                    try:
                        setting.kwh_price = float(request.form.get('kwh_price', setting.kwh_price))
                        setting.printer_power = int(request.form.get('printer_power', setting.printer_power))
                    except (ValueError, TypeError):
                        pass
                    app.logger.debug(f"Printer/energy settings updated: kwh={setting.kwh_price}, power={setting.printer_power}W")

                elif action == 'add_prusa_printer':
                    from routes.prusa import _validate_host
                    host_raw = request.form.get('host', '').strip()
                    host = _validate_host(host_raw)
                    alias = request.form.get('name', '').strip()
                    api_key_raw = request.form.get('api_key', '').strip()
                    power_raw = request.form.get('power_draw_watts', '').strip()
                    power_val = None
                    if power_raw:
                        try:
                            power_val = max(0, int(power_raw))
                        except (ValueError, TypeError):
                            pass
                    if host and alias and api_key_raw:
                        db.session.add(PrusaPrinter(
                            name=alias,
                            host=host,
                            api_key=encrypt_token(api_key_raw),
                            notes=request.form.get('notes', '').strip() or None,
                            power_draw_watts=power_val,
                        ))
                        app.logger.debug(f'Added PrusaLink printer: {alias} @ {host}')

                elif action == 'edit_prusa_printer':
                    from routes.prusa import _validate_host
                    printer = db.session.get(PrusaPrinter, request.form.get('id', type=int))
                    if printer:
                        new_name = request.form.get('name', '').strip()
                        new_host = _validate_host(request.form.get('host', '').strip())
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
                    setting = AppSetting.query.first()
                    url_raw = request.form.get('reorder_shop_url', '').strip()
                    setting.reorder_shop_url = url_raw or None
                    app.logger.debug(f'Reorder shop URL updated: {setting.reorder_shop_url}')

                elif action == 'app_timezone':
                    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                    setting = AppSetting.query.first()
                    tz_raw = request.form.get('app_timezone', '').strip()
                    if tz_raw:
                        try:
                            ZoneInfo(tz_raw)  # validate the zone name
                            setting.app_timezone = tz_raw
                            app.logger.debug(f'App timezone set to: {tz_raw}')
                        except (ZoneInfoNotFoundError, KeyError):
                            app.logger.warning(f'Invalid timezone rejected: {tz_raw}')

                elif action == 'billing_settings':
                    setting = AppSetting.query.first()
                    setting.company_name = request.form.get('company_name', '').strip() or None
                    setting.company_street = request.form.get('company_street', '').strip() or None
                    setting.company_city = request.form.get('company_city', '').strip() or None
                    setting.company_zip = request.form.get('company_zip', '').strip() or None
                    setting.company_id = request.form.get('company_id', '').strip() or None
                    setting.company_vat_id = request.form.get('company_vat_id', '').strip() or None
                    setting.company_bank_account = request.form.get('company_bank_account', '').strip() or None
                    app.logger.debug('Billing settings updated.')

                db.session.commit()
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Settings action error: {str(e)}")
            _dicts_actions = {
                'brand', 'color', 'material',
                'edit_brand', 'edit_material', 'edit_color',
                'delete_brand', 'delete_material', 'delete_color',
            }
            _printers_actions = {
                'printer_energy_settings',
                'edit_bambu_printer', 'delete_bambu_printer',
            }
            _integrations_actions = {
                'bambu_cloud_settings', 'bambu_cloud_disconnect',
                'reorder_shop_settings',
                'add_prusa_printer', 'edit_prusa_printer', 'delete_prusa_printer',
                'delete_filament_tag', 'delete_project_tag',
            }
            _company_actions = {'billing_settings'}
            if action in _dicts_actions:
                tab = 'dicts'
            elif action in _printers_actions:
                tab = 'printers'
            elif action in _integrations_actions:
                tab = 'integrations'
            elif action in _company_actions:
                tab = 'company'
            else:
                tab = 'general'
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
        return render_template(
            'settings.html',
            brands=brands, colors=colors, materials=materials,
            app_settings=app_settings, printers=printers,
            prusa_printers=prusa_printers,
            filament_tag_cloud=filament_tag_cloud, project_tag_cloud=project_tag_cloud,
            bambu_sync_status=bambu_sync_status,
            prusa_sync_states=prusa_sync_states,
            action_center=build_action_center(),
        )



    @bp.route('/toggle-theme', methods=['POST'])
    def toggle_theme():
        setting = AppSetting.query.first()
        if setting:
            new_theme = 'light' if setting.theme == 'dark' else 'dark'
            setting.theme = new_theme
            db.session.commit()
            app.logger.debug(f"Theme changed to: {new_theme}")
        return redirect(request.referrer or url_for('index'))

    @bp.route('/onboarding/dismiss', methods=['POST'])
    def onboarding_dismiss():
        setting = AppSetting.query.first()
        if setting:
            setting.onboarding_dismissed = True
            db.session.commit()
        return redirect(request.referrer or url_for('index'))
    app.register_blueprint(bp)
