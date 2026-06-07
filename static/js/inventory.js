// Inventory helpers: skeleton builders
function buildInventorySkeletonHtml(mode) {
    if (mode === 'list' || mode === 'compact') {
        return buildInventoryListSkeletonHtml();
    }
    return buildInventoryCardSkeletonHtml();
}

function buildInventoryCardSkeletonHtml() {
    const cards = Array.from({ length: 6 }).map(() => `
        <div class="ui-panel p-4 ui-panel-hover">
            <div class="flex items-start gap-3 mb-4">
                <div class="w-3 h-14 rounded-full bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="flex-1 space-y-2">
                    <div class="h-4 w-3/4 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                    <div class="h-3 w-1/2 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                </div>
                <div class="h-6 w-16 rounded-full bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            </div>
            <div class="space-y-2.5">
                <div class="h-2.5 w-full rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="h-2.5 w-5/6 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            </div>
            <div class="mt-4 flex justify-between">
                <div class="h-3 w-16 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="h-3 w-10 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            </div>
        </div>
    `).join('');
    return cards;
}

function buildInventoryListSkeletonHtml() {
    const rows = Array.from({ length: 8 }).map(() => `
        <div class="bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700 px-4 py-3 grid grid-cols-12 gap-3 items-center">
            <div class="col-span-1 h-5 w-5 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="col-span-5 sm:col-span-3 flex items-center gap-2">
                <div class="w-3 h-10 rounded-full bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="flex-1 space-y-2">
                    <div class="h-3.5 w-4/5 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                    <div class="h-3 w-2/5 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                </div>
            </div>
            <div class="hidden sm:block sm:col-span-2 h-3.5 w-3/4 justify-self-center rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="hidden sm:block sm:col-span-1 h-3.5 w-8 justify-self-center rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="hidden sm:block sm:col-span-1 h-3.5 w-12 justify-self-center rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="hidden sm:block sm:col-span-1 h-3.5 w-12 justify-self-center rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="col-span-3 sm:col-span-1 h-6 w-12 justify-self-center rounded-full bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="col-span-3 sm:col-span-2 flex justify-end gap-1.5">
                <div class="h-6 w-6 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="h-6 w-6 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
                <div class="h-6 w-6 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            </div>
        </div>
    `).join('');

    return `
        <div class="bg-white dark:bg-slate-800 p-2.5 rounded-t-lg border border-gray-100 dark:border-slate-700 border-b-0 mb-0 flex items-center justify-between gap-2">
            <div class="h-4 w-40 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
            <div class="h-8 w-32 rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
        </div>
        <div class="hidden sm:grid grid-cols-12 gap-3 bg-gray-100 dark:bg-slate-900 border-b border-gray-300 dark:border-slate-700 px-4 py-2 sticky top-0 z-10 rounded-t-lg mb-0">
            <div class="col-span-12 h-3.5 w-full rounded bg-gray-200/70 dark:bg-slate-700/60 ui-skeleton"></div>
        </div>
        ${rows}
    `;
}


let __lastCheckedFilament = null;

function updateBulkDeleteState() {
    const checkboxes = Array.from(document.querySelectorAll('.filament-select'));
    const checked = checkboxes.filter(cb => cb.checked);
    const countLabel = document.getElementById('selectedFilamentsCount');
    const deleteButton = document.getElementById('bulkDeleteButton');
    const selectAll = document.getElementById('selectAllFilaments');
    if (countLabel) countLabel.textContent = `${(window._filCtxT && window._filCtxT.selectedPrefix) || 'Selected:'} ${checked.length}`;
    if (deleteButton) deleteButton.disabled = checked.length === 0;
    if (selectAll) {
        selectAll.checked = checkboxes.length > 0 && checked.length === checkboxes.length;
        selectAll.indeterminate = checked.length > 0 && checked.length < checkboxes.length;
    }
}

