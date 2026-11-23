"""[제작 완료] 검수 게이트 — 화면 쪽(사용자 결정 2026-11-21, ``test_production_complete_requires_inspect.py`` 에서 나눔).

모든 [제작 완료] 단추가 같은 완료 API 로 가고, 시트 두 곳은 뷰 모델의 같은 판정(``complete_ready``)으로 회색 · 파랑을
그린다. 공정 칸을 쓴 주문만 막는다(11-21 사용자 "공정 칸을 쓴 주문만 막기") — 한 칸도 안 켠 주문은 파랑(규칙 밖).
"""
from __future__ import annotations

import re

from foms.services.production.steps import production_steps_missing
from tests.domains.test_production_complete_requires_inspect import (
    _all_off,
    _complete,
    _fresh,
    _login,
    _order,
    _read,
    _user,
)
from tests.support.production_steps_seed import inspected_steps


# --------------------------------------------------------------------------- #
# 6. 화면 — 모든 [제작 완료] 단추가 같은 API 를 부르고, 시트 두 곳은 같은 함수로 회색
# --------------------------------------------------------------------------- #
def test_모든_제작_완료_단추는_같은_완료_API_로_간다() -> None:
    """작업 시트 · 옆 시트(tablet-domain-sheets.js) · 칸반 카드(tablet-production-kanban.js) · PC 보드 상세 · 폰 큐
    (production/partials/scripts.html completeProduction)가 모두 /production/complete — 서버 거절 하나가 전부를 막는다."""
    assert '"/production/complete"' in _read("static/js/foms/tablet-domain-sheets.js")
    assert 'path: "/production/complete"' in _read("static/js/foms/tablet-production-kanban.js")
    assert "submitProductionTransition(orderId, '/production/complete')" in _read("templates/production/partials/scripts.html")
    assert "'data_action': 'completeProduction'" in _read("templates/production/partials/mobile_queue.html")


def test_거절_글이_엉뚱한_연결_끊김_글로_덮이지_않는다() -> None:
    """409 는 서버 글을 그대로 보인다 — '연결이 끊겼어요' 는 진짜 연결 실패(catch · network)에서만."""
    sheets = _read("static/js/foms/tablet-domain-sheets.js")
    i = sheets.index("function submitTransition(")
    body = sheets[i:sheets.index("function productionStart(", i)]
    assert 'window.alert("오류: " + (failed.message || failed.error || "처리 실패"));' in body
    assert body.index("연결이 끊겼어요") > body.index(".catch(function (err)")
    kanban = _read("static/js/foms/tablet-production-kanban.js")
    assert 'window.alert("오류: " + (failed.message || failed.error || result.message));' in kanban
    pc = _read("templates/production/partials/scripts.html")
    assert "alert('오류: ' + (result.data.message || '처리에 실패했습니다.'));" in pc
    # 공용 쓰기 래퍼는 서버 글을 먼저 쓴다(409 기본 글 '충돌' 은 서버 글이 없을 때만)
    write = _read("static/js/foms/foms-write.js")
    assert "extractServerMessage(data) || STATUS_MESSAGES[res.status]" in write
    # 관리자는 사유를 적고 한 번 더 보낼 수 있다(재시도 목록에 같은 글자)
    retry = _read("static/js/foms/foms-admin-override.js").split("var RETRYABLE_CODES")[1].split("]")[0]
    assert "'STEPS_INCOMPLETE'" in retry


def test_일괄_화면이_막힌_주문을_알린다() -> None:
    js = _read("static/js/orders/dashboard/erp-dashboard-detail-dom.js")
    assert "data.blocked_steps_incomplete && data.blocked_steps_incomplete.length" in js


