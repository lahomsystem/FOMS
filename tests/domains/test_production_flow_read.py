"""생산 새 흐름 읽기(ⓐ) — 탭 문 · 파트 계정 판에서 내 카드 빼기 · '내 공정' · '작업 중' 재료 · 탭 숫자 · 쿼리 수(설계서
2026-11-28-production-my-steps-flow §3-1 · §3-2 · §3-4 · §3-6 · §5, 사장님 답 2 · 3 · 9 · 13 · 19 · 24 · 28 · 29 · 30 · 32).

화면 글 · 마크업은 화면 일꾼(ⓒ) 몫이라 여기서는 템플릿에 넘긴 값(``template_rendered``)과 ``?view=counts`` JSON 을 본다.
되돌리면 실패: 파트 계정 판에 내 카드가 남음 · 같이 작업 카드가 남음 · 남이 담은 카드가 빠짐 · 반장 판이 빠짐 · 묶음 순서 ·
어제 끝낸 것이 '오늘 끝낸 것'에 듦 · 같이 작업 카드가 한 사람 묶음에만 · 미정 숫자 ≠ 카드 수 · 캡이 조용히 자름 · 쿼리가 늚.
이름은 모두 지어낸 값이다(김재단 · 오재단 · 박엣지 · 박반장 · 고객 정하늘 · 윤봄).
"""
from __future__ import annotations

import copy
import datetime
import re
from contextlib import contextmanager
from itertools import count

import pytest
from flask import template_rendered
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, to_utc_naive
from foms.services.production.my_steps import build_my_steps
from foms.services.production.part_access import part_account_parts
from foms.services.production.part_board_ctx import board_ctx, card_rows
from foms.services.production.part_constants import normalize_production_parts, production_part_columns
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home, production_home_day
from models import Order, ProductionPartMark, ProductionRun, User
from tests.domains.test_production_home_query_count import _count_queries_and_marks
from tests.support.production_factory_seed import PC, TABLET, mixed_order, set_cookies
from tests.support.production_part_claim_seed import Person, login, make_user, mark

HOME = "/erp/production/home"
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"}
_seq = count(1)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


# --------------------------------------------------------------------------- #
# 준비물
# --------------------------------------------------------------------------- #
class Seed:
    def __init__(self, oid: int, keys: tuple[str, ...]):
        self.id, self.keys = oid, keys


def _order(name: str, n: int, *, day: int | None = 1, stage: str = "PRODUCTION") -> Seed:
    """생산 단계 주문 — 확정 도면 ``n`` 장, 시공일 = 오늘 + ``day``(None = 시공일 없음), 제작 회차 있음."""
    prefix = f"fl{next(_seq)}"
    files = [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]
    when = (get_today_kst() + datetime.timedelta(days=day)).isoformat() if day is not None else None
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": name}}, "drawing_current_files": files,
          "items": [{"product_name": "붙박이장", "spec_width": "2400"}]}
    if when:
        sd["schedule"] = {"construction": {"date": when}}
    order = Order(received_date=get_today_kst().isoformat(), customer_name=name, phone="010-0000-0000", address="가짜시",
                  product="붙박이장", status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=when,
                  structured_data=sd)
    db_session.add(order)
    db_session.commit()
    db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return Seed(order.id, tuple(f["key"] for f in files))


def _multi(name: str, parts: list[str]) -> Person:
    stored, first = production_part_columns("PRODUCTION", normalize_production_parts(parts))
    user = User(username=f"flm_{next(_seq)}", password=generate_password_hash("x"), role="STAFF", team="PRODUCTION", name=name,
                is_active=True, production_parts=stored, production_part=first)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role, name)


def _press(client, who: Person, order: Seed, j: int, action: str, seen: str, part: str = "cut") -> None:
    login(client, who)
    resp = mark(client, order, j, part, action, seen)
    assert resp.status_code == 200, resp.get_json()


def _take(client, who, order, j, part="cut"):
    _press(client, who, order, j, "take", "none", part)


def _join(client, who, order, j, part="cut"):
    _press(client, who, order, j, "join", "need", part)


def _done(client, who, order, j, part="cut"):
    _press(client, who, order, j, "done", "need", part)


