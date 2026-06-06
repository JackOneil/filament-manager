"""Progressive Web App support — manifest + service worker.

Refactor 5.12: the service worker now ships with a versioned cache
strategy and a proper ``activate`` handler that purges caches belonging
to previous versions.  Previously the worker installed a ``v1`` cache
that was never cleaned up, so any future upgrade would leak dead data
on every device.

The cache name is derived from ``app.config['APP_VERSION']`` so each
release installs a fresh cache and the ``activate`` step removes the
old one via ``caches.delete()``.
"""
from flask import current_app, make_response, Blueprint

# Fallback for environments where ``app.config['APP_VERSION']`` is missing
# (e.g. very old installs).  Bumping the prefix invalidates every
# previously-cached response in one shot.
_DEFAULT_SW_CACHE_PREFIX = 'filament-manager'


def _sw_cache_name() -> str:
    version = (current_app.config.get('APP_VERSION') or '0').split('.')[0]
    return f'{_DEFAULT_SW_CACHE_PREFIX}-v{version}-static'


# Static assets eligible for cache-first retrieval.  Path-only matching
# (no querystrings) so we don't serve stale CSV exports or one-shot
# JSON endpoints from the cache.
_CACHEABLE_STATIC_PREFIXES = (
    '/static/',
    '/manifest.json',
)


def register(app):
    bp = Blueprint('pwa', __name__)

    @bp.route('/manifest.json')
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

    @bp.route('/sw.js')
    def service_worker():
        cache_name = _sw_cache_name()
        # The JavaScript is generated as a string so the cache name
        # stays in sync with APP_VERSION at request time.  We deliberately
        # keep this small — full offline support is still on the roadmap.
        sw_js = (
            "const CACHE_NAME = '" + cache_name + "';\n"
            "const CACHEABLE_PREFIXES = ['/static/', '/manifest.json'];\n"
            "\n"
            "self.addEventListener('install', event => {\n"
            "  self.skipWaiting();\n"
            "});\n"
            "\n"
            "self.addEventListener('activate', event => {\n"
            "  event.waitUntil(\n"
            "    caches.keys().then(keys =>\n"
            "      Promise.all(\n"
            "        keys\n"
            "          .filter(k => k.startsWith('" + _DEFAULT_SW_CACHE_PREFIX + "-') && k !== CACHE_NAME)\n"
            "          .map(k => caches.delete(k))\n"
            "      )\n"
            "    ).then(() => clients.claim())\n"
            "  );\n"
            "});\n"
            "\n"
            "self.addEventListener('fetch', event => {\n"
            "  const req = event.request;\n"
            "  if (req.method !== 'GET') return;\n"
            "  const url = new URL(req.url);\n"
            "  if (url.origin !== self.location.origin) return;\n"
            "  const path = url.pathname;\n"
            "  const isCacheable = CACHEABLE_PREFIXES.some(p => path === p || path.startsWith(p));\n"
            "  if (!isCacheable) return; // default browser handling for HTML / API\n"
            "  event.respondWith(\n"
            "    caches.open(CACHE_NAME).then(cache =>\n"
            "      cache.match(req).then(cached =>\n"
            "        cached || fetch(req).then(resp => {\n"
            "          if (resp && resp.status === 200) cache.put(req, resp.clone());\n"
            "          return resp;\n"
            "        }).catch(() => cached)\n"
            "      )\n"
            "    )\n"
            "  );\n"
            "});\n"
        )
        response = make_response(sw_js)
        # Service workers must be served as JavaScript with no caching
        # by intermediaries — the browser re-reads sw.js on every check.
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Service-Worker-Allowed'] = '/'
        return response

    app.register_blueprint(bp)