function initBulkSelectionUI() {
    const checkboxes = Array.from(document.querySelectorAll('.filament-select'));
    const selectAll = document.getElementById('selectAllFilaments');
    __lastCheckedFilament = null;

    checkboxes.forEach((checkbox, index) => {
        checkbox.dataset.checkboxIndex = index;
        checkbox.onclick = (event) => {
            if (event.shiftKey && __lastCheckedFilament !== null) {
                const last = Number(__lastCheckedFilament.dataset.checkboxIndex);
                const current = Number(checkbox.dataset.checkboxIndex);
                const [start, end] = [Math.min(last, current), Math.max(last, current)];
                for (let i = start; i <= end; i += 1) {
                    checkboxes[i].checked = checkbox.checked;
                }
            }
            __lastCheckedFilament = checkbox;
            updateBulkDeleteState();
        };
        checkbox.onchange = null;
    });

    if (selectAll) {
        selectAll.onchange = () => {
            checkboxes.forEach((checkbox) => {
                checkbox.checked = selectAll.checked;
            });
            __lastCheckedFilament = null;
            updateBulkDeleteState();
        };
    }

    updateBulkDeleteState();
}

document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('useFilamentModal');
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === this) closeUseFilamentModal();
        });
    }
    const addSpoolModal = document.getElementById('addSpoolModal');
    if (addSpoolModal) {
        addSpoolModal.addEventListener('click', function (e) {
            if (e.target === this) closeAddSpoolModal();
        });
    }
    const addSpoolForm = document.getElementById('addSpoolForm');
    if (addSpoolForm) {
        addSpoolForm.addEventListener('submit', async function (event) {
            event.preventDefault();
            const submitButton = addSpoolForm.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true;
            try {
                const response = await fetch(addSpoolForm.action, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                    body: new FormData(addSpoolForm),
                });
                if (!response.ok) throw new Error('add_spool_failed');
                closeAddSpoolModal();
                if (window.__inv) {
                    await window.__inv.fetchContent(window.__inv.currentPage || 1);
                }
            } catch (e) {
                alert((window._filCtxT && window._filCtxT.addSpoolError) || 'Error adding spool.');
            } finally {
                if (submitButton) submitButton.disabled = false;
            }
        });
    }
    initBulkSelectionUI();
});


