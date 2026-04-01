from flask import Blueprint, make_response, current_app, render_template_string

def register(app):
    pwa_bp = Blueprint('pwa', __name__)

    @pwa_bp.route('/manifest.json')
    def manifest():
        manifest_data = {
            "name": "Filament Manager",
            "short_name": "FilamentMgr",
            "description": "Správa filamentů a 3D tiskových projektů.",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#2563eb",
            "icons": [
                {
                    # Since we don't have custom icons yet, we can use a generic data URI or omit.
                    # Good practice is to provide at least a 192x192 placeholder icon. 
                    "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Cpath fill='%232563eb' d='M0 256a256 256 0 1 1 512 0A256 256 0 1 1 0 256zm256 32a32 32 0 1 0 0-64 32 32 0 1 0 0 64zm-80 0a32 32 0 1 0 0-64 32 32 0 1 0 0 64zm160 0a32 32 0 1 0 0-64 32 32 0 1 0 0 64z'/%3E%3C/svg%3E",
                    "sizes": "192x192",
                    "type": "image/svg+xml",
                    "purpose": "any maskable"
                },
                {
                    "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Cpath fill='%232563eb' d='M0 256a256 256 0 1 1 512 0A256 256 0 1 1 0 256zm256 32a32 32 0 1 0 0-64 32 32 0 1 0 0 64zm-80 0a32 32 0 1 0 0-64 32 32 0 1 0 0 64zm160 0a32 32 0 1 0 0-64 32 32 0 1 0 0 64z'/%3E%3C/svg%3E",
                    "sizes": "512x512",
                    "type": "image/svg+xml"
                }
            ]
        }
        import json
        response = make_response(json.dumps(manifest_data))
        response.headers['Content-Type'] = 'application/json'
        return response

    @pwa_bp.route('/sw.js')
    def service_worker():
        # Minimal Service Worker for installability
        sw_js = """
const CACHE_NAME = 'filament-manager-v1';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', event => {
  // Let the browser do its default thing for now.
  // Full offline support not implemented yet.
});
"""
        response = make_response(sw_js)
        response.headers['Content-Type'] = 'application/javascript'
        return response

    app.register_blueprint(pwa_bp)
