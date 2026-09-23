/**
 * 실측 모바일 바텀시트 부품 — 시트로 옮긴 카드의 배치 손질, 뒤 화면 inert, 방문 기록(history) 도우미.
 * mobile-glance-sheet.js 가 부른다(이 파일은 그보다 먼저 실린다).
 *
 * - "실측 체크" 토글: 카드 제목 바로 밑(목업 순서).
 * - 실측 사진: ERP 에 등록된 미리보기 이미지가 있을 때만 주소·연락처(meta) 아래로 옮기고 제목
 *   "실측 사진 · 사진 n" 을 단다. 이미지가 없으면 칸 자체를 숨긴다(사진 추가 없음).
 * - 넘긴 주문의 "실측 완료" 표시: 단추 줄 자리(카드 footer)로.
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
            if (meta && meta.parentNode && meta.nextElementSibling !== att) {
                meta.parentNode.insertBefore(att, meta.nextSibling);
            }
            var head = photoHeader(att);
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

    function decorate(card, sheet) {
        var vc = sheet.querySelector('[data-meas-sheet-check]');
        var title = card.querySelector('.queue-card__title');
        if (vc && title && title.parentNode) title.parentNode.insertBefore(vc, title.nextSibling);
        placePhotos(card);
        placeHanded(card);
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
