"""
Route registration helpers.

Each module exposes a register(app) function that creates a Flask Blueprint
and registers it on the app. A custom url_for BuildError fallback handler
(in app.py) resolves legacy unprefixed endpoint names to blueprint-prefixed
ones, so url_for('endpoint') works as-is in templates.
"""
from routes.inventory import register as register_inventory
from routes.auth import register as register_auth
from routes.api import register as register_api
from routes.calculator import register as register_calculator
from routes.history import register as register_history
from routes.settings import register as register_settings
from routes.backup import register as register_backup
from routes.projects import register as register_projects
from routes.bambu import register as register_bambu
from routes.prusa import register as register_prusa
from routes.stats import register as register_stats
from routes.storage import register as register_storage
from routes.pwa import register as register_pwa
from routes.maintenance import register as register_maintenance
from routes.waste import register as register_waste
from routes.models import register as register_models


def register_all(app):
    register_auth(app)
    register_inventory(app)
    register_api(app)
    register_calculator(app)
    register_history(app)
    register_settings(app)
    register_backup(app)
    register_projects(app)
    register_bambu(app)
    register_prusa(app)
    register_stats(app)
    register_storage(app)
    register_pwa(app)
    register_maintenance(app)
    register_waste(app)
    register_models(app)