def _set_done_at(order: Seed, j: int, part: str, uid: int, when_utc: datetime.datetime) -> None:
    """그 장 · 파트 목록에서 그 사람 몫의 완료 시각을 바꾼다(UTC naive → ISO)."""
    row = db_session.query(ProductionPartMark).filter_by(order_id=order.id, drawing_key=order.keys[j], part=part).one()
    holders = copy.deepcopy(row.holders)
    for item in holders:
        if item.get("uid") == uid:
            item["done_at"] = when_utc.replace(tzinfo=datetime.timezone.utc).isoformat()
    row.holders = holders
    flag_modified(row, "holders")
    db_session.commit()


@contextmanager
def _capture(app):
    seen: list[dict] = []

    def record(sender, template, context, **extra):
        seen.append(context)

    template_rendered.connect(record, app)
    try:
        yield seen
    finally:
        template_rendered.disconnect(record, app)


def _ctx(client, who: Person, url: str = HOME, cookies: dict = TABLET) -> dict:
    """그 사람 · 그 기기로 연 화면에 넘긴 템플릿 값."""
    login(client, who)
    set_cookies(client, cookies)
    with _capture(client.application) as seen:
        resp = client.get(url)
    assert resp.status_code == 200, resp.status_code
    return seen[0]


def _tab(client, who: Person, url: str, cookies: dict = TABLET) -> str:
    login(client, who)
    set_cookies(client, cookies)
    resp = client.get(url)
    assert resp.status_code == 200
    return re.search(r'data-foms-home-tab="([a-z]+)"', resp.get_data(as_text=True)).group(1)


def _tomorrow() -> str:
    return (get_today_kst() + datetime.timedelta(days=1)).isoformat()


def _cards(my_steps: dict) -> list[dict]:
    return [c for d in my_steps["days"] for o in d["orders"] for c in o["cards"]]


def my_steps_of(user) -> dict:
    """서비스 길 그대로 만든 '내 공정' 재료(요청 밖 — 읽기 모델 시험이 같이 쓴다)."""
    rows, _ = build_production_home(db_session, user)
    today = get_today_kst()
    cards = card_rows(rows)
    ctx = board_ctx(db_session, user, cards, mode="part", part=part_account_parts(user)[0], today=today, scene_rows=rows)
    return build_my_steps(user, cards, ctx, production_home_days(rows, today)["strip"], today=today)


# --------------------------------------------------------------------------- #
# 탭 문
# --------------------------------------------------------------------------- #
def test_tab_doors_mine_for_part_crew_for_lead_admin_readonly_pc_and_phone_get_date(client, cohort):
    kim, lead = make_user("김재단", part="cut"), make_user("박반장", lead=True)
    admin, ro = make_user("관리자", team="CS", role="ADMIN"), make_user("상담", team="CS")
    _order("정하늘", 1)
    assert _tab(client, kim, HOME + "?tab=mine") == "mine" and _tab(client, kim, HOME + "?tab=crew") == "date"
    for who in (lead, admin, ro):
        assert _tab(client, who, HOME + "?tab=crew") == "crew" and _tab(client, who, HOME + "?tab=mine") == "date"
    assert _tab(client, lead, HOME + "?tab=steps") == "steps"  # '남은 공정' 은 그대로(답 30)
    for who in (kim, lead):
        for cookies in (PC, PHONE):  # PC(마우스) · 폰(긴 변 992 미만)은 둘 다 날짜로
            assert _tab(client, who, HOME + "?tab=mine", cookies) == "date"
            assert _tab(client, who, HOME + "?tab=crew", cookies) == "date"


