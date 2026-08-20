/* 네이버 수집 워크벤치 — 화면 스크립트.
 *
 * 탭 전환은 서버 라운드트립(?tab=)이라 JS 가 없다. 여기 있는 건 불가역 액션 하나뿐이다.
 * CSRF 는 공용 레이아웃의 fetch 래퍼가 붙인다.
 */
(function () {
    'use strict';

    wireCreateOrder();
    wirePlaceOrder();

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
