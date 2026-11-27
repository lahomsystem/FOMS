"""PG 레인 — 도면 여러 장 주문의 공정 칸 켜기 거절(사장님 2026-11-27 "도면 두 장 이상이면 막기", 409 ``STEP_PER_SHEET``).

운영 DB(PostgreSQL · JSONB)에서 거절이 주문 쓰기 엔진의 콜백 안(잠금 아래)에서 되감겨 칸 · 버전 · 이벤트가 그대로인지, 도면 1장 주문은 지금처럼
켜지는지 본다. 도메인 시험은 ``tests/domains/test_production_per_sheet_only_1127.py``.
"""
from __future__ import annotations

from models import Order, OrderEvent, ProductionRun
from tests.postgres.test_production_part_marks_race_pg import _SEQ, _session, _user, pg_app  # noqa: F401  # pg_app = 고정물

MSG = "도면이 여러 장인 주문이에요. 도면 화면에서 한 장씩 완료해 주세요."


def _seed(pg_engine, n: int):
    _SEQ[0] += 1
    tag = f"ps{_SEQ[0]}"
    s = _session(pg_engine)
    try:
        foreman = _user(s, "박반장", None, tag, lead=True)
        files = [{"key": f"{tag}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{tag}-s{j}"} for j in range(n)]
        order = Order(received_date="2026-11-27", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                      structured_data={"workflow": {"stage": "PRODUCTION"}, "drawing_current_files": files,
                                       "parties": {"customer": {"name": "가짜고객"}}})
        s.add(order)
        s.flush()
        s.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        s.commit()
        return order.id, foreman
    finally:
        s.close()


def _state(pg_engine, order_id: int):
    s = _session(pg_engine)
    try:
        order = s.get(Order, order_id)
        steps = (order.structured_data.get("production") or {}).get("steps") or []
        checked = s.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STEP_CHECKED").count()
        return int(order.mutation_version or 0), [st.get("done") for st in steps], checked
    finally:
        s.close()


def _post(app, user, order_id: int, done: bool):
    client = app.test_client()
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    return client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": done})


def test_multi_sheet_turn_on_is_refused_and_rolled_back_on_pg(pg_engine, pg_app):
    order_id, foreman = _seed(pg_engine, 3)
    before = _state(pg_engine, order_id)
    res = _post(pg_app, foreman, order_id, True)
    assert res.status_code == 409 and res.get_json()["data"]["code"] == "STEP_PER_SHEET" and res.get_json()["error"] == MSG
    assert _state(pg_engine, order_id) == before  # 칸 · 버전 · 이벤트 그대로
    one_id, foreman1 = _seed(pg_engine, 1)  # 대조군 — 도면 1장은 지금처럼 켜진다
    version = _state(pg_engine, one_id)[0]
    assert _post(pg_app, foreman1, one_id, True).status_code == 200
    after = _state(pg_engine, one_id)
    assert after[0] == version + 1 and after[1][0] is True and after[2] == 1
