/* 네이버 수집 워크벤치 v3 — 화면 스크립트.
 *
 * 이 파일 전체를 지배하는 규율 셋.
 *
 *  ① **전부 이벤트 위임**. 상세 pane(#wb-pane)은 통째로 갈린다 — 행을 눌러도 페이지를
 *     다시 받지 않는 것이 v3 의 핵심(사용자가 지목한 통증 ②)이다. 요소를 잡아 두고
 *     `element.addEventListener` 로 배선하면 첫 교체에서 전부 죽는다. 그래서 배선은
 *     document 한 곳에서 `closest()` 로 판정한다.
 *
 *  ② **불가역 액션은 반드시 모달을 거친다**. 발주확인·발송처리·취소·주문 만들기는
 *     네이버로 나가거나 되돌릴 수 없는 조작이다. 여기서는 **모달 안의 확인 버튼**만
 *     문다 — 모달 없이 바로 POST 하는 경로를 만들지 않는다. 모달을 여는 일은
 *     마크업의 `data-bs-toggle="modal"` 이 하고 JS 가 가로채지 않는다.
 *
 *  ③ **재진술 숫자는 마크업이 준 값만 쓴다**. 벌크 모달의 집 수·상품주문 건수는
 *     체크된 `input.wb-pick` 의 `data-count` 합이고, 보내는 대상도 **같은 그 체크박스들**
 *     이다. 화면이 말한 건수와 서버가 처리할 건수가 갈리면 불가역 호출이 어긋난다.
 *
 * CSRF 는 공용 레이아웃(templates/partials/shared/layout_head.html)의 fetch 래퍼가
 * same-origin mutation 에 자동으로 붙인다 — 여기서 토큰을 손대지 않는다.
 * 필터 칩(a.wb-chip)은 평범한 링크다. 가로채지 않는다(계약 §4.6).
 */
