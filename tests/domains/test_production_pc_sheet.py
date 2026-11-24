"""PC 공정 칸 → 도면 목록 창(사장님 2026-11-24 "PC 에서도 도면별로 체크, PC 는 감독 성격이 강해 세세한 정보를 볼 수 있어야 돼").

* 칸: 확정 도면 1장 이상인 줄의 PC 공정 칸만 누름 칸(role=button · data-foms-pc-sheet) — 모양 · 글 · 쿼리 수는 그대로, 도면 0장 줄 ·
  태블릿 출력은 하나도 안 바뀐다(음성 대조).
* 창 자료 ``GET /api/production/part-sheet``: 도면 판 글 그대로(안 봄 · 아직 · 작업 필요 · 재단 끝 · 기본 · 손 체크 "재단 완료 · 박반장" +
  "작업 시트") · 담당 · 완료한 사람과 시각 · 바뀐 기록 · 막힘(서버 글) · 안내 글(공정 칸 체크 거절 글 그대로) · [모두 체크] 조건 ·
  쓰기 가능(관리자 · 반장) · 그 줄 공정 칸 HTML(첫 화면과 같은 매크로 — 바이트까지 같음). 쿼리 3(+ 로그인 사용자).
* 쓰기는 있는 길만(part-marks · 공정 API) — 창 JS 가 부르는 순서(맡기 → 완료, 완료 취소, 공정 칸 켜기)대로 보내 칸이 "재단 3/5" → 채움.
창 틀 · 스크립트 · JS · CSS 계약은 ``test_production_pc_sheet_screen.py``.
"""
from __future__ import annotations

import datetime
import re
import time
from itertools import count
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.production.pc_view import EDIT_COOKIE
from models import Order, ProductionPartMark, ProductionRun, User
from tests.domains.test_production_home_query_count import _count_queries

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
API = "/api/production/part-sheet"
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
TABLET = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}
# 2026-11-24 00:16 UTC = KST 11/24 09:16 · 2026-11-23 23:10 UTC = KST 11/24 08:10
T1 = datetime.datetime(2026, 11, 24, 0, 16)
T0 = datetime.datetime(2026, 11, 23, 23, 10)
_seq = count(1)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _user(name: str, *, role: str = "STAFF", team: str = "PRODUCTION", part: str | None = None) -> User:
    user = User(username=f"pcsh_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return user


def _partner() -> User:
    from models import PartnerOrg

    org = PartnerOrg(name="가짜협력")
    db_session.add(org)
    db_session.commit()
    user = User(username=f"pcsh_{next(_seq)}", password=generate_password_hash("x"), role="PARTNER", team=None,
                name="협력", is_active=True, partner_org_id=org.id)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User, cookies: dict | None = PC) -> User:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    for key in ("foms_ptr", "foms_vw", "foms_scr"):
        client.delete_cookie(key, domain="localhost")
    for key, value in (cookies or {}).items():
        client.set_cookie(key, value, domain="localhost")
    return user


def _edit(client) -> None:
    client.set_cookie(EDIT_COOKIE, str(int(time.time()) - 60), domain="localhost", path="/erp/production")


def _order(name: str, n: int, *, done=(), hold: str | None = None, run: bool = True, off: int = 1) -> Order:
    day = (get_today_kst() + datetime.timedelta(days=off)).isoformat()
    steps = [{"key": k, "label": lb, "done": k in done, "at": "2026-11-24T01:20:00+00:00" if k in done else None,
              "by_name": "박반장" if k in done else None, "via": "sheet" if k in done else None}
             for k, lb in (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))]
    production: dict = {"steps": steps}
    if hold:
        production["hold"] = {"active": True, "reason": hold}
    files = [{"key": f"orders/pcs/{name}_{j}.png", "filename": f"{name}-도면{j + 1}.png"} for j in range(n)]
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
          "schedule": {"construction": {"date": day}}, "items": [{"product_name": "붙박이장", "spec_width": "2400"}],
          "production": production, "drawing_current_files": files}
    order = Order(received_date=day, customer_name=name, phone="010-0000-0000", address="가짜시", product="붙박이장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=day,
                  structured_data=sd)
    db_session.add(order)
    db_session.flush()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True,
                                     started_at=T0))
    db_session.commit()
    return order


