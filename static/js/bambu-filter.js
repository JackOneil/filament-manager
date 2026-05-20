        (function () {
            var KEY = 'bambu_hide_failed';

            function applyRememberedBambuFilters() {
                var hideFailed = localStorage.getItem(KEY) === '1';
                document.querySelectorAll('[data-bambu-remember-hide-failed]').forEach(function (link) {
                    var baseHref = link.dataset.baseHref || link.getAttribute('href');
                    if (!baseHref) return;
                    var url = new URL(baseHref, window.location.origin);
                    if (hideFailed) {
                        url.searchParams.set('hide_failed', '1');
                    } else {
                        url.searchParams.delete('hide_failed');
                    }
                    link.setAttribute('href', url.pathname + url.search + url.hash);
                });
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', applyRememberedBambuFilters);
            } else {
                applyRememberedBambuFilters();
            }
        })();
