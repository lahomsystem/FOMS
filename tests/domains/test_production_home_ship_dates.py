"""생산 첫 화면 날짜 띠를 출고 일정과 같은 날짜로(사장님 2026-11-25 "출고 일정 = 제작 일정" · "내일 부터").

- A: 주문 하나의 출고일 목록(:func:`ship_dates`) — ① 지방 + 상차 예정일 ② 시공일 전부(쉼표 · 제품별, 취소 제품 뺌)
  ③ 시공일 없는 협력사 희망일 ④ 없음. 위에서 처음 맞는 갈래 하나.
- B · G: 띠 · 날짜 판은 내일 이후 출고일마다 그 날 줄에, 남은 날이 없으면 가장 늦은 지난 날(오늘 포함) 하나에. 주문 수는 한 번.
- 출고 화면 읽기 모델(일정 표 + 확정 대기 희망일)과 같은 날 — 지방 상차 예정일만 다르다.
- C: 납작 열이 옛날이어도 출고일이 남은 주문은 캡에 안 밀리고, 장은 출고일로 선다.
- E: 띠 글 셋(출고일 2주 · 지난 출고일 · 출고일 없음)과 줄의 '상차 12/1' · '희망일 12/3'. 시공일 하나뿐인 보통 주문은 전과 같다(음성 대조군).

날짜 단위 시험은 고정 날(2026-11-25 수)로, 화면 시험은 ``get_today_kst()`` 에서 센 날로 짠다(오늘을 가정하지 않는다).
"""
from __future__ import annotations

import datetime
import re
from itertools import count

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import production_home_read_model as home_read_model
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.partners.schedule_request import pending_request_ids_by_date
from foms.services.production.drawing_arrival import attach_drawing_arrival, drawing_deadline
from foms.services.production.late_rule import production_late_level
from foms.services.production.part_screen import morning_chip
from foms.services.production.pc_view import pc_due
from foms.services.production.ship_dates import (
    SHIP_BUILD,
    SHIP_LOAD,
    SHIP_WISH,
    due_day,
    live_condition,
    order_ship_dates,
    pane_key,
    placed_days,
    ship_dates,
)
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import build_production_home, production_home_counts, production_home_groups
from foms.services.shipment_dashboard_helpers import extract_all_construction_dates
from models import Order, PartnerOrg, ProductionPartMark, User

D = datetime.date
TODAY = D(2026, 11, 25)  # 수
HOME = "/erp/production/home"
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
_seq = count(1)


# --------------------------------------------------------------------------- #
# A — 출고일 목록 네 갈래와 차례
# --------------------------------------------------------------------------- #
def _sd(build: str | None = None, items: list | None = None, wish: str | None = None) -> dict:
    sd: dict = {"schedule": {"construction": {"date": build}} if build is not None else {}, "items": items or []}
    if wish is not None:
        sd["partner_intake"] = {"requested_construction": {"date": wish, "time": "오전"}}
    return sd


def _ship(sd: dict, *, regional: bool = False, loading=None, partner=None, stage: str = "PRODUCTION"):
    return ship_dates(sd, regional=regional, loading_date=loading, partner_org_id=partner, stage_code=stage)


def test_A_지방_상차_예정일이_먼저_없으면_시공일() -> None:
    sd = _sd("2026-12-03")
    assert _ship(sd, regional=True, loading="2026-12-01") == [(D(2026, 12, 1), SHIP_LOAD)]
    assert _ship(sd, regional=True, loading=None) == [(D(2026, 12, 3), SHIP_BUILD)]  # 적혀 있지 않으면 시공일
    assert _ship(sd, regional=True, loading="") == [(D(2026, 12, 3), SHIP_BUILD)]
    assert _ship(sd, regional=True, loading="2026-13-01") == [(D(2026, 12, 3), SHIP_BUILD)]  # 못 읽는 날 = 없음
    # 대조군: 지방이 아니면 상차 예정일이 있어도 시공일(출고 화면은 상차 예정일을 안 읽는다)
    assert _ship(sd, regional=False, loading="2026-12-01") == [(D(2026, 12, 3), SHIP_BUILD)]


