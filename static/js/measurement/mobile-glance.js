/**
 * 실측 모바일 한눈 목록: 줄 → 카드 이동·강조, 체크 칸 → "실측만 완료" 토글(measurement_visits).
 * 체크는 카드의 "실측 완료"(measurement_completed/도면 넘김)와 다른 개념이다.
 * 방문 시간은 전날 확정된 예정값이라 시간순 강조·재정렬·ETA 는 하지 않는다(서버 행 순서 그대로).
 *
 * 전역 가드 1회 + document 위임 click 리스너 1개 → 프래그먼트 스왑에도 재바인딩 불필요(G4).
 */
(function () {
    if (window.__FOMS_MEAS_GLANCE_BOUND) return;
    window.__FOMS_MEAS_GLANCE_BOUND = true;

    var FLASH_CLASS = 'is-glance-flash';
    var FLASH_MS = 1800;
    var MSG_MS = 4000;
    var FAIL_MSG = '체크를 저장하지 못했어요. 다시 눌러 주세요';

    var flashTimer = null;
    var flashCard = null;
    var msgTimers = typeof WeakMap === 'function' ? new WeakMap() : null;

    function goToCard(orderId) {
        if (!orderId) return;
        var card = document.getElementById('meas-card-' + orderId);
        if (!card) return;
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });

        if (flashTimer) {
            clearTimeout(flashTimer);
            flashTimer = null;
        }
        if (flashCard && flashCard !== card) flashCard.classList.remove(FLASH_CLASS);
        card.classList.remove(FLASH_CLASS);
        void card.offsetWidth;
        card.classList.add(FLASH_CLASS);
        flashCard = card;
        flashTimer = setTimeout(function () {
            card.classList.remove(FLASH_CLASS);
            flashTimer = null;
            flashCard = null;
        }, FLASH_MS);

        if (!card.hasAttribute('tabindex')) card.setAttribute('tabindex', '-1');
        try {
            card.focus({ preventScroll: true });
        } catch (e) {
            /* 오래된 브라우저: focus 옵션 미지원 → 스크롤만으로 충분 */
        }
    }

    function refreshCounts(panel) {
        if (!panel) return;
        panel.querySelectorAll('[data-meas-glance-grp]').forEach(function (grp) {
            var rows = grp.querySelectorAll('.foms-meas-glance__row');
            var n = rows.length;
            var d = grp.querySelectorAll('.foms-meas-glance__row.is-done').length;
            var prog = grp.querySelector('progress.foms-meas-glance__prog');
            if (prog) {
                prog.max = n;
                prog.value = d;
            }
            var grpCount = grp.querySelector('[data-meas-glance-grp-count]');
            if (grpCount) grpCount.textContent = '실측 ' + d + '/' + n;
        });

        var total = panel.querySelectorAll('.foms-meas-glance__row').length;
        var done = panel.querySelectorAll('.foms-meas-glance__row.is-done').length;
        var count = panel.querySelector('[data-meas-glance-count]');
        if (count) count.textContent = total + '곳 · 실측 ' + done + ' · 남은 ' + (total - done);
    }

    function applyState(btn, done) {
        btn.setAttribute('aria-pressed', done ? 'true' : 'false');
        var row = btn.closest('.foms-meas-glance__row');
        if (row) row.classList.toggle('is-done', !!done);
        refreshCounts(btn.closest('[data-meas-glance]'));
    }

    function showMsg(panel, text) {
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

    document.addEventListener('click', function (evt) {
        var target = evt.target;
        if (!target || typeof target.closest !== 'function') return;
        // 담당자 전화(tel:) 링크는 절대 가로채지 않는다.
        if (target.closest('a[href^="tel:"]')) return;

        var toggleBtn = target.closest('[data-meas-visit-toggle]');
        if (toggleBtn) {
            evt.preventDefault();
            toggleVisit(toggleBtn);
            return;
        }
        var goLink = target.closest('[data-meas-glance-go]');
        if (goLink) {
            evt.preventDefault();
            goToCard(goLink.getAttribute('data-meas-glance-go'));
        }
    });
})();
