"""도면 마감 알림 — 때 · 한 번만 · 늦음 다시 알림 · 글 · 스위치 · 기록(설계서 2026-11-22-production-drawing-arrival-upgrade §9 · §10).

받는 사람 · 링크 · 폰 · 작업 시트 줄은 ``test_drawing_deadline_alert_recipients.py``, 두 WORKER 잠금은 PG 레인
(``tests/postgres/test_drawing_deadline_alert_lock_pg.py``). 이름은 모두 지어낸 값이다.

날(2026-11): 시공 11/25 (수) → 마감 11/23 (월). 시공 11/30 (월) → 마감 11/26 (목) — 금 11/27 · 월 11/30 아침이 늦음 알림.
"""
from __future__ import annotations

import datetime
import logging

import pytest

from db import db_session
from foms.services.notifications import drawing_deadline_alert as alert
from foms.services.notifications import drawing_deadline_plan as plan
from foms.services.production_home_read_model import production_home_stage
from tests.support.drawing_deadline_seed import (
    at,
    change_order,
    enable,
    make_order,
    make_user,
    rows,
    run,
    state,
    statements,
    to_ids,
)


@pytest.fixture
def people(app):
    """도면 담당 장가짜 · 영업 이가짜(이름이 주문 담당 칸과 맞는다)."""
    return {"draw": make_user("장가짜", "DRAWING"), "sales": make_user("이가짜", "SALES")}


def _order(people, construction="2026-11-25", **kw):
    kw.setdefault("assignees", ((people["draw"], "장가짜"),))
    return make_order("김가짜", construction, **kw)


# --------------------------------------------------------------------------- #
# 때 — 칸 경계 · 마감 날만 · 영업일만
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hh,mm,slot", [
    (7, 59, None), (8, 0, "am"), (10, 59, "am"), (11, 0, None),
    (17, 59, None), (18, 0, "pm"), (20, 59, "pm"), (21, 0, None),
])
def test_칸_경계(hh, mm, slot):
    assert plan.slot_of(at("2026-11-23", hh, mm)) == slot


def test_시간대가_다른_now_도_KST_로_본다():
    utc = datetime.datetime(2026, 11, 22, 23, 30, tzinfo=datetime.timezone.utc)  # = KST 11/23 08:30
    assert plan.slot_of(plan.to_kst(utc)) == "am" and plan.to_kst(utc).date() == datetime.date(2026, 11, 23)


def test_대상_단계는_첫_화면_기다림과_같다():
    for code in plan.TARGET_STAGE_CODES:
        assert production_home_stage(code, False, [], False)[2] == "wait", code
    for code in ("PRODUCTION", "생산", "CONSTRUCTION", "시공"):
        assert production_home_stage(code, False, [], False)[2] != "wait", code


def test_마감_날_아침_첫_바퀴에만_한_번_저녁도_한_번(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people)
    assert run(at("2026-11-23", 7, 59))["notifications"] == 0 and rows() == []
    first = run(at("2026-11-23", 8, 0))
    assert first["slot"] == "am" and first["sent"] == 1 and first["notifications"] == 2
    assert to_ids(oid) == sorted(people.values())
    for hh, mm in ((8, 1), (9, 30), (10, 59), (11, 0), (17, 59)):
        assert run(at("2026-11-23", hh, mm))["notifications"] == 0
    evening = run(at("2026-11-23", 18, 0))
    assert evening["slot"] == "pm" and evening["notifications"] == 2
    assert run(at("2026-11-23", 20, 59))["notifications"] == 0 and run(at("2026-11-23", 21, 0))["notifications"] == 0
    assert len(rows(oid)) == 4
    assert set(state()) == {f"{oid}:2026-11-23:am", f"{oid}:2026-11-23:pm"}


def test_마감_날이_아니면_안_간다(people, monkeypatch):
    enable(monkeypatch)
    _order(people, "2026-11-26")  # 마감 11/24 (화)
    assert run(at("2026-11-23", 8, 5))["notifications"] == 0  # 마감 전날
    assert run(at("2026-11-23", 18, 5))["notifications"] == 0
    assert run(at("2026-11-24", 8, 5))["notifications"] == 2  # 대조군: 마감 날