def test_A_시공일은_쉼표_날과_제품_날_전부_취소_제품은_뺀다() -> None:
    sd = _sd("2026-12-10, 2026-12-03", items=[
        {"product_name": "붙박이장", "construction_date": "2026-12-05"},
        {"product_name": "신발장", "construction_date": "2026-12-07", "cancel": {"at": "2026-11-20"}},  # 취소 = 뺌
        {"product_name": "거실장"},
    ])
    assert _ship(sd) == [(D(2026, 12, 3), SHIP_BUILD), (D(2026, 12, 5), SHIP_BUILD), (D(2026, 12, 10), SHIP_BUILD)]
    assert _ship(_sd("2026-12-03")) == [(D(2026, 12, 3), SHIP_BUILD)]  # 하나뿐인 보통 주문


def test_A_협력사_희망일은_시공일이_하나도_없을_때만_출고_화면과_같은_함수로() -> None:
    assert _ship(_sd(wish="2026-12-03"), partner=7, stage="DRAWING") == [(D(2026, 12, 3), SHIP_WISH)]
    assert _ship(_sd("", wish="2026-12-03"), partner=7) == [(D(2026, 12, 3), SHIP_WISH)]
    # 우리 시공일(주문 칸이든 제품 칸이든)이 있으면 시공일 — 희망일은 안 본다
    assert _ship(_sd("2026-12-08", wish="2026-12-03"), partner=7) == [(D(2026, 12, 8), SHIP_BUILD)]
    assert _ship(_sd(items=[{"construction_date": "2026-12-09"}], wish="2026-12-03"), partner=7) == \
        [(D(2026, 12, 9), SHIP_BUILD)]
    # 출고 화면이 희망일을 더 받지 않는 단계(시공 이후) · 협력사 주문이 아님 · 못 읽는 날 = 없음
    assert _ship(_sd(wish="2026-12-03"), partner=7, stage="CONSTRUCTION") == []
    assert _ship(_sd(wish="2026-12-03"), partner=None) == []
    assert _ship(_sd(wish="12/3"), partner=7) == []
    # 지방 + 상차 예정일이 희망일보다 먼저
    assert _ship(_sd(wish="2026-12-03"), regional=True, loading="2026-12-01", partner=7) == [(D(2026, 12, 1), SHIP_LOAD)]


def test_A_아무_날짜도_없으면_빈_목록() -> None:
    assert _ship({}) == [] and _ship(_sd("")) == [] and _ship(None) == []  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# B · G — 띠 놓기
# --------------------------------------------------------------------------- #
def _row(rid: int, *days: D, view: str = "prod", stage: str = "제작 대기") -> dict:
    return {"id": rid, "customer_name": f"집{rid}", "ship_days": list(days), "ship_due": due_day(days, TODAY),
            "home_view": view, "home_stage": stage, "home_steps": [], "has_changes": False}


def _ids(pane: dict) -> list[int]:
    return [r["id"] for r in pane["wait_rows"] + pane["make_rows"] + pane["done_rows"]]


def test_B_남은_날마다_서고_남은_날이_없으면_가장_늦은_지난_날_하나() -> None:
    rows = [
        _row(1, D(2026, 11, 20), D(2026, 11, 27), D(2026, 11, 30), D(2026, 12, 20), D(2026, 12, 25)),  # 남은 날 넷
        _row(2, D(2026, 11, 20), D(2026, 11, 25)),   # 남은 날 없음 → 가장 늦은 지난 날 = 오늘 → 지난 7일
        _row(3, D(2026, 11, 10), D(2026, 11, 12)),   # 가장 늦은 날도 7일 넘게 지남 → 지난 출고일
        _row(4, D(2026, 11, 25), D(2026, 11, 26)),   # 오늘 + 내일 → 내일만(오늘 출고는 이미 나가고 있다)
        _row(5),                                     # 출고일 없음
        _row(6, D(2026, 11, 26), view="wait", stage="도면 기다림"),
    ]
    days = production_home_days(rows, TODAY)
    by = {p["key"]: p for p in days["panes"]}
    placed = {key: _ids(p) for key, p in by.items() if p["total"]}
    assert placed == {"2026-11-26": [6, 4], "2026-11-27": [1], "2026-11-30": [1], "later": [1], "recent": [2],
                      "past": [3], "none": [5]}
    assert by["later"]["total"] == 1  # 그 뒤 장에 남은 날이 둘이어도 한 번
    # 머리 '전체 N건'(주문 수)은 주문을 한 번만 센다 — 장 숫자 합(8)과 다르다
    assert production_home_counts(rows)["all"] == 6 and sum(p["total"] for p in days["panes"]) == 8
    assert days["selected"] == "2026-11-26"  # 처음 여는 장 = 내일
    assert [placed_days(r["ship_days"], TODAY) for r in rows[:2]] == [
        [D(2026, 11, 27), D(2026, 11, 30), D(2026, 12, 20), D(2026, 12, 25)], [D(2026, 11, 25)]]