// Right-click context menu
(function() {
    'use strict';
    var _menu = null;
    function getCSRF() {
        var el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }
    function ensureMenu() {
        if (!_menu) {
            _menu = document.createElement('div');
            _menu.id = 'fil-ctx-menu';
            _menu.style.cssText = 'position:fixed;z-index:9999;display:none;min-width:170px';
            _menu.className = 'bg-white border border-gray-200 shadow-xl rounded-lg py-1 text-sm';
            _menu.addEventListener('click', function(e) { e.stopPropagation(); });
            document.body.appendChild(_menu);
        }
        return _menu;
    }
    window.openFilCtxMenu = function(e, el) {
        e.preventDefault();
        e.stopPropagation();
        var id = parseInt(el.dataset.filId, 10);
        var name = el.dataset.filName || '';
        var weight = parseFloat(el.dataset.filWeight) || 0;
        var editUrl = el.dataset.filEdit || '';
        var detailUrl = el.dataset.filDetail || '';
        var deleteUrl = el.dataset.filDelete || '';
        var isAdmin = el.dataset.filAdmin === '1';
        var shopUrl = el.dataset.filShop || '';
        var t = window._filCtxT || {};
        var truncName = name.length > 22 ? name.substring(0, 22) + '\u2026' : name;
        var safeName = truncName.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        // Attribute-escape values interpolated into HTML attributes
        var attrEsc = function(v) { return String(v).replace(/"/g, '&quot;'); };
        var html = '<div class="px-3 py-1.5 text-xs font-bold text-gray-400 uppercase tracking-wider border-b border-gray-100 mb-1">' + safeName + '</div>';
        if (isAdmin) {
            html += '<button type="button" id="_fctx_use" class="w-full text-left px-4 py-2 hover:bg-blue-50 hover:text-blue-700 transition-colors flex items-center gap-2"><i class="fa-solid fa-minus-circle w-4 text-blue-500"></i> ' + (t.use||'') + '</button>';
            html += '<button type="button" id="_fctx_add" class="w-full text-left px-4 py-2 hover:bg-emerald-50 hover:text-emerald-700 transition-colors flex items-center gap-2"><i class="fa-solid fa-plus-circle w-4 text-emerald-500"></i> ' + (t.addSpool||'') + '</button>';
            html += '<a href="' + attrEsc(editUrl) + '" class="w-full text-left px-4 py-2 hover:bg-gray-50 transition-colors flex items-center gap-2 block"><i class="fa-solid fa-edit w-4 text-gray-500"></i> ' + (t.edit||'') + '</a>';
        }
        html += '<a href="' + attrEsc(detailUrl) + '" class="w-full text-left px-4 py-2 hover:bg-gray-50 transition-colors flex items-center gap-2 block"><i class="fa-solid fa-wave-square w-4 text-indigo-400"></i> ' + (t.timeline||'') + '</a>';
        if (shopUrl) {
            html += '<div class="border-t border-gray-100 my-1"></div>';
            html += '<button type="button" id="_fctx_shop" class="w-full text-left px-4 py-2 hover:bg-orange-50 hover:text-orange-700 transition-colors flex items-center gap-2"><i class="fa-solid fa-cart-shopping w-4 text-orange-400"></i> ' + (t.shop||'') + '</button>';
        }
        if (isAdmin) {
            html += '<div class="border-t border-gray-100 my-1"></div>';
            html += '<button type="button" id="_fctx_del" class="w-full text-left px-4 py-2 hover:bg-red-50 hover:text-red-600 transition-colors flex items-center gap-2"><i class="fa-solid fa-trash w-4 text-red-400"></i> ' + (t.del||'') + '</button>';
        }
        var menu = ensureMenu();
        menu.innerHTML = html;
        // Attach handlers after innerHTML to avoid double-quote attribute escaping issues
        if (isAdmin) {
            var useBtn = menu.querySelector('#_fctx_use');
            if (useBtn) useBtn.addEventListener('click', function() {
                openUseFilamentModal(id, name, weight);
                window.closeFilCtxMenu();
            });
            var addBtn = menu.querySelector('#_fctx_add');
            if (addBtn) addBtn.addEventListener('click', function() {
                window.closeFilCtxMenu();
                openAddSpoolModal(id, name);
            });
            var delBtn = menu.querySelector('#_fctx_del');
            if (delBtn) delBtn.addEventListener('click', function() {
                window._filCtxDelete(id, deleteUrl);
            });
        }
        if (shopUrl) {
            var shopBtn = menu.querySelector('#_fctx_shop');
            if (shopBtn) shopBtn.addEventListener('click', function() {
                window.closeFilCtxMenu();
                var resolvedUrl = shopUrl.replace(/\{[^}]+\}/g, encodeURIComponent(name));
                window.open(resolvedUrl, '_blank', 'noopener,noreferrer');
            });
        }
        menu.style.display = 'block';
        var x = e.clientX, y = e.clientY;
        var mW = menu.offsetWidth, mH = menu.offsetHeight;
        if (x + mW > window.innerWidth - 5) x = window.innerWidth - mW - 5;
        if (y + mH > window.innerHeight - 5) y = window.innerHeight - mH - 5;
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
    };
    window.closeFilCtxMenu = function() {
        if (_menu) _menu.style.display = 'none';
    };
    window._filCtxDelete = function(id, url) {
        var t = window._filCtxT || {};
        closeFilCtxMenu();
        if (!confirm(t.confirmDelete || 'Delete?')) return;
        var f = document.createElement('form');
        f.method = 'POST'; f.action = url;
        var ci = document.createElement('input');
        ci.type = 'hidden'; ci.name = 'csrf_token'; ci.value = getCSRF();
        f.appendChild(ci);
        document.body.appendChild(f);
        f.submit();
    };
    document.addEventListener('click', window.closeFilCtxMenu);
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') window.closeFilCtxMenu();
    });
    document.addEventListener('contextmenu', function(e) {
        var el = e.target.closest('[data-fil-id]');
        if (!el) { window.closeFilCtxMenu(); return; }
        e.preventDefault();
        window.openFilCtxMenu(e, el);
    });
})();
