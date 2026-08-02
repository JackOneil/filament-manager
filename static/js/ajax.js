/* Shared AJAX response/error helpers. */
(function () {
    'use strict';

    function text(key) {
        var lang = window.__helpLang || 'cs';
        var dictionaries = window.__i18n || {};
        return (dictionaries[lang] && dictionaries[lang][key]) || key;
    }

    function escapeHtml(value) {
        var node = document.createElement('div');
        node.textContent = value || '';
        return node.innerHTML;
    }

    function assertOk(response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response;
    }

    function renderError(container, options) {
        if (!container) return;
        options = options || {};
        var wrapper = document.createElement('div');
        wrapper.className = 'ajax-error-state flex flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50/70 dark:border-red-900/60 dark:bg-red-950/30 p-8 text-center';
        wrapper.setAttribute('role', 'alert');
        wrapper.setAttribute('aria-live', 'polite');

        var icon = document.createElement('i');
        icon.className = 'fa-solid fa-circle-exclamation text-2xl text-red-500';
        icon.setAttribute('aria-hidden', 'true');
        wrapper.appendChild(icon);

        var message = document.createElement('p');
        message.className = 'text-sm font-medium text-red-700 dark:text-red-300';
        message.textContent = options.message || text('ajax_load_error');
        wrapper.appendChild(message);

        if (typeof options.onRetry === 'function') {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'inline-flex items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-400';
            button.innerHTML = '<i class="fa-solid fa-rotate-right" aria-hidden="true"></i><span>' + escapeHtml(options.retryLabel || text('ajax_retry')) + '</span>';
            button.addEventListener('click', function () {
                button.disabled = true;
                options.onRetry();
            });
            wrapper.appendChild(button);
        }
        container.replaceChildren(wrapper);
    }

    window.ajaxUi = {
        assertOk: assertOk,
        renderError: renderError,
        text: text,
    };
}());
