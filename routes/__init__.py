"""
Route registration helpers.
Each module exposes a register(app) function that attaches routes directly onto
the Flask app — no Blueprints, so url_for('endpoint') works in templates as-is.
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
