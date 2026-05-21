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
        script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
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
            this.loading = true;
            try {
                const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
                if (res.ok) {
                    const data = await res.json();
                    this.results = data.results || [];
                }
            } catch (e) {
                 console.error(e);
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
    document.addEventListener('DOMContentLoaded', function () {
        new MutationObserver(injectCsrfIntoForms).observe(
            document.body,
            { childList: true, subtree: true }
        );
    });

    // Patch window.fetch to send the CSRF header on every non-GET request
    var _origFetch = window.fetch;
    window.fetch = function (url, opts) {
        opts = opts || {};
        var method = (opts.method || 'GET').toUpperCase();
        if (method !== 'GET' && method !== 'HEAD') {
            opts.headers = Object.assign({}, opts.headers, {
                'X-CSRFToken': csrfToken
            });
        }
        return _origFetch.call(this, url, opts);
    };
})();
