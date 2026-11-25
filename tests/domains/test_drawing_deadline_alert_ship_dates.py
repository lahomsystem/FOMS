"""도면 마감 자동 알림 = 화면과 같은 출고일(사장님 2026-11-25 "출고일 기준으로 바꾸기").

지방 주문은 상차 예정일(시공일보다 뒤면 시공일), 시공일 없이 희망일만 있는 협력사 주문도 대상, 시공일이 여럿이면 화면과 같은 판정 날
(내일 이후 가장 가까운 날). 대조군: 시공일 하나뿐인 보통 주문은 전과 같은 날 · 같은 열쇠. 폰 · 배지 배달은 부르지 않는다(읽기 · 기록만).

날(2026-11): 월 11/23 · 화 11/24 · 수 11/25 · 목 11/26 · 금 11/27 · 월 11/30.
"""
from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.notifications import drawing_deadline_plan as plan
from foms.services.production.drawing_arrival import drawing_deadline
from models import Order, PartnerOrg
from tests.support.drawing_deadline_seed import at, enable, make_order, make_user, run, state

D = datetime.date


@pytest.fixture
def people(app):
    return {"draw": make_user("장가짜", "DRAWING"), "sales": make_user("이가짜", "SALES")}


def _order(people, construction, *, regional=False, loading=None, partner=None, wish=None) -> int:
    oid = make_order("김가짜", construction, assignees=((people["draw"], "장가짜"),))
    order = db_session.get(Order, oid)
    # 납작 열 = 처음 적힌 날 앞 10자(String(10) — 실제 저장의 sync_erp_flat_columns 와 같은 꼴)
    order.erp_construction_date = (construction or "").split(",")[0].strip()[:10] or None
    order.is_regional, order.shipping_scheduled_date, order.partner_org_id = regional, loading, partner
    if wish:
        sd = dict(order.structured_data)
        sd["partner_intake"] = {"requested_construction": {"date": wish, "time": "오전"}}
        order.structured_data = sd
    db_session.commit()
    return oid


def _dues(today: str, slot: str = "am") -> dict[int, tuple[str, D, D]]:
    _checked, dues = plan.due_alerts(db_session, D.fromisoformat(today), slot)
    return {d.order_id: (d.kind, d.deadline, d.day) for d in dues}


def _texts(today: str, slot: str = "am") -> dict[int, str]:
    _checked, dues = plan.due_alerts(db_session, D.fromisoformat(today), slot)
    return {d.order_id: plan.alert_text(d, D.fromisoformat(today))[1] for d in dues}


def test_알림_글의_날_이름은_놓인_날_보통_주문은_글자까지_그대로(people):
    org = PartnerOrg(name="가짜협력사글")
    db_session.add(org)
    db_session.commit()
    load = _order(people, "2026-11-30", regional=True, loading="2026-11-26")    # 상차 11/26 → 마감 11/24
    wrong = _order(people, "2026-11-26", regional=True, loading="2026-11-30")   # 상차가 뒤 → 시공 11/26
    wish = _order(people, None, partner=org.id, wish="2026-11-26")              # 희망 11/26 → 마감 11/24
    plain = _order(people, "2026-11-26")                                         # 대조군
    am = _texts("2026-11-24")
    assert f" — 11/26 (목) 상차라 오늘(11/24 화)까지 도면이 생산으로 내려와야 해요. 지금: " in am[load]
    assert f" — 11/26 (목) 희망일이라 오늘(11/24 화)까지 도면이 생산으로 내려와야 해요. 지금: " in am[wish]
    for oid in (wrong, plain):
        assert am[oid].startswith(f"#{oid} 김가짜 · 붙박이장 — 11/26 (목) 시공이라 오늘(11/24 화)까지 도면이 생산으로 내려와야 해요. "
                                  "지금: "), oid
    late = _texts("2026-11-25")  # 마감 11/24 지남 → 늦음 아침
    assert "을 1일 넘겼어요. 11/26 (목) 상차예요. 지금: " in late[load]
    assert "을 1일 넘겼어요. 11/26 (목) 희망일이에요. 지금: " in late[wish]
    assert late[plain].startswith(f"#{plain} 김가짜 도면이 마감(11/24 화)을 1일 넘겼어요. 11/26 (목) 시공이에요. 지금: ")
    assert _texts("2026-11-24", "pm")[load].startswith("저녁 6시인데 ")  # 저녁 글은 날 이름이 없다 — 그대로


def test_지방_주문은_상차_예정일로_마감을_센다(people):
    load = _order(people, "2026-11-30", regional=True, loading="2026-11-26")   # 상차 11/26 → 마감 11/24
    wrong = _order(people, "2026-11-26", regional=True, loading="2026-11-30")  # 상차가 시공보다 뒤 → 시공 11/26
    plain = _order(people, "2026-11-30")                                         # 대조군: 마감 11/26
    on24 = _dues("2026-11-24")
    assert on24[load] == ("am", D(2026, 11, 24), D(2026, 11, 26))
    assert on24[wrong] == ("am", D(2026, 11, 24), D(2026, 11, 26))
    assert plain not in on24 and _dues("2026-11-26")[plain] == ("am", D(2026, 11, 26), D(2026, 11, 30))
    assert drawing_deadline(D(2026, 11, 30)) == D(2026, 11, 26)


def test_희망일만_있는_협력사_주문도_대상(people):
    org = PartnerOrg(name="가짜협력사알림")
    db_session.add(org)
    db_session.commit()
    wish = _order(people, None, partner=org.id, wish="2026-11-25")  # 희망 11/25 → 마감 11/23
    assert _dues("2026-11-23")[wish] == ("am", D(2026, 11, 23), D(2026, 11, 25))
    no_partner = _order(people, None, wish="2026-11-25")  # 대조군: 협력사 주문이 아니면 희망일을 안 본다
    assert no_partner not in _dues("2026-11-23")


def test_시공일이_여럿이면_화면과_같은_판정_날(people):
    multi = _order(people, "2026-11-20, 2026-11-27")  # 납작 열 11/20(지남) — 판정 날 11/27 → 마감 11/25
    assert _dues("2026-11-25")[multi] == ("am", D(2026, 11, 25), D(2026, 11, 27))
    assert multi not in _dues("2026-11-23")


def test_보통_주문은_전과_같은_날_같은_열쇠_다시_보기도_같다(people, monkeypatch):
    enable(monkeypatch)
    plain = _order(people, "2026-11-25")
    load = _order(people, "2026-11-30", regional=True, loading="2026-11-25")
    assert run(at("2026-11-23", 8, 2))["sent"] == 2
    assert {f"{plain}:2026-11-23:am", f"{load}:2026-11-23:am"} <= set(state())
    assert run(at("2026-11-23", 8, 30))["sent"] == 0  # 같은 칸 두 번은 없다
    _c, dues = plan.due_alerts(db_session, D(2026, 11, 23), "pm")
    assert sorted(d.order_id for d in plan.still_waiting(db_session, dues)) == sorted([plain, load])
    order = db_session.get(Order, load)
    order.shipping_scheduled_date = "2026-11-27"  # 상차 예정일이 바뀌면 보내기 직전 다시 보기에서 빠진다
    db_session.commit()
    assert sorted(d.order_id for d in plan.still_waiting(db_session, dues)) == [plain]
