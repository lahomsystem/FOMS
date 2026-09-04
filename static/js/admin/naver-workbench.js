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
    /** 전체 다시 읽기 진행 조회(집 수와 무관하게 서버 조회 1회). */
    var REFRESH_PROGRESS_URL = '/admin/naver-ingest/triage/refresh-progress';
    var REFRESH_RUNNING_URL = '/admin/naver-ingest/triage/refresh-running';
    /** 운영 실측 2026-08-30: 58집 62초. 캡 200집이면 그 3배 남짓이라 창을 여유 있게. */
    var REFRESH_POLL_INTERVAL_MS = 3000;
    var REFRESH_POLL_TIMEOUT_MS = 300000;

    /** 소급 수집(백필) 실행·진행 경로. 실행은 큐에 넣기만 한다(HTTP 는 WORKER). */
    var BACKFILL_URL = '/admin/naver-ingest/backfill';
    var BACKFILL_STATE_URL = '/admin/naver-ingest/backfill-state';
    /** 백필은 하루 창을 순서대로 훑는다 — 90일이면 몇 분이라 창을 아주 넓게 잡는다. */
    var BACKFILL_POLL_INTERVAL_MS = 5000;
    var BACKFILL_POLL_TIMEOUT_MS = 900000;

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
    /** 전체 다시 읽기 폴링 토큰·타이머(벌크·단건과 따로 둔다 — 서로를 끊으면 안 된다). */
    var refreshAllToken = 0;
    var refreshAllTimer = null;
    // 남이 눌러 놓은 다시 읽기를 따라가는 폴링(NVREPAY-05 T1) — 자기 요청 폴링과 별개 축이다.
    var refreshRunningToken = 0;
    var refreshRunningTimer = null;

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
        'wb-return-confirm': submitReturn,
        'wb-reject-confirm': submitReturnReject,
        'wb-cancel-approve-confirm': submitCancelApprove,
        'wb-return-approve-confirm': submitReturnApprove,
        'wb-reject-save': saveRejectTemplate,
        'wb-review-done': submitReviewDone,
        'wb-refresh': submitRefresh,
        'wb-detach': submitDetach,
        'wb-bulk-confirm': submitBulk,
        'wb-bulk-clear': clearPicks,
        'wb-retry-failed': submitRetry,
        'wb-run-now': submitRunNow,
        'wb-backfill-run': submitBackfill,
        'wb-expiry-edit': toggleExpiryEdit,
        'wb-ghost-discard': submitGhostDiscard,
        'wb-origin-refresh-all': submitOriginRefreshAll,
        'wb-origin-cancel-confirm': submitOriginCancel,
        'wb-origin-return-confirm': submitOriginReturn,
        'wb-refresh-all': submitRefreshAll,
        'wb-seek-run': submitSeek
    };

    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    // 검색칸에서 Enter 는 찾기와 같은 일이다 — 누르는 사람은 버튼을 안 찾는다.
    document.addEventListener('keydown', onKeydown);
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
        // 서버가 "남이 돌리는 중" 이라 그렸으면 여기서도 따라간다 — 끝나면 스스로 새로 그린다.
        syncRefreshRunning();
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
    /**
     * **수집된 집 전부**를 네이버에서 다시 읽는다 (NVREPAY-03).
     *
     * 되돌릴 것은 없지만(조회만) 한 번에 수십 집의 호출이 나가고 새로 발견된 취소·반품은
     * 알림으로 나가므로, 몇 집인지 말하고 한 번 묻는다. 단건 `다시 읽기` 가 모달을 두지
     * 않는 것과 다른 이유는 **되돌림이 아니라 규모**다.
     *
     * 결과는 새로고침으로 확인한다 — 워커가 읽고 나면 목록의 상태·금액이 바뀌므로 조각
     * 교체보다 전체 렌더가 정직하다.
     *
     * @param {HTMLElement} button 눌린 버튼(집 수를 물고 있다).
     * @returns {Promise<void>}
     */
    async function submitRefreshAll(button) {
        var count = safeId(button.dataset.count) || '';
        // 걸리는 시간은 **서버가 만든 값**을 그대로 옮긴다 — 툴팁·모달·진행 라벨이 같은
        // 말을 해야 한다(여기서 다시 계산하면 같은 화면이 두 말을 하는 자리가 된다).
        var eta = (button.dataset.eta || '').trim();
        var message = '아직 변할 수 있는 ' + (count || '전체') + '개 주문을 네이버에서 다시 읽습니다.\n'
            + (eta ? eta + ' 걸립니다. 끝나면 화면이 스스로 새로 그려집니다.\n' : '')
            + '조회만 하며 네이버에는 아무것도 보내지 않습니다.\n'
            + '취소·반품이 처음 발견되면 담당자·관리자에게 알림이 갑니다.';
        if (!window.confirm(message)) {
            return;
        }
        button.disabled = true;
        var label = button.textContent;
        const result = await postJson(BASE + 'refresh-all', {});
        if (!result.ok) {
            window.alert(result.error);
            button.disabled = false;
            button.textContent = label;
            return;
        }
        var data = result.data || {};
        var queued = data.queued || 0;
        if (!queued) {
            button.textContent = skipNote(data) || '다시 읽을 주문 없음';
            return;
        }
        button.textContent = '다시 읽는 중 — ' + queued + '주문';
        watchRefreshAll(data);
    }

    /**
     * 대상에서 뺀 집을 사람이 읽는 한 마디로 만든다.
     *
     * **조용히 줄이지 않는다** — "전체"라 적고 덜 읽으면 그게 거짓말이다. 뺀 이유가
     * 둘(종결·쿨다운)이라 각각 이름을 준다.
     *
     * @param {object} data refresh-all 응답의 data.
     * @returns {string} 뺀 게 없으면 빈 문자열.
     */
    function skipNote(data) {
        var parts = [];
        if (data.skipped_done) {
            parts.push('끝난 주문 ' + data.skipped_done + '건');
        }
        if (data.skipped_recent) {
            parts.push('방금 읽은 주문 ' + data.skipped_recent + '건');
        }
        return parts.length ? parts.join(' · ') + ' 제외' : '';
    }

    /**
     * 전체 다시 읽기가 끝나는 것을 기다렸다가 **화면을 스스로 새로 그린다**.
     *
     * 왜: 예전에는 라벨을 `다시 읽는 중 … (끝나면 새로고침)` 으로 바꿔 두고 끝났는지는
     * 아무도 말하지 않았다. 사람은 그걸 멈춘 걸로 읽는다 — 운영 2026-08-30 에 28초
     * 간격으로 두 번 눌렸고 두 번째는 통째로 낭비였다.
     *
     * 배선은 벌크 발주확인(:func:`watchBulk`)과 **같은 모양**이다. 서버 조회는 집 수와
     * 무관하게 회차당 1회이고, 마감이 있다(무한 폴링 금지).
     *
     * @param {object} data refresh-all 응답의 data(`link_ids` 대신 `queued`·`since`).
     * @returns {void}
     */
    function watchRefreshAll(data) {
        var button = document.getElementById('wb-refresh-all');
        var ids = data.link_ids || [];
        if (!ids.length || !data.since) {
            return;
        }
        stopRefreshAllWatch();
        var mine = refreshAllToken;
        var deadline = Date.now() + REFRESH_POLL_TIMEOUT_MS;
        refreshAllTimer = window.setTimeout(tick, REFRESH_POLL_INTERVAL_MS);

        async function tick() {
            if (mine !== refreshAllToken) {
                return;
            }
            const progress = await readRefreshProgress(ids, data.since);
            if (mine !== refreshAllToken) {
                return;
            }
            if (progress) {
                if (!progress.pending) {
                    stopRefreshAllWatch();
                    await softRefresh();
                    return;
                }
                if (button) {
                    button.textContent = '다시 읽는 중 — ' + progress.total + '주문 중 '
                        + progress.done + '주문 완료';
                }
            }
            if (Date.now() >= deadline) {
                // 무한 폴링 금지. 지금 시점의 서버 사실로 한 번 맞추고 접는다.
                stopRefreshAllWatch();
                await softRefresh();
                return;
            }
            refreshAllTimer = window.setTimeout(tick, REFRESH_POLL_INTERVAL_MS);
        }
    }

    /**
     * **남이 눌러 놓은** 전체 다시 읽기를 이 화면에서도 따라간다 (NVREPAY-05 T1).
     *
     * 왜: :func:`watchRefreshAll` 은 자기가 방금 큐에 넣은 링크 id 를 들고 있어야 돈다.
     * 그래서 진행 표시가 누른 브라우저 안에만 있었고, 다른 관리자에게는 돌고 있는 중에도
     * `다시 읽기 45주문` 이라 적혀 있었다 — 그래서 또 누른다.
     *
     * 서버가 띠를 그렸을 때만 돈다(`#wb-refresh-all-running`). 끝나면 화면을 스스로 새로
     * 그린다 — 그 순간이 버튼이 돌아오는 순간이다. 조회는 회차당 1회, 마감이 있다.
     *
     * @returns {void}
     */
    function syncRefreshRunning() {
        stopRefreshRunningWatch();
        if (!document.getElementById('wb-refresh-all-running')) {
            return;
        }
        var mine = refreshRunningToken;
        var deadline = Date.now() + REFRESH_POLL_TIMEOUT_MS;
        refreshRunningTimer = window.setTimeout(tick, REFRESH_POLL_INTERVAL_MS);

        async function tick() {
            if (mine !== refreshRunningToken) {
                return;
            }
            const state = await readRefreshRunning();
            if (mine !== refreshRunningToken) {
                return;
            }
            if (state && !state.running) {
                // 끝났다 — 남의 요청이라도 결과는 이 화면의 목록에 그대로 들어온다.
                stopRefreshRunningWatch();
                await softRefresh();
                return;
            }
            var chip = document.getElementById('wb-refresh-all-running');
            if (state && chip) {
                chip.innerHTML = '';
                chip.appendChild(document.createTextNode(
                    '다시 읽는 중 — ' + state.total + '주문 중 ' + state.done + '주문 완료 · '
                    + (state.actor || '다른 관리자') + ' 시작'));
            }
            if (Date.now() >= deadline) {
                // 무한 폴링 금지. 서버 창(5분)과 같은 마감이라 여기서 접어도 띠는 사라진다.
                stopRefreshRunningWatch();
                await softRefresh();
                return;
            }
            refreshRunningTimer = window.setTimeout(tick, REFRESH_POLL_INTERVAL_MS);
        }
    }

    /** 남의 다시 읽기 진행을 읽는다(일시 오류는 다음 회차에 다시 묻는다). */
    async function readRefreshRunning() {
        try {
            const response = await fetch(REFRESH_RUNNING_URL, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                return null;
            }
            const payload = await response.json();
            return payload && payload.success ? (payload.data || null) : null;
        } catch (error) {
            return null;
        }
    }

    /** 남의 다시 읽기 폴링을 끊는다(완료·마감·화면 교체). */
    function stopRefreshRunningWatch() {
        refreshRunningToken += 1;
        if (refreshRunningTimer !== null) {
            window.clearTimeout(refreshRunningTimer);
            refreshRunningTimer = null;
        }
    }

    /** 돌고 있는 전체 다시 읽기 폴링을 끊는다(완료·마감·다시 누름). */
    function stopRefreshAllWatch() {
        refreshAllToken += 1;
        if (refreshAllTimer !== null) {
            window.clearTimeout(refreshAllTimer);
            refreshAllTimer = null;
        }
    }

    /** 전체 다시 읽기 진행을 읽는다(일시 오류는 다음 회차에 다시 묻는다). */
    async function readRefreshProgress(ids, since) {
        try {
            const response = await fetch(REFRESH_PROGRESS_URL + '?link_ids=' + ids.join(',')
                + '&since=' + encodeURIComponent(since), {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) {
                return null;
            }
            const payload = await response.json();
            return payload && payload.success ? payload.data : null;
        } catch (error) {
            return null;
        }
    }

    /**
     * 정리 대기 중인 **옛 주문 전부**를 네이버에서 다시 읽는다 (NVREPAY-02).
     *
     * 확인 모달을 두지 않는다 — 나가는 호출이 상세 조회뿐이라 되돌릴 것이 없다(단건
     * `다시 읽기` 와 같은 규율). 대신 **대상을 여기서 고르지 않는다**: 서버가 정리 대기
     * 집을 다시 세어 그 집들만 큐에 넣는다.
     *
     * 결과는 새로고침으로 확인한다 — 워커가 읽고 나면 이 띠의 건수 자체가 바뀌므로
     * 조각 교체보다 전체 렌더가 정직하다. 큐에 넣은 직후에는 아직 옛 값이라 **바로
     * 새로고침하지 않고** 무엇을 기다리는지 말한다.
     *
     * @param {HTMLElement} button 눌린 버튼.
     * @returns {Promise<void>}
     */
    async function submitOriginRefreshAll(button) {
        button.disabled = true;
        const result = await postJson(BASE + 'origin-cleanup/refresh', {});
        if (!result.ok) {
            window.alert(result.error);
            button.disabled = false;
            return;
        }
        var queued = (result.data && result.data.queued) || 0;
        button.textContent = queued
            ? '다시 읽는 중 — ' + queued + '집 (끝나면 새로고침)'
            : '다시 읽을 집 없음';
    }

    function submitGhostDiscard(button) {
        var orderId = safeId(button.dataset.orderId);
        if (!orderId) {
            return;
        }
        var who = button.dataset.customer || '';
        var stage = button.dataset.stage || '';
        var message = '주문 #' + orderId + (who ? ' (' + who + ')' : '')
            + ' 을 휴지통으로 보냅니다. 복구할 수 있습니다.';
        var note = '';
        if (button.dataset.needsReason) {
            // 접수 이후 단계는 실측 방문·치수 같은 기록이 함께 화면에서 사라진다. 그래서
            // 확인창이 아니라 **사유 입력**을 받는다 — 서버도 같은 조건으로 막는다(관리자 + 사유).
            note = window.prompt([
                message,
                '',
                (stage ? stage + ' 단계라 ' : '') + '실측·도면 기록도 함께 화면에서 사라집니다.',
                '왜 접는지 한 줄 적어 주세요.'
            ].join('\n'), '');
            if (note === null) {
                return;
            }
            note = String(note).trim();
            if (!note) {
                window.alert('사유를 적어야 접을 수 있습니다.');
                return;
            }
        } else if (!window.confirm(message)) {
            return;
        }
        button.disabled = true;
        postJson(BASE + 'ghost/' + orderId + '/discard', { reason: note }).then(function (result) {
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
            // 찾은 주문에 붙이는 버튼(T2). 결과 줄 수만큼 나오므로 id 가 아니라
            // 클래스로 문다(절대 규칙 1).
            if (btn.classList.contains('wb-seek-attach')) {
                submitSeekAttach(btn);
                return;
            }
            // 거부 상용구 채우기(T8-S3). 문장 수만큼 나오므로 클래스로 문다(절대 규칙 1).
            // **채워 넣기만 한다** — 넣은 뒤 그 자리에서 고칠 수 있어야 자유 입력이다.
            if (btn.classList.contains('wb-reject-fill')) {
                fillRejectReason(btn.dataset.text || '');
                return;
            }
            // 목록에서 지우기(관리자만 보인다). 지우면 **모두에게** 적용된다.
            if (btn.classList.contains('wb-reject-drop')) {
                dropRejectTemplate(btn.dataset.label || '');
                return;
            }
            if (btn.classList.contains('wb-plan-close')) {
                closePlan(btn.closest('.wb-plan'));
                return;
            }
            // 옛 주문이 여럿일 수 있어 id 를 달면 문서에 중복이 생긴다(절대 규칙 1).
            if (btn.classList.contains('wb-origin-open')) {
                openOrigin(btn);
                return;
            }
            // 띠에서 바로 쏘는 불가역(2026-09-01). 줄마다 나오므로 클래스로 문다.
            if (btn.classList.contains('wb-origin-act')) {
                openOriginAct(btn);
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
        // 승인 체크를 켜면 빨간 띠가 한 줄 더 말한다 — 접수보다 무겁다(환불이 나간다).
        // 위임으로 붙이는 이유: 이 모달은 pane 프래그먼트라 교체될 때마다 다시 그려진다.
        if (target.id === 'wb-return-approve') {
            var warn = document.getElementById('wb-return-approve-warn');
            if (warn) {
                warn.hidden = !target.checked;
            }
            return;
        }
        // 띠 모달의 같은 체크. pane 과 id 를 나눠 둔 이유는 두 모달이 한 문서에 함께
        // 살아서다 — 같은 id 면 어느 쪽 경고를 켜는지 갈린다.
        if (target.id === 'wb-origin-return-approve') {
            var originWarn = document.getElementById('wb-origin-return-approve-warn');
            if (originWarn) {
                originWarn.hidden = !target.checked;
            }
            return;
        }
        // 갈래(승계/취소 처리)를 바꾸면 1번 칸의 안내 문장이 달라진다 — 취소 처리는 붙이지
        // 않기 때문이다. 계획과 실제 동작이 어긋난 채로 실행 버튼을 누르는 자리를 막는다.
        if (target.classList.contains('wb-fork__pick')) {
            applyPlanFork(target.closest('.wb-plan'));
            return;
        }
        // 만료일은 **고르는 순간 저장**한다 — 저장 버튼을 따로 두면 상태 카드가 폼이 된다.
        if (target.id === 'wb-expiry-input') {
            submitExpiry(target);
        }
    }

    /**
     * 목록 안 찾기 — **처리 탭 전용**이다. 지금 화면에 있는 줄만 즉시 좁힌다.
     *
     * 서버로 보내지 않는 이유: 처리 탭 목록은 이미 한 번에 다 와 있고(캡 500집),
     * 왕복을 넣으면 한 글자마다 조회가 나간다. 대신 **범위를 화면에 못 박는다** —
     * 확인 완료로 큐에서 빠진 집은 목록에 없으므로 여기서도 안 나온다.
     *
     * 이력 탭은 반대다(2026-09-02): 서버가 쪽수로 자른 목록이라 화면 필터가 닿는 데가
     * 지금 쪽 50집뿐이었고, 16쪽짜리 이력에서 이름을 쳐도 0주문이 나왔다. 그래서 그 탭의
     * 찾기 칸은 GET 폼이고 서버가 좁힌다 — 여기서는 손대지 않는다.
     *
     * 정렬은 반대로 서버가 한다: 캡보다 먼저 돌아야 캡이 자를 집이 달라진다.
     */
    function onInput(event) {
        if (!event.target) {
            return;
        }
        // 거부 사유는 **보낼 문장을 그대로 되읽어 준다**. 입력칸을 보고 있으면서도 오타를
        // 못 보는 자리라, 보낼 값을 한 번 더 따로 보여 준다(불가역 4종 세트의 재진술).
        if (event.target.id === 'wb-reject-reason') {
            syncRejectEcho();
            return;
        }
        if (event.target.id !== 'wb-find') {
            return;
        }
        if (isHistoryTab()) {
            // 이력 탭 찾기는 서버가 한다(폼 제출). 여기서 행을 숨기면 서버가 준 결과 위에
            // 화면 필터가 한 겹 더 얹혀, 서버 note 가 말하는 숫자와 보이는 줄이 갈린다.
            return;
        }
        applyFind(event.target.value);
    }

    /**
     * 붙일 주문 검색칸에서 Enter — 찾기 버튼과 같은 일을 한다.
     *
     * `#wb-find`(목록 안 찾기)와 **다른 칸**이다. 그쪽은 입력할 때마다 화면에서 걸러내고
     * 서버로 나가지 않는다. 이쪽은 서버 조회라 사람이 끝냈다고 말할 때만 나간다.
     */
    function onKeydown(event) {
        if (!event.target || event.target.id !== 'wb-seek-q' || event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        var run = document.getElementById('wb-seek-run');
        if (run) {
            submitSeek(run);
        }
    }

    /** 지금 열린 탭이 이력인가 — 찾기 주체가 갈리는 유일한 분기다. */
    function isHistoryTab() {
        var root = document.querySelector('.naver-workbench');
        return !!root && root.dataset.activeTab === 'all';
    }

    /**
     * 찾기 낱말로 행을 숨기고 결과 수를 고지한다.
     *
     * 모집단은 처리 탭의 집 줄이다. 셀렉터에 이력 표 행이 남아 있는 이유는 서버 렌더가
     * 실패해 이력 탭에 옛 마크업이 오더라도 같은 규칙으로 동작하게 두기 위해서다 —
     * 정상 경로에서는 :func:`onInput` 이 이력 탭을 먼저 걸러 여기까지 오지 않는다.
     * @param {string} raw 사용자가 친 문자열.
     */
    function applyFind(raw) {
        var needle = String(raw || '').trim().toLowerCase();
        var rows = Array.prototype.slice.call(
            document.querySelectorAll('#wb-queue a.wb-row, table.wb-hist tbody tr[data-find]'));
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
            note.textContent = needle ? (shown + '주문 / ' + rows.length + '주문') : '';
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
                // **모든 호출이 누르기 직전의 실패 시각을 넘긴다**(2026-09-04). 예전에는
                // `다시 읽기` 하나만 넘기고 나머지 여섯 갈래는 폴백으로 옛 동작을 남겼는데,
                // 그 유예 때문에 취소 승인이 **성공한** 직후 화면이 옛 취소 실패를
                // "네이버 취소 실패"라고 다시 말했다(사용자 2차 신고).
                var freshError = state.last_error
                    && state.last_error_at !== (baseErrorAt || '');
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
            // 새로 받은 화면에 진행 띠가 있으면 폴링을 다시 건다(교체로 끊긴다).
            syncRefreshRunning();
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
        watchFulfillment(id, result.data && result.data.rev, '발주확인',
                         result.data && result.data.err_at);
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
     * 옛 주문을 **다시 읽고** 그 집 화면으로 간다 (NVREPAY-01).
     *
     * 새 결제를 받은 뒤로 그 옛 주문을 한 번도 안 읽은 경우에만 이 버튼이 나온다. 그
     * 구간이 "고객이 스스로 취소했는데 우리가 또 취소를 거는" 위험이 사는 자리라, 사람이
     * 불가역 버튼 앞에 서기 전에 최신 값을 한 번 가져온다. `다시 읽기` 는 읽기 전용이라
     * 되돌릴 것이 없다.
     *
     * 큐가 막혀 있어도 **이동은 막지 않는다** — 옛 주문 화면 자체는 봐야 하고, 그 화면이
     * 마지막으로 읽은 시각을 그대로 말해 준다. 대신 왜 못 읽었는지는 알린다.
     *
     * @param {HTMLElement} btn 링크 id 와 이동 주소를 물고 있는 버튼.
     * @returns {Promise<void>}
     */
    async function openOrigin(btn) {
        var id = safeId(btn.dataset.linkId);
        var url = btn.dataset.paneUrl;
        if (!id || !url) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/refresh', {});
        if (!result.ok) {
            window.alert('다시 읽기를 넣지 못했습니다: ' + result.error
                         + '\n옛 주문 화면은 그대로 엽니다 — 화면이 말하는 조회 시각을 보세요.');
        }
        window.location.href = url;
    }

    /**
     * 재결제 옛 주문 — 띠에서 바로 쏘기 전 단계 (2026-09-01 사용자 결정).
     *
     * **낡은 줄은 모달을 열지 않는다.** `stale` 은 "새 결제를 받은 뒤로 이 옛 주문을 한
     * 번도 안 읽었다"는 뜻이라, 그 사이 고객이 스스로 취소했을 수 있다. 낡은 값 위에서
     * 되돌릴 수 없는 호출을 쏘는 것이 이 띠가 원래 막던 사고다 — 대신 다시 읽기를 큐에
     * 넣고 무엇을 기다리는지 말한다(즉시 반영이 아니라 워커가 읽는다).
     *
     * 모달 문장은 **눌린 줄에서 그대로 옮겨 적는다**. 재진술이지 대상 지정이 아니다 —
     * 처리할 집은 서버가 `link_id` 로 다시 계산한다.
     *
     * @param {HTMLElement} btn 눌린 줄의 실행 버튼.
     * @returns {Promise<void>}
     */
    async function openOriginAct(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var isReturn = btn.dataset.kind === 'return';
        if (btn.dataset.stale === '1') {
            btn.disabled = true;
            const refreshed = await postJson(BASE + id + '/refresh', {});
            btn.textContent = refreshed.ok
                ? '다시 읽는 중 — 끝나면 새로고침하고 누르세요'
                : '다시 읽기 실패 — ' + refreshed.error;
            return;
        }
        var who = (btn.dataset.orderNo || '')
            + ' · 상품주문 ' + (btn.dataset.count || '0') + '건'
            + ' · ' + (btn.dataset.amount || '0') + '원';
        if (btn.dataset.customer) {
            who += ' (' + btn.dataset.customer + ')';
        }
        var whoBox = document.getElementById(isReturn
            ? 'wb-origin-return-who' : 'wb-origin-cancel-who');
        if (whoBox) {
            whoBox.textContent = who;
        }
        // 분할 발송 집은 **나간 건만** 나간다(서버 `is_return_pending`). 위 줄의 '상품주문
        // N건' 만 두면 그 수가 그대로 약속으로 읽히는데, 서버는 그보다 적게 보낸다 —
        // 되돌릴 수 없는 경로의 과대 진술이다. 전부 나간 집에서는 이 줄을 숨긴다.
        if (isReturn) {
            var scope = document.getElementById('wb-origin-return-scope');
            if (scope) {
                var total = parseInt(btn.dataset.count, 10) || 0;
                var sendable = parseInt(btn.dataset.returnCount, 10) || 0;
                scope.hidden = !(total && sendable < total);
                scope.textContent = scope.hidden ? '' : ('이 집은 상품주문 ' + total
                    + '건인데 발송된 ' + sendable + '건만 나갑니다 — 아직 안 나간 물건은 '
                    + '반품이 아니라 취소입니다.');
            }
        }
        var confirmBtn = document.getElementById(isReturn
            ? 'wb-origin-return-confirm' : 'wb-origin-cancel-confirm');
        if (confirmBtn) {
            confirmBtn.dataset.linkId = String(id);
            confirmBtn.disabled = false;
        }
        // **입력을 비운다.** 모달 하나를 여러 줄이 돌려 쓰므로, 안 비우면 앞 줄에서 고른
        // 사유가 다음 줄에 그대로 실린다 — 되돌릴 수 없는 호출에 남의 사유가 붙는다.
        resetOriginActForm(isReturn);
        var modal = document.getElementById(isReturn
            ? 'wb-modal-origin-return' : 'wb-modal-origin-cancel');
        var instance = modalInstance(modal, true);
        if (instance) {
            instance.show();
        }
    }

    /**
     * 띠 모달의 입력을 처음 상태로 되돌린다.
     *
     * 모달은 문서에 하나뿐인데 띠 줄은 여럿이다 — 비우지 않으면 앞 줄에서 고른 사유·상세·
     * 승인 체크가 다음 줄로 따라간다. 승인 체크가 따라가는 것이 특히 나쁘다(환불이 확정되고
     * 무를 API 가 없다). 그래서 **열 때마다** 비운다.
     *
     * @param {boolean} isReturn 반품 모달이면 참.
     */
    function resetOriginActForm(isReturn) {
        var reason = document.getElementById(isReturn
            ? 'wb-origin-return-reason' : 'wb-origin-cancel-reason');
        if (reason) {
            reason.value = '';
        }
        var detail = document.getElementById(isReturn
            ? 'wb-origin-return-detail' : 'wb-origin-cancel-detail');
        if (detail) {
            detail.value = '';
        }
        if (!isReturn) {
            return;
        }
        var approve = document.getElementById('wb-origin-return-approve');
        if (approve) {
            approve.checked = false;
        }
        var warn = document.getElementById('wb-origin-return-approve-warn');
        if (warn) {
            warn.hidden = true;
        }
    }

    /**
     * 띠에서 옛 주문 **취소**를 큐에 넣는다.
     *
     * pane 의 `submitCancel` 과 같은 라우트·같은 payload 다. 다른 것은 결과를 말하는
     * 자리뿐이다 — 띠에는 pane 이 없어 `watchFulfillment` 를 걸 자리가 없다. 그래서
     * 무엇을 기다리는지 버튼이 직접 말하고, 확인은 새로고침으로 한다
     * (`전부 다시 읽기` 와 같은 규율).
     *
     * @param {HTMLElement} btn 모달의 확인 버튼.
     * @returns {Promise<void>}
     */
    async function submitOriginCancel(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var reasonEl = document.getElementById('wb-origin-cancel-reason');
        if (!reasonEl || !reasonEl.value) {
            window.alert('취소 사유를 고르세요.');
            return;
        }
        var detailEl = document.getElementById('wb-origin-cancel-detail');
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
        await hideModal(document.getElementById('wb-modal-origin-cancel'));
        markOriginActQueued(id, '취소');
        watchOriginAct(id, result.data && result.data.rev, '취소');
    }

    /**
     * 띠에서 옛 주문 **반품 접수**를 큐에 넣는다. 승인 체크는 pane 과 같은 뜻이다 —
     * 켜면 환불이 확정되고 되돌리는 엔드포인트가 없다. 화면 값을 믿지 않는 것은 라우트
     * 몫이고(문자열 "false" 정규화), 여기서는 불리언으로만 보낸다.
     *
     * @param {HTMLElement} btn 모달의 확인 버튼.
     * @returns {Promise<void>}
     */
    async function submitOriginReturn(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var reasonEl = document.getElementById('wb-origin-return-reason');
        if (!reasonEl || !reasonEl.value) {
            window.alert('반품 사유를 고르세요.');
            return;
        }
        var detailEl = document.getElementById('wb-origin-return-detail');
        var approveEl = document.getElementById('wb-origin-return-approve');
        var approve = !!(approveEl && approveEl.checked);
        btn.disabled = true;
        const result = await postJson(BASE + id + '/return', {
            reason: reasonEl.value,
            detail: detailEl ? detailEl.value : '',
            approve: approve
        });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        await hideModal(document.getElementById('wb-modal-origin-return'));
        var label = approve ? '반품 접수+승인' : '반품 접수';
        markOriginActQueued(id, label);
        watchOriginAct(id, result.data && result.data.rev, label);
    }

    /**
     * 띠에서 쏜 불가역의 **결과**를 그 줄이 말하게 한다 (2026-09-01).
     *
     * pane 의 :func:`watchFulfillment` 를 재사용하지 않는다 — 그것은 pane 에 묶여 있어
     * (`lockPaneActions`·`setPaneAck`·`softRefresh`) 띠에서 부르면 **지금 열려 있는 다른
     * 집**의 화면을 잠그고 남의 자리에 결과를 쓴다.
     *
     * 이게 없으면 워커가 거절해도 줄은 "보냄"으로 남는다 — 안 나간 것을 나갔다고 말하는
     * 자리다. 지문(`rev`)이 바뀌면 실패 여부를 그 자리에서 말하고, 오래 걸리면 무한히
     * 돌지 않고 접으면서 **새로고침으로 확인하라**고 말한다(거짓 완료를 만들지 않는다).
     *
     * @param {number} linkId 처리한 링크 id.
     * @param {string} baseRev enqueue 직전 지문(라우트가 준 값).
     * @param {string} label 사람이 읽는 동작 이름.
     */
    function watchOriginAct(linkId, baseRev, label) {
        var id = safeId(linkId);
        if (!id) {
            return;
        }
        var deadline = Date.now() + POLL_TIMEOUT_MS;
        window.setTimeout(tick, POLL_INTERVAL_MS);

        async function tick() {
            var btn = document.querySelector('.wb-origin-act[data-link-id="' + id + '"]');
            if (!btn) {
                return;
            }
            const state = await readFulfillmentState(id);
            if (state && state.rev && state.rev !== baseRev) {
                btn.textContent = state.last_error
                    ? label + ' 실패 — ' + state.last_error
                    : label + ' 완료 — 새로고침하면 이 줄이 사라집니다';
                btn.classList.toggle('wb-origin-act--err', !!state.last_error);
                return;
            }
            if (Date.now() >= deadline) {
                btn.textContent = label + ' 결과가 아직 안 왔습니다 — 새로고침해서 확인하세요';
                return;
            }
            window.setTimeout(tick, POLL_INTERVAL_MS);
        }
    }

    /**
     * 큐에 넣은 줄이 그 사실을 말하게 한다 — 두 번 누르는 자리를 막는다.
     *
     * 띠 자체를 다시 그리지 않는 이유는 `전부 다시 읽기` 와 같다: 워커가 읽기 전에는
     * 아직 옛 값이라, 지금 새로 그리면 화면이 "아직 살아 있다"고 다시 말한다.
     *
     * @param {number} linkId 처리한 링크 id.
     * @param {string} label 사람이 읽는 동작 이름.
     */
    function markOriginActQueued(linkId, label) {
        var btn = document.querySelector('.wb-origin-act[data-link-id="' + linkId + '"]');
        if (!btn) {
            return;
        }
        btn.disabled = true;
        btn.textContent = label + ' 보냄 — 끝나면 새로고침';
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
        watchFulfillment(id, result.data && result.data.rev, '발송처리',
                         result.data && result.data.err_at);
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
        watchFulfillment(id, result.data && result.data.rev, '취소',
                         result.data && result.data.err_at);
        await hideModal(document.getElementById('wb-modal-cancel'));
    }

    /**
     * 판매자 반품 접수 — 취소의 거울이다. 사유 목록이 다르고(RETURN_REASONS), 회수 방법은
     * 화면이 고르지 않는다(서버 상수 한 값). 서버가 사유를 다시 검사한다.
     */
    async function submitReturn(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var reasonEl = document.getElementById('wb-return-reason');
        var detailEl = document.getElementById('wb-return-detail');
        if (!reasonEl || !reasonEl.value) {
            window.alert('반품 사유를 고르세요.');
            return;
        }
        // 승인까지 한 번에 (T8-S2). 체크박스가 없으면 **끈 것으로 본다** — 환불이 나가는
        // 갈래라 "모르면 안 켠다"가 안전한 기본값이다.
        var approveEl = document.getElementById('wb-return-approve');
        var approve = !!(approveEl && approveEl.checked);
        btn.disabled = true;
        const result = await postJson(BASE + id + '/return', {
            reason: reasonEl.value,
            detail: detailEl ? detailEl.value : '',
            approve: approve
        });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        watchFulfillment(id, result.data && result.data.rev,
                         approve ? '반품 접수+승인' : '반품 접수',
                         result.data && result.data.err_at);
        await hideModal(document.getElementById('wb-modal-return'));
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
        // 접수 이후 단계를 접을 때만 나오는 칸이다(서버도 같은 조건으로 요구한다).
        var reasonInput = card.querySelector('.wb-plan-reason');
        var reason = reasonInput ? String(reasonInput.value || '').trim() : '';
        if (fork === 'DISCARD' && reasonInput && !reason) {
            window.alert('왜 접는지 한 줄 적어 주세요 — 접수 이후 단계라 실측·도면 기록이 '
                + '함께 화면에서 사라집니다.');
            reasonInput.focus();
            return;
        }
        // 관계를 잘못 고르면 예약금 안내가 '바꾸기'/'더하기' 로 갈려 고객 청구액이
        // 틀어진다 — 저장 직전에 **어느 관계인지**를 가장 먼저 다시 말한다(2026-09-04).
        var head = fork === 'DISCARD'
            ? '주문 #' + orderId + ' 을 휴지통으로 보냅니다(복구할 수 있습니다).'
                + '\n새 주문은 붙이지 않습니다 — 큐에 그대로 남습니다.'
            : '이 건을 [' + label + '] 로 정리합니다.'
                + '\n새 결제를 주문 #' + orderId + ' 에 붙이고, 주문은 그대로 둡니다.'
                + '\n예약금은 안내만 합니다 — 정리한 뒤 주문 화면에서 직접 적어야 합니다.';
        if (!window.confirm(head + '\n\n두 동작은 한 번에 저장됩니다 — 하나만 되는 일은 없습니다.')) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + linkId + '/reconcile', {
            order_id: Number(orderId),
            relation: relation,
            fork: fork,
            reason: reason
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

    /* ── 반품 거부 (T8-S3) ───────────────────────────────────────────── */

    /**
     * 상용구를 입력칸에 **넣기만** 한다. 넣은 뒤 고칠 수 있어야 자유 입력이다
     * (사용자 결정 2026-08-31 — 고정 문구 강제가 아니다).
     */
    function fillRejectReason(text) {
        var box = document.getElementById('wb-reject-reason');
        if (!box || !text) {
            return;
        }
        box.value = text;
        box.focus();
        syncRejectEcho();
    }

    /** 보낼 문장을 그대로 되읽어 준다(빈 값이면 줄 자체를 내지 않는다). */
    function syncRejectEcho() {
        var box = document.getElementById('wb-reject-reason');
        var echo = document.getElementById('wb-reject-echo');
        if (!box || !echo) {
            return;
        }
        var text = String(box.value || '').trim();
        echo.textContent = text ? '보낼 문장: “' + text + '”' : '';
        echo.hidden = !text;
    }

    /** 지금 화면에 그려진 상용구 목록을 그대로 읽는다(마크업이 정본이다). */
    function readRejectTemplates() {
        var box = document.getElementById('wb-reject-fills');
        if (!box) {
            return [];
        }
        return Array.prototype.map.call(
            box.querySelectorAll('.wb-reject-fill'),
            function (el) {
                return { label: el.dataset.label || '', text: el.dataset.text || '' };
            });
    }

    /**
     * 목록을 다시 그린다. 저장 응답이 정본이라 그것으로 갈아 끼운다 — 화면에서 만든
     * 목록을 그대로 두면 서버가 거른 항목(빈 문장·길이 초과)이 화면에만 남는다.
     */
    function renderRejectTemplates(templates, version) {
        var box = document.getElementById('wb-reject-fills');
        if (!box) {
            return;
        }
        var canManage = !!box.dataset.canManage;
        Array.prototype.forEach.call(box.querySelectorAll('.wb-reject__chip'),
                                     function (el) { el.remove(); });
        (templates || []).forEach(function (item) {
            var chip = document.createElement('span');
            chip.className = 'wb-reject__chip';
            var pick = document.createElement('button');
            pick.type = 'button';
            pick.className = 'btn btn-sm btn-outline-secondary wb-reject-fill';
            pick.dataset.text = item.text || '';
            pick.dataset.label = item.label || '';
            pick.textContent = item.label || '';
            chip.appendChild(pick);
            if (canManage) {
                var drop = document.createElement('button');
                drop.type = 'button';
                drop.className = 'btn btn-sm btn-link wb-reject-drop';
                drop.dataset.label = item.label || '';
                drop.title = '이 문장을 목록에서 지웁니다(모두에게 적용)';
                drop.textContent = '×';
                chip.appendChild(drop);
            }
            box.appendChild(chip);
        });
        if (version !== undefined && version !== null) {
            box.dataset.version = String(version);
        }
    }

    /**
     * 목록 전체를 저장한다 — 항목 단위 병합이 아니라 **통째로 덮어쓴다**(삭제를
     * 표현할 수 있는 유일한 방법이다). 버전이 어긋나면 서버가 409 로 막는다.
     */
    async function postRejectTemplates(templates) {
        var box = document.getElementById('wb-reject-fills');
        var version = box ? Number(box.dataset.version || 0) : 0;
        const result = await postJson(BASE + 'reject-templates', {
            templates: templates,
            version: version
        });
        if (!result.ok) {
            window.alert(result.error);
            return false;
        }
        renderRejectTemplates(result.data && result.data.templates,
                              result.data && result.data.version);
        return true;
    }

    /** 지금 쓴 문장을 이름을 달아 목록에 넣는다(같은 이름이면 덮어쓴다). */
    async function saveRejectTemplate(btn) {
        var reason = document.getElementById('wb-reject-reason');
        var name = document.getElementById('wb-reject-name');
        var text = reason ? String(reason.value || '').trim() : '';
        var label = name ? String(name.value || '').trim() : '';
        if (!text) {
            window.alert('저장할 문장을 먼저 쓰세요.');
            return;
        }
        if (!label) {
            window.alert('이름을 넣으세요 — 버튼에 보일 짧은 말입니다(예: 제작 착수).');
            if (name) {
                name.focus();
            }
            return;
        }
        var next = readRejectTemplates().filter(function (item) {
            return item.label !== label;
        });
        next.push({ label: label, text: text });
        btn.disabled = true;
        var ok = await postRejectTemplates(next);
        btn.disabled = false;
        if (ok && name) {
            name.value = '';
        }
    }

    /** 목록에서 문장 하나를 뺀다 — **모두에게** 적용되므로 한 번 묻는다. */
    async function dropRejectTemplate(label) {
        if (!label) {
            return;
        }
        var next = readRejectTemplates().filter(function (item) {
            return item.label !== label;
        });
        if (!next.length) {
            window.alert('마지막 문장은 지울 수 없습니다 — 목록이 비면 기본 문장이 다시 보입니다.');
            return;
        }
        if (!window.confirm('“' + label + '” 문장을 목록에서 지웁니다.\n\n모든 담당자 화면에서 사라집니다.')) {
            return;
        }
        await postRejectTemplates(next);
    }

    /**
     * 반품 거부 — **고객이 낸 요청**을 되돌려보낸다. 접수와 다른 라우트다.
     *
     * 사유는 코드가 아니라 문장이고 **구매자에게 그대로 간다**. 빈 문장은 여기서 막고
     * 서버가 한 번 더 막는다(빈 요청으로 불가역 API 를 때리지 않는다).
     */
    async function submitReturnReject(btn) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var box = document.getElementById('wb-reject-reason');
        var text = box ? String(box.value || '').trim() : '';
        if (!text) {
            window.alert('거부 사유 문장을 입력하세요 — 구매자에게 그대로 전달됩니다.');
            if (box) {
                box.focus();
            }
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + id + '/return-reject', { reason: text });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        watchFulfillment(id, result.data && result.data.rev, '반품 거부',
                         result.data && result.data.err_at);
        await hideModal(document.getElementById('wb-modal-return-reject'));
    }


    /**
     * 구매자가 낸 취소 요청을 **승인**한다 (T9-G1).
     *
     * 거부와 같은 모양이되 보낼 본문이 없다 — 네이버 규격이 path 파라미터만 받는다.
     * 그래서 입력 검증도 없고, 확인은 모달의 목록 재진술과 경고가 맡는다.
     *
     * **되돌릴 수 없다.** 승인 시점에 환불이 확정되고, 취소를 거절하는 API 는 없다.
     *
     * @param {HTMLElement} btn 확인 버튼(`data-link-id`).
     */
    async function submitCancelApprove(btn) {
        await submitClaimApprove(btn, 'cancel');
    }

    /**
     * 고객이 낸 반품 요청을 **승인**한다 — 접수와 분리된 독립 경로 (T9-G2).
     *
     * @param {HTMLElement} btn 확인 버튼(`data-link-id`).
     */
    async function submitReturnApprove(btn) {
        await submitClaimApprove(btn, 'return');
    }

    /**
     * 승인 2종의 공통 몸통 — 라우트·라벨·모달 id 만 다르다 (T9).
     *
     * 한 벌로 두는 이유는 서버 라우트와 같다: 갈래를 복사하면 `watchFulfillment` 로
     * 결과를 지켜보는 자리나 실패 시 버튼을 되살리는 자리가 한쪽에서만 조용히 낡는다.
     *
     * @param {HTMLElement} btn 확인 버튼(`data-link-id`).
     * @param {string} kind `'cancel'` 또는 `'return'`.
     */
    async function submitClaimApprove(btn, kind) {
        var id = safeId(btn.dataset.linkId);
        if (!id) {
            return;
        }
        var isCancel = kind === 'cancel';
        var path = isCancel ? '/cancel-approve' : '/return-approve';
        var label = isCancel ? '취소 승인' : '반품 승인';
        var modalId = isCancel ? 'wb-modal-cancel-approve' : 'wb-modal-return-approve';
        btn.disabled = true;
        const result = await postJson(BASE + id + path, {});
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        watchFulfillment(id, result.data && result.data.rev, label,
                         result.data && result.data.err_at);
        await hideModal(document.getElementById(modalId));
    }

    /* ── 주문 찾아서 붙이기 (T2) ─────────────────────────────────────── */

    /**
     * 검색 경합 토큰. 낱말을 고쳐 다시 찾으면 앞 요청이 아직 돌고 있다 — 늦게 온 결과가
     * 새 결과를 덮으면 화면이 지금 친 낱말과 다른 목록을 보여주고, 그 목록에서 누른
     * 붙이기는 담당자가 의도하지 않은 주문으로 나간다.
     */
    var seekToken = 0;

    /**
     * 이름·전화·주문번호로 붙일 주문을 찾는다(읽기 전용 GET).
     *
     * 서버가 그린 조각을 그대로 꽂는다. JS 로 표를 다시 지으면 판정 근거 열(옛 결제
     * 상태·금액 견주기)이 후보 표와 두 벌이 되고, 같은 판단을 하는 두 표가 서로 다른
     * 말을 하게 된다.
     */
    async function submitSeek(btn) {
        var id = safeId(btn.dataset.linkId);
        var input = document.getElementById('wb-seek-q');
        var box = document.getElementById('wb-seek-result');
        if (!id || !input || !box) {
            return;
        }
        var token = ++seekToken;
        box.setAttribute('aria-busy', 'true');
        box.innerHTML = '<p class="wb-seek__msg">찾는 중…</p>';
        try {
            const response = await fetch(
                BASE + id + '/order-search?q=' + encodeURIComponent(String(input.value || '')),
                { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const html = await response.text();
            if (token !== seekToken) {
                return;   // 늦게 온 응답 — 새 검색을 덮지 않는다.
            }
            box.innerHTML = html;
        } catch (error) {
            if (token !== seekToken) {
                return;
            }
            // 조용히 비우지 않는다 — 빈 결과는 "그런 주문이 없다"로 읽힌다.
            box.innerHTML = '<p class="wb-seek__msg wb-seek__msg--err">찾지 못했습니다'
                + '(연결 오류). 잠시 뒤 다시 눌러 주세요.</p>';
        } finally {
            if (token === seekToken) {
                box.setAttribute('aria-busy', 'false');
            }
        }
    }

    /**
     * 찾은 주문에 붙인다 — **기존 `/attach` 라우트 그대로**다.
     *
     * 후보 표의 `정리 실행`(붙이기 + ERP 처리 한 트랜잭션)이 아니다. `/reconcile` 은
     * 후보 목록 안 주문만 받고, 그 목록 밖을 받게 만들면 취소 처리(휴지통) 갈래가
     * 범용 삭제 경로가 된다. 여기서 하는 일은 **되돌릴 수 있는 붙이기 하나**다.
     */
    async function submitSeekAttach(btn) {
        var linkId = safeId(btn.dataset.linkId);
        var orderId = safeId(btn.dataset.orderId);
        if (!linkId || !orderId) {
            return;
        }
        var relation = btn.dataset.relation === 'ADDON' ? 'ADDON' : 'REPAY';
        var label = relation === 'ADDON' ? '추가결제' : '재결제';
        var who = btn.dataset.customer ? ' (' + btn.dataset.customer + ')' : '';
        if (!window.confirm('이 집을 주문 #' + orderId + who + ' 에 ' + label + ' 로 붙입니다.'
                + '\n\n새 주문을 만들지 않습니다. 되돌릴 수 있습니다.')) {
            return;
        }
        btn.disabled = true;
        const result = await postJson(BASE + linkId + '/attach', {
            order_id: Number(orderId),
            relation: relation
        });
        if (!result.ok) {
            window.alert(result.error);
            btn.disabled = false;
            return;
        }
        showSeekResult(result.data || {}, label, btn.dataset.deposit || '');
    }

    /**
     * 붙인 결과를 그 자리에 쓴다. 새로고침으로 바로 넘기지 않는 이유는 **예약금에 넣을
     * 금액** 때문이다 — 시스템이 넣지 않으므로(D-1) 사람이 그 숫자를 읽고 주문 화면에
     * 옮겨 적어야 하는데, 새로고침이 먼저 오면 그 숫자가 사라진다(정리 계획 카드와 같은 규율).
     */
    function showSeekResult(data, label, depositSentence) {
        var done = document.getElementById('wb-seek-done');
        var box = document.getElementById('wb-seek-result');
        if (!done) {
            window.location.reload();
            return;
        }
        if (box) {
            box.innerHTML = '';   // 붙인 뒤에는 같은 목록에서 또 누르지 못하게 한다.
        }
        done.textContent = '';
        var title = document.createElement('div');
        title.className = 'wb-plan__h';
        title.textContent = '✓ 붙이기 완료 — 주문 #' + data.order_id + ' 에 '
            + data.attached + '건 (' + label + ')';
        done.appendChild(title);

        if (depositSentence) {
            var money = document.createElement('div');
            money.className = 'wb-plan__money';
            var strong = document.createElement('b');
            strong.textContent = '예약금(선금): ' + depositSentence;
            money.appendChild(strong);
            var note = document.createElement('div');
            note.className = 'wb-plan__d';
            note.textContent = '시스템이 넣지 않습니다 — 주문 화면에서 사람이 입력합니다.';
            money.appendChild(note);
            done.appendChild(money);
        }
        if (data.edit_url) {
            var link = document.createElement('a');
            link.className = 'btn btn-sm btn-outline-primary';
            link.href = data.edit_url;
            link.target = '_blank';
            link.rel = 'noopener';
            link.textContent = '주문 #' + data.order_id + ' 열어서 넣기 ↗';
            done.appendChild(link);
        }
        var hint = document.createElement('div');
        hint.className = 'wb-plan__d';
        hint.textContent = '잘못 붙였으면 화면을 새로 고친 뒤 관계 줄의 되돌리기를 누르세요.';
        done.appendChild(hint);
        done.hidden = false;
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
     * 과거 주문 소급 수집(백필) — 구간을 보내고 **끝날 때까지 지켜본다**.
     *
     * 워터마크는 앞으로만 가므로 첫 수집 이전 주문은 원본이 아예 없다. 이 버튼이 그
     * 구멍을 메우는 유일한 길이다. 실행은 큐에 넣기만 하고 네이버 HTTP 는 WORKER 가 낸다.
     *
     * 끝을 말하지 않으면 사람은 멈춘 줄 알고 다시 누른다(전체 다시 읽기에서 이미 겪었다).
     * 그래서 진행 상태를 폴링해 창 진척을 그대로 보여준다.
     *
     * @param {HTMLElement} btn 눌린 버튼.
     */
    async function submitBackfill(btn) {
        var from = document.getElementById('wb-backfill-from');
        var to = document.getElementById('wb-backfill-to');
        var fromValue = from ? String(from.value || '') : '';
        var toValue = to ? String(to.value || '') : '';
        if (!fromValue || !toValue) {
            setBackfillNote('시작일과 종료일을 모두 골라 주세요.');
            return;
        }
        btn.disabled = true;
        setBackfillNote('작업 큐에 넣는 중…');
        const result = await postJson(BACKFILL_URL, { from: fromValue, to: toValue });
        if (!result.ok) {
            // 구간 오류·워커 없음·큐 장애 — 넣지 못했으니 기다릴 결과가 없다.
            setBackfillNote(result.error);
            enableBackfill();
            return;
        }
        watchBackfill(String((result.data && result.data.rev) || ''));
    }

    /**
     * 소급 수집 진행을 지켜본다. 끝나면 화면을 다시 받는다.
     *
     * @param {string} baseRev 큐에 넣기 직전 상태 지문(바뀌면 워커가 손댔다는 뜻).
     */
    function watchBackfill(baseRev) {
        var deadline = Date.now() + BACKFILL_POLL_TIMEOUT_MS;
        setBackfillNote('과거 구간을 긁는 중입니다. 하루씩 훑기 때문에 몇 분 걸립니다…');
        window.setTimeout(tick, BACKFILL_POLL_INTERVAL_MS);

        async function tick() {
            const state = await readBackfillState();
            if (state && !state.running && String(state.rev || '') !== baseRev) {
                var summary = state.last_summary || {};
                // 갱신을 **먼저** 한다 — softRefresh 가 문구 칸을 서버가 준 빈 칸으로 간다.
                await softRefresh();
                if (state.last_error) {
                    setBackfillNote('소급 수집이 중간에 멈췄습니다: ' + state.last_error
                        + ' (' + (state.done_through || '시작 지점') + ' 까지는 남아 있습니다)');
                } else {
                    setBackfillNote('소급 수집 완료 — 새로 받은 주문 '
                        + (summary.collected || 0) + '건 · 이미 있던 것 '
                        + (summary.skipped || 0) + '건 · 보류 '
                        + (summary.pending_review || 0) + '건. '
                        + '붙이기는 처리 탭 후보 화면에서 사람이 고릅니다.');
                }
                enableBackfill();
                return;
            }
            if (state && state.running) {
                setBackfillNote('과거 구간을 긁는 중입니다 — '
                    + (state.done_through ? state.done_through.slice(0, 10) + ' 까지 마쳤습니다.'
                        : '첫 구간을 훑는 중입니다.'));
            }
            if (Date.now() >= deadline) {
                setBackfillNote('아직 돌고 있습니다 — 잠시 뒤 새로고침해서 결과를 확인하세요.');
                enableBackfill();
                return;
            }
            window.setTimeout(tick, BACKFILL_POLL_INTERVAL_MS);
        }
    }

    /** 소급 수집 진행 상태를 읽는다(실패하면 null — 폴링이 죽지 않게). */
    async function readBackfillState() {
        try {
            const response = await fetch(BACKFILL_STATE_URL, {
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

    /** 소급 수집 안내 문구. */
    function setBackfillNote(message) {
        setText('wb-backfill-note', message || '');
    }

    /** 소급 수집 버튼을 다시 연다(갱신을 거치지 않은 끝맺음에서 필요). */
    function enableBackfill() {
        var btn = document.getElementById('wb-backfill-run');
        if (btn) {
            btn.disabled = false;
        }
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
    /**
     * 만료일 칸을 펼치고 달력을 연다 — 등록면은 이 버튼 하나뿐이다.
     *
     * `showPicker()` 가 있으면 클릭 한 번으로 달력까지 뜬다(크롬·엣지). 없으면
     * 포커스만 준다 — 그 브라우저에서도 칸을 눌러 고르면 그만이다.
     *
     * @param {HTMLElement} btn 눌린 `수정`(또는 `등록`) 버튼.
     */
    function toggleExpiryEdit(btn) {
        var input = document.getElementById('wb-expiry-input');
        if (!input) {
            return;
        }
        var opening = input.classList.contains('d-none');
        input.classList.toggle('d-none', !opening);
        btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
        if (!opening) {
            return;
        }
        input.focus();
        if (typeof input.showPicker === 'function') {
            try {
                input.showPicker();
            } catch (error) {
                /* 사용자 제스처 밖 호출은 브라우저가 막는다 — 포커스만으로 충분하다. */
            }
        }
    }

    /**
     * 커머스API 인증 만료일 저장 — 날짜를 **고르는 순간** 나간다.
     *
     * 저장하면 카드 문구(남은 일수·D-7 경고)가 서버 판정으로 바뀌어야 하므로 **부분
     * 갱신**으로 다시 그린다. 통째 이동은 하지 않는다(찾기 낱말·글자 배율·스크롤을 잃는다).
     *
     * @param {HTMLInputElement} input 날짜 칸.
     */
    async function submitExpiry(input) {
        var value = String(input.value || '').trim();
        if (!value) {
            return;
        }
        input.disabled = true;
        setExpiryNote('저장하는 중…');
        const result = await postJson('/admin/naver-ingest/app-expiry', { expires_on: value });
        if (!result.ok) {
            setExpiryNote(result.error);
            input.disabled = false;
            return;
        }
        // 문구는 **갱신 뒤에** 쓴다: softRefresh 가 이 칸을 서버가 준 것으로 갈아 끼우므로
        // 먼저 쓰면 그 자리에서 지워진다(지금 수집 버튼과 같은 순서 함정).
        await softRefresh();
        setExpiryNote('만료일을 ' + result.data.expires_on + ' 로 저장했습니다'
            + (result.data.days_left === null ? '.' : ' (' + result.data.days_left + '일 남음).'));
    }

    /** 만료일 칸 안내 문구. */
    function setExpiryNote(message) {
        setText('wb-expiry-note', message || '');
    }

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
