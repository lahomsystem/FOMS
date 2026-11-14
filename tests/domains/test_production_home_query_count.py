"""생산 첫 화면(``/erp/production/home``) 쿼리 수 계약 — 설계서 §15.6 '쿼리 수' · §15.7(P15-3 첫 단계).

옛 보드 계약(``test_production_dashboard_query_count.py``)과 같은 꼴: SQLAlchemy ``before_cursor_execute`` 로 라우트
한 번의 실제 SQL 수를 세고, 주문 4건 대 12건 차이로 **주문이 늘어도 쿼리가 늘지 않음**(≤``ALLOWED_DELTA``)과 절대
상한(실측 + 30%)을 함께 단언한다. 파트 화면(P15-5)은 이 위에 표시 줄 읽기 +1 만 허용한다.

warmup: 첫 요청의 한 번뿐인 쿼리(설정 · 기능 스위치 등)를 재기에서 뺀다 — 안 빼면 small 이 부풀어 N+1 을 가린다.
시드 함정: 첫 화면 쿼리는 납작 칸 ``erp_stage_code`` 와 ``erp_construction_date`` 로 고르므로 둘 다 직접 넣는다.
"""
from __future__ import annotations

import datetime

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from models import Order, ProductionRun, User

HOME_URL = "/erp/production/home"

# 실측(2026-11-13, SQLite 레인, 파트 없는 생산팀 계정): small(4건) = 9, big(12건) = 9 → 차이 0.
# 아홉 = 로그인 사용자 · 바탕 주문 · 지난 주문 수 · 제작 회차 id · 설정 2(출고 설정 · 물어보기 설정) · 변경 알림
# 이벤트 · 묘비(취소 주문) · 협력사 이름 목록. 행마다 붙는 쿼리는 없다.
ALLOWED_DELTA = 2
# 절대 상한 = 실측 big(9) + 30% ≈ 11.
ABS_QUERY_CAP = 11


def _login(client) -> User:
    user = User(
        username="prod_home_qc", password=generate_password_hash("x"), role="STAFF",
        team="PRODUCTION", name="생산첫화면", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(idx: int) -> int:
    """생산 단계 주문 1건 — 확정 도면 2장, 짝수는 제작 회차까지(제작 대기 · 만드는 중 섞기)."""
    day = (get_today_kst() + datetime.timedelta(days=idx % 5)).isoformat()
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "parties": {"customer": {"name": f"첫화면{idx}", "phone": f"010-3000-{idx:04d}"}},
        "site": {"address_full": f"서울시 생산구 {idx}"},
        "schedule": {"construction": {"date": day}},
        "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
        "drawing_current_files": [
            {"key": f"orders/{idx}/drawing/a{j}.png", "filename": f"a{j}.png"} for j in range(2)
        ],
    }
    order = Order(
        received_date=get_today_kst().isoformat(), customer_name=f"첫화면{idx}", phone=f"010-3000-{idx:04d}",
        address=f"서울시 생산구 {idx}", product="붙박이장", status="PRODUCTION", manager_name="생산첫화면",
        is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=day, structured_data=sd,
    )
    db_session.add(order)
    db_session.flush()
    if idx % 2 == 0:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return order.id


def _count_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_production_home_query_count_does_not_grow_with_orders(client):
    """주문 4 → 12건으로 늘려도 첫 화면(날짜 탭) 쿼리 수가 늘지 않고, 절대 상한 안이다."""
    _login(client)
    for i in range(4):
        _seed_order(i)
    warm = client.get(HOME_URL)
    assert warm.status_code == 200
    resp_small, q_small = _count_queries(lambda: client.get(HOME_URL))
    assert resp_small.status_code == 200
    assert "첫화면0" in resp_small.get_data(as_text=True)  # 시드가 실제로 화면에 섰다(빈 화면 재기 방지)

    for i in range(100, 108):  # +8 → 12건
        _seed_order(i)
    resp_big, q_big = _count_queries(lambda: client.get(HOME_URL))
    assert resp_big.status_code == 200
    assert "첫화면107" in resp_big.get_data(as_text=True)

    delta = q_big - q_small
    assert delta <= ALLOWED_DELTA, f"N+1 회귀 의심: 주문 8건 더해 쿼리 {delta}건 늘었어요(small={q_small}, big={q_big})"
    assert q_big <= ABS_QUERY_CAP, f"절대 쿼리 상한 넘음: big={q_big} > {ABS_QUERY_CAP}"


