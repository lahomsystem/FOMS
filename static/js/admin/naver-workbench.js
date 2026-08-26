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
    // 이력 행의 **읽기 전용** 원본 조각. pane 과 다른 경로다 — 조각에 처리 버튼이
    // 없어야 이력에서 되돌릴 수 없는 호출이 나가지 않는다(이력 절대 규칙 3).
    var DETAIL_URL = '/admin/naver-ingest/triage/detail';
    /** mutation 라우트 접두어. 뒤에 `<link_id>/<작업>` 이 붙는다. */
    var BASE = '/admin/naver-ingest/';

    /** 집의 워커 처리 표식만 묻는 읽기 전용 경로(폴링 대상). */
    var STATE_URL = '/admin/naver-ingest/triage/fulfillment-state';
    /** 폴링 주기·마감. **끝이 있어야 한다** — 무한 폴링 금지(nav 뱃지 부하와 겹친다). */
    var POLL_INTERVAL_MS = 2000;
    var POLL_TIMEOUT_MS = 25000;
    /** 재시도는 폴링하지 않는다(집 수만큼 곱해진다) — 한 번만 늦게 갱신한다. */
    var BULK_REFRESH_MS = 15000;
    /** 벌크 진행 조회(집 수와 무관하게 서버 조회 2회). */
    var PROGRESS_URL = '/admin/naver-ingest/triage/fulfillment-progress';
    /** 벌크는 워커가 집을 하나씩 처리한다 — 단건보다 창이 넓어야 끝을 본다. */
    var BULK_POLL_INTERVAL_MS = 3000;
    var BULK_POLL_TIMEOUT_MS = 90000;

    /** 수집 워터마크만 묻는 읽기 전용 경로('지금 수집' 결과 폴링 대상). */
    var RUN_STATE_URL = '/admin/naver-ingest/run-state';
    /** 수집 한 바퀴는 집 조작 하나보다 오래 걸린다(네이버 여러 페이지) — 창을 넓게 잡는다. */
    var RUN_POLL_INTERVAL_MS = 3000;
    var RUN_POLL_TIMEOUT_MS = 90000;

    /**
     * 부분 갱신 경합 토큰.
     * 행을 빠르게 두 번 누르면 응답 순서가 뒤집힐 수 있다. 늦게 온 응답이 새 선택을
     * 덮으면 목록의 하이라이트와 오른쪽 상세가 서로 다른 집을 가리킨다 — 그 상태에서
     * 취소를 누르면 보고 있지 않은 집으로 호출이 나간다.
     */
    var paneToken = 0;
    var detailToken = 0;

    /**
     * 폴링 경합 토큰과 타이머.
     * 집을 연속으로 조작하면 앞 폴링이 아직 돌고 있다. 늦게 온 폴링이 새 조작의 결과를
     * 덮으면 화면이 방금 누른 것과 다른 집·다른 작업을 말한다.
     */
    var pollToken = 0;
    var pollTimer = null;

    /** 전역 nav 높이 재측정 디바운스 타이머(위쪽 고정줄 오프셋). */
    var navOffsetTimer = null;

    /** 벌크 폴링 토큰·타이머(단건과 따로 — 서로를 끊지 않는다). */
    var bulkToken = 0;
    var bulkTimer = null;

    /** 수집 폴링 토큰·타이머. 단건(pollToken)·벌크(bulkToken)와 **따로 둔다** —
        하나를 나눠 쓰면 '지금 수집' 을 누른 순간 돌고 있던 집 조작 폴링이 끊기고(그
        반대도 마찬가지) 끊긴 쪽은 결과를 영영 못 본다. */
    var runToken = 0;
    var runTimer = null;

    /** 글자 크기 단계와 저장 키. **init() 보다 위에 둔다** — defer 스크립트라 init 이
        곧바로 실행되는데, var 는 선언만 끌어올려지고 대입은 안 따라온다(값이 undefined). */
    var FONT_STEPS = [1, 1.15, 1.3, 1.5];
    var FONT_KEY = 'foms.naverWorkbench.fontScale';

    /** id → 핸들러. 버튼 하나가 라우트 하나를 문다. */
    var ACTIONS = {
        'wb-create-order': submitCreateOrder,
        'wb-fs-up': function () { stepFontScale(1); },
        'wb-fs-down': function () { stepFontScale(-1); },
        'wb-confirm-submit': submitConfirm,
        'wb-dispatch-confirm': submitDispatch,
        'wb-cancel-confirm': submitCancel,
        'wb-review-done': submitReviewDone,
        'wb-refresh': submitRefresh,
        'wb-detach': submitDetach,
        'wb-bulk-confirm': submitBulk,
        'wb-bulk-clear': clearPicks,
        'wb-retry-failed': submitRetry,
        'wb-run-now': submitRunNow,
        'wb-ghost-discard': submitGhostDiscard
    };

    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    // 목록 안 찾기는 서버 왕복 없이 즉시 좁힌다 — 위임이라 pane 교체에도 안 죽는다.
    document.addEventListener('input', onInput);
    // Bootstrap 5 의 모달 이벤트는 버블한다 — 벌크 모달이 열리기 직전에 재진술을 한 번 더
    // 맞춘다(체크 상태와 모달 문장이 어긋난 채 열리는 자리를 막는다).
    document.addEventListener('show.bs.modal', onModalShow);
    window.addEventListener('popstate', onPopState);
    // 폭 변화(= nav 접힘)와 nav 자체 높이 변화(메뉴 펼침·알림 줄바꿈) 둘 다 잡는다.
    window.addEventListener('resize', scheduleNavOffset);
    if (typeof window.ResizeObserver === 'function') {
        window.addEventListener('DOMContentLoaded', observeNav);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /* ── 초기화 ─────────────────────────────────────────────────────── */

    function init() {
        applyFontScale(readFontScale());
        syncNavOffset();
        syncBulk();
        // 서버가 전체 렌더에서 내린 "목록 밖 집" 판정을 첫 화면에서 읽어 둔다 —
        // 이후 조각 교체는 이 값을 옮겨 붙인다(applyOfflistFlag).
        paneOfflist = readOfflistFlag();
        // 첫 화면도 우리 상태로 남긴다 — 뒤로가기가 여기로 돌아왔을 때 무엇을 열어야
        // 하는지 알 수 있어야 한다.
        var current = document.querySelector('.wb-row[aria-current="true"]');
        var id = current ? safeId(current.dataset.linkId) : '';
        replacePaneState(id || null);
    }

    /* ── 유령 주문 취소 처리 (R-2 · 2026-08-25) ──────────────────────────
       네이버 결제가 전부 취소됐는데 살아 있는 ERP 주문을 접는다. soft delete 라
       휴지통에서 복구된다 — 그래서 불가역 4종 세트 모달이 아니라 확인창 1회다.
       (되돌릴 수 없는 것만 모달을 쓴다는 이 화면의 규율.) */
    function submitGhostDiscard(button) {
        var orderId = safeId(button.dataset.orderId);
        if (!orderId) {
            return;
        }
        var who = button.dataset.customer || '';
        var message = '주문 #' + orderId + (who ? ' (' + who + ')' : '')
            + ' 을 취소 처리합니다. 휴지통으로 가며 복구할 수 있습니다.';
        if (!window.confirm(message)) {
            return;
        }
        button.disabled = true;
        postJson(BASE + 'ghost/' + orderId + '/discard', {}).then(function (result) {
            if (!result.ok) {
                button.disabled = false;
                window.alert(result.error);
                return;
            }
            // 목록에서 그 줄만 걷어낸다 — 페이지를 다시 받지 않는다(v3 규율 ②).
            var row = button.closest('[data-ghost-order-id]');
            if (row && row.parentNode) {
                row.parentNode.removeChild(row);
            }
        });
    }

    /* ── 위쪽 고정줄 오프셋 (2026-08-25) ─────────────────────────────────
       머리줄·도구줄은 처음부터 `position: sticky` 였는데 **화면에서는 안 붙어 보였다**.
       위에 전역 nav(`.layout-global-nav`)가 `sticky; top: 0; z-index: 1000` 으로 이미
       붙어 있어서, `top: 0` 인 머리줄이 그 **밑에 깔린** 것이다(z-index 3 vs 1000).

       고정 px 로 비켜 세울 수 없다: nav 높이가 폭에 따라 67 -> 97 -> 121 -> 169px 로
       변한다(1920/992/900/768 실측). 그래서 실측해서 CSS 변수 하나로 흘린다 —
       CSS 쪽 세 자리(머리줄·도구줄·상세 pane)가 전부 그 변수를 문다.

       nav 가 없거나 숨겨진 셸(모바일 v2 등)에서는 0 이 들어가 예전 동작(top: 0)이 된다. */
    function syncNavOffset() {
        var root = document.querySelector('.naver-workbench');
        if (!root) {
            return;
        }
        var nav = document.querySelector('.layout-global-nav');
        // getBoundingClientRect 는 sticky 여도 **높이**는 스크롤과 무관하게 같은 값을 준다.
        var height = nav ? Math.round(nav.getBoundingClientRect().height) : 0;
        root.style.setProperty('--wb-nav-h', height + 'px');
    }

    /** nav 자체가 커지는 경우(햄버거 메뉴 펼침 등)는 resize 가 안 온다 — 직접 지켜본다. */
    function observeNav() {
        var nav = document.querySelector('.layout-global-nav');
        if (!nav) {
            return;
        }
        new window.ResizeObserver(scheduleNavOffset).observe(nav);
    }

    /** 폭이 바뀌면 nav 가 접히며 높이가 변한다 — 다시 잰다(연타 방지 디바운스). */
    function scheduleNavOffset() {
        if (navOffsetTimer) {
            window.clearTimeout(navOffsetTimer);
        }
        navOffsetTimer = window.setTimeout(function () {
            navOffsetTimer = null;
            syncNavOffset();
        }, 120);
    }

    /* ── 글자 크기 (2026-08-24) ──────────────────────────────────────────
       브라우저를 80% 로 축소해 쓰는 사용자에게 11~12px 는 9~10px 로 보인다. 브라우저
       확대는 화면 전체를 키워 2단 목록이 잘리므로, **이 화면 글자만** 단계로 키운다.
       배율은 CSS 변수 `--wb-fs` 하나로 흐른다(모든 font-size 가 calc 로 그 변수를 문다).
       사람마다 쓰는 축소율이 달라 선택은 localStorage 에 남긴다. */
    function readFontScale() {
        try {
            var saved = parseFloat(window.localStorage.getItem(FONT_KEY));
            // 저장값이 단계 목록에 없으면(옛 값·손댄 값) 기본으로 되돌린다.
            return FONT_STEPS.indexOf(saved) >= 0 ? saved : FONT_STEPS[0];
        } catch (error) {
            return FONT_STEPS[0];   // 사생활 보호 모드 등에서 localStorage 가 막힌다
        }
    }

    function applyFontScale(scale) {
        var root = document.querySelector('.naver-workbench');
        if (!root) {
            return;
        }
        root.style.setProperty('--wb-fs', String(scale));
        var label = document.getElementById('wb-fs-now');
        if (label) {
            label.textContent = Math.round(scale * 100) + '%';
        }
        var idx = FONT_STEPS.indexOf(scale);
        var down = document.getElementById('wb-fs-down');
        var up = document.getElementById('wb-fs-up');
        // 끝에 닿으면 잠근다 — 눌러도 안 변하는 버튼은 고장으로 읽힌다.
        if (down) { down.disabled = idx <= 0; }
        if (up) { up.disabled = idx >= FONT_STEPS.length - 1; }
    }

    function stepFontScale(direction) {
        var idx = FONT_STEPS.indexOf(readFontScale()) + direction;
        if (idx < 0 || idx >= FONT_STEPS.length) {
            return;
        }
        var next = FONT_STEPS[idx];
        try {
            window.localStorage.setItem(FONT_KEY, String(next));
        } catch (error) {
            /* 저장만 못 한다 — 이번 화면에서는 그대로 적용된다. */
        }
        applyFontScale(next);
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

            // 후보 버튼은 후보 수만큼 나온다 — id 를 달면 문서에 중복이 생긴다(절대 규칙 1).
            // R-3 부터 이 버튼은 바로 붙이지 않고 **정리 계획 카드**를 연다.
            if (btn.classList.contains('wb-attach')) {
                openReconcilePlan(btn);
                return;
            }
            if (btn.classList.contains('wb-plan-run')) {
                submitReconcile(btn);
                return;
            }
            if (btn.classList.contains('wb-plan-close')) {
                closePlan(btn.closest('.wb-plan'));
                return;
            }
            // 나머지 버튼(모달 열기·닫기)은 Bootstrap 이 맡는다.
        }

        // 이력 '원본 보기' — 평범한 링크다(이력 절대 규칙 3). JS 가 있을 때만 가로채
        // 모달로 띄우고, 없으면 그 조각이 그대로 열린다. 행 수만큼 나오므로 id 가 아니라
        // 클래스로 문다(절대 규칙 1).
        var detailLink = target.closest('a.wb-hist-detail');
        if (detailLink) {
            event.preventDefault();
            openHistoryDetail(detailLink);
            return;
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
            return;
        }
        // 갈래(승계/취소 처리)를 바꾸면 1번 칸의 안내 문장이 달라진다 — 취소 처리는 붙이지
        // 않기 때문이다. 계획과 실제 동작이 어긋난 채로 실행 버튼을 누르는 자리를 막는다.
        if (target.classList.contains('wb-fork__pick')) {
            applyPlanFork(target.closest('.wb-plan'));
        }
    }

    /**
     * 목록 안 찾기 — 지금 화면에 있는 줄만 즉시 좁힌다.
     *
     * 서버로 보내지 않는 이유: 이 화면의 목록은 이미 한 번에 다 와 있고(캡 500집),
     * 왕복을 넣으면 한 글자마다 조회가 나간다. 대신 **범위를 화면에 못 박는다** —
     * 확인 완료로 큐에서 빠진 집은 목록에 없으므로 여기서도 안 나온다.
     *
     * 정렬은 반대로 서버가 한다: 캡보다 먼저 돌아야 캡이 자를 집이 달라진다.
     */
    function onInput(event) {
        if (!event.target || event.target.id !== 'wb-find') {
            return;
        }
        applyFind(event.target.value);
    }

    /**
     * 찾기 낱말로 행을 숨기고 결과 수를 고지한다.
     * @param {string} raw 사용자가 친 문자열.
     */
    function applyFind(raw) {
        var needle = String(raw || '').trim().toLowerCase();
        var rows = Array.prototype.slice.call(
            document.querySelectorAll('#wb-queue a.wb-row'));
        var shown = 0;
        rows.forEach(function (row) {
            var hay = row.getAttribute('data-find') || '';
            var hit = !needle || hay.indexOf(needle) !== -1;
            // hidden 은 CSS 없이도 먹는다 — 이 화면 CSS 가 늦게 와도 목록이 안 어긋난다.
            row.hidden = !hit;
            if (hit) {
                shown += 1;
            }
        });
        var note = document.getElementById('wb-find-note');
        if (note) {
            // 조용히 좁히면 "집이 사라졌다"가 된다. 찾는 중일 때만 말한다.
            note.textContent = needle
                ? (shown + '주문 / ' + rows.length + '주문')
                : '';
        }
        // 숨은 줄이 선택에 남아 있으면 벌크가 화면에 없는 집으로 나간다(계약 §0-5).
        clearHiddenPicks();
        syncBulk();
    }

    /** 찾기로 숨겨진 행의 체크를 푼다 — 벌크 대상은 **화면에 보이는 집**의 부분집합이다. */
    function clearHiddenPicks() {
        var boxes = document.querySelectorAll('#wb-queue a.wb-row[hidden] input.wb-pick:checked');
        Array.prototype.forEach.call(boxes, function (box) {
            box.checked = false;
        });
    }

    /**
     * 찾기 칸의 상태를 뜬다 — 화면 루트를 통째로 갈기 **직전**에 부른다.
     *
     * 전체 렌더는 이 칸을 늘 빈 채로 준다(서버는 사용자가 무엇을 쳤는지 모른다). 뜨지
     * 않고 갈면 조작 한 번에 낱말이 날아가, 큐에서 보던 자리를 다시 쳐서 찾아야 한다.
     * @returns {{value: string, focused: boolean, start: number, end: number}}
     */
    function captureFind() {
        var el = document.getElementById('wb-find');
        if (!el) {
            return { value: '', focused: false, start: 0, end: 0 };
        }
        var caret = el.value.length;
        var start = caret;
        var end = caret;
        try {
            // 캐럿 API 는 input 종류에 따라 던진다(email·number 계열). 지금 이 칸은
            // type="search" 라 안전하지만, 종류가 바뀌어도 낱말은 지키도록 감싸 둔다.
            start = el.selectionStart === null ? caret : el.selectionStart;
            end = el.selectionEnd === null ? caret : el.selectionEnd;
        } catch (error) {
            /* 캐럿만 잃는다 — 값과 포커스는 그대로 돌려준다. */
        }
        return { value: el.value, focused: document.activeElement === el, start: start, end: end };
    }

    /**
     * 뜬 찾기 상태를 새 칸에 옮겨 심고 목록을 **다시 좁힌다**.
     *
     * 값만 옮기고 좁히지 않으면 칸에는 낱말이 남았는데 전체 목록이 보인다 — 한 화면이
     * 두 말을 한다. 서버가 새로 준 목록(집 하나가 빠졌을 수 있다)에 같은 낱말을 먹인다.
     * @param {{value: string, focused: boolean, start: number, end: number}} state
     */
    function restoreFind(state) {
        var el = document.getElementById('wb-find');
        if (!el || !state) {
            return;
        }
        if (state.value) {
            el.value = state.value;
            applyFind(state.value);
        }
        if (state.focused) {
            // 치는 도중에 갱신이 끼어들면 포커스까지 잃는다 — 다음 글자가 허공으로 간다.
            el.focus();
            try {
                el.setSelectionRange(state.start, state.end);
            } catch (error) {
                /* 캐럿만 못 놓는다 — 커서는 글자 끝에 선다. */
            }
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
        paneOfflist = false;   // 왼쪽 목록의 행을 눌러 연 집이다.
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
    /**
     * 이력 행의 네이버 원본을 **읽기 전용 모달**로 연다.
     *
     * 큐에서 빠진 집은 처리 목록에 없어서, 지금까지 원본을 보려면 ERP 편집기를 새 탭으로
     * 열어야 했다 — 그런데 옵션 원문·배송메모·클레임 사유·발송 결과는 거기 없다.
     *
     * 조각을 그대로 넣는다. 실패해도 페이지를 갈아엎지 않는다 — 이력은 읽는 화면이라
     * 모달 안에서 사실대로 말하고 끝낸다(전체 왕복 폴백은 여기서 오히려 맥락을 잃는다).
     */
    async function openHistoryDetail(link) {
        var id = safeId(link.getAttribute('data-detail-id'));
        var body = document.getElementById('wb-detail-body');
        var who = document.getElementById('wb-detail-who');
        var modal = document.getElementById('wb-modal-detail');
        if (!id || !body || !modal || !window.bootstrap) {
            return;
        }
        if (who) {
            who.textContent = link.getAttribute('data-customer') || '';
        }
        body.setAttribute('aria-busy', 'true');
        body.innerHTML = '<p class="text-muted mb-0">불러오는 중…</p>';
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
        var token = ++detailToken;
        try {
            const response = await fetch(DETAIL_URL + '?link_id=' + id, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const html = await response.text();
            if (token !== detailToken) {
                return;   // 늦게 온 응답 — 새로 연 집을 덮지 않는다.
            }
            body.innerHTML = html;
        } catch (error) {
            if (token !== detailToken) {
                return;
            }
            // 조용히 비우지 않는다 — 빈 모달은 "원본이 없다"로 읽힌다.
            body.innerHTML = '<p class="text-danger mb-0">원본을 불러오지 못했습니다. '
                + '잠시 뒤 다시 눌러 주세요.</p>';
        } finally {
            if (token === detailToken) {
                body.setAttribute('aria-busy', 'false');
            }
        }
    }

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
    /**
     * "지금 왼쪽 목록에 없는 집" 판정을 조각 교체 너머로 옮긴다.
     *
     * 판정 주체는 여전히 서버다(전체 렌더의 `_selected_offlist`). 다만 pane 프래그먼트
     * 응답에는 목록이 없어 서버가 같은 판정을 할 수 없고, 그 자리에서 술어를 다시
     * 구현하면 모집단 판정이 두 벌이 된다(v3 리뷰 H1 이 그 갈라짐에서 나왔다).
     * 그래서 값을 **여기서 들고 다닌다** — 행을 눌러 연 집은 정의상 목록 안이라 false 로
     * 내려가고, 발주확인 성공·뒤로가기처럼 **같은 집을 다시 받는** 경로는 직전 값을 유지한다.
     * 이게 없으면 발주확인을 누른 순간 경고만 사라지고 불가역 버튼은 그대로 남는다.
     */
    var paneOfflist = false;

    function readOfflistFlag() {
        var note = document.getElementById('wb-offlist');
        return !!(note && !note.hasAttribute('hidden'));
    }

    function applyOfflistFlag() {
        var note = document.getElementById('wb-offlist');
        if (!note) {
            return;
        }
        if (paneOfflist) {
            note.removeAttribute('hidden');
        } else {
            note.setAttribute('hidden', 'hidden');
        }
    }

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
        applyOfflistFlag();
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

    /**
     * 열려 있는 집을 history 상태에 다시 심는다.
     *
     * @param {?string} id 열린 집의 링크 id. 없으면 null(선택 해제).
     * @param {string} [href] 주소도 함께 바꿀 때만 준다(기본은 지금 주소 유지).
     *   선택을 놓는 자리는 **새 기록을 쌓지 않는다** — pushState 로 하면 뒤로가기가
     *   방금 큐에서 뺀 집으로 되돌아간다. 그래서 push 가 아니라 replace 다.
     */
    function replacePaneState(id, href) {
        try {
            window.history.replaceState({ wbLinkId: id }, '', href || window.location.href);
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

        // 진행 문구가 남아 있으면 선택이 0 이어도 바를 연다 — 화면을 다시 받으면 체크가
        // 풀리는데, 그때 바가 접히면 "다 됐는지" 를 말할 자리가 같이 사라진다.
        var note = document.getElementById('wb-bulk-note');
        var noteOn = !!(note && note.textContent.trim());
        bar.classList.toggle('on', chosen.length > 0 || noteOn);
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

    /* ── 워커 결과 기다리기 (2026-08-24) ───────────────────────────────
       발주확인·발송처리·취소는 **큐에 들어가고 서버가 바로 답한다**(네이버 HTTP 는
       WORKER 단일 출구 — 커머스API 호출 IP 3슬롯 계약). 그 직후에 화면을 갱신하면
       아직 옛 상태다: 사용자에게는 "눌러도 아무 일이 없다"로 보이고, 되돌릴 수 없는
       조작에서 재클릭을 부른다. 실패는 더 나빴다 — 워커가 남긴 사유가 전체 렌더의
       실패 띠에만 있어 새로고침 전에는 어디에도 없었다.

       그래서 집의 처리 표식 지문(rev)이 뒤집힐 때까지 짧게 폴링하고, 뒤집히면 화면을
       조용히 다시 받는다. 성공도 실패도 같은 신호로 잡힌다(워커는 성공 시 last_error 를
       지우고 실패 시 쓴다 — 둘 다 표식 변화다). */

    /** 돌고 있는 폴링을 끊는다(새 조작·완료·마감). */
    function stopWatch() {
        pollToken += 1;
        if (pollTimer !== null) {
            window.clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    /**
     * 불가역 작업의 결과를 기다렸다가 화면을 다시 그린다.
     *
     * @param {string} linkId 조작한 집의 대표 링크 id.
     * @param {string} baseRev POST 응답이 준 **enqueue 직전** 지문.
     * @param {string} label 사람이 읽는 작업 이름(발주확인·발송처리·취소).
     */
    function watchFulfillment(linkId, baseRev, label, baseErrorAt) {
        var id = safeId(linkId);
        if (!id) {
            return;
        }
        stopWatch();
        var mine = pollToken;
        // 시작 시점의 pane 을 기억한다 — 사용자가 다른 집을 열면 이 폴링은 남의 일이 된다.
        var paneAt = paneToken;
        var deadline = Date.now() + POLL_TIMEOUT_MS;
        lockPaneActions();
        setPaneAck(label + ' 요청을 보냈습니다. 네이버 응답을 기다리는 중…');
        pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);

        async function tick() {
            if (mine !== pollToken || paneAt !== paneToken) {
                return;
            }
            const state = await readFulfillmentState(id);
            if (mine !== pollToken || paneAt !== paneToken) {
                return;
            }
            if (state && state.rev && state.rev !== baseRev) {
                stopWatch();
                await softRefresh();
                // 옛 실패가 남아 있는 주문에서 이번 동작을 실패로 말하지 않는다.
                // `baseErrorAt` 를 넘긴 호출(다시 읽기)만 이 비교를 쓴다 —
                // 안 넘긴 기존 호출은 예전과 똑같이 동작한다(2026-08-26 CEO 리뷰 B3).
                var freshError = state.last_error
                    && (baseErrorAt === undefined || state.last_error_at !== baseErrorAt);
                if (freshError) {
                    setPaneAck('네이버 ' + (state.action_label || label) + ' 실패: '
                        + state.last_error, true);
                } else {
                    setPaneAck('네이버 ' + label + ' 완료.');
                }
                return;
            }
            if (Date.now() >= deadline) {
                // 무한 폴링 금지. 지금 시점의 서버 사실로 한 번 맞추고 접는다 — 버튼이
                // 다시 열려도 두 번 나가지 않는다(워커 서비스가 멱등을 지킨다).
                stopWatch();
                await softRefresh();
                setPaneAck(label + ' 결과가 아직 안 왔습니다(네이버 응답 지연). '
                    + '잠시 뒤 목록에서 다시 확인하세요.');
                return;
            }
            pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);
        }
    }

    /**
     * 집의 처리 표식을 읽는다. 일시 오류는 null 로 삼키고 다음 회차에 다시 묻는다 —
     * 마감은 `deadline` 이 쥐고 있어서 여기서 멈추면 오히려 결과를 못 본다.
     */
    async function readFulfillmentState(linkId) {
        try {
            const response = await fetch(STATE_URL + '?link_id=' + linkId, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                return null;
            }
            const data = await response.json();
            return data && data.success ? data.data : null;
        } catch (error) {
            return null;
        }
    }

    /**
     * 응답을 기다리는 동안 불가역 버튼을 잠근다 — 되돌릴 수 없는 호출에서 재클릭은
     * 그 자체가 사고 경로다. 다시 여는 것은 우리가 하지 않는다: 화면을 다시 받으면
     * 서버 판정대로 열린다(잠금 판정 SSOT 는 서버 하나다).
     */
    function lockPaneActions() {
        ['wb-confirm', 'wb-dispatch', 'wb-cancel', 'wb-create'].forEach(function (id) {
            var btn = document.getElementById(id);
            if (btn) {
                btn.disabled = true;
            }
        });
    }

    /**
     * 지금 주소를 다시 받아 `.naver-workbench` 를 통째로 갈아 끼운다.
     *
     * pane 만 갈면 왼쪽 목록 행의 `발주확인 전` 배지·칩 숫자·탭 숫자가 낡은 채 남아
     * 한 화면이 두 말을 한다. 이 파일의 배선은 전부 document 위임(규율 ①)이라 하위
     * 트리를 통째로 바꿔도 죽는 핸들러가 없다 — 그래서 통째 교체가 가능하고,
     * `location.reload()` 와 달리 스크롤·글자 배율·열린 탭을 잃지 않는다.
     *
     * 조각이 아닌 응답(로그인 리다이렉트·오류 페이지)이면 전체 왕복으로 되돌린다.
     */
    async function softRefresh() {
        if (!document.querySelector('.naver-workbench')) {
            window.location.reload();
            return false;
        }
        try {
            const response = await fetch(window.location.href, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const html = await response.text();
            var next = new DOMParser().parseFromString(html, 'text/html')
                .querySelector('.naver-workbench');
            var current = document.querySelector('.naver-workbench');
            if (!next || !current) {
                throw new Error('workbench root missing');
            }
            // 교체 **직전**에 뜬다. 응답을 기다리는 동안 사용자가 더 스크롤했거나
            // 낱말을 더 쳤을 수 있다 — 되돌릴 값은 그 최신 상태여야 한다.
            var find = captureFind();
            var scrollX = window.scrollX;
            var scrollY = window.scrollY;
            teardownModals(current);
            current.replaceWith(next);
            // 교체로 잃는 것만 되돌린다. 목록 밖 판정은 전체 렌더가 서버에서 다시
            // 내려주므로 들고 다니던 값 대신 서버 값을 읽는다(이 쪽이 더 정확하다).
            applyFontScale(readFontScale());
            syncBulk();
            paneOfflist = readOfflistFlag();
            restoreFind(find);
            // 새 목록이 더 짧으면(집 하나가 큐에서 빠지면) 문서가 줄어 브라우저가 스크롤을
            // 위로 당긴다. 훑던 자리를 그대로 돌려준다 — 그게 통째 이동과의 차이다.
            // behavior 를 못박는다 — 전역 CSS 가 나중에 smooth 를 켜면 갱신마다
            // 화면이 미끄러지며 되돌아간다(움직임 자체가 새 통증이 된다).
            window.scrollTo({ left: scrollX, top: scrollY, behavior: 'auto' });
            return true;
        } catch (error) {
            window.location.reload();
            return false;
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
        var ids = [];
        for (const box of chosen) {
            const id = safeId(box.dataset.groupId);
            if (!id) {
                continue;
            }
            ids.push(id);
            const result = await postJson(BASE + id + '/fulfillment', { action: 'confirm' });
            if (!result.ok) {
                failures.push((box.dataset.name || id) + ': ' + result.error);
            }
        }
        if (failures.length) {
            // 사유는 삼키지 않는다. 실패 띠(#wb-result)에도 서버가 다시 남긴다.
            window.alert('실패 ' + failures.length + '주문' + String.fromCharCode(10)
                + failures.join(String.fromCharCode(10)));
        }
        await hideModal(document.getElementById('wb-modal-bulk'));
        // 집마다 폴링하지 않는다 — 조회가 집 수만큼 곱해진다(33집이면 회차마다 66회).
        // 진행 조회는 묶음키로 한 번에 걷어 **집 수와 무관하게 조회 2회**다.
        watchBulk(ids, chosen.length);
    }

    /**
     * 벌크 결과를 기다린다 — 남은 상품주문 건수가 줄어드는 것을 진행으로 보여준다.
     *
     * 워커는 집을 **하나씩** 처리한다. 단건과 같은 25초 창으로는 33집이 끝나기 전에
     * 접히므로 창을 넓히고(90초) 대신 주기를 늘렸다(3초). 조회는 집 수와 무관하게
     * 회차마다 2회다(서버가 묶음키로 한 번에 걷는다).
     *
     * @param {string[]} ids 벌크로 보낸 집들의 대표 링크 id.
     * @param {number} houses 사람이 읽을 집 수(재진술용).
     */
    function watchBulk(ids, houses) {
        if (!ids.length) {
            return;
        }
        stopBulkWatch();
        var mine = bulkToken;
        var deadline = Date.now() + BULK_POLL_TIMEOUT_MS;
        var base = null;                 // 첫 회차에서 잡는 '보내기 전 남은 건수'
        setBulkNote(houses + '주문에 발주확인을 보냈습니다. 네이버 응답을 기다리는 중…');
        bulkTimer = window.setTimeout(tick, BULK_POLL_INTERVAL_MS);

        async function tick() {
            if (mine !== bulkToken) {
                return;
            }
            const data = await readBulkProgress(ids);
            if (mine !== bulkToken) {
                return;
            }
            if (data) {
                if (base === null) {
                    base = data.place_pending;
                }
                var done = Math.max(0, base - data.place_pending);
                if (data.place_pending === 0) {
                    stopBulkWatch();
                    await softRefresh();
                    setBulkNote(houses + '주문 발주확인이 끝났습니다'
                        + (data.failed_links ? ' — 실패 ' + data.failed_links
                            + '건은 위 실패 목록을 보세요.' : '.'));
                    return;
                }
                setBulkNote('보내는 중… 상품주문 ' + base + '건 중 ' + done + '건 완료'
                    + (data.failed_links ? ' · 실패 ' + data.failed_links + '건' : ''));
            }
            if (Date.now() >= deadline) {
                // 무한 폴링 금지. 지금 시점의 서버 사실로 한 번 맞추고 접는다.
                stopBulkWatch();
                await softRefresh();
                setBulkNote('아직 처리 중입니다 — 잠시 뒤 목록에서 다시 확인하세요.');
                return;
            }
            bulkTimer = window.setTimeout(tick, BULK_POLL_INTERVAL_MS);
        }
    }

    /** 돌고 있는 벌크 폴링을 끊는다(새 벌크·완료·마감). */
    function stopBulkWatch() {
        bulkToken += 1;
        if (bulkTimer !== null) {
            window.clearTimeout(bulkTimer);
            bulkTimer = null;
        }
    }

    /** 벌크 대상 전체의 남은 건수를 읽는다(일시 오류는 다음 회차에 다시 묻는다). */
    async function readBulkProgress(ids) {
        try {
            const response = await fetch(PROGRESS_URL + '?link_ids=' + ids.join(','), {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                return null;
            }
            const data = await response.json();
            return data && data.success ? data.data : null;
        } catch (error) {
            return null;
        }
    }

    /** 벌크 바 상태 문구 — 문구가 있으면 바는 선택 0 이어도 열린 채 남는다. */
    function setBulkNote(message) {
        var box = document.getElementById('wb-bulk-note');
        if (box) {
            box.textContent = message || '';
        }
        syncBulk();
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
        // 갱신을 여기서 바로 하면 아직 워커 전이라 화면이 그대로다 — 결과가 나올 때까지
        // 기다렸다가 그린다. **모달을 닫기 전에** 시작한다: 닫는 애니메이션(최대 0.6초)
        // 동안 pane 의 불가역 버튼이 열려 있으면 그 틈에 한 번 더 눌린다.
        watchFulfillment(id, result.data && result.data.rev, '발주확인');
        await hideModal(document.getElementById('wb-modal-confirm'));
    }

    /**
     * 다시 읽기 — 이 주문을 네이버에서 최신 상태로 **조회만** 한다(T4).
     *
     * 네이버에 쓰는 것이 없어 확인 모달이 없다. 되돌릴 게 없으므로 두 번 눌러도 조회가
     * 한 번 더 나갈 뿐이다(그래도 응답 전까지는 버튼을 잠가 헛요청을 줄인다).
     * 결과는 워커가 반영하므로 화면은 발주확인·발송처리와 **같은 폴링**을 쓴다 —
     * `_fulfillment_state.rev` 가 `claim_sync.refreshed_at` 까지 지문에 넣는다.
     *
     * @param {HTMLElement} btn 눌린 버튼.
     */
    async function submitRefresh(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/refresh', {});
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        watchFulfillment(id, result.data && result.data.rev, '다시 읽기',
                         result.data && result.data.err_at);
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
        watchFulfillment(id, result.data && result.data.rev, '발송처리');
        await hideModal(document.getElementById('wb-modal-dispatch'));
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
        watchFulfillment(id, result.data && result.data.rev, '취소');
        await hideModal(document.getElementById('wb-modal-cancel'));
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
        //
        // 예전에는 여기서 `location.href` 로 페이지를 통째로 다시 받았다. 큐를 위에서부터
        // 훑는 손이 한 집을 뺄 때마다 맨 위로 튕기고 찾기 낱말·글자 배율까지 잃었다 —
        // "페이지를 다시 받지 않는다"는 v3 규율 밖에 남아 있던 마지막 자리다.
        // 주소에서 선택만 지우고(기록은 쌓지 않는다) 화면 루트만 갈아 끼운다.
        var next = urlWithoutSelection();
        replacePaneState(null, next);
        var refreshed = await softRefresh();
        if (!refreshed) {
            // 부분 갱신이 안 되는 응답(로그인 리다이렉트·오류 페이지)이면 예전 경로로
            // 되돌린다 — 뺀 집이 큐에 남은 것처럼 보이는 채로 끝내지 않는다.
            window.location.href = next;
        }
    }

    /** 붙이기 — 되돌릴 수 있다(/detach). 확인창 한 번으로 끝낸다. */
    /* ── 재결제 정리 (R-3 · 2026-08-25) ──────────────────────────────────
       후보 버튼은 **바로 붙이지 않는다**. 붙이기와 ERP 기존 주문 처리를 한 번에
       커밋해야 반쪽 상태가 안 생기므로, 두 동작을 함께 보여주는 계획 카드를 먼저 연다.
       카드에 실린 숫자는 전부 서버가 렌더한 값이다 — 화면이 다시 세지 않는다.
       네이버로 나가는 호출은 이 흐름에 없다(2026-08-25 결정). */

    /** 관계를 골라 그 후보의 정리 계획 카드를 연다. */
    function openReconcilePlan(btn) {
        var orderId = safeId(btn.dataset.orderId);
        var relation = btn.dataset.relation === 'ADDON' ? 'ADDON' : 'REPAY';
        var card = orderId
            ? document.querySelector('.wb-plan[data-plan-for="' + orderId + '"]')
            : null;
        if (!card) {
            return;
        }
        // 카드는 후보마다 하나다 — 둘이 동시에 열려 있으면 어느 계획을 실행하는지 흐려진다.
        closeAllPlans();
        card.dataset.relation = relation;
        applyPlanRelation(card);
        applyPlanFork(card);
        card.hidden = false;
        card.scrollIntoView({ block: 'nearest' });
    }

    /** 관계(재결제/추가결제)에 해당하는 조각만 남긴다 — 예약금 안내가 관계마다 다르다. */
    function applyPlanRelation(card) {
        if (!card) {
            return;
        }
        var relation = card.dataset.relation === 'ADDON' ? 'ADDON' : 'REPAY';
        Array.prototype.forEach.call(card.querySelectorAll('[data-plan-rel]'), function (el) {
            el.hidden = el.getAttribute('data-plan-rel') !== relation;
        });
    }

    /** 지금 고른 갈래를 돌려준다(기본은 승계). */
    function planFork(card) {
        var picked = card ? card.querySelector('input.wb-fork__pick:checked') : null;
        return picked && picked.value === 'DISCARD' ? 'DISCARD' : 'SUCCEED';
    }

    /** 갈래에 매인 안내만 남긴다(취소 처리는 붙이지 않는다는 사실을 1번 칸이 말한다). */
    function applyPlanFork(card) {
        if (!card) {
            return;
        }
        var fork = planFork(card);
        Array.prototype.forEach.call(card.querySelectorAll('[data-plan-when]'), function (el) {
            el.hidden = el.getAttribute('data-plan-when') !== fork;
        });
    }

    function closeAllPlans() {
        Array.prototype.forEach.call(document.querySelectorAll('.wb-plan'), closePlan);
    }

    /**
     * 계획 카드를 접는다. **실행이 끝난 카드는 접지 않고 새로고침한다** —
     * 붙이기·취소 처리 결과가 목록·상세에 반영돼야 화면이 거짓말을 안 한다.
     */
    function closePlan(card) {
        if (!card) {
            return;
        }
        if (card.dataset.done === '1') {
            window.location.reload();
            return;
        }
        card.hidden = true;
    }

    /** 정리 실행 — 붙이기와 ERP 처리가 서버에서 한 트랜잭션으로 커밋된다. */
    async function submitReconcile(btn) {
        var card = btn.closest('.wb-plan');
        var linkId = safeId(btn.dataset.linkId);
        var orderId = safeId(btn.dataset.orderId);
        if (!card || !linkId || !orderId) {
            return;
        }
        var relation = card.dataset.relation === 'ADDON' ? 'ADDON' : 'REPAY';
        var fork = planFork(card);
        var label = relation === 'ADDON' ? '추가결제' : '재결제';
        var head = fork === 'DISCARD'
            ? '주문 #' + orderId + ' 을 취소 처리합니다(휴지통 — 복구할 수 있습니다).'
                + '\n새 주문은 붙이지 않습니다 — 큐에 남습니다.'
            : '새 주문을 주문 #' + orderId + ' 에 ' + label + ' 로 붙입니다.'
                + '\n주문은 그대로 두고 예약금은 안내만 합니다.';
        if (!window.confirm(head + '\n\n두 동작은 한 번에 저장됩니다 — 하나만 되는 일은 없습니다.')) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + linkId + '/reconcile', {
            order_id: Number(orderId),
            relation: relation,
            fork: fork
        });
        if (!result.ok) {
            // 한 트랜잭션이라 실패는 곧 '아무것도 안 바뀜' 이다 — 그 사실까지 말한다.
            window.alert(result.error + '\n\n붙이기도 ERP 처리도 되지 않았습니다.');
            btn.disabled = false;
            return;
        }
        showPlanResult(card, result.data || {});
    }

    /**
     * 실행 결과를 카드 안에 쓴다. 새로고침으로 바로 넘기지 않는 이유는 **예약금에 넣을
     * 금액** 때문이다 — 시스템이 넣지 않으므로 사람이 그 숫자를 읽고 주문 화면에 옮겨
     * 적어야 한다. 새로고침이 먼저 오면 그 숫자가 사라진다.
     */
    function showPlanResult(card, data) {
        var done = card.querySelector('.wb-plan__done');
        var acts = card.querySelector('.wb-plan__acts');
        if (!done) {
            window.location.reload();
            return;
        }
        card.dataset.done = '1';
        if (acts) {
            acts.hidden = true;
        }
        done.textContent = '';
        var title = document.createElement('div');
        title.className = 'wb-plan__h';
        title.textContent = data.discarded
            ? '✓ 취소 처리 완료 — 주문 #' + data.order_id + ' 이 휴지통으로 갔습니다'
            : '✓ 붙이기 완료 — 주문 #' + data.order_id + ' 에 ' + data.attached + '건';
        done.appendChild(title);

        if (data.deposit) {
            var money = document.createElement('div');
            money.className = 'wb-plan__money';
            var strong = document.createElement('b');
            strong.textContent = '예약금(선금)에 넣을 금액: '
                + Number(data.deposit.target).toLocaleString('ko-KR') + '원';
            money.appendChild(strong);
            var note = document.createElement('div');
            note.className = 'wb-plan__d';
            note.textContent = data.deposit.sentence + ' 시스템이 넣지 않습니다.';
            money.appendChild(note);
            done.appendChild(money);
        }
        if (data.edit_url && !data.discarded) {
            var link = document.createElement('a');
            link.className = 'btn btn-sm btn-outline-primary';
            link.href = data.edit_url;
            link.target = '_blank';
            link.rel = 'noopener';
            link.textContent = '주문 #' + data.order_id + ' 열어서 넣기 ↗';
            done.appendChild(link);
        } else if (data.discarded) {
            var hint = document.createElement('div');
            hint.className = 'wb-plan__d';
            hint.textContent = '새 주문은 큐에 그대로 있습니다 — 이제 주문 만들기를 누르세요.';
            done.appendChild(hint);
        }
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'btn btn-sm btn-outline-secondary wb-plan-close ms-2';
        close.textContent = '닫기';
        done.appendChild(close);
        done.hidden = false;
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
            window.alert('다시 시도했지만 ' + stillFailing.length + '주문이 또 실패했습니다.'
                + String.fromCharCode(10) + stillFailing.join(String.fromCharCode(10)));
        }
        // 재시도도 큐에 들어간다 — 바로 갱신하면 옛 실패 띠를 다시 그린다. 벌크와 같은
        // 규칙으로 한 번만 늦게 받는다(집마다 폴링하지 않는다).
        var note = document.getElementById('wb-retry-note');
        if (note) {
            note.textContent = pairs.length + '주문을 다시 보냈습니다. 결과를 기다리는 중…';
        }
        window.setTimeout(function () { softRefresh(); }, BULK_REFRESH_MS);
    }

    /**
     * 지금 수집 — 큐에 넣고 **워커가 한 바퀴 돌 때까지 지켜본다**.
     *
     * 네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 한도 3). 예전에는 큐에 넣은 뒤
     * "잠시 뒤 새로고침하면 이력에 나타납니다"로 끝냈다 — 사용자가 F5 를 누르기 전까지
     * 화면은 영원히 그대로였고, 돌고 있는지 실패했는지 알 길이 없었다.
     * 이제 수집 워터마크 지문(rev)이 뒤집히는 것만 보고, 뒤집히면 화면을 조용히 다시 받는다.
     */
    async function submitRunNow(btn) {
        btn.disabled = true;
        setRunNote('작업 큐에 넣는 중…');
        const result = await postJson('/admin/naver-ingest/run', {});
        if (!result.ok) {
            // 워커가 하나도 없으면 서버가 503 + 사유를 준다. 넣지도 못했으니 기다릴 결과가
            // 없다 — 폴링하지 않고 사유를 그대로 띄우고 버튼을 다시 연다.
            setRunNote(result.error);
            enableRunNow();
            return;
        }
        var rev = result.data && result.data.rev;
        if (!rev) {
            // 기준 지문이 없으면 무엇이 바뀌었는지 판정할 수 없다. 없는 기준으로 90초를
            // 도는 대신 예전 안내로 정직하게 끝낸다(폴링을 흉내 내지 않는다).
            setRunNote('수집 작업을 큐에 넣었습니다. 잠시 뒤 새로고침하면 결과가 이력에 나타납니다.');
            enableRunNow();
            return;
        }
        watchRun(rev);
    }

    /**
     * 수집 결과를 기다렸다가 화면을 다시 그린다.
     *
     * 성공도 실패도 같은 신호로 잡힌다 — 워커는 성공하면 요약을, 실패하면 사유를 남기고
     * 둘 다 워터마크 지문을 바꾼다.
     *
     * @param {string} baseRev POST 응답이 준 **큐에 넣기 직전** 워터마크 지문.
     */
    function watchRun(baseRev) {
        stopRunWatch();
        var mine = runToken;
        var deadline = Date.now() + RUN_POLL_TIMEOUT_MS;
        setRunNote('수집 작업을 큐에 넣었습니다. 워커 결과를 기다리는 중…');
        runTimer = window.setTimeout(tick, RUN_POLL_INTERVAL_MS);

        async function tick() {
            if (mine !== runToken) {
                return;
            }
            const state = await readRunState();
            if (mine !== runToken) {
                return;
            }
            if (state && state.rev && state.rev !== baseRev) {
                stopRunWatch();
                // 갱신을 **먼저** 한다: softRefresh 가 `#wb-run-result` 를 서버가 준 빈
                // 칸으로 갈아 끼우므로, 문구를 먼저 쓰면 그 자리에서 지워진다.
                await softRefresh();
                setRunNote(state.last_error
                    ? '수집 실패: ' + state.last_error
                    // 지문은 **전역** 워터마크다 — 5분 주기 자동 스윕이 이 창 안에 끝나면
                    // 그 결과로 뒤집힌다. 그래서 "당신이 누른 그 수집이 끝났다"고 말하지
                    // 않는다. 화면이 말할 수 있는 사실은 "상태가 갱신됐고 지금 값은 이것"뿐이다.
                    : '수집 상태가 갱신되었습니다 — '
                        + (state.last_summary || '결과 요약이 비어 있습니다.'));
                return;
            }
            if (Date.now() >= deadline) {
                // 무한 폴링 금지. 지문이 그대로면 새로 그릴 것도 없다 — 문구만 남기고
                // 버튼을 다시 연다(수집은 워터마크로 이어 받아 두 번 돌아도 겹치지 않는다).
                stopRunWatch();
                setRunNote('아직 처리 중입니다 — 잠시 뒤 다시 확인하세요.');
                enableRunNow();
                return;
            }
            runTimer = window.setTimeout(tick, RUN_POLL_INTERVAL_MS);
        }
    }

    /** 돌고 있는 수집 폴링을 끊는다(새 수집·완료·마감). */
    function stopRunWatch() {
        runToken += 1;
        if (runTimer !== null) {
            window.clearTimeout(runTimer);
            runTimer = null;
        }
    }

    /**
     * 수집 워터마크를 읽는다(읽기 전용 경로). 일시 오류는 null 로 삼키고 다음 회차에
     * 다시 묻는다 — 마감은 `deadline` 이 쥐고 있어서 여기서 멈추면 결과를 못 본다.
     */
    async function readRunState() {
        try {
            const response = await fetch(RUN_STATE_URL, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                return null;
            }
            const data = await response.json();
            return data && data.success ? data.data : null;
        } catch (error) {
            return null;
        }
    }

    /**
     * 수집 안내 문구를 쓴다. 요소는 **쓸 때마다 다시 찾는다** — softRefresh 가 화면
     * 루트를 갈면 들고 있던 요소는 문서 밖이라, 거기 쓴 글자는 아무 데도 안 보인다.
     * @param {string} message 사람이 읽는 문장.
     */
    function setRunNote(message) {
        setText('wb-run-result', message || '');
    }

    /** 수집 버튼을 다시 연다 — 갱신을 거치지 않은 끝맺음에서만 필요하다
        (갱신을 거치면 서버가 준 새 버튼이 이미 열려 있다). */
    function enableRunNow() {
        var btn = document.getElementById('wb-run-now');
        if (btn) {
            btn.disabled = false;
        }
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
