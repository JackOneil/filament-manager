// ── Filament Manager — Shared Dashboard Module ───────────────────────────────
// Provides unified widget layout management used across all dashboard pages:
//   Overview (/), Projects (/projects), Statistics (/stats)
//
// NEVER include Jinja2 template syntax here — pass all translated strings as
// config parameters. This file must be pure, static JavaScript.
//
// Exports (globals):
//   createWidgetLayoutManager(config)   – flat-grid pages (Overview, Projects)
//   createCardResizeManager(config)     – card-level resize/limits (Statistics)
// ─────────────────────────────────────────────────────────────────────────────

'use strict';

// ── Shared resize corner SVG icon ─────────────────────────────────────────────
var _DASH_RESIZE_SVG = '<svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" style="pointer-events:none;opacity:.7"><path d="M0 10 L10 0 L10 2 L2 10 Z M4 10 L10 4 L10 6 L6 10 Z M8 10 L10 8 L10 10 Z"/></svg>';

// ── Widget colour palette ─────────────────────────────────────────────────────
// 9 accent tints (+ empty id = no colour). Stored as id string in layout.colors.
var _DASH_COLORS = [
    { id: '',       dot: null,        bg_l: '',                            bg_d: '' },
    { id: 'blue',   dot: '#3b82f6',   bg_l: 'rgba(59,130,246,0.07)',       bg_d: 'rgba(59,130,246,0.14)' },
    { id: 'green',  dot: '#10b981',   bg_l: 'rgba(16,185,129,0.07)',       bg_d: 'rgba(16,185,129,0.14)' },
    { id: 'amber',  dot: '#f59e0b',   bg_l: 'rgba(245,158,11,0.08)',       bg_d: 'rgba(245,158,11,0.14)' },
    { id: 'red',    dot: '#ef4444',   bg_l: 'rgba(239,68,68,0.07)',        bg_d: 'rgba(239,68,68,0.14)' },
    { id: 'purple', dot: '#8b5cf6',   bg_l: 'rgba(139,92,246,0.07)',       bg_d: 'rgba(139,92,246,0.14)' },
    { id: 'rose',   dot: '#f472b6',   bg_l: 'rgba(244,114,182,0.07)',      bg_d: 'rgba(244,114,182,0.14)' },
    { id: 'cyan',   dot: '#06b6d4',   bg_l: 'rgba(6,182,212,0.07)',        bg_d: 'rgba(6,182,212,0.14)' },
    { id: 'slate',  dot: '#64748b',   bg_l: 'rgba(100,116,139,0.07)',      bg_d: 'rgba(100,116,139,0.16)' },
];

function _dashGetBg(colorId) {
    var isDark = document.documentElement.classList.contains('dark');
    for (var i = 0; i < _DASH_COLORS.length; i++) {
        if (_DASH_COLORS[i].id === (colorId || '')) {
            return isDark ? _DASH_COLORS[i].bg_d : _DASH_COLORS[i].bg_l;
        }
    }
    return '';
}

function _dashColorDot(colorId) {
    for (var i = 0; i < _DASH_COLORS.length; i++) {
        if (_DASH_COLORS[i].id === (colorId || '')) return _DASH_COLORS[i].dot;
    }
    return null;
}

// Register "close open pickers on outside click" handler globally (once).
var _dashPickerCloseReg = false;
function _dashEnsurePickerClose() {
    if (_dashPickerCloseReg) return;
    _dashPickerCloseReg = true;
    document.addEventListener('mousedown', function(e) {
        if (!e.target.closest || !e.target.closest('.widget-color-wrap')) {
            document.querySelectorAll('.widget-color-picker').forEach(function(p) {
                p.classList.add('hidden');
            });
        }
    });
}

// Returns the inner visual card element to which background colour should be applied.
// For flat-grid pages, items are wrapper <section> elements; the card itself is the
// first child .ui-panel / .ui-card-soft / .ui-card inside it.
function _dashInnerCard(item) {
    return item.querySelector(':scope > .ui-panel') ||
           item.querySelector(':scope > .ui-card-soft') ||
           item.querySelector(':scope > .ui-card') ||
           item;
}

function _dashUpdateColorBtnUI(btn, colorId) {
    var dot = _dashColorDot(colorId);
    if (dot) {
        btn.innerHTML = '<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:' +
            dot + ';border:2px solid rgba(0,0,0,0.15)"></span>';
        btn.title = colorId.charAt(0).toUpperCase() + colorId.slice(1);
    } else {
        btn.innerHTML = '<i class="fa-solid fa-palette text-xs text-gray-400"></i>';
        btn.title = 'Color';
    }
}

