"""정산 얇은 문서 — **SQL 투영 == 파이썬 정본**이고 정산 응답이 그대로라는 증명 (PGTEST-00 lane).

SQLite 레인(``tests/domains/test_settlement_source.py``)은 투영을 파이썬 정본
(:func:`settlement_source.project_settlement_sd`)으로 하므로 "판정이 읽는 경로 ⊆ 투영"과
"투영 문서의 답 == 통째 원본의 답"만 증명한다. 진짜 SQL(``JSON_OBJECT … ABSENT ON NULL`` +
품목 원소 ``json_agg``)이 그 정본과 같은 문서를 내는지는 여기서만 잴 수 있다.

여기서 재는 것:

1. 표본 모양마다(명시적 null·dict 아닌 자리·빈 품목·dict 아닌 원소·빈 문서·문서 없음·
   dict 아닌 최상위 포함) SQL 투영 결과 == 파이썬 정본, ``json.dumps`` 문자열까지 같다.
2. 진짜 투영이 걸린 상태의 ``aggregate_settlement``·``list_settlement_rows`` == 옛 경로(통째 원본).
   음성 대조군 — 예약금 갈래를 뺀 투영이면 같은 비교가 갈린다.
3. 정산 조회가 낸 SQL 에 ``structured_data`` **본문 컬럼**이 없고, 원본은 행마다 한 번만 푼다
   (``#> '{}'`` + ``OFFSET 0`` 울타리 — 없으면 투영 식이 참조마다 TOAST 를 다시 푼다).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import event, select

from foms.services import settlement_aggregation, settlement_rows
from foms.services import settlement_source as ss
from models import Order
from tests.domains.settlement_source_helpers import SHAPES, seed_shapes, spec_without


@pytest.fixture
def sql_projection(pg_session):
    """SQL 투영이 실제로 걸리는 서버인지 확인한다(PostgreSQL 16+)."""
    if not ss.supports_sql_projection(pg_session):
        pytest.skip("PostgreSQL 16 미만 — JSON_OBJECT ABSENT ON NULL 이 없어 파이썬 투영으로 떨어진다")
    return pg_session


def _odd_roots(session) -> list[int]:
    """dict 가 아닌 최상위 문서(배열·문자열·숫자)도 그대로 돌아와야 한다."""
    ids = []
    for index, raw in enumerate(([1, {"items": [1]}], "문자", 7)):
        order = Order(received_date="2026-01-01", customer_name=f"SSRC-ODD-{index}",
                      phone="010-0000-0000", address="서울", product="붙박이장",
                      status="COMPLETED", is_erp_order=True, erp_stage_code="COMPLETED",
                      structured_data=raw)
        session.add(order)
        session.flush()
        ids.append(order.id)
    return ids


def test_sql_projection_equals_the_python_reference(sql_projection):
    """모양마다 SQL 투영 == 파이썬 정본 — 값·없는 키·null·dict 아닌 자리·원소 수·키 순서까지."""
    session = sql_projection
    ids = seed_shapes(session) + _odd_roots(session)

    # 통째 원본은 Core select 로 DB 에서 **다시** 읽는다(식별자 지도의 파이썬 dict 는 jsonb
    # 왕복 전 키 순서라 비교 기준이 못 된다).
    full = dict(session.execute(
        select(Order.id, Order.structured_data).where(Order.id.in_(ids))).all())
    rows = ss.fetch_settlement_rows(session, (Order.id, Order.customer_name),
                                    (Order.id.in_(ids),))

    assert len(rows) == len(ids) == len(SHAPES) + 5 + 3
    for row in rows:
        expected = ss.project_settlement_sd(full[row.id])
        assert row.structured_data == expected, row.customer_name
        assert (json.dumps(row.structured_data, ensure_ascii=False)
                == json.dumps(expected, ensure_ascii=False)), f"{row.customer_name}: 키 순서"
    thin = next(row for row in rows if row.customer_name == "SSRC-품목합-폴백-단가모양")
    assert "quests" not in thin.structured_data
    assert len(thin.structured_data["items"]) == len(SHAPES["품목합-폴백-단가모양"][0]["items"])
    assert thin.structured_data["items"][-1] == {}


def _outputs(session) -> tuple[list, list]:
    aggregates = [settlement_aggregation.aggregate_settlement(
        session, month_from=mf, month_to=mt, granularity=g)
        for mf, mt, g in (("2026-09", "2026-10", "day"), ("2025-11", "2026-10", "week"),
                          ("2030-01", "2030-01", "month"))]
    rows = [settlement_rows.list_settlement_rows(session, include_naver_settlement=inc, **case)
            for case in (dict(), dict(period="31"), dict(settlement="issued"),
                         dict(aging="D91_PLUS"))
            for inc in (False, True)]
    return aggregates, rows


def test_screen_outputs_match_the_full_document_path(sql_projection, monkeypatch):
    """진짜 SQL 투영의 정산 응답 == 옛 경로(통째 원본). 음성 대조군 포함."""
    session = sql_projection
    seed_shapes(session)

    projected = _outputs(session)
    assert projected[0][0]["kpi"]["completed_count"] > 0, "빈 결과끼리 같다는 거짓 통과"
    assert projected[1][0]["total_count"] == len(SHAPES)

    def _full_fetch(db, columns, criteria):
        return db.query(*columns, Order.structured_data).filter(*criteria).all()

    monkeypatch.setattr(settlement_aggregation, "fetch_settlement_rows", _full_fetch)
    monkeypatch.setattr(settlement_rows, "fetch_settlement_rows", _full_fetch)
    full = _outputs(session)
    assert json.dumps(projected, ensure_ascii=False) == json.dumps(full, ensure_ascii=False)

    # 음성 대조군: 예약금 갈래를 뺀 SQL 투영이면 같은 비교가 갈린다.
    dropped = spec_without(ss.SETTLEMENT_SD_SPEC, ("payment",))

    def _dropped_fetch(db, columns, criteria):
        return db.execute(ss.settlement_rows_statement(columns, criteria, dropped)).all()

    monkeypatch.setattr(settlement_aggregation, "fetch_settlement_rows", _dropped_fetch)
    monkeypatch.setattr(settlement_rows, "fetch_settlement_rows", _dropped_fetch)
    assert json.dumps(_outputs(session), ensure_ascii=False) != json.dumps(full, ensure_ascii=False)


def test_settlement_reads_never_select_the_document_body(sql_projection, pg_engine):
    """정산 조회의 SQL 에 문서 본문 컬럼이 없고, 원본은 울타리 안에서 한 번만 푼다."""
    session = sql_projection
    seed_shapes(session)
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        settlement_aggregation.aggregate_settlement(
            session, month_from="2026-09", month_to="2026-10", granularity="day")
        settlement_rows.list_settlement_rows(session, include_naver_settlement=True)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    body = re.compile(r"orders\.structured_data\s+AS\b", re.IGNORECASE)
    assert not [sql for sql in seen if body.search(sql)], "정산 조회가 문서 본문을 실었다"
    projected = [sql for sql in seen if "JSON_OBJECT(" in sql]
    assert len(projected) == 3, "모집단 2회(집계·실무) + 단계 카드 1회가 모두 투영이어야 한다"
    for sql in projected:
        # 푸는 자리는 하나뿐이고, 바깥 식은 그 풀린 사본(settle_src.sd)만 본다.
        assert sql.count("#> '{}'") == 1, sql
        assert "OFFSET" in sql.upper(), "울타리가 없으면 바깥 식이 원본을 다시 푼다"
        outer = sql.split("FROM (", 1)[0]
        assert "orders.structured_data" not in outer, "바깥 식이 원본 컬럼을 직접 참조한다"


def test_empty_object_node_is_valid_sql_and_matches_python(sql_projection):
    """남길 키가 없는 마디(``{}``)도 문법 오류 없이 빈 객체를 낸다 — 음성 대조군 나무가 이 모양이다."""
    session = sql_projection
    ids = seed_shapes(session)
    spec = {"schedule": {"construction": {}}, "payment": {}}

    full = dict(session.execute(
        select(Order.id, Order.structured_data).where(Order.id.in_(ids))).all())
    rows = session.execute(ss.settlement_rows_statement(
        (Order.id,), (Order.id.in_(ids),), spec)).all()

    assert len(rows) == len(ids)
    for row in rows:
        assert row.structured_data == ss.project_settlement_sd(full[row.id], spec), row.id
