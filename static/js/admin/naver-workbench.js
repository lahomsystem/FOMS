/* 네이버 수집 워크벤치 — 화면 스크립트.
 *
 * 탭 전환은 서버 라운드트립(?tab=)이라 JS 가 없다. 여기 있는 건 불가역 액션 하나뿐이다.
 * CSRF 는 공용 레이아웃의 fetch 래퍼가 붙인다.
 */
(function () {
    'use strict';

    wireCreateOrder();
    wirePlaceOrder();
    wireClaimDone();
    wireRetryFailed();
    wireDispatch();

    /* ── 처리 대기 탭: 발송처리 ────────────────────────────────────────
       네이버에 "물건이 나갔다"를 알린다. 되돌릴 수 없어 모달을 거치고, 실제 호출은
       WORKER 가 낸다(web 은 큐에 넣기만 한다 — 커머스API 호출 IP 제약). */
    function wireDispatch() {
        var confirmBtn = document.getElementById('wb-dispatch-confirm');
        if (!confirmBtn) {
            return;
        }
        confirmBtn.addEventListener('click', async function () {
            var linkId = confirmBtn.dataset.linkId;
            if (!linkId) {
                return;
            }
            // 두 번 눌러 두 번 나가는 걸 막는다(멱등은 워커도 지키지만 화면에서 먼저 막는다).
            confirmBtn.disabled = true;
            try {
                const response = await fetch('/admin/naver-ingest/' + linkId + '/fulfillment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'dispatch' })
                });
                const data = await response.json();
                if (!data.success) {
                    window.alert(data.error || '발송처리 요청에 실패했습니다.');
                    confirmBtn.disabled = false;
                    return;
                }
                window.location.reload();
            } catch (error) {
                window.alert('요청 중 오류가 발생했습니다: ' + error);
                confirmBtn.disabled = false;
            }
        });
    }

    /* ── 결과 띠: 실패한 집만 다시 시도 (결정 7 의 ④단계) ──────────────
       성공한 집은 서버가 목록에 넣지 않았으므로 여기 없다 — 재시도가 성공분을
       건드릴 수 없다. */
    function wireRetryFailed() {
        var retryBtn = document.getElementById('wb-retry-failed');
        if (!retryBtn) {
            return;
        }
        retryBtn.addEventListener('click', async function () {
            // `<링크 id>:<작업>` 쌍이다. 실패한 그 작업으로 다시 보낸다 — 전부 발주확인으로
            // 보내면 발송처리 실패는 멱등 규칙에 걸려 조용히 넘어가고 띠만 영원히 남는다.
            var pairs = (retryBtn.dataset.linkIds || '').split(',').filter(Boolean)
                .map(function (chunk) {
                    var parts = chunk.split(':');
                    return { id: parts[0], action: parts[1] === 'dispatch' ? 'dispatch' : 'confirm' };
                });
            if (!pairs.length) {
                return;
            }
            retryBtn.disabled = true;
            var stillFailing = [];
            for (const pair of pairs) {
                try {
                    const response = await fetch('/admin/naver-ingest/' + pair.id + '/fulfillment', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action: pair.action })
                    });
                    const data = await response.json();
                    if (!data.success) {
                        stillFailing.push(data.error || '실패');
                    }
                } catch (error) {
                    stillFailing.push(String(error));
                }
            }
            if (stillFailing.length) {
                window.alert('다시 시도했지만 ' + stillFailing.length + '집이 또 실패했습니다.\n'
                    + stillFailing.join('\n'));
            }
            window.location.reload();
        });
    }

    /* ── 취소·반품 탭: 큐에서 빼기 ───────────────────────────────────────
       네이버 쪽에는 아무 영향이 없다 — 우리 큐에서만 사라진다. 그래서 확인 모달을
       두지 않는다(불가역이 아닌 일에 모달을 달면 진짜 불가역 경고가 값을 잃는다). */
    function wireClaimDone() {
        var doneBtn = document.getElementById('wb-claim-done');
        if (!doneBtn) {
            return;
        }
        doneBtn.addEventListener('click', async function () {
            // 묶음 전체를 처리한다 — 형제 한 건이 남으면 같은 집이 큐에 다시 뜬다.
            var ids = (doneBtn.dataset.linkIds || '').split(',').filter(Boolean);
            if (!ids.length) {
                return;
            }
            doneBtn.disabled = true;
            for (const id of ids) {
                try {
                    const response = await fetch('/admin/naver-ingest/' + id + '/review', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}'
                    });
                    const data = await response.json();
                    if (!data.success) {
                        window.alert(data.error || '확인 처리에 실패했습니다.');
                        doneBtn.disabled = false;
                        return;
                    }
                } catch (error) {
                    window.alert('요청 중 오류가 발생했습니다: ' + error);
                    doneBtn.disabled = false;
                    return;
                }
            }
            window.location.href = '/admin/naver-ingest/triage?tab=claim';
        });
    }

    /* ── 발주확인 전 탭: 선택 개수 ↔ 버튼 상태 ↔ 모달 문장 ─────────────── */
    function wirePlaceOrder() {
        var submit = document.getElementById('wb-place-submit');
        if (!submit) {
            return;
        }
        var picks = Array.prototype.slice.call(document.querySelectorAll('.wb-pick'));
        var pickAll = document.getElementById('wb-pick-all');
        var nSpan = document.getElementById('wb-place-n');
        var countSpan = document.getElementById('wb-place-count');
        var namesSpan = document.getElementById('wb-place-names');
        var confirmBtn = document.getElementById('wb-place-confirm');

        function selected() {
            return picks.filter(function (c) { return c.checked; });
        }

        function sync() {
            var chosen = selected();
            // 버튼 라벨과 모달 문장이 같은 숫자를 말해야 한다 — 한쪽만 갱신하면
            // 사람이 몇 건을 보내는지 모르는 채로 불가역 호출을 누른다.
            nSpan.textContent = chosen.length;
            countSpan.textContent = chosen.length;
            namesSpan.textContent = chosen.map(function (c) { return c.dataset.name; }).join(', ');
            submit.disabled = chosen.length === 0;
        }

        picks.forEach(function (c) { c.addEventListener('change', sync); });
        if (pickAll) {
            pickAll.addEventListener('change', function () {
                var on = this.checked;
                picks.forEach(function (c) { c.checked = on; });
                sync();
            });
        }
        sync();

        confirmBtn.addEventListener('click', async function () {
            var chosen = selected();
            if (!chosen.length) {
                return;
            }
            confirmBtn.disabled = true;
            var failures = [];
            for (const box of chosen) {
                try {
                    const response = await fetch(
                        '/admin/naver-ingest/' + box.dataset.linkId + '/fulfillment', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'confirm' })
                        });
                    const data = await response.json();
                    if (!data.success) {
                        failures.push(box.dataset.name + ': ' + (data.error || '실패'));
                    }
                } catch (error) {
                    failures.push(box.dataset.name + ': ' + error);
                }
            }
            if (failures.length) {
                // W5 에서 결과 띠로 옮긴다. 그때까지도 사유는 삼키지 않는다.
                window.alert('실패 ' + failures.length + '집\n' + failures.join('\n'));
            }
            window.location.reload();
        });
    }

    /* ── 처리 대기 탭: 주문 만들기 ────────────────────────────────────── */
    function wireCreateOrder() {
        var createBtn = document.getElementById('wb-create-order');
        if (!createBtn) {
            return;
    }

        createBtn.addEventListener('click', async function () {
            var linkId = createBtn.dataset.linkId;
            if (!linkId) {
                return;
            }
            // 두 번 눌러 주문이 두 개 생기는 걸 막는다 — 불가역 액션이다.
            createBtn.disabled = true;
            try {
                const response = await fetch('/admin/naver-ingest/' + linkId + '/create-order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
                const data = await response.json();
                if (!data.success) {
                    window.alert(data.error || '주문 생성에 실패했습니다.');
                    createBtn.disabled = false;
                    return;
                }
                // 편집기는 새 탭으로 연다 — 워크벤치 자리를 잃지 않아야 다음 집으로 넘어간다.
                if (data.data && data.data.edit_url) {
                    window.open(data.data.edit_url, '_blank', 'noopener');
                }
                window.location.reload();
            } catch (error) {
                window.alert('요청 중 오류가 발생했습니다: ' + error);
                createBtn.disabled = false;
            }
        });
    }
})();
