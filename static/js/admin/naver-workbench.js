/* 네이버 수집 워크벤치 — 화면 스크립트.
 *
 * 탭 전환은 서버 라운드트립(?tab=)이라 JS 가 없다. 여기 있는 건 불가역 액션 하나뿐이다.
 * CSRF 는 공용 레이아웃의 fetch 래퍼가 붙인다.
 */
(function () {
    'use strict';

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
})();
