"""S2 — 도면 작업실 PC 결정 바·공용 시트 렌더 (설계서 2026-09-29 도면 탭 고객 보내기 §3.2·§3.4·§3.5 + Q5).

PC 결정 바는 서버가 만든 ``customer_send.bar`` 를 **순회만** 한다(§3.0). 버튼 판정은 S1 읽기 모델의 몫이라,
이 파일의 모양 테스트는 실제 상세 라우트를 타되 ``render_template`` 직전에 ``customer_send`` 를 **빈 값에서 시작해**
주어진 값만 채운다(``_inject``). 그래서 S1 이 판정 본문·실제 값을 바꿔도 이 테스트는 "주어진 목록을 어떻게 그리나"만 본다.
빈 bar 대체·회차 기록 줄·S1 합친 뒤 통합 테스트는 test_drawing_tab_send_pc_s1_link.py, 공용 도우미는
tests/support/drawing_tab_send_pc_helpers.py.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest

from db import db_session
from models import Order
from tests.support.drawing_tab_send_pc_helpers import _bar, _bar_keys, _inject, _order, _page, _pc, make_people

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def people():
    return make_people()


# --------------------------------------------------------------------------- 영업 결정 바


def test_sales_transferred_not_sent_bar(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("rev_sales", "send", "ok_no_customer", tone={"send": "primary"}),
                          "can_send": True, "has_phone": True, "phone_masked": "010-****-0022",
                          "round": 1, "round_text": "1차"})
    soup = _page(client, people["sales"], oid)
    pc = _pc(soup)
    assert _bar_keys(soup) == ["rev_sales", "send", "ok_no_customer"]
    send = pc.select_one('[data-bar-key="send"]')
    assert "btn-primary" in send["class"] and send["data-bs-target"] == "#dwCustomerSendModal"
    assert send["data-customer-send-mode"] == "first" and "고객에게 보내기" in send.get_text()
    rev = pc.select_one('[data-bar-key="rev_sales"]')
    assert rev["data-bs-target"] == "#dwRevisionModal" and not rev.has_attr("data-revision-source")
    assert rev.get_text(strip=True) == "수정 요청"  # 출처 구분 없이 하나의 '수정 요청'
    assert "내 의견" not in pc.get_text()
    ok = soup.select("#btn-confirm-receipt")
    assert len(ok) == 1, "확정 버튼 id 는 한 번만"
    assert ok[0]["data-bar-key"] == "ok_no_customer" and ok[0]["data-bs-target"] == "#dwCustomerOkModal"
    assert ok[0]["data-customer-ok-mode"] == "no_customer" and "확정 (고객 답 없이)" in ok[0].get_text()
    assert soup.select_one("#dwCustomerSendModal") is not None
    assert soup.select_one("#dwCustomerOkModal") is not None


def test_sales_after_send_bar(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("resend", "rev_customer", "ok"), "sent_this_round": True,
                          "sent_text": "오늘 11:52 알림톡으로 보냈고 링크가 1번 열렸어요", "round_text": "1차"})
    soup = _page(client, people["sales"], oid)
    pc = _pc(soup)
    assert "다시 보내기" in pc.select_one('[data-bar-key="resend"]').get_text()
    assert pc.select_one('[data-bar-key="resend"]')["data-customer-send-mode"] == "again"
    rc = pc.select_one('[data-bar-key="rev_customer"]')
    assert not rc.has_attr("data-revision-source") and rc.get_text(strip=True) == "수정 요청"
    assert "고객이 고쳐 달래요" not in pc.get_text()
    ok = soup.select("#btn-confirm-receipt")
    assert len(ok) == 1 and ok[0]["data-customer-ok-mode"] == "customer" and "고객 OK · 확정" in ok[0].get_text()
    modal = soup.select_one("#dwCustomerSendModal")
    assert modal["data-sent-this-round"] == "true"
    assert "11:52" in modal["data-sent-text"]
    assert "11:52" in modal.select_one("[data-send-again]").get_text()


def test_returned_bar_has_cancel_and_edit_but_no_send(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")
    prefill = {"note": "문짝 폭 줄여 주세요", "source": "customer", "received_via": "kakao",
               "files": [{"key": f"orders/{oid}/drawing_gateway/revisions/a.png", "filename": "a.png"}],
               "target_file_keys": ["orders/s2/drawing/plan-2.png"]}
    _inject(monkeypatch, {"bar": _bar("cancel_revision", "edit_revision"), "edit_revision": prefill})
    soup = _page(client, people["sales"], oid)
    assert _bar_keys(soup) == ["cancel_revision", "edit_revision"]
    assert len(soup.select("#btn-cancel-revision")) == 1
    assert soup.select_one("#dwCustomerSendModal") is None
    edit_btn = _pc(soup).select_one('[data-bar-key="edit_revision"]')
    assert edit_btn["data-bs-target"] == "#dwRevisionEditModal" and "요청 고치기" in edit_btn.get_text()
    modal = soup.select_one("#dwRevisionEditModal")
    assert json.loads(modal["data-edit-revision"]) == prefill  # data-* JSON 이 그대로 되읽힌다
    assert modal["data-drawing-count"] == "2"
    assert len(modal.select('input[name="dw-edit-target"]')) == 2
    # 수정요청은 출처를 나누지 않는다 — 고치기 창에도 '누구 말인가요'·'어떻게 받았나요' 칸이 없다.
    assert modal.select('input[name="dw-edit-source"]') == [] and modal.select('input[name="dw-edit-via"]') == []
    assert modal.select_one("[data-edit-via-block]") is None
    assert "누구 말인가요" not in modal.get_text() and "내 의견" not in modal.get_text()


def test_confirmed_bar_approve_and_send_as_secondary(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="CONFIRMED", stage="CONFIRM")
    _inject(monkeypatch, {"bar": _bar("rev_post", "send", "approve_confirm"), "can_approve_after_confirm": True})
    soup = _page(client, people["sales"], oid)
    pc = _pc(soup)
    assert "btn-outline-primary" in pc.select_one('[data-bar-key="send"]')["class"]  # 주 버튼 아님
    approve = pc.select_one('[data-bar-key="approve_confirm"]')
    assert approve.has_attr("data-customer-approve") and approve["data-order-id"] == str(oid)
    assert "고객 컨펌하고 생산으로" in approve.get_text()
    rev_post = pc.select_one('[data-bar-key="rev_post"]')
    assert not rev_post.has_attr("data-revision-source") and rev_post.get_text(strip=True) == "수정 요청"
    assert soup.select_one("[data-approve-role-hint]") is None


def test_confirmed_without_approve_power_shows_production_and_hint(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="CONFIRMED", stage="CONFIRM")
    _inject(monkeypatch, {"bar": _bar("rev_post", "send", "production"), "can_approve_after_confirm": False})
    soup = _page(client, people["sales"], oid)
    prod = _pc(soup).select_one('[data-bar-key="production"]')
    assert prod.name == "a" and prod["href"].endswith(f"?focus_order={oid}")
    assert "고객 컨펌은 영업·CS 팀이 해요" in soup.select_one("[data-approve-role-hint]").get_text()


def test_production_stage_has_no_role_hint(client, monkeypatch, people):
    """대조군: 이미 생산 단계면 컨펌이 해당 없으니 '영업·CS 팀이 해요' 줄을 안 보인다."""
    oid = _order(people["drafter"]["id"], status="CONFIRMED", stage="PRODUCTION")
    _inject(monkeypatch, {"bar": _bar("rev_post", "send", "production"), "can_approve_after_confirm": False})
    soup = _page(client, people["sales"], oid)
    assert soup.select_one("[data-approve-role-hint]") is None


# --------------------------------------------------------------------------- 도면팀 · 상태 한 줄 · 긴급 호출


def test_drawing_team_sees_status_line_and_pc_urgent_call_only(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("urgent_call"), "status_line": "영업 → 고객 · 1차 보냄 11:52 알림톡 · 링크 열림 1번",
                          "views": 1})
    soup = _page(client, people["drafter"], oid)
    assert _bar_keys(soup) == ["urgent_call"]  # 영업 버튼 0개
    line = soup.select_one("[data-customer-send-status]").get_text()
    assert "영업 → 고객" in line and "직원이 연 것도 셀 수 있어요" in line
    urgent = _pc(soup).select_one('[data-bar-key="urgent_call"]')
    # PC 버튼은 drawing-urgent-call-pc.js 가 받아 공용 긴급 호출 창을 이 주문으로 연다(SPEC 2026-10-01).
    assert urgent.has_attr("data-dw-urgent-call") and not urgent.has_attr("data-foms-urgent-call")
    assert urgent["data-order-id"] == str(oid)
    assert soup.select_one("#dwUrgentCallModal") is None  # 도면 전용 창은 지웠다
    modal = soup.select_one("#fomsUrgentCallModal")  # 공용 창(layout_scripts.html)
    assert modal is not None and modal.find_parent(class_="d-lg-none") is None
    assert modal.select_one("[data-foms-urgent-send]").has_attr("disabled")


# --------------------------------------------------------------------------- 전달 취소 경고(§3.4 · Q4 · Q5-④)


def test_cancel_transfer_warning_only_when_sent_this_round(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"cancel_warning_text_pc": "영업이 이 1차 도면을 고객에게 이미 보냈어요(PC)",
                          "cancel_warning_text_mobile": "영업이 이 1차 도면을 고객에게 이미 보냈어요(모바일)",
                          "round_text": "1차"})
    soup = _page(client, people["drafter"], oid)
    btn = soup.select_one("#btn-cancel-transfer")
    assert btn["data-customer-sent-text-pc"].endswith("(PC)")
    assert btn["data-customer-sent-text-mobile"].endswith("(모바일)")
    warn = soup.select_one("#dwCancelWarnModal")
    assert warn is not None and warn.select_one("[data-cancel-transfer-confirm]") is not None
    ping = warn.select_one("[data-dw-urgent-call]")
    assert ping["data-urgent-team"] == "SALES" and "영업에게 먼저 알리기" in ping.get_text()
    assert ping["data-order-id"] == str(oid)
    # 모바일 프록시·도면 전용 창 없이 공용 창 하나를 연다(SPEC 2026-10-01).
    assert warn.select_one("[data-cancel-warn-mobile-proxy]") is None
    assert soup.select_one("#dwUrgentCallModal") is None
    assert soup.select_one("#fomsUrgentCallModal") is not None


def test_cancel_transfer_without_send_keeps_plain_confirm(client, people):
    """대조군(같은 주문 모양): 안 보낸 회차면 경고 속성·경고 시트가 없다."""
    oid = _order(people["drafter"]["id"])
    soup = _page(client, people["drafter"], oid)
    btn = soup.select_one("#btn-cancel-transfer")
    assert btn is not None
    assert not btn.has_attr("data-customer-sent-text-pc") and not btn.has_attr("data-customer-sent-text-mobile")
    assert soup.select_one("#dwCancelWarnModal") is None


# --------------------------------------------------------------------------- 시트 (가)(나)(다)


@pytest.mark.parametrize("can_approve", [True, False])
def test_customer_ok_modal_approve_radio_follows_power(client, monkeypatch, people, can_approve):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("ok"), "can_approve_after_confirm": can_approve, "round_text": "1차"})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerOkModal")
    assert modal["data-can-approve"] == ("true" if can_approve else "false")
    radio = modal.select_one("#dw-ok-after-approve")
    text = modal.get_text()
    if can_approve:
        assert radio is not None and radio.has_attr("checked")
        assert "생산팀에 알림이 가요" in text and "확정하고 생산으로 넘기기" in text
    else:
        assert radio is None, "컨펌 권한이 없으면 '컨펌까지' 라디오를 그리지 않는다"
        assert "고객 컨펌은 영업·CS 팀이 해요" in text and "생산팀에 알림이 가요" not in text
    assert modal.select_one("#dw-ok-note")["maxlength"] == "200"


def test_send_modal_preview_data_and_bundle_chip(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("send"), "has_phone": True, "phone_masked": "010-****-0022",
                          "bundle_both_template": True, "doc_label_drawing": "수정 도면(2차)",
                          "doc_label_bundle": "수정 도면(2차)·계약서", "round": 2, "round_text": "2차"})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerSendModal")
    assert modal["data-bundle-both-template"] == "true"
    assert modal["data-doc-label-bundle"] == "수정 도면(2차)·계약서"
    assert modal["data-round-label"] == "2차" and modal["data-order-id"] == str(oid)
    text = modal.get_text()
    assert "도면+계약서" in text and "도면+견적서" not in text
    assert "이제 2차만 보여요" in text
    assert "010-****-0022" in text
    # 번호 바꾸기 권한이 없으면 주문 화면 링크(폼 잠금 M1 과 겹치지 않게).
    assert modal.select_one("[data-send-phone-toggle]") is None
    assert "번호가 틀리면 주문 화면에서 고쳐요" in text
    mine = modal.select_one('label[for="dw-send-channel-mine"]')
    assert "d-lg-none" in mine["class"]  # 내 폰 문자는 모바일에서만


@pytest.mark.parametrize("name,expect_title,expect_attr", [("-", "고객님께 2차 도면 보내기", ""),
                                                          ("홍길동", "홍길동 고객님께 2차 도면 보내기", "홍길동")])
def test_send_modal_missing_customer_name_reads_naturally(client, monkeypatch, people, name, expect_title, expect_attr):
    """ctx customer_name 은 이름이 없으면 '-' 다 — '- 고객님께' 가 나오지 않게 빈 값으로 본다."""
    oid = _order(people["drafter"]["id"])

    def patch(ctx):
        ctx["customer_name"] = name

    _inject(monkeypatch, {"bar": _bar("send"), "has_phone": True, "phone_masked": "010-****-0022", "round_text": "2차"},
            patch)
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerSendModal")
    title = " ".join(modal.select_one("#dwCustomerSendTitle").get_text().split())
    assert title == expect_title
    assert modal["data-customer-name"] == expect_attr
    assert "- ·" not in modal.get_text()


def test_send_modal_carries_structured_stamp_for_phone_save(client, monkeypatch, people):
    """주문 번호 저장(PATCH structured/fields)이 X-If-Match 로 보낼 structured_updated_at 을 data-* 로 싣는다."""
    oid = _order(people["drafter"]["id"])
    order = db_session.get(Order, oid)
    order.structured_updated_at = datetime.datetime(2026, 9, 29, 10, 11, 12)
    db_session.commit()
    _inject(monkeypatch, {"bar": _bar("send"), "can_change_phone": True, "can_save_phone": True})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerSendModal")
    assert modal["data-structured-updated-at"] == "2026-09-29 10:11:12"


def test_send_modal_phone_change_and_save_checkbox(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("send"), "has_phone": False, "can_change_phone": True, "can_save_phone": True})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerSendModal")
    assert modal["data-has-phone"] == "false"
    assert "고객 휴대폰 번호가 없어요" in modal.get_text()
    assert modal.select_one("[data-send-phone-toggle]") is not None
    assert modal.select_one("#dw-send-phone")["type"] == "tel"
    assert modal.select_one("#dw-send-save-phone") is not None


def test_send_modal_phone_change_without_save_power(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("send"), "has_phone": True, "can_change_phone": True, "can_save_phone": False})
    modal = _page(client, people["sales"], oid).select_one("#dwCustomerSendModal")
    assert modal.select_one("#dw-send-phone") is not None
    assert modal.select_one("#dw-send-save-phone") is None


def test_revision_modal_has_no_source_or_via_fields(client, monkeypatch, people):
    """수정요청은 '고객 요청'·'내 의견'으로 나누지 않는다 — 출처·받은 경로 칸이 없고 제목·메모 칸은 하나."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("rev_customer")})
    soup = _page(client, people["sales"], oid)
    modal = soup.select_one("#dwRevisionModal")
    assert not modal.has_attr("data-revision-source")
    assert modal.select('input[name="dw-revision-source"]') == []
    assert modal.select('input[name="dw-revision-via"]') == []
    assert modal.select_one("[data-revision-source-block]") is None
    assert modal.select_one("[data-revision-via-block]") is None
    assert modal.select_one("[data-revision-note-hint]") is None
    assert modal.select_one("[data-revision-title]").get_text(strip=True) == "수정 요청"
    assert modal.select_one("[data-revision-note-label]").get_text(strip=True) == "수정 요청 메모 (필수)"
    for gone in ("누구 말인가요", "어떻게 받았나요", "내 의견"):
        assert gone not in modal.get_text()
    assert soup.select('input[name="dw-edit-source"]') == [] and soup.select('input[name="dw-edit-via"]') == []
    assert soup.select("[data-revision-source]") == []
    assert "선택하지 않으면 자동으로 최신본이 선택됩니다" not in modal.get_text()
    assert "도면이 2장 이상이면 꼭 골라요" in modal.get_text()
    assert modal["data-confirmed"] == "false" and modal.select_one("[data-revision-confirmed-warning]") is None


