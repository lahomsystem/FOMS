"""처리 목록 축소 스냅샷 — **SQL 투영 == 파이썬 정본**(키 순서까지)이라는 증명 (PGTEST-00 lane).

SQLite 레인은 투영을 파이썬 정본(:func:`naver_list_snapshot.project_list_snapshot`)으로 하므로
"목록이 읽는 경로 ⊆ 투영"과 "투영 행 목록 == 통째 원본 목록"만 증명한다. 진짜 SQL
(``JSON_OBJECT … ABSENT ON NULL``)이 그 정본과 같은 문서를 내는지는 여기서만 잴 수 있다.

여기서 재는 것:

1. 표본 모양마다(평평한 응답·dict 아닌 ``productOrder``·명시적 null·빈 원본·원본 없음 포함)
   SQL 투영 결과 == 파이썬 정본, ``json.dumps`` 문자열까지 같다(키 순서).
2. 진짜 투영이 걸린 상태에서 ``_work_groups(display=True)`` == 옛 경로(ORM 통째).
3. 목록 경로가 낸 SQL 에 ``raw_snapshot`` **본문 컬럼**이 없고, 원본은 행마다 한 번만 푼다
   (``#> '{}'`` + ``OFFSET 0`` 울타리 — 없으면 투영 식이 참조마다 TOAST 를 다시 푼다).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import event, select

from models import ExternalOrderLink
from tests.services.integrations.naver_list_snapshot_helpers import SHAPES, seed_shapes


@pytest.fixture
def sql_projection(pg_session):
    """SQL 투영이 실제로 걸리는 서버인지 확인한다(PostgreSQL 16+)."""
    from foms.web.admin.naver_list_snapshot import supports_sql_projection

    if not supports_sql_projection(pg_session):
        pytest.skip("PostgreSQL 16 미만 — JSON_OBJECT ABSENT ON NULL 이 없어 파이썬 투영으로 떨어진다")
    return pg_session


def _odd_rows(session) -> None:
    """dict 가 아닌 원본(배열·문자열·숫자)도 그대로 돌아와야 한다."""
    for index, raw in enumerate(([1, {"a": 2}], "문자", 7)):
        session.add(ExternalOrderLink(channel="NAVER", external_id=f"LS-ODD-{index}",
                                      external_order_no="", sync_status="COLLECTED",
                                      place_order_status="NOT_YET", raw_snapshot=raw))
    session.flush()


def test_sql_projection_equals_the_python_reference(sql_projection):
    """모양마다 SQL 투영 == 파이썬 정본 — 값·없는 키·null·dict 아닌 자리·키 순서까지."""
    from foms.web.admin.naver_list_snapshot import fetch_list_links, project_list_snapshot

    session = sql_projection
    seed_shapes(session, commit=False)
    _odd_rows(session)

    # 통째 원본은 Core select 로 DB 에서 **다시** 읽는다(식별자 지도의 파이썬 dict 는 jsonb
    # 왕복 전 키 순서라 비교 기준이 못 된다).
    full = dict(session.execute(
        select(ExternalOrderLink.id, ExternalOrderLink.raw_snapshot)).all())
    rows = fetch_list_links(session, ExternalOrderLink.channel == "NAVER",
                            order_by=(ExternalOrderLink.id.asc(),))

    assert len(rows) == len(SHAPES) + 3
    for row in rows:
        expected = project_list_snapshot(full[row.id])
        assert row.raw_snapshot == expected, row.external_id
        assert (json.dumps(row.raw_snapshot, ensure_ascii=False)
                == json.dumps(expected, ensure_ascii=False)), f"{row.external_id}: 키 순서"
    dropped = next(row for row in rows if row.external_id.endswith("중첩-정상"))
    assert "completedClaims" not in dropped.raw_snapshot
    assert "takingAddress" not in dropped.raw_snapshot["productOrder"]


def test_work_groups_match_the_full_orm_path(sql_projection, monkeypatch):
    """진짜 투영이 걸린 목록 == 옛 경로(ORM 통째 스냅샷) 목록 — 정렬 둘 다."""
    import foms.web.admin.naver_ingest as ingest

    session = sql_projection
    seed_shapes(session, commit=False)

    projected = {sort: ingest._work_groups(session, display=True, sort=sort)
                 for sort in ingest.WORKBENCH_SORTS}
    real = ingest._fetch_links

    def _orm_fetch(db, *criteria, display, order_by=None, limit=None, orm=False):
        return real(db, *criteria, display=display, order_by=order_by, limit=limit,
                    orm=orm or display)

    monkeypatch.setattr(ingest, "_fetch_links", _orm_fetch)
    session.expunge_all()
    full = {sort: ingest._work_groups(session, display=True, sort=sort)
            for sort in ingest.WORKBENCH_SORTS}

    assert projected == full
    assert full["new"][0], "빈 목록끼리 같다는 거짓 통과"


def test_list_path_never_selects_the_snapshot_body(sql_projection, pg_engine):
    """목록 경로의 SQL 에 본문 컬럼이 없고, 원본은 울타리 안에서 한 번만 푼다."""
    import foms.web.admin.naver_ingest as ingest

    session = sql_projection
    seed_shapes(session, commit=False)
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _record)
    try:
        ingest._work_groups(session, display=True)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _record)

    body = re.compile(r"external_order_links\.raw_snapshot\s+AS", re.IGNORECASE)
    assert not [sql for sql in seen if body.search(sql)], "목록 경로가 스냅샷 본문을 실었다"
    projected = [sql for sql in seen if "JSON_OBJECT(" in sql]
    assert projected, "투영이 아예 안 걸렸다"
    for sql in projected:
        # 한 번 푸는 자리는 하나뿐이고, 바깥 식은 그 풀린 사본(wb_list_src.r)만 본다.
        assert sql.count("external_order_links.raw_snapshot") == 1, sql
        assert "#> '{}'::text[]" in sql and "OFFSET" in sql and "LATERAL" in sql


def test_reference_check_catches_null_filled_keys_negative_control(sql_projection):
    """음성 대조군 — 없는 키를 null 로 채우는 투영(``NULL ON NULL``)이면 같은 비교가 잡는다."""
    from sqlalchemy import text
    from sqlalchemy.dialects import postgresql

    from foms.web.admin.naver_list_snapshot import list_snapshot_statement, project_list_snapshot

    session = sql_projection
    seed_shapes(session, commit=False)
    full = dict(session.execute(
        select(ExternalOrderLink.id, ExternalOrderLink.raw_snapshot)).all())
    sql = str(list_snapshot_statement((ExternalOrderLink.channel == "NAVER",))
              .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ABSENT ON NULL" in sql
    filled = session.execute(text(sql.replace("ABSENT ON NULL", "NULL ON NULL"))).all()

    differs = [row.id for row in filled if row.raw_snapshot != project_list_snapshot(full[row.id])]
    assert differs, "null 로 채운 투영도 통과한다면 위 비교는 아무것도 못 가른다"
