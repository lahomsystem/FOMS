"""생산팀 첫 화면(전체 주문 한 줄) — 설계서 §12 (2026-11-09, D10·D12).

도면 기다리는 주문부터 시공 단계까지 시공일 순으로 한 줄에 그리고, 왼쪽 큰 글자가 지금 단계다.
금액은 어디에도 없다(D7). 도면팀·시공팀은 403(생산 홈은 CS·영업·생산·관리자만).
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_read_model import (
    PRODUCTION_HOME_STEP_DEFS,
    production_home_day,
    production_home_groups,
    production_home_stage,
    production_home_steps,
)
from models import Order, ProductionRun, User

HOME_URL = "/erp/production/home"


def _make_user(client, username: str, team: str | None, role: str = "STAFF") -> User:
    """주어진 팀·권한으로 사용자를 만들고 세션에 로그인시킨다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _add_order(
    stage: str,
    name: str,
    construction_date: str | None,
    *,
    steps_done: tuple[str, ...] = (),
    with_run: bool = False,
    price: int = 1234000,
) -> Order:
    steps = [
        {"key": key, "label": label, "done": key in steps_done, "at": None, "by_name": None}
        for key, label in _PRODUCTION_STEP_DEFS
    ]
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
        "site": {"address_full": f"{name} 사는 곳 101동 1203호"},
        "schedule": {"construction": {"date": construction_date}},
        "items": [{"product": "거실장", "name": "거실장", "quantity": 1, "price": price, "width": 3100}],
        "production": {"steps": steps},
    }
    order = Order(
        received_date=get_today_kst().isoformat(),
        customer_name=name,
        phone="010-0000-0000",
        address=f"{name} 사는 곳",
        product="거실장",
        manager_name="관리",
        status=stage,
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage,
        erp_construction_date=construction_date,
    )
    db_session.add(order)
    db_session.commit()
    if with_run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return order


def _iso(days: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=days)).isoformat()


def test_생산팀_첫_화면은_도면부터_시공까지_시공일_순으로_그린다(client) -> None:
    _make_user(client, "home_prod_staff", "PRODUCTION")
    _add_order("DRAWING", "서지호", _iso(11))
    _add_order("PRODUCTION", "김하늘", _iso(3), steps_done=("cut", "edge"), with_run=True)
    _add_order("PRODUCTION", "박서준", _iso(3))
    _add_order("CONSTRUCTION", "정수아", _iso(0), steps_done=("cut", "edge", "paint", "assemble", "inspect"))
    _add_order("CONFIRM", "최유진", None)

    response = client.get(HOME_URL)
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # 시공일 순: 오늘 → D-3 → D-11 → 시공일 없음
    positions = [html.index(name) for name in ("정수아", "김하늘", "서지호", "최유진")]
    assert positions == sorted(positions)
    assert "오늘 " in html and "D-3" in html and "D-11" in html and "시공일 없음" in html
    # 날짜 묶음은 접었다 편다(모바일 실측 탭과 같은 말): 머리줄 단추 4, 오늘만 펼침, 나머지 접힘
    assert html.count("data-foms-home-tog") == 4
    assert html.count('data-foms-home-tog aria-expanded="true"') == 1
    assert html.count('data-foms-home-tog aria-expanded="false"') == 3
    assert html.count('foms-prod-home__grp is-closed') == 3
    assert "모두 펼치기" in html and "펼침 <b data-foms-home-open-count>1</b>" in html

    # 큰 글자 = 지금 단계
    for label in ("도면 기다림", "도장 중", "제작 대기", "제작 완료", "컨펌 기다림"):
        assert label in html, label
    # 탭 숫자: 전체 5 · 생산 중 2(제작 대기 + 도장 중) · 바뀐 것 0
    assert 'data-foms-home-view="all" aria-pressed="true">전체 <small>5</small>' in html
    assert '>생산 중 <small>2</small>' in html
    assert html.count('data-view="prod"') == 2
    # 금액은 어디에도 없다(D7)
    assert "1234000" not in html and "1,234,000" not in html
    # 카드는 전체 화면 작업 시트로 간다(설계서 §12.2)
    assert "/erp/production/sheet/" in html
    # 자산: 첫 화면 CSS·JS 핀
    assert "css/contexts/production/home.css" in html
    assert "js/production/foms-production-home.js" in html


