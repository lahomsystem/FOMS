"""'내 공정' 탭 '오늘 끝낸 것' — 제작 완료(시공 대기)로 넘어간 주문도 오늘 내가 끝낸 장은 KST 자정까지 남는다(사장님 2026-11-28
"제작 완료돼도 남김", 설계서 2026-11-28-production-my-steps-flow §0 답 3 "담은 것 + 오늘 끝낸 것" · §3-4).

되돌리면 실패: 제작 완료한 주문 카드가 '오늘 끝낸 것'에서 사라짐 · 도면 없는 주문('도면 없음' 카드)이 사라짐 · 끝낸 카드에 단추가 생김 ·
띠 숫자 · 담아 놓은 것에 끝낸 카드가 듦 · 어제 끝낸 것이 듦 · '내 공정' 밖 탭 쿼리가 늚 · '내 공정' 표시 줄 읽기가 둘이 됨.
이름은 모두 지어낸 값이다(김재단 · 박엣지 · 최조립 · 한검수 · 박반장, 고객 정하늘 · 윤봄 · 서가을 · 강단비 · 한여름).
"""
from __future__ import annotations

import copy
import datetime

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst, to_utc_naive
from foms.services.production.part_board_ctx import fetch_part_marks
from foms.services.production_home_read_model import build_production_home
from models import Order, ProductionPartMark, User
from tests.domains.test_production_flow_read import Seed, _ctx, _done, _order, _q, _take, cohort  # noqa: F401
from tests.support.production_factory_seed import PC, TABLET, set_cookies
from tests.support.production_part_claim_seed import login, make_user

HOME = "/erp/production/home"
MINE = HOME + "?tab=mine"
PARTS = ("cut", "edge", "assemble", "inspect")


@pytest.fixture
def crew():
    """파트 넷 + 반장 — 한 사람이 한 파트씩."""
    return {"cut": make_user("김재단", part="cut"), "edge": make_user("박엣지", part="edge"),
            "assemble": make_user("최조립", part="assemble"), "inspect": make_user("한검수", part="inspect"),
            "lead": make_user("박반장", lead=True)}


def _tomorrow() -> str:
    return (get_today_kst() + datetime.timedelta(days=1)).isoformat()


def _finish_all(client, crew: dict, order: Seed) -> None:
    """장마다 네 파트를 그 파트 사람이 담고 끝낸다(검수는 앞 셋 뒤) — 진짜 쓰기 API."""
    for j in range(len(order.keys)):
        for part in PARTS:
            _take(client, crew[part], order, j, part)
            _done(client, crew[part], order, j, part)


def _complete(client, who, oid: int) -> None:
    """[제작 완료] — 지금 제작 완료 API 그대로(시공 대기로 넘어감)."""
    login(client, who)
    resp = client.post(f"/api/orders/{oid}/production/complete", json={})
    assert resp.status_code == 200, resp.get_json()


def _view_of(who, oid: int) -> str:
    """첫 화면 행의 보기 키 — 제작 완료면 'done'(시공 대기)."""
    rows, _ = build_production_home(db_session, db_session.get(User, who.id))
    return next(r["home_view"] for r in rows if r["id"] == oid)


def _done_html(client, who) -> str:
    """'내 공정' 화면의 '오늘 끝낸 것' 묶음 HTML."""
    login(client, who)
    set_cookies(client, TABLET)
    resp = client.get(MINE)
    assert resp.status_code == 200
    return resp.get_data(as_text=True).split("data-flow-done", 1)[1].split("</section>", 1)[0]


def _to_construction(oid: int) -> None:
    """제작 완료로 넘김(단계만 — 시험 자료)."""
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["workflow"]["stage"] = "CONSTRUCTION"
    order.structured_data, order.erp_stage_code, order.status = sd, "CONSTRUCTION", "CONSTRUCTION"
    flag_modified(order, "structured_data")
    db_session.commit()


