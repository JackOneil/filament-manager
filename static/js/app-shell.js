// Alpine.js Global Store for Shared State
document.addEventListener('alpine:init', () => {
    Alpine.store('appState', {
        theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
        sidebarPinned: localStorage.getItem('sidebarPinned') === 'true',
        mobileOpen: false,
        commandOpen: false,
        toggleSidebar() {
            this.sidebarPinned = !this.sidebarPinned;
            localStorage.setItem('sidebarPinned', this.sidebarPinned);
        },
        toggleMobile() {
            this.mobileOpen = !this.mobileOpen;
        },
        toggleCommand() {
            this.commandOpen = !this.commandOpen;
        }
    });
});

// Lazy loader helper for heavy JS libraries
window.loadScript = function(src) {
    if (!window.loadedScripts) {
        window.loadedScripts = {};
    }
    if (window.loadedScripts[src]) {
        return window.loadedScripts[src];
    }
    window.loadedScripts[src] = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = () => resolve(true);
        script.onerror = () => {
            // Clear the cache entry so a future call retries instead of
            // returning the stale rejection permanently.
            delete window.loadedScripts[src];
            reject(new Error(`Failed to load script: ${src}`));
        };
        document.head.appendChild(script);
    });
    return window.loadedScripts[src];
};

function appShell() {
    return {
        mounted: false,
        query: '',
        loading: false,
        results: [],
        staticItems: [],
        selectedIndex: 0,
        
        init() {
            this.$nextTick(() => { this.mounted = true; });
            if (this.$refs.commandItems) {
                this.staticItems = JSON.parse(this.$refs.commandItems.textContent || '[]');
            }
            this.$watch('query', (value) => {
                this.selectedIndex = 0;
                if (value.trim().length > 0) {
                    this.fetchResults(value);
                } else {
                    this.results = [];
                }
            });
            document.addEventListener('keydown', (event) => {
                const state = Alpine.store('appState');
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
                    event.preventDefault();
                    this.openCommand();
                }
                if (event.key === 'Escape') {
                    state.commandOpen = false;
                }
                if (state.commandOpen) {
                    if (event.key === 'ArrowDown') {
                        event.preventDefault();
                        if (this.selectedIndex < this.displayItems.length - 1) this.selectedIndex++;
                        this.scrollToSelected();
                    }
                    if (event.key === 'ArrowUp') {
                        event.preventDefault();
                        if (this.selectedIndex > 0) this.selectedIndex--;
                        this.scrollToSelected();
                    }
                    if (event.key === 'Enter') {
                        event.preventDefault();
                        const item = this.displayItems[this.selectedIndex];
                        if (item && item.url) window.location.href = item.url;
                        else if (item && item.href) window.location.href = item.href;
                    }
                }
            });
        },
        openCommand() {
            const state = Alpine.store('appState');
            state.commandOpen = true;
            this.query = '';
            this.results = [];
            this.selectedIndex = 0;
            this.$nextTick(() => {
                const input = this.$refs.commandInput;
                if (input) input.focus();
            });
        },
        scrollToSelected() {
            this.$nextTick(() => {
                const activeEl = this.$refs.resultsContainer?.querySelector('.is-selected');
                if (activeEl) {
                    activeEl.scrollIntoView({ block: 'nearest' });
                }
            });
        },
        async fetchResults(q) {
            // Cancel previous in-flight request to prevent race conditions
            if (this._abortController) {
                this._abortController.abort();
            }
            this._abortController = new AbortController();
            this.loading = true;
            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, {
                    signal: this._abortController.signal
                });
                if (res.ok) {
                    const data = await res.json();
                    this.results = data.results || [];
                }
            } catch (e) {
                if (e.name !== 'AbortError') {
                    console.error(e);
                }
            } finally {
                this.loading = false;
                this.scrollToSelected();
            }
        },
        get displayItems() {
            if (this.query.trim().length === 0) {
                 return this.staticItems;
            }
            const q = this.query.trim().toLowerCase();
            const filteredStatic = this.staticItems.filter((item) => {
                return [item.label, item.note, item.section].join(' ').toLowerCase().includes(q);
            });
            
            return [...filteredStatic, ...this.results];
        },
        get hasResults() {
            return this.displayItems.length > 0;
        }
    };
}

