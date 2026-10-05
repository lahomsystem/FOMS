"""생산 탭 렌더 전 304 키 — PostgreSQL ``xmin`` 지문 (하트비트 설계서 2026-10-05 §3.3 C).

SQLite 레인은 ``xmin`` 이 없어 "모든 열 값을 이은 문자열"로 대신 시험한다. 운영 경로(``xmin``)가 실제로
도는지, 그리고 설계서가 기대는 성질을 여기서 고정한다:

- ORM 을 거치지 않는 raw SQL 쓰기(워커·우회 경로)도 지문을 바꾼다.
- 사용자 표는 ``xmin`` 이 아니라 화면에 쓰는 열의 값으로 뜬다 — ``last_login`` 쓰기(5분마다)에 안 흔들린다.
- 설정은 값 digest, 이벤트·첨부·회차는 그 주문들로 좁힌 ``xmin`` 지문이다.
- 지문 SQL 은 두 번(창 1회 + 딸린 표 UNION ALL 1회)이다.

각 쓰기는 따로 커밋한다 — 한 트랜잭션 안의 갱신은 같은 ``xmin`` 을 가진다(운영 쓰기는 늘 따로 커밋된다).
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from foms.services import production_fragment_version as pfv
from foms.services.datetime_kst import get_today_kst
from foms.services.production_read_model import apply_production_dashboard_sort, build_production_orders_query
from models import Order, OrderEvent, SystemSetting, User
from tests.postgres.conftest import _reset_pg_database_to_fresh


def _seed(engine) -> dict[str, Any]:
    with Session(bind=engine) as s:
        user = User(username="pgfv_admin", password=generate_password_hash("x"), role="ADMIN", team="CS",
                    name="관리자", is_active=True)
        s.add(user)
        orders = []
        for i, stage in enumerate(("CONFIRM", "PRODUCTION", "CONSTRUCTION")):
            cdate = (datetime.date(2026, 10, 5) + datetime.timedelta(days=i)).isoformat()
            orders.append(Order(
                received_date="2026-10-01", customer_name=f"고객{i}", phone="010", address="서울", product="장",
                status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=cdate,
                structured_data={"workflow": {"stage": stage}, "parties": {"customer": {"name": f"고객{i}"}}},
            ))
        s.add_all(orders)
        s.add(SystemSetting(setting_key="erp_shipment_settings", setting_value={"measurement_manager": []}))
        s.commit()
        return {"user": user.id, "orders": [o.id for o in orders]}


def _fingerprints(engine, user_id: int, kanban: bool = True) -> dict[str, Any]:
    with Session(bind=engine) as s:
        user = s.get(User, user_id)
        sorted_q = apply_production_dashboard_sort(build_production_orders_query(s, user, "", "", False), "", "asc")
        window, ids = pfv._window(s, sorted_q, kanban, total=3, page=1, dialect="postgresql")
        deps = pfv._dependents(s, ids, kanban, "postgresql")
        return {"window": window, "ids": ids, **deps}


def _exec(engine, sql: str, **params: Any) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql), params)


@pytest.fixture
def board(pg_engine) -> dict[str, Any]:
    _reset_pg_database_to_fresh(pg_engine)  # 쓰기를 커밋하므로 테스트마다 출발선을 되돌린다
    return _seed(pg_engine)


def test_window_uses_xmin_and_matches_render_order(pg_engine, board):
    fp = _fingerprints(pg_engine, board["user"])
    assert fp["ids"] == board["orders"], "시공일 빠른 순 — 렌더와 같은 정렬"
    assert all(isinstance(ver, str) and ver.isdigit() for _tag, _oid, ver in fp["window"]), fp["window"]


def test_raw_sql_write_outside_the_orm_changes_the_window(pg_engine, board):
    before = _fingerprints(pg_engine, board["user"])
    _exec(pg_engine, "UPDATE orders SET customer_name = '우회쓰기' WHERE id = :id", id=board["orders"][1])
    after = _fingerprints(pg_engine, board["user"])
    assert before["window"] != after["window"]
    assert before["events"] == after["events"]


def test_event_attachment_and_run_rows_change_their_own_fingerprint(pg_engine, board):
    oid = board["orders"][1]
    before = _fingerprints(pg_engine, board["user"])
    with Session(bind=pg_engine) as s:
        s.add(OrderEvent(order_id=oid, event_type="PRODUCTION_CHANGE_ACK", payload={}))
        s.commit()
    mid = _fingerprints(pg_engine, board["user"])
    assert mid["events"] != before["events"] and mid["window"] == before["window"]
    _exec(pg_engine, "INSERT INTO order_attachments (order_id, filename, file_type, category, storage_key, file_size, "
          "created_at) VALUES (:id, 'a.jpg', 'image', 'measurement', 'k', 1, now())", id=oid)
    after_att = _fingerprints(pg_engine, board["user"])
    assert after_att["att"] != mid["att"]
    _exec(pg_engine, "UPDATE order_attachments SET deleted_at = now() WHERE order_id = :id", id=oid)
    assert _fingerprints(pg_engine, board["user"])["att"] != after_att["att"], "soft delete 도 지문을 바꾼다"


def test_users_digest_ignores_last_login_but_sees_names(pg_engine, board):
    before = _fingerprints(pg_engine, board["user"])
    _exec(pg_engine, "UPDATE users SET last_login = now() WHERE id = :id", id=board["user"])
    assert _fingerprints(pg_engine, board["user"])["users"] == before["users"], "last_login 은 화면에 안 쓴다"
    _exec(pg_engine, "UPDATE users SET name = '새이름' WHERE id = :id", id=board["user"])
    assert _fingerprints(pg_engine, board["user"])["users"] != before["users"]


def test_settings_value_digest_and_tombstones(pg_engine, board):
    before = _fingerprints(pg_engine, board["user"])
    _exec(pg_engine, "UPDATE system_settings SET setting_value = CAST(:v AS jsonb) "
          "WHERE setting_key = 'erp_shipment_settings'", v='{"measurement_manager": [{"name": "김", "phone": "1"}]}')
    after = _fingerprints(pg_engine, board["user"])
    assert after["settings"] != before["settings"]
    today = get_today_kst().isoformat()
    _exec(pg_engine, "UPDATE orders SET status = 'DELETED', deleted_at = :d WHERE id = :id",
          d=f"{today} 09:00:00", id=board["orders"][2])
    gone = _fingerprints(pg_engine, board["user"])
    assert gone["tomb"].startswith("1:") and gone["ids"] == board["orders"][:2]


def test_fingerprint_is_two_statements(pg_engine, board):
    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if "xmin" in statement:
            statements.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _count)
    try:
        _fingerprints(pg_engine, board["user"], kanban=True)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _count)
    assert len(statements) == 2, statements
    assert "UNION ALL" in statements[1]
