/**
 * 실측 모바일 통합 목록 — 담당자 탭·좌우 밀기·묶음 접기·모두 펼치기·자리 찾기(reveal).
 * 스펙: docs/specs/2026-09-23-measurement-mobile-unified-list_SPEC.md §3
 *
 * - 탭: `전체` + 담당자. 담당자 탭이면 그 담당 묶음만 보이고 접기가 없다(is-solo). 선택은 ?mgr= 로 replaceState.
 * - 목록을 좌우로 밀면(가로 60px 초과 · 세로의 1.5배 초과) 옆 탭. 체크 칸·전화에서 시작한 밀기는 무시.
 * - 전체 탭의 펼침 상태는 localStorage(날짜별 1벌, try/catch) — 저장이 막혀도 서버가 그린 처음 상태로 동작.
 * - 실측 완료 뒤 새로 읽기: erp-quest-approve.js 가 `foms:quest-approve:before-restore` 를 쏘고 같은 값을
 *   window.__fomsQuestApproveRestore 에 남긴다. 실측 번들은 그 뒤에 실리므로 init 에서 받아 줄을 찾아 간다.
 * 전역 가드 1회 + document 위임 리스너 → 프래그먼트 스왑에도 재바인딩 불필요. 섹션별 init 만 다시 돈다.
 */
