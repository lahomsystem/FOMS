"""FOMS 공지 창 · 배지 요약의 질의 수 가드(검토 반영 2026-11-02, 설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5).

본사 공용 창 스크립트(``GET /api/notices?view=popup``)는 모든 페이지에서 불리고, 협력사 화면 context_processor 는 매 화면
그릴 때 돈다. 둘 다 공지 수와 무관하게 질의 수가 일정해야 하고, 목록 본문을 읽지 않아야 한다(창에 띄울 최대 5건 본문만
``id IN (...)`` 한 번). 공지를 늘려도 질의 수가 그대로인지 · 본문을 읽는 문장이 그 하나뿐인지 고정한다.
"""
from __future__ import annotations

from sqlalchemy import event

from db import db_session, engine
from foms.services.notices.service import notice_summary
from models import Notice, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출

_BODY_MARK = "본문표식"


def _seed(count: int, start: int = 0) -> None:
    """본사 · 협력사 모두 받는 공지 — 창 · 목록 반씩, 남(다른 팀)의 공지도 섞는다."""
    for i in range(start, start + count):
        db_session.add(Notice(title=f"공지 {i}", body=f"{_BODY_MARK} {i}", created_by_name="라홈 본사",
                              audience_staff_all=True, audience_partner_all=True,
                              display_mode="POPUP" if i % 2 == 0 else "LIST"))
        db_session.add(Notice(title=f"영업만 {i}", body=f"{_BODY_MARK} 영업 {i}", audience_staff_teams=["SALES"],
                              display_mode="POPUP"))
    db_session.commit()


def _capture(fn):
    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    db_session.expire_all()
    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, statements


def _body_reads(statements: list[str]) -> list[str]:
    return [s for s in statements if "notices.body" in s]


def _assert_constant(fn) -> tuple:
    _seed(2)
    small, q_small = _capture(fn)
    _seed(14, start=100)
    big, q_big = _capture(fn)
    assert len(q_big) == len(q_small), (len(q_small), len(q_big), q_big)
    # 본문은 창에 띄울 공지(최대 5건)만 id IN (...) 으로 한 번 읽는다.
    reads = _body_reads(q_big)
    assert len(reads) <= 1 and all(" IN " in s.upper() for s in reads), reads
    return small, big


def test_staff_summary_query_count_is_constant(app, world):
    user = db_session.get(User, world["staff"])
    small, big = _assert_constant(lambda: notice_summary(db_session, user))
    assert len(small["pending"]) == 1 and len(big["pending"]) == 5
    assert big["unread"] == 16


def test_partner_summary_query_count_is_constant(app, world):
    user = db_session.get(User, world["partner_a"])
    small, big = _assert_constant(lambda: notice_summary(db_session, user))
    assert len(small["pending"]) == 1 and len(big["pending"]) == 5
    assert big["unread"] == 16


def test_popup_api_query_count_is_constant(app, world):
    client = _client(app, db_session.get(User, world["staff"]))
    assert client.get("/api/notices?view=popup").status_code == 200  # 처음 한 번(캐시 데우기)

    def call():
        resp = client.get("/api/notices?view=popup")
        assert resp.status_code == 200
        return resp.get_json()["data"]

    _seed(2)
    _small, q_small = _capture(call)
    _seed(14, start=100)
    big, q_big = _capture(call)
    assert len(q_big) == len(q_small), (len(q_small), len(q_big))
    reads = _body_reads(q_big)
    assert len(reads) <= 1 and all(" IN " in s.upper() for s in reads), reads
    assert set(big) == {"pending", "unread"}  # 목록(items) · LIST 공지 본문은 싣지 않는다
    assert [p["body"].startswith(_BODY_MARK) for p in big["pending"]] == [True] * 5


def test_partner_screen_context_query_count_is_constant(app, world):
    """협력사 화면 머리(context_processor)는 공지 본문 전부를 매 화면 읽지 않는다."""
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.get("/partner").status_code == 200

    def call():
        resp = client.get("/partner")
        assert resp.status_code == 200
        return resp.get_data(as_text=True)

    _seed(2)
    _small, q_small = _capture(call)
    _seed(14, start=100)
    _big, q_big = _capture(call)
    assert len(q_big) == len(q_small), (len(q_small), len(q_big))
    reads = _body_reads(q_big)
    assert len(reads) <= 1 and all(" IN " in s.upper() for s in reads), reads
