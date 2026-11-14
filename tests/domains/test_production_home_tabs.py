"""생산팀 첫 화면 탭 "날짜"(안 3)·"내 공정"·"바뀐 것" — 설계서 §12.3 (2026-11-09 D13 · 2026-11-10 D17·D18).

날짜: 왼쪽 2주 띠(지난 7일 · 오늘부터 11일 · 그 뒤) + 아래 지난 시공일·시공일 없음, 오른쪽은 고른 날 한 장
     (만들 것 큰 줄 · 도면 기다림/제작 완료 작은 칸 · 다음 만들 것 미리 보기). 제목 줄에 글자 크기 손잡이.
내 공정: 공정 4탭 숫자 = 그 공정이 첫 미완인 제작 중 주문, [<공정> 끝] 단추, 보류는 단추 없이 '보류', 아래 "곧 올 것".
바뀐 것: 받은함(미확인 변경 + 취소 주문) [확인했어요].
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import (
    production_home_inbox,
    production_home_step_queues,
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
               deleted=False, orderer: str | None = None, manager: str | None = None) -> Order:
    today = get_today_kst()
    date = (today + datetime.timedelta(days=day_offset)).isoformat() if day_offset is not None else None
    production = {"steps": [{"key": k, "label": l, "done": k in steps_done, "at": None, "by_name": None} for k, l in _PRODUCTION_STEP_DEFS]}
    if hold:
        production["hold"] = {"active": True, "reason": "자재 대기"}
    parties = {"customer": {"name": name, "phone": "010-0000-0000"}}
    if orderer is not None:
        parties["orderer"] = {"name": orderer}
    if manager is not None:
        parties["manager"] = {"name": manager}
    sd = {
        "workflow": {"stage": stage},
        "parties": parties,
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


def _pane(html: str, key: str) -> str:
    """오른쪽 한 장(여는 태그 포함) — 다음 장 앞까지."""
    return html.split(f'data-foms-home-daypane="{key}"')[1].split("data-foms-home-daypane=")[0]


def test_날짜_탭은_2주_띠와_고른_날_한_장을_그린다(client) -> None:
    _make_user(client, "tabs_prod_date", "PRODUCTION")
    today = get_today_kst()
    _add_order("PRODUCTION", "오늘엣지", 0, steps_done=("cut",), with_run=True)
    _add_order("DRAWING", "오늘도면", 0)
    _add_order("CONSTRUCTION", "내일완료", 1)
    _add_order("PRODUCTION", "사흘뒤대기", 3)
    _add_order("PRODUCTION", "사흘전대기", -3)
    _add_order("PRODUCTION", "오래된주문", -20)
    _add_order("DRAWING", "날짜미정", None)
    _add_order("DRAWING", "먼날주문", 30)

    response = client.get(HOME)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # 첫 화면 = 날짜 탭. 제목 줄: 탭 넷 + 글자 크기 손잡이(①), 옛 "이번 주" 탭 없음
    assert 'data-foms-home-tab="date"' in html and "data-foms-home-date" in html
    assert "data-foms-fs-ctl" in html and ">이번 주<" not in html
    for label in (">날짜</a>", ">내 공정 <small>1</small></a>", ">바뀐 것 <small>0</small></a>", ">찾기</a>"):
        assert label in html, label
    assert "전체 8건" in html  # 머리 숫자 = 실제 총계
    # 띠: 지난 7일 + 오늘부터 11일 + 그 뒤 = 13줄, 아래 지난 시공일·시공일 없음 = 단추 15
    assert html.count('data-foms-home-daybtn="') == 15
    today_key = today.isoformat()
    today_btn = html.split(f'data-foms-home-daybtn="{today_key}"')[1].split("</a>")[0]
    assert 'aria-current="true"' in today_btn and "<b>1</b><small> / 2</small>" in today_btn
    assert '<rect class="is-p"' in today_btn and '<rect class="is-x"' in today_btn  # 막대: 만드는 중 + 도면 기다림
    # 날 단추 = 진짜 링크(스크립트 전에 눌러도 그 날로 간다) · 셸 조각 교체 제외(날 고르기 JS 가 받는다)
    tomorrow_key = (today + datetime.timedelta(days=1)).isoformat()
    tomorrow_btn = re.search(rf'<a [^>]*data-foms-home-daybtn="{tomorrow_key}"[^>]*>', html).group(0)
    assert f'href="{HOME}?day={tomorrow_key}"' in tomorrow_btn and 'data-foms-erp-no-shell="1"' in tomorrow_btn
    # 오른쪽: 고른 날(오늘) 장 하나만 그린다(11-14) — 다른 날 장은 껍데기도 내용도 없다
    assert html.count('data-foms-home-daypane="') == 1 and html.count('class="fph-pane__h"') == 1
    assert f'data-foms-home-daypane="{today_key}">' in html
    for other in ("내일완료", "오래된주문", "먼날주문", "날짜미정"):
        assert other not in html, other
    pane = _pane(html, today_key)
    assert "시공 2건 · 만들 것 1 · 도면·컨펌 기다림 1" in pane
    assert "오늘엣지" in pane and "엣지 중" in pane and "오늘도면" in pane
    assert pane.count("fph-dr__st is-done") == 1 and pane.count("fph-dr__st is-now") == 1  # 재단 끝 · 엣지 지금
    # 오늘 아래 미리 보기 = 다음에 만들 것이 있는 날(내일은 제작 완료뿐이라 건너뜀)
    assert "미리 보기" in pane and "사흘뒤대기" in pane and "내일완료" not in pane
    # 다른 날 = 같은 주소 + view=day 조각: 그 날 장 하나만(셸 · 띠 · 머리 없음), 머리글로 받은 날을 알린다
    frag = client.get(HOME + f"?day={tomorrow_key}&view=day")
    assert frag.status_code == 200 and frag.headers["X-FOMS-HOME-DAY"] == tomorrow_key
    assert frag.headers["Cache-Control"] == "no-store"
    body = frag.get_data(as_text=True)
    assert body.count('data-foms-home-daypane="') == 1 and f'data-foms-home-daypane="{tomorrow_key}">' in body
    assert "fph-strip" not in body and "data-foms-prod-home" not in body and "<!DOCTYPE" not in body and "<script" not in body
    assert "내일완료" in body and "fph-wi is-done" in body and "오늘엣지" not in body
    # 묶음 장: 지난 7일 · 지난 시공일(7일 넘음) · 그 뒤 · 시공일 없음 — 각각 조각으로
    def day(key: str) -> str:
        return client.get(HOME + f"?day={key}&view=day").get_data(as_text=True)
    assert "사흘전대기" in day("recent") and "오래된주문" in day("past")
    assert "먼날주문" in day("later") and "날짜미정" in day("none")
    # 금액 없음(D7) · 작업 시트로 감
    assert "/erp/production/sheet/" in pane

    # ?day= 로 고른 날이 열린다. 모르는 값이면 오늘(조각도 같다 — 머리글이 고른 날과 달라 JS 가 실패로 본다)
    picked = client.get(HOME + "?day=none").get_data(as_text=True)
    assert 'data-foms-home-daypane="none">' in picked and f'data-foms-home-daypane="{today_key}"' not in picked
    assert f'data-foms-home-daypane="{today_key}">' in client.get(HOME + "?day=뭐지").get_data(as_text=True)
    assert client.get(HOME + "?day=뭐지&view=day").headers["X-FOMS-HOME-DAY"] == today_key
    # 다른 탭에서 view=day 는 조각이 아니라 그 탭 페이지(날짜 · 도면 카드 탭만 날 조각이 있다)
    steps = client.get(HOME + "?tab=steps&view=day")
    assert "X-FOMS-HOME-DAY" not in steps.headers and 'data-foms-home-tab="steps"' in steps.get_data(as_text=True)


def test_바뀐_것_탭은_받은함에_취소_주문과_확인_단추(client) -> None:
    _make_user(client, "tabs_prod_changes", "PRODUCTION")
    _add_order("PRODUCTION", "만드는주문", 2, steps_done=("cut",), with_run=True)
    _add_order("PRODUCTION", "취소된주문", 2, deleted=True)

    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert 'data-foms-home-tab="changes"' in html and "fph-inbox--page" in html
    # 받은함: 취소 주문(묘비) + [확인했어요](change-ack 계약)
    assert "취소된주문" in html and "주문 취소" in html
    assert 'data-kanban-action="change-ack"' in html
    assert "js/foms/tablet-domain-sheets.js" in html
    # 다른 탭은 그 JS 를 싣지 않는다
    assert "js/foms/tablet-domain-sheets.js" not in client.get(HOME).get_data(as_text=True)


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
    assert ">조립 <small>0</small>" in html and "도장" not in html
    # 줄: 재단 칸에 재단차례(단추) + 보류중(단추 없이 보류), 엣지 칸에 엣지차례
    cut_q = html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0]
    assert "재단차례" in cut_q and "보류중" in cut_q and "엣지차례" not in cut_q
    assert cut_q.count("data-foms-home-step-done") == 1 and ">재단 끝<" in cut_q and ">보류<" in cut_q
    edge_q = html.split('data-foms-home-stepq="edge"')[1].split('data-foms-home-stepq="assemble"')[0]
    assert "엣지차례" in edge_q and 'data-step-key="edge"' in edge_q
    # 곧 올 것(사용자 11-10 ② 빈 화면 없이): 재단 = 제작 대기, 엣지 = 재단 중(보류는 빼고), 조립 = 엣지 중
    assert "곧 올 것 <b>1</b><small>제작 대기 — 작업 시트에서 [제작 시작]</small>" in cut_q and "아직대기" in cut_q
    edge_next = edge_q.split("fph-q__nextlist")[1]
    assert "곧 올 것 <b>1</b><small>재단 중</small>" in edge_q and "재단차례" in edge_next and "보류중" not in edge_next
    assemble_q = html.split('data-foms-home-stepq="assemble"')[1].split('data-foms-home-stepq="inspect"')[0]
    assert "조립에 와 있는 주문이 없어요." in assemble_q and "엣지차례" in assemble_q.split("fph-q__nextlist")[1]
    # 줄 밖 숫자: 제작 대기 1 · 검수 끝 1. 도면 주문은 아예 없음
    assert "제작 대기 <b>1</b>건 · 검수까지 끝난 것 <b>1</b>건" in html
    assert "도면중" not in html
    # 일의 양(판 장수) 글자 없음(D11)
    assert "판 " not in html


def test_탭_값이_이상하거나_옛_탭이면_날짜(client) -> None:
    _make_user(client, "tabs_prod_bad", "PRODUCTION")
    for tab in ("뭐지", "week"):
        html = client.get(HOME + f"?tab={tab}").get_data(as_text=True)
        assert 'data-foms-home-tab="date"' in html and "data-foms-home-date" in html, tab
    # 찾기 = 전체 주문 줄 목록
    found = client.get(HOME + "?tab=all").get_data(as_text=True)
    assert 'data-foms-home-tab="all"' in found and "data-foms-home-list" in found and "data-foms-home-q" in found


def test_날짜_띠_규칙() -> None:
    today = datetime.date(2026, 11, 11)  # 수

    def _row(rid: int, date: str | None, view: str, stage: str, *, changed: bool = False, done: int = 0) -> dict:
        steps = [{"key": k, "done": i < done, "now": False} for i, k in enumerate(("cut", "edge", "assemble", "inspect"))]
        return {"id": rid, "construction_date": date, "home_view": view, "home_stage": stage, "has_changes": changed,
                "home_steps": steps, "customer_name": f"집{rid}"}

    rows = [
        _row(1, "2026-11-01", "wait", "도면 기다림"),            # 10일 지남 → past
        _row(2, "2026-11-08", "prod", "제작 대기"),              # 3일 지남 → recent
        _row(3, "2026-11-11", "prod", "제작 대기"),
        _row(4, "2026-11-11", "prod", "엣지 중", done=1),
        _row(5, "2026-11-11", "prod", "재단 중", changed=True),
        _row(6, "2026-11-11", "wait", "도면 기다림"),
        _row(7, "2026-11-11", "done", "제작 완료"),
        _row(8, "2026-11-12", "wait", "도면 기다림"),
        _row(9, "2026-11-14", "prod", "조립 중", done=2),
        _row(10, "2026-11-21", "prod", "검수 끝", done=4),       # 오늘+10 = 띠의 마지막 날
        _row(11, "2026-11-22", "wait", "컨펌 기다림"),           # 그 뒤
        _row(12, None, "wait", "도면 기다림"),
    ]
    days = production_home_days(rows, today, past_hidden=7)
    keys = [b["key"] for b in days["strip"]]
    assert len(keys) == 13 and keys[0] == "recent" and keys[1] == "2026-11-11" and keys[11] == "2026-11-21" and keys[12] == "later"
    assert [b["key"] for b in days["footer"]] == ["past", "none"] and len(days["panes"]) == 15
    assert days["selected"] == "2026-11-11" and days["today_key"] == "2026-11-11"
    by = {b["key"]: b for b in days["panes"]}
    wed = by["2026-11-11"]
    assert wed["is_today"] and wed["label"] == "오늘 11/11" and wed["title"] == "오늘 11/11 (수)"
    assert wed["total"] == 5 and wed["make"] == 3 and len(wed["wait_rows"]) == 1 and len(wed["done_rows"]) == 1
    # 만들 것 순서: 바뀐 것 → 만드는 중(공정이 많이 간 것) → 제작 대기
    assert [r["id"] for r in wed["make_rows"]] == [5, 4, 3]
    # 막대: 제작 완료 1 · 만드는 중 2 · 제작 대기 1 · 도면 기다림 1 = 20/40/20/20, 이어 붙음
    assert [(s["k"], s["x"], s["w"]) for s in wed["segs"]] == [("f", 0.0, 20.0), ("p", 20.0, 40.0), ("w", 60.0, 20.0), ("x", 80.0, 20.0)]
    # 검수 끝은 만들 것 줄에 남고(제작 완료를 눌러야 함) 막대는 완료 색
    assert by["2026-11-21"]["make"] == 1 and by["2026-11-21"]["segs"][0]["k"] == "f"
    assert by["2026-11-12"]["sub"] == "목 · 내일" and by["2026-11-14"]["sub"] == "토 · D-3" and by["2026-11-14"]["is_weekend"]
    assert by["recent"]["total"] == 1 and by["recent"]["show_day"] and by["recent"]["sub"] == "11/4~11/10"
    assert by["past"]["total"] == 1 and by["past"]["note"] == "더 오래된 7건은 안 보여요"
    assert by["later"]["total"] == 1 and by["later"]["sub"] == "11/22~" and by["none"]["total"] == 1
    # 미리 보기 = 뒤 장들 만들 것을 6줄까지 이어 붙이고 모자라면 밀린 것(M4 §18). 자기 날은 아님
    def _pv(key: str) -> list:
        return [(p["title"], p["hint"], [r["id"] for r in p["rows"]]) for p in by[key]["previews"]]
    assert _pv("2026-11-11") == [("다음에 만들 것 2", "미리 보기", [9, 10]), ("지난 7일 만들 것 1", "밀린 것", [2])]
    assert _pv("recent") == [("다음에 만들 것 5", "미리 보기", [5, 4, 3, 9, 10])]  # 지난 7일 장은 오늘부터, 밀린 것 없음
    for key in ("2026-11-21", "later"):  # 뒤로 만들 것이 없는 끝날·그 뒤 장은 밀린 것만
        assert _pv(key) == [("지난 7일 만들 것 1", "밀린 것", [2])] and by[key]["previews"][0]["show_day"], key
    assert by["past"]["previews"] == [] and by["none"]["previews"] == []
    # 고른 날: 아는 열쇠만
    assert production_home_days(rows, today, "past")["selected"] == "past"
    assert production_home_days(rows, today, "2026-12-25")["selected"] == "2026-11-11"
    assert production_home_days([], today)["strip"][1]["segs"] == []
    # 오늘이 비었으면 일이 있는 가장 가까운 장: 오늘 뒤 → 그 뒤 → 지난 7일 → 지난 시공일 → 시공일 없음. 다 비면 오늘
    assert production_home_days([], today)["selected"] == "2026-11-11"
    assert production_home_days([rows[0], rows[11]], today)["selected"] == "past"
    assert production_home_days([rows[0], rows[1], rows[8]], today)["selected"] == "2026-11-14"
    assert production_home_days([rows[1], rows[10]], today)["selected"] == "later"
    assert production_home_days([rows[11]], today)["selected"] == "none"
    assert production_home_days([rows[0]], today, "2026-11-11")["selected"] == "2026-11-11"  # 직접 고른 날은 비어도 그대로


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
    # 곧 올 것: 재단 = 제작 대기 줄, 엣지 = 재단 줄(없음), 조립 = 엣지 줄에서 보류를 뺀 것
    assert [r["id"] for r in by_key["cut"]["incoming"]] == [2] and by_key["cut"]["incoming_label"] == "제작 대기"
    assert by_key["edge"]["incoming"] == [] and by_key["edge"]["incoming_label"] == "재단 중"
    assert [r["id"] for r in by_key["assemble"]["incoming"]] == [1] and by_key["assemble"]["incoming_label"] == "엣지 중"


def test_액션_JS_게이트와_핀이_같다() -> None:
    js = (ROOT / "static/js/foms/tablet-domain-sheets.js").read_text(encoding="utf-8")
    assert '[data-foms-prod-sheet-page], [data-foms-prod-home]' in js
    kanban = (ROOT / "templates/production/partials/tablet_kanban_body.html").read_text(encoding="utf-8")
    pin = kanban.split("tablet-domain-sheets.js') }}?v=")[1].split('"')[0]
    for rel in ("templates/production/sheet.html", "templates/production/partials/home_body.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={pin}" in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in ("templates/production/partials/home_all.html", "templates/production/partials/home_date.html",
                "templates/production/partials/home_changes.html", "templates/production/partials/home_steps.html",
                "templates/production/home.html", "templates/production/partials/home_body.html",
                "templates/production/partials/home_day_pane.html", "templates/production/partials/home_fragment.html",
                "templates/production/partials/home_scripts.html", "templates/production/partials/home_styles.html",
                "templates/production/partials/home_date_macros.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "<script>" not in text, rel


def test_글자_크기_손잡이를_따라가는_CSS() -> None:
    """px 글자는 ``calc(Npx * var(--foms-fs, 1))`` 꼴이어야 탭별 글자 크기가 먹는다(foms-ui-zoom.css 규칙)."""
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert not re.findall(r"font-size:\s*\d+px", css)
    assert css.count("var(--foms-fs, 1)") > 60
    # 띠가 화면 높이를 쓸 때는 전역 화면 크기 배율로 나눈다
    assert "calc(100dvh / var(--foms-ui-zoom, 1) - var(--fph-bar-h, 73px))" in css
    # 글자가 커지면 글자가 든 칸 폭도 같이(R8) — 큰 줄 도면 칸 · 내 공정 시공일 칸
    assert "auto calc(92px * var(--foms-fs, 1))" in css
    assert "calc(150px * var(--foms-fs, 1)) 190px" in css
    # 바뀐 줄은 품목 줄 두 줄까지(S5) — 바뀐 내용이 말줄임에 안 묻힌다
    # 큰 줄 품목·치수 글은 모두 두 줄까지(S5 · M3) — 바뀐 줄 전용 규칙은 없다
    assert ".fph-dr__pr { font-size: calc(14px * var(--foms-fs, 1)); color: var(--fph-text2); white-space: normal; overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;" in css
    assert ".fph-dr.is-chg .fph-dr__pr" not in css and css.count(".fph-dr__pr {") == 1


def test_옆_시트는_글자를_크게_키워도_단추와_주소가_안_잘린다() -> None:
    """실화면 S1·S2(11-10): 140% 부터 바닥 단추 셋이 400px 를 넘고, 붙은 긴 주소가 [지도] 밑으로 들어갔다."""
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    assert ".foms-prod-sheet__foot { flex-wrap: wrap; }" in css
    contact = re.search(r"\.foms-prod-sheet__contact-text \{[^}]*\}", css).group(0)
    assert "overflow-wrap: anywhere" in contact
    tile = re.search(r"\.foms-prod-sheet__drawing-file \{[^}]*\}", css).group(0)
    assert "min-height: 80px" in tile and "height: 80px;" not in tile.replace("min-height: 80px;", "")
    assert not re.findall(r"font-size:\s*\d+px", css)
