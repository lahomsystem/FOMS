"""파트 맡기 고침 P1 화면 쿼리 수(설계서 2026-11-23 §12) — 칸 아래 이름 · 아침 칩 · 3판 카드 칸이 더하는 읽기.

재기 함수 · 시드는 ``test_production_home_query_count.py`` 그대로다(파일 SQLite 레인, warmup 뒤 재기). 시드에 맡음 · 완료 · 담당 바꾸기 ·
밤 넘긴 맡음 줄을 더해 주문 4 → 12건에도 쿼리가 같음(N+1 없음)을 본다. 상한(지금 계약)은 바꾸지 않았다:

=====================================  ======  =========  ======================================================
응답                                    실측     상한        더한 것
=====================================  ======  =========  ======================================================
날짜 탭 · 파트 없는 생산팀(태블릿)          10      11          칸 아래 이름 표시 줄 1
날짜 탭 · 파트 계정(태블릿)               11      12          아침 칩 1(표시 줄은 판과 같은 줄을 다시 씀)
날 조각 · 파트 계정                       7       9           0(판과 같은 줄)
날 조각 · 파트 없는 생산팀(처음 잼)        7       9           칸 아래 이름 표시 줄 1
PC 날짜 · 찾기                            9       11          표시 줄 1
도면 카드 탭 · 관리자(태블릿)              9       12          0(판이 읽는 줄 하나 그대로)
30초 받아 오기(로그인 사용자 + 표시 줄)    2       2           0(새 칸이 같은 줄에 실려 감)
=====================================  ======  =========  ======================================================
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from models import Order, ProductionPartMark, User
from tests.domains.test_production_home_query_count import (
    ABS_QUERY_CAP,
    ALLOWED_DELTA,
    DAY_PANE_QUERY_CAP,
    HOME_URL,
    PART_SCREEN_EXTRA_QUERIES,
    PC_COOKIES,
    _count_queries,
    _seed_order,
    _seed_waits,
)

#: 실측(2026-11-23, 이 가지, SQLite 레인) — 위 표. 상한은 지금 시험 값 그대로 쓴다.
MEASURED = {"date_plain": 10, "date_part": 11, "day_part": 7, "day_plain": 7, "pc_date": 9, "pc_all": 9, "parts_tab": 9, "sync": 2}


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _login(client, name: str, *, part: str | None = None, role: str = "STAFF", team: str = "PRODUCTION",
           cookies: dict | None = None) -> User:
    user = User(username=f"sfqc_{name}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    for key, value in (cookies or {"foms_ptr": "coarse"}).items():
        client.set_cookie(key, value, domain="localhost")
    return user


def _marks(order_id: int, idx: int, me: User) -> None:
    """한 주문에 3판 줄 — 내 맡음(밤 넘김) · 남의 완료 · 담당 바꾸기 줄. 화면이 그 줄 수만큼 더 읽으면 N+1."""
    yesterday = now_utc_naive() - datetime.timedelta(days=1, hours=2)
    rows = [("a0.png", "cut", "NEED", me.id, me.name, None, yesterday, None),
            ("a1.png", "cut", "DONE", me.id + 1000, "박재단", "박재단", yesterday, None),
            ("a0.png", "edge", "NEED", me.id + 1001, "김민준", None, now_utc_naive(), "박엣지")]
    for key, part, state, uid, name, done, picked_at, handed in rows:
        db_session.add(ProductionPartMark(
            order_id=order_id, drawing_key=f"orders/{idx}/drawing/{key}", part=part, state=state,
            picked_by_user_id=uid, picked_by_name=name, picked_at=picked_at,
            done_by_user_id=uid if done else None, done_by_name=done, done_at=now_utc_naive() if done else None,
            handed_from_name=handed, handed_at=now_utc_naive() if handed else None,
            updated_by_user_id=uid, updated_at=now_utc_naive()))
    db_session.commit()


def _seed(start: int, n: int, me: User | None) -> None:
    for i in range(start, start + n):
        oid = _seed_order(i)
        if me is not None:
            _marks(oid, i, me)


def _measure(client, url: str, me: User | None, starts: tuple[int, int]) -> tuple[int, int, str]:
    _seed(starts[0], 4, me)
    _seed_waits(starts[0] + 900, 1)
    assert client.get(url).status_code == 200
    resp_small, q_small = _count_queries(lambda: client.get(url))
    assert resp_small.status_code == 200
    _seed(starts[1], 8, me)
    _seed_waits(starts[1] + 900, 3)
    resp_big, q_big = _count_queries(lambda: client.get(url))
    assert resp_big.status_code == 200
    assert q_big - q_small <= ALLOWED_DELTA, f"N+1 회귀 의심: small={q_small}, big={q_big}"
    return q_small, q_big, resp_big.get_data(as_text=True)


def test_날짜_탭_파트_없는_생산팀은_칸_아래_이름_읽기_하나(client, cohort):
    me = _login(client, "반장")
    small, big, html = _measure(client, HOME_URL, me, (1000, 1100))
    assert "fph-dr__steps has-hd" in html and "fph-dr__hd" in html  # 이름 줄이 실제로 섰다
    assert big <= ABS_QUERY_CAP and big == MEASURED["date_plain"], (small, big)


def test_날짜_탭_파트_계정은_아침_칩_하나만_더한다(client, cohort):
    me = _login(client, "김재단", part="cut")
    small, big, html = _measure(client, HOME_URL, me, (1200, 1300))
    assert "data-pp-card " in html and "data-pp-mchip" in html and "어제부터 내 담당" in html  # 판 · 아침 칩이 섰다
    assert big <= ABS_QUERY_CAP + PART_SCREEN_EXTRA_QUERIES and big == MEASURED["date_part"], (small, big)


@pytest.mark.parametrize("who", ["part", "plain"])
def test_날_조각은_파트_계정_없는_계정_모두_상한_안(client, cohort, who):
    me = _login(client, f"조각{who}", part="cut" if who == "part" else None)
    day = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    small, big, html = _measure(client, f"{HOME_URL}?day={day}&view=day", me, (1400 if who == "part" else 1600, 1500 if who == "part" else 1700))
    assert "data-pp-mchip" not in html  # 아침 칩은 전체 페이지에만
    assert big <= DAY_PANE_QUERY_CAP and big == MEASURED["day_" + who], (who, small, big)


@pytest.mark.parametrize("tab", ["", "?tab=all"])
def test_PC_날짜_찾기는_표시_줄_하나(client, cohort, tab):
    me = _login(client, f"관리자{tab[-3:]}", role="ADMIN", team="CS", cookies=PC_COOKIES)
    small, big, html = _measure(client, HOME_URL + tab, me, (1800 if not tab else 2000, 1900 if not tab else 2100))
    assert "fpc-steps has-hd" in html
    assert big <= ABS_QUERY_CAP and big == MEASURED["pc_all" if tab else "pc_date"], (tab, small, big)


def test_30초_받아_오기는_한_번(client, cohort):
    me = _login(client, "받기재단", part="cut")
    _seed(2200, 12, me)
    ids = [o.id for o in db_session.query(Order).filter(Order.customer_name.like("첫화면22%")).all()]
    since = (now_utc_naive() - datetime.timedelta(days=3)).isoformat()
    url = f"/api/production/part-marks?order_ids={','.join(map(str, ids))}&since={since}"
    assert client.get(url).status_code == 200
    resp, q = _count_queries(lambda: client.get(url))
    marks = resp.get_json()["data"]["marks"]
    assert len(marks) == 36 and all("handed_from_name" in m and "picked_day" in m for m in marks)
    assert q == MEASURED["sync"], q


def test_도면_카드_탭_관리자는_판_읽기_하나(client, cohort):
    """관리자 · 태블릿 '도면 카드' 탭(?tab=parts) — 줄을 안 그리니 칸 아래 이름 읽기가 없고 판이 표시 줄을 한 번 읽는다(지금 그대로)."""
    me = _login(client, "카드관리", role="ADMIN", team="CS")
    small, big, html = _measure(client, HOME_URL + "?tab=parts&part=edge", me, (2400, 2500))
    assert "data-pp-card " in html and "pp-held" in html  # 남의 담당 칸(작업 필요 · 김민준)이 누름 칸으로 섰다
    assert big <= ABS_QUERY_CAP + PART_SCREEN_EXTRA_QUERIES and big == MEASURED["parts_tab"], (small, big)