def _mark(order: Order, j: int, part: str, state: str, who: User, *, handed: str | None = None) -> None:
    fin = state in ("DONE", "BASIC")
    db_session.add(ProductionPartMark(
        order_id=order.id, drawing_key=f"orders/pcs/{order.customer_name}_{j}.png", part=part, state=state,
        picked_by_user_id=None if state == "BASIC" else who.id, picked_by_name=None if state == "BASIC" else who.name,
        picked_at=T0, done_by_user_id=who.id if fin else None, done_by_name=who.name if fin else None,
        done_at=T1 if fin else None, handed_from_name=handed, handed_at=T1 if handed else None,
        updated_by_user_id=who.id, updated_at=T1))
    db_session.commit()


def _seed_five() -> tuple[Order, dict[str, int]]:
    """도면 5장 재단: 완료 2(김재단) · 작업 필요 1(박재단, 박엣지에서 바뀜) · 안 봄 2. 사람은 id 로 돌려준다(요청 뒤 세션이 닫힌다)."""
    people = {k: _user(v) for k, v in (("kim", "김재단"), ("park", "박재단"))}
    order = _order("구슬기", 5)
    for j in (0, 1):
        _mark(order, j, "cut", "DONE", people["kim"])
    _mark(order, 2, "cut", "NEED", people["park"], handed="박엣지")
    ids = {k: u.id for k, u in people.items()}
    order_id = order.id
    return db_session.get(Order, order_id), ids


def _get(client, order, part: str):
    oid = order if isinstance(order, int) else order.id
    return client.get(f"{API}?order_id={oid}&part={part}")


def _row(html: str, order_id: int) -> str:
    return html.split(f'data-foms-home-dayrow="{order_id}"', 1)[1].split('<div class="fpc-r', 1)[0]


def _day(order: Order) -> str:
    return f"{HOME}?view=day&day={order.erp_construction_date}"


# --------------------------------------------------------------------------- #
# 칸 — 누름 칸은 도면 있는 줄만, 모양 · 글은 그대로
# --------------------------------------------------------------------------- #
def test_칸은_도면이_있는_줄만_누름_칸이고_태블릿은_그대로(client, cohort) -> None:
    order, _ = _seed_five()
    bare = _order("빈도면", 0)
    _login(client, _user("관리", role="ADMIN", team="CS"))
    html = client.get(_day(order)).get_data(as_text=True)
    row = _row(html, order.id)
    assert row.count('role="button" aria-haspopup="dialog" data-foms-pc-sheet=') == 4
    for key in ("cut", "edge", "assemble", "inspect"):
        assert f'data-foms-pc-sheet="{key}"' in row
    # 지금 글 그대로 — 마우스 글 · 칸 이름 · 칸 아래 이름(누름 칸 표지는 aria-label 뒤에만 붙는다)
    assert re.search(r'data-tip="재단 2/5 · 3장 미완료 · 담당 박재단 · 박엣지에서 바뀜 [0-9:]+" tabindex="0" aria-label="[^"]+" role="button"', row)
    assert ">재단 2/5</span>" in row
    assert "data-foms-pc-sheet" not in _row(html, bare.id)  # 음성 대조 — 도면 0장 줄은 지금 그대로(창 없음)
    _login(client, _user("태블릿"), TABLET)
    tablet = client.get(_day(order)).get_data(as_text=True)
    assert "data-foms-pc-sheet" not in tablet and "foms-production-pc-sheet" not in tablet