(function () {
    'use strict';
    if (window.__FOMS_MEAS_GLANCE_TABS_BOUND) return;
    window.__FOMS_MEAS_GLANCE_TABS_BOUND = true;

    var STORE_KEY = 'foms:meas-glance:open';
    var SWIPE_MIN = 60;
    var SWIPE_RATIO = 1.5;
    var FLASH_MS = 1800;
    var RESTORE_TTL_MS = 30 * 1000;

    function toArr(list) { return Array.prototype.slice.call(list || []); }
    function section() { return document.querySelector('[data-meas-glance]'); }
    function groupsOf(sec) { return toArr(sec.querySelectorAll('[data-meas-glance-grp]')); }
    function nameOf(grp) { return grp.getAttribute('data-meas-glance-grp') || ''; }
    function tabsOf(sec) { return toArr(sec.querySelectorAll('[data-meas-glance-tab]')); }
    function currentTab(sec) {
        var t = sec.querySelector('[data-meas-glance-tab][aria-selected="true"]');
        return t ? t.getAttribute('data-meas-glance-tab') : '';
    }

    function readOpen(sec) {
        try {
            var v = JSON.parse(window.localStorage.getItem(STORE_KEY) || 'null');
            if (!v || v.d !== sec.getAttribute('data-meas-glance-date') || !Array.isArray(v.open)) return null;
            return v.open;
        } catch (e) { return null; }
    }
    function openNames(sec) {
        var names = [];
        groupsOf(sec).forEach(function (g) {
            if (!g.classList.contains('is-closed') && names.indexOf(nameOf(g)) < 0) names.push(nameOf(g));
        });
        return names;
    }
    function saveOpen(sec) {
        try {
            window.localStorage.setItem(STORE_KEY, JSON.stringify({
                d: sec.getAttribute('data-meas-glance-date'), open: openNames(sec)
            }));
        } catch (e) { /* 저장 차단(사생활 모드 등): 이번 화면에서만 유지 */ }
    }

    function syncToggle(grp) {
        var tog = grp.querySelector('[data-meas-glance-tog]');
        if (!tog) return;
        var solo = grp.classList.contains('is-solo');
        tog.setAttribute('aria-expanded', (solo || !grp.classList.contains('is-closed')) ? 'true' : 'false');
        if (solo) tog.setAttribute('aria-disabled', 'true');
        else tog.removeAttribute('aria-disabled');
    }
    function setOpen(grp, open) {
        grp.classList.toggle('is-closed', !open);
        syncToggle(grp);
    }

    function syncCtl(sec) {
        var ctl = sec.querySelector('[data-meas-glance-ctl]');
        if (!ctl) return;
        var openCount = sec.querySelector('[data-meas-glance-open-count]');
        if (openCount) openCount.textContent = String(openNames(sec).length);
        var anyClosed = groupsOf(sec).some(function (g) { return g.classList.contains('is-closed'); });
        var all = ctl.querySelector('[data-meas-glance-all]');
        if (all) all.setAttribute('data-meas-glance-all', anyClosed ? 'open' : 'close');
        var label = ctl.querySelector('[data-meas-glance-all-label]');
        if (label) label.textContent = anyClosed ? '모두 펼치기' : '모두 접기';
    }

    function writeUrl(name) {
        try {
            var u = new URL(window.location.href);
            if (name) u.searchParams.set('mgr', name);
            else u.searchParams.delete('mgr');
            window.history.replaceState(window.history.state, '', u.pathname + u.search + u.hash);
            // 셸이 기억하는 '지금 그린 화면' 주소도 같이 옮긴다(겹층 기록 건너뛰기 판정, erp-shell.js).
            var shell = window.FOMS_ERP_SHELL;
            if (shell && typeof shell.syncRenderedUrl === 'function') shell.syncRenderedUrl();
        } catch (e) { /* 주소 갱신 실패는 화면 동작과 무관 */ }
    }

    function revealTabInStrip(strip, tab) {
        var prev = tab.previousElementSibling;
        strip.scrollLeft = Math.max(0, tab.offsetLeft - 16 - (prev ? 56 : 0));
    }

    /** 탭이 머리 밑에 붙은 상태에서 탭을 바꾸면 목록 맨 위(탭 바로 밑)로 올린다. */
    function scrollListTop(sec) {
        var strip = sec.querySelector('[data-meas-glance-tabs]');
        var panel = sec.querySelector('[data-meas-glance-list]');
        if (!strip || !panel) return;
        var want = strip.getBoundingClientRect().top + strip.offsetHeight;
        var top = panel.getBoundingClientRect().top;
        if (top < want - 1) window.scrollTo(0, (window.scrollY || window.pageYOffset || 0) + top - want);
    }

    function selectTab(sec, name, opts) {
        opts = opts || {};
        var tabs = tabsOf(sec);
        var target = tabs.filter(function (t) { return t.getAttribute('data-meas-glance-tab') === name; })[0];
        if (!target) return false;
        tabs.forEach(function (t) {
            var on = t === target;
            t.setAttribute('aria-selected', on ? 'true' : 'false');
            t.setAttribute('tabindex', on ? '0' : '-1');
        });
        var panel = sec.querySelector('[data-meas-glance-list]');
        if (panel && target.id) panel.setAttribute('aria-labelledby', target.id);
        groupsOf(sec).forEach(function (g) {
            g.hidden = !!name && nameOf(g) !== name;
            g.classList.toggle('is-solo', !!name);
            syncToggle(g);
        });
        var ctl = sec.querySelector('[data-meas-glance-ctl]');
        if (ctl) ctl.hidden = !!name;
        var strip = sec.querySelector('[data-meas-glance-tabs]');
        if (strip) revealTabInStrip(strip, target);
        if (!opts.noUrl) writeUrl(name);
        if (!opts.noScroll) scrollListTop(sec);
        if (panel && opts.dir) {
            panel.classList.remove('is-slide-l', 'is-slide-r');
            void panel.offsetWidth;
            panel.classList.add(opts.dir > 0 ? 'is-slide-l' : 'is-slide-r');
        }
        return true;
    }

    function goTab(sec, dir) {
        var tabs = tabsOf(sec);
        var cur = currentTab(sec);
        var idx = tabs.map(function (t) { return t.getAttribute('data-meas-glance-tab'); }).indexOf(cur);
        var next = tabs[idx + dir];
        if (!next) return false;
        return selectTab(sec, next.getAttribute('data-meas-glance-tab'), { dir: dir });
    }

    function flash(row) {
        row.classList.remove('is-glance-flash');
        void row.offsetWidth;
        row.classList.add('is-glance-flash');
        window.setTimeout(function () { row.classList.remove('is-glance-flash'); }, FLASH_MS);
    }

    /** 그 주문 줄이 보이게: 다른 담당 탭이면 그 담당 탭으로, 접힌 묶음이면 펼친다. 스크롤·강조는 opts. */
    function reveal(orderId, opts) {
        opts = opts || {};
        var sec = section();
        if (!sec || !orderId) return null;
        var row = sec.querySelector('[data-meas-glance-row="' + String(orderId).replace(/"/g, '') + '"]');
        if (!row) return null;
        var grp = row.closest('[data-meas-glance-grp]');
        if (grp && grp.hidden) selectTab(sec, nameOf(grp), { noScroll: true });
        if (grp && grp.classList.contains('is-closed') && !grp.classList.contains('is-solo')) {
            setOpen(grp, true);
            syncCtl(sec);
            saveOpen(sec);
        }
        if (opts.scroll !== false) row.scrollIntoView({ block: 'center' });
        if (opts.flash) flash(row);
        return row;
    }

    function takeQuestRestore() {
        var saved = window.__fomsQuestApproveRestore;
        window.__fomsQuestApproveRestore = null;
        if (!saved || !saved.orderId || Date.now() - (saved.at || 0) > RESTORE_TTL_MS) return null;
        // 다른 화면에서 남긴 값을 셸 이동 뒤 실측이 쓰지 않게 — 같은 주소일 때만.
        if (saved.path !== window.location.pathname + window.location.search) return null;
        return saved;
    }

    function init() {
        var sec = section();
        if (!sec || sec.__fomsMeasTabsInit) return;
        sec.__fomsMeasTabsInit = true;
        var strip = sec.querySelector('[data-meas-glance-tabs]');
        if (strip) {
            var stored = readOpen(sec);
            if (stored) groupsOf(sec).forEach(function (g) { setOpen(g, stored.indexOf(nameOf(g)) >= 0); });
            var mgr = '';
            try { mgr = new URLSearchParams(window.location.search).get('mgr') || ''; } catch (e) { mgr = ''; }
            if (!selectTab(sec, mgr, { noScroll: true, noUrl: true })) selectTab(sec, '', { noScroll: true });
            syncCtl(sec);
        }
        var restore = takeQuestRestore();
        if (restore && reveal(restore.orderId, { flash: true })) {
            window.FomsMeasGlance.restoredOrderId = String(restore.orderId);
        }
    }

    document.addEventListener('click', function (e) {
        var t = e.target;
        if (!t || typeof t.closest !== 'function') return;
        var sec = t.closest('[data-meas-glance]');
        if (!sec) return;
        var tab = t.closest('[data-meas-glance-tab]');
        if (tab) {
            selectTab(sec, tab.getAttribute('data-meas-glance-tab'));
            return;
        }
        var tog = t.closest('[data-meas-glance-tog]');
        if (tog) {
            var grp = tog.closest('[data-meas-glance-grp]');
            if (!grp || grp.classList.contains('is-solo')) return;
            setOpen(grp, grp.classList.contains('is-closed'));
            syncCtl(sec);
            saveOpen(sec);
            return;
        }
        var all = t.closest('[data-meas-glance-all]');
        if (all) {
            var open = all.getAttribute('data-meas-glance-all') === 'open';
            groupsOf(sec).forEach(function (g) { setOpen(g, open); });
            syncCtl(sec);
            saveOpen(sec);
        }
    });

    document.addEventListener('keydown', function (e) {
        var tab = e.target && e.target.closest && e.target.closest('[data-meas-glance-tab]');
        if (!tab) return;
        var sec = tab.closest('[data-meas-glance]');
        var tabs = tabsOf(sec);
        var i = tabs.indexOf(tab);
        var j = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key];
        if (j === undefined) return;
        e.preventDefault();
        selectTab(sec, tabs[j].getAttribute('data-meas-glance-tab'));
        tabs[j].focus();
    });

    // ── 목록 좌우 밀기 → 옆 탭 ──
    var drag = null;
    var suppressUntil = 0;
    document.addEventListener('pointerdown', function (e) {
        drag = null;
        suppressUntil = 0; // 새 누름은 앞 밀기의 클릭 막기를 물려받지 않는다
        if (e.isPrimary === false || !e.target || !e.target.closest) return;
        var list = e.target.closest('[data-meas-glance-list]');
        var sec = list && list.closest('[data-meas-glance]');
        if (!sec || !sec.querySelector('[data-meas-glance-tabs]')) return;
        if (e.target.closest('[data-meas-visit-toggle], .foms-meas-glance__call, a[href^="tel:"], input, select, textarea')) return;
        drag = { x: e.clientX, y: e.clientY, sec: sec };
    });
    document.addEventListener('pointercancel', function () { drag = null; });
    document.addEventListener('pointerup', function (e) {
        var d = drag;
        drag = null;
        if (!d) return;
        var dx = e.clientX - d.x;
        var dy = e.clientY - d.y;
        if (Math.abs(dx) > SWIPE_MIN && Math.abs(dx) > Math.abs(dy) * SWIPE_RATIO) {
            suppressUntil = Date.now() + 400;
            goTab(d.sec, dx < 0 ? 1 : -1);
        }
    });
    // 밀기 끝에 따라오는 click 은 줄 열기로 치지 않는다.
    document.addEventListener('click', function (e) {
        if (!suppressUntil || Date.now() > suppressUntil) return;
        suppressUntil = 0;
        if (e.target && e.target.closest && e.target.closest('[data-meas-glance-list]')) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);

    // 이 번들이 먼저 실린 경우(드묾): 복원 직전 이벤트로 바로 처리하고 공용 스크롤은 막는다.
    document.addEventListener('foms:quest-approve:before-restore', function (e) {
        var id = e.detail && e.detail.orderId;
        if (id && reveal(id, { flash: true })) {
            window.__fomsQuestApproveRestore = null;
            window.FomsMeasGlance.restoredOrderId = String(id);
            e.preventDefault();
        }
    });

    window.FomsMeasGlance = window.FomsMeasGlance || {};
    window.FomsMeasGlance.reveal = reveal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    document.addEventListener('foms:erp-shell-fragment-swapped', init);
})();
