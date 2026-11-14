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
import foms.services.production_home_read_model as home_read_model
from foms.services.production_home_read_model import (
    PRODUCTION_HOME_STEP_DEFS,
    build_production_home,
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
    _add_order("CONSTRUCTION", "정수아", _iso(0), steps_done=("cut", "edge", "assemble", "inspect"))
    _add_order("CONFIRM", "최유진", None)

    response = client.get(HOME_URL + "?tab=all")  # 전체 주문 줄 목록 = "찾기" 탭(첫 화면은 날짜 탭, D18)
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
    for label in ("도면 기다림", "조립 중", "제작 대기", "제작 완료", "컨펌 기다림"):
        assert label in html, label
    # 탭 숫자: 전체 5 · 생산 중 2(제작 대기 + 조립 중) · 바뀐 것 0
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
    assert [s["done"] for s in steps] == [True, False, False, False]
    assert [s["now"] for s in steps] == [False, True, False, False]
    assert production_home_stage("PRODUCTION", True, steps, False) == ("엣지 중", "생산", "prod")
    assert production_home_stage("PRODUCTION", False, steps, False) == ("제작 대기", "생산", "prod")
    assert production_home_stage("생산", True, steps, True) == ("보류", "생산", "prod")
    all_done = production_home_steps(
        {"production": {"steps": [{"key": k, "done": True} for k, _ in PRODUCTION_HOME_STEP_DEFS]}}, mark_now=True
    )
    assert production_home_stage("PRODUCTION", True, all_done, False) == ("검수 끝", "생산", "prod")
    assert production_home_stage("도면", False, steps, False) == ("도면 기다림", "도면팀", "wait")
    assert production_home_stage("CONSTRUCTION", False, steps, False) == ("제작 완료", "시공 대기", "done")
    # 공정 칸이 아직 없는 주문도 4칸 모두 미완으로 그린다. 옛 주문의 도장(paint) 항목은 걸러진다(D15)
    legacy = production_home_steps({"production": {"steps": [{"key": "paint", "done": True}, {"key": "cut", "done": True}]}}, mark_now=False)
    assert [s["key"] for s in legacy] == ["cut", "edge", "assemble", "inspect"] and legacy[0]["done"]
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


def test_일주일_넘게_지난_시공일은_맨_아래_한_묶음으로() -> None:
    today = datetime.date(2026, 11, 9)

    def _row(key: str, label: str) -> dict:
        return {"day_key": key, "day_label": label, "day_sub": "", "day_is_today": False, "has_changes": key == "2026-06-23"}

    groups = production_home_groups([
        _row("2026-06-23", "6/23 (화)"),      # 139일 지남 → 지난 묶음
        _row("2026-10-31", "10/31 (토)"),     # 9일 지남 → 지난 묶음
        _row("2026-11-05", "11/5 (목)"),      # 4일 지남 → 제자리(급한 일)
        _row("2026-11-12", "11/12 (목)"),
        _row("none", "시공일 없음"),
    ], today)
    assert [g["key"] for g in groups] == ["2026-11-05", "2026-11-12", "none", "past"]
    past = groups[-1]
    assert past["count"] == 2 and past["changed"] == 1 and past["is_open"] is False
    assert past["label"].startswith("지난 시공일")
    assert all(r["day_key"] == "past" for r in past["rows"])
    # 오늘·내일이 없으니 첫 묶음(4일 지남)만 펼침
    assert [g["is_open"] for g in groups] == [True, False, False, False]


def test_캡은_지난_주문만_오래된_것부터_자른다(client, monkeypatch) -> None:
    """운영 실측(11-09): 옛 주문 300+ 에 시공일 오름차순 캡 → 최근·앞날이 잘려 이번 주·내 공정 탭이 0.
    고침: 7일 안·앞날·미정은 전부, 지난 것은 최근부터 남는 자리만, 밀린 수는 지난 묶음 머리줄에."""
    user = _make_user(client, "home_cap_staff", "PRODUCTION")
    _add_order("PRODUCTION", "옛주문", _iso(-60))
    _add_order("PRODUCTION", "덜옛주문", _iso(-30))
    _add_order("PRODUCTION", "조금옛", _iso(-9))
    _add_order("PRODUCTION", "앞날", _iso(3), with_run=True)
    _add_order("CONFIRM", "미정", None)
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 3)

    rows, stats = build_production_home(db_session, user)
    # 앞날·미정은 전부(오름차순), 지난 것은 최근 1건만 → 60일·30일 지난 둘은 밀림
    assert [r["customer_name"] for r in rows] == ["앞날", "미정", "조금옛"]
    assert stats == {"past_hidden": 2, "total": 5}
    groups = production_home_groups(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    assert groups[-1]["key"] == "past" and groups[-1]["count"] == 1
    assert groups[-1]["sub"] == "더 오래된 2건은 안 보여요"

    html = client.get(HOME_URL).get_data(as_text=True)
    assert "앞날" in html and "옛주문" not in html
    # 첫 응답은 고른 날(앞날) 장만 그린다(11-14) — 지난 시공일 장은 그 날 조각으로 받는다. 띠 단추는 밀린 수를 늘 싣는다.
    assert "조금옛" not in html and "<small>2건 더</small>" in html
    past = client.get(HOME_URL + "?day=past&view=day").get_data(as_text=True)
    assert "조금옛" in past and "옛주문" not in past
    assert "더 오래된 2건은 안 보여요" in past
    # 캡이 넉넉하면 전부 보이고 머리줄 글도 없다
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 300)
    rows, stats = build_production_home(db_session, user)
    assert len(rows) == 5 and stats == {"past_hidden": 0, "total": 5}
    assert [r["customer_name"] for r in rows[2:]] == ["조금옛", "덜옛주문", "옛주문"]


