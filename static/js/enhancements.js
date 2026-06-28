// ── Filament Manager — UI Enhancements (v1.119.0) ───────────────────────────
// Theme reactivity, micro-interactions, KPI counters, mobile row actions,
// responsive table-to-card transformation, and Chart.js theming helper.
//
// All functions are exposed on `window.enh` to avoid pollution but keep
// easily accessible from inline handlers.
// ─────────────────────────────────────────────────────────────────────────────

(function () {
    'use strict';

    // ── Theme reactivity ─────────────────────────────────────────────────
    // Chart.js instances register via window.enh.registerChart(instance).
    // When the theme toggles, every registered chart is re-themed and
    // re-rendered with smooth transition. Avoids the previous behaviour
    // of charts keeping light-mode colours after dark-mode toggle.
    const _chartRegistry = new Set();
    const _COLOR_TOKENS = {
        light: {
            grid: 'rgba(148, 163, 184, 0.18)',
            text: '#475569',
            axis: 'rgba(100, 116, 139, 0.6)',
            tooltipBg: 'rgba(255, 255, 255, 0.98)',
            tooltipText: '#0f172a',
        },
        dark: {
            grid: 'rgba(148, 163, 184, 0.12)',
            text: '#cbd5e1',
            axis: 'rgba(148, 163, 184, 0.45)',
            tooltipBg: 'rgba(17, 24, 39, 0.97)',
            tooltipText: '#f3f4f6',
        },
    };

    function _isDark() {
        return document.documentElement.classList.contains('dark');
    }

    function _palette() {
        return _isDark() ? _COLOR_TOKENS.dark : _COLOR_TOKENS.light;
    }

    function registerChart(chart) {
        _chartRegistry.add(chart);
        return chart;
    }

    function unregisterChart(chart) {
        _chartRegistry.delete(chart);
    }

    function rethemeAllCharts() {
        const pal = _palette();
        _chartRegistry.forEach(function (chart) {
            try {
                const opts = chart.options || {};
                if (opts.scales) {
                    Object.keys(opts.scales).forEach(function (key) {
                        const s = opts.scales[key];
                        if (!s) return;
                        if (s.grid) s.grid.color = pal.grid;
                        if (s.ticks) s.ticks.color = pal.text;
                        if (s.title && s.title.color !== undefined) s.title.color = pal.text;
                    });
                }
                if (opts.plugins && opts.plugins.legend && opts.plugins.legend.labels) {
                    opts.plugins.legend.labels.color = pal.text;
                }
                if (opts.plugins && opts.plugins.tooltip) {
                    opts.plugins.tooltip.backgroundColor = pal.tooltipBg;
                    opts.plugins.tooltip.titleColor = pal.tooltipText;
                    opts.plugins.tooltip.bodyColor = pal.tooltipText;
                    opts.plugins.tooltip.borderColor = pal.grid;
                    opts.plugins.tooltip.borderWidth = 1;
                }
                chart.update('none');
            } catch (e) { /* chart may have been destroyed */ }
        });
    }

    // ── KPI animated counter ─────────────────────────────────────────────
    // Renders the target number by tweening from 0 (or the previous value)
    // over `duration` ms. Triggers a quick roll-in animation on every change.
    function animateCounter(el, target, opts) {
        opts = opts || {};
        const duration = opts.duration || 900;
        const decimals = opts.decimals != null ? opts.decimals : (String(target).split('.')[1] || '').length;
        const start = parseFloat(el.dataset.value || '0') || 0;
        const delta = target - start;
        const startTs = performance.now();
        if (el._enhCounterRaf) cancelAnimationFrame(el._enhCounterRaf);
        function step(now) {
            const t = Math.min(1, (now - startTs) / duration);
            // ease-out-cubic
            const eased = 1 - Math.pow(1 - t, 3);
            const current = start + delta * eased;
            el.textContent = (decimals > 0 ? current.toFixed(decimals) : Math.round(current).toLocaleString()) + (opts.suffix || '');
            if (t < 1) {
                el._enhCounterRaf = requestAnimationFrame(step);
            } else {
                el.dataset.value = String(target);
                el._enhCounterRaf = null;
            }
        }
        el._enhCounterRaf = requestAnimationFrame(step);
        el.classList.add('enh-kpi-value', 'is-flipping');
        setTimeout(function () { el.classList.remove('is-flipping'); }, 360);
    }

    // ── Auto-counter init: any element with data-enh-counter="N" ─────────
    function initKpiCounters() {
        document.querySelectorAll('[data-enh-counter]').forEach(function (el) {
            const target = parseFloat(el.dataset.enhCounter);
            if (!isFinite(target)) return;
            animateCounter(el, target, { suffix: el.dataset.enhSuffix || '' });
        });
    }

    // ── Ripple on primary buttons (data-enh-ripple) ──────────────────────
    function initRipple() {
        document.addEventListener('pointerdown', function (e) {
            const btn = e.target.closest && e.target.closest('[data-enh-ripple]');
            if (!btn) return;
            const rect = btn.getBoundingClientRect();
            btn.style.setProperty('--ripple-x', (e.clientX - rect.left) + 'px');
            btn.style.setProperty('--ripple-y', (e.clientY - rect.top) + 'px');
            btn.classList.remove('is-rippling');
            // Force reflow so the animation restarts on rapid clicks.
            void btn.offsetWidth;
            btn.classList.add('is-rippling');
            setTimeout(function () { btn.classList.remove('is-rippling'); }, 650);
        });
    }

    // ── Mobile row actions (long-press / tap on right edge) ──────────────
    function initMobileRowActions() {
        if (window.matchMedia('(min-width: 768px)').matches) return;
        let timer = null;
        let active = null;
        function reset() {
            if (active) active.classList.remove('is-revealed');
            active = null;
        }
        document.addEventListener('contextmenu', function (e) {
            const row = e.target.closest && e.target.closest('.enh-mobile-actions');
            if (row) e.preventDefault();
        });
        document.addEventListener('pointerdown', function (e) {
            const row = e.target.closest && e.target.closest('.enh-mobile-actions');
            if (!row) return;
            if (e.target.closest('button, a, input, [role="button"]')) return;
            clearTimeout(timer);
            timer = setTimeout(function () {
                if (active && active !== row) active.classList.remove('is-revealed');
                active = row;
                row.classList.add('is-revealed');
            }, 280);
        });
        ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) {
            document.addEventListener(ev, function (e) {
                const row = e.target.closest && e.target.closest('.enh-mobile-actions');
                if (!row) return;
                clearTimeout(timer);
            });
        });
        // Tap outside to close
        document.addEventListener('click', function (e) {
            if (!active) return;
            if (!e.target.closest || !e.target.closest('.enh-mobile-actions')) reset();
        });
    }

    // ── Theme change → chart re-theme (debounced) ────────────────────────
    let _themeRaf = null;
    function watchTheme() {
        const obs = new MutationObserver(function () {
            if (_themeRaf) cancelAnimationFrame(_themeRaf);
            _themeRaf = requestAnimationFrame(rethemeAllCharts);
        });
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    }

    // ── Sparkline renderer (pure SVG, no deps) ──────────────────────────
    // data-enh-sparkline="12,18,9,22,17,30,24" — renders inside the element.
    function initSparklines() {
        document.querySelectorAll('[data-enh-sparkline]').forEach(function (el) {
            const raw = (el.dataset.enhSparkline || '').split(',').map(parseFloat).filter(function (n) { return isFinite(n); });
            if (raw.length < 2) return;
            const w = el.clientWidth || 200;
            const h = parseFloat(el.dataset.enhSparkHeight) || 38;
            const max = Math.max.apply(null, raw);
            const min = Math.min.apply(null, raw);
            const range = max - min || 1;
            const step = w / (raw.length - 1);
            const pts = raw.map(function (v, i) { return [i * step, h - 4 - ((v - min) / range) * (h - 8)]; });
            const linePath = pts.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ');
            const areaPath = linePath + ' L' + w.toFixed(1) + ',' + h + ' L0,' + h + ' Z';
            const last = pts[pts.length - 1];
            el.innerHTML = '' +
                '<svg class="enh-sparkline" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
                '<path class="spark-baseline" d="M0,' + (h - 4 - ((raw[0] - min) / range) * (h - 8)).toFixed(1) + ' L' + w + ',' + (h - 4 - ((raw[0] - min) / range) * (h - 8)).toFixed(1) + '" />' +
                '<path class="spark-area" d="' + areaPath + '" />' +
                '<path class="spark-line" d="' + linePath + '" />' +
                '<circle class="spark-dot" cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="3" />' +
                '</svg>';
        });
    }

    // ── Heatmap renderer ─────────────────────────────────────────────────
    // Element has data-enh-heatmap with JSON: { matrix: [[7x24]], labels: ['Po'..] }.
    function initHeatmaps() {
        document.querySelectorAll('[data-enh-heatmap]').forEach(function (el) {
            let payload;
            try { payload = JSON.parse(el.dataset.enhHeatmap); } catch (e) { return; }
            if (!payload || !Array.isArray(payload.matrix)) return;
            const days = payload.days || ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne'];
            const labels = payload.labels || days;
            const matrix = payload.matrix;
            const flatMax = Math.max.apply(null, [].concat.apply([], matrix)) || 1;
            const flatSum = matrix.reduce(function (s, row) { return s + row.reduce(function (a, b) { return a + b; }, 0); }, 0);
            let html = '<div class="enh-heatmap">';
            // header row (hour labels every 3 hours)
            html += '<div></div>';
            for (let h = 0; h < 24; h++) {
                html += '<div class="enh-heatmap-hour">' + (h % 3 === 0 ? h : '') + '</div>';
            }
            // body rows
            for (let d = 0; d < matrix.length; d++) {
                html += '<div class="enh-heatmap-label">' + (labels[d] ? labels[d].replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : '') + '</div>';
                for (let h = 0; h < 24; h++) {
                    const v = matrix[d][h] || 0;
                    const pct = v / flatMax;
                    let bg = 'var(--enh-heatmap-empty)';
                    if (pct > 0.66) bg = 'var(--enh-heatmap-high)';
                    else if (pct > 0.33) bg = 'var(--enh-heatmap-mid)';
                    else if (pct > 0) bg = 'var(--enh-heatmap-low)';
                    const tip = (labels[d] || '') + ' ' + h + ':00 — ' + v.toFixed(0) + ' g';
                    html += '<div class="enh-heatmap-cell" style="background:' + bg + '" data-tooltip="' + tip.replace(/"/g, '&quot;') + '"></div>';
                }
            }
            html += '</div>';
            var _ll = _resolveLocalLabels();
            html += '<div class="enh-heatmap-legend"><span>' + _ll.less + '</span><div class="enh-heatmap-legend-bar"></div><span>' + _ll.more + '</span></div>';
            el.innerHTML = html;
        });
    }

    // ── i18n labels (resolved from window.__i18n) ────────────────────────
    const _localLabels = {
        cs: { less: 'méně', more: 'více' },
        en: { less: 'less', more: 'more' },
    };
    function _resolveLocalLabels() {
        const lang = (window.__helpLang || document.documentElement.lang || 'en').substring(0, 2);
        return _localLabels[lang] || _localLabels.en;
    }

    function init() {
        initKpiCounters();
        initRipple();
        initMobileRowActions();
        initSparklines();
        initHeatmaps();
        watchTheme();
    }

    // Public API
    window.enh = {
        registerChart: registerChart,
        unregisterChart: unregisterChart,
        rethemeAllCharts: rethemeAllCharts,
        animateCounter: animateCounter,
        isDark: _isDark,
        palette: _palette,
        initSparklines: initSparklines,
        initHeatmaps: initHeatmaps,
        initKpiCounters: initKpiCounters,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