# --------------------------------------------------------------------------- #
# 창 자료
# --------------------------------------------------------------------------- #
def test_창_자료는_도면_판_글_그대로와_시각(client, cohort) -> None:
    order, people = _seed_five()
    _login(client, _user("관리", role="ADMIN", team="CS"))
    body = _get(client, order, "cut").get_json()
    assert body["success"] is True and body["error"] is None
    d = body["data"]
    assert (d["label"], d["total"], d["done_n"], d["customer_name"], d["order_id"]) == ("재단", 5, 2, "구슬기", order.id)
    assert d["can_write"] is True and d["all"] is False and d["hand_off"] is False
    assert d["notice"] == "도면 3장이 아직 미완료예요. 남은 도면을 완료하면 자동으로 체크돼요."  # 거절 글 그대로(승인 때 고친 것 2)
    rows = d["rows"]
    assert [r["label"] for r in rows] == [f"도면 {i}/5" for i in range(1, 6)]
    assert [r["word"] for r in rows] == ["재단 끝", "재단 끝", "작업 필요", "안 봄", "안 봄"]
    assert [r["act"] for r in rows] == ["uncheck", "uncheck", "check", "check", "check"]
    assert rows[0]["holder"] == "담당 김재단 · 11/24 08:10" and rows[0]["done"] == "완료 김재단 · 11/24 09:16"
    assert rows[2]["holder"] == "담당 박재단 · 11/24 08:10" and rows[2]["done"] is None
    assert rows[2]["handed"] == "박엣지에서 바뀜 11/24 09:16"  # 작업 시트 바뀐 기록 꼴(시각까지)
    assert (rows[2]["seen"], rows[2]["seen_by"]) == ("need", people["park"])
    assert rows[3]["holder"] == "담당 미정" and rows[3]["block"] is None and rows[3]["item"] == "붙박이장 · W2400"
    assert rows[0]["thumb"].startswith("/erp/production/parts/thumb/") and rows[0]["image"] is True
    assert d["sheets"] == 5 and d["parts"]["cut"]["uses_cards"] is True and d["keys"][0].endswith("_0.png")
    # 그 줄 공정 칸 = 첫 화면이 그린 칸과 바이트까지 같다(체크 뒤 그대로 바꿔 끼운다)
    page = _row(client.get(_day(order)).get_data(as_text=True), order.id)
    assert d["cells_html"] in page and d["status_html"] in page and d["late"] in (None, "late", "tight")
    # 다른 파트 = "아직", 담당 미정
    edge = _get(client, order, "edge").get_json()["data"]
    assert {r["word"] for r in edge["rows"]} == {"아직"} and edge["all"] is True and edge["notice"] is None


def test_손_체크_파트는_도면_판_손_체크_글과_통째_해제(client, cohort) -> None:
    order = _order("황보민재", 3, done=("cut",))
    _login(client, _user("반장"))
    d = _get(client, order, "cut").get_json()["data"]
    assert d["hand_off"] is True and d["all"] is False and d["hand"] == "재단 완료 · 박반장"
    assert {(r["word"], r["note"], r["act"]) for r in d["rows"]} == {("재단 완료 · 박반장", "작업 시트", None)}
    assert d["rows"][0]["done"] == "완료 박반장 · 11/24 10:20" and d["can_write"] is True


def test_막힘은_서버_글_그대로(client, cohort) -> None:
    kim = _user("김재단")
    hold_id = _order("오세린", 2, hold="자재 기다림").id
    order = _order("윤서아", 2)
    for j in (0, 1):
        _mark(order, j, "cut", "DONE", kim)
    oid = order.id
    _login(client, _user("관리", role="ADMIN", team="CS"))
    held = _get(client, hold_id, "cut").get_json()["data"]
    assert {(r["block"] or {}).get("text") for r in held["rows"]} == {"보류 · 자재 기다림"}
    assert held["rows"][0]["block"]["why"] == "보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."
    insp = _get(client, oid, "inspect").get_json()["data"]
    assert [r["block"]["text"] for r in insp["rows"]] == ["엣지 · 조립 미완료"] * 2
    assert insp["rows"][0]["block"]["why"].startswith("아직 검수할 수 없어요. 엣지(담당 미정) · 조립(담당 미정)")


@pytest.mark.parametrize("who,status,write", [("admin", 200, True), ("boss", 200, True), ("part", 200, False),
                                              ("cs", 200, False), ("noteam", 403, False), ("partner", 403, False)])
