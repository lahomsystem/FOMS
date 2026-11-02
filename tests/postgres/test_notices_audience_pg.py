"""NOTICE (PG 레인): 받는 쪽 거르기를 SQL 로 — JSONB ``@>`` 가 실제 PostgreSQL 에서 파이썬 판정과 같은 결과를 낸다.

SQLite 레인은 팀 · 회사 목록을 넓게(``IS NOT NULL``) 거르고 파이썬(:func:`user_matches`)이 마저 본다. 운영(PostgreSQL)은
``audience_staff_teams @> '["SALES"]'`` · ``audience_partner_org_ids @> '[3]'`` 로 질의에서 줄인다 — 여기서 그 결과가
본사 팀(실측 → 영업 묶음 포함) · 협력사 회사 · 전체 공지 · 대조군(다른 팀 · 다른 회사)에서 맞는지와, 문장에 ``@>`` 가
실제로 실리는지를 고정한다.
"""
from __future__ import annotations

import time

from sqlalchemy import event
from sqlalchemy.orm import Session

from foms.services.notices.service import notice_summary, visible_notices
from models import Notice, PartnerOrg, User


def _suffix() -> str:
    return str(int(time.time() * 1_000_000) % 10_000_000)


def _user(session: Session, *, team=None, org=None, name="사람") -> User:
    user = User(username=f"nt-{_suffix()}-{name}", password="pw-not-committed", name=name,
                role="PARTNER" if org is not None else "STAFF", team=team, is_active=True,
                partner_org_id=org.id if org is not None else None)
    session.add(user)
    session.flush()
    return user


def test_jsonb_audience_filter_matches_python_rules(pg_session: Session, pg_engine) -> None:
    org_a = PartnerOrg(name=f"라운즈-{_suffix()}")
    org_b = PartnerOrg(name=f"다라가구-{_suffix()}")
    pg_session.add_all([org_a, org_b])
    pg_session.flush()
    sales = _user(pg_session, team="SALES", name="영업")
    measure = _user(pg_session, team="MEASURE", name="실측")
    cs = _user(pg_session, team="CS", name="상담")
    pa = _user(pg_session, org=org_a, name="라운즈 직원")
    pb = _user(pg_session, org=org_b, name="다라 직원")

    def add(title, **kw):
        row = Notice(title=title, body=f"{title} 본문", display_mode="POPUP", **kw)
        pg_session.add(row)
        pg_session.flush()
        return row.id

    team_sales = add("영업 · 도면", audience_staff_teams=["SALES", "DRAWING"])
    team_cs = add("상담만", audience_staff_teams=["CS"])
    org_only_a = add("라운즈만", audience_partner_org_ids=[org_a.id])
    org_both = add("두 회사", audience_partner_org_ids=[org_b.id, org_a.id], audience_staff_teams=["CS"])
    every = add("모두", audience_staff_all=True, audience_partner_all=True)

    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _before)
    try:
        seen = {u.name: {i["id"] for i in visible_notices(pg_session, u)} for u in (sales, measure, cs, pa, pb)}
        summary = notice_summary(pg_session, pa)
    finally:
        event.remove(pg_engine, "before_cursor_execute", _before)

    assert seen["영업"] == {team_sales, every}
    assert seen["실측"] == {team_sales, every}  # MEASURE → SALES 로 묶인다
    assert seen["상담"] == {team_cs, org_both, every}
    assert seen["라운즈 직원"] == {org_only_a, org_both, every}
    assert seen["다라 직원"] == {org_both, every}
    assert {p["id"] for p in summary["pending"]} == {org_only_a, org_both, every} and summary["unread"] == 3
    assert any("@>" in s and "audience_staff_teams" in s for s in statements)
    assert any("@>" in s and "audience_partner_org_ids" in s for s in statements)