def test_시트_두_곳은_뷰_모델의_같은_판정으로_그린다() -> None:
    page = _read("templates/production/sheet.html")
    side = _read("templates/production/partials/tablet_sheet.html")
    assert "{% set _inspected = order.complete_ready %}" in page
    assert "steps_done >= (order.steps | length)" not in page  # 템플릿이 스스로 세지 않는다
    assert "order.complete_ready" in side and "data-foms-sheet-complete" in side
    assert "검수까지 끝나면 눌러요" in page and "검수까지 끝나면 눌러요" in side
    css = _read("static/css/contexts/production/sheet.css")
    assert ".foms-prod-sheet__btn--off, .foms-prod-sheet__btn--off:disabled" in css


def _render_side_sheet(client, oid: int) -> str:
    resp = client.get(f"/erp/production/tablet-sheet/{oid}")
    assert resp.status_code == 200, resp.status_code
    html = resp.get_data(as_text=True)
    return re.search(r'<button [^>]*data-tablet-sheet-action="production-complete"[^>]*>.*?</button>', html, re.S).group(0)


def test_옆_시트_제작_완료는_검수_전_회색_검수_끝_파랑(client) -> None:
    _login(client, _user())
    grey = _render_side_sheet(client, _order(production={"steps": inspected_steps(upto="cut")}))
    # 진짜 disabled 없이 aria-disabled 만 — 누르면 남은 공정을 알린다(2026-11-22, test_production_sheet_tap_explains)
    assert "foms-prod-sheet__btn--off" in grey and " disabled" not in grey and 'aria-disabled="true"' in grey
    assert "검수까지 끝나면 눌러요" in grey and "data-foms-sheet-complete-hint>" in grey
    blue = _render_side_sheet(client, _order(production={"steps": inspected_steps()}))
    assert "foms-prod-sheet__btn--pri" in blue and " disabled" not in blue
    assert "data-foms-sheet-complete-hint hidden" in blue
    # 한 칸도 안 켠 주문 = 규칙 밖이라 파랑(서버가 그대로 완료시키므로 회색으로 막아 보이지 않는다)
    for production in (None, {"steps": _all_off()}):
        unused = _render_side_sheet(client, _order(production=production))
        assert "foms-prod-sheet__btn--pri" in unused and " disabled" not in unused, production
        assert "data-foms-sheet-complete-hint hidden" in unused


def test_공정_API_는_같은_함수의_답을_싣는다(client) -> None:
    _login(client, _user(part=None, lead=True))  # 반장
    oid = _order(production={"steps": inspected_steps(upto="assemble")})
    got = client.get(f"/api/orders/{oid}/production/steps").get_json()["data"]
    assert got["complete_ready"] is False
    done = client.post(f"/api/orders/{oid}/production/steps", json={"key": "inspect", "done": True}).get_json()["data"]
    assert done["complete_ready"] is True and done["done_count"] == 4
    undone = client.post(f"/api/orders/{oid}/production/steps", json={"key": "cut", "done": False}).get_json()["data"]
    assert undone["complete_ready"] is False


def test_모두_켰다가_모두_끄면_규칙_밖으로_돌아간다(client) -> None:
    """칸을 하나 켜면 공정을 쓴 주문(막힘), 4칸 다 켜면 풀림, 모두 다시 끄면 안 쓴 주문으로 돌아가 그대로 완료된다."""
    _login(client, _user(part=None, lead=True))  # 반장
    oid = _order(production={"steps": _all_off()})

    def _toggle(key: str, done: bool) -> bool:
        resp = client.post(f"/api/orders/{oid}/production/steps", json={"key": key, "done": done})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return resp.get_json()["data"]["complete_ready"]

    assert client.get(f"/api/orders/{oid}/production/steps").get_json()["data"]["complete_ready"] is True
    keys = ("cut", "edge", "assemble", "inspect")
    assert [_toggle(k, True) for k in keys] == [False, False, False, True]
    assert [_toggle(k, False) for k in keys] == [False, False, False, True]
    assert production_steps_missing(_fresh(oid).structured_data) == []

    resp = _complete(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).erp_stage_code == "CONSTRUCTION"