def _age(order: Seed, j: int, part: str, uid: int, when_utc: datetime.datetime, *, touched: bool) -> None:
    """그 장 · 파트의 그 사람 몫 완료 시각을 ``when_utc`` 로(``touched`` 면 줄의 손댄 때 ``updated_at`` 도 같이)."""
    row = db_session.query(ProductionPartMark).filter_by(order_id=order.id, drawing_key=order.keys[j], part=part).one()
    holders = copy.deepcopy(row.holders)
    for item in holders:
        if item.get("uid") == uid:
            item["done_at"] = when_utc.replace(tzinfo=datetime.timezone.utc).isoformat()
    row.holders, row.done_at = holders, when_utc
    flag_modified(row, "holders")
    db_session.commit()
    if touched:  # onupdate 를 건너뛰어 손댄 때를 직접 둔다
        db_session.query(ProductionPartMark).filter_by(id=row.id).update({"updated_at": when_utc}, synchronize_session=False)
        db_session.commit()


def _midnight() -> datetime.datetime:
    return to_utc_naive(datetime.datetime.combine(get_today_kst(), datetime.time(0, 0)), assume_utc_if_naive=False)


# --------------------------------------------------------------------------- #
# (가) 도면 2장 주문 — 김재단이 재단을 끝내고 나머지가 끝내 제작 완료
# --------------------------------------------------------------------------- #
def test_finished_order_keeps_my_two_sheets_in_today_done_without_buttons(client, cohort, crew):
    order = _order("정하늘", 2)
    _finish_all(client, crew, order)
    _complete(client, crew["lead"], order.id)
    assert _view_of(crew["lead"], order.id) == "done"  # 시공 대기 줄(생산 단계 줄이 아니다)

    steps = _ctx(client, crew["cut"], MINE)["my_steps"]
    assert {(c["order_id"], c["key"], c["part"]) for c in steps["done"]} == {(order.id, k, "cut") for k in order.keys}
    assert all(c["state"] == "done" and c["done_by_me"] and c["day_key"] == _tomorrow() for c in steps["done"])  # 띠 줄로 거른다
    assert all(o["word"] == "완료" for c in steps["done"] for o in c["others"])  # 다른 파트 낱말 줄 그대로("검수 완료")
    assert steps["days"] == [] and steps["strip"][0]["count"] == 0 and steps["hidden"] == 0  # 담아 놓은 것 · 띠 숫자 밖

    done = _done_html(client, crew["cut"])
    assert all(f'data-key="{k}"' in done for k in order.keys) and done.count("data-pp-card ") == 2
    assert "data-pp-act=" not in done and done.count(">재단 완료 · 김재단</span>") == 2  # 단추 0 — 글 칸만
    edge = _ctx(client, crew["edge"], MINE)["my_steps"]["done"]  # 같은 주문 다른 파트 사람도 자기 장만
    assert {(c["key"], c["part"]) for c in edge} == {(k, "edge") for k in order.keys}


# --------------------------------------------------------------------------- #
# (나) 도면 없는 주문 — 네 파트 끝내기 → 제작 완료 → 네 사람 각자 '도면 없음' 카드
# --------------------------------------------------------------------------- #
def test_finished_order_without_drawings_keeps_the_order_card_for_each_of_four(client, cohort, crew):
    seed = _order("윤봄", 0)
    order = Seed(seed.id, ("@order",))
    _finish_all(client, crew, order)
    _complete(client, crew["lead"], order.id)
    assert _view_of(crew["lead"], order.id) == "done"
    for part in PARTS:
        done = _ctx(client, crew[part], MINE)["my_steps"]["done"]
        assert [(c["order_id"], c["key"], c["part"], c["order_card"]) for c in done] == [(order.id, "@order", part, True)], part
        assert done[0]["state"] == "done" and done[0]["day_key"] == _tomorrow()
        html = _done_html(client, crew[part])
        assert 'data-order-card="1"' in html and ">도면 없음</span>" in html and "data-pp-act=" not in html, part