def test_flow_config_only_inside_the_door_and_counts_keys(client, cohort):
    kim, lead = make_user("김재단", part="cut"), make_user("박반장", lead=True)
    _order("정하늘", 2)
    page = _ctx(client, kim)
    assert page["flow"] == {"tab": "mine", "mine_href": "/erp/production/home?tab=mine"}
    assert page["part_config"]["flow"] == page["flow"] and {"mine", "crew"} <= set(page["counts"])
    parts = _ctx(client, lead, HOME + "?tab=parts&part=cut")
    assert parts["part_config"]["flow"] == {"tab": "crew", "mine_href": "/erp/production/home?tab=crew"}
    phone = _ctx(client, kim, HOME, PHONE)  # 폰도 판은 그린다(태블릿 가로 CSS 만 보임) — 흐름 키는 없다
    assert phone["part_config"] is not None and "flow" not in phone["part_config"] and phone["flow"] is None
    assert "mine" not in phone["counts"] and "crew" not in phone["counts"]
    pc = _ctx(client, lead, HOME, PC)
    assert pc["part_config"] is None and pc["flow"] is None and "crew" not in pc["counts"]


# --------------------------------------------------------------------------- #
# 날짜 탭 판 — 파트 계정은 내 카드를 뺀다, 반장 판은 그대로
# --------------------------------------------------------------------------- #
def _five(client):
    """정하늘 내일 5장(재단): 0 = 김재단 · 1 = 오재단 + 김재단 같이 · 2 = 오재단 · 3 = 김재단 완료 · 4 = 아무도."""
    kim, oh = make_user("김재단", part="cut"), make_user("오재단", part="cut")
    order = _order("정하늘", 5)
    _take(client, kim, order, 0)
    _take(client, oh, order, 1)
    _join(client, kim, order, 1)
    _take(client, oh, order, 2)
    _take(client, kim, order, 3)
    _done(client, kim, order, 3)
    return kim, oh, order


def test_part_board_drops_my_and_co_working_cards_keeps_others_and_my_done(client, cohort):
    kim, oh, order = _five(client)
    k = order.keys
    page = _ctx(client, kim)
    pane = page["part_board"]["panes"][_tomorrow()]
    assert [c["key"] for c in pane["cards"]] == [k[4], k[2], k[3]]  # 미정 → 남이 담은 → 내가 끝낸(완료 칩에 남음)
    assert pane["mine_out"] == 2  # 내가 담은 0 · 같이 작업하는 1
    assert pane["counts"] == {"all": 3, "need": 0, "done": 1, "unseen": 1}  # 전체 도면 = 뺀 수
    assert pane["bulk"] == 1  # [남은 N장 모두 기본] = 안 본 장 그대로(담은 장은 원래 안 셈)
    taken = next(c for c in pane["cards"] if c["key"] == k[2])
    assert taken["badge"] == "taken" and taken["taken_by_other"]  # 남이 담은 카드는 그대로 [같이 작업](답 5)
    assert (page["counts"]["mine"], page["counts"]["crew"]) == (2, 3)

    oh_pane = _ctx(client, oh)["part_board"]["panes"][_tomorrow()]
    assert [c["key"] for c in oh_pane["cards"]] == [k[4], k[0], k[3]] and oh_pane["mine_out"] == 2

    lead = _ctx(client, make_user("박반장", lead=True), HOME + "?tab=parts&part=cut")
    lead_pane = lead["part_board"]["panes"][_tomorrow()]
    assert len(lead_pane["cards"]) == 5 and lead_pane["mine_out"] == 0  # 반장 · 관리자 판은 아무것도 안 빠진다(답 19)
    assert lead_pane["counts"]["need"] == 3 and (lead["counts"]["crew"], lead["counts"]["mine"]) == (3, 0)


def test_part_board_cap_counts_after_dropping(client, cohort, monkeypatch):
    kim = make_user("김재단", part="cut")
    order = _order("정하늘", 4)
    _take(client, kim, order, 0)
    monkeypatch.setattr("foms.services.production.part_board.PART_BOARD_CARD_CAP", 2)
    pane = _ctx(client, kim)["part_board"]["panes"][_tomorrow()]
    assert len(pane["cards"]) == 2 and pane["hidden"] == 1 and pane["counts"]["all"] == 3  # 200장 캡은 뺀 뒤 기준