def test_revision_modal_confirmed_warning(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="CONFIRMED", stage="CONFIRM")
    _inject(monkeypatch, {"bar": _bar("rev_post")})
    modal = _page(client, people["sales"], oid).select_one("#dwRevisionModal")
    assert modal["data-confirmed"] == "true"
    assert "생산팀에 변경 알림" in modal.select_one("[data-revision-confirmed-warning]").get_text()


def test_source_tag_badges_on_requests_and_timeline(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")

    def patch(ctx):
        for r in ctx.get("revision_requests") or []:
            r["source_tag"] = "고객 요청 · 1차 · 카톡 답장"
        for h in ctx.get("history") or []:
            if h.get("action") == "REQUEST_REVISION":
                h["source_tag"] = "고객 요청 · 1차 · 카톡 답장"

    _inject(monkeypatch, None, patch)
    soup = _page(client, people["sales"], oid)
    tags = [t.get_text(strip=True) for t in soup.select(".dw-legacy-detail [data-source-tag]")]
    assert tags.count("고객 요청 · 1차 · 카톡 답장") == 2  # 요청사항 카드 1 + 타임라인 1


def test_old_mobile_bar_confirm_opens_ok_modal(client, people):
    oid = _order(people["drafter"]["id"])
    soup = _page(client, people["sales"], oid)
    btn = soup.select_one("#btn-confirm-receipt-mobile")
    assert btn is not None and btn["data-bs-target"] == "#dwCustomerOkModal"
    assert soup.select_one("#dwCustomerOkModal") is not None


# --------------------------------------------------------------------------- 정적(템플릿·인라인 스크립트)


def _detail_body() -> str:
    return (ROOT / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")


def test_inline_confirm_receipt_moved_out_and_stays_on_drawing_tab():
    body = _detail_body()
    assert "async function confirmReceipt" not in body
    assert "addEventListener('click', confirmReceipt)" not in body
    inline = body[body.index("<script>\n  (function () {"):body.index("</script>", body.index("<script>\n  (function () {"))]
    assert "/erp/dashboard?focus_order=" not in inline and "open_quest" not in inline  # C14
    assert "typeof window.fomsDrawingRevisionExtras === 'function'" in inline
    assert "window.fomsDrawingUploadRevisionFiles" in inline
    # 전달 취소 경고 갈래는 새 JS 가 떴을 때만 시트로(동작은 test_drawing_customer_js_behavior 가 Node 로 실행해 본다).
    assert "window.__FOMS_DRAWING_URGENT_PC_BOUND && typeof window.fomsDrawingCancelWarn === 'function'" in inline


def test_new_sheets_have_no_inline_style_or_handlers():
    text = (ROOT / "templates/drawing/partials/workbench_customer_send_modals.html").read_text(encoding="utf-8")
    assert 'style="' not in text
    assert not re.search(r"\son[a-z]+=", text)


def test_sheet_alerts_survive_global_autodismiss(client, monkeypatch, people):
    """전역 script.js 는 5초 뒤 `.alert:not([data-foms-no-autodismiss])` 를 DOM 에서 지운다 — 시트 안
    안내·경고·오류 줄(전달 취소 경고 문구 포함)은 나중에 열리므로 전부 빠져야 한다."""
    oid = _order(people["drafter"]["id"], status="CONFIRMED", stage="CONFIRM")
    _inject(monkeypatch, {"bar": _bar("send", "ok", "edit_revision", "urgent_call", "rev_post"),
                          "can_approve_after_confirm": True, "round": 2, "round_text": "2차"})
    soup = _page(client, people["sales"], oid)
    ids = ("#dwCustomerSendModal", "#dwCustomerOkModal", "#dwRevisionEditModal", "#fomsUrgentCallModal", "#dwRevisionModal")
    alerts = [a for mid in ids for a in soup.select(f"{mid} .alert")]
    assert len(alerts) >= 10
    assert [a.get_text(strip=True)[:20] for a in alerts if not a.has_attr("data-foms-no-autodismiss")] == []


def test_revision_preview_opens_viewer_on_image_click(client, monkeypatch, people):
    """수정요청 시트 도면 미리보기 — 파일명 줄·[전체화면] 버튼 없이 이미지를 누르면 공용 뷰어로 연다."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("rev_customer")})
    soup = _page(client, people["sales"], oid)
    modal = soup.select_one("#dwRevisionModal")
    assert modal.select_one("#dw-revision-drawing-preview-stage") is not None
    assert modal.select_one("#dw-revision-drawing-preview-expand") is None
    assert modal.select_one("#dw-revision-drawing-preview-label") is None
    html = str(soup)
    assert "data-revision-preview-focus" in html
    assert "getElementById('dw-revision-drawing-preview-stage')?.addEventListener('click'" in html
    assert "window.GlobalImageViewer.open(files, index)" in html
