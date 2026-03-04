from database import db
from models import AppSetting, MovementHistory


def get_settings():
    return AppSetting.query.first()


def get_current_lang():
    setting = get_settings()
    return setting.lang if setting else 'cs'


def get_current_currency():
    setting = get_settings()
    return setting.currency if setting and setting.currency else 'CZK'


def get_current_theme():
    setting = get_settings()
    return setting.theme if setting and setting.theme else 'light'


def log_movement(filament, action_type, weight):
    """Record a filament weight movement with cost calculation."""
    if weight <= 0:
        return
    cost_per_gram = filament.price / filament.weight_total if filament.weight_total > 0 else 0
    total_cost = cost_per_gram * weight
    currency = get_current_currency()

    brand_name = filament.brand.name if filament.brand else ""
    mat_name = filament.material.name if filament.material else ""
    filament_name = f"{filament.name} | {brand_name} {mat_name}".strip(" | ")

    movement = MovementHistory(
        filament_name=filament_name,
        action_type=action_type,
        weight=weight,
        cost=total_cost,
        currency=currency,
    )
    db.session.add(movement)