def test_도면팀과_시공팀은_생산_첫_화면을_못_본다(client) -> None:
    _make_user(client, "home_drawing_staff", "DRAWING")
    assert client.get(HOME_URL).status_code == 403
    # 시공팀은 전역 문지기가 먼저 출고 화면으로 돌려보낸다(302) — 어느 쪽이든 200 은 아니다.
    _make_user(client, "home_construction_staff", "CONSTRUCTION")
    assert client.get(HOME_URL).status_code in (302, 403)


def test_관리자와_CS_는_생산_첫_화면을_본다(client) -> None:
    _make_user(client, "home_admin", None, role="ADMIN")
    assert client.get(HOME_URL).status_code == 200
    _make_user(client, "home_cs", "CS")
    assert client.get(HOME_URL).status_code == 200


def test_첫_화면_공정_정의는_API_와_같다() -> None:
    assert PRODUCTION_HOME_STEP_DEFS == _PRODUCTION_STEP_DEFS


def test_지금_단계_글자_규칙() -> None:
    steps = production_home_steps({"production": {"steps": [{"key": "cut", "done": True}]}}, mark_now=True)
    assert [s["done"] for s in steps] == [True, False, False, False, False]
    assert [s["now"] for s in steps] == [False, True, False, False, False]
    assert production_home_stage("PRODUCTION", True, steps, False) == ("엣지 중", "생산", "prod")
    assert production_home_stage("PRODUCTION", False, steps, False) == ("제작 대기", "생산", "prod")
    assert production_home_stage("생산", True, steps, True) == ("보류", "생산", "prod")
    all_done = production_home_steps(
        {"production": {"steps": [{"key": k, "done": True} for k, _ in PRODUCTION_HOME_STEP_DEFS]}}, mark_now=True
    )
    assert production_home_stage("PRODUCTION", True, all_done, False) == ("검수 끝", "생산", "prod")
    assert production_home_stage("도면", False, steps, False) == ("도면 기다림", "도면팀", "wait")
    assert production_home_stage("CONSTRUCTION", False, steps, False) == ("제작 완료", "시공 대기", "done")
    # 공정 칸이 아직 없는 주문도 5칸 모두 미완으로 그린다
    assert all(not s["done"] for s in production_home_steps({}, mark_now=False))


def test_날짜_묶음은_오늘_내일만_펼치고_둘_다_없으면_첫_묶음만() -> None:
    def _row(key: str, label: str, today: bool = False, changed: bool = False) -> dict:
        return {"day_key": key, "day_label": label, "day_sub": "", "day_is_today": today, "has_changes": changed}

    groups = production_home_groups([
        _row("2026-11-09", "오늘 11/9 (월)", today=True),
        _row("2026-11-10", "내일 11/10 (화)"),
        _row("2026-11-12", "11/12 (목)", changed=True),
        _row("2026-11-12", "11/12 (목)"),
        _row("none", "시공일 없음"),
    ])
    assert [g["key"] for g in groups] == ["2026-11-09", "2026-11-10", "2026-11-12", "none"]
    assert [g["is_open"] for g in groups] == [True, True, False, False]
    assert groups[2]["count"] == 2 and groups[2]["changed"] == 1

    later = production_home_groups([_row("2026-11-20", "11/20 (금)"), _row("none", "시공일 없음")])
    assert [g["is_open"] for g in later] == [True, False]
    assert production_home_groups([]) == []


def test_날짜_머리줄_규칙() -> None:
    today = datetime.date(2026, 11, 9)  # 월
    assert production_home_day("2026-11-09", today) == {"key": "2026-11-09", "label": "오늘 11/9 (월)", "sub": "", "is_today": True}
    assert production_home_day("2026-11-10", today)["label"] == "내일 11/10 (화)"
    assert production_home_day("2026-11-12", today)["sub"] == "D-3"
    assert production_home_day("2026-11-07", today)["sub"] == "2일 지남"
    assert production_home_day(None, today)["label"] == "시공일 없음"
    assert production_home_day("이상한 값", today)["key"] == "none"
