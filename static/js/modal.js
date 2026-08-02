/* Shared accessible modal manager.
 * Modals remain plain DOM helpers so Alpine components and AJAX partials can
 * call the same API without registering Alpine plugins or replacing DOM trees.
 */
(function () {
    'use strict';

    var stack = [];
    var mainState = null;
    var sequence = 0;

    function focusable(root) {
        if (!root) return [];
        return Array.from(root.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
            'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter(function (el) {
            return !el.hasAttribute('hidden') && el.getClientRects().length > 0;
        });
    }

    function getPanel(element) {
        return element.querySelector('[data-modal-panel]') || element.firstElementChild || element;
    }

    function lockMain() {
        if (mainState) return;
        var main = document.querySelector('main');
        if (!main) return;
        mainState = { element: main, overflow: main.style.overflow };
        main.style.overflow = 'hidden';
    }

    function unlockMain() {
        if (!mainState) return;
        mainState.element.style.overflow = mainState.overflow;
        mainState = null;
    }

    function focusInitial(entry) {
        var target = entry.options.initialFocus;
        if (typeof target === 'string') target = entry.element.querySelector(target);
        if (!target) target = entry.element.querySelector('[autofocus]');
        if (!target) target = focusable(getPanel(entry.element))[0];
        if (target && typeof target.focus === 'function') target.focus({ preventScroll: true });
    }

    function open(element, options) {
        if (!element) return;
        options = options || {};
        var existing = stack.find(function (entry) { return entry.element === element; });
        if (existing) {
            focusInitial(existing);
            return;
        }

        var title = options.titleId || (element.querySelector('[data-modal-title]') || {}).id;
        if (!title) {
            var titleElement = element.querySelector('h1, h2, h3, [role="heading"]');
            if (titleElement) {
                if (!titleElement.id) titleElement.id = 'modal-title-' + (++sequence);
                title = titleElement.id;
            }
        }

        var entry = {
            element: element,
            options: options,
            returnFocus: options.focusReturnTo || document.activeElement,
            scrollTop: document.querySelector('main') ? document.querySelector('main').scrollTop : 0,
        };
        element.classList.remove('hidden');
        element.setAttribute('role', element.getAttribute('role') || 'dialog');
        element.setAttribute('aria-modal', 'true');
        element.setAttribute('aria-hidden', 'false');
        if (title) element.setAttribute('aria-labelledby', title);
        stack.push(entry);
        lockMain();
        window.requestAnimationFrame(function () { focusInitial(entry); });
    }

    function close(element) {
        if (!element) return;
        var index = stack.findIndex(function (entry) { return entry.element === element; });
        if (index === -1) {
            element.classList.add('hidden');
            element.setAttribute('aria-hidden', 'true');
            return;
        }
        var entry = stack[index];
        stack.splice(index, 1);
        element.classList.add('hidden');
        element.setAttribute('aria-hidden', 'true');
        if (stack.length === 0) {
            unlockMain();
            var main = document.querySelector('main');
            if (main) main.scrollTop = entry.scrollTop;
        }
        var restore = entry.options.focusReturnTo || entry.returnFocus;
        if (restore && document.contains(restore) && typeof restore.focus === 'function') {
            window.requestAnimationFrame(function () { restore.focus({ preventScroll: true }); });
        }
        if (typeof entry.options.onClose === 'function') entry.options.onClose();
    }

    function closeTop() {
        if (stack.length) close(stack[stack.length - 1].element);
    }

    function trapFocus(event) {
        if (!stack.length || event.key !== 'Tab') return;
        var entry = stack[stack.length - 1];
        var items = focusable(getPanel(entry.element));
        if (!items.length) {
            event.preventDefault();
            entry.element.focus({ preventScroll: true });
            return;
        }
        var first = items[0];
        var last = items[items.length - 1];
        if (!entry.element.contains(document.activeElement)) {
            event.preventDefault();
            first.focus({ preventScroll: true });
        } else if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus({ preventScroll: true });
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus({ preventScroll: true });
        }
    }

    document.addEventListener('keydown', function (event) {
        if (!stack.length) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeTop();
            return;
        }
        trapFocus(event);
    }, true);

    document.addEventListener('click', function (event) {
        if (stack.length && event.target === stack[stack.length - 1].element) {
            var rootEntry = stack[stack.length - 1];
            if (rootEntry.options.backdropClose !== false) close(rootEntry.element);
            return;
        }
        var closeButton = event.target.closest && event.target.closest('[data-modal-close]');
        if (closeButton) {
            var closeModal = closeButton.closest('[data-modal]');
            if (closeModal) {
                event.preventDefault();
                close(closeModal);
                return;
            }
        }
        var backdrop = event.target.closest && event.target.closest('[data-modal-backdrop]');
        if (backdrop) {
            var backdropModal = backdrop.closest('[data-modal]');
            if (backdropModal && backdropModal.dataset.modalBackdropClose !== 'false') close(backdropModal);
        }
    });

    window.modal = {
        open: open,
        close: close,
        closeTop: closeTop,
        isOpen: function (element) { return stack.some(function (entry) { return entry.element === element; }); },
        get stack() { return stack.slice(); },
    };
}());
