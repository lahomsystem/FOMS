/**
 * 실측 모바일 통합 목록: 체크 칸 → "실측만 완료" 토글(measurement_visits) + 숫자 갱신.
 * 체크는 카드의 "실측 완료"(measurement_completed/도면 넘김)와 다른 개념이다.
 * 방문 시간은 전날 확정된 예정값이라 시간순 강조·재정렬·ETA 는 하지 않는다(서버 행 순서 그대로).
 *
 * 탭·접기·밀기는 mobile-glance-tabs.js, 줄 → 바텀시트는 mobile-glance-sheet.js 가 맡는다.
 * 체크 상태가 바뀔 때마다 `foms:meas-glance:visit` 이벤트({orderId, done})를 쏜다 — 시트의
 * "실측 체크" 토글이 이 이벤트로 같은 상태를 따라간다.
 *
 * 전역 가드 1회 + document 위임 click 리스너 1개 → 프래그먼트 스왑에도 재바인딩 불필요(G4).
 */
(function () {
    if (window.__FOMS_MEAS_GLANCE_BOUND) return;
    window.__FOMS_MEAS_GLANCE_BOUND = true;

    var MSG_MS = 4000;
    var FAIL_MSG = '체크를 저장하지 못했어요. 다시 눌러 주세요';
    var ROW = '.foms-meas-glance__row';
    var ROW_DONE = '.foms-meas-glance__row.is-done';

    var msgTimers = typeof WeakMap === 'function' ? new WeakMap() : null;

    function setProgress(prog, done, total) {
        if (!prog) return;
        prog.max = total;
        prog.value = done;
    }

    /** 담당 이름이 같은 묶음 전부(한 담당이 두 묶음으로 갈릴 수 있다). */
    function groupsNamed(panel, name) {
        return Array.prototype.filter.call(panel.querySelectorAll('[data-meas-glance-grp]'), function (g) {
            return g.getAttribute('data-meas-glance-grp') === name;
        });
    }

    function countIn(nodes) {
        var n = 0;
        var d = 0;
        nodes.forEach(function (node) {
            n += node.querySelectorAll(ROW).length;
            d += node.querySelectorAll(ROW_DONE).length;
        });
        return { n: n, d: d };
    }

    function refreshCounts(panel) {
        if (!panel) return;
        panel.querySelectorAll('[data-meas-glance-grp]').forEach(function (grp) {
            var c = countIn([grp]);
            setProgress(grp.querySelector('progress.foms-meas-glance__prog'), c.d, c.n);
            var grpCount = grp.querySelector('[data-meas-glance-grp-count]');
            if (grpCount) {
                grpCount.textContent = '실측 ' + c.d + '/' + c.n;
                grpCount.classList.toggle('is-full', c.n > 0 && c.d === c.n);
            }
        });

        panel.querySelectorAll('[data-meas-glance-tab]').forEach(function (tab) {
            var name = tab.getAttribute('data-meas-glance-tab');
            var c = name ? countIn(groupsNamed(panel, name)) : countIn([panel]);
            var tabCount = tab.querySelector('[data-meas-glance-tab-count]');
            if (tabCount) tabCount.textContent = c.d + '/' + c.n;
            setProgress(tab.querySelector('progress'), c.d, c.n);
            tab.classList.toggle('is-full', c.n > 0 && c.d === c.n);
        });

        var total = panel.querySelectorAll(ROW).length;
        var done = panel.querySelectorAll(ROW_DONE).length;
        var handed = panel.querySelectorAll(ROW + '[data-meas-glance-handed]').length;
        var count = panel.querySelector('[data-meas-glance-count]');
        if (count) count.textContent = total + '곳 · 실측 ' + done + ' · 넘김 ' + handed;
    }

    function applyState(btn, done) {
        btn.setAttribute('aria-pressed', done ? 'true' : 'false');
        var row = btn.closest(ROW);
        if (row) row.classList.toggle('is-done', !!done);
        refreshCounts(btn.closest('[data-meas-glance]'));
        document.dispatchEvent(new CustomEvent('foms:meas-glance:visit', {
            detail: { orderId: btn.getAttribute('data-meas-visit-toggle'), done: !!done }
        }));
    }

    function showMsg(panel, text) {
        // 바텀시트가 열려 있으면 목록 안내는 시트 뒤에 가린다 — 전역 토스트로 보인다.
        if (document.documentElement.classList.contains('foms-meas-sheet-open') &&
            typeof window.fomsFlashToast === 'function') {
            window.fomsFlashToast(text);
            return;
        }
        if (!panel) return;
        var msg = panel.querySelector('[data-meas-glance-msg]');
        if (!msg) return;
        msg.textContent = text;
        msg.hidden = false;
        if (msgTimers) {
            var prevTimer = msgTimers.get(msg);
            if (prevTimer) clearTimeout(prevTimer);
        }
        var timer = setTimeout(function () {
            msg.hidden = true;
            if (msgTimers) msgTimers.delete(msg);
        }, MSG_MS);
        if (msgTimers) msgTimers.set(msg, timer);
    }

    function invalidateShellCache() {
        var shell = window.FOMS_ERP_SHELL;
        if (shell && typeof shell.invalidatePrimaryNavFragmentCache === 'function') {
            shell.invalidatePrimaryNavFragmentCache();
        }
    }

    async function toggleVisit(btn) {
        if (btn.disabled || btn.getAttribute('aria-busy') === 'true') return;
        var orderId = btn.getAttribute('data-meas-visit-toggle');
        var date = btn.getAttribute('data-meas-visit-date');
        if (!orderId || !date) return;

        var prev = btn.getAttribute('aria-pressed') === 'true';
        var next = !prev;
        var panel = btn.closest('[data-meas-glance]');

        applyState(btn, next);
        btn.setAttribute('aria-busy', 'true');
        try {
            // CSRF 헤더는 csrf_bootstrap 전역 fetch 래퍼가 same-origin POST 에 붙인다.
            const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/measurement-visit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: date, done: next })
            });
            let data = null;
            try {
                data = await res.json();
            } catch (e) {
                data = null;
            }
            if (!res.ok || !data || data.success !== true) {
                throw new Error((data && (data.error || data.message)) || ('HTTP ' + res.status));
            }
            applyState(btn, !!(data.data && data.data.done));
            invalidateShellCache();
        } catch (err) {
            console.warn('[mobile-glance] 실측 체크 저장 실패:', err);
            applyState(btn, prev);
            showMsg(panel, FAIL_MSG);
        } finally {
            btn.removeAttribute('aria-busy');
        }
    }

    window.FomsMeasGlance = window.FomsMeasGlance || {};
    window.FomsMeasGlance.refreshCounts = refreshCounts;

    document.addEventListener('click', function (evt) {
        var target = evt.target;
        if (!target || typeof target.closest !== 'function') return;
        // 담당자 전화(tel:) 링크는 절대 가로채지 않는다.
        if (target.closest('a[href^="tel:"]')) return;

        var toggleBtn = target.closest('[data-meas-visit-toggle]');
        if (toggleBtn) {
            evt.preventDefault();
            toggleVisit(toggleBtn);
        }
    });
})();
