"""Settings, export/import, and theme routes."""
import json
import logging
from flask import render_template, request, redirect, url_for, jsonify
from database import db
from models import (
    Brand, Color, Material, AppSetting, Filament, MovementHistory,
    PrintHistory, Project, ProjectFile, ProjectLink, ProjectFilament,
    BambuPrinter, BambuPrintJob, BambuJobMaterial,
)


def register(app):

    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        if request.method == 'POST':
            action = request.form.get('action')
            try:
                if action == 'brand':
                    brand_name = request.form['name']
                    db.session.add(Brand(name=brand_name))
                    app.logger.debug(f"Added brand: {brand_name}")

                elif action == 'color':
                    db.session.add(Color(name=request.form['name'], hex_value=request.form['hex_value']))
                    app.logger.debug(f"Added color: {request.form['name']}")

                elif action == 'material':
                    db.session.add(Material(name=request.form['name']))
                    app.logger.debug(f"Added material: {request.form['name']}")

                elif action == 'language':
                    setting = AppSetting.query.first()
                    old = setting.lang
                    setting.lang = request.form['lang']
                    app.logger.debug(f"Language changed: {old} -> {setting.lang}")

                elif action == 'currency':
                    setting = AppSetting.query.first()
                    old = setting.currency
                    setting.currency = request.form['currency']
                    app.logger.debug(f"Currency changed: {old} -> {setting.currency}")

                elif action == 'items_per_page':
                    setting = AppSetting.query.first()
                    setting.items_per_page = int(request.form['items_per_page'])
                    app.logger.debug(f"Items per page changed to: {setting.items_per_page}")

                elif action == 'debug_logging':
                    setting = AppSetting.query.first()
                    setting.debug_logging = request.form.get('debug_logging') == 'on'
                    if setting.debug_logging:
                        app.logger.setLevel(logging.DEBUG)
                        app.logger.debug("Debug logging enabled.")
                    else:
                        app.logger.setLevel(logging.INFO)

                elif action == 'edit_brand':
                    brand = db.session.get(Brand, request.form['id'])
                    if brand:
                        old = brand.name
                        brand.name = request.form['name']
                        app.logger.debug(f"Brand edited: {old} -> {brand.name}")

                elif action == 'edit_material':
                    mat = db.session.get(Material, request.form['id'])
                    if mat:
                        old = mat.name
                        mat.name = request.form['name']
                        app.logger.debug(f"Material edited: {old} -> {mat.name}")

                elif action == 'edit_color':
                    col = db.session.get(Color, request.form['id'])
                    if col:
                        col.name = request.form['name']
                        col.hex_value = request.form['hex_value']
                        app.logger.debug(f"Color edited: {col.name}")

                elif action == 'delete_brand':
                    brand = db.session.get(Brand, request.form['id'])
                    if brand and len(brand.filaments) == 0:
                        db.session.delete(brand)
                        app.logger.debug(f"Brand deleted: {brand.name}")

                elif action == 'delete_material':
                    mat = db.session.get(Material, request.form['id'])
                    if mat and len(mat.filaments) == 0:
                        db.session.delete(mat)
                        app.logger.debug(f"Material deleted: {mat.name}")

                elif action == 'delete_color':
                    col = db.session.get(Color, request.form['id'])
                    if col and len(col.filaments) == 0:
                        db.session.delete(col)
                        app.logger.debug(f"Color deleted: {col.name}")

                elif action == 'bambu_cloud_settings':
                    setting = AppSetting.query.first()
                    token = request.form.get('bambu_token', '').strip()
                    region = request.form.get('bambu_region', 'global')
                    if region not in ('global', 'china'):
                        region = 'global'
                    if token:
                        setting.bambu_token = token
                    setting.bambu_region = region
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
                            app.logger.debug(f"Renamed printer {printer.device_id} → {new_name}")

                elif action == 'printer_energy_settings':
                    setting = AppSetting.query.first()
                    try:
                        setting.kwh_price = float(request.form.get('kwh_price', setting.kwh_price))
                        setting.printer_power = int(request.form.get('printer_power', setting.printer_power))
                    except (ValueError, TypeError):
                        pass
                    app.logger.debug(f"Printer/energy settings updated: kwh={setting.kwh_price}, power={setting.printer_power}W")

                db.session.commit()
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Settings action error: {str(e)}")
            return redirect(url_for('settings'))

        brands = Brand.query.order_by(Brand.name).all()
        colors = Color.query.order_by(Color.name).all()
        materials = Material.query.order_by(Material.name).all()
        app_settings = AppSetting.query.first()
        printers = BambuPrinter.query.order_by(BambuPrinter.name).all()
        return render_template(
            'settings.html',
            brands=brands, colors=colors, materials=materials,
            app_settings=app_settings, printers=printers,
        )

    @app.route('/export')
    def export_data():
        setting = AppSetting.query.first()

        data = {
            # ── Enumerations ───────────────────────────────────────────
            'brands': [b.name for b in Brand.query.all()],
            'materials': [m.name for m in Material.query.all()],
            'colors': [{'name': c.name, 'hex_value': c.hex_value} for c in Color.query.all()],

            # ── App settings ───────────────────────────────────────────
            'app_settings': {
                'lang': setting.lang if setting else 'cs',
                'currency': setting.currency if setting else 'CZK',
                'theme': setting.theme if setting else 'light',
                'view_mode': setting.view_mode if setting else 'card',
                'items_per_page': setting.items_per_page if setting else 12,
                'kwh_price': setting.kwh_price if setting else 5.0,
                'printer_power': setting.printer_power if setting else 150,
                'debug_logging': setting.debug_logging if setting else False,
                'bambu_region': setting.bambu_region if setting else 'global',
                # bambu_token intentionally excluded for security
            } if setting else {},

            # ── Inventory ──────────────────────────────────────────────
            'filaments': [{
                'name': f.name,
                'brand': f.brand.name if f.brand else '',
                'material': f.material.name if f.material else '',
                'color': f.color.name if f.color else '',
                'weight_total': f.weight_total,
                'weight_remaining': f.weight_remaining,
                'price': f.price,
                'quantity': f.quantity,
            } for f in Filament.query.all()],

            # ── Movement history ───────────────────────────────────────
            'movement_history': [{
                'filament_name': m.filament_name,
                'action_type': m.action_type,
                'weight': m.weight,
                'cost': m.cost,
                'currency': m.currency,
                'created_at': m.created_at.isoformat() if m.created_at else None,
            } for m in MovementHistory.query.order_by(MovementHistory.created_at).all()],

            # ── Calculator / print history ─────────────────────────────
            'print_history': [{
                'filament_name': p.filament_name,
                'weight': p.weight,
                'total_cost': p.total_cost,
                'created_at': p.created_at.isoformat() if p.created_at else None,
            } for p in PrintHistory.query.order_by(PrintHistory.created_at).all()],

            # ── Projects ───────────────────────────────────────────────
            'projects': [{
                'name': proj.name,
                'description': proj.description,
                'status': proj.status,
                'client_name': proj.client_name,
                'estimated_print_time': proj.estimated_print_time,
                'due_date': proj.due_date.isoformat() if proj.due_date else None,
                'created_at': proj.created_at.isoformat() if proj.created_at else None,
                'files': [{
                    'filename': pf.filename,
                    'filepath': pf.filepath,
                } for pf in proj.files],
                'links': [{
                    'url': pl.url,
                    'name': pl.name,
                    'og_title': pl.og_title,
                    'og_image': pl.og_image,
                    'og_description': pl.og_description,
                    'domain': pl.domain,
                } for pl in proj.links],
                'filaments': [{
                    'filament_name': pf.filament.name if pf.filament else None,
                    'estimated_weight': pf.estimated_weight,
                    'is_used': pf.is_used,
                } for pf in proj.filaments],
            } for proj in Project.query.order_by(Project.created_at).all()],

            # ── Bambu integration ──────────────────────────────────────
            'bambu_printers': [{
                'device_id': bp.device_id,
                'name': bp.name,
                'printer_model': bp.printer_model,
                'notes': bp.notes,
            } for bp in BambuPrinter.query.all()],

            'bambu_jobs': [{
                'external_id': j.external_id,
                'printer_name': j.printer_name,
                'printer_model': j.printer_model,
                'device_id': j.device_id,
                'model_name': j.model_name,
                'status': j.status,
                'weight_grams': j.weight_grams,
                'cost_time': j.cost_time,
                'started_at': j.started_at.isoformat() if j.started_at else None,
                'finished_at': j.finished_at.isoformat() if j.finished_at else None,
                'synced_at': j.synced_at.isoformat() if j.synced_at else None,
                'deducted': j.deducted,
                'filament_name': j.filament.name if j.filament else None,
                'project_name': j.project.name if j.project else None,
                'materials': [{
                    'ams_id': m.ams_id,
                    'tray_id': m.tray_id,
                    'color_hex': m.color_hex,
                    'material_name': m.material_name,
                    'weight_grams': m.weight_grams,
                    'filament_name': m.filament.name if m.filament else None,
                    'deducted': m.deducted,
                } for m in j.materials],
            } for j in BambuPrintJob.query.order_by(BambuPrintJob.started_at).all()],
        }

        app.logger.debug(
            f"Export: {len(data['filaments'])} filaments, "
            f"{len(data['projects'])} projects, "
            f"{len(data['bambu_jobs'])} Bambu jobs"
        )
        response = jsonify(data)
        response.headers['Content-Disposition'] = 'attachment; filename=filament_backup.json'
        return response

    @app.route('/import', methods=['POST'])
    def import_data():
        from datetime import datetime
        file = request.files.get('file')
        if not file or file.filename == '':
            return redirect(url_for('settings'))

        imported_filaments = 0
        try:
            data = json.load(file)
            with db.session.begin():
                # ── 1. Enumerations ────────────────────────────────────
                for b_name in data.get('brands', []):
                    if not Brand.query.filter_by(name=b_name).first():
                        db.session.add(Brand(name=b_name))

                for m_name in data.get('materials', []):
                    if not Material.query.filter_by(name=m_name).first():
                        db.session.add(Material(name=m_name))

                for c in data.get('colors', []):
                    if not Color.query.filter_by(name=c.get('name')).first():
                        db.session.add(Color(name=c.get('name'), hex_value=c.get('hex_value', '')))

                db.session.flush()

                # ── 2. App settings ────────────────────────────────────
                s = data.get('app_settings', {})
                if s:
                    setting = AppSetting.query.first()
                    if setting:
                        setting.lang = s.get('lang', setting.lang)
                        setting.currency = s.get('currency', setting.currency)
                        setting.theme = s.get('theme', setting.theme)
                        setting.view_mode = s.get('view_mode', setting.view_mode)
                        setting.items_per_page = s.get('items_per_page', setting.items_per_page)
                        setting.kwh_price = s.get('kwh_price', setting.kwh_price)
                        setting.printer_power = s.get('printer_power', setting.printer_power)
                        setting.debug_logging = s.get('debug_logging', setting.debug_logging)
                        setting.bambu_region = s.get('bambu_region', setting.bambu_region)

                # ── 3. Filaments ───────────────────────────────────────
                for f in data.get('filaments', []):
                    b = Brand.query.filter_by(name=f.get('brand')).first()
                    m = Material.query.filter_by(name=f.get('material')).first()
                    c = Color.query.filter_by(name=f.get('color')).first()
                    if b and m and c:
                        exists = Filament.query.filter_by(
                            name=f.get('name'), brand_id=b.id, material_id=m.id, color_id=c.id
                        ).first()
                        if not exists:
                            db.session.add(Filament(
                                name=f.get('name'),
                                brand_id=b.id, material_id=m.id, color_id=c.id,
                                weight_total=f.get('weight_total', 1000),
                                weight_remaining=f.get('weight_remaining', 1000),
                                price=f.get('price', 0),
                                quantity=f.get('quantity', 1),
                            ))
                            imported_filaments += 1

                db.session.flush()

                # ── 4. Movement history ────────────────────────────────
                for m in data.get('movement_history', []):
                    ts = datetime.fromisoformat(m['created_at']) if m.get('created_at') else datetime.utcnow()
                    exists = MovementHistory.query.filter_by(
                        filament_name=m.get('filament_name'),
                        action_type=m.get('action_type'),
                        created_at=ts,
                    ).first()
                    if not exists:
                        db.session.add(MovementHistory(
                            filament_name=m.get('filament_name'),
                            action_type=m.get('action_type'),
                            weight=m.get('weight', 0),
                            cost=m.get('cost', 0),
                            currency=m.get('currency', 'CZK'),
                            created_at=ts,
                        ))

                # ── 5. Print history (calculator) ─────────────────────
                for p in data.get('print_history', []):
                    ts = datetime.fromisoformat(p['created_at']) if p.get('created_at') else datetime.utcnow()
                    exists = PrintHistory.query.filter_by(
                        filament_name=p.get('filament_name'),
                        created_at=ts,
                    ).first()
                    if not exists:
                        db.session.add(PrintHistory(
                            filament_name=p.get('filament_name'),
                            weight=p.get('weight', 0),
                            total_cost=p.get('total_cost', 0),
                            created_at=ts,
                        ))

                # ── 6. Projects ───────────────────────────────────────
                for proj_data in data.get('projects', []):
                    proj = Project.query.filter_by(name=proj_data.get('name')).first()
                    if not proj:
                        proj = Project(
                            name=proj_data.get('name'),
                            description=proj_data.get('description'),
                            status=proj_data.get('status', 'NEW'),
                            client_name=proj_data.get('client_name'),
                            estimated_print_time=proj_data.get('estimated_print_time', 0),
                            due_date=datetime.fromisoformat(proj_data['due_date']) if proj_data.get('due_date') else None,
                            created_at=datetime.fromisoformat(proj_data['created_at']) if proj_data.get('created_at') else datetime.utcnow(),
                        )
                        db.session.add(proj)
                        db.session.flush()

                        for link in proj_data.get('links', []):
                            db.session.add(ProjectLink(
                                project_id=proj.id,
                                url=link.get('url', ''),
                                name=link.get('name'),
                                og_title=link.get('og_title'),
                                og_image=link.get('og_image'),
                                og_description=link.get('og_description'),
                                domain=link.get('domain'),
                            ))

                        for pf_data in proj_data.get('filaments', []):
                            fil = Filament.query.filter_by(name=pf_data.get('filament_name')).first()
                            if fil:
                                db.session.add(ProjectFilament(
                                    project_id=proj.id,
                                    filament_id=fil.id,
                                    estimated_weight=pf_data.get('estimated_weight', 0),
                                    is_used=pf_data.get('is_used', False),
                                ))

                # ── 7. Bambu printers ─────────────────────────────────
                for bp in data.get('bambu_printers', []):
                    if not BambuPrinter.query.filter_by(device_id=bp.get('device_id')).first():
                        db.session.add(BambuPrinter(
                            device_id=bp.get('device_id'),
                            name=bp.get('name', ''),
                            printer_model=bp.get('printer_model'),
                            notes=bp.get('notes'),
                        ))

                # ── 8. Bambu jobs ─────────────────────────────────────
                for j in data.get('bambu_jobs', []):
                    if BambuPrintJob.query.filter_by(external_id=j.get('external_id')).first():
                        continue
                    fil = Filament.query.filter_by(name=j.get('filament_name')).first() if j.get('filament_name') else None
                    proj = Project.query.filter_by(name=j.get('project_name')).first() if j.get('project_name') else None
                    job = BambuPrintJob(
                        external_id=j.get('external_id'),
                        printer_name=j.get('printer_name'),
                        printer_model=j.get('printer_model'),
                        device_id=j.get('device_id'),
                        model_name=j.get('model_name'),
                        status=j.get('status'),
                        weight_grams=j.get('weight_grams'),
                        cost_time=j.get('cost_time'),
                        started_at=datetime.fromisoformat(j['started_at']) if j.get('started_at') else None,
                        finished_at=datetime.fromisoformat(j['finished_at']) if j.get('finished_at') else None,
                        synced_at=datetime.fromisoformat(j['synced_at']) if j.get('synced_at') else datetime.utcnow(),
                        deducted=j.get('deducted', False),
                        filament_id=fil.id if fil else None,
                        project_id=proj.id if proj else None,
                    )
                    db.session.add(job)
                    db.session.flush()

                    for mat in j.get('materials', []):
                        mat_fil = Filament.query.filter_by(name=mat.get('filament_name')).first() if mat.get('filament_name') else None
                        db.session.add(BambuJobMaterial(
                            job_id=job.id,
                            ams_id=mat.get('ams_id'),
                            tray_id=mat.get('tray_id'),
                            color_hex=mat.get('color_hex'),
                            material_name=mat.get('material_name'),
                            weight_grams=mat.get('weight_grams'),
                            filament_id=mat_fil.id if mat_fil else None,
                            deducted=mat.get('deducted', False),
                        ))

            app.logger.debug(f"Import finished: {imported_filaments} filaments, projects and Bambu jobs processed.")
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Import failed: {str(e)}")

        return redirect(url_for('settings'))

    @app.route('/toggle-theme', methods=['POST'])
    def toggle_theme():
        setting = AppSetting.query.first()
        if setting:
            new_theme = 'light' if setting.theme == 'dark' else 'dark'
            setting.theme = new_theme
            db.session.commit()
            app.logger.debug(f"Theme changed to: {new_theme}")
        return redirect(request.referrer or url_for('index'))
