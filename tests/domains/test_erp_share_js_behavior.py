"""고객 공유 링크 창(erp-share.js)을 Node 로 실제로 돌려 공유 종류 동그라미를 본다(2026-11-08 점검 ui-pc 4).

모바일 v2 코호트 주문 화면은 PC·휴대폰 조각을 둘 다 싣고 한쪽을 지운다. 같은 name 동그라미가
문서에 두 벌 들어오는 순간 뒤 벌의 checked 가 앞 벌을 풀어, PC 에 남은 창은 "도면 / 견적서"
둘 다 빈 채로 열렸다. 창을 열 때 아무것도 안 골라져 있으면 서식 기본값(도면)을 다시 고르고,
직원이 고른 값은 그대로 둔다. 발급은 보이는 창의 동그라미를 읽는다.
"""

from __future__ import annotations

from tests.support.drawing_customer_js_harness import run_js

SHARE_JS = "static/js/orders/erp-share.js"

# 창 하나 + 동그라미 둘. DRAWING_ON · ESTIMATE_ON 은 driver 앞에서 정한다.
# querySelector 는 지금 checked 인 것을 돌려줘야 하므로 고정 표 대신 함수로 단다.
SHARE_DOM = r"""
window.ORDER_ID = 77;
const modal = makeEl({ id: 'erpShareModal', attrs: { 'data-kakao-js-key': '' } });
const drawing = makeEl({ id: 'erp-share-kind-drawing', value: 'drawing', checked: DRAWING_ON });
drawing.defaultChecked = true;  // 서식의 checked 속성
const estimate = makeEl({ id: 'erp-share-kind-estimate', value: 'estimate', checked: ESTIMATE_ON });
modal._all['input[name="erp-share-kind"]'] = [drawing, estimate];
modal.querySelector = function (s) {
  if (s === 'input[name="erp-share-kind"]:checked') return [drawing, estimate].find(function (r) { return r.checked; }) || null;
  return null;
};
route('/api/share/list/77', function () { return Resp(200, { success: true, data: { items: [] }, error: null }); });
route('/api/share/create/77', function () {
  return Resp(200, { success: true, data: { share_id: 9, url: 'https://x/s/t', kind: 'drawing', token: 't' }, error: null });
});
loadSources();
"""


def _open(drawing_on: bool, estimate_on: bool) -> dict:
    driver = (
        f"const DRAWING_ON = {str(drawing_on).lower()}; const ESTIMATE_ON = {str(estimate_on).lower()};\n"
        + SHARE_DOM
        + "window.erpOpenShareModal();\nawait flush();\n"
        + "out({ drawing: drawing.checked, estimate: estimate.checked });"
    )
    return run_js([SHARE_JS], driver)


def test_둘_다_빈_채면_열_때_서식_기본값_도면을_고른다() -> None:
    res = _open(False, False)
    assert res["drawing"] is True
    assert res["estimate"] is False
    assert ["show", "erpShareModal"] in res["modalOps"]


def test_직원이_고른_견적서는_다시_열어도_그대로() -> None:
    res = _open(False, True)
    assert res["estimate"] is True
    assert res["drawing"] is False


def test_발급은_보이는_창의_동그라미를_읽는다() -> None:
    """문서 첫 번째 checked(지워질 다른 표면의 견적서)가 아니라 보이는 창의 도면으로 발급한다."""
    driver = (
        "const DRAWING_ON = false; const ESTIMATE_ON = false;\n"
        + SHARE_DOM
        + r"""
const otherSurfaceEstimate = makeEl({ value: 'estimate', checked: true });
globalSel['input[name="erp-share-kind"]:checked'] = otherSurfaceEstimate;
window.erpOpenShareModal();
await flush();
const createBtn = makeEl({ id: 'erp-share-create-btn' });
createBtn._closest['#erp-share-create-btn'] = createBtn;
fire('click', createBtn);
await flush();
out({});
"""
    )
    res = run_js([SHARE_JS], driver)
    creates = [c for c in res["calls"] if c["url"] == "/api/share/create/77"]
    assert len(creates) == 1
    assert creates[0]["method"] == "POST"
    assert creates[0]["body"] == {"kind": "drawing"}