def test_주말_공휴일은_쿼리_0_으로_안_간다(people, monkeypatch):
    enable(monkeypatch)
    _order(people, "2026-12-28")  # 마감 12/23 (수), 12/25 (금) 성탄절
    for day in ("2026-11-28", "2026-11-29", "2026-12-25"):
        with statements() as seen:
            got = run(at(day, 8, 30))
        assert got["notifications"] == 0 and seen == [], day


def test_아침_뒤_내려오면_저녁은_안_간다(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people)
    assert run(at("2026-11-23", 8, 2))["notifications"] == 2
    change_order(oid, stage="PRODUCTION")
    assert run(at("2026-11-23", 18, 1))["notifications"] == 0
    assert run(at("2026-11-24", 8, 1))["notifications"] == 0  # 내려온 주문은 늦음 알림도 없다


def test_보내기_직전_다시_보기는_내려온_주문과_시공일이_바뀐_주문을_뺀다(people, monkeypatch):
    enable(monkeypatch)
    keep, gone, moved = _order(people), _order(people), _order(people)
    _c, dues = plan.due_alerts(db_session, datetime.date(2026, 11, 23), "am")
    change_order(gone, stage="CONFIRM")  # 아직 기다림 단계 — 남는다
    change_order(moved, construction="2026-11-26")
    change_order(keep, stage="PRODUCTION")
    assert sorted(d.order_id for d in plan.still_waiting(db_session, dues)) == [gone]


# --------------------------------------------------------------------------- #
# 늦음 — 마감 뒤 일하는 날 아침마다(§9-7, 사장님 답 3)
# --------------------------------------------------------------------------- #
def test_마감_지나면_일하는_날_아침마다_시공일까지_금요일_다음은_월요일(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people, "2026-11-30")  # 마감 11/26 (목)
    sent = {}
    for day in ("2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30", "2026-12-01"):
        sent[day] = (run(at(day, 8, 3))["sent"], run(at(day, 18, 3))["sent"])
    assert sent == {"2026-11-26": (1, 1), "2026-11-27": (1, 0), "2026-11-28": (0, 0), "2026-11-29": (0, 0),
                    "2026-11-30": (1, 0), "2026-12-01": (0, 0)}
    assert set(state()) == {f"{oid}:2026-11-26:am", f"{oid}:2026-11-26:pm", f"{oid}:2026-11-27:late",
                            f"{oid}:2026-11-30:late"}
    assert {n.title for n in rows(oid)} == {"오늘 도면 마감이에요", "도면 마감 — 아직 안 내려왔어요", "도면 마감이 지났어요"}


def test_늦음_알림은_내려오면_멈춘다(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people, "2026-11-30")
    assert run(at("2026-11-27", 8, 3))["sent"] == 1
    change_order(oid, stage="PRODUCTION")
    assert run(at("2026-11-30", 8, 3))["sent"] == 0


def test_해를_넘기는_늦음_알림은_신정을_건너뛴다(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people, "2027-01-04")  # 마감 2026-12-30 (수)
    got = {day: run(at(day, 9, 0))["sent"] for day in ("2026-12-30", "2026-12-31", "2027-01-01", "2027-01-04")}
    assert got == {"2026-12-30": 1, "2026-12-31": 1, "2027-01-01": 0, "2027-01-04": 1}
    assert f"{oid}:2027-01-04:late" in state()


def test_시공일이_바뀌어_새_마감이_오늘이면_새_열쇠로_다시_간다(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people)  # 마감 11/23
    run(at("2026-11-23", 8, 2))
    change_order(oid, construction="2026-11-26")  # 새 마감 11/24
    assert run(at("2026-11-23", 18, 2))["sent"] == 0  # 오늘은 이제 마감 날이 아니다
    assert run(at("2026-11-24", 8, 2))["sent"] == 1
    assert {f"{oid}:2026-11-23:am", f"{oid}:2026-11-24:am"} <= set(state())


