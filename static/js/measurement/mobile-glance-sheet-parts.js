/**
 * 실측 모바일 바텀시트 부품 — 시트로 옮긴 카드의 배치 손질, 뒤 화면 inert, 방문 기록(history) 도우미.
 * mobile-glance-sheet.js 가 부른다(이 파일은 그보다 먼저 실린다).
 *
 * - "실측 체크" 토글: 카드 제목 바로 밑(목업 순서).
 * - 실측 사진: ERP 에 등록된 미리보기 이미지가 있을 때만 주소·연락처(meta) 아래로 옮기고 제목
 *   "실측 사진 · 사진 n" 을 단다. 이미지가 없으면 칸 자체를 숨긴다(사진 추가 없음).
 * - 넘긴 주문의 "실측 완료" 표시: 단추 줄 자리(카드 footer)로.
 * - 압축 시트 표식(data-meas-sheet-row·badge·foot): CSS 가 :has() 없이 고르게 — tagRows.
 * - 뒤 화면 inert: 시트에서 body 까지 올라가며 형제를 inert 로 — 사진 미리보기·오프캔버스·모달은 제외.
 * - 기록: 시트 기록과 그 앞 기록에 fomsShellKeep 표식(erp-shell.js 가 같은 화면일 때만 건너뜀).
 * 카드는 닫을 때 숨은 원본 칸으로 돌아가므로 카드 안 순서를 되돌릴 필요는 없다(다음 열 때 같은 결과).
 */