def test_D_시공일이_여럿이면_장마다_그_장의_날로_판정_표시() -> None:
    """같은 주문이 두 장에 서면 장마다 그 날 — 마감 · 시공일 표가 장의 날을 따른다(행 판정 날은 첫 장의 날)."""
    row = _row(7, D(2026, 11, 26), D(2026, 12, 2), view="wait", stage="도면 기다림")
    attach_drawing_arrival([row], TODAY)
    by = {p["key"]: p for p in production_home_days([row], TODAY)["panes"]}
    first, second = by["2026-11-26"]["wait_rows"][0], by["2026-12-02"]["wait_rows"][0]
    assert first is row and second is not row and second["id"] == row["id"]  # 첫 장은 행 그대로(보통 주문과 같은 길)
    assert first["dw_deadline"] == drawing_deadline(D(2026, 11, 26)) and first["dw_state"] == "late"
    assert second["dw_deadline"] == drawing_deadline(D(2026, 12, 2)) and second["dw_state"] == "calm"
    assert second["ship_due"] == D(2026, 12, 2) and second["day_label"] == "12/2 (수)" and second["day_sub"] == "D-7"
    assert by["2026-11-26"]["arrival"]["state"] == "late" and by["2026-12-02"]["arrival"]["state"] == "calm"


def test_G_날_줄은_내일부터_오늘은_지난_7일_장_처음은_내일() -> None:
    days = production_home_days([_row(1, TODAY)], TODAY)
    keys = [b["key"] for b in days["strip"]]
    assert keys[1] == "2026-11-26" and keys[-2] == "2026-12-06" and len(keys) == 13 and "2026-11-25" not in keys
    recent = days["strip"][0]
    # 지난 7일 장 = 11/18 ~ 오늘(11/25)까지 — 범위 글도 오늘까지
    assert (recent["label"], recent["sub"], recent["title"]) == ("지난 7일", "11/18~11/25", "지난 7일 11/18~11/25")
    assert _ids(recent) == [1]
    later = days["strip"][-1]
    assert later["sub"] == "12/7~" and later["title"] == "12/7 뒤"  # 그 뒤 = 오늘 + 12일부터(예전 + 11일)
    first = days["strip"][1]
    assert (first["label"], first["sub"], first["title"]) == ("11/26", "목 · 내일", "내일 11/26 (목)")
    assert not any(b["is_today"] for b in days["panes"])
    # 내일이 비었으니 일이 있는 가장 가까운 장(지금 규칙 그대로) = 지난 7일. 다 비면 내일
    assert days["selected"] == "recent" and production_home_days([], TODAY)["selected"] == "2026-11-26"
    assert pane_key(TODAY, TODAY) == "recent" and pane_key(D(2026, 11, 18), TODAY) == "recent"
    assert pane_key(D(2026, 11, 17), TODAY) == "past" and pane_key(D(2026, 12, 7), TODAY) == "later"