def test_바뀐_시공일의_마감이_이미_지났으면_마감_날_두_번은_없고_늦음_아침만(people, monkeypatch):
    """§9-7 1판 글 '이미 지났으면 안 간다' 는 2판 답 3(일하는 날 아침마다)이 덮는다 — 마감 날 아침 · 저녁 열쇠는 안 생기고,
    시공일 전 일하는 날 아침에 늦음 알림만 간다(시공일 당일 포함)."""
    enable(monkeypatch)
    oid = _order(people, "2026-11-30")
    change_order(oid, construction="2026-11-25")  # 11/24 (화) 에 바꿈 → 새 마감 11/23 이미 지남
    assert run(at("2026-11-24", 8, 4))["sent"] == 1 and run(at("2026-11-24", 18, 4))["sent"] == 0
    assert run(at("2026-11-25", 8, 4))["sent"] == 1 and run(at("2026-11-26", 8, 4))["sent"] == 0
    assert set(state()) == {f"{oid}:2026-11-24:late", f"{oid}:2026-11-25:late"}


# --------------------------------------------------------------------------- #
# 글(§9-4) — 해요체 · 금액 · 전화 · 주소 없음, 까닭 · 이름은 drawing_arrival 그대로
# --------------------------------------------------------------------------- #
def test_글_아침_저녁_늦음(people, monkeypatch):
    enable(monkeypatch)
    oid = _order(people)
    run(at("2026-11-23", 8, 2))
    run(at("2026-11-23", 18, 1))
    run(at("2026-11-24", 8, 1))
    got = [(n.title, n.message) for n in rows(oid) if n.target_user_id == people["sales"]]
    now = "도면 고치는 중 · 도면 장가짜 · 영업 이가짜"
    assert got == [
        ("오늘 도면 마감이에요", f"#{oid} 김가짜 · 붙박이장 — 11/25 (수) 시공이라 오늘(11/23 월)까지 도면이 생산으로 내려와야 해요. 지금: {now}"),
        ("도면 마감 — 아직 안 내려왔어요", f"저녁 6시인데 #{oid} 김가짜 도면이 아직 생산으로 안 내려왔어요. 지금: {now}. 오늘 안에 넘겨 주세요."),
        ("도면 마감이 지났어요", f"#{oid} 김가짜 도면이 마감(11/23 월)을 1일 넘겼어요. 11/25 (수) 시공이에요. 지금: {now}"),
    ]
    for _t, body in got:
        assert "010" not in body and "가짜시" not in body  # 전화 · 주소 없음(금액 칸은 읽지도 않는다)


def test_날_글은_화면_마감_글과_같은_꼴():
    from foms.services.production.drawing_arrival import LATE, day_md, deadline_head

    day = datetime.date(2026, 11, 23)
    assert day_md(day) == "11/23 (월)" and deadline_head(day, datetime.date(2026, 11, 24), LATE) == f"마감 {day_md(day)} 지났어요"


def test_글의_까닭은_화면과_같은_함수(people, monkeypatch):
    enable(monkeypatch)
    nobody = make_order("나가짜", "2026-11-25", status="PENDING")
    sales_check = _order(people, status="TRANSFERRED")
    run(at("2026-11-23", 8, 2))
    assert "지금: 담당 없음 · 영업 이가짜" in rows(nobody)[0].message
    assert "지금: 영업 확인 기다림 · 도면 장가짜 · 영업 이가짜" in rows(sales_check)[0].message


# --------------------------------------------------------------------------- #
# 스위치 · 쿼리 수 · 주문 쓰기 없음 · 기록 정리 · 창 놓침
# --------------------------------------------------------------------------- #
def test_스위치_끔이면_쿼리_0_안_보냄(people, monkeypatch):
    monkeypatch.delenv(alert.ENABLED_ENV, raising=False)
    _order(people)
    with statements() as seen:
        got = run(at("2026-11-23", 8, 2))
    assert got["enabled"] is False and got["notifications"] == 0 and seen == [] and rows() == []
    monkeypatch.setenv(alert.ENABLED_ENV, "0")
    with statements() as seen:
        assert run(at("2026-11-23", 8, 2))["enabled"] is False
    assert seen == []


