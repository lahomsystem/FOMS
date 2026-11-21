/**
 * 새 주문 안내 — 같은 고객의 진행 중 주문 한 줄 (PC ERP 주문 폼 · 주문 복사 도착 화면).
 *
 * 설계서 2026-11-20 "한 주문 여러 시공일 1단계" 6.2 (M15 · M17).
 * - 새 주문(초안)에서 연락처 · 주소 칸을 벗어날 때 서버에 물어 폼 위에 한 줄을 그린다. 저장하면 화면이 바로
 *   떠나므로 저장 전에 보여야 한다. 알리기만 하고 저장은 막지 않는다.
 * - 복사로 만든 주문의 편집 화면에 도착하면 한 번 묻는다(자기 자신은 뺀다).
 * - 프리랜서 · 협력사는 서버가 403 을, 목록 밖 역할은 로그인 화면 HTML 을 준다 — 둘 다 막힘으로 보고
 *   조용히 넘어가며 다시 묻지 않는다.
 * - 고객 이름은 보내지 않는다(서버가 찾는 데 쓰지 않고, 주소창 기록 · 접속 로그에 남는다).
 *
 * 자리: templates/orders/partials/erp_order_tab.html 의 #erp-same-customer-notice. 화면 낭독기가 첫 안내를
 * 읽도록 자리는 처음부터 접근성 트리에 두고, 비었을 때는 visually-hidden 으로 눈에만 숨긴다.
 * 글은 textContent 로만 넣는다(주소는 저장된 값이다).
 */
