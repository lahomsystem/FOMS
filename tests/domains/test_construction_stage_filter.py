"""D6: 시공 대시보드 단계 필터 flat 컬럼(erp_stage_code) 전환 스코프 가드.

`apply_construction_stage_sql_filter`는 JSONB path cast
(``structured_data['workflow']['stage']``, 인덱스 없음)를 flat 컬럼
``Order.erp_stage_code``(``ix_orders_erp_stage_code``)로 전환했다.

이 테스트는 **스코프 값이 전환 전 JSONB 필터와 1:1 동일**함을 고정한다
(순수 인덱스 전환 — 시공탭에 들어오던 주문 집합 불변).
- 시공대기/시공중 → CONSTRUCTION / 시공 / CONSTRUCTING
- 시공완료      → COMPLETED / 완료 / AS_WAIT / CS
그 외(MEASURE/RECEIVED/NULL 등)는 어떤 시공 탭 필터에도 걸리지 않는다.

seed 함정(Wave 3 교훈): flat 필터는 ``erp_stage_code``를 읽으므로 seed가
structured_data만 넣고 이 컬럼을 비우면 필터가 전부 걸러 오탐이 난다.
운영 진실(sync가 workflow.stage 원문을 erp_stage_code로 복사)에 맞춰
seed에 ``erp_stage_code``를 명시 세팅한다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction_read_model import apply_construction_stage_sql_filter
from models import Order, User

# 전환 전 JSONB 필터가 매칭하던 원값(JSON 따옴표 제거) — 스코프 SSOT.
WAIT_CONSTRUCT_STAGES = ["CONSTRUCTION", "시공", "CONSTRUCTING"]
COMPLETE_STAGES = ["COMPLETED", "완료", "AS_WAIT", "CS"]
# 시공 탭 스코프 밖(어떤 단계 필터에도 걸리면 안 됨).
OUT_OF_SCOPE_STAGES = ["MEASURE", "RECEIVED", "PRODUCTION", None]


def _make_user() -> User:
    user = User(
        username="construction_stage_filter_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CONSTRUCTION",
        name="시공담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _seed(stage: str | None) -> int:
    """운영 진실 정렬: erp_stage_code + structured_data.workflow.stage 동일 값."""
    order = Order(
        received_date="2026-06-01",
        customer_name=f"시공-{stage}",
        phone="010-9000-0000",
        address="서울시 시공구 1",
        product="싱크대",
        status="IN_CONSTRUCTION",
        manager_name="시공담당",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={"workflow": {"stage": stage} if stage else {}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _seed_all() -> dict[str | None, int]:
    ids: dict[str | None, int] = {}
    for stage in WAIT_CONSTRUCT_STAGES + COMPLETE_STAGES + OUT_OF_SCOPE_STAGES:
        ids[stage] = _seed(stage)
    return ids


def _filtered_ids(f_stage: str, seeded_ids: list[int]) -> set[int]:
    base = db_session.query(Order).filter(Order.id.in_(seeded_ids))
    q = apply_construction_stage_sql_filter(base, f_stage)
    return {row.id for row in q.with_entities(Order.id).all()}


def test_wait_and_constructing_tab_scope(app):
    """시공대기/시공중 탭 → CONSTRUCTION/시공/CONSTRUCTING만, 완료·범위밖 제외."""
    with app.app_context():
        _make_user()
        ids = _seed_all()
        all_ids = list(ids.values())
        expected = {ids[s] for s in WAIT_CONSTRUCT_STAGES}
        for tab in ("시공대기", "시공중"):
            got = _filtered_ids(tab, all_ids)
            assert got == expected, f"{tab} 스코프 불일치: got={got} expected={expected}"
            # 완료/범위밖은 절대 포함 금지
            for s in COMPLETE_STAGES + OUT_OF_SCOPE_STAGES:
                assert ids[s] not in got, f"{tab}에 {s} 누출"


def test_complete_tab_scope(app):
    """시공완료 탭 → COMPLETED/완료/AS_WAIT/CS만, 시공중·범위밖 제외."""
    with app.app_context():
        _make_user()
        ids = _seed_all()
        all_ids = list(ids.values())
        expected = {ids[s] for s in COMPLETE_STAGES}
        got = _filtered_ids("시공완료", all_ids)
        assert got == expected, f"시공완료 스코프 불일치: got={got} expected={expected}"
        for s in WAIT_CONSTRUCT_STAGES + OUT_OF_SCOPE_STAGES:
            assert ids[s] not in got, f"시공완료에 {s} 누출"


def test_empty_stage_returns_all(app):
    """f_stage 없으면 단계 필터 미적용(원 쿼리 그대로)."""
    with app.app_context():
        _make_user()
        ids = _seed_all()
        all_ids = list(ids.values())
        got = _filtered_ids("", all_ids)
        assert got == set(all_ids)
        # 인식 못하는 값도 필터 미적용(원본 동작 보존)
        assert _filtered_ids("존재하지않는탭", all_ids) == set(all_ids)


def test_scope_values_are_index_column_not_jsonb(app):
    """스코프가 flat erp_stage_code로 좁혀지고, JSONB만 있는 행은 안 걸림(오탐 가드).

    erp_stage_code=NULL이면서 structured_data.workflow.stage='CONSTRUCTION'인
    행은 flat 필터에 걸리지 않아야 한다(전환의 본질 — 인덱스 컬럼 기준).
    """
    with app.app_context():
        _make_user()
        # flat 컬럼만 세팅(정상 운영 진실)
        good = _seed("CONSTRUCTION")
        # 함정 케이스: JSONB만 있고 flat은 NULL
        jsonb_only = Order(
            received_date="2026-06-01",
            customer_name="jsonb-only",
            phone="010-9000-0001",
            address="서울시 시공구 2",
            product="싱크대",
            status="IN_CONSTRUCTION",
            manager_name="시공담당",
            is_erp_order=True,
            erp_stage_code=None,
            structured_data={"workflow": {"stage": "CONSTRUCTION"}},
        )
        db_session.add(jsonb_only)
        db_session.commit()
        got = _filtered_ids("시공대기", [good, jsonb_only.id])
        assert good in got
        assert jsonb_only.id not in got, "JSONB-only 행이 flat 필터에 걸림(인덱스 전환 위배)"