(function () {
    'use strict';
    if (window.FomsMeasSheetParts) return;

    var KEEP = '#global-image-viewer, .offcanvas, .modal, .toast-container';
    var inerted = [];

    function photoHeader(att) {
        var prev = att.previousElementSibling;
        if (prev && prev.hasAttribute('data-meas-sheet-ph-h')) return prev;
        var head = document.createElement('div');
        head.className = 'foms-meas-sheet__ph-h';
        head.setAttribute('data-meas-sheet-ph-h', '');
        var title = document.createElement('h4');
        title.className = 'foms-meas-sheet__ph-title';
        title.textContent = '실측 사진';
        var count = document.createElement('span');
        count.className = 'foms-meas-sheet__ph-count';
        head.appendChild(title);
        head.appendChild(count);
        att.parentNode.insertBefore(head, att);
        return head;
    }

    function placePhotos(card) {
        var meta = card.querySelector('.queue-card__meta');
        card.querySelectorAll('.queue-card__attachments').forEach(function (att) {
            var has = !!att.querySelector('img');
            att.hidden = !has;
            var prevHead = att.previousElementSibling;
            if (!has) {
                if (prevHead && prevHead.hasAttribute('data-meas-sheet-ph-h')) prevHead.hidden = true;
                return;
            }
            // 같은 카드가 시트에 다시 들어올 때마다(이전·다음) 불린다 — 제목은 하나만 두고 사진 칸과 함께 옮긴다.
            // 예전에는 사진 칸만 옮기고 제목을 남겨 두어, 넘길 때마다 "실측 사진 · 사진 n" 제목이 한 줄씩 늘었다.
            var head = photoHeader(att);
            card.querySelectorAll('[data-meas-sheet-ph-h]').forEach(function (h) {
                var nx = h.nextElementSibling;
                if (h !== head && !(nx && nx.classList.contains('queue-card__attachments'))) h.parentNode.removeChild(h);
            });
            if (meta && meta.parentNode) {
                if (meta.nextElementSibling !== head) meta.parentNode.insertBefore(head, meta.nextSibling);
                if (head.nextElementSibling !== att) meta.parentNode.insertBefore(att, head.nextSibling);
            }
            head.hidden = false;
            var n = att.querySelectorAll('[data-foms-erp-attachment-view-url]').length;
            head.querySelector('.foms-meas-sheet__ph-count').textContent = '사진 ' + n;
        });
    }

    function placeHanded(card) {
        var done = card.querySelector('.foms-measure-done');
        var foot = card.querySelector('.queue-card__action');
        if (done && foot && done.parentNode !== foot) foot.appendChild(done);
    }

    /** 같은 값이면 그대로, 없어야 하면 지운다 — 몇 번 불려도 결과가 같다(노드는 옮기지 않는다). */
    function mark(el, name, value) {
        if (!el) return;
        if (value) {
            if (el.getAttribute(name) !== value) el.setAttribute(name, value);
        } else if (el.hasAttribute(name)) {
            el.removeAttribute(name);
        }
    }

    /**
     * 압축 시트 CSS 가 고를 표식(:has() 없이 — iOS 15.4 미만). 줄: 주소·연락처(한 줄 전체 링크),
     * 실측 날짜·담당(시트에서 숨김). 머리의 파란 "실측" 단계 뱃지(--measure 만 숨김 — 다른 단계는 보인다). 넘긴 주문의 단추 줄(줄바꿈 허용).
     * 원본 칸으로 돌아가도 표식은 남지만 그 칸은 숨어 있어 아무 영향이 없다.
     */
    function tagRows(card) {
        var meta = card.querySelector('.queue-card__meta');
        if (meta) {
            Array.prototype.forEach.call(meta.children, function (row) {
                var kind = null;
                if (row.querySelector(':scope > dd[data-queue-card-field="address"] > a[data-queue-card-map-link]')) kind = 'addr';
                else if (row.querySelector(':scope > dd[data-queue-card-field="phone"] > a[data-queue-card-call-link]')) kind = 'phone';
                else if (row.querySelector(':scope > dd.foms-tabular')) kind = 'date';
                else if (row.querySelector(':scope > dd[data-queue-card-field="manager"]')) kind = 'mgr';
                mark(row, 'data-meas-sheet-row', kind);
            });
        }
        var badge = card.querySelector('.foms-queue-card-v2__head > .foms-stage-badge');
        mark(badge, 'data-meas-sheet-badge', badge && badge.classList.contains('foms-stage-badge--measure') ? 'stage' : null);
        var foot = card.querySelector('.queue-card__action');
        mark(foot, 'data-meas-sheet-foot', foot && foot.querySelector(':scope > .foms-measure-done') ? 'handed' : null);
    }

    function decorate(card, sheet) {
        var vc = sheet.querySelector('[data-meas-sheet-check]');
        var title = card.querySelector('.queue-card__title');
        if (vc && title && title.parentNode && title.nextSibling !== vc) title.parentNode.insertBefore(vc, title.nextSibling);
        placePhotos(card);
        placeHanded(card);
        tagRows(card);
    }

    /** 지킬 층(KEEP)이 아니면 inert. 지킬 층을 품은 상자는 그 안으로 내려가 나머지만 inert. */
    function inertOutside(el) {
        if (el.hasAttribute('inert') || /^(SCRIPT|STYLE|LINK|TEMPLATE|META)$/.test(el.tagName)) return;
        if (el.matches(KEEP)) return;
        if (el.querySelector(KEEP)) {
            Array.prototype.forEach.call(el.children, inertOutside);
            return;
        }
        el.setAttribute('inert', '');
        inerted.push(el);
    }

    function setInert(sheet, on) {
        inerted.forEach(function (el) { el.removeAttribute('inert'); });
        inerted = [];
        if (!on || !sheet) return;
        var node = sheet;
        while (node && node !== document.body && node.parentElement) {
            var parent = node.parentElement;
            Array.prototype.forEach.call(parent.children, function (sib) {
                if (sib !== node) inertOutside(sib);
            });
            node = parent;
        }
    }

    /** 지금 기록 상태에서 시트 표식을 빼고(id 없음) 또는 넣은(id 있음) 사본. */
    function stateWith(id) {
        var base = window.history.state && typeof window.history.state === 'object' ? window.history.state : {};
        var next = {};
        Object.keys(base).forEach(function (k) {
            if (k !== 'measSheet' && k !== 'fomsShellKeep') next[k] = base[k];
        });
        if (id) {
            next.measSheet = String(id);
            next.fomsShellKeep = 1;
        }
        return next;
    }
    /** 시트 앞 기록에 셸 건너뛰기 표식만 단다(뒤로 가기로 돌아와도 셸이 화면을 다시 읽지 않게). */
    function keepBase() {
        var next = stateWith(null);
        next.fomsShellKeep = 1;
        window.history.replaceState(next, '');
    }
    function unkeep() {
        try { window.history.replaceState(stateWith(null), ''); } catch (e) { /* 무시 */ }
    }

    /** ?focus_order 는 한 번만 쓴다 — 주소에서 지워 재진입·뒤로 가기마다 시트가 다시 열리지 않게. */
    function dropFocusParam() {
        try {
            var u = new URL(window.location.href);
            u.searchParams.delete('focus_order');
            window.history.replaceState(window.history.state, '', u.pathname + u.search + u.hash);
            var shell = window.FOMS_ERP_SHELL;
            if (shell && typeof shell.syncRenderedUrl === 'function') shell.syncRenderedUrl();
        } catch (e) { /* 무시 */ }
    }

    window.FomsMeasSheetParts = {
        decorate: decorate, setInert: setInert,
        stateWith: stateWith, keepBase: keepBase, unkeep: unkeep, dropFocusParam: dropFocusParam
    };
})();