# --------------------------------------------------------------------------- #
# '내 공정' 재료
# --------------------------------------------------------------------------- #
def test_my_steps_groups_by_day_then_order_and_strip_counts(client, cohort):
    kim = make_user("김재단", part="cut")
    old, recent, soon, later, none = (_order("윤봄", 1, day=-10), _order("정하늘", 2, day=-1), _order("윤봄", 2, day=1),
                                      _order("정하늘", 1, day=5), _order("윤봄", 1, day=None))
    for order in (old, recent, soon, later, none):
        _take(client, kim, order, 0)
    _take(client, kim, soon, 1)
    page = _ctx(client, kim, HOME + "?tab=mine")
    steps, today = page["my_steps"], get_today_kst()
    assert [d["key"] for d in steps["days"]] == [(today + datetime.timedelta(days=n)).isoformat() for n in (-10, -1, 1, 5)] + ["none"]
    assert [d["title"] for d in steps["days"][:-1]] == [production_home_day(today + datetime.timedelta(days=n), today)["label"]
                                                         for n in (-10, -1, 1, 5)] and steps["days"][-1]["title"] == "출고일 없음"
    soon_day = steps["days"][2]
    assert soon_day["count"] == 2 and soon_day["orders"] == [
        {"id": soon.id, "name": "윤봄", "count": 2, "cards": soon_day["orders"][0]["cards"]}]
    assert [c["key"] for c in soon_day["orders"][0]["cards"]] == list(soon.keys)
    # 띠: 맨 위 '전체' + 날짜 탭 띠와 같은 줄(13) — 숫자 = 그 줄 안 끝낸 장, 띠 밖(지난 출고일 · 출고일 없음)은 day_key ''
    strip = steps["strip"]
    assert strip[0] == {"key": "all", "label": "전체", "sub": "모든 날", "count": 6} and len(strip) == 14
    by_key = {s["key"]: s["count"] for s in strip}
    assert (by_key["recent"], by_key[_tomorrow()], by_key[(today + datetime.timedelta(days=5)).isoformat()], by_key["later"]) == (1, 2, 1, 0)
    assert [c["day_key"] for c in _cards(steps)] == ["", "recent", _tomorrow(), _tomorrow(),
                                                     (today + datetime.timedelta(days=5)).isoformat(), ""]
    assert all(c["mine_row"] and c["part"] == "cut" and c["part_label"] == "재단" for c in _cards(steps))
    assert page["counts"]["mine"] == len(_cards(steps)) == 6 and steps["done"] == [] and steps["hidden"] == 0
    # 같은 카드 dict(날짜 판 조각) — 판 머리 · 판 설정도 같이(확인 창 · 스크립트)
    assert page["part_board"]["writable"] and page["part_config"]["flow"]["tab"] == "mine" and page["crew"] is None


def test_my_steps_mixes_parts_for_multi_part_account(client, cohort):
    both = _multi("김재단", ["cut", "edge"])
    order = _order("정하늘", 2)
    _take(client, both, order, 0, "cut")
    _take(client, both, order, 0, "edge")
    _take(client, both, order, 1, "edge")
    cards = _cards(_ctx(client, both, HOME + "?tab=mine")["my_steps"])
    assert [(c["no"], c["part"]) for c in cards] == [(1, "cut"), (1, "edge"), (2, "edge")]  # 장 번호 → 파트 순서로 섞는다


def test_today_done_follows_kst_midnight_and_drops_yesterday(client, cohort):
    kim, oh = make_user("김재단", part="cut"), make_user("오재단", part="cut")
    order = _order("정하늘", 5)
    for j in (0, 1, 2):
        _take(client, kim, order, j)
        _done(client, kim, order, j)
    _take(client, oh, order, 3)
    _join(client, kim, order, 3)
    _done(client, kim, order, 3)  # 내 몫만 완료("재단 1/2 완료") — 오재단은 작업 중
    login(client, kim)
    assert mark(client, order, 4, "cut", "basic", "none").status_code == 200  # [기본]은 끝낸 것에 안 든다
    midnight = to_utc_naive(datetime.datetime.combine(get_today_kst(), datetime.time(0, 0)), assume_utc_if_naive=False)
    _set_done_at(order, 0, "cut", kim.id, midnight)  # KST 오늘 0시 = 오늘
    _set_done_at(order, 1, "cut", kim.id, midnight - datetime.timedelta(seconds=1))  # KST 어제 23:59:59 = 어제
    steps = _ctx(client, kim, HOME + "?tab=mine")["my_steps"]
    done = {c["key"]: c for c in steps["done"]}
    assert set(done) == {order.keys[0], order.keys[2], order.keys[3]}
    assert done[order.keys[3]]["state"] == "need" and done[order.keys[3]]["done_by_me"]  # 1/2 완료도 내가 끝낸 것
    assert steps["days"] == [] and steps["strip"][0]["count"] == 0 and steps["done_hidden"] == 0