def test_권한_보기는_생산_화면_보는_직원_쓰기는_관리자_반장(client, cohort, who, status, write) -> None:
    order, _ = _seed_five()
    user = {"admin": lambda: _user("관리", role="ADMIN", team="CS"), "boss": lambda: _user("반장"),
            "part": lambda: _user("재단", part="cut"), "cs": lambda: _user("상담", team="CS"),
            "noteam": lambda: _user("팀없음", team=None), "partner": lambda: _partner()}[who]()
    _login(client, user)
    resp = _get(client, order, "cut")
    assert resp.status_code == status, resp.get_json()
    if status == 200:
        assert resp.get_json()["data"]["can_write"] is write


def test_질의가_틀리면_400_없는_주문_404_쿼리_셋(client, cohort) -> None:
    order, _ = _seed_five()
    _login(client, _user("관리", role="ADMIN", team="CS"))
    for qs in ("order_id=abc&part=cut", f"order_id={order.id}&part=paint", f"order_id={order.id}", "part=cut"):
        assert client.get(f"{API}?{qs}").status_code == 400, qs
    assert client.get(f"{API}?order_id=999999&part=cut").status_code == 404
    assert _get(client, order, "cut").status_code == 200  # warmup
    resp, n = _count_queries(lambda: _get(client, order, "cut"))
    assert resp.status_code == 200 and n == 4, n  # 로그인 사용자 + 주문 · 표시 줄 · 지금 회차(실측 4)


# --------------------------------------------------------------------------- #
# 쓰기 = 있는 길만 — 창 JS 가 보내는 순서대로
# --------------------------------------------------------------------------- #
def _post(client, url: str, body: dict):
    return client.post(url, json=body)


def test_체크_맡기_완료_뒤_칸이_3_5_그리고_해제(client, cohort) -> None:
    order, people = _seed_five()
    oid, name = order.id, order.customer_name
    admin_id = _login(client, _user("관리", role="ADMIN", team="CS")).id
    key, held = f"orders/pcs/{name}_3.png", f"orders/pcs/{name}_2.png"

    def mark(drawing_key: str, action: str, seen: str, **extra):
        resp = _post(client, "/api/production/part-marks", {"order_id": oid, "drawing_key": drawing_key, "part": "cut",
                                                            "action": action, "seen": seen, **extra})
        assert resp.status_code == 200, resp.get_json()

    mark(key, "take", "none")
    mark(key, "done", "need", seen_by=admin_id)
    d = _get(client, oid, "cut").get_json()["data"]
    assert d["rows"][3]["word"] == "재단 끝" and d["rows"][3]["done"].startswith("완료 관리 · ")
    assert ">재단 3/5</span>" in d["cells_html"]
    mark(held, "done", "need", seen_by=people["park"])  # 남의 장(박재단) 대신 완료 — 서버가 덮어쓰기로 적는다(지금 규칙)
    mark(key, "undo", "done")
    d = _get(client, oid, "cut").get_json()["data"]
    assert d["rows"][3]["word"] == "작업 필요" and d["rows"][2]["word"] == "재단 끝" and ">재단 3/5</span>" in d["cells_html"]


def test_모두_체크는_공정_칸_길_그대로이고_칸이_채워진다(client, cohort) -> None:
    oid = _order("제갈하늘", 3, done=("cut",)).id
    _login(client, _user("반장"))
    before = _get(client, oid, "edge").get_json()["data"]
    assert before["all"] is True and 'class="fpc-s is-done"' in before["cells_html"]  # 재단은 이미 칸 체크(손)
    resp = _post(client, f"/api/orders/{oid}/production/steps", {"key": "edge", "done": True})
    assert resp.status_code == 200, resp.get_json()
    after = _get(client, oid, "edge").get_json()["data"]
    assert after["hand_off"] is True and after["all"] is False and after["hand"].startswith("엣지 완료 · ")
    assert after["cells_html"].count('class="fpc-s is-done"') == 2 and "조립 중" in after["status_html"]