// Build a colour-picker button with dropdown. Returns a wrapper <div>.
// onSelect(colorId) is called when the user picks a colour.
function _dashMakeColorPickerBtn(currentColorId, onSelect) {
    _dashEnsurePickerClose();
    var wrap = document.createElement('div');
    wrap.className = 'widget-color-wrap relative inline-flex';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'widget-color-btn w-7 h-7 flex items-center justify-center rounded transition hover:bg-blue-50';
    _dashUpdateColorBtnUI(btn, currentColorId || '');

    // Picker dropdown shell
    var pickerOuter = document.createElement('div');
    pickerOuter.className = 'widget-color-picker hidden absolute z-[999] right-0 top-full mt-1.5';

    var pickerInner = document.createElement('div');
    pickerInner.style.cssText = 'min-width:156px';
    pickerInner.className = 'bg-white border border-gray-200 rounded-xl shadow-xl p-2.5';

    var grid = document.createElement('div');
    grid.className = 'grid grid-cols-5 gap-1.5';

    _DASH_COLORS.forEach(function(color) {
        var isActive = (color.id || '') === (currentColorId || '');
        var swatch = document.createElement('button');
        swatch.type  = 'button';
        swatch.title = color.id || 'Default';

        if (!color.id) {
            swatch.className = 'w-7 h-7 rounded-lg flex items-center justify-center border-2 transition-all bg-gray-50 ' +
                (isActive ? 'border-blue-500' : 'border-gray-200 hover:border-gray-400');
            swatch.innerHTML = '<i class="fa-solid fa-ban text-gray-300 text-xs"></i>';
        } else {
            swatch.className = 'w-7 h-7 rounded-full border-2 transition-all ' +
                (isActive ? 'border-blue-500 ring-2 ring-offset-1 ring-blue-300' : 'border-white hover:scale-110 hover:border-gray-300');
            swatch.style.backgroundColor = color.dot;
        }

        swatch.addEventListener('click', function(e) {
            e.stopPropagation();
            pickerOuter.classList.add('hidden');
            _dashUpdateColorBtnUI(btn, color.id);
            // Refresh active ring on sibling swatches
            grid.querySelectorAll('button').forEach(function(s, si) {
                var c = _DASH_COLORS[si];
                if (!c) return;
                var active = (c.id || '') === (color.id || '');
                if (!c.id) {
                    s.className = 'w-7 h-7 rounded-lg flex items-center justify-center border-2 transition-all bg-gray-50 ' +
                        (active ? 'border-blue-500' : 'border-gray-200 hover:border-gray-400');
                } else {
                    s.className = 'w-7 h-7 rounded-full border-2 transition-all ' +
                        (active ? 'border-blue-500 ring-2 ring-offset-1 ring-blue-300' : 'border-white hover:scale-110 hover:border-gray-300');
                }
            });
            onSelect(color.id);
        });
        grid.appendChild(swatch);
    });

    pickerInner.appendChild(grid);
    pickerOuter.appendChild(pickerInner);
    wrap.appendChild(btn);
    wrap.appendChild(pickerOuter);

    btn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var isHidden = pickerOuter.classList.contains('hidden');
        // Close all other pickers first
        document.querySelectorAll('.widget-color-picker').forEach(function(p) {
            p.classList.add('hidden');
        });
        if (isHidden) pickerOuter.classList.remove('hidden');
    });

    return wrap;
}