def test_my_steps_cap_200_reports_hidden(client, cohort, monkeypatch):
    kim = make_user("김재단", part="cut")
    order = _order("정하늘", 3)
    for j in range(3):
        _take(client, kim, order, j)
    monkeypatch.setattr("foms.services.production.part_board.PART_BOARD_CARD_CAP", 2)
    page = _ctx(client, kim, HOME + "?tab=mine")
    steps = page["my_steps"]
    assert len(_cards(steps)) == 2 and steps["hidden"] == 1
    assert steps["strip"][0]["count"] == 3 == page["counts"]["mine"]  # 숫자는 캡과 무관


def test_order_card_key_without_number_does_not_break_sorting():
    """ⓑ 가 더할 주문 카드(``key`` = ``@order``, 도면 번호 0)가 섞여도 묶음 · 정렬이 죽지 않는다(약속 6)."""
    from foms.services.production.my_steps import group_days

    cards = [{"order_id": 7, "customer_name": "정하늘", "day_key": "", "key": "@order", "no": 0, "of": 0},
             {"order_id": 7, "customer_name": "정하늘", "day_key": "", "key": "x/d0.png", "no": 1, "of": 1}]
    days = group_days(cards, {7: ("none", "출고일 없음")})
    assert days[0]["count"] == 2 and days[0]["orders"][0]["cards"] == cards


# --------------------------------------------------------------------------- #
# '작업 중' 재료(반장)
# --------------------------------------------------------------------------- #
def _crew_seed(client):
    """정하늘 내일 4장: 재단 0 = 김재단 · 1 = 오재단 + 김재단 같이 · 2 = 오재단 + 김재단(김재단 몫 완료) · 3 = 아무도, 엣지 0 = 박엣지."""
    kim, oh, edge = make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("박엣지", part="edge")
    order = _order("정하늘", 4)
    _take(client, kim, order, 0)
    _take(client, oh, order, 1)
    _join(client, kim, order, 1)
    _take(client, oh, order, 2)
    _join(client, kim, order, 2)
    _done(client, kim, order, 2)
    _take(client, edge, order, 0, "edge")
    return order, make_user("박반장", lead=True)


def test_crew_people_groups_co_working_in_both_and_none_counts(client, cohort):
    order, lead = _crew_seed(client)
    k = order.keys
    page = _ctx(client, lead, HOME + "?tab=crew")
    crew = page["crew"]
    assert crew["part"] == "all" and [p["key"] for p in crew["parts"]] == ["all", "cut", "edge", "assemble", "inspect"]
    assert crew["parts"][0]["href"] == "/erp/production/home?tab=crew" and crew["parts"][1]["href"].endswith("tab=crew&part=cut")
    groups = [(g["part"], g["name"], [c["key"] for c in g["cards"]]) for g in crew["people"]]
    assert groups == [("cut", "김재단", [k[0], k[1]]), ("cut", "오재단", [k[1], k[2]]), ("edge", "박엣지", [k[0]])]  # 답 32
    assert crew["people"][0]["part_label"] == "재단" and crew["hidden"] == 0
    assert crew["none"] == {"counts": {"cut": 1, "edge": 3, "assemble": 4, "inspect": 4}, "cards": None, "hidden": 0}
    assert page["counts"]["crew"] == 4 == len({(c["key"], c["part"]) for g in crew["people"] for c in g["cards"]})
    assert page["my_steps"] is None and page["part_config"]["flow"]["tab"] == "crew"

    edge = _ctx(client, lead, HOME + "?tab=crew&part=edge")["crew"]
    assert edge["part"] == "edge" and [g["name"] for g in edge["people"]] == ["박엣지"]
    assert [c["key"] for c in edge["none"]["cards"]] == [k[1], k[2], k[3]] == [k[j] for j in (1, 2, 3)]
    assert edge["none"]["counts"]["edge"] == len(edge["none"]["cards"])  # 미정 숫자 = 파트 고른 카드 수
    assert all(c["state"] == "none" and c["part"] == "edge" for c in edge["none"]["cards"])


