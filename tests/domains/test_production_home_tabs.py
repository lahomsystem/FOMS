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
from foms.services import production_home_read_model
from foms.services.production_home_read_model import (
    production_home_counts,
    production_home_days,
    production_home_stage,
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
    today_btn = html.split(f'data-foms-home-daybtn="{today_key}"')[1].split("</button>")[0]
    assert 'aria-pressed="true"' in today_btn and "<b>1</b><small> / 2</small>" in today_btn
    assert '<rect class="is-p"' in today_btn and '<rect class="is-x"' in today_btn  # 막대: 만드는 중 + 도면 기다림
    # 오른쪽: 오늘 장만 보이고 나머지는 hidden
    assert f'data-foms-home-daypane="{today_key}">' in html
    assert html.count('data-foms-home-daypane="') == 15
    assert len(re.findall(r'data-foms-home-daypane="[^"]+" hidden>', html)) == 14
    pane = _pane(html, today_key)
    assert "시공 2건 · 만들 것 1 · 도면·컨펌 기다림 1" in pane
    assert "오늘엣지" in pane and "엣지 중" in pane and "오늘도면" in pane
    assert pane.count("fph-dr__st is-done") == 1 and pane.count("fph-dr__st is-now") == 1  # 재단 끝 · 엣지 지금
    # 오늘 아래 미리 보기 = 다음에 만들 것이 있는 날(내일은 제작 완료뿐이라 건너뜀)
    assert "미리 보기" in pane and "사흘뒤대기" in pane and "내일완료" not in pane
    tomorrow = _pane(html, (today + datetime.timedelta(days=1)).isoformat())
    assert "내일완료" in tomorrow and "fph-wi is-done" in tomorrow
    # 묶음 장: 지난 7일 · 지난 시공일(7일 넘음) · 그 뒤 · 시공일 없음
    assert "사흘전대기" in _pane(html, "recent") and "오래된주문" in _pane(html, "past")
    assert "먼날주문" in _pane(html, "later") and "날짜미정" in _pane(html, "none")
    # 금액 없음(D7) · 작업 시트로 감
    assert "/erp/production/sheet/" in pane

    # ?day= 로 고른 날이 열린다. 모르는 값이면 오늘
    picked = client.get(HOME + "?day=none").get_data(as_text=True)
    assert 'data-foms-home-daypane="none">' in picked and f'data-foms-home-daypane="{today_key}" hidden>' in picked
    assert f'data-foms-home-daypane="{today_key}">' in client.get(HOME + "?day=뭐지").get_data(as_text=True)


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
    for rel in ("templates/production/sheet.html", "templates/production/home.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={pin}" in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in ("templates/production/partials/home_all.html", "templates/production/partials/home_date.html",
                "templates/production/partials/home_changes.html", "templates/production/partials/home_steps.html",
                "templates/production/home.html"):
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


# ── 리뷰 고침 묶음(원장 §16 R1·R2·R3·R5·R10, 2026-11-10) ──

def _reload_href(html: str) -> str:
    return re.search(r'data-foms-home-reload href="([^"]*)"', html).group(1)


def test_보류는_생산_단계만_도면_컨펌_보류는_기다림() -> None:
    steps = [{"key": "cut", "label": "재단", "done": False, "now": False}]
    assert production_home_stage("PRODUCTION", False, steps, True) == ("보류", "생산", "prod")
    assert production_home_stage("도면", False, steps, True) == ("도면 기다림", "도면팀", "wait")
    assert production_home_stage("CONFIRM", False, steps, True) == ("컨펌 기다림", "영업", "wait")
    assert production_home_stage("CONSTRUCTION", True, steps, True) == ("제작 완료", "시공 대기", "done")


def test_내_공정_탭_숫자는_공정_줄_합과_같다_보류_run_없음_포함(client) -> None:
    _make_user(client, "tabs_prod_r1", "PRODUCTION")
    _add_order("PRODUCTION", "보류런없음", 0, hold=True)
    _add_order("PRODUCTION", "보류런있음", 0, steps_done=("cut",), with_run=True, hold=True)
    _add_order("DRAWING", "도면보류", 0, hold=True)
    _add_order("PRODUCTION", "재단차례", 0, with_run=True)
    _add_order("PRODUCTION", "아직대기", 0)
    _add_order("PRODUCTION", "다끝남", 0, steps_done=tuple(k for k, _ in _PRODUCTION_STEP_DEFS), with_run=True)

    steps_html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    lane_counts = [int(n) for n in re.findall(r'data-foms-home-steptab="[a-z]+"[^>]*>[^<]+<small>(\d+)</small>', steps_html)]
    assert len(lane_counts) == 4 and sum(lane_counts) == 3  # 재단 = 보류런없음·재단차례, 엣지 = 보류런있음
    assert f">내 공정 <small>{sum(lane_counts)}</small></a>" in steps_html
    cut_q = steps_html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0].split("fph-q__nextlist")[0]
    assert "보류런없음" in cut_q and "재단차례" in cut_q and "도면보류" not in steps_html
    # 날짜 탭: 도면 단계 보류는 큰 줄이 아니라 도면·컨펌 기다림 칸, 큰 줄 클래스 = 제작 대기 w · 만드는 중/보류 p · 검수 끝 f
    date_html = client.get(HOME).get_data(as_text=True)
    assert f">내 공정 <small>{sum(lane_counts)}</small></a>" in date_html
    pane = _pane(date_html, get_today_kst().isoformat())
    assert "만들 것 5 · 도면·컨펌 기다림 1" in pane and ">도면·컨펌 기다림 1 <small>" in pane
    big = {m.group(2).strip(): m.group(1) for m in re.finditer(
        r'<a class="fph-dr is-([wfp])[^"]*"[^>]*>.*?fph-dr__nm">([^<]+)<small>', pane, re.S)}
    assert big == {"보류런없음": "p", "보류런있음": "p", "재단차례": "p", "아직대기": "w", "다끝남": "f"}
    assert "도면보류" in pane.split("fph-wg")[1]


def test_바뀐_것_숫자에_취소_주문이_모든_탭에서_든다(client) -> None:
    _make_user(client, "tabs_prod_r2", "PRODUCTION")
    _add_order("PRODUCTION", "만드는주문", 2, with_run=True)
    _add_order("PRODUCTION", "취소된주문", 2, deleted=True)
    changes = client.get(HOME + "?tab=changes").get_data(as_text=True)
    inbox_n = changes.count("data-foms-home-inbox=")
    assert inbox_n == 1
    for url in (HOME, HOME + "?tab=steps", HOME + "?tab=all", HOME + "?tab=changes"):
        html = client.get(url).get_data(as_text=True)
        assert f'>바뀐 것 <small class="is-hot">{inbox_n}</small></a>' in html, url
    assert production_home_counts([{"has_changes": True}, {}], 2)["changed"] == 3


def test_다시_받기_주소는_직접_고른_날만_붙인다(client) -> None:
    _make_user(client, "tabs_prod_r3", "PRODUCTION")
    _add_order("PRODUCTION", "사흘뒤", 3)  # 오늘이 비어 자동으로 사흘 뒤 장이 열린다
    today_key = get_today_kst().isoformat()
    auto = client.get(HOME).get_data(as_text=True)
    assert 'aria-pressed="true"' in auto.split(f'data-foms-home-daybtn="{(get_today_kst() + datetime.timedelta(days=3)).isoformat()}"')[1].split("</button>")[0]
    assert _reload_href(auto) == HOME
    assert _reload_href(client.get(HOME + f"?day={today_key}").get_data(as_text=True)) == f"{HOME}?day={today_key}"
    assert _reload_href(client.get(HOME + "?day=recent").get_data(as_text=True)) == f"{HOME}?day=recent"
    assert _reload_href(client.get(HOME + "?day=뭐지").get_data(as_text=True)) == HOME
    assert _reload_href(client.get(HOME + "?tab=steps").get_data(as_text=True)) == f"{HOME}?tab=steps"
    days = production_home_days([], datetime.date(2026, 11, 11))
    assert days["auto"] and not production_home_days([], datetime.date(2026, 11, 11), "2026-11-11")["auto"]


def test_지난_시공일_장은_안_읽은_수가_있으면_없어요를_숨기고_단추에_같이(client, monkeypatch) -> None:
    _make_user(client, "tabs_prod_r5", "PRODUCTION")
    monkeypatch.setattr(production_home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 1)
    _add_order("PRODUCTION", "오늘대기", 0)
    _add_order("PRODUCTION", "옛주문하나", -20)
    _add_order("PRODUCTION", "옛주문둘", -30)
    html = client.get(HOME + "?day=past").get_data(as_text=True)
    past = _pane(html, "past")
    assert "더 오래된 2건은 안 보여요" in past and "이 날은 시공이 없어요." not in past
    assert "옛주문하나" not in past
    btn = html.split('data-foms-home-daybtn="past"')[1].split("</button>")[0]
    assert btn.endswith(">지난 시공일 0건<small>2건 더</small>")  # 안 읽은 수는 둘째 줄 작은 글(M5)
    # 시공일 없음 장은 안 읽은 수가 없으니 '없어요' 그대로, 단추는 한 줄(small 없음)
    assert "이 날은 시공이 없어요." in _pane(html, "none")
    none_btn = html.split('data-foms-home-daybtn="none"')[1].split("</button>")[0]
    assert none_btn.endswith(">시공일 없음 0건") and "<small>" not in none_btn
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-sf small { display: block; font-size: calc(12px * var(--foms-fs, 1));" in css


def test_작업_시트_뒤로_단추는_생산이고_같은_출처_홈에서만_주소를_되돌린다() -> None:
    sheet = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    back = sheet.split('class="foms-prod-page__back"')[1].split("</a>")[0]
    assert "data-foms-prod-back" in back and back.endswith(">생산") and "전체 주문" not in back
    js = (ROOT / "static/js/production/foms-production-sheet-page.js").read_text(encoding="utf-8")
    assert "document.referrer" in js and "from.origin !== window.location.origin" in js
    assert "from.pathname !== home.pathname" in js and "if (!back || !document.referrer) { return; }" in js


def test_제목_줄_보드_단추와_레일_생산이_첫_화면(client, monkeypatch) -> None:
    """D19(11-10): 제목 줄 탭 끝(찾기 뒤)에 옛 보드로 가는 [보드], 태블릿 레일 '생산' 은 첫 화면으로 가고 강조된다."""
    user = _make_user(client, "tabs_prod_board", "PRODUCTION")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    html = client.get(HOME).get_data(as_text=True)
    nav = html[html.index('class="foms-prod-home__nav"'):]
    nav = nav[: nav.index("</nav>")]
    board = re.search(r"<a [^>]*data-foms-home-board[^>]*>", nav)
    assert board and 'href="/erp/production/dashboard"' in board.group(0)
    assert "foms-prod-home__navtab--out" in board.group(0)
    assert nav.index(">찾기</a>") < nav.index("data-foms-home-board")
    assert "home.css?v=20261111b" in html
    # [보드] 는 온전한 페이지 이동(첫 화면은 조각 화면이 아니다)
    assert 'data-foms-erp-no-shell="1"' in board.group(0)
    # 제목 줄 오른쪽 묶음: 받음 표시 · 글자 손잡이 · [다시 받기] 가 한 묶음이라 줄이 넘쳐도 같이 내려간다(② 빈 줄 없이)
    tools = html[html.index('class="foms-prod-home__tools"'):]
    tools = tools[: tools.index("</header>")]
    assert "data-foms-home-sync" in tools and "data-foms-fs-ctl" in tools and "data-foms-home-reload" in tools
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".foms-prod-home__tools { margin-left: auto; display: flex;" in css
    # 띠: 하루짜리 빈 줄만 '· 없음', 묶음 줄(지난 7일 · 그 뒤)은 날짜 글이 길어 안 붙인다
    strip = html[html.index('class="fph-strip"'):]
    strip = strip[: strip.index("</aside>")]
    recent = re.search(r'data-foms-home-daybtn="recent".*?</button>', strip, re.S).group(0)
    assert "없음" not in recent
    rail = html[html.index('class="foms-tablet-rail"'):]
    rail = rail[: rail.index("</nav>")]
    prod = re.search(r'<a\s+class="foms-tablet-rail__item[^"]*"\s+href="([^"]+)"\s+title="생산"[^>]*>', rail)
    assert prod and prod.group(1) == HOME and "is-active" in prod.group(0)
    assert 'data-foms-rail-match="/erp/production"' in prod.group(0)
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".foms-prod-home__navtab--out i { font-size: calc(13px * var(--foms-fs, 1)); }" in css


def test_공정_줄과_곧_올_것은_시공일_빠른_순() -> None:
    """M2(11-11): 지난 날 → 앞날 → 시공일 없음, 같은 날은 주문 번호 순. 보류도 같은 규칙."""
    def _row(rid: int, date: str | None, stage: str, *, hold: bool = False) -> dict:
        now = stage == "재단 중"
        return {"id": rid, "construction_date": date, "home_view": "prod", "home_stage": stage, "hold_active": hold,
                "home_steps": [{"key": "cut", "done": False, "now": now}, {"key": "edge", "done": False, "now": False}]}

    rows = [_row(5, "2026-11-05", "재단 중"), _row(1, "2026-11-17", "재단 중"), _row(9, None, "보류", hold=True),
            _row(4, "2026-10-31", "보류", hold=True), _row(2, "2026-11-05", "재단 중"), _row(3, "2026-10-27", "재단 중"),
            _row(8, None, "제작 대기"), _row(7, "2026-11-20", "제작 대기"), _row(6, "2026-11-01", "제작 대기")]
    cut = production_home_step_queues(rows)["queues"][0]
    assert [r["id"] for r in cut["rows"]] == [3, 4, 2, 5, 1, 9]
    assert [r["id"] for r in cut["incoming"]] == [6, 7, 8]
    edge = production_home_step_queues(rows)["queues"][1]
    assert [r["id"] for r in edge["incoming"]] == [3, 2, 5, 1]  # 재단 줄에서 보류만 뺀 같은 순서


def test_날짜_장_미리_보기는_6줄까지_뒤_장들을_잇고_모자라면_밀린_것_자기_자신은_안_단다(client) -> None:
    """M4(11-11 · §18 11-11): 뒤 장들(그 뒤 포함) 만들 것을 6줄까지 잇고, 모자라면 남은 자리만큼 지난 7일(밀린 것).
    지난 7일 장은 자기를 안 달고, 아래 두 장(지난 시공일 · 시공일 없음)에는 없다."""
    today = datetime.date(2026, 11, 11)

    def _row(rid: int, date: str | None) -> dict:
        return {"id": rid, "construction_date": date, "home_view": "prod", "home_stage": "제작 대기", "home_steps": []}

    def _pv(days: dict, key: str) -> list:
        return [(p["title"], p["hint"], p["show_day"], [r["id"] for r in p["rows"]])
                for p in next(b for b in days["panes"] if b["key"] == key)["previews"]]

    recent7 = [_row(100 + i, "2026-11-08") for i in range(7)]
    on13 = [_row(20 + i, "2026-11-13") for i in range(7)]
    rows = recent7 + on13 + [_row(10, "2026-11-12"), _row(11, "2026-11-12"), _row(30, "2026-11-21"),
                             _row(40, "2026-12-01"), _row(50, "2026-10-01"), _row(60, None)]
    days = production_home_days(rows, today)
    # (가) 뒤 장 하나로 6줄이 차면 그 장 제목, 밀린 것 없음
    assert _pv(days, "2026-11-12") == [("11/13 (금) 만들 것 7", "미리 보기", False, [20, 21, 22, 23, 24, 25])]
    # (나) 여러 장을 이으면 "다음에 만들 것 <뒤 장들 합계>", 줄마다 시공일, 6줄 이하
    assert _pv(days, "2026-11-11") == [("다음에 만들 것 11", "미리 보기", True, [10, 11, 20, 21, 22, 23])]
    # (다) 뒤가 1줄(그 뒤 묶음) 뿐이면 밀린 것 5줄을 더해 합 6. 그 뒤 장은 뒤가 없어 밀린 것 6줄
    assert _pv(days, "2026-11-21") == [("11/22 뒤 만들 것 1", "미리 보기", True, [40]),
                                       ("지난 7일 만들 것 7", "밀린 것", True, [100, 101, 102, 103, 104])]
    assert _pv(days, "later") == [("지난 7일 만들 것 7", "밀린 것", True, [100, 101, 102, 103, 104, 105])]
    # (라) 지난 7일 장에는 밀린 것 없음 (마) 아래 두 장에는 미리 보기 없음
    assert [p[1] for p in _pv(days, "recent")] == ["미리 보기"]
    assert _pv(days, "past") == [] and _pv(days, "none") == []
    alone = production_home_days(recent7[:1], today)
    assert _pv(alone, "recent") == [] and _pv(alone, "2026-11-11") == [("지난 7일 만들 것 1", "밀린 것", True, [100])]
    # 화면: 밀린 것 제목과 줄의 시공일 글
    _make_user(client, "tabs_prod_m4", "PRODUCTION")
    _add_order("PRODUCTION", "밀린주문", -3)
    pane = _pane(client.get(HOME + f"?day={get_today_kst().isoformat()}").get_data(as_text=True), get_today_kst().isoformat())
    old = production_home_read_model.production_home_day(get_today_kst() - datetime.timedelta(days=3), get_today_kst())["label"]
    assert "지난 7일 만들 것 1 <small>밀린 것</small>" in pane and "밀린주문" in pane and f"<small>{old}</small>" in pane