// ── createWidgetLayoutManager ─────────────────────────────────────────────────
// Used by: Overview (overview.html), Projects (projects_index.html)
//
// Config shape:
//   containerId        – ID of the grid wrapper
//   scopeId            – ID of the page scope element (gets 'layout-edit-mode' class)
//   storageKey         – localStorage key
//   editButtonId       – ID of the edit/done toggle button
//   labelId            – ID of the button label span
//   hintId             – ID of the edit-mode hint bar
//   visibilityPanelId  – ID of the widget overview panel
//   editText           – "Edit layout" button label (translated)
//   doneText           – "Done" button label (translated)
//   hideBtnTitle       – "Hide widget" tooltip (translated)
//   showBtnTitle       – "Show widget" tooltip (translated)
//   limitAllText       – "All" option for row-limit selector (translated)
//   defaultOrder       – array of widget IDs for fallback order
//   itemSelector       – CSS selector for items (default: '[data-widget-id]')
//   mdGridCols         – number of grid columns at the md breakpoint (default: 1)
//                        Set to 2 if the grid container uses md:grid-cols-2.
//                        When 1, md:col-span-* classes are suppressed to prevent
//                        implicit grid-column creation in a 1-col md grid.
//
// Features:
//   • FLIP-animated live reorder during drag (items slide into position as you drag)
//   • Clean pill-style drag ghost with subtle shadow
//   • Resize handles with snap-to-grid
//   • Colour pickers, visibility panel, row-limit selectors
//   • localStorage persistence of order, sizes, heights, visibility, limits, colors
// ─────────────────────────────────────────────────────────────────────────────
function createWidgetLayoutManager(config) {
    var container = document.getElementById(config.containerId);
    if (!container) {
        return { toggleEditMode: function(){}, moveUp: function(){}, moveDown: function(){}, reset: function(){} };
    }

    var itemSelector = config.itemSelector || '[data-widget-id]';
    var defaultOrder = config.defaultOrder || [];
    var limitAllText = config.limitAllText  || 'All';
    var hideBtnTitle = config.hideBtnTitle  || 'Hide';
    var showBtnTitle = config.showBtnTitle  || 'Show';
    var mdGridCols   = config.mdGridCols    || 1;
    var layout       = loadLayout();
    var editMode     = false;
    var dragSrc      = null;
    var dragGhostEl  = null;
    var resizeState  = null;
    var _flipLock    = false;  // Prevent concurrent FLIP animations

    // ========================================================================
    //  STORAGE
    // ========================================================================
    function loadLayout() {
        try {
            var raw = JSON.parse(localStorage.getItem(config.storageKey) || '{}');
            var order = Array.isArray(raw.order) ? raw.order : defaultOrder.slice();
            // Append any newly-added widget IDs missing from a saved (stale) order
            defaultOrder.forEach(function(id) {
                if (order.indexOf(id) === -1) order.push(id);
            });
            return {
                order:      order,
                sizes:      raw.sizes      && typeof raw.sizes      === 'object' ? raw.sizes      : {},
                heights:    raw.heights    && typeof raw.heights    === 'object' ? raw.heights    : {},
                visibility: raw.visibility && typeof raw.visibility === 'object' ? raw.visibility : {},
                limits:     raw.limits     && typeof raw.limits     === 'object' ? raw.limits     : {},
                colors:     raw.colors     && typeof raw.colors     === 'object' ? raw.colors     : {}
            };
        } catch (e) {
            return { order: defaultOrder.slice(), sizes: {}, heights: {}, visibility: {}, limits: {}, colors: {} };
        }
    }

    function items() {
        return Array.from(container.querySelectorAll(':scope > ' + itemSelector));
    }

    function saveLayout() {
        layout.order = items().map(function(item) { return item.dataset.widgetId; });
        localStorage.setItem(config.storageKey, JSON.stringify(layout));
    }

    // ========================================================================
    //  CSS HELPERS
    // ========================================================================
    function clearSizeClasses(item) {
        item.className = item.className
            .replace(/\bxl:col-span-\d+\b/g, '')
            .replace(/\bmd:col-span-\d+\b/g, '')
            .replace(/\bcol-span-\d+\b/g, '')
            .replace(/\s{2,}/g, ' ')
            .trim();
    }

    function spanClass(size) {
        if (mdGridCols >= 2) {
            return 'col-span-1 md:col-span-' + Math.min(size, mdGridCols) + ' xl:col-span-' + size;
        }
        return 'xl:col-span-' + size;
    }

    // ========================================================================
    //  FLIP ANIMATION — smooth reorder transitions
    // ========================================================================
    // Capture the current bounding rect of every widget (keyed by widget ID).
    function _captureRects() {
        var rects = {};
        items().forEach(function(item) {
            var id = item.dataset.widgetId;
            if (id) rects[id] = item.getBoundingClientRect();
        });
        return rects;
    }

    // Animate all widgets from previously-captured positions to their current
    // positions. The dragged element is skipped (its own opacity animation runs).
    function _flipAnimate(beforeRects, duration) {
        if (_flipLock) return;
        _flipLock = true;
        var dur = duration || 220;

        var afterRects = _captureRects();
        items().forEach(function(item) {
            var id = item.dataset.widgetId;
            if (!id) return;
            if (item === dragSrc) return;           // dragged item has its own visual
            if (item.dataset._flipAnimating === '1') return; // prevent double-animation

            var b = beforeRects[id];
            var a = afterRects[id];
            if (!b || !a) return;

            var dx = b.left - a.left;
            var dy = b.top  - a.top;
            if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

            item.dataset._flipAnimating = '1';
            item.animate(
                [
                    { transform: 'translate(' + dx + 'px, ' + dy + 'px)' },
                    { transform: 'translate(0, 0)' }
                ],
                {
                    duration: dur,
                    easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
                    fill: 'backwards'
                }
            ).onfinish = function() {
                item.dataset._flipAnimating = '0';
            };
        });

        // Release the lock after all animations should be done
        setTimeout(function() { _flipLock = false; }, dur + 50);
    }

    // ========================================================================
    //  LAYOUT APPLY — restore saved state on page load
    // ========================================================================
    function applyLayout(animate) {
        var map = {};
        items().forEach(function(item) {
            var id = item.dataset.widgetId;
            map[id] = item;

            // Cache default span classes on first call
            if (!item.dataset.defaultSpanClass) {
                var cls   = item.className || '';
                var parts = [];
                var base  = cls.match(/\bcol-span-\d+\b/);
                var md    = cls.match(/\bmd:col-span-\d+\b/);
                var xl    = cls.match(/\bxl:col-span-\d+\b/);
                if (base) parts.push(base[0]);
                if (md)   parts.push(md[0]);
                if (xl)   parts.push(xl[0]);
                item.dataset.defaultSpanClass = parts.join(' ');
            }

            // Span size
            clearSizeClasses(item);
            var savedSize = layout.sizes && layout.sizes[id];
            if (savedSize) {
                var classes = savedSize.split(/\s+/).filter(Boolean);
                if (mdGridCols < 2) {
                    // Strip col-span-* and md:col-span-* — grid is 1-col below xl,
                    // applying these would create unwanted implicit grid columns.
                    classes = classes.filter(function(c) { return /^xl:col-span-/.test(c); });
                }
                item.classList.add.apply(item.classList, classes);
            } else if (item.dataset.defaultSpanClass) {
                item.classList.add.apply(item.classList, item.dataset.defaultSpanClass.split(/\s+/).filter(Boolean));
            }

            // Visibility: in edit mode show hidden widgets at opacity-50 (toggle-able);
            // outside edit mode hide completely.
            var isHidden = layout.visibility && layout.visibility[id] === false;
            if (isHidden) {
                item.style.display = editMode ? '' : 'none';
                if (editMode) item.classList.add('opacity-50');
            } else {
                item.style.display = '';
                item.classList.remove('opacity-50');
            }

            // Height
            item.style.minHeight = (layout.heights && layout.heights[id]) ? layout.heights[id] + 'px' : '';

            // Background colour (applied to inner visual card, not the wrapper)
            _dashInnerCard(item).style.backgroundColor = _dashGetBg((layout.colors && layout.colors[id]) || '');

            // Resize handle (add once)
            if (!item.querySelector('.resize-handle')) addResizeHandle(item, id);

            // Edit bar controls
            var bar = item.querySelector('.dashboard-edit-bar');
            if (bar) {
                var mlAuto = bar.querySelector('.ml-auto');

                // Row-limit selector (add once when indexed rows exist)
                if (!bar.querySelector('.widget-limit-select')) {
                    var hasRows = item.querySelectorAll('[data-row-index]').length > 0;
                    if (hasRows) {
                        var sel = document.createElement('select');
                        sel.className = 'widget-limit-select text-xs border border-blue-200 rounded px-1 py-0.5 bg-white text-blue-700 ml-2';
                        sel.title = config.limitSelectTitle || 'Rows';
                        [5, 10, 20, 'all'].forEach(function(opt) {
                            var o = document.createElement('option');
                            o.value = String(opt);
                            o.textContent = (opt === 'all') ? limitAllText : String(opt);
                            sel.appendChild(o);
                        });
                        var curLim = (layout.limits && layout.limits[id] !== undefined) ? String(layout.limits[id]) : '10';
                        sel.value = curLim;
                        sel.addEventListener('change', function(e) {
                            if (!layout.limits) layout.limits = {};
                            layout.limits[id] = e.target.value;
                            applyWidgetLimits();
                            saveLayout();
                        });
                        bar.insertBefore(sel, mlAuto || null);
                    }
                }

                // Colour picker (add once)
                if (!bar.querySelector('.widget-color-wrap')) {
                    var colorWrap = _dashMakeColorPickerBtn(
                        (layout.colors && layout.colors[id]) || '',
                        (function(wid) {
                            return function(colorId) {
                                if (!layout.colors) layout.colors = {};
                                layout.colors[wid] = colorId;
                                var el = document.querySelector('[data-widget-id="' + wid + '"]');
                                if (el) _dashInnerCard(el).style.backgroundColor = _dashGetBg(colorId);
                                syncVisibility();  // refresh dot in overview panel
                                saveLayout();
                            };
                        }(id))
                    );
                    if (mlAuto) mlAuto.insertBefore(colorWrap, mlAuto.firstChild);
                    else bar.appendChild(colorWrap);
                }

                // Hide/show toggle (find or create; always refresh state)
                var hideBtn = bar.querySelector('.widget-hide-btn');
                if (!hideBtn) {
                    hideBtn    = document.createElement('button');
                    hideBtn.type = 'button';
                    var colorW = bar.querySelector('.widget-color-wrap');
                    if (mlAuto) {
                        mlAuto.insertBefore(hideBtn, colorW ? colorW.nextSibling : mlAuto.firstChild);
                    } else {
                        bar.appendChild(hideBtn);
                    }
                }
                // Refresh the button state on every applyLayout call
                hideBtn.className = 'widget-hide-btn w-7 h-7 flex items-center justify-center rounded transition ' +
                    (isHidden
                        ? 'text-amber-500 hover:bg-amber-50 hover:text-amber-600'
                        : 'text-gray-400 hover:bg-red-50 hover:text-red-500');
                hideBtn.title     = isHidden ? showBtnTitle : hideBtnTitle;
                hideBtn.innerHTML = '<i class="fa-solid ' + (isHidden ? 'fa-eye' : 'fa-eye-slash') + ' text-xs"></i>';
                hideBtn.onclick   = (function(wid, hidden) {
                    return function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        // hidden=true  → widget was hidden  → set to true  (show it)
                        // hidden=false → widget was visible → set to false (hide it)
                        layout.visibility[wid] = hidden;
                        applyLayout();
                        syncVisibility();
                        saveLayout();
                    };
                }(id, isHidden));
            }
        });

        // Re-order DOM items (with FLIP animation if requested)
        if (animate && items().length > 0) {
            var beforeRects = _captureRects();
            layout.order.forEach(function(id) {
                if (map[id]) { container.appendChild(map[id]); delete map[id]; }
            });
            Object.values(map).forEach(function(item) { container.appendChild(item); });
            _flipAnimate(beforeRects, 280);
        } else {
            layout.order.forEach(function(id) {
                if (map[id]) { container.appendChild(map[id]); delete map[id]; }
            });
            Object.values(map).forEach(function(item) { container.appendChild(item); });
        }
        saveLayout();
    }

    // ========================================================================
    //  RESIZE
    // ========================================================================
    function getMaxCols() {
        var m = (container.className || '').match(/xl:grid-cols-(\d+)/);
        return m ? parseInt(m[1], 10) : 4;
    }

    function getColWidth() {
        var maxCols = getMaxCols();
        var style   = getComputedStyle(container);
        var gap     = parseFloat(style.columnGap) || parseFloat(style.gap) || 24;
        return (container.getBoundingClientRect().width - (maxCols - 1) * gap) / maxCols;
    }

    function addResizeHandle(item, id) {
        var handle = document.createElement('div');
        handle.className = 'resize-handle';
        handle.setAttribute('draggable', 'false');
        handle.title     = 'Resize';
        handle.innerHTML = _DASH_RESIZE_SVG;
        item.appendChild(handle);

        handle.addEventListener('mousedown', function(e) {
            if (!editMode) return;
            e.preventDefault();
            e.stopPropagation();
            var rect      = item.getBoundingClientRect();
            var xlMatch   = (item.className || '').match(/xl:col-span-(\d+)/);
            var defMatch  = (item.dataset.defaultSpanClass || '').match(/xl:col-span-(\d+)/);
            var startCols = xlMatch  ? parseInt(xlMatch[1], 10)  : (defMatch ? parseInt(defMatch[1], 10) : 1);
            resizeState = {
                item: item, id: id,
                startX: e.clientX, startY: e.clientY,
                startCols: startCols, startHeight: rect.height,
                currentCols: startCols, currentHeight: rect.height
            };
            document.addEventListener('mousemove', onGlobalMouseMove);
            document.addEventListener('mouseup',   onGlobalMouseUp);
            document.body.classList.add('resize-dragging');
        });
    }

    function onGlobalMouseMove(e) {
        if (!resizeState) return;
        var maxCols   = getMaxCols();
        var colWidth  = getColWidth();
        var newCols   = Math.max(1, Math.min(maxCols, Math.round(resizeState.startCols + (e.clientX - resizeState.startX) / colWidth)));
        var ROW_SNAP  = 80;
        var newHeight = Math.max(ROW_SNAP, Math.round((resizeState.startHeight + (e.clientY - resizeState.startY)) / ROW_SNAP) * ROW_SNAP);
        clearSizeClasses(resizeState.item);
        if (mdGridCols >= 2) {
            resizeState.item.classList.add('col-span-1', 'md:col-span-' + Math.min(newCols, mdGridCols), 'xl:col-span-' + newCols);
        } else {
            resizeState.item.classList.add('xl:col-span-' + newCols);
        }
        resizeState.item.style.minHeight = newHeight + 'px';
        resizeState.currentCols   = newCols;
        resizeState.currentHeight = newHeight;
    }

    function onGlobalMouseUp() {
        if (!resizeState) return;
        if (resizeState.currentCols !== resizeState.startCols) {
            layout.sizes[resizeState.id] = spanClass(resizeState.currentCols);
        }
        if (resizeState.currentHeight !== resizeState.startHeight) {
            if (!layout.heights) layout.heights = {};
            layout.heights[resizeState.id] = resizeState.currentHeight;
        }
        document.removeEventListener('mousemove', onGlobalMouseMove);
        document.removeEventListener('mouseup',   onGlobalMouseUp);
        document.body.classList.remove('resize-dragging');
        resizeState = null;
        saveLayout();
        applyLayout();
    }

    // ========================================================================
    //  DRAG GHOST — clean pill-style badge
    // ========================================================================
    function makeDragGhost(item) {
        var titleEl = item.querySelector('.dashboard-edit-bar span.text-sm') ||
                      item.querySelector('h2') ||
                      item.querySelector('[class*="font-bold"]');
        var title = titleEl ? titleEl.textContent.trim().substring(0, 40) : 'Widget';

        var wrapper = document.createElement('div');
        wrapper.style.position = 'fixed';
        wrapper.style.top = '-9999px';
        wrapper.style.left = '-9999px';
        wrapper.style.pointerEvents = 'none';
        wrapper.style.zIndex = '9999';
        wrapper.style.opacity = '0.95';
        wrapper.style.transition = 'none';

        // Inner pill
        var pill = document.createElement('div');
        pill.style.cssText =
            'background:white;' +
            'border-radius:12px;' +
            'padding:10px 18px;' +
            'box-shadow:0 16px 40px rgba(15,23,42,0.22),0 0 0 1px rgba(59,130,246,0.25);' +
            'display:flex;align-items:center;gap:10px;' +
            'font-family:"Plus Jakarta Sans",ui-sans-serif,system-ui,sans-serif;' +
            'white-space:nowrap;';
        pill.innerHTML =
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#3b82f6;flex-shrink:0;"></span>' +
            '<span style="font-weight:700;font-size:13px;color:#1e293b;">' + _escHtml(title) + '</span>';

        wrapper.appendChild(pill);
        document.body.appendChild(wrapper);
        return wrapper;
    }

    function _escHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ========================================================================
    //  DRAG-TO-REORDER — with live FLIP-animated reorder
    // ========================================================================
    function onDragStart(e) {
        if (resizeState) { e.preventDefault(); return; }
        dragSrc = this;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', this.dataset.widgetId);
        container.classList.add('drag-session');
        this.classList.add('drag-source', 'is-dragging');

        // Promote to own layer for smooth animations when other items FLIP
        this.style.willChange = 'transform, opacity';
        this.style.transition = 'none';

        try {
            dragGhostEl = makeDragGhost(this);
            // Position ghost at cursor via a follow handler
            var rect = this.getBoundingClientRect();
            e.dataTransfer.setDragImage(dragGhostEl, Math.round(rect.width * 0.15), 20);
            // Track ghost position manually for live cursor follow
            document.addEventListener('dragover', _trackGhost);
        } catch (_err) {
            if (dragGhostEl && dragGhostEl.parentNode) {
                dragGhostEl.parentNode.removeChild(dragGhostEl);
            }
            dragGhostEl = null;
        }
    }

    // Track the ghost to follow cursor (native dragimage doesn't follow precisely)
    function _trackGhost(e) {
        if (!dragGhostEl) return;
        dragGhostEl.style.left = (e.clientX + 16) + 'px';
        dragGhostEl.style.top  = (e.clientY - 10) + 'px';
    }

    function onDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    }

    function onDragEnter(e) {
        e.preventDefault();
        if (!dragSrc || this === dragSrc) return;

        var allItems = items();
        var srcIdx = allItems.indexOf(dragSrc);
        var dstIdx = allItems.indexOf(this);
        if (srcIdx < 0 || dstIdx < 0) return;

        // Determine insertion point: above or below the midpoint of target
        var targetRect = this.getBoundingClientRect();
        var midY = targetRect.top + targetRect.height / 2;

        // Capture positions before the move
        var beforeRects = _captureRects();

        // Compute new dstIdx after potential move
        var newSrcIdx = allItems.indexOf(dragSrc);

        if (e.clientY < midY) {
            // Insert before target
            if (newSrcIdx > dstIdx) {
                // Moving up: insert dragSrc before target
                container.insertBefore(dragSrc, this);
            } else if (newSrcIdx < dstIdx - 1) {
                // Target is further down, insert before the item just before target
                container.insertBefore(dragSrc, this);
            }
        } else {
            // Insert after target
            if (newSrcIdx < dstIdx) {
                // Moving down: insert dragSrc after target
                container.insertBefore(dragSrc, this.nextSibling);
            } else if (newSrcIdx > dstIdx + 1) {
                // Target is further up, insert after target
                container.insertBefore(dragSrc, this.nextSibling);
            }
        }

        // Animate the layout shift
        _flipAnimate(beforeRects, 200);

        // Show insertion indicator on the target
        // Remove from all first
        allItems.forEach(function(item) { item.classList.remove('drag-insert-before', 'drag-insert-after'); });
        // Add to current target
        if (e.clientY < midY) {
            this.classList.add('drag-insert-before');
        } else {
            this.classList.add('drag-insert-after');
        }

        // Visual highlight on the target area
        this.classList.add('drag-over');

        // Save layout progressively during drag for live feedback
        saveLayout();
    }

    function onDragLeave(e) {
        this.classList.remove('drag-over', 'drag-insert-before', 'drag-insert-after');
    }

    function onDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.classList.remove('drag-over', 'drag-insert-before', 'drag-insert-after');

        if (dragSrc && dragSrc !== this) {
            // Items are already in the correct order from live reorder; just save
            saveLayout();
            // Pulse animation on the drop target
            var dropTarget = this;
            dropTarget.classList.add('drop-pulse');
            setTimeout(function() {
                dropTarget.classList.remove('drop-pulse');
            }, 300);
        }
    }

    function onDragEnd() {
        this.classList.remove('is-dragging', 'drag-source');
        this.style.willChange = '';
        this.style.transition = '';
        items().forEach(function(i) {
            i.classList.remove('drag-over', 'drag-insert-before', 'drag-insert-after');
        });
        container.classList.remove('drag-session');
        if (dragGhostEl && dragGhostEl.parentNode) {
            dragGhostEl.parentNode.removeChild(dragGhostEl);
        }
        dragGhostEl = null;
        dragSrc = null;
        document.removeEventListener('dragover', _trackGhost);
        saveLayout();
    }

    function enableDrag() {
        items().forEach(function(item) {
            item.setAttribute('draggable', 'true');
            item.addEventListener('dragstart', onDragStart);
            item.addEventListener('dragover',  onDragOver);
            item.addEventListener('dragenter', onDragEnter);
            item.addEventListener('dragleave', onDragLeave);
            item.addEventListener('drop',      onDrop);
            item.addEventListener('dragend',   onDragEnd);
        });
    }

    function disableDrag() {
        items().forEach(function(item) {
            item.removeAttribute('draggable');
            item.removeEventListener('dragstart', onDragStart);
            item.removeEventListener('dragover',  onDragOver);
            item.removeEventListener('dragenter', onDragEnter);
            item.removeEventListener('dragleave', onDragLeave);
            item.removeEventListener('drop',      onDrop);
            item.removeEventListener('dragend',   onDragEnd);
            item.classList.remove('drag-over', 'drag-insert-before', 'drag-insert-after',
                                  'is-dragging', 'drag-source', 'drop-pulse');
            item.style.willChange = '';
            item.style.transition = '';
        });
        container.classList.remove('drag-session');
        if (dragGhostEl && dragGhostEl.parentNode) {
            dragGhostEl.parentNode.removeChild(dragGhostEl);
        }
        dragGhostEl = null;
        document.removeEventListener('dragover', _trackGhost);
    }

    // ========================================================================
    //  VISIBILITY PANEL — shown in edit mode, lists all widgets
    // ========================================================================
    function syncVisibility() {
        var panel = document.getElementById(config.visibilityPanelId);
        if (!panel) return;
        if (!editMode) {
            panel.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        var grid = panel.querySelector('.visibility-toggles');
        if (!grid) return;
        grid.innerHTML = '';

        items().forEach(function(item) {
            var id      = item.dataset.widgetId;
            var titleEl = item.querySelector('h2');
            var title   = titleEl ? titleEl.textContent.trim() : id;
            var isVis   = layout.visibility[id] !== false;
            var colorId = (layout.colors && layout.colors[id]) || '';
            var dot     = _dashColorDot(colorId);

            var card = document.createElement('div');
            card.className = 'flex items-center gap-2 px-3 py-2.5 rounded-xl border cursor-default transition-all ' +
                (isVis
                    ? 'border-gray-200 bg-white/80 dark:border-slate-600 dark:bg-slate-800/60'
                    : 'border-dashed border-gray-300 bg-gray-50 dark:border-slate-600 dark:bg-slate-800/30 opacity-60');

            // Colour dot
            var dotEl = document.createElement('div');
            dotEl.style.cssText = 'width:12px;height:12px;border-radius:50%;flex-shrink:0;border:1.5px solid rgba(0,0,0,0.12);background:' +
                (dot || (isVis ? '#e2e8f0' : '#cbd5e1'));
            card.appendChild(dotEl);

            // Widget title
            var titleSpan = document.createElement('span');
            titleSpan.className = 'flex-1 text-xs font-semibold truncate text-gray-700 dark:text-slate-300 min-w-0';
            titleSpan.textContent = title;
            card.appendChild(titleSpan);

            // Eye toggle button
            var eyeBtn = document.createElement('button');
            eyeBtn.type      = 'button';
            eyeBtn.innerHTML = '<i class="fa-solid ' + (isVis ? 'fa-eye' : 'fa-eye-slash') + ' text-xs"></i>';
            eyeBtn.title     = isVis ? hideBtnTitle : showBtnTitle;
            eyeBtn.className = 'w-6 h-6 flex-shrink-0 flex items-center justify-center rounded transition ' +
                (isVis
                    ? 'text-blue-500 hover:bg-blue-100 dark:hover:bg-blue-900/40'
                    : 'text-gray-400 hover:bg-green-100 hover:text-green-600 dark:hover:bg-green-900/40');
            eyeBtn.onclick = (function(wid, visible) {
                return function(e) {
                    e.stopPropagation();
                    layout.visibility[wid] = !visible;
                    saveLayout();
                    applyLayout();
                    syncVisibility();
                };
            }(id, isVis));
            card.appendChild(eyeBtn);

            grid.appendChild(card);
        });
    }

    // ========================================================================
    //  CONTROLS / EDIT MODE
    // ========================================================================
    function syncControls() {
        var scope = document.getElementById(config.scopeId) || container;
        var btn   = document.getElementById(config.editButtonId);
        var label = document.getElementById(config.labelId);
        var hint  = document.getElementById(config.hintId);
        if (editMode) {
            scope.classList.add('layout-edit-mode');
            if (btn) {
                btn.classList.add('bg-blue-600', 'text-white', 'border-blue-600', 'hover:bg-blue-700');
                btn.classList.remove('bg-white', 'text-gray-700', 'border-gray-300', 'hover:bg-gray-50');
            }
            if (label) label.textContent = config.doneText;
            if (hint)  hint.classList.remove('hidden');
            enableDrag();
        } else {
            scope.classList.remove('layout-edit-mode');
            if (btn) {
                btn.classList.remove('bg-blue-600', 'text-white', 'border-blue-600', 'hover:bg-blue-700');
                btn.classList.add('bg-white', 'text-gray-700', 'border-gray-300', 'hover:bg-gray-50');
            }
            if (label) label.textContent = config.editText;
            if (hint)  hint.classList.add('hidden');
            disableDrag();
        }
    }

    function toggleEditMode() {
        editMode = !editMode;
        syncControls();
        syncVisibility();
        applyLayout();
    }

    function moveUp(widgetId) {
        var all = items();
        var idx = all.findIndex(function(i) { return i.dataset.widgetId === widgetId; });
        if (idx > 0) {
            var beforeRects = _captureRects();
            container.insertBefore(all[idx], all[idx - 1]);
            saveLayout();
            _flipAnimate(beforeRects, 200);
        }
    }

    function moveDown(widgetId) {
        var all = items();
        var idx = all.findIndex(function(i) { return i.dataset.widgetId === widgetId; });
        if (idx >= 0 && idx < all.length - 1) {
            var beforeRects = _captureRects();
            container.insertBefore(all[idx + 1], all[idx]);
            saveLayout();
            _flipAnimate(beforeRects, 200);
        }
    }

    // ========================================================================
    //  ROW LIMITS
    // ========================================================================
    function applyWidgetLimits() {
        items().forEach(function(item) {
            var id    = item.dataset.widgetId;
            if (!id) return;
            var lim   = (layout.limits && layout.limits[id] !== undefined) ? layout.limits[id] : null;
            var limit = (lim === 'all' || lim === null) ? Infinity : parseInt(lim);
            item.querySelectorAll('[data-row-index]').forEach(function(row) {
                row.style.display = parseInt(row.dataset.rowIndex) >= limit ? 'none' : '';
            });
            var sel = item.querySelector('.widget-limit-select');
            if (sel && lim !== null) sel.value = String(lim);
        });
    }

    // ========================================================================
    //  RESET
    // ========================================================================
    function reset() {
        localStorage.removeItem(config.storageKey);
        layout = loadLayout();
        items().forEach(function(item) {
            item.style.minHeight = '';
            _dashInnerCard(item).style.backgroundColor = '';
            item.style.backgroundColor = '';
        });
        applyLayout();
        applyWidgetLimits();
    }

    // ========================================================================
    //  INIT
    // ========================================================================
    if (items().length > 0) {
        applyLayout();  // restore saved layout instantly, no animation on page load
        applyWidgetLimits();
        syncControls();
        syncVisibility();
    }

    return { toggleEditMode: toggleEditMode, moveUp: moveUp, moveDown: moveDown, reset: reset };
}