# --------------------------------------------------------------------------- #
# (다) 대조군 — 같은 제작 완료 주문들 가운데 어제 끝낸 것은 안 나온다(KST 자정 경계)
# --------------------------------------------------------------------------- #
def test_finished_orders_done_yesterday_stay_out(client, cohort, crew):
    kim = crew["cut"]
    today, late_yesterday, gone = _order("서가을", 1), _order("강단비", 1), _order("한여름", 1)
    for order in (today, late_yesterday, gone):
        _take(client, kim, order, 0)
        _done(client, kim, order, 0)
        _to_construction(order.id)
    midnight = _midnight()
    _age(today, 0, "cut", kim.id, midnight, touched=True)  # KST 오늘 0시 = 오늘
    _age(late_yesterday, 0, "cut", kim.id, midnight - datetime.timedelta(seconds=1), touched=False)  # 줄은 오늘 손댐 · 끝낸 때는 어제
    _age(gone, 0, "cut", kim.id, midnight - datetime.timedelta(seconds=1), touched=True)  # 끝낸 때 · 손댄 때 모두 어제
    done = _ctx(client, kim, MINE)["my_steps"]["done"]
    assert [c["order_id"] for c in done] == [today.id]
    # 손댄 때가 어제인 제작 완료 주문은 표시 줄을 아예 안 읽는다(하위 질의) — 오늘 손댄 주문 줄은 그 주문 줄 전부
    rows = fetch_part_marks(db_session, [], touched=[today.id, late_yesterday.id, gone.id], since=midnight)
    assert {r.order_id for r in rows} == {today.id, late_yesterday.id}
    assert fetch_part_marks(db_session, [], touched=[gone.id]) == []  # since 가 없으면 더 읽지 않는다(지금 꼴)


# --------------------------------------------------------------------------- #
# (라) 쿼리 수 — 제작 완료 주문이 있어도 모든 탭 문장 수 그대로, '내 공정' 표시 줄 읽기는 한 번
# --------------------------------------------------------------------------- #
def test_query_counts_stay_with_finished_orders_on_screen(client, cohort, crew):
    kim, lead = crew["cut"], crew["lead"]
    admin = make_user("관리자", team="CS", role="ADMIN")
    working = _order("정하늘", 2)
    _take(client, kim, working, 0)
    screens = {"date": (kim, HOME, TABLET), "mine": (kim, MINE, TABLET), "changes": (kim, HOME + "?tab=changes", TABLET),
               "find": (kim, HOME + "?tab=all", TABLET), "crew": (admin, HOME + "?tab=crew", TABLET),
               "parts": (admin, HOME + "?tab=parts&part=cut", TABLET), "steps": (lead, HOME + "?tab=steps", TABLET),
               "pc_find": (lead, HOME + "?tab=all", PC), "counts": (kim, HOME + "?view=counts", TABLET)}
    before = {name: _q(client, who, url, cookies) for name, (who, url, cookies) in screens.items()}
    for name in ("윤봄", "서가을"):  # 제작 완료 주문 둘 — 도면 1장 · 도면 0장, 김재단이 오늘 끝냄
        seed = _order(name, 1 if name == "윤봄" else 0)
        order = seed if seed.keys else Seed(seed.id, ("@order",))
        _take(client, kim, order, 0)
        _done(client, kim, order, 0)
        _to_construction(order.id)
    after = {name: _q(client, who, url, cookies) for name, (who, url, cookies) in screens.items()}
    assert after == before  # (전체 SQL 수, 표시 줄 표 SQL 수) 탭마다 그대로
    assert after["mine"][1] == 1 and after["mine"][0] == after["date"][0] - 1  # 표시 줄 한 번 · 날짜 탭 − 아침 칩
    assert len(_ctx(client, kim, MINE)["my_steps"]["done"]) == 2  # 그 한 번에 제작 완료 주문 둘이 실려 왔다