def test_crew_none_cap_and_readonly_same_material(client, cohort, monkeypatch):
    order, _lead = _crew_seed(client)
    monkeypatch.setattr("foms.services.production.part_board.PART_BOARD_CARD_CAP", 2)
    ro = _ctx(client, make_user("상담", team="CS"), HOME + "?tab=crew&part=assemble")
    none = ro["crew"]["none"]
    assert len(none["cards"]) == 2 and none["hidden"] == 2 and none["counts"]["assemble"] == 4
    assert ro["part_board"]["writable"] is False and order.id  # 읽기 전용 = 같은 재료, 단추 없는 판 머리


# --------------------------------------------------------------------------- #
# 따라가 본 사실 — 아침 칩 · 2공장 남의 공장 묶음 · 제작 완료 주문
# --------------------------------------------------------------------------- #
def test_morning_chip_still_counts_my_old_cards_after_they_leave_the_board(client, cohort):
    kim = make_user("김재단", part="cut")
    order = _order("정하늘", 2)
    _take(client, kim, order, 0)
    row = db_session.query(ProductionPartMark).filter_by(order_id=order.id, drawing_key=order.keys[0], part="cut").one()
    yesterday = row.picked_at - datetime.timedelta(days=1)
    holders = copy.deepcopy(row.holders)
    holders[0]["at"] = yesterday.replace(tzinfo=datetime.timezone.utc).isoformat()
    row.holders, row.picked_at = holders, yesterday
    flag_modified(row, "holders")
    db_session.commit()
    page = _ctx(client, kim)
    assert page["part_morning"]["count"] == 1 and page["part_board"]["panes"][_tomorrow()]["mine_out"] == 1
    assert page["counts"]["mine"] == 1


def test_other_factory_card_i_hold_stays_in_the_other_factory_group(client, cohort):
    kim = make_user("김재단", part="cut")
    seed = mixed_order(3, f2=(2,))  # 시공일 없음 장 · 도면 3 = 2공장
    db_session.add(ProductionPartMark(order_id=seed.id, drawing_key=seed.keys[2], part="cut", state="NEED",
                                      picked_by_user_id=kim.id, picked_by_name=kim.name, updated_by_user_id=kim.id))
    db_session.commit()
    page = _ctx(client, kim, HOME + "?day=none")
    pane = page["part_board"]["panes"]["none"]
    assert [c["key"] for c in pane["elsewhere"]] == [seed.keys[2]] and pane["mine_out"] == 0  # 빼지 않는다(누름 없는 묶음 그대로)
    assert page["counts"]["mine"] == 0 and _cards(_ctx(client, kim, HOME + "?tab=mine")["my_steps"]) == []


def test_finished_order_stays_in_today_done_like_production_order(client, cohort):
    """제작 완료(시공 단계로 넘어감)한 주문의 오늘 끝낸 카드도 '오늘 끝낸 것'에 남는다(사장님 2026-11-28 "제작 완료돼도 남김") —
    생산 단계에 있는 주문과 같이. 더 본 것은 test_production_flow_done_today.py."""
    kim = make_user("김재단", part="cut")
    gone, stays = _order("정하늘", 1), _order("윤봄", 1)
    for order in (gone, stays):
        _take(client, kim, order, 0)
        _done(client, kim, order, 0)
    moved = db_session.get(Order, gone.id)  # 제작 완료 = 시공 단계로(화면 줄은 '제작 완료' 작은 칸 — 카드가 아니다)
    sd = copy.deepcopy(moved.structured_data)
    sd["workflow"]["stage"] = "CONSTRUCTION"
    moved.structured_data, moved.erp_stage_code, moved.status = sd, "CONSTRUCTION", "CONSTRUCTION"
    flag_modified(moved, "structured_data")
    db_session.commit()
    done = _ctx(client, kim, HOME + "?tab=mine")["my_steps"]["done"]
    assert sorted(c["order_id"] for c in done) == sorted([gone.id, stays.id])