// ── CSRF auto-protection ──────────────────────────────────────────────
// Injects the CSRF token into every POST form and patches window.fetch
// so AJAX calls automatically include the X-CSRFToken header.
// Flask-WTF accepts the token either as a form field or this header.
(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return;
    var csrfToken = meta.getAttribute('content');

    function injectCsrfIntoForms() {
        document.querySelectorAll('form').forEach(function (form) {
            if (
                form.method &&
                form.method.toLowerCase() === 'post' &&
                !form.querySelector('[name="csrf_token"]')
            ) {
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'csrf_token';
                input.value = csrfToken;
                form.appendChild(input);
            }
        });
    }

    // Inject into forms already in the DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectCsrfIntoForms);
    } else {
        injectCsrfIntoForms();
    }

    // Inject into forms added by AJAX (e.g. fetchContent() in inventory)
    function startMutationObserver() {
        new MutationObserver(injectCsrfIntoForms).observe(
            document.body,
            { childList: true, subtree: true }
        );
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startMutationObserver);
    } else {
        startMutationObserver();
    }

    // ── Shop URL resolver ─────────────────────────────────────────────────
    // Shared by filament cards, list rows, stats, and overview widgets.
    // Replaces {query} (or any {placeholder}) in a shop URL template with
    // the URL-encoded filament name, then opens the result in a new tab.
    window.openReorderShop = function (name, template) {
        var url = template.replace(/\{[^}]+\}/g, encodeURIComponent(name));
        window.open(url, '_blank', 'noopener,noreferrer');
    };

    // ── CSRF auto-injection for window.fetch ────────────────────────────
    // Paired with the meta[name="csrf-token"] tag injected by base.html.
    // Every call to fetch() — including those from templates, third-party
    // libraries, and inline scripts — automatically gets the X-CSRFToken
    // header on non-GET/HEAD requests. We use new Headers(opts.headers)
    // instead of Object.assign() to preserve Headers-instance methods
    // (iteration, .get(), .set()) that Object.assign strips.
    // Skip blob: and data: URLs — they are internal browser resources.
    var _origFetch = window.fetch;
    window.fetch = function (url, opts) {
        var urlStr = (typeof url === 'string') ? url : (url && url.url) || '';
        if (/^(blob:|data:)/i.test(urlStr)) {
            return _origFetch.call(this, url, opts);
        }
        opts = opts || {};
        var method = (opts.method || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD') {
            var headers = new Headers(opts.headers || {});
            headers.set('X-CSRFToken', csrfToken);
            var newOpts = {};
            for (var k in opts) {
                if (k === 'headers') continue;
                newOpts[k] = opts[k];
            }
            newOpts.headers = headers;
            return _origFetch.call(this, url, newOpts);
        }
        return _origFetch.call(this, url, opts);
    };

    // ── Client-side toast helper ─────────────────────────────────────────
    // Used by JS code (e.g. optimistic reaction rollback) to display a
    // brief message. The container is injected into <body> on first use.
    // i18n: keys are resolved via the server-rendered __i18n map exposed
    // on the window (set in base.html). Falls back to the raw key.
    window.showToast = function (messageKey, category, opts) {
        category = category || 'info';
        opts = opts || {};
        var ttl = opts.ttl || 4000;
        var actions = opts.actions || [];
        var lang = (window.__helpLang || 'cs');
        var dict = (window.__i18n && window.__i18n[lang]) || {};
        var text = dict[messageKey] || messageKey;

        var container = document.getElementById('client-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'client-toast-container';
            container.className = 'fixed bottom-6 right-6 z-[60] flex flex-col gap-2 pointer-events-none';
            document.body.appendChild(container);
        }

        var palette = {
            info:    'bg-slate-50 border-slate-200 text-slate-800 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-100',
            success: 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/95 dark:border-green-700 dark:text-green-100',
            error:   'bg-red-50 border-red-200 text-red-800 dark:bg-red-900/95 dark:border-red-700 dark:text-red-100',
        }[category] || 'bg-slate-50 border-slate-200 text-slate-800';

        var icon = {
            info:    'fa-circle-info text-slate-500',
            success: 'fa-circle-check text-green-500',
            error:   'fa-circle-exclamation text-red-500',
        }[category] || 'fa-circle-info text-slate-500';

        var toast = document.createElement('div');
        toast.className = 'rounded-lg border px-4 py-3 shadow-xl flex items-start gap-3 backdrop-blur-md pointer-events-auto ' + palette;
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');

        var html = '<div class="mt-0.5"><i class="fa-solid ' + icon + '"></i></div>' +
                   '<div class="flex-1 min-w-0 font-medium">' + escapeHtml(text) + '</div>';
        if (actions.length) {
            html += '<div class="flex gap-2">';
            actions.forEach(function (a) {
                html += '<button type="button" data-action="' + escapeAttr(a.action) + '" class="text-xs font-semibold underline hover:no-underline">' + escapeHtml(a.label) + '</button>';
            });
            html += '</div>';
        }
        html += '<button type="button" class="opacity-50 hover:opacity-100 focus:outline-none transition-opacity" aria-label="close">' +
                '<i class="fa-solid fa-xmark"></i></button>';
        toast.innerHTML = html;

        var close = function () {
            if (!toast.parentNode) return;
            toast.style.transition = 'opacity 200ms, transform 200ms';
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(8px)';
            setTimeout(function () { toast.remove(); }, 220);
        };
        toast.querySelector('button[aria-label="close"]').addEventListener('click', close);
        actions.forEach(function (a) {
            var btn = toast.querySelector('button[data-action="' + cssEscape(a.action) + '"]');
            if (btn) btn.addEventListener('click', function () {
                try { a.onClick(); } finally { close(); }
            });
        });
        container.appendChild(toast);
        if (ttl > 0) setTimeout(close, ttl);
        return { close: close };
    };

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function escapeAttr(s) { return escapeHtml(s); }
    function cssEscape(s) { return String(s).replace(/[^a-zA-Z0-9_-]/g, '_'); }
})();
