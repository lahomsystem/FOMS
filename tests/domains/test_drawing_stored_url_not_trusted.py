"""화면은 저장된 파일 URL 을 믿지 않고 key 로 다시 만든다 + 수정요청 취소 표시·안내 문구(2b).

SPEC §4.3.4: 2a-1① 전까지 폼 PUT·수정요청 API 가 ``drawing_current_files``·이력에 임의 URL
(``javascript:`` 포함)을 넣을 수 있었고 이미 들어간 값은 남는다. ``a href="javascript:…"`` 는
Jinja 이스케이프로 막히지 않는다. 그래서 다섯 화면(PC 작업실 갤러리·PC 현재 도면 목록·
모바일 도면 방·시공 카드 썸네일·ERP 창구 이력 JS) 모두 key 로만 URL 을 만든다. 같은 이유로
확정본 정규화(생산 시트 썸네일)·태블릿 검토 행도 key 로만 만든다.

SPEC §4.4: 수정요청 취소는 이력에 ``REVISION_CANCELLED`` 로 남고 파일을 지우지 않는다 —
라벨 "수정요청 취소", "참고 파일이 삭제" 라는 거짓 안내가 없어야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction_dashboard_display import _url_from_file_entry
from foms.services.datetime_kst import get_today_kst
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
EVIL = "javascript:alert(7331)"
EVIL_HOST = "evil-7331.example"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _user(username, role, team, name):
    u = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
             name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


def _page(client, monkeypatch, who, oid, query=""):
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = who["id"], who["username"], who["role"]
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    res = client.get(f"/erp/drawing-workbench/{oid}{query}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def _poisoned_order(drafter_id):
    """옛 값이 남은 주문 — 현재본·전달 이력·수정요청·취소 기록 모두 저장 URL 이 독이다."""
    o = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="URL고객",
              phone="010", address="서울", product="장", status="DRAWING", manager_name="영업U",
              is_erp_order=True, structured_data={})
    db_session.add(o)
    db_session.commit()
    oid = o.id
    cur = f"orders/{oid}/drawing/current.png"
    ref = f"orders/{oid}/drawing_gateway/revisions/20260929_101010_ab12cd34_ref.jpg"
    foreign = f"orders/{oid + 1}/drawing_gateway/revisions/20260929_101010_ab12cd34_x.jpg"
    poison = {"view_url": EVIL, "download_url": f"https://{EVIL_HOST}/steal"}
    o.structured_data = {
        "parties": {"customer": {"name": "URL고객"}, "manager": {"name": "영업U"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "RETURNED",
        "assignments": {"drawing_assignee_user_ids": [drafter_id]},
        "drawing_current_files": [{"key": cur, "filename": "current.png", **poison},
                                  {"filename": "no-key.png", **poison}],
        "drawing_transfer_history": [
            {"action": "TRANSFER", "at": "2026-09-28 01:00:00", "by_user_name": "도면U",
             "files": [{"key": cur, "filename": "current.png", **poison}]},
            {"action": "REQUEST_REVISION", "at": "2026-09-28 02:00:00", "by_user_name": "영업U",
             "by_user_id": 1, "note": "색 변경",
             "files": [{"key": ref, "filename": "ref.jpg", **poison},
                       {"key": foreign, "filename": "x.jpg", **poison}]},
            {"action": "REVISION_CANCELLED", "at": "2026-09-28 03:00:00", "by_user_name": "영업U",
             "reason": "고객 철회",
             "request": {"action": "REQUEST_REVISION", "note": "옛 요청 메모",
                         "files": [{"key": ref, **poison}]}},
            {"action": "REQUEST_REVISION", "at": "2026-09-28 04:00:00", "by_user_name": "영업U",
             "by_user_id": 1, "note": "다시 요청", "files": []},
        ],
    }
    db_session.commit()
    return oid, cur, ref, foreign


def test_workbench_pc_and_mobile_never_render_stored_urls(client, monkeypatch):
    drafter = _user("url_dr", "STAFF", "DRAWING", "도면U")
    oid, cur, ref, foreign = _poisoned_order(drafter["id"])
    html = _page(client, monkeypatch, drafter, oid)
    soup = BeautifulSoup(html, "html.parser")
    # 설정 JSON 섬(type=application/json)은 링크가 아니라 데이터다(JS 는 key·개수만 읽는다).
    for island in soup.select('script[type="application/json"]'):
        island.decompose()
    rendered = str(soup)
    assert EVIL not in rendered and EVIL_HOST not in rendered, "저장된 URL 이 화면에 실렸다"
    assert foreign not in rendered

    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None
    assert f"/api/files/view/{cur}" in str(handoff)
    assert f"/api/files/download/{cur}" in str(handoff)
    assert "/api/files/view/drawing-2" not in html  # key 없는 행은 링크를 그리지 않는다

    pc = soup.select_one(".dw-legacy-detail")
    assert pc is not None
    pc_html = str(pc)
    assert f"/api/files/view/{cur}" in pc_html
    assert f"/api/files/view/{ref}" in pc_html  # 이 주문 창구 참고사진은 key 로 링크
    assert "열 수 없음" in pc.get_text(" ", strip=True)  # 남의 key 는 개수만


def test_revision_cancelled_is_labelled_on_pc_and_mobile(client, monkeypatch):
    drafter = _user("url_dr2", "STAFF", "DRAWING", "도면U")
    oid, cur, *_ = _poisoned_order(drafter["id"])
    # 도면이 여러 장이면 모바일은 목록 화면이라 대화 스레드가 없다 — 한 장을 골라 상세로 연다.
    soup = BeautifulSoup(_page(client, monkeypatch, drafter, oid, f"?drawing_key={cur}"), "html.parser")
    pc_text = soup.select_one(".dw-legacy-detail").get_text(" ", strip=True)
    assert "수정요청 취소" in pc_text and "REVISION_CANCELLED" not in pc_text
    assert "옛 요청 메모" in pc_text and "고객 철회" in pc_text
    thread = soup.select_one(".foms-drawing-handoff .foms-drawing-thread")
    tags = [t.get_text(" ", strip=True) for t in thread.select(".foms-drawing-thread__tag")]
    assert any(t.startswith("수정요청 취소") for t in tags), tags
    assert "옛 요청 메모" in thread.get_text(" ", strip=True)


def test_construction_card_thumbnail_uses_key_only():
    key = "orders/5/drawing/plan.png"
    assert _url_from_file_entry({"key": key, "filename": "plan.png", "view_url": EVIL}) == (
        f"/api/files/view/{key}")
    assert _url_from_file_entry({"filename": "plan.png", "view_url": "/api/files/view/x.png"}) is None


def test_confirmed_files_and_tablet_rows_rebuild_urls_from_key(app):
    """확정본 정규화(생산 시트 썸네일·확정 기록이 쓴다)와 태블릿 검토 행도 key 로만 만든다."""
    from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
    from foms.services.drawing_workbench_display import resolve_row_image_list

    key = "orders/5/drawing/plan.png"
    poisoned = [{"key": key, "filename": "plan.png", "view_url": EVIL,
                 "download_url": f"https://{EVIL_HOST}/x"}]
    final = resolve_final_drawing_files({"drawing_current_files": poisoned})
    assert final[0]["view_url"] == f"/api/files/view/{key}"
    assert final[0]["download_url"] == f"/api/files/download/{key}"
    rows = resolve_row_image_list(5, poisoned, db_session, mobile_v2_active=True)
    assert rows[0]["view_url"] == f"/api/files/view/{key}"
    assert rows[0]["download_url"] == f"/api/files/download/{key}"


def test_erp_gateway_js_builds_urls_from_key_only():
    js = _read("static/js/orders/dashboard/erp-dashboard-gateway.js")
    body = js[js.index("function gatewayViewUrl"):js.index("function isGatewayImageFile")]
    assert "view_url" not in body and "download_url" not in body
    assert "REVISION_CANCELLED: '수정요청 취소'" in js
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    assert "erp-dashboard-gateway.js?v=20260929e" in entry


def test_cancel_guidance_no_longer_claims_files_are_deleted():
    """취소 안내 3곳이 "참고 파일 삭제" 라고 거짓 안내하지 않는다 + 핀 연쇄."""
    detail_dom = _read("static/js/orders/dashboard/erp-dashboard-detail-dom.js")
    drawing_js = _read("static/js/orders/dashboard/erp-dashboard-drawing.js")
    body = _read("templates/drawing/partials/workbench_detail_body.html")
    for text in (detail_dom, drawing_js, body):
        assert not re.search(r"참고 파일이 (함께 )?삭제", text)
    assert "취소해도 요청 기록과 참고 파일은 남고, 도면 전달 상태로 돌아갑니다." in detail_dom
    assert "요청 기록과 참고 파일은 남고, 도면 전달 상태로 돌아갑니다." in drawing_js
    assert "요청 기록과 참고 파일은 남고, 도면 전달 상태로 돌아갑니다." in body
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    assert "erp-dashboard-detail-dom.js?v=20260929l" in entry
    assert "erp-dashboard-drawing.js?v=20260929l" in entry
    assert "erp-dashboard-entry.js') }}?v=20260929l" in _read("templates/partials/shared/layout_scripts.html")
    grid = _read("templates/orders/partials/dashboard_grid.html")
    assert "REVISION_CANCELLED" in grid and "수정요청 취소" in grid


def test_detail_summary_latest_event_labels_cover_cancel_and_confirm():
    """ERP 상세 '도면 창구 요약' 최근 이벤트 라벨이 수정요청 취소·수령 확정·주문 변경을 안다(2b 리뷰 P3).

    수정요청 취소는 이력 끝에 REVISION_CANCELLED 를 붙이므로, 라벨 표에 없으면 취소한
    주문마다 '이력 없음 · <취소자>' 로 잘못 보인다.
    """
    js = _read("static/js/orders/dashboard/erp-dashboard-detail-dom.js")
    block = js[js.index("const latestEvent = drawHistory"):js.index("const latestWho")]
    for action, label in (
        ("TRANSFER", "도면 전달"),
        ("REQUEST_REVISION", "수정 요청"),
        ("CANCEL_TRANSFER", "전달 취소"),
        ("REVISION_CANCELLED", "수정요청 취소"),
        ("CONFIRM_RECEIPT", "수령 확정"),
        ("ERP_ORDER_CHANGED", "주문 변경"),
    ):
        assert f"{action}: '{label}'" in block, action
    assert "erp-dashboard-detail-dom.js?v=20260929e" in _read("static/js/orders/erp-dashboard-entry.js")