def test_D_판정_날은_놓는_날과_같다_내일_이후_가장_가까운_날_없으면_가장_늦은_지난_날() -> None:
    # 오늘 출고는 이미 나가고 있다 — 남은 날(내일 이후)이 있으면 그 날, 없을 때만 오늘을 포함한 가장 늦은 날
    assert due_day([D(2026, 11, 20), D(2026, 11, 25), D(2026, 11, 28)], TODAY) == D(2026, 11, 28)
    assert due_day([D(2026, 11, 25), D(2026, 11, 30)], TODAY) == D(2026, 11, 30)
    assert due_day([D(2026, 11, 20), D(2026, 11, 25)], TODAY) == TODAY
    assert due_day([D(2026, 11, 20), D(2026, 11, 28), D(2026, 12, 5)], TODAY) == D(2026, 11, 28)
    assert due_day([D(2026, 11, 10), D(2026, 11, 20)], TODAY) == D(2026, 11, 20)
    assert due_day([], TODAY) is None
    for days in ([D(2026, 11, 25), D(2026, 11, 30)], [D(2026, 11, 20), D(2026, 11, 25)], [D(2026, 11, 26)]):
        assert due_day(days, TODAY) == placed_days(days, TODAY)[0]  # 판정 날 = 첫 장의 날
    # 도면 마감 · 늦음 = 판정 날(납작 열 construction_date 가 아니다)
    row = {**_row(1, D(2026, 11, 20), D(2026, 12, 4), view="wait", stage="도면 기다림"), "construction_date": "2026-11-20"}
    attach_drawing_arrival([row], TODAY)
    assert row["dw_deadline"] == drawing_deadline(D(2026, 12, 4)) and row["dw_state"] == "calm"
    prod = {**_row(2, D(2026, 11, 20), D(2026, 11, 26), stage="제작 대기"), "construction_date": "2026-12-30"}
    assert production_late_level(prod, TODAY) == "late"  # 내일 출고인데 시작 전


# --------------------------------------------------------------------------- #
# 화면 — 시드
# --------------------------------------------------------------------------- #
def _login(client, *, team: str = "PRODUCTION", role: str = "STAFF") -> User:
    user = User(username=f"ship_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team,
                name="생산가짜", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _iso(off: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=off)).isoformat()


def _md(off: int) -> str:
    day = get_today_kst() + datetime.timedelta(days=off)
    return f"{day.month}/{day.day}"


