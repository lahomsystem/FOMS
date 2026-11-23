"""도면 내려옴 · 마감 · 막힌 까닭 · 담당 이름 — 설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md §4 · §8 · §10.

순수 함수(:mod:`foms.services.production.drawing_arrival`)는 DB 없이 돈다. 마지막 시험만 첫 화면 행을 실제로 만들어
'여러 시공일 주문은 장을 고르는 납작 칸(먼저 적힌 날) 기준'(§4-6)을 고정한다. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

import pytest

from foms.services.production import drawing_arrival as da

D = datetime.date


@pytest.mark.parametrize(("day", "want"), [
    (D(2026, 11, 25), D(2026, 11, 23)),  # 수 → 월(화 1 · 월 2)
    (D(2026, 11, 28), D(2026, 11, 26)),  # 토 → 목(금 1 · 목 2)
    (D(2026, 11, 30), D(2026, 11, 26)),  # 월 → 목(토 · 일 빼고) — 토요일 시공과 같은 마감
    (D(2026, 12, 1), D(2026, 11, 27)),  # 화 → 금
    (D(2026, 12, 28), D(2026, 12, 23)),  # 12/25 성탄절 빠짐
    (D(2027, 1, 4), D(2026, 12, 30)),  # 1/1 신정 빠짐(해 넘김)
    (D(2027, 2, 10), D(2027, 2, 4)),  # 설 연휴 2/6 ~ 2/9(대체 휴일 포함) 빠짐
    (D(2027, 3, 2), D(2027, 2, 25)),  # 3/1 삼일절 빠짐
])
def test_마감은_시공일_앞_영업일_둘째_날(day: datetime.date, want: datetime.date) -> None:
    assert da.DRAWING_DEADLINE_WORKDAYS == 2
    assert da.drawing_deadline(day) == want


def test_마감_상태_넷과_금요일의_월요일_마감() -> None:
    tue = D(2026, 11, 24)
    assert da.deadline_state(D(2026, 11, 23), tue, all_in=False) == "late"
    assert da.deadline_state(D(2026, 11, 24), tue, all_in=False) == "soon"  # 오늘
    assert da.deadline_state(D(2026, 11, 25), tue, all_in=False) == "soon"  # 내일
    assert da.deadline_state(D(2026, 11, 26), tue, all_in=False) == "calm"
    assert da.deadline_state(D(2026, 11, 23), tue, all_in=True) == "ok"  # 다 오면 마감과 상관없이 초록
    assert da.deadline_state(None, tue, all_in=False) == "calm"  # 시공일 없음 = 다 옴 또는 여유만
    fri = D(2026, 11, 27)
    assert da.deadline_state(D(2026, 11, 30), fri, all_in=False) == "soon"  # 금요일에 월요일 마감 = 빠듯(§14 답 4)
    assert da.deadline_state(D(2026, 12, 1), fri, all_in=False) == "calm"
    assert da.soon_word(D(2026, 11, 30), fri) == "월요일"
    assert da.soon_word(fri, fri) == "오늘" and da.soon_word(D(2026, 11, 28), fri) == "내일"
    sat = D(2026, 11, 28)  # 쉬는 날에 보면 다음 영업일(월) 마감도 빠듯
    assert da.deadline_state(D(2026, 11, 30), sat, all_in=False) == "soon" and da.soon_word(D(2026, 11, 30), sat) == "월요일"
    # 하루 장 머리 글
    assert da.deadline_head(D(2026, 11, 23), tue, "late") == "마감 11/23 (월) 지났어요"
    assert da.deadline_head(tue, tue, "soon") == "마감 오늘 11/24 (화)"
    assert da.deadline_head(D(2026, 11, 25), tue, "soon") == "마감 내일 11/25 (수)"
    assert da.deadline_head(D(2026, 11, 30), fri, "soon") == "마감 11/30 (월)"
    assert da.deadline_head(D(2026, 11, 26), tue, "calm") == "마감 11/26 (목)"


def _wait(rid: int, day: str | None, **sd) -> dict:
    return {"id": rid, "home_view": "wait", "construction_date": day, "structured_data": sd, "manager_name": "-"}


def _made(rid: int, day: str | None, view: str = "prod") -> dict:
    return {"id": rid, "home_view": view, "construction_date": day, "structured_data": {}}


def test_줄_글_x_n_과_가장_급한_상태() -> None:
    tue = D(2026, 11, 24)
    assert da.arrival_line([], tue) is None
    # 하루 줄: 제작 완료도 n 에 든다
    line = da.arrival_line([_made(1, "2026-11-25"), _made(2, "2026-11-25", "done"), _wait(3, "2026-11-25")], tue)
    assert line == {"x": 2, "n": 3, "state": "late", "strip": "도면 2/3 마감 지남", "pane": "도면 2/3 내려옴"}
    assert da.arrival_line([_made(1, "2026-11-26"), _wait(2, "2026-11-26")], tue)["strip"] == "도면 1/2 마감 오늘"
    assert da.arrival_line([_wait(2, "2026-11-27")], tue)["strip"] == "도면 0/1 마감 내일"
    assert da.arrival_line([_wait(2, "2026-11-30")], tue)["strip"] == "도면 0/1"
    assert da.arrival_line([_made(1, "2026-11-25"), _made(2, "2026-11-25", "done")], tue)["strip"] == "도면 2/2 다 옴"
    # 여러 날 줄: 주문마다 매겨 가장 급한 것(늦음 > 빠듯 > 여유). 빠듯끼리는 가장 이른 마감의 '언제'
    many = [_wait(1, "2026-12-03"), _wait(2, "2026-11-27"), _wait(3, "2026-11-26"), _made(4, "2026-11-20")]
    assert da.arrival_line(many, tue)["strip"] == "도면 1/4 마감 오늘"
    assert da.arrival_line(many + [_wait(5, "2026-11-25")], tue)["state"] == "late"
    # 시공일 없음 줄은 마감이 없어 다 옴 또는 여유만
    assert da.arrival_line([_wait(1, None)], tue)["state"] == "calm"
    assert da.arrival_line([_made(1, None)], tue)["state"] == "ok"
    # 붙여 둔 값이 있으면 그것을 쓴다(같은 판정 한 곳)
    rows = [_wait(1, "2026-12-03")]
    da.attach_drawing_arrival(rows, tue)
    assert rows[0]["dw_state"] == "calm" and rows[0]["dw_deadline"] == D(2026, 12, 1) and rows[0]["dw_deadline_md"] == "12/1"


@pytest.mark.parametrize(("sd", "key", "label"), [
    ({"drawing_status": "TRANSFERRED"}, "sales_check", "영업 확인 기다림"),  # 담당과 상관없음
    ({"drawing_status": "TRANSFERRED", "drawing_assignees": [{"id": 7, "name": "장미래"}]}, "sales_check", "영업 확인 기다림"),
    ({"drawing_status": "CONFIRMED"}, "customer", "고객 컨펌 기다림"),
    ({"drawing_status": "DONE", "drawing_assignees": [{"id": 7, "name": "장미래"}]}, "customer", "고객 컨펌 기다림"),
    ({"drawing_status": "RETURNED"}, "no_owner", "담당 없음"),  # 고치는 중이라도 담당이 없으면 담당 없음
    ({"drawing_status": "PENDING"}, "no_owner", "담당 없음"),
    ({}, "no_owner", "담당 없음"),
    ({"drawing_status": "RETURNED", "drawing_assignees": [{"id": 7, "name": "장미래"}]}, "fixing", "도면 고치는 중"),
    ({"drawing_status": "PENDING", "drawing_assignees": [{"id": 7, "name": "장미래"}]}, "drawing", "도면 그리는 중"),
    ({"drawing_assignees": [{"id": 7, "name": "장미래"}]}, "drawing", "도면 그리는 중"),  # 빈 값
    ({"drawing_status": "WHATEVER", "assignments": {"drawing_assignee_user_ids": [7]}}, "drawing", "도면 그리는 중"),  # 모르는 값 · id 만
    ({"drawing": {"status": "returned"}, "shipment": {"drawing_managers": ["오가람"]}}, "fixing", "도면 고치는 중"),  # 중첩 · 옛 이름 칸
])
def test_막힌_까닭_다섯(sd: dict, key: str, label: str) -> None:
    got = da.drawing_blocker(sd)
    assert got == {"key": key, "label": label, "none": key == "no_owner"}


def test_단계는_까닭을_바꾸지_않는다() -> None:
    # 도면 단계 + CONFIRMED(단계 유지 수령 확정) = 고객 컨펌 기다림, 고객컨펌 단계 + PENDING(옛 주문) = 담당 있음/없음에 따라 5 · 3
    stage_drawing = {"workflow": {"stage": "DRAWING"}, "drawing_status": "CONFIRMED"}
    stage_confirm = {"workflow": {"stage": "CONFIRM"}, "drawing_status": "PENDING"}
    assert da.drawing_blocker(stage_drawing)["label"] == "고객 컨펌 기다림"
    assert da.drawing_blocker(stage_confirm)["label"] == "담당 없음"
    assert da.drawing_blocker({**stage_confirm, "drawing_assignees": [{"name": "장미래"}]})["label"] == "도면 그리는 중"
    assert da.drawing_blocker(None)["label"] == "담당 없음"


def test_담당_이름_대체와_빈_값() -> None:
    sd = {"drawing_assignees": [{"id": 1, "name": "장미래"}, {"id": 2, "name": "오가람"}],
          "shipment": {"drawing_managers": ["옛이름"]}}
    assert da.drawing_people(sd, "이하늘") == {"drawing": ["장미래", "오가람"], "sales": "이하늘",
                                               "parts": ["도면 장미래, 오가람", "영업 이하늘"],
                                               "text": "도면 장미래, 오가람 · 영업 이하늘"}
    # drawing_assignees 가 비면 shipment.drawing_managers(같은 쓰기가 함께 남긴 옛 칸)
    assert da.drawing_people({"shipment": {"drawing_managers": ["오가람", {"name": "나별"}]}}, None)["text"] == "도면 오가람, 나별"
    # 영업 담당 '-' · 빈 값은 안 쓴다
    assert da.drawing_people({}, "-") == {"drawing": [], "sales": "", "parts": [], "text": ""}
    assert da.drawing_people({"drawing_assignees": [{"name": " 장미래 "}]}, "  ")["text"] == "도면 장미래"


def test_붙이기는_기다림_행만_날짜마다_한_번(monkeypatch) -> None:
    tue = D(2026, 11, 24)
    calls: list[datetime.date] = []
    real = da.drawing_deadline

    def _count(day):
        calls.append(day)
        return real(day)

    monkeypatch.setattr(da, "drawing_deadline", _count)
    rows = [_wait(1, "2026-11-25", drawing_status="RETURNED", drawing_assignees=[{"name": "장미래"}]),
            _wait(2, "2026-11-25"), _wait(3, None), _made(4, "2026-11-25")]
    rows[0]["manager_name"] = "이하늘"
    da.attach_drawing_arrival(rows, tue)
    assert calls == [D(2026, 11, 25)]  # 같은 날 두 행 = 한 번
    assert rows[0]["dw_blocker"]["label"] == "도면 고치는 중" and rows[0]["dw_people"]["text"] == "도면 장미래 · 영업 이하늘"
    assert rows[0]["dw_state"] == "late" and rows[0]["dw_deadline_md"] == "11/23"
    assert rows[1]["dw_blocker"]["none"] is True and rows[1]["dw_people"]["text"] == ""
    assert rows[2]["dw_deadline"] is None and rows[2]["dw_deadline_md"] == "" and rows[2]["dw_state"] == "calm"
    assert "dw_state" not in rows[3]  # 내려온 행은 그대로


def test_여러_시공일_주문은_장을_고르는_납작_칸_기준(client) -> None:
    """§4-6: 띠 · 장 제목 · 칸이 한 날을 써야 x/n 과 '마감은 묶음 머리에 한 번'이 맞는다 — 기준 = 납작 칸(먼저 적힌 날).
    다른 제품 날이 더 이르면 마감이 늦게 잡힐 수 있다(§12 위험 — 규칙을 여기서 고정)."""
    from db import db_session
    from foms.services.datetime_kst import get_today_kst
    from foms.services.production_home_read_model import build_production_home
    from models import Order, User

    today = get_today_kst()
    flat = today + datetime.timedelta(days=20)
    earlier = today + datetime.timedelta(days=9)
    user = User(username="dw_multi", password="x", role="STAFF", team="PRODUCTION", name="생산", is_active=True)
    db_session.add(user)
    sd = {"workflow": {"stage": "DRAWING"}, "parties": {"customer": {"name": "여러날집"}},
          "schedule": {"construction": {"date": flat.isoformat()}},
          "items": [{"product_name": "붙박이장", "construction_date": earlier.isoformat()}]}
    db_session.add(Order(received_date=today.isoformat(), customer_name="여러날집", phone="010-0000-0000", address="가짜",
                         product="장", status="DRAWING", is_erp_order=True, erp_stage_code="DRAWING",
                         erp_construction_date=flat.isoformat(), structured_data=sd))
    db_session.commit()
    rows, _stats = build_production_home(db_session, user, today=today)
    row = next(r for r in rows if r["customer_name"] == "여러날집")
    assert row["dw_deadline"] == da.drawing_deadline(flat) != da.drawing_deadline(earlier)
    assert row["dw_blocker"]["label"] == "담당 없음"
