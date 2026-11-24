/**
 * 네이버 쿠폰 표시 — 예약금 동전 옆 쿠폰 그림 · 아래 한 줄 · 눌렀을 때만 내역 (2026-11-24).
 *
 * 데이터는 도크와 같은 #naver-origin-data 의 `coupon_view` 하나(추가 fetch 0).
 * 낱말 · 돈 표기 · 색(tone)은 서버(coupon_view.py)가 만든다 — 여기는 그리기만 한다.
 * 원본 글은 전부 textContent 로만 넣는다. 쿠폰을 안 쓴 주문은 coupon_view 가 없어 아무것도 안 생긴다.
 */
(function () {
    'use strict';

    var TONES = { ours: 1, naver: 1, unknown: 1 };
    // 쿠폰 그림(고정 글 — 서버 값이 들어가지 않는다). 색은 CSS 의 currentColor.
    var TICKET_SVG = '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">' +
        '<path fill="currentColor" d="M5 11h30a2 2 0 0 1 2 2v4a3 3 0 0 0 0 6v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4a3 3 0 0 0 0-6v-4a2 2 0 0 1 2-2z"/>' +
        '<path stroke="#fff" stroke-width="1.6" stroke-dasharray="2.5 2.5" fill="none" d="M14 13v14"/>' +
        '<text x="25" y="25" text-anchor="middle" font-size="13" font-weight="700" fill="#fff">MARK</text></svg>';

    function readView() {
        var node = document.getElementById('naver-origin-data');
        if (!node) return null;
        try {
            var payload = JSON.parse(node.textContent || 'null');
            return (payload && payload.coupon_view) || null;
        } catch (error) {
            return null;
        }
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function fillBox(box, view) {
        box.textContent = '';
        box.appendChild(el('div', 'erp-coupon-box__title', view.title || '쿠폰 내역'));
        (view.rows || []).forEach(function (row) {
            var item = el('div', 'erp-coupon-box__row');
            item.appendChild(el('span', 'erp-coupon-box__label', row.label));
            item.appendChild(el('span', 'erp-coupon-box__amount', row.amount));
            item.appendChild(el('span', 'erp-coupon-box__who', row.who));
            box.appendChild(item);
        });
        if (view.note) box.appendChild(el('div', 'erp-coupon-box__note', view.note));
        [['쿠폰 합계', view.total], ['우리가 낸 몫', view.ours]].forEach(function (pair) {
            if (!pair[1]) return;
            var sum = el('div', 'erp-coupon-box__sum');
            sum.appendChild(el('span', '', pair[0]));
            sum.appendChild(el('span', 'erp-coupon-box__amount', pair[1]));
            box.appendChild(sum);
        });
    }

    function init() {
        var icon = document.getElementById('erp-coupon-icon');
        var line = document.getElementById('erp-coupon-line');
        var box = document.getElementById('erp-coupon-box');
        if (!icon || !line || !box || icon.dataset.couponBound === '1') return;
        var view = readView();
        if (!view || !TONES[view.tone]) return;
        icon.dataset.couponBound = '1';
        var tone = 'erp-coupon--' + view.tone;

        function setOpen(open) {
            box.hidden = !open;
            icon.setAttribute('aria-expanded', open ? 'true' : 'false');
            lineBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
        }
        function toggle() { setOpen(box.hidden); }

        icon.innerHTML = TICKET_SVG.replace('MARK', view.tone === 'unknown' ? '?' : '%');
        icon.classList.add(tone);
        icon.hidden = false;
        // 모바일 틀은 그림과 한 줄 글을 한 줄 상자(.erp-coupon-row)에 담는다 — 상자도 같이 연다.
        var rowWrap = icon.closest('.erp-coupon-row');
        if (rowWrap) rowWrap.hidden = false;

        var lineBtn = el('button', 'erp-coupon-line__btn ' + tone, view.line);
        lineBtn.type = 'button';
        lineBtn.setAttribute('aria-controls', 'erp-coupon-box');
        line.textContent = '';
        line.appendChild(lineBtn);
        line.hidden = false;

        box.classList.add(tone);
        fillBox(box, view);
        setOpen(false);
        icon.addEventListener('click', toggle);
        lineBtn.addEventListener('click', toggle);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
    // fragment 스왑으로 편집 화면이 나중에 오는 길 — 쿠폰 칸이 나타나면 다시 그린다.
    new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i += 1) {
            var added = mutations[i].addedNodes;
            for (var j = 0; j < added.length; j += 1) {
                var node = added[j];
                if (node.nodeType === 1 && (node.id === 'erp-coupon-line' || node.id === 'naver-origin-data' ||
                    (node.querySelector && node.querySelector('#erp-coupon-line, #naver-origin-data')))) {
                    init();
                    return;
                }
            }
        }
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