# 파트 화면(P15-5, 설계서 §15.6 '쿼리 수'): 파트 계정 + 태블릿 코호트는 표시 줄 읽기 한 번(``order_id IN (그날들 생산 주문)``)만
# 더 쓴다 — 카드 수(주문 4건 = 8장 대 12건 = 24장)가 늘어도 같다.
PART_SCREEN_EXTRA_QUERIES = 1


def test_production_home_part_screen_adds_one_query_only(client, monkeypatch):
    """재단 계정 + 태블릿: 카드가 그려진 첫 화면도 주문이 늘어 쿼리가 늘지 않고, 상한은 지금 계약 + 1."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    user = User(
        username="prod_home_qc_part", password=generate_password_hash("x"), role="STAFF",
        team="PRODUCTION", name="김재단", is_active=True, production_part="cut",
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    for i in range(4):
        _seed_order(i)
    assert client.get(HOME_URL).status_code == 200
    resp_small, q_small = _count_queries(lambda: client.get(HOME_URL))
    # 카드가 실제로 섰다(빈 판 재기 방지). 첫 응답은 고른 날(오늘) 장만 그린다(11-14) — 오늘 주문 1건 = 2장
    assert resp_small.get_data(as_text=True).count("data-pp-card ") == 2

    for i in range(200, 208):
        _seed_order(i)
    resp_big, q_big = _count_queries(lambda: client.get(HOME_URL))
    assert resp_big.get_data(as_text=True).count("data-pp-card ") == 6  # 오늘 3건 = 6장

    assert q_big - q_small <= ALLOWED_DELTA, f"N+1 회귀 의심: small={q_small}, big={q_big}"
    assert q_big <= ABS_QUERY_CAP + PART_SCREEN_EXTRA_QUERIES, f"파트 화면 쿼리 상한 넘음: big={q_big}"


# 날짜 한 장 조각(``?view=day&day=``, 11-14): 날을 누를 때 받는 길. 첫 화면과 같은 자료 경로에서 묘비(취소 주문) 읽기와
# 페이지 틀(셸 머리 · 메뉴)의 설정 읽기 2가 빠진다. 실측(2026-11-14, SQLite 레인, 재단 계정): 페이지 10 · 조각 7(4건 = 12건).
# 일곱 = 로그인 사용자 · 바탕 주문 · 지난 주문 수 · 제작 회차 id · 변경 알림 이벤트 · 협력사 이름 목록 · 표시 줄. 상한 = 7 + 30% ≈ 9.
DAY_PANE_QUERY_CAP = 9


def test_production_home_day_pane_fragment_query_count(client, monkeypatch):
    """재단 계정 + 태블릿: 그 날 장 조각은 그 날 카드만, 쿼리는 첫 화면보다 적고 주문이 늘어도 같다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    user = User(
        username="prod_home_qc_day", password=generate_password_hash("x"), role="STAFF",
        team="PRODUCTION", name="박재단", is_active=True, production_part="cut",
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    for i in range(4):
        _seed_order(i)
    day = (get_today_kst() + datetime.timedelta(days=1)).isoformat()
    url = f"{HOME_URL}?day={day}&view=day"
    assert client.get(url).status_code == 200
    _, q_page = _count_queries(lambda: client.get(f"{HOME_URL}?day={day}"))
    resp_small, q_small = _count_queries(lambda: client.get(url))
    assert resp_small.headers["X-FOMS-HOME-DAY"] == day
    assert resp_small.get_data(as_text=True).count("data-pp-card ") == 2  # 내일 주문 1건 = 2장
    assert q_small < q_page, f"조각이 페이지보다 쿼리가 많아요: page={q_page}, day={q_small}"

    for i in range(300, 308):  # +8 → 내일 주문 3건(idx % 5 == 1: 301, 306)
        _seed_order(i)
    resp_big, q_big = _count_queries(lambda: client.get(url))
    assert resp_big.get_data(as_text=True).count("data-pp-card ") == 6
    assert q_big - q_small <= ALLOWED_DELTA, f"N+1 회귀 의심: small={q_small}, big={q_big}"
    assert q_big <= DAY_PANE_QUERY_CAP, f"날 조각 쿼리 상한 넘음: big={q_big} > {DAY_PANE_QUERY_CAP}"