def test_read_model_helper_matches_the_screen(client, cohort):
    kim, _oh, order = _five(client)
    steps = my_steps_of(db_session.get(User, kim.id))
    assert [c["key"] for c in _cards(steps)] == [order.keys[0], order.keys[1]] and [c["key"] for c in steps["done"]] == [order.keys[3]]


# --------------------------------------------------------------------------- #
# 쿼리 수 · 숫자 길
# --------------------------------------------------------------------------- #
def _q(client, who: Person, url: str, cookies: dict) -> tuple[int, int]:
    login(client, who)
    set_cookies(client, cookies)
    assert client.get(url).status_code == 200  # warmup
    resp, n, marks = _count_queries_and_marks(lambda: client.get(url))
    assert resp.status_code == 200
    return n, marks


def test_query_counts_mine_date_crew_parts_and_counts_view(client, cohort):
    kim, oh, order = _five(client)
    _order("윤봄", 3, day=3)  # 다른 날 생산 주문 — 날짜 탭은 같은 한 번을 넓혀 읽는다
    date_tablet, marks_tablet = _q(client, kim, HOME, TABLET)
    date_phone, marks_phone = _q(client, kim, HOME, PHONE)
    # 날짜 탭 +0(문 안 = 같은 한 번을 넓힘) — 표시 줄 표 읽기 둘 = 칸 아래 이름 · 판(넓힌 한 번) + 아침 칩
    assert date_tablet == date_phone and marks_tablet == marks_phone == 2
    mine, marks_mine = _q(client, kim, HOME + "?tab=mine", TABLET)
    assert mine == date_tablet - 1 and marks_mine == 1  # = 날짜 탭 − 아침 칩(내 공정 탭에는 칩이 없다), 표시 줄 한 번
    admin = make_user("관리자", team="CS", role="ADMIN")
    parts, marks_parts = _q(client, admin, HOME + "?tab=parts&part=cut", TABLET)
    crew, marks_crew = _q(client, admin, HOME + "?tab=crew", TABLET)
    assert crew == parts and marks_crew == marks_parts == 1
    counts_tablet, _m1 = _q(client, kim, HOME + "?view=counts", TABLET)
    counts_phone, _m0 = _q(client, kim, HOME + "?view=counts", PHONE)
    assert counts_tablet == counts_phone + 1  # 숫자 길만 문 안 +1(표시 줄 한 번)
    # 숫자를 안 세는 탭('바뀐 것' · '찾기')은 표시 줄을 안 읽는다 — 숫자 None
    changes, marks_changes = _q(client, kim, HOME + "?tab=changes", TABLET)
    assert marks_changes == 0 and _ctx(client, kim, HOME + "?tab=changes")["counts"]["mine"] is None and oh.id and changes


def test_counts_view_keys_match_the_screen(client, cohort):
    kim, _oh, _order_ = _five(client)
    login(client, kim)
    set_cookies(client, TABLET)
    body = client.get(HOME + "?view=counts").get_json()
    screen = _ctx(client, kim)["counts"]
    assert set(body["data"]["counts"]) == {"making", "changed", "mine", "crew"}
    assert (body["data"]["counts"]["mine"], body["data"]["counts"]["crew"]) == (screen["mine"], screen["crew"]) == (2, 3)
    set_cookies(client, PC)
    assert set(client.get(HOME + "?view=counts").get_json()["data"]["counts"]) == {"making", "changed"}  # 문 밖은 지금 그대로


def test_mine_and_crew_tabs_render_and_day_fragment_keeps_pane_marks(client, cohort):
    kim, _oh, order = _five(client)
    login(client, kim)
    set_cookies(client, TABLET)
    assert client.get(HOME + "?tab=mine").status_code == 200
    frag = client.get(HOME + f"?day={_tomorrow()}&view=day")
    assert frag.status_code == 200 and f'data-key="{order.keys[0]}"' not in frag.get_data(as_text=True)  # 날 조각도 같은 빼기
    login(client, make_user("박반장", lead=True))
    assert client.get(HOME + "?tab=crew&part=edge").status_code == 200
