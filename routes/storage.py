"""Storage shelves visualisation and placement routes."""
from flask import render_template, request, redirect, url_for, jsonify, Blueprint
from sqlalchemy.orm import joinedload

from database import db
from models import Brand, Color, Filament, Material, StoragePlacement, StorageShelf
from utils import get_filament_tags, parse_tags


def _placement_fill_percent(filament):
    capacity = (filament.quantity or 0) * (filament.weight_total or 0)
    if capacity <= 0:
        return 0
    return max(0, min(100, round((filament.weight_remaining / capacity) * 100)))


def _resolve_named_entity(raw_value, model):
    value = (raw_value or '').strip()
    if not value:
        return None
    if value.lower() in {'all', 'vše'}:
        return None
    prefix = value.split(' - ', 1)[0].strip()
    if prefix.isdigit():
        entity = db.session.get(model, int(prefix))
        if entity:
            return entity
    if hasattr(model, 'name'):
        return model.query.filter_by(name=value).first()
    return None


def _repack_shelf_slots(shelf, new_slots_count):
    kept_slots = set()
    overflow = []

    for placement in sorted(shelf.placements, key=lambda item: item.slot_index):
        if placement.slot_index <= new_slots_count and placement.slot_index not in kept_slots:
            kept_slots.add(placement.slot_index)
        else:
            overflow.append(placement)

    free_slots = [slot for slot in range(1, new_slots_count + 1) if slot not in kept_slots]
    for placement, target_slot in zip(overflow, free_slots):
        placement.slot_index = target_slot
        kept_slots.add(target_slot)

    for placement in overflow[len(free_slots):]:
        db.session.delete(placement)


def _storage_redirect_for_shelf(shelf):
    if not shelf:
        return redirect(url_for('storage'))
    return redirect(url_for('storage', shelf=f'{shelf.id} - {shelf.name}'))