def test_날짜_머리줄_규칙() -> None:
    today = datetime.date(2026, 11, 9)  # 월
    assert production_home_day("2026-11-09", today) == {"key": "2026-11-09", "label": "오늘 11/9 (월)", "sub": "", "is_today": True}
    assert production_home_day("2026-11-10", today)["label"] == "내일 11/10 (화)"
    assert production_home_day("2026-11-12", today)["sub"] == "D-3"
    assert production_home_day("2026-11-07", today)["sub"] == "2일 지남"
    assert production_home_day(None, today)["label"] == "시공일 없음"
    assert production_home_day("이상한 값", today)["key"] == "none"


def _add_drawing_transfer(order: Order) -> None:
    """도면 재전달 한 건(주문이 생긴 뒤 시각) — 생산 변경 알림이 읽는 ``drawing_transfer_history``."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    sd = copy.deepcopy(order.structured_data)
    at = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    sd["drawing_transfer_history"] = [{"action": "TRANSFER", "transferred_at": at, "note": "문짝 바꿈"}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_바뀐_것은_생산_단계_주문만_도면_기다림과_제작_완료는_안_친다(client) -> None:
    """D20(11-10 "만들 주문만"): 도면 기다림·제작 완료 주문의 변경은 숫자·받은함·테두리·찾기 거르기에 안 잡힌다."""
    import re

    _make_user(client, "home_prod_d20", "PRODUCTION")
    for stage, name, run in (("DRAWING", "도면바뀜", False), ("PRODUCTION", "생산바뀜", True), ("CONSTRUCTION", "완료바뀜", False)):
        _add_drawing_transfer(_add_order(stage, name, _iso(2), with_run=run))
    day = _iso(2)
    tab_n = '>바뀐 것 <small class="is-hot">1</small></a>'
    changes = client.get(HOME_URL + "?tab=changes").get_data(as_text=True)
    assert tab_n in changes and changes.count("data-foms-home-inbox=") == 1
    inbox = changes.split("fph-inbox--page")[1]
    assert "생산바뀜" in inbox and "도면 재전달" in inbox and "도면바뀜" not in inbox and "완료바뀜" not in inbox
    date = client.get(HOME_URL + f"?day={day}").get_data(as_text=True)
    assert tab_n in date
    pane = date.split(f'data-foms-home-daypane="{day}"')[1].split("data-foms-home-daypane=")[0]
    chips = {m.group(2).strip(): m.group(1) for m in re.finditer(r'<a class="fph-wi([^"]*)"[^>]*>([^<]+)<small>', pane)}
    assert chips == {"도면바뀜": "", "완료바뀜": " is-done"}
    big = re.search(r'<a class="fph-dr ([^"]*)"[^>]*>.*?fph-dr__nm"><b>생산바뀜', pane, re.S)
    assert big and "is-chg" in big.group(1) and "<small>바뀜</small>" in pane
    found = client.get(HOME_URL + "?tab=all").get_data(as_text=True)
    flags = dict((q.split(" ")[0], c) for c, q in re.findall(r'data-changed="(\d)" data-q="([^"]*)"', found))
    assert flags == {"도면바뀜": "0", "생산바뀜": "1", "완료바뀜": "0"}
