"""PG 레인 — 반장이 바로 완료한 도면의 [완료 취소] = 한 번에 미정(사장님 2026-11-27 "한 번에 미정으로").

운영 DB(PostgreSQL · JSONB ``holders``)에서 시작한 때 == 완료한 때 판정(같은 요청이 쓴 ISO 글)이 그대로 남아, 취소 한 번에 표시 줄이
NONE · 목록 빔 · 감사 한 줄이 되고, 도면 1장 주문의 공정 칸이 꺼지는지 본다. 대조: [작업 시작] 뒤 따로 [완료]한 도면은 작업 중으로.
도메인 시험은 ``tests/domains/test_production_direct_done_undo_1127.py``.
"""
from __future__ import annotations

from models import Order, ProductionPartMark, SecurityLog
from tests.postgres.test_production_part_marks_race_pg import _SEQ, _session, _user, pg_app  # noqa: F401  # pg_app = 고정물

ONE = "/api/production/part-marks"


def _seed(pg_engine):
    _SEQ[0] += 1
    tag = f"du{_SEQ[0]}"
    s = _session(pg_engine)
    try:
        lead = _user(s, "박반장", None, tag, lead=True)
        files = [{"key": f"{tag}/d0.png", "filename": "d0.png", "sheet_id": f"{tag}-s0"}]
        steps = [{"key": k, "label": k, "done": False, "at": None, "by_name": None} for k in ("cut", "edge", "assemble", "inspect")]
        order = Order(received_date="2026-11-27", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                      structured_data={"workflow": {"stage": "PRODUCTION"}, "drawing_current_files": files,
                                       "parties": {"customer": {"name": "가짜고객"}}, "production": {"steps": steps}})
        s.add(order)
        s.commit()
        return order.id, files[0]["key"], lead
    finally:
        s.close()


def _press(app, user, order_id: int, key: str, action: str, seen: str, seen_me: str):
    client = app.test_client()
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    return client.post(ONE, json={"order_id": order_id, "drawing_key": key, "part": "cut", "action": action, "seen": seen,
                                  "seen_me": seen_me})


def _state(pg_engine, order_id: int):
    s = _session(pg_engine)
    try:
        saved = s.query(ProductionPartMark).filter_by(order_id=order_id, part="cut").one()
        step = next(st for st in s.get(Order, order_id).structured_data["production"]["steps"] if st["key"] == "cut")
        audits = s.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order_id).count()
        return saved.state, saved.holders, saved.picked_by_name, step["done"], audits
    finally:
        s.close()


def test_direct_done_undo_is_unseen_in_one_press_on_pg(pg_engine, pg_app):
    order_id, key, lead = _seed(pg_engine)
    assert _press(pg_app, lead, order_id, key, "check", "none", "none").status_code == 200
    state, holders, _, step_done, _ = _state(pg_engine, order_id)
    assert state == "DONE" and step_done is True and holders[0]["at"] == holders[0]["done_at"]  # JSONB 에 같은 글로 남음
    res = _press(pg_app, lead, order_id, key, "undo", "done", "done")
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "none"
    assert _state(pg_engine, order_id) == ("NONE", [], None, False, 2)  # 감사 = 완료 한 줄 + 취소 한 줄

    other_id, other_key, lead2 = _seed(pg_engine)  # 대조 — [작업 시작] 뒤 따로 [완료] = 작업 중으로
    assert _press(pg_app, lead2, other_id, other_key, "take", "none", "none").status_code == 200
    assert _press(pg_app, lead2, other_id, other_key, "done", "need", "held").status_code == 200
    res = _press(pg_app, lead2, other_id, other_key, "undo", "done", "done")
    assert res.status_code == 200 and res.get_json()["data"]["mark"]["state"] == "need"
    state, holders, picked, _, _ = _state(pg_engine, other_id)
    assert (state, picked, [h["done_at"] for h in holders]) == ("NEED", "박반장", [None])