def _order(name: str, build: str | None, *, items: list | None = None, stage: str = "PRODUCTION", regional: bool = False,
           loading: str | None = None, partner: int | None = None, wish: str | None = None,
           files: list | None = None) -> Order:
    sd = _sd(build, items=items or [{"product_name": "붙박이장", "spec_width": "1800"}], wish=wish)
    sd.update({"workflow": {"stage": stage}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
               "drawing_current_files": files or []})
    flat = (build or "").split(",")[0].strip() or None
    order = Order(received_date=get_today_kst().isoformat(), customer_name=name, phone="010-0000-0000", address="가짜시",
                  product="붙박이장", status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=flat,
                  is_regional=regional, shipping_scheduled_date=loading, partner_org_id=partner, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _partner() -> int:
    org = PartnerOrg(name=f"가짜협력사{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    return org.id


def _six(partner: int) -> dict[str, Order]:
    """실화면 시험과 같은 여섯 — 보통 · 시공일 둘(하나는 지남) · 지방 + 상차 예정일 · 지방인데 상차 예정일 없음 · 희망일만 · 없음."""
    return {
        "plain": _order("보통가짜", _iso(3)),
        "two": _order("두날가짜", f"{_iso(-2)}, {_iso(4)}"),
        "load": _order("상차가짜", _iso(6), regional=True, loading=_iso(2)),
        "noload": _order("상차없음가짜", _iso(5), regional=True),
        "wish": _order("희망가짜", None, stage="DRAWING", partner=partner, wish=_iso(7)),
        "none": _order("날없음가짜", None, stage="DRAWING"),
    }


# --------------------------------------------------------------------------- #
# 출고 화면과 같은 날
# --------------------------------------------------------------------------- #
def test_출고_화면과_같은_날짜_지방_상차_예정일만_다르다(client) -> None:
    orders = _six(_partner())
    multi = _order("여러제품가짜", f"{_iso(1)},{_iso(9)}", items=[
        {"product_name": "장", "construction_date": _iso(3)},
        {"product_name": "취소장", "construction_date": _iso(8), "cancel": {"at": _iso(-1)}}])
    orders["multi"] = multi
    window = [_iso(off) for off in range(-30, 31)]
    wish_by_id = pending_request_ids_by_date(db_session.query(Order), window)  # 출고 화면 확정 대기 희망일(같은 SQL)
    for key, order in orders.items():
        db_session.refresh(order)
        shipment = {str(d) for d in extract_all_construction_dates(order)}  # 출고 화면 = 일정 표
        if order.id in wish_by_id:
            shipment.add(wish_by_id[order.id])
        production = {d.isoformat() for d, _kind in order_ship_dates(order)}
        if key == "load":
            assert production == {_iso(2)} and shipment == {_iso(6)}, key  # 다른 것은 이 한 갈래뿐
        else:
            assert production == shipment, key
    assert {d.isoformat() for d, _k in order_ship_dates(multi)} == {_iso(1), _iso(3), _iso(9)}  # 취소 제품 날 뺌
    assert wish_by_id == {orders["wish"].id: _iso(7)}


# --------------------------------------------------------------------------- #
# C — 상한 · 경계
# --------------------------------------------------------------------------- #
def test_C_납작_열이_옛날이어도_출고일이_남은_주문은_캡에_안_밀리고_출고일_장에(client, monkeypatch) -> None:
    """경계 SQL(live_condition)은 ship_dates 와 같은 뜻 — 출고일이 7일 안 · 앞날인 주문만 다 읽고, 나머지는 캡 대상."""
    user = _login(client)
    partner = _partner()
    multi = _order("옛첫날가짜", f"{_iso(-40)}, {_iso(3)}")                         # 납작 열 -40, 남은 날 +3
    load_recent = _order("상차지난가짜", _iso(5), regional=True, loading=_iso(-2))    # 상차 -2(시공 +5 보다 앞) → 지난 7일
    wish = _order("희망만가짜", None, stage="DRAWING", partner=partner, wish=_iso(4))
    early_load = _order("이른상차가짜", _iso(2), regional=True, loading=_iso(-12))    # 상차 -12 → 지난 출고일(캡 대상)
    late_build = _order("늦은상차가짜", _iso(-10), regional=True, loading=_iso(-2))   # 상차가 시공보다 뒤 → 시공 -10
    for off in (-30, -31, -32):
        _order(f"옛주문가짜{-off}", _iso(off))
    cutoff = (get_today_kst() - datetime.timedelta(days=7)).isoformat()
    live = {oid for (oid,) in db_session.query(Order.id).filter(live_condition(cutoff)).all()}
    assert live == {multi.id, load_recent.id, wish.id}  # 화면이 놓는 날과 같은 갈래로 가른다
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 5)
    rows, stats = build_production_home(db_session, user)
    assert {r["id"] for r in rows} == {multi.id, load_recent.id, wish.id, early_load.id, late_build.id}
    assert stats == {"past_hidden": 3, "total": 8}  # 출고일이 모두 지난 옛 주문 셋만 밀린다
    days = production_home_days(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    by = {p["key"]: p for p in days["panes"]}
    assert [r["id"] for r in by[_iso(3)]["make_rows"]] == [multi.id]
    assert [r["id"] for r in by["recent"]["make_rows"]] == [load_recent.id]
    assert [r["id"] for r in by[_iso(4)]["wait_rows"]] == [wish.id]
    assert [r["id"] for r in by["past"]["make_rows"]] == [late_build.id, early_load.id] and by["past"]["hidden"] == 3
    assert by[_iso(2)]["total"] == 0 and by[_iso(5)]["total"] == 0  # 납작 열(시공) 장에 안 선다
    groups = production_home_groups(rows, get_today_kst(), past_hidden=stats["past_hidden"])
    assert [g["key"] for g in groups] == [_iso(-2), _iso(3), _iso(4), "past"]


# --------------------------------------------------------------------------- #
# E — 띠 글 · 줄 표, 음성 대조군
# --------------------------------------------------------------------------- #
def _pane(html: str, key: str) -> str:
    return html.split(f'data-foms-home-daypane="{key}"')[1].split("data-foms-home-daypane=")[0]


def _row_html(pane: str, oid: int) -> str:
    return re.search(rf'(<a class="fph-(?:dr|wi)[^"]*"[^>]*/{oid}"[^>]*>.*?</a>)', pane, re.S).group(1)


def test_E_띠_글과_상차_희망일_표_보통_주문은_그대로(client) -> None:
    _login(client)
    orders = _six(_partner())
    today_order = _order("오늘출고가짜", _iso(0))
    html = client.get(HOME).get_data(as_text=True)
    strip = html.split('<aside class="fph-strip"', 1)[1].split("</aside>", 1)[0]
    assert strip.startswith(' aria-label="출고일 2주">') and '<div class="fph-strip__h">출고일 2주<small>만들 것 / 전체</small>' in strip
    assert re.search(r'data-foms-home-daybtn="past"[^>]*>지난 출고일 0건</a>', strip)
    assert re.search(r'data-foms-home-daybtn="none"[^>]*>출고일 없음 1건</a>', strip)
    assert 'class="foms-prod-home__date"' not in html  # 태블릿은 날짜 · 전체 건수 글이 없다(사장님 2026-11-26)
    client.set_cookie("foms_ptr", "fine", domain="localhost")
    pc_html = client.get(HOME).get_data(as_text=True)
    client.delete_cookie("foms_ptr", domain="localhost")
    head = re.search(r'<span class="foms-prod-home__date">(.*?)</span>', pc_html).group(1)
    assert head.endswith(" · 전체 7건")  # PC 는 그대로 — 주문 수는 한 번(두날가짜는 장 둘)
    # 지방 + 상차 예정일 → 상차 날 장, 줄 = 진짜 시공일 표 + 같은 모양 '상차 M/D'(이름 칸 바로 뒤 — 이름을 더 줄이지 않는다)
    load = _row_html(_pane(client.get(HOME + f"?day={_iso(2)}&view=day").get_data(as_text=True), _iso(2)),
                     orders["load"].id)
    assert re.search(r'<span class="fph-due" data-foms-home-due><i>시공</i><b>[^<]+</b><small>D-6</small></span></span>'
                     rf'<span class="fph-due" data-foms-home-ship><i>상차</i><b>{_md(2)}</b></span>', load)
    # 희망일만 있는 협력사 주문 → 희망일 장(기다림 칸), 시공일 없음 표 + '희망일 M/D'
    wish = _row_html(_pane(client.get(HOME + f"?day={_iso(7)}&view=day").get_data(as_text=True), _iso(7)),
                     orders["wish"].id)
    assert wish.startswith('<a class="fph-wi has-why" ')  # 기다림 칸은 이미 줄을 넘긴다
    assert re.search(r'<span class="fph-due is-none" data-foms-home-due><b>시공일 없음</b></span><b class="fph-wi__nm">희망가짜</b>'
                     rf'<small>[^<]*</small><span class="fph-due" data-foms-home-ship><i>희망일</i><b>{_md(7)}</b></span>', wish)
    # 시공일 둘(하나 지남) → 남은 날 장에만, 표는 남은 시공일
    two_pane = _pane(client.get(HOME + f"?day={_iso(4)}&view=day").get_data(as_text=True), _iso(4))
    assert "data-foms-home-ship" not in _row_html(two_pane, orders["two"].id)
    recent = _pane(client.get(HOME + "?day=recent&view=day").get_data(as_text=True), "recent")
    assert f"/{orders['two'].id}\"" not in recent and f"/{today_order.id}\"" in recent  # 오늘 출고 = 지난 7일 장
    # 지방인데 상차 예정일이 없으면 시공일 장, 표 없음
    noload = _row_html(_pane(client.get(HOME + f"?day={_iso(5)}&view=day").get_data(as_text=True), _iso(5)),
                       orders["noload"].id)
    assert "data-foms-home-ship" not in noload
    # 음성 대조군: 시공일 하나뿐인 보통 주문은 예전과 같은 줄 · 같은 글(그 날 장 · 시공 표 · 표 없음)
    plain_pane = _pane(client.get(HOME + f"?day={_iso(3)}&view=day").get_data(as_text=True), _iso(3))
    plain = _row_html(plain_pane, orders["plain"].id)
    head = home_read_model.production_home_day(get_today_kst() + datetime.timedelta(days=3), get_today_kst())
    assert (f'<b>보통가짜</b> <small>#{orders["plain"].id}</small><span class="fph-due" data-foms-home-due><i>시공</i>'
            f'<b>{head["label"]}</b><small>D-3</small></span></span>') in plain
    assert "data-foms-home-ship" not in plain_pane and plain_pane.count("data-foms-home-dayrow=") == 1


def test_E_PC_시공일_칸에_상차_표_늦음은_출고일로(client) -> None:
    _login(client, role="ADMIN", team="CS")
    orders = _six(_partner())
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pane = client.get(HOME + f"?day={_iso(2)}&view=day").get_data(as_text=True)
    cell = pane.split(f'data-foms-home-dayrow="{orders["load"].id}"', 1)[1].split('<span class="fpc-st', 1)[0]
    head = pane.split(f'data-foms-home-dayrow="{orders["load"].id}"', 1)[0].rsplit("<div ", 1)[1]
    md6 = f"{(get_today_kst() + datetime.timedelta(days=6)).month}/{(get_today_kst() + datetime.timedelta(days=6)).day} ("
    assert f"<b>{md6}" in cell and "<span>D-6</span>" in cell and f"<span>상차 {_md(2)}</span>" in cell
    assert "is-late" in head  # 상차 모레인데 시작 전(제작 대기 늦음 = 일하는 날 2일 이하) — 기준 = 출고일
    # 음성 대조군: 보통 주문 ① 칸은 지금 글 그대로
    plain = client.get(HOME + f"?day={_iso(3)}&view=day").get_data(as_text=True)
    plain_cell = plain.split(f'data-foms-home-dayrow="{orders["plain"].id}"', 1)[1].split('<span class="fpc-st', 1)[0]
    assert "<span>D-3</span>" in plain_cell and "상차" not in plain_cell and "희망일" not in plain_cell
    row = {"structured_data": orders["plain"].structured_data, "ship_days": [get_today_kst() + datetime.timedelta(days=3)],
           "ship_due": get_today_kst() + datetime.timedelta(days=3), "ship_mark": None}
    assert pc_due(row, get_today_kst())["more"] == 0 and pc_due(row, get_today_kst())["mark"] is None


def _cell(html: str, oid: int) -> str:
    """PC 줄 하나의 ① 시공일 칸 ~ ② 상태 칸(늦음 줄 포함)."""
    row = html.split(f'data-foms-home-dayrow="{oid}"', 1)[1]
    return row.split('<span class="fpc-who"', 1)[0]


def test_D_오늘과_앞날_시공_주문은_앞날로_판정_장_늦음_PC_칸_찾기(client) -> None:
    """[오늘, +5] 주문은 +5 장에만 서고, +5 로 판정한다 — 시공일 표 · 늦음 · PC 칸 · 찾기 묶음이 +5 하나만 시공인 주문과 같다."""
    user = _login(client, role="ADMIN", team="CS")
    two = _order("오늘닷새가짜", f"{_iso(0)}, {_iso(5)}")
    one = _order("닷새만가짜", _iso(5))
    rows, _stats = build_production_home(db_session, user)
    by = {r["id"]: r for r in rows}
    today = get_today_kst()
    plus5 = today + datetime.timedelta(days=5)
    assert by[two.id]["ship_due"] == by[one.id]["ship_due"] == plus5 and by[two.id]["day_key"] == _iso(5)
    assert by[two.id]["day_label"] == by[one.id]["day_label"] and not by[two.id]["day_label"].startswith("오늘")
    assert production_late_level(by[two.id], today) == production_late_level(by[one.id], today)
    groups = production_home_groups(rows, today)
    assert [(g["key"], sorted(r["id"] for r in g["rows"])) for g in groups] == [(_iso(5), sorted([two.id, one.id]))]
    # 날짜 탭(태블릿 · 폰 줄): +5 장에 두 주문, 시공일 표 글이 같다
    pane = _pane(client.get(HOME + f"?day={_iso(5)}&view=day").get_data(as_text=True), _iso(5))
    due = re.compile(r'<span class="fph-due[^"]*" data-foms-home-due>.*?</span>')
    assert due.search(_row_html(pane, two.id)).group(0) == due.search(_row_html(pane, one.id)).group(0)
    assert f"/{two.id}\"" not in _pane(client.get(HOME + "?day=recent&view=day").get_data(as_text=True), "recent")
    # PC: ① 칸 · 늦음 줄 · 줄 꼴이 +5 하나뿐인 주문과 같고, 다른 시공일은 '외 1'
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pc = _pane(client.get(HOME + f"?day={_iso(5)}&view=day").get_data(as_text=True), _iso(5))
    two_cell, one_cell = _cell(pc, two.id), _cell(pc, one.id)
    assert "<small>외 1</small>" in two_cell and "<small>외 1</small>" not in one_cell
    assert two_cell.replace("<small>외 1</small>", "") == one_cell
    assert "오늘 시공" not in two_cell and "<span>오늘</span>" not in two_cell


def test_D_PC_늦음_줄_글(client) -> None:
    """PC 상태 칸 아래 늦음 줄 — 내일 출고인데 시작 전 = '늦음 — 내일 시공, 아직 시작 전'. 오늘 · 내일 시공 주문은 내일로 센다."""
    _login(client, role="ADMIN", team="CS")
    tomorrow = _order("내일늦음가짜", _iso(1))
    both = _order("오늘내일가짜", f"{_iso(0)}, {_iso(1)}")
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    pc = _pane(client.get(HOME + f"?day={_iso(1)}&view=day").get_data(as_text=True), _iso(1))
    for oid in (tomorrow.id, both.id):
        assert '<small>늦음 — 내일 시공, 아직 시작 전</small>' in _cell(pc, oid), oid
    head = pc.split(f'data-foms-home-dayrow="{both.id}"', 1)[0].rsplit("<div ", 1)[1]
    assert "is-late" in head


def test_D_PC_작업_시트_머리에_상차_희망일_표(client) -> None:
    _login(client, role="ADMIN", team="CS")
    ids = {key: order.id for key, order in _six(_partner()).items()}  # 요청 뒤에는 세션이 닫혀 객체를 못 읽는다
    for k, v in PC.items():
        client.set_cookie(k, v, domain="localhost")
    for key, word, off in (("load", "상차", 2), ("wish", "희망일", 7)):
        html = client.get(f"/erp/production/sheet/{ids[key]}").get_data(as_text=True)
        head = re.search(r'<span class="foms-prod-page__due fpc-sheet-due[^"]*" data-foms-pc-due>(.*?)</span>', html).group(1)
        assert head.endswith(f" · {word} {_md(off)}"), head
    plain = client.get(f"/erp/production/sheet/{ids['plain']}").get_data(as_text=True)
    head = re.search(r'<span class="foms-prod-page__due fpc-sheet-due[^"]*" data-foms-pc-due>(.*?)</span>', plain).group(1)
    assert "상차" not in head and "희망일" not in head and head.startswith("시공 ")  # 음성 대조군


def test_G_오늘_출고_주문의_아침_칩_보기는_지난_7일_장(client) -> None:
    me = User(username=f"ship_{next(_seq)}", password=generate_password_hash("x"), role="STAFF", team="PRODUCTION",
              name="김재단가짜", is_active=True, production_part="cut")
    db_session.add(me)
    db_session.commit()
    order = _order("오늘칩가짜", _iso(0), files=[{"key": "ochip/d0.png", "filename": "d0.png"}])
    old = now_utc_naive() - datetime.timedelta(days=2)
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key="ochip/d0.png", part="cut", state="NEED",
                                      picked_by_user_id=me.id, picked_by_name=me.name, picked_at=old,
                                      updated_by_user_id=me.id, updated_at=old))
    db_session.commit()
    rows, _stats = build_production_home(db_session, me)
    row = next(r for r in rows if r["id"] == order.id)
    assert row["day_label"].startswith("오늘 ") and row["day_key"] == _iso(0)  # 줄 표 · 찾기 묶음은 오늘 그대로
    chip = morning_chip(db_session, me, "cut", rows, get_today_kst())
    # [보기] = 그 주문이 선 장(오늘 날 줄은 없다 — 지난 7일), 글은 그 날
    assert chip["count"] == 1 and chip["days"][0]["key"] == "recent"
    assert chip["days"][0]["label"].startswith(f"출고 {_md(0)} (")