// ── createCardResizeManager ───────────────────────────────────────────────────
// Used by: Statistics page (stats.html) for card-level resize, limits, colours.
//
// Config shape:
//   getLayout      – function() → layout object { sizes, heights, limits, colors }
//   saveLayout     – function() that persists the layout
//   isEditMode     – function() → boolean
//   cardSelector   – CSS selector for cards (default: '.stats-card')
//   resizeSnap     – vertical snap in px (default: 80)
//   limitAllText   – "All" label (translated)
// ─────────────────────────────────────────────────────────────────────────────
function createCardResizeManager(config) {
    var cardSelector = config.cardSelector || '.stats-card';
    var ROW_SNAP     = config.resizeSnap   || 80;
    var resizeState  = null;

    // ── Helpers ───────────────────────────────────────────────────────────────
    function getParentMaxCols(card) {
        var grid = card.parentElement;
        if (!grid) return 1;
        var m = (grid.className || '').match(/xl:grid-cols-(\d+)/);
        return m ? parseInt(m[1], 10) : 1;
    }

    function getCardColWidth(card) {
        var grid = card.parentElement;
        if (!grid) return 200;
        var maxCols = getParentMaxCols(card);
        var style   = getComputedStyle(grid);
        var gap     = parseFloat(style.columnGap) || parseFloat(style.gap) || 24;
        return (grid.getBoundingClientRect().width - (maxCols - 1) * gap) / maxCols;
    }

    function clearXlSpan(card) {
        card.className = card.className
            .replace(/\bxl:col-span-\d+\b/g, '')
            .replace(/\s{2,}/g, ' ')
            .trim();
    }

    function getDefaultSize(card) {
        if (!card) return 1;
        if (!card.dataset.defaultXlSpan) {
            var m = (card.className || '').match(/\bxl:col-span-(\d+)\b/);
            card.dataset.defaultXlSpan = m ? m[1] : '1';
        }
        return parseInt(card.dataset.defaultXlSpan, 10) || 1;
    }

    // ── Size ──────────────────────────────────────────────────────────────────
    function applySize(cardId, size) {
        var card = document.querySelector('[data-card-id="' + cardId + '"]');
        if (!card) return;
        clearXlSpan(card);
        var nextSize = parseInt(size || getDefaultSize(card), 10) || getDefaultSize(card);
        if (nextSize > 1) card.classList.add('xl:col-span-' + nextSize);
    }

    function setSize(cardId, size) {
        var layout      = config.getLayout();
        var card        = document.querySelector('[data-card-id="' + cardId + '"]');
        if (!card) return;
        var defaultSize = getDefaultSize(card);
        if (parseInt(size, 10) === defaultSize) {
            delete layout.sizes[cardId];
        } else {
            layout.sizes[cardId] = parseInt(size, 10);
        }
        applySize(cardId, layout.sizes[cardId] || defaultSize);
        config.saveLayout();
    }

    // ── Row limits ────────────────────────────────────────────────────────────
    function applyLimit(cardId, limit) {
        var card = document.querySelector('[data-card-id="' + cardId + '"]');
        if (!card) return;
        var lim = (limit === 'all') ? Infinity : parseInt(limit);
        card.querySelectorAll('[data-row-index]').forEach(function(row) {
            row.style.display = parseInt(row.dataset.rowIndex) >= lim ? 'none' : '';
        });
    }

    function setLimit(cardId, value) {
        var layout = config.getLayout();
        layout.limits[cardId] = (value === 'all') ? 'all' : parseInt(value);
        applyLimit(cardId, layout.limits[cardId]);
        config.saveLayout();
    }

    function applyLimits() {
        var layout = config.getLayout();
        Object.entries(layout.limits).forEach(function(entry) { applyLimit(entry[0], entry[1]); });
    }

    // ── Colours ───────────────────────────────────────────────────────────────
    function applyColors() {
        var layout = config.getLayout();
        document.querySelectorAll(cardSelector).forEach(function(card) {
            var id = card.dataset.cardId;
            card.style.backgroundColor = _dashGetBg((layout.colors && layout.colors[id]) || '');
        });
    }

    // ── Resize handles + colour pickers ──────────────────────────────────────
    function initHandles() {
        document.querySelectorAll(cardSelector).forEach(function(card) {
            var id = card.dataset.cardId;
            if (!id) return;

            // Resize handle (add once)
            if (!card.querySelector('.resize-handle')) {
                var handle = document.createElement('div');
                handle.className = 'resize-handle';
                handle.setAttribute('draggable', 'false');
                handle.title     = 'Resize';
                handle.innerHTML = _DASH_RESIZE_SVG;
                card.appendChild(handle);
                handle.addEventListener('mousedown', function(e) {
                    if (!config.isEditMode()) return;
                    e.preventDefault(); e.stopPropagation();
                    var layout    = config.getLayout();
                    var rect      = card.getBoundingClientRect();
                    var savedSize = layout.sizes[id] || getDefaultSize(card);
                    resizeState = {
                        card: card, id: id,
                        startX: e.clientX, startY: e.clientY,
                        startCols: parseInt(savedSize) || 1, startHeight: rect.height,
                        currentCols: parseInt(savedSize) || 1, currentHeight: rect.height
                    };
                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup',   onMouseUp);
                    document.body.classList.add('resize-dragging');
                });
            }

            // Colour picker in .card-edit-bar (add once)
            var bar = card.querySelector('.card-edit-bar');
            if (bar && !bar.querySelector('.widget-color-wrap')) {
                var mlAuto = bar.querySelector('.ml-auto');
                var cw = _dashMakeColorPickerBtn(
                    (config.getLayout().colors && config.getLayout().colors[id]) || '',
                    (function(cid) {
                        return function(colorId) {
                            var layout = config.getLayout();
                            if (!layout.colors) layout.colors = {};
                            layout.colors[cid] = colorId;
                            var el = document.querySelector('[data-card-id="' + cid + '"]');
                            if (el) el.style.backgroundColor = _dashGetBg(colorId);
                            config.saveLayout();
                            if (typeof updateRestorePanel === 'function') updateRestorePanel();
                        };
                    }(id))
                );
                if (mlAuto) mlAuto.insertBefore(cw, mlAuto.firstChild);
                else bar.appendChild(cw);
            }
        });
    }

    function onMouseMove(e) {
        if (!resizeState) return;
        var maxCols   = getParentMaxCols(resizeState.card);
        var colWidth  = getCardColWidth(resizeState.card);
        var newCols   = Math.max(1, Math.min(maxCols, Math.round(resizeState.startCols + (e.clientX - resizeState.startX) / colWidth)));
        var newHeight = Math.max(ROW_SNAP, Math.round((resizeState.startHeight + (e.clientY - resizeState.startY)) / ROW_SNAP) * ROW_SNAP);
        clearXlSpan(resizeState.card);
        if (newCols > 1) resizeState.card.classList.add('xl:col-span-' + newCols);
        resizeState.card.style.minHeight = newHeight + 'px';
        resizeState.currentCols   = newCols;
        resizeState.currentHeight = newHeight;
    }

    function onMouseUp() {
        if (!resizeState) return;
        if (resizeState.currentCols !== resizeState.startCols)   setSize(resizeState.id, resizeState.currentCols);
        if (resizeState.currentHeight !== resizeState.startHeight) {
            var layout = config.getLayout();
            if (!layout.heights) layout.heights = {};
            layout.heights[resizeState.id] = resizeState.currentHeight;
            var card = document.querySelector('[data-card-id="' + resizeState.id + '"]');
            if (card) card.style.minHeight = resizeState.currentHeight + 'px';
            config.saveLayout();
        }
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup',   onMouseUp);
        document.body.classList.remove('resize-dragging');
        resizeState = null;
    }

    // ── Bulk apply ────────────────────────────────────────────────────────────
    function applySizes() {
        var layout = config.getLayout();
        document.querySelectorAll(cardSelector).forEach(function(card) {
            var id   = card.dataset.cardId;
            var size = layout.sizes[id] || getDefaultSize(card);
            applySize(id, size);
        });
    }

    function applyHeights() {
        var layout = config.getLayout();
        if (!layout.heights) return;
        Object.entries(layout.heights).forEach(function(entry) {
            var el = document.querySelector('[data-card-id="' + entry[0] + '"]');
            if (el) el.style.minHeight = entry[1] + 'px';
        });
    }

    function applySizesAndLimits() {
        applySizes();
        applyHeights();
        applyLimits();
        applyColors();
    }

    return {
        initHandles:  initHandles,
        applySize:    applySize,
        setSize:      setSize,
        applyLimit:   applyLimit,
        setLimit:     setLimit,
        applyLimits:  applyLimits,
        applySizes:   applySizes,
        applyHeights: applyHeights,
        applyColors:  applyColors,
        applySizesAndLimits: applySizesAndLimits,
    };
}