def test_쿼리_수_창_안_보낼_것이_없으면_후보_1(people, monkeypatch):
    """보낸 뒤 같은 칸의 다음 바퀴: 커밋된 기록을 한 번 읽어 기억 → 그 뒤 바퀴는 후보 1개만(§8 표)."""
    enable(monkeypatch)
    _order(people)
    run(at("2026-11-23", 8, 2))
    with statements() as seen:
        assert run(at("2026-11-23", 8, 3))["due"] == 0
    assert len(seen) == 2  # 후보 + 기록 읽기(자기 쓰기는 기억하지 않는다 — 커밋 실패 때 거짓 기억 방지)
    with statements() as seen:
        assert run(at("2026-11-23", 8, 4))["due"] == 0
    assert len(seen) == 1
    alert.reset_process_memory()  # 다른 WORKER(기억 없음)도 기록 줄을 보고 안 보낸다
    assert run(at("2026-11-23", 8, 5))["notifications"] == 0


def test_쿼리_수_창_밖_0_창_안_대상_0이면_1(people, monkeypatch):
    enable(monkeypatch)
    with statements() as seen:
        run(at("2026-11-23", 7, 30))  # 아직 끝난 칸이 없다
    assert seen == []
    with statements() as seen:
        assert run(at("2026-11-23", 8, 30))["checked"] == 0
    assert len(seen) == 1 and seen[0].startswith("SELECT")
    with statements() as seen:
        run(at("2026-11-23", 11, 30))  # 아침 칸 놓침 확인 — 대상 없음이면 후보 1
    assert len(seen) == 1
    with statements() as seen:
        run(at("2026-11-23", 11, 31))  # 그 뒤 창 밖은 0
    assert seen == []


def test_백그라운드는_주문_행을_쓰지_않는다(people, monkeypatch):
    """§9-6: 알림 · 기록 줄만 쓴다 — 주문 JSONB 를 쓰면 화면 쓰기와 부딪히고 지문 · 변경 감지를 건드린다."""
    from models import Order

    enable(monkeypatch)
    oid = _order(people)
    before = dict(db_session.get(Order, oid).structured_data)
    with statements() as seen:
        assert run(at("2026-11-23", 8, 2))["notifications"] == 2
    writes = [s for s in seen if s.startswith(("UPDATE", "INSERT", "DELETE"))]
    assert writes and not [s for s in writes if s.startswith(("UPDATE ORDERS", "INSERT INTO ORDERS", "DELETE FROM ORDERS"))]
    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data == before


def test_14일_지난_열쇠는_지운다(people, monkeypatch):
    from models import SystemSetting

    enable(monkeypatch)
    db_session.add(SystemSetting(setting_key=alert.STATE_KEY, version=1, setting_value={"sent": {
        "1:2026-11-02:am": {"at": "2026-11-02T08:01+09:00", "to": ["옛가짜"], "skipped": 0},
        "2:2026-11-10:pm": {"at": "2026-11-10T18:01+09:00", "to": ["새가짜"], "skipped": 0},
    }}))
    db_session.commit()
    oid = _order(people)
    run(at("2026-11-23", 8, 2))
    assert set(state()) == {"2:2026-11-10:pm", f"{oid}:2026-11-23:am"}
    assert state()[f"{oid}:2026-11-23:am"] == {"at": "2026-11-23T08:02+09:00", "to": ["장가짜", "이가짜"], "skipped": 0}  # 받은 사람 번호 순


def test_창이_끝났는데_기록이_없으면_missed_slot_한_줄(people, monkeypatch, caplog):
    enable(monkeypatch)
    _order(people)
    with caplog.at_level(logging.WARNING, logger="drawing_deadline_alert"):
        got = run(at("2026-11-23", 12, 0))  # 아침 칸 동안 루프가 안 돌았다
    assert got["missed_slot"] == 1 and "missed_slot day=2026-11-23 slot=am orders=1" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="drawing_deadline_alert"):
        assert run(at("2026-11-23", 12, 1))["missed_slot"] == 0  # 칸마다 한 번만
    assert "missed_slot" not in caplog.text
    assert run(at("2026-11-23", 18, 30))["notifications"] == 2  # 저녁 칸은 그대로 간다
    alert.reset_process_memory()
    assert run(at("2026-11-23", 21, 30))["missed_slot"] == 1  # 대조군: 저녁은 보냈다, 아침만 놓침