def register(app):
    bp = Blueprint('storage', __name__)

    @bp.route('/storage')
    def storage():
        shelf_input = request.args.get('shelf', '').strip()
        brand_input = request.args.get('brand', '').strip()
        material_input = request.args.get('material', '').strip()
        color_input = request.args.get('color', '').strip()
        filament_input = request.args.get('filament', '').strip()
        tag = request.args.get('tag', '').strip().lower()

        shelf_entity = _resolve_named_entity(shelf_input, StorageShelf)
        brand_entity = _resolve_named_entity(brand_input, Brand)
        material_entity = _resolve_named_entity(material_input, Material)
        color_entity = _resolve_named_entity(color_input, Color)
        filament_entity = _resolve_named_entity(filament_input, Filament)

        shelf_id = shelf_entity.id if shelf_entity else None
        brand_id = brand_entity.id if brand_entity else None
        material_id = material_entity.id if material_entity else None
        color_id = color_entity.id if color_entity else None
        filament_id = filament_entity.id if filament_entity else None

        shelves = StorageShelf.query.options(
            joinedload(StorageShelf.placements)
            .joinedload(StoragePlacement.filament)
            .joinedload(Filament.brand),
            joinedload(StorageShelf.placements)
            .joinedload(StoragePlacement.filament)
            .joinedload(Filament.material),
            joinedload(StorageShelf.placements)
            .joinedload(StoragePlacement.filament)
            .joinedload(Filament.color),
        ).order_by(StorageShelf.sort_order.asc(), StorageShelf.name.asc()).all()

        all_filaments = Filament.query.options(
            joinedload(Filament.brand),
            joinedload(Filament.material),
            joinedload(Filament.color),
        ).order_by(Filament.name.asc()).all()

        filtered_filaments = all_filaments
        if brand_id:
            filtered_filaments = [fil for fil in filtered_filaments if fil.brand_id == brand_id]
        if material_id:
            filtered_filaments = [fil for fil in filtered_filaments if fil.material_id == material_id]
        if color_id:
            filtered_filaments = [fil for fil in filtered_filaments if fil.color_id == color_id]
        if tag:
            filtered_filaments = [fil for fil in filtered_filaments if tag in [item.lower() for item in get_filament_tags(fil)]]
        if filament_id:
            filtered_filaments = [fil for fil in filtered_filaments if fil.id == filament_id]
        filtered_filament_ids = {fil.id for fil in filtered_filaments}
        has_active_filter = bool(brand_id or material_id or color_id or tag or filament_id)

        prepared_shelves = []
        for shelf in shelves:
            if shelf_id and shelf.id != shelf_id:
                continue
            slot_map = {}
            for placement in shelf.placements:
                placement.fill_percent = _placement_fill_percent(placement.filament)
                placement.tag_list = get_filament_tags(placement.filament)
                placement.matches_filter = (not filtered_filament_ids) or placement.filament_id in filtered_filament_ids
                placement.brand_short = (placement.filament.brand.name[:3].upper() if placement.filament and placement.filament.brand else '---')
                slot_map[placement.slot_index] = placement
            matched_slots = sum(1 for placement in shelf.placements if getattr(placement, 'matches_filter', True))
            occupied_slots = len(shelf.placements)
            total_slots = shelf.slots_count
            occupancy_percent = round((occupied_slots / total_slots) * 100) if total_slots > 0 else 0
            prepared_shelves.append({
                'shelf': shelf,
                'slot_map': slot_map,
                'slots': list(range(1, shelf.slots_count + 1)),
                'compact': (shelf.columns or 1) >= 8,
                'matched_slots': matched_slots,
                'occupied_slots': occupied_slots,
                'occupancy_percent': occupancy_percent,
            })

        tag_options = sorted({
            tag_value
            for filament in all_filaments
            for tag_value in parse_tags(filament.tag_text)
        }, key=str.lower)

        brands = Brand.query.order_by(Brand.name.asc()).all()
        materials = Material.query.order_by(Material.name.asc()).all()
        colors = Color.query.order_by(Color.name.asc()).all()

        return render_template(
            'storage.html',
            shelves=prepared_shelves,
            all_shelves=shelves,
            all_filaments=all_filaments,
            brands=brands,
            materials=materials,
            colors=colors,
            tag_options=tag_options,
            active_shelf=shelf_input,
            active_brand=brand_input,
            active_material=material_input,
            active_color=color_input,
            active_filament=filament_input,
            active_tag=tag,
            has_active_filter=has_active_filter,
        )

    @bp.route('/storage/shelf', methods=['POST'])
    def storage_add_shelf():
        name = request.form.get('name', '').strip()
        columns = max(request.form.get('columns', 4, type=int), 1)
        slots_count = max(request.form.get('slots_count', 12, type=int), columns)
        if name and not StorageShelf.query.filter_by(name=name).first():
            sort_order = (db.session.query(db.func.max(StorageShelf.sort_order)).scalar() or 0) + 1
            db.session.add(StorageShelf(name=name, columns=columns, slots_count=slots_count, sort_order=sort_order))
            db.session.commit()
        return redirect(url_for('storage'))

    @bp.route('/storage/shelf/<int:shelf_id>/update', methods=['POST'])
    def storage_update_shelf(shelf_id):
        shelf = db.session.get(StorageShelf, shelf_id)
        if shelf:
            new_name = request.form.get('name', '').strip()
            columns = max(request.form.get('columns', shelf.columns, type=int), 1)
            slots_count = max(request.form.get('slots_count', shelf.slots_count, type=int), columns)
            if new_name and (new_name == shelf.name or not StorageShelf.query.filter_by(name=new_name).first()):
                shelf.name = new_name
            shelf.columns = columns
            shelf.slots_count = slots_count
            _repack_shelf_slots(shelf, slots_count)
            db.session.commit()
        return _storage_redirect_for_shelf(shelf)

    @bp.route('/storage/shelf/<int:shelf_id>/delete', methods=['POST'])
    def storage_delete_shelf(shelf_id):
        shelf = db.session.get(StorageShelf, shelf_id)
        if shelf:
            db.session.delete(shelf)
            db.session.commit()
        return redirect(url_for('storage'))

    @bp.route('/storage/slot/assign', methods=['POST'])
    def storage_assign_slot():
        shelf = db.session.get(StorageShelf, request.form.get('shelf_id', type=int))
        filament = _resolve_named_entity(request.form.get('filament', ''), Filament)
        slot_index = request.form.get('slot_index', type=int)
        if shelf and filament and slot_index and 1 <= slot_index <= shelf.slots_count:
            existing = StoragePlacement.query.filter_by(shelf_id=shelf.id, slot_index=slot_index).first()
            if not existing:
                db.session.add(StoragePlacement(
                    shelf_id=shelf.id,
                    filament_id=filament.id,
                    slot_index=slot_index,
                    orientation='standing',
                ))
                db.session.commit()
        return redirect(url_for('storage'))

    @bp.route('/storage/placement/<int:placement_id>/move', methods=['POST'])
    def storage_move_placement(placement_id):
        placement = db.session.get(StoragePlacement, placement_id)
        if not placement:
            return jsonify({'ok': False}), 404

        target_shelf_id = request.form.get('shelf_id', type=int)
        target_slot_index = request.form.get('slot_index', type=int)
        target_shelf = db.session.get(StorageShelf, target_shelf_id) if target_shelf_id else None
        if not target_shelf or not target_slot_index or target_slot_index < 1 or target_slot_index > target_shelf.slots_count:
            return jsonify({'ok': False}), 400

        existing = StoragePlacement.query.filter_by(shelf_id=target_shelf.id, slot_index=target_slot_index).first()
        if existing and existing.id != placement.id:
            existing.shelf_id, placement.shelf_id = placement.shelf_id, existing.shelf_id
            existing.slot_index, placement.slot_index = placement.slot_index, existing.slot_index
        else:
            placement.shelf_id = target_shelf.id
            placement.slot_index = target_slot_index

        db.session.commit()
        return jsonify({'ok': True})

    @bp.route('/storage/placement/<int:placement_id>/orientation', methods=['POST'])
    def storage_update_orientation(placement_id):
        placement = db.session.get(StoragePlacement, placement_id)
        if not placement:
            return redirect(url_for('storage'))
        orientation = request.form.get('orientation', placement.orientation).strip() or placement.orientation
        placement.orientation = orientation
        db.session.commit()
        return _storage_redirect_for_shelf(placement.shelf)

    @bp.route('/storage/placement/<int:placement_id>/delete', methods=['POST'])
    def storage_delete_placement(placement_id):
        placement = db.session.get(StoragePlacement, placement_id)
        if placement:
            shelf = placement.shelf
            db.session.delete(placement)
            db.session.commit()
            return _storage_redirect_for_shelf(shelf)
        return redirect(url_for('storage'))
    app.register_blueprint(bp)
