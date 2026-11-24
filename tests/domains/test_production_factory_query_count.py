"""2공장 생산 화면 쿼리 수(설계서 2026-11-23 §12, 3단계 ⑤) — 공장 칸은 이미 읽은 사용자 행 · 주문 JSON 에서만(쿼리 0).

재기 · 시드는 ``test_production_selfclaim_query_count.py`` 그대로에 주문 반을 섞인 주문(장 하나 2공장)으로 바꾼다. 상한 · 실측은 그 시험
값 그대로다 — 2공장 그림이 켜져도(남의 공장 카드 · 묶음 · 공장 고르기 · 도면 칸 두 줄) 숫자가 같아야 한다. 주문 4 → 12건에도 같음(N+1 없음).
"""
from __future__ import annotations

import copy
import datetime

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order, User
from tests.domains import test_production_selfclaim_query_count as sq
from tests.domains.test_production_home_query_count import (
    ABS_QUERY_CAP,
    ALLOWED_DELTA,
    DAY_PANE_QUERY_CAP,
    HOME_URL,
    PART_SCREEN_EXTRA_QUERIES,
    PC_COOKIES,
    _count_queries,
    _seed_waits,
)

MEASURED = sq.MEASURED


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _mix_all() -> None:
    """도면이 두 장인 주문 중 짝수 id 의 둘째 장을 2공장으로(공장 지정 API 가 쓰는 꼴 — files 표)."""
    for order in db_session.query(Order).filter(Order.customer_name.like("첫화면%")).all():
        sd = copy.deepcopy(order.structured_data or {})
        files = sd.get("drawing_current_files") or []
        if order.id % 2 or len(files) < 2 or sd.get("drawing_factory"):
            continue
        sd["drawing_factory"] = {"sheets": {}, "files": {files[1]["key"]: 2}}
        order.structured_data = sd
        flag_modified(order, "structured_data")
    db_session.commit()


def _measure(client, url: str, me, starts: tuple[int, int]) -> tuple[int, int, str]:
    sq._seed(starts[0], 4, me)
    _seed_waits(starts[0] + 900, 1)
    _mix_all()
    assert client.get(url).status_code == 200
    resp_small, q_small = _count_queries(lambda: client.get(url))
    sq._seed(starts[1], 8, me)
    _seed_waits(starts[1] + 900, 3)
    _mix_all()
    resp_big, q_big = _count_queries(lambda: client.get(url))
    assert resp_small.status_code == 200 and resp_big.status_code == 200
    assert q_big - q_small <= ALLOWED_DELTA, f"N+1 회귀 의심: small={q_small}, big={q_big}"
    return q_small, q_big, resp_big.get_data(as_text=True)


def _second_factory(me) -> None:
    db_session.get(User, me.id).production_factory = 2
    db_session.commit()


def test_날짜_탭_반장_섞인_주문도_같은_수(client, cohort):
    me = sq._login(client, "반장")
    db_session.get(User, me.id).production_lead = True  # 한 공장 계정(반장 — 날짜 줄을 공장으로 묶는다)
    db_session.commit()
    _small, big, html = _measure(client, HOME_URL, me, (3000, 3100))
    assert "fph-dr__dw is-split" in html and "fph-fac-now" in html  # 2공장 그림이 실제로 켜졌다
    assert big <= ABS_QUERY_CAP and big == MEASURED["date_plain"], big


@pytest.mark.parametrize("factory", [1, 2])
def test_날짜_탭_파트_계정_두_공장_모두_같은_수(client, cohort, factory):
    me = sq._login(client, f"재단{factory}", part="cut")
    if factory == 2:
        _second_factory(me)
    _small, big, html = _measure(client, HOME_URL, me, (3200 + factory * 200, 3300 + factory * 200))
    assert "data-pp-elsewhere " in html and "pp-otherg" in html  # 남의 공장 카드 묶음이 섰다
    assert big <= ABS_QUERY_CAP + PART_SCREEN_EXTRA_QUERIES and big == MEASURED["date_part"], (factory, big)


def test_날_조각_파트_계정(client, cohort):
    me = sq._login(client, "조각재단", part="cut")
    day = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    _small, big, html = _measure(client, f"{HOME_URL}?day={day}&view=day", me, (3800, 3900))
    assert "data-pp-elsewhere " in html
    assert big <= DAY_PANE_QUERY_CAP and big == MEASURED["day_part"], big


@pytest.mark.parametrize("tab", ["", "?tab=all"])
def test_PC_날짜_찾기_같은_수(client, cohort, tab):
    me = sq._login(client, f"관리{tab[-3:]}", role="ADMIN", team="CS", cookies=PC_COOKIES)
    _small, big, html = _measure(client, HOME_URL + tab, me, (4000 if not tab else 4200, 4100 if not tab else 4300))
    assert "fpc-dw is-split" in html
    assert big <= ABS_QUERY_CAP and big == MEASURED["pc_all" if tab else "pc_date"], (tab, big)


def test_도면_카드_탭_관리자_공장_고르기(client, cohort):
    me = sq._login(client, "카드관리", role="ADMIN", team="CS")
    _small, big, html = _measure(client, HOME_URL + "?tab=parts&part=edge&factory=2", me, (4400, 4500))
    assert 'aria-label="공장 고르기"' in html and "data-pp-elsewhere " in html
    assert big <= ABS_QUERY_CAP + PART_SCREEN_EXTRA_QUERIES and big == MEASURED["parts_tab"], big
