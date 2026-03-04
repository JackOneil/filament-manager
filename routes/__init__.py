"""
Route registration helpers.
Each module exposes a register(app) function that attaches routes directly onto
the Flask app — no Blueprints, so url_for('endpoint') works in templates as-is.
"""
from routes.inventory import register as register_inventory
from routes.api import register as register_api
from routes.calculator import register as register_calculator
from routes.history import register as register_history
from routes.settings import register as register_settings


def register_all(app):
    register_inventory(app)
    register_api(app)
    register_calculator(app)
    register_history(app)
    register_settings(app)