(function () {
    'use strict';

    /** 상세 pane 조각 라우트(읽기 전용 GET). */
    var PANE_URL = '/admin/naver-ingest/triage/pane';
    /** mutation 라우트 접두어. 뒤에 `<link_id>/<작업>` 이 붙는다. */
    var BASE = '/admin/naver-ingest/';

    /**
     * 부분 갱신 경합 토큰.
     * 행을 빠르게 두 번 누르면 응답 순서가 뒤집힐 수 있다. 늦게 온 응답이 새 선택을
     * 덮으면 목록의 하이라이트와 오른쪽 상세가 서로 다른 집을 가리킨다 — 그 상태에서
     * 취소를 누르면 보고 있지 않은 집으로 호출이 나간다.
     */
    var paneToken = 0;

    /** id → 핸들러. 버튼 하나가 라우트 하나를 문다. */
    var ACTIONS = {
        'wb-create-order': submitCreateOrder,
        'wb-confirm-submit': submitConfirm,
        'wb-dispatch-confirm': submitDispatch,
        'wb-cancel-confirm': submitCancel,
        'wb-review-done': submitReviewDone,
        'wb-detach': submitDetach,
        'wb-bulk-confirm': submitBulk,
        'wb-bulk-clear': clearPicks,
        'wb-retry-failed': submitRetry,
        'wb-run-now': submitRunNow
    };

    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    // Bootstrap 5 의 모달 이벤트는 버블한다 — 벌크 모달이 열리기 직전에 재진술을 한 번 더
    // 맞춘다(체크 상태와 모달 문장이 어긋난 채 열리는 자리를 막는다).
    document.addEventListener('show.bs.modal', onModalShow);
    window.addEventListener('popstate', onPopState);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /* ── 초기화 ─────────────────────────────────────────────────────── */

    function init() {
        syncBulk();
        // 첫 화면도 우리 상태로 남긴다 — 뒤로가기가 여기로 돌아왔을 때 무엇을 열어야
        // 하는지 알 수 있어야 한다.
        var current = document.querySelector('.wb-row[aria-current="true"]');
        var id = current ? safeId(current.dataset.linkId) : '';
        replacePaneState(id || null);
    }

    /* ── 위임 진입점 ─────────────────────────────────────────────────── */

    function onClick(event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }

        // 체크박스는 a.wb-row **안**에 있다. 먼저 가로채지 않으면 행이 열린다.
        var box = target.closest('input.wb-pick');
        if (box) {
            onPickClick(event, box);
            return;
        }

        var btn = target.closest('button');
        if (btn) {
            if (Object.prototype.hasOwnProperty.call(ACTIONS, btn.id)) {
                ACTIONS[btn.id](btn);
                return;
            }
            if (btn.classList.contains('wb-ack')) {
                submitAck(btn);
                return;
            }
            // 붙이기 버튼은 후보 수만큼 나온다 — id 를 달면 문서에 중복이 생긴다(절대 규칙 1).
            if (btn.classList.contains('wb-attach') || btn.classList.contains('naver-attach-btn')) {
                submitAttach(btn);
                return;
            }
            // 나머지 버튼(모달 열기·닫기)은 Bootstrap 이 맡는다.
        }

        var row = target.closest('a.wb-row');
        if (row) {
            onRowClick(event, row);
        }
    }

    function onChange(event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }
        if (target.id === 'wb-pick-all') {
            togglePickAll(target.checked);
            return;
        }
        if (target.closest('input.wb-pick')) {
            syncBulk();
        }
    }

    function onModalShow(event) {
        if (event.target && event.target.id === 'wb-modal-bulk') {
            syncBulk();
        }
    }

    /* ── 행 클릭 = 부분 갱신 ─────────────────────────────────────────── */

    /**
     * 체크박스 클릭은 **행 열기가 아니다**(계약 §4.2).
     *
     * 체크박스가 앵커 안에 있어서 그냥 return 하면 앵커 기본 이동이 나간다. 그렇다고
     * `preventDefault()` 만 부르면 브라우저에 따라(활성화 대상이 체크박스인 구현) 체크
     * 토글까지 되돌려진다. 그래서 **원하는 최종 상태를 기억해 두고** 기본 동작이 끝난
     * 다음 태스크에서 우리가 확정한다 — 어느 구현에서든 같은 결과가 된다.
     */
    function onPickClick(event, box) {
        var want = box.checked;
        event.preventDefault();
        window.setTimeout(function () {
            if (box.checked !== want) {
                box.checked = want;
            }
            syncBulk();
        }, 0);
    }

    function onRowClick(event, row) {
        var id = safeId(row.dataset.linkId);
        // data-link-id 가 없는 줄은 평범한 링크다(이력 표 — 절대 규칙 3).
        if (!id || event.defaultPrevented) {
            return;
        }
        // 새 탭·새 창으로 여는 조작은 존중한다.
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        if (!document.getElementById('wb-pane')) {
            return;
        }
        event.preventDefault();
        if (row.getAttribute('aria-current') === 'true') {
            return;
        }
        markCurrent(row);
        var href = row.href;
        loadPane(id, href).then(function (ok) {
            if (ok) {
                pushPaneState(id, href);
            }
        });
    }

    function onPopState(event) {
        var state = event.state;
        var id = state ? safeId(state.wbLinkId) : '';
        if (!id) {
            // 우리가 만들지 않은 항목(또는 선택이 없던 첫 화면)이다. 주소는 이미 바뀌었으니
            // 그 주소를 그대로 다시 받는다.
            window.location.reload();
            return;
        }
        var row = document.querySelector('a.wb-row[data-link-id="' + id + '"]');
        if (row) {
            markCurrent(row);
        }
        loadPane(id, window.location.href);
    }

    /**
     * pane 조각을 받아 갈아 끼운다.
     *
     * 실패하면(네트워크·비200·조각이 아닌 응답) 전체 페이지 왕복으로 되돌린다 —
     * 부분 갱신이 막혔다고 일이 멈추면 안 된다.
     */
    async function loadPane(linkId, fallbackHref) {
        var id = safeId(linkId);
        var pane = document.getElementById('wb-pane');
        if (!id || !pane) {
            return false;
        }
        var token = ++paneToken;
        pane.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(PANE_URL + '?link_id=' + id, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const html = await response.text();
            if (token !== paneToken) {
                return false;   // 늦게 온 응답 — 새 선택을 덮지 않는다.
            }
            swapPane(html);
            return true;
        } catch (error) {
            if (token !== paneToken) {
                return false;
            }
            window.location.href = fallbackHref || window.location.href;
            return false;
        } finally {
            if (token === paneToken) {
                var current = document.getElementById('wb-pane');
                if (current) {
                    current.removeAttribute('aria-busy');
                }
            }
        }
    }

    /**
     * 응답 조각의 최상위 `#wb-pane` 으로 지금 pane 을 교체한다.
     *
     * 로그인 리다이렉트나 오류 페이지가 오면 조각이 아니다 — 그때는 갈아 끼우지 않고
     * 던져서 호출자가 전체 왕복으로 되돌리게 한다.
     */
    function swapPane(html) {
        var holder = document.createElement('div');
        holder.innerHTML = html;
        var next = holder.querySelector('#wb-pane');
        var current = document.getElementById('wb-pane');
        if (!next || !current) {
            throw new Error('pane fragment missing');
        }
        teardownModals(current);
        current.replaceWith(next);
    }

    function markCurrent(row) {
        document.querySelectorAll('.wb-row[aria-current]').forEach(function (el) {
            if (el !== row) {
                el.removeAttribute('aria-current');
            }
        });
        if (row) {
            row.setAttribute('aria-current', 'true');
        }
    }

    function pushPaneState(id, href) {
        try {
            window.history.pushState({ wbLinkId: id }, '', href);
        } catch (error) {
            /* 주소만 못 바꾼다 — 화면은 이미 갱신됐다. */
        }
    }

    function replacePaneState(id) {
        try {
            window.history.replaceState({ wbLinkId: id }, '', window.location.href);
        } catch (error) {
            /* 같음. */
        }
    }

    /* ── Bootstrap 모달 뒷정리 ───────────────────────────────────────── */

    /**
     * 교체돼 사라질 pane 안의 모달 인스턴스를 버린다.
     *
     * Bootstrap 은 인스턴스를 element 키 맵에 들고 있어서, 정리하지 않으면 행을 누를
     * 때마다 죽은 pane 이 쌓인다. 그보다 나쁜 건 **열린 채로 교체된 경우**다 —
     * 모달 요소만 사라지고 백드롭과 body.modal-open 이 남아 화면이 어둡게 잠긴다.
     */
    function teardownModals(root) {
        var wasOpen = false;
        root.querySelectorAll('.modal').forEach(function (el) {
            if (el.classList.contains('show')) {
                wasOpen = true;
            }
            var instance = modalInstance(el, false);
            if (instance) {
                try {
                    instance.dispose();
                } catch (error) {
                    /* 이미 정리된 인스턴스 — 무시해도 남는 게 없다. */
                }
            }
        });
        if (wasOpen) {
            clearModalArtifacts();
        }
    }

    function clearModalArtifacts() {
        document.querySelectorAll('.modal-backdrop').forEach(function (el) { el.remove(); });
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
    }

    function modalInstance(el, create) {
        var Modal = window.bootstrap && window.bootstrap.Modal;
        if (!el || !Modal) {
            return null;
        }
        return create ? Modal.getOrCreateInstance(el) : Modal.getInstance(el);
    }

    /**
     * 모달을 닫고 실제로 닫힐 때까지 기다린다.
     *
     * pane 을 다시 받기 전에 반드시 거친다 — 열린 모달을 그대로 두고 pane 을 갈면
     * 백드롭만 남는다. 애니메이션 이벤트가 오지 않아도 진행은 막지 않는다.
     */
    function hideModal(el) {
        return new Promise(function (resolve) {
            if (!el || !el.classList.contains('show')) {
                resolve();
                return;
            }
            var instance = modalInstance(el, true);
            if (!instance) {
                clearModalArtifacts();
                resolve();
                return;
            }
            var done = false;
            function finish() {
                if (!done) {
                    done = true;
                    resolve();
                }
            }
            el.addEventListener('hidden.bs.modal', finish, { once: true });
            window.setTimeout(finish, 600);
            try {
                instance.hide();
            } catch (error) {
                finish();
            }
        });
    }

    /* ── 벌크 선택 ───────────────────────────────────────────────────── */

    /**
     * 벌크 대상 후보.
     *
     * 절대 규칙 5: **화면 목록 안**의 체크박스만 센다. 잠긴 행(취소·반품/취소 완료/이미
     * 발주확인)은 마크업이 `disabled` 로 낸다 — 여기서 다시 판정하지 않는다.
     */
    function pickBoxes() {
        return Array.prototype.slice.call(
            document.querySelectorAll('#wb-queue input.wb-pick:not([disabled])'));
    }

    function chosenBoxes() {
        return pickBoxes().filter(function (box) { return box.checked; });
    }

    function syncBulk() {
        var bar = document.getElementById('wb-bulk');
        if (!bar) {
            return;
        }
        var boxes = pickBoxes();
        var chosen = boxes.filter(function (box) { return box.checked; });
        // 집 수만 읽히면 "2집" 이 실제로 상품주문 9건인 걸 모른다 — 둘을 함께 재진술한다.
        var items = chosen.reduce(function (sum, box) {
            return sum + (parseInt(box.dataset.count, 10) || 0);
        }, 0);

        bar.classList.toggle('on', chosen.length > 0);
        setText('wb-bulk-n', chosen.length);
        setText('wb-bulk-count', chosen.length);
        setText('wb-bulk-items', items);
        setText('wb-bulk-names', chosen.map(function (box) {
            return box.dataset.name || '';
        }).join(', '));

        var submit = document.getElementById('wb-bulk-submit');
        if (submit) {
            submit.disabled = chosen.length === 0;
        }
        var all = document.getElementById('wb-pick-all');
        if (all) {
            all.checked = boxes.length > 0 && chosen.length === boxes.length;
            all.indeterminate = chosen.length > 0 && chosen.length < boxes.length;
        }
    }

    function togglePickAll(on) {
        pickBoxes().forEach(function (box) { box.checked = on; });
        syncBulk();
    }

    function clearPicks() {
        togglePickAll(false);
        var all = document.getElementById('wb-pick-all');
        if (all) {
            all.checked = false;
            all.indeterminate = false;
        }
    }

    /* ── 불가역 액션 (모달 확인 버튼) ─────────────────────────────────── */

    /**
     * 벌크 발주확인 — 모달이 재진술한 **그 체크박스들**에만 보낸다.
     *
     * 대상 집 키는 체크박스의 `data-group-id`(대표 link id, 행의 `data-link-id` 와 같은
     * 값)에서만 나온다. "선택 없으면 전체" 패턴은 쓰지 않는다(2026-08-14 일괄 완료처리
     * AS 증발 사고가 그 패턴에서 났다).
     */
    async function submitBulk(btn) {
        var chosen = chosenBoxes();
        if (!chosen.length) {
            return;
        }
        btn.disabled = true;
        var failures = [];
        for (const box of chosen) {
            const id = safeId(box.dataset.groupId);
            if (!id) {
                continue;
            }
            const result = await postJson(BASE + id + '/fulfillment', { action: 'confirm' });
            if (!result.ok) {
                failures.push((box.dataset.name || id) + ': ' + result.error);
            }
        }
        if (failures.length) {
            // 사유는 삼키지 않는다. 실패 띠(#wb-result)에도 서버가 다시 남긴다.
            window.alert('실패 ' + failures.length + '집\n' + failures.join('\n'));
        }
        window.location.reload();
    }

    /**
     * 발주확인 단건(v3 신설).
     *
     * 예전에는 이걸 하려고 '발주확인 전' 탭으로 건너가 같은 집을 다시 찾아야 했다 —
     * 사용자가 지목한 통증 ①. 성공하면 전체 리로드 없이 pane 만 다시 받는다.
     */
    async function submitConfirm(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/fulfillment', { action: 'confirm' });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        await hideModal(document.getElementById('wb-modal-confirm'));
        var row = document.querySelector('a.wb-row[data-link-id="' + id + '"]');
        await loadPane(id, row ? row.href : window.location.href);
        // 발주확인은 **큐에 넣기만** 한다 — pane 을 다시 받아도 화면이 그대로다.
        // 아무 표시가 없으면 사람은 안 눌렸다고 보고 한 번 더 누른다. 불가역 호출에서
        // 재클릭은 그 자체가 사고 경로라 성공을 말로 남긴다.
        setPaneAck('발주확인을 보냈습니다. 네이버 응답은 잠시 뒤 목록에 반영됩니다.');
    }

    /**
     * pane 성공 문구를 채운다 — 실패는 화면 위 `#wb-result` 띠가 받는다.
     *
     * @param {string} message 사람이 읽는 문장.
     * @param {boolean} [isError] 참이면 위험색으로.
     */
    function setPaneAck(message, isError) {
        var box = document.getElementById('wb-pane-ack');
        if (!box) {
            return;
        }
        box.textContent = message || '';
        box.classList.toggle('wb-pane__ack--err', !!isError);
    }

    /**
     * 발송처리 — 네이버에 "물건이 나갔다"를 알린다. 되돌릴 수 없다.
     * 두 번 눌러 두 번 나가는 걸 화면에서 먼저 막는다(멱등은 워커도 지킨다).
     */
    async function submitDispatch(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/fulfillment', { action: 'dispatch' });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        window.location.reload();
    }

    /**
     * 판매자 직접취소 — 사유는 네이버 코드 그대로 보내고 서버가 다시 검사한다.
     */
    async function submitCancel(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var reasonEl = document.getElementById('wb-cancel-reason');
        var detailEl = document.getElementById('wb-cancel-detail');
        if (!reasonEl || !reasonEl.value) {
            window.alert('취소 사유를 고르세요.');
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/cancel', {
            reason: reasonEl.value,
            detail: detailEl ? detailEl.value : ''
        });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        window.location.reload();
    }

    /**
     * 주문 만들기 — 편집기는 새 탭으로 연다(워크벤치 자리를 잃지 않아야 다음 집으로 간다).
     */
    async function submitCreateOrder(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/create-order', {});
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        if (result.data && result.data.edit_url) {
            window.open(result.data.edit_url, '_blank', 'noopener');
        }
        window.location.reload();
    }

    /* ── 되돌릴 수 있는 조작 (모달 없음 — window.confirm 한 번) ───────── */

    /**
     * 확인 완료 — 큐에서 빼기. 네이버에는 아무것도 보내지 않는다(우리 큐에서만 사라진다).
     * 묶음 전체를 처리한다 — 형제 한 건이 남으면 같은 집이 큐에 다시 뜬다.
     */
    async function submitReviewDone(btn) {
        var ids = String(btn.dataset.linkIds || '').split(',').map(safeId).filter(Boolean);
        if (!ids.length) {
            return;
        }
        btn.disabled = true;
        for (const id of ids) {
            const result = await postJson(BASE + id + '/review', {});
            if (!result.ok) {
                window.alert(result.error);
                btn.disabled = false;
                return;
            }
        }
        // 이 집은 목록에서 사라진다 — 지금 탭·필터는 지키고 선택만 놓는다.
        // (옛 코드가 가던 `?tab=claim` 은 v3 에서 없어진 탭이다.)
        window.location.href = urlWithoutSelection();
    }

    /** 붙이기 — 되돌릴 수 있다(/detach). 확인창 한 번으로 끝낸다. */
    async function submitAttach(btn) {
        var id = safeId(btn.dataset.linkId);
        var orderId = safeId(btn.dataset.orderId);
        if (!id || !orderId) {
            return;
        }
        var label = btn.dataset.relation === 'ADDON' ? '추가결제' : '재결제';
        if (!window.confirm('주문 #' + orderId + ' 에 ' + label
                            + ' 로 붙입니다. 새 주문은 만들지 않습니다.')) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/attach', {
            order_id: Number(orderId),
            relation: btn.dataset.relation
        });
        if (!result.ok) {
            // 취소·반품 집의 추가결제는 서버가 막는다 — 사유를 그대로 띄운다.
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        window.location.reload();
    }

    async function submitDetach(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        if (!window.confirm('붙이기를 되돌립니다. 수집 직후 상태로 돌아갑니다.')) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/detach', {});
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        window.location.reload();
    }

    /* ── 결과 띠 · 수집 상태 ─────────────────────────────────────────── */

    /**
     * 실패 기록 닫기 — 네이버에는 아무 영향이 없다(우리 기록만 지운다).
     * 불가역이 아닌 일에 모달을 달면 진짜 불가역 경고가 값을 잃는다.
     */
    async function submitAck(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/fulfillment-clear', {});
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        window.location.reload();
    }

    /**
     * 실패한 집만 다시 시도.
     *
     * `<링크 id>:<작업>` 쌍이다 — 실패한 **그 작업**으로 다시 보낸다. 전부 발주확인으로
     * 보내면 발송처리 실패는 멱등 규칙에 걸려 조용히 넘어가고 띠만 영원히 남는다.
     * 모르는 작업을 confirm 으로 강등하지 않는다(취소 실패 집에 발주확인이 나가던 자리 —
     * 2026-08-23 리뷰 F9). 템플릿이 이미 거르지만 방어선을 둔다.
     */
    async function submitRetry(btn) {
        var pairs = String(btn.dataset.linkIds || '').split(',').filter(Boolean)
            .map(function (chunk) {
                var parts = chunk.split(':');
                if (parts[1] !== 'dispatch' && parts[1] !== 'confirm') {
                    return null;
                }
                var id = safeId(parts[0]);
                return id ? { id: id, action: parts[1] } : null;
            }).filter(Boolean);
        if (!pairs.length) {
            return;
        }
        btn.disabled = true;
        var stillFailing = [];
        for (const pair of pairs) {
            const result = await postJson(BASE + pair.id + '/fulfillment', { action: pair.action });
            if (!result.ok) {
                stillFailing.push(result.error);
            }
        }
        if (stillFailing.length) {
            window.alert('다시 시도했지만 ' + stillFailing.length + '집이 또 실패했습니다.\n'
                + stillFailing.join('\n'));
        }
        window.location.reload();
    }

    /** 지금 수집 — 큐에 넣기만 한다. 네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 한도 3). */
    async function submitRunNow(btn) {
        var out = document.getElementById('wb-run-result');
        btn.disabled = true;
        if (out) {
            out.textContent = '작업 큐에 넣는 중…';
        }
        const result = await postJson('/admin/naver-ingest/run', {});
        if (out) {
            out.textContent = result.ok
                ? '수집 작업을 큐에 넣었습니다. 잠시 뒤 새로고침하면 결과가 이력에 나타납니다.'
                : result.error;
        }
        btn.disabled = false;
    }

    /* ── 공용 ────────────────────────────────────────────────────────── */

    /**
     * JSON POST 한 번. 프로젝트 규칙대로 try/catch + `data.success` 검증을 여기 모은다.
     * CSRF 헤더는 공용 fetch 래퍼가 붙인다.
     */
    async function postJson(url, payload) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload || {})
            });
            let data = null;
            try {
                data = await response.json();
            } catch (parseError) {
                data = null;
            }
            if (!data) {
                // 403/500 이 HTML 로 오는 경우다 — 조용히 성공으로 넘기지 않는다.
                return { ok: false, data: null, error: '서버 응답을 읽지 못했습니다(HTTP '
                    + response.status + '). 새로고침한 뒤 다시 시도하세요.' };
            }
            if (!data.success) {
                return { ok: false, data: null, error: data.error || '요청에 실패했습니다.' };
            }
            return { ok: true, data: data.data, error: null };
        } catch (error) {
            return { ok: false, data: null, error: '요청 중 오류가 발생했습니다: ' + error };
        }
    }

    /** 링크 id 는 서버가 심은 정수다. 선택자·주소에 그대로 쓰기 전에 숫자만 남긴다. */
    function safeId(value) {
        return String(value === undefined || value === null ? '' : value).replace(/[^0-9]/g, '');
    }

    function setText(id, value) {
        var el = document.getElementById(id);
        if (el) {
            el.textContent = String(value);
        }
    }

    /** 지금 주소에서 선택(link_id)만 뺀 주소 — 탭·필터는 그대로 지킨다. */
    function urlWithoutSelection() {
        try {
            var url = new URL(window.location.href);
            url.searchParams.delete('link_id');
            return url.toString();
        } catch (error) {
            return window.location.pathname + window.location.search;
        }
    }
})();
