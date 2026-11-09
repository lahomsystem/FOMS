"""생산팀 첫 화면 탭 "이번 주"(안 4)·"내 공정"(안 3) — 설계서 §12.3 (2026-11-09, D13).

이번 주: 월~토 요일 칸에 시공일 기준 주문(단계 색), 오른쪽 받은함(미확인 변경 + 취소 주문) [확인했어요].
내 공정: 공정 5탭 숫자 = 그 공정이 첫 미완인 제작 중 주문, [<공정> 끝] 단추, 보류는 단추 없이 '보류'.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_read_model import (
    production_home_inbox,
    production_home_step_queues,
    production_home_week,
)
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"


def _make_user(client, username: str, team: str | None, role: str = "STAFF") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _add_order(stage: str, name: str, day_offset: int | None, *, steps_done=(), with_run=False, hold=False,
               deleted=False) -> Order:
    today = get_today_kst()
    date = (today + datetime.timedelta(days=day_offset)).isoformat() if day_offset is not None else None
    production = {"steps": [{"key": k, "label": l, "done": k in steps_done, "at": None, "by_name": None} for k, l in _PRODUCTION_STEP_DEFS]}
    if hold:
        production["hold"] = {"active": True, "reason": "자재 대기"}
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
        "site": {"address_full": f"{name} 사는 곳"},
        "schedule": {"construction": {"date": date}},
        "items": [{"product_name": "거실장", "spec_width": "3100", "quantity": 1}],
        "production": production,
    }
    order = Order(
        received_date=today.isoformat(), customer_name=name, phone="010-0000-0000", address=f"{name} 사는 곳",
        product="거실장", manager_name="관리", status="DELETED" if deleted else stage, is_erp_order=True,
        structured_data=sd, erp_stage_code=stage, erp_construction_date=date,
        deleted_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) if deleted else None,
    )
    db_session.add(order)
    db_session.commit()
    if with_run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return order


def test_이번_주_탭은_요일_칸에_시공일로_놓고_취소_주문은_받은함에(client) -> None:
    _make_user(client, "tabs_prod_week", "PRODUCTION")
    today = get_today_kst()
    monday = today - datetime.timedelta(days=today.weekday())
    # 이번 주 수요일(월요일 + 2)에 생산 중 주문, 금요일에 제작 완료 주문, 다음 주에 하나(이번 주 칸엔 안 보임)
    wed = (monday + datetime.timedelta(days=2) - today).days
    fri = (monday + datetime.timedelta(days=4) - today).days
    _add_order("PRODUCTION", "수요일주문", wed, steps_done=("cut",), with_run=True)
    _add_order("CONSTRUCTION", "금요일주문", fri)
    _add_order("PRODUCTION", "다음주주문", fri + 7)
    _add_order("PRODUCTION", "취소된주문", wed, deleted=True)

    response = client.get(HOME + "?tab=week")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-foms-home-tab="week"' in html
    assert html.count('data-foms-home-weekday="') == 6  # 월~토(일요일에 일이 없으면 6칸)
    wed_key = (monday + datetime.timedelta(days=2)).isoformat()
    wed_cell = html.split(f'data-foms-home-weekday="{wed_key}"')[1].split("data-foms-home-weekday=")[0]
    assert "수요일주문" in wed_cell and "엣지 중" in wed_cell and "fph-ev is-prod" in wed_cell
    fri_key = (monday + datetime.timedelta(days=4)).isoformat()
    fri_cell = html.split(f'data-foms-home-weekday="{fri_key}"')[1].split("</div>\n      </div>")[0]
    assert "금요일주문" in fri_cell and "fph-ev is-done" in fri_cell
    assert "다음주주문" not in html.split("fph-inbox")[0]
    # 받은함: 취소 주문(묘비) + [확인했어요](change-ack 계약)
    assert "취소된주문" in html and "주문 취소" in html
    assert 'data-kanban-action="change-ack"' in html
    assert "js/foms/tablet-domain-sheets.js" in html
    # 주 넘기기 링크
    nxt = (monday + datetime.timedelta(days=7)).isoformat()
    assert f"tab=week&amp;week={nxt}" in html or f"week={nxt}" in html


def test_내_공정_탭은_첫_미완_공정으로_줄을_세우고_보류는_단추가_없다(client) -> None:
    _make_user(client, "tabs_prod_steps", "PRODUCTION")
    _add_order("PRODUCTION", "엣지차례", 3, steps_done=("cut",), with_run=True)
    _add_order("PRODUCTION", "재단차례", 4, with_run=True)
    _add_order("PRODUCTION", "보류중", 5, with_run=True, hold=True)
    _add_order("PRODUCTION", "아직대기", 6)
    _add_order("PRODUCTION", "다끝남", 2, steps_done=tuple(k for k, _ in _PRODUCTION_STEP_DEFS), with_run=True)
    _add_order("DRAWING", "도면중", 8)

    html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    assert 'data-foms-home-tab="steps"' in html
    assert 'data-foms-home-steptab="cut" aria-selected="true" aria-controls="fph-q-cut">재단 <small>2</small>' in html
    assert 'data-foms-home-steptab="edge" aria-selected="false" aria-controls="fph-q-edge">엣지 <small>1</small>' in html
    assert ">도장 <small>0</small>" in html
    # 줄: 재단 칸에 재단차례(단추) + 보류중(단추 없이 보류), 엣지 칸에 엣지차례
    cut_q = html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0]
    assert "재단차례" in cut_q and "보류중" in cut_q and "엣지차례" not in cut_q
    assert cut_q.count("data-foms-home-step-done") == 1 and ">재단 끝<" in cut_q and ">보류<" in cut_q
    edge_q = html.split('data-foms-home-stepq="edge"')[1].split('data-foms-home-stepq="paint"')[0]
    assert "엣지차례" in edge_q and 'data-step-key="edge"' in edge_q
    # 줄 밖 숫자: 제작 대기 1 · 검수 끝 1. 도면 주문은 아예 없음
    assert "제작 대기 <b>1</b>건 · 검수까지 끝난 것 <b>1</b>건" in html
    assert "도면중" not in html
    # 일의 양(판 장수) 글자 없음(D11)
    assert "판 " not in html


def test_탭_값이_이상하면_전체_주문(client) -> None:
    _make_user(client, "tabs_prod_bad", "PRODUCTION")
    html = client.get(HOME + "?tab=뭐지").get_data(as_text=True)
    assert 'data-foms-home-tab="all"' in html and "data-foms-home-list" in html


def test_이번_주_묶음_규칙() -> None:
    today = datetime.date(2026, 11, 11)  # 수

    def _row(date: str | None, view: str, name: str) -> dict:
        return {"construction_date": date, "home_view": view, "customer_name": name, "has_changes": False}

    week = production_home_week([
        _row("2026-11-09", "prod", "월"), _row("2026-11-11", "done", "수"), _row("2026-11-11", "wait", "수2"),
        _row("2026-11-16", "prod", "다음주"), _row(None, "prod", "없음"),
    ], today)
    assert week["start"] == "2026-11-09" and week["is_this_week"] is True
    assert [d["num"] for d in week["days"]] == [9, 10, 11, 12, 13, 14]
    assert week["days"][2]["is_today"] and week["days"][0]["is_past"] and not week["days"][3]["is_past"]
    assert [len(d["events"]) for d in week["days"]] == [1, 0, 2, 0, 0, 0]
    assert week["days"][2]["count_done"] == 1 and week["days"][2]["count_wait"] == 1
    assert week["total"] == 3 and week["prev"] == "2026-11-02" and week["next"] == "2026-11-16"
    # 일요일에 일이 있으면 7칸, 다른 주로 이동
    sunday = production_home_week([_row("2026-11-22", "prod", "일요일")], today, "2026-11-16")
    assert len(sunday["days"]) == 7 and sunday["is_this_week"] is False
    # 못 읽는 week 값은 오늘의 주
    assert production_home_week([], today, "이상")["start"] == "2026-11-09"


def test_받은함과_공정_줄_규칙() -> None:
    rows = [
        {"id": 1, "customer_name": "가", "v3_product_label": "거실장", "home_stage": "엣지 중", "day_label": "11/12 (목)",
         "home_alerts": [{"kind": "construction_date", "label": "시공일 변경", "detail": "11/10 → 11/12", "from_md": "11/10", "to_md": "11/12"}],
         "home_view": "prod", "home_steps": [{"key": "cut", "done": True, "now": False}, {"key": "edge", "done": False, "now": True}]},
        {"id": 2, "customer_name": "나", "home_alerts": [], "home_view": "prod", "home_stage": "제작 대기", "home_steps": [{"key": "cut", "done": False, "now": False}]},
        {"id": 3, "customer_name": "다", "home_alerts": [], "home_view": "prod", "home_stage": "보류", "hold_active": True,
         "home_steps": [{"key": "cut", "done": True, "now": False}, {"key": "edge", "done": False, "now": False}]},
        {"id": 4, "customer_name": "라", "home_alerts": [], "home_view": "wait", "home_stage": "도면 기다림", "home_steps": []},
    ]
    inbox = production_home_inbox(rows, [{"id": 9, "customer_name": "마", "deleted_md": "11/8", "product_label": "신발장"}])
    assert [i["kind"] for i in inbox] == ["change", "cancelled"]
    assert inbox[0]["alerts"][0]["to_md"] == "11/12" and inbox[1]["day_label"] == "취소 11/8"
    queues = production_home_step_queues(rows)
    by_key = {q["key"]: q for q in queues["queues"]}
    assert by_key["edge"]["count"] == 2 and {r["id"] for r in by_key["edge"]["rows"]} == {1, 3}
    assert by_key["cut"]["count"] == 0 and queues["waiting"] == 1 and queues["finished"] == 0


def test_액션_JS_게이트와_핀이_같다() -> None:
    js = (ROOT / "static/js/foms/tablet-domain-sheets.js").read_text(encoding="utf-8")
    assert '[data-foms-prod-sheet-page], [data-foms-prod-home]' in js
    kanban = (ROOT / "templates/production/partials/tablet_kanban_body.html").read_text(encoding="utf-8")
    pin = kanban.split("tablet-domain-sheets.js') }}?v=")[1].split('"')[0]
    for rel in ("templates/production/sheet.html", "templates/production/home.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={pin}" in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in ("templates/production/partials/home_all.html", "templates/production/partials/home_week.html",
                "templates/production/partials/home_steps.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "<script>" not in text, rel
