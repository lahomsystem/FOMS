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


# --- 휴대폰 아래 단추 묶음 접기(2026-11-02 결정 D1) ------------------------------------------------
# 실측 끝 단추가 있으면 묶음이 3층(발송 기록 · 실측 끝 · 저장/PUSH/알림톡)이라 입력 칸이 약 96px 줄었다 → 손잡이 한 줄로 통째
# 접는다. 기본은 접힘 · 기억 안 함. 대조군: 실측 끝 단추가 없는 주문은 묶음이 지금 마크업 그대로(손잡이 · hidden 없음).
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
OLD_FOOTER_OPEN = ('<footer class="foms-sticky-action-bar erp-mobile-sticky-action-bar" role="group" '
                   'aria-label="ERP 주문 저장 및 전송">')


def _mobile_footers(app, monkeypatch) -> tuple[str, str]:
    """(실측 단계 주문, 도면 단계 대조군) 휴대폰 편집 화면의 아래 단추 묶음."""
    sales = _make_user(role="STAFF", team="SALES", username="md-fold-sales")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(sales.id))
    ids = (_create_order(quests=[_measure_assignee_quest()]).id,
           _create_order(stage="DRAWING", status="DRAWING", quests=[_measure_assignee_quest("DRAWING")]).id)
    client = app.test_client()
    _login(client, sales)
    footers = []
    for order_id in ids:
        page = client.get(f"/edit/{order_id}", headers={"User-Agent": IPHONE})
        assert page.status_code == 200
        html = page.get_data(as_text=True)
        mobile = html[html.index('<div id="erp-order-form-mobile">'):]
        start = mobile.index('<footer class="foms-sticky-action-bar erp-mobile-sticky-action-bar')
        footers.append(mobile[start:mobile.index("</footer>", start)])
    db_session.rollback()
    return footers[0], footers[1]


def test_mobile_footer_folds_whole_bar_for_measure_order_and_leaves_control_alone(app, monkeypatch):
    measure, control = _mobile_footers(app, monkeypatch)

    toggle = measure[measure.index("<button"):measure.index("</button>")]
    assert "data-erp-action-fold-toggle" in toggle and 'type="button"' in toggle
    assert 'aria-expanded="false"' in toggle and 'aria-controls="erp-action-fold-body"' in toggle
    assert "저장 · PUSH · 알림톡 · <strong>실측 끝</strong>" in toggle
    assert "data-erp-action-fold-count hidden" in toggle  # 발송 수는 JS 가 채우고 나서야 보인다
    body_open = measure.index('id="erp-action-fold-body"')
    body_tag = measure[measure.rindex("<div", 0, body_open):measure.index(">", body_open)]
    assert body_tag.rstrip().endswith("hidden")  # 기본은 접힘
    body = measure[body_open:]
    for part in ('data-erp-send-trace="fold"', "data-erp-measure-done", 'id="erp-save-btn"',
                 'id="erp-channeltalk-push-picker-btn"', 'id="erp-alimtalk-picker-btn"'):
        assert part in body, part
    assert 'style="' not in measure

    # 대조군(도면 단계 = 실측 끝 단추 없음): 손잡이 · 접힘 없음, 단추가 바로 보인다.
    assert control.startswith(OLD_FOOTER_OPEN)
    assert "erp-action-fold" not in control and "hidden" not in control
    assert "data-erp-measure-done" not in control
    order = [control.index(p) for p in ('data-erp-send-trace="fold"', 'id="erp-save-btn"',
                                        'id="erp-channeltalk-push-picker-btn"', 'id="erp-alimtalk-picker-btn"')]
    assert order == sorted(order)


def test_fold_toggle_flips_aria_expanded_and_hidden_together_without_memory() -> None:
    js = JS.read_text(encoding="utf-8")
    fn = js[js.index("function setFold(toggle, open)"):js.index("function updateFoldCount")]
    assert "toggle.setAttribute('aria-expanded', open ? 'true' : 'false');" in fn
    assert "body.hidden = !open;" in fn
    assert "getElementById(toggle.getAttribute('aria-controls'))" in fn
    handler = js[js.index("closest('[data-erp-action-fold-toggle]')"):]
    assert "setFold(toggle, toggle.getAttribute('aria-expanded') !== 'true');" in handler
    # 기본 접힘 · 기억 안 함(사용자 결정) — 저장소에 상태를 남기지 않는다.
    assert "localStorage" not in js and "sessionStorage" not in js
    # 발송 수는 발송 기록 모듈과 같은 규칙으로 센다(새 API 없음).
    assert "window.erpSendTraceModel(window.__erpLastStructuredData, Date.now())" in js
    css = (ROOT / "static/css/orders/erp-channel-push.css").read_text(encoding="utf-8")
    assert ".erp-action-fold__body[hidden] {\n  display: none;" in css
