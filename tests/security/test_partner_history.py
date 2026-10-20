"""PARTNER-FOMS 3-3: 협력사 주문 화면 도면 미리보기 · 이력 탭.

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.7 · §15.
이력에는 우리 직원 이름 · 도면팀 메모 · 우리 쪽 수정 요청 내용이 없어야 한다(협력사가 보낸 수정 요청은 대조군).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.partners.history import partner_order_history
from models import Order, OrderEvent, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    _user,
    world,
)


def _order(app, partner_id) -> int:
    resp = _create(app, partner_id)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]["order_id"]


def _patch_sd(order_id, **values):
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd.update(values)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _event(order_id, event_type, payload, at, user_id=None):
    db_session.add(OrderEvent(order_id=order_id, event_type=event_type, payload=payload,
                              created_by_user_id=user_id, created_at=at))
    db_session.commit()


def _seed_history(app, world) -> tuple[int, int]:
    """보냄 → 도면 작업 → 1차 → 우리 쪽 수정 요청 → 2차 → 협력사 수정 요청 → 3차 → 확정 → 승인 → 시공일 → 시공 끝 → AS."""
    order_id = _order(app, world["partner_a"])
    drafter = _user(team="DRAWING", name="도면박")
    _to_stage(order_id, "COMPLETED")
    order = db_session.get(Order, order_id)
    intake = dict(order.structured_data["partner_intake"])
    intake["submitted_at"] = "2026-10-19T09:00:00+09:00"
    intake["item_edits"] = [{"at": "2026-10-19T09:30:00+09:00", "by_user_id": world["partner_a2"], "by_name": "가나 둘째"}]
    transfer = {"action": "TRANSFER", "by_user_id": drafter.id, "by_user_name": "도면박", "note": "내부 메모 abc", "files_count": 2}
    _patch_sd(
        order_id,
        partner_intake=intake,
        drawing_transfer_history=[
            {**transfer, "transferred_at": "2026-10-19 02:00:00"},
            {"action": "REQUEST_REVISION", "by_user_id": world["staff"], "by_user_name": "영업김", "at": "2026-10-19 03:00:00", "note": "우리끼리 메모"},
            {**transfer, "transferred_at": "2026-10-19 04:00:00"},
            {"action": "REQUEST_REVISION", "by_user_id": world["partner_a"], "by_user_name": "가나 직원 (협력사)", "at": "2026-10-19 05:00:00", "note": "서랍 3단으로"},
            {**transfer, "transferred_at": "2026-10-19 06:00:00"},
            {"action": "CONFIRM_RECEIPT", "by_user_id": world["staff"], "by_user_name": "영업김", "at": "2026-10-19 07:00:00", "note": "도면 수령 확인"},
        ],
        blueprint={"customer_confirmed": True, "confirmed_at": "2026-10-19T08:00:00", "confirmed_by": "가나 직원 (협력사)"},
        as_lifecycle={"current_cycle_id": "c1", "cycles": [{"cycle_id": "c1", "transitions": [
            {"command": "AS_REGISTER", "to": "RECEIVED", "actor_id": world["partner_a"], "at": "2026-10-23T01:00:00", "payload": {}},
            {"command": "AS_SCHEDULE", "to": "RECEIVED", "actor_id": world["staff"], "at": "2026-10-23T02:00:00",
             "payload": {"visit_date": "2026-10-25", "visit_time": "14:00"}},
            {"command": "AS_COMPLETE", "to": "COMPLETED", "actor_id": world["staff"], "at": "2026-10-25T06:00:00", "payload": {"note": "부품비 우리 부담"}},
        ]}]},
    )
    _event(order_id, "STAGE_CHANGED", {"from": "RECEIVED", "to": "DRAWING", "reason": "내부 사유 xyz"}, dt.datetime(2026, 10, 19, 1, 0), world["staff"])
    _event(order_id, "CONSTRUCTION_DATE_CHANGED", {"from": "", "to": "2026-10-22"}, dt.datetime(2026, 10, 19, 9, 0), world["staff"])
    _event(order_id, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-10-22", "to": "2026-10-22, 2026-10-23"}, dt.datetime(2026, 10, 20, 9, 0))
    _event(order_id, "CONSTRUCTION_COMPLETED", {"memo": "시공 메모 비밀"}, dt.datetime(2026, 10, 22, 9, 0), world["staff"])
    return order_id, drafter.id


def test_history_lines_partner_projection(app, world):
    order_id, _ = _seed_history(app, world)
    lines = partner_order_history(db_session, db_session.get(Order, order_id))
    assert all(set(x) == {"at", "kind", "title", "who", "detail"} for x in lines)
    titles = [x["title"] for x in lines]
    assert titles[:3] == ["AS 처리 끝", "AS 방문 예정", "AS 접수"]  # 최근이 위
    assert titles[-1] == "주문 보냄"
    assert [t for t in titles if t.endswith("차 도면 올라옴")] == ["3차 도면 올라옴", "2차 도면 올라옴", "1차 도면 올라옴"]
    by_title = {x["title"]: x for x in lines}
    assert by_title["1차 도면 올라옴"]["at"] == "2026-10-19 11:00" and by_title["1차 도면 올라옴"]["who"] == "저희 도면팀"  # KST
    assert by_title["이대로 만들어 주세요"]["who"] == "가나 직원" and by_title["이대로 만들어 주세요"]["detail"] == "3차 도면으로 제작"
    assert by_title["시공일 정해짐"]["detail"] == "2026-10-22"
    assert by_title["시공일 바뀜"]["detail"] == "2026-10-22 → 2026-10-22, 2026-10-23"
    assert by_title["AS 방문 예정"]["detail"] == "2026-10-25 14:00" and by_title["AS 접수"]["who"] == "가나 직원"
    assert {"주문 확인 · 도면 작업 시작", "도면 확정 · 협력사 확인 차례", "시공 끝", "품목 고침"} <= set(titles)
    revisions = [x for x in lines if x["title"] == "수정 요청"]
    assert [(x["who"], x["detail"]) for x in revisions] == [("가나 직원", "서랍 3단으로"), ("저희 담당자", "")]


def test_history_tab_hides_our_staff_and_internal_notes(app, world):
    order_id, _ = _seed_history(app, world)
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert 'data-pp-tab="history"' in html and "data-pp-history" in html
    history = html[html.index("data-pp-history"):]
    assert "서랍 3단으로" in history and "가나 둘째" in history  # 협력사 몫은 보인다(대조군)
    for secret in ("도면박", "영업김", "내부 메모 abc", "우리끼리 메모", "내부 사유 xyz", "시공 메모 비밀", "부품비"):
        assert secret not in html, secret
    other = _client(app, db_session.get(User, world["partner_b"])).get(f"/partner/orders/{order_id}")
    assert other.status_code == 404


def test_drawing_tab_gallery_for_images_and_file_rows_for_pdf(app, world):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "CONFIRM")
    base = f"orders/{order_id}/drawing"
    _patch_sd(
        order_id,
        drawing_status="TRANSFERRED",
        drawing_current_files=[
            {"key": f"{base}/plan-a.png", "filename": "plan-a.png"},
            {"key": f"{base}/plan-b.jpg", "filename": "plan-b.jpg"},
            {"key": f"{base}/detail.pdf", "filename": "detail.pdf"},
        ],
        drawing_transfer_history=[{"action": "TRANSFER", "transferred_at": "2026-10-20 05:05:00", "files_count": 3}],
    )
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/orders/{order_id}").get_data(as_text=True)
    gallery = html[html.index("data-pp-drawing-gallery"):html.index("data-pp-drawing-files")]
    assert gallery.count("data-foms-lightbox-src=") == 2 and f"/api/files/view/{base}/plan-a.png" in gallery
    assert f"/api/files/download/{base}/plan-b.jpg" in gallery and "detail.pdf" not in gallery
    files = html[html.index("data-pp-drawing-files"):]
    assert f"/api/files/view/{base}/detail.pdf" in files[:400]
    assert "1차 · 10-20 14:05 올라옴" in html and "js/foms/lightbox.js" in html


def test_drawing_tab_without_images_skips_gallery_and_lightbox(app, world):
    order_id = _order(app, world["partner_a"])
    _to_stage(order_id, "CONFIRM")
    _patch_sd(order_id, drawing_status="TRANSFERRED",
              drawing_current_files=[{"key": f"orders/{order_id}/drawing/final.pdf", "filename": "final.pdf"}])
    html = _client(app, db_session.get(User, world["partner_a"])).get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "data-pp-drawing-gallery" not in html and "js/foms/lightbox.js" not in html
    assert "data-pp-drawing-files" in html and "final.pdf" in html
