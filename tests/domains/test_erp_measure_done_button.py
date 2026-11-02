"""주문 편집 화면 "실측 끝 · 도면 넘기기"(영업팀 요청 2026-11-02).

휴대폰에서 실측 저장 → 영발 → 대시보드 검색 → 도면 단계로 넘기기를 하던 것을 편집 화면 단추 하나로. 새 API 는 없다 —
저장 · quest 승인 · 영발 PUSH 를 화면이 차례로 부른다(erp-measure-done.js). 단추는 대시보드 "도면 단계로 넘기기"와
같은 서버 판정(drawing_transfer_cta)으로 실측 단계 · 승인 권한일 때만 그린다. 대조군: 도면 단계 주문 · 협력사 화면 없음.
"""
from __future__ import annotations

from pathlib import Path

from db import db_session
from foms.services.order_edit_view_context import build_order_edit_get_context
from tests.domains.drawing_transfer_helpers import (
    _create_order,
    _login,
    _make_user,
    _measure_assignee_quest,
)

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/orders/erp-measure-done.js"


def test_context_offers_button_only_on_measure_stage(app):
    sales = _make_user(role="STAFF", team="SALES", username="md-sales")
    measuring = _create_order(quests=[_measure_assignee_quest()])
    drawing = _create_order(stage="DRAWING", status="DRAWING", quests=[_measure_assignee_quest("DRAWING")])
    with app.test_request_context():
        cta = build_order_edit_get_context(measuring, user=sales)["measure_done_cta"]
        assert cta["visible"] and cta["enabled"] and cta["confirm"]
        assert not build_order_edit_get_context(drawing, user=sales)["measure_done_cta"]["visible"]
        assert build_order_edit_get_context(measuring, user=None)["measure_done_cta"] is None


def test_edit_page_renders_button_for_measure_order(app):
    sales = _make_user(role="STAFF", team="SALES", username="md-sales2")
    order = _create_order(quests=[_measure_assignee_quest()])
    client = app.test_client()
    _login(client, sales)
    page = client.get(f"/edit/{order.id}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130"})
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "data-erp-measure-done" in html and "실측 끝 · 도면 넘기기" in html
    assert "erp-measure-done.js" in html
    db_session.rollback()


def test_js_saves_then_approves_then_pushes_and_asks_resend_note_first() -> None:
    js = JS.read_text(encoding="utf-8")
    save = js.index("await erpSaveStructured({ redirect: false })")
    approve = js.index("await approveToDrawing(orderId)")
    push = js.index("pushed = await window.erpRunChannelPush(btn, 'measurement'")
    note = js.index("erpPromptChannelPushResendNote('measurement')")
    assert note < js.index("btn.disabled = true;") and save < approve < push
    assert "가로 치수가 빈 제품" in js  # 막지 않고 확인창에 적는다
    shared = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "window.erpRunChannelPush = erpRunChannelPush;" in shared
    assert 'style="' not in (ROOT / "templates/orders/partials/erp_order_tab_mobile.html").read_text(encoding="utf-8").split(
        "data-erp-measure-done")[1][:400]
