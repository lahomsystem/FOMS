"""PG 레인 — 도면이 연 제작 시작 되돌리기(사장님 2026-11-27 "제작 대기로 저절로 돌아가게").

운영 DB(PostgreSQL)에서 ① 첫 도면 [작업 시작] → [시작 취소]가 회차를 닫고(SUPERSEDED) 이벤트 ``PRODUCTION_CANCELLED``
(``via:'part_marks'`` · JSONB 에 회차 id 글)를 남기며 다시 [작업 시작]하면 새 회차가 열리는지(부분 유일 색인), ② 그 판정이 주문 행 잠금
아래에서 도는지 본다 — 연결 B 가 주문 행을 ``FOR UPDATE`` 로 쥐고 **다른 도면**을 잡은 뒤 커밋 전에 기다리는 동안 실제 Flask 라우트
(스레드 A)가 첫 도면을 [시작 취소]한다. A 는 잠금에서 기다렸다가 B 의 표시 줄을 보고 되돌리지 않아야 한다(작업 중 도면이 있는데 제작 대기로
돌아가면 안 된다). 도메인 시험은 ``tests/domains/test_production_start_rollback_1127.py``.
``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다.
"""
from __future__ import annotations

from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderEvent, ProductionPartMark, ProductionRun
from tests.postgres.test_production_part_marks_race_pg import (  # noqa: F401  # pg_app = 고정물
    _SEQ,
    _call_route,
    _race,
    _session,
    _user,
    pg_app,
)

ONE = "/api/production/part-marks"


def _seed(pg_engine):
    """제작 대기 주문 1건(도면 2장 · 회차 없음) + 엣지 계정 둘."""
    _SEQ[0] += 1
    tag = f"rb{_SEQ[0]}"
    s = _session(pg_engine)
    try:
        park, kim = _user(s, "박엣지", "edge", tag), _user(s, "김민준", "edge", tag)
        files = [{"key": f"{tag}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{tag}-s{j}"} for j in range(2)]
        steps = [{"key": k, "label": k, "done": False, "at": None, "by_name": None} for k in ("cut", "edge", "assemble", "inspect")]
        order = Order(received_date="2026-11-27", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                      structured_data={"workflow": {"stage": "PRODUCTION"}, "drawing_current_files": files,
                                       "parties": {"customer": {"name": "가짜고객"}}, "production": {"steps": steps}})
        s.add(order)
        s.commit()
        return order.id, [f["key"] for f in files], {"park": park, "kim": kim}
    finally:
        s.close()


def _body(order_id: int, key: str, action: str, seen: str, seen_me: str) -> dict:
    return {"order_id": order_id, "drawing_key": key, "part": "edge", "action": action, "seen": seen, "seen_me": seen_me}


def _press(app, user, body: dict) -> dict:
    out: dict = {}
    _call_route(app, user, ONE, body, out)
    assert out["status"] == 200, out
    return out["json"]["data"]


def _state(pg_engine, order_id: int):
    """(지금 회차 수, 회차 상태들, 취소 이벤트 payload 들, 시작 이벤트 수)."""
    s = _session(pg_engine)
    try:
        runs = s.query(ProductionRun).filter_by(order_id=order_id).order_by(ProductionRun.started_at).all()
        cancelled = [e.payload for e in s.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_CANCELLED")
                     .order_by(OrderEvent.id)]
        started = s.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STARTED").count()
        return sum(1 for r in runs if r.is_current), [(r.id, r.status) for r in runs], cancelled, started
    finally:
        s.close()


def test_card_start_then_release_closes_run_and_retake_opens_new_one_on_pg(pg_engine, pg_app):
    order_id, keys, who = _seed(pg_engine)
    assert _press(pg_app, who["park"], _body(order_id, keys[0], "take", "none", "none"))["run_started"] is True
    data = _press(pg_app, who["park"], _body(order_id, keys[0], "release", "need", "held"))
    assert (data["run_cancelled"], data["run_started"], data["mark"]["state"]) == (True, False, "none")
    current, runs, cancelled, started = _state(pg_engine, order_id)
    assert current == 0 and [status for _, status in runs] == ["SUPERSEDED"] and started == 1
    assert cancelled == [{"domain": "PRODUCTION_DOMAIN", "action": "PRODUCTION_CANCELLED", "reason": "", "rework_cleared": False,
                          "hold_released": False, "run_id": runs[0][0], "via": "part_marks"}]
    again = _press(pg_app, who["park"], _body(order_id, keys[0], "release", "need", "held"))  # 같은 요청 두 번 = 바뀜 없음
    assert (again["changed"], again["run_cancelled"]) == (False, False) and len(_state(pg_engine, order_id)[2]) == 1
    assert _press(pg_app, who["park"], _body(order_id, keys[0], "take", "none", "none"))["run_started"] is True
    current, runs, cancelled, started = _state(pg_engine, order_id)
    assert current == 1 and sorted(status for _, status in runs) == ["IN_PROGRESS", "SUPERSEDED"] and started == 2


def test_release_waits_for_another_take_and_keeps_run_on_pg(pg_engine, pg_app):
    order_id, keys, who = _seed(pg_engine)
    assert _press(pg_app, who["park"], _body(order_id, keys[0], "take", "none", "none"))["run_started"] is True

    def take_other(s, _mark):  # B = 김민준이 다른 도면(2번)을 잡는다 — 커밋 전까지 A 는 못 본다
        now = now_utc_naive()
        s.add(ProductionPartMark(order_id=order_id, drawing_key=keys[1], part="edge", state="NEED",
                                 picked_by_user_id=who["kim"][0], picked_by_name="김민준", picked_at=now,
                                 updated_by_user_id=who["kim"][0], updated_at=now))

    out = _race(pg_engine, pg_app, order_id, keys[0], take_other, who["park"], ONE,
                _body(order_id, keys[0], "release", "need", "held"))
    assert out["status"] == 200, out
    data = out["json"]["data"]
    assert (data["mark"]["state"], data["run_cancelled"]) == ("none", False)  # B 의 작업 중 도면이 있어 되돌리지 않는다
    current, runs, cancelled, _started = _state(pg_engine, order_id)
    assert current == 1 and [status for _, status in runs] == ["IN_PROGRESS"] and cancelled == []