(function () {
    'use strict';

    var TITLE = '이 고객의 진행 중인 주문이 있습니다';
    var OPEN_LABEL = '그 주문 열기';
    var PHONE_ID = 'erp-customer-phone';
    var ADDRESS_ID = 'erp-address';
    var ADDRESS_MODAL_ID = 'erpAddressSearchModal';
    var EMPTY_CLASS = 'visually-hidden';

    var box = document.getElementById('erp-same-customer-notice');
    if (!box) return;
    var lookupUrl = box.getAttribute('data-lookup-url') || '';
    if (!lookupUrl) return;

    var lastKey = null;
    var requestSeq = 0;
    var denied = false;

    function fieldValue(id) {
        var el = document.getElementById(id);
        return el ? String(el.value || '').trim() : '';
    }

    /** 쓰고 있는 주문이 아직 등록 전(초안)인가 — 등록된 주문을 고칠 때는 묻지 않는다. */
    function isNewOrder() {
        if (typeof window.erpIsDraftBackedOrder === 'function') return !!window.erpIsDraftBackedOrder();
        return !!window.__ERP_ORDER_DRAFT_MODE;
    }

    /** 빼야 할 자기 주문 번호(초안 줄 · 복사본). */
    function currentOrderId() {
        var resolved = typeof window.erpResolveCurrentOrderId === 'function' ? window.erpResolveCurrentOrderId() : 0;
        return resolved || parseInt(box.getAttribute('data-order-id') || '0', 10) || 0;
    }

    /** '2026-11-17' → '11/17'. 꼴이 다르면 그대로 둔다. */
    function shortDate(value) {
        var match = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(String(value || ''));
        return match ? parseInt(match[2], 10) + '/' + parseInt(match[3], 10) : String(value || '');
    }

    /** 주문 한 줄 글: '주문 #5687 · 생산 단계 · 시공 11/5, 11/17 · 주소'. */
    function orderText(order) {
        var parts = ['주문 #' + order.order_id];
        if (order.stage_label) parts.push(order.stage_label + ' 단계');
        var dates = Array.isArray(order.construction_dates) ? order.construction_dates : [];
        if (dates.length) parts.push('시공 ' + dates.map(shortDate).join(', '));
        if (order.address) parts.push(order.address);
        return parts.join(' · ');
    }

    function hide() {
        box.classList.add(EMPTY_CLASS);
        box.replaceChildren();
    }

    /** JSON 이 아닌 응답(권한 밖 역할이 받는 로그인 화면 등)이면 null. */
    async function readJson(response) {
        var type = response.headers.get('Content-Type') || '';
        if (type.indexOf('application/json') === -1) return null;
        try {
            return await response.json();
        } catch (parseError) {
            return null;
        }
    }

    function render(data) {
        var orders = Array.isArray(data.orders) ? data.orders : [];
        if (!orders.length) {
            hide();
            return;
        }
        var title = document.createElement('div');
        title.className = 'fw-bold';
        var icon = document.createElement('i');
        icon.className = 'fas fa-triangle-exclamation me-1';
        icon.setAttribute('aria-hidden', 'true');
        title.appendChild(icon);
        title.appendChild(document.createTextNode(TITLE));

        var rows = orders.map(function (order) {
            var row = document.createElement('div');
            row.appendChild(document.createTextNode(orderText(order) + ' '));
            if (order.url) {
                var link = document.createElement('a');
                link.className = 'alert-link text-nowrap';
                link.href = order.url;
                link.target = '_blank';
                link.rel = 'noopener';
                link.textContent = OPEN_LABEL;
                link.setAttribute('aria-label', OPEN_LABEL + ' (주문 #' + order.order_id + ')');
                row.appendChild(link);
            }
            return row;
        });

        var more = parseInt(data.more, 10) || 0;
        var nodes = [title].concat(rows);
        if (more > 0) {
            var rest = document.createElement('div');
            rest.className = 'small';
            rest.textContent = '외 ' + more + '건';
            nodes.push(rest);
        }
        box.replaceChildren.apply(box, nodes);
        box.classList.remove(EMPTY_CLASS);
    }

    /**
     * 서버에 물어 한 줄을 그린다. 같은 입력이면 다시 묻지 않는다.
     * @param {string} phone 연락처 칸 값
     * @param {string} address 주소 칸 값
     */
    async function lookup(phone, address) {
        if (denied) return;
        var orderId = currentOrderId();
        var key = [phone, address, orderId].join('|');
        if (key === lastKey) return;
        lastKey = key;
        var mine = ++requestSeq;
        if (!phone && !address) {
            hide();
            return;
        }
        var params = new URLSearchParams({ phone: phone, address: address });
        if (orderId) params.set('exclude_order_id', String(orderId));
        try {
            var response = await fetch(lookupUrl + '?' + params.toString(), {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' }
            });
            var data = response.status === 403 ? null : await readJson(response);
            if (response.status === 403 || data === null) {
                denied = true; // 막힌 역할 — 이 화면에서는 다시 묻지 않는다
                hide();
                return;
            }
            if (mine !== requestSeq) return; // 늦게 온 옛 응답은 버린다
            if (!response.ok || !data || !data.success) {
                hide();
                return;
            }
            render(data.data || {});
        } catch (error) {
            if (mine === requestSeq) hide();
            console.warn('[erp-same-customer-notice] 진행 중 주문 확인 실패', error);
        }
    }

    function checkForm() {
        if (!isNewOrder()) return;
        lookup(fieldValue(PHONE_ID), fieldValue(ADDRESS_ID));
    }

    [PHONE_ID, ADDRESS_ID].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('blur', checkForm);
        el.addEventListener('change', checkForm);
    });
    // 주소 찾기 창에서 고른 주소는 칸을 벗어나지 않고 들어온다 — 창이 닫힐 때 한 번 본다.
    document.addEventListener('hidden.bs.modal', function (event) {
        if (event.target && event.target.id === ADDRESS_MODAL_ID) checkForm();
    });

    // 복사로 만든 주문에 도착했을 때 한 번(원본이 아직 진행 중이면 그 주문이 걸린다).
    if (box.getAttribute('data-copy-arrival') === 'true') {
        lookup(
            String(box.getAttribute('data-copy-phone') || '').trim(),
            String(box.getAttribute('data-copy-address') || '').trim()
        );
    }
})();
