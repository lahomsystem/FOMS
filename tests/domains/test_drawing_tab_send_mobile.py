"""도면 탭 고객 보내기 — 모바일 도면 방·목록 카드·고객 링크 화면(S3, 설계서 2026-09-29 §3.1·§3.3·§4.5·§7.1).

서버 판정(`customer_send.*`)은 S1 이 채운다. 이 파일은 S1a 기본값(빈 값)과 **직접 채운 ctx** 로
모바일 템플릿이 그 값을 어떻게 그리는지만 고정한다 — 판정을 템플릿에 따로 쓰지 않았는지가 핵심이다.

직접 채우는 방법: `foms.web.drawing.workbench.render_template` 를 감싸 ctx 의 `customer_send` 를
덮는다(S1 이 빌더 이름을 바꿔도 이 자리는 그대로다). 같은 응답에 숨은 PC 마크업이 함께 오므로
모바일 표면(`.erp-mobile-shell.foms-drawing-handoff`)을 파서로 잘라 본다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.web.drawing.workbench as workbench_mod
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.drawing_customer_send import BAR_KEYS, empty_customer_send_view
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_TPL = ROOT / "templates/drawing/partials/workbench_mobile_handoff.html"
QUEUE_CARD_TPL = ROOT / "templates/drawing/partials/workbench_mobile_queue_card.html"
MOBILE_CSS = ROOT / "static/css/components/foms-drawing-mobile.css"
CANCEL_WARN_JS = ROOT / "static/js/foms/drawing-cancel-warn-mobile.js"

# 버튼 키마다 모바일이 다는 여는 속성(§3.1-3 + Q5). 시트·모달 본문은 S2 소유 — 여기서는 여는 훅만 본다.
OPENERS = {
    "send": {"data-bs-toggle": "modal", "data-bs-target": "#dwCustomerSendModal", "data-customer-send-mode": "first"},
    "resend": {"data-bs-toggle": "modal", "data-bs-target": "#dwCustomerSendModal", "data-customer-send-mode": "again"},
    "rev_customer": {"data-bs-target": "#dwRevisionModal", "data-revision-source": "customer",
                     "data-drawing-handoff-action": "revision"},
    "rev_post": {"data-bs-target": "#dwRevisionModal", "data-revision-source": "customer",
                 "data-drawing-handoff-action": "revision"},
    "rev_sales": {"data-bs-target": "#dwRevisionModal", "data-revision-source": "sales",
                  "data-drawing-handoff-action": "revision"},
    "ok": {"data-bs-target": "#dwCustomerOkModal", "data-customer-ok-mode": "customer"},
    "ok_no_customer": {"data-bs-target": "#dwCustomerOkModal", "data-customer-ok-mode": "no_customer"},
    "cancel_revision": {"data-drawing-handoff-action": "cancel-revision"},
    "edit_revision": {"data-bs-toggle": "modal", "data-bs-target": "#dwRevisionEditModal"},
}

# §3.0 상태별 영업 쪽 버튼(서버가 만든 목록 모양 그대로 흉내 낸다).
STATE_BARS = {
    "transferred_unsent": [("rev_sales", "내 의견", "secondary"), ("send", "고객에게 보내기", "primary"),
                           ("ok_no_customer", "확정", "line")],
    "transferred_sent": [("resend", "다시 보내기", "secondary"), ("rev_customer", "고객이 고쳐 달래요", "warn"),
                         ("ok", "고객 OK · 확정", "success")],
    "returned": [("edit_revision", "요청 고치기", "secondary"), ("cancel_revision", "수정요청 취소", "secondary")],
    "confirmed_approve": [("rev_post", "고객이 또 바꿔 달래요", "warn"), ("send", "고객에게 보내기", "secondary"),
                          ("approve_confirm", "고객 컨펌하고 생산으로", "success")],
    "confirmed_other": [("rev_post", "고객이 또 바꿔 달래요", "warn"), ("send", "고객에게 보내기", "secondary"),
                        ("production", "생산 현황 보기", "primary")],
}


def _bar(items, slots=None):
    slots = slots or {}
    return [{"key": k, "label": label, "tone": tone, "slot": slots.get(k, "main")} for k, label, tone in items]


# ── 픽스처 조각 ────────────────────────────────────────────────────────────────


def _user(username: str, *, role: str, team: str) -> dict:
    # 영업 쪽 판정(_can_modify_sales_domain)은 주문 담당 이름으로 맞춘다 — SALES 팀은 주문 담당 "영업담당".
    name = "영업담당" if team == "SALES" else username
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=name, is_active=True)
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _order(drafter_id: int, *, status: str = "TRANSFERRED", files: int = 2, revision: bool = False) -> int:
    order = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="S3 고객",
                  phone="010-0000-0033", address="서울", product="붙박이장", status="DRAWING",
                  manager_name="영업담당", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.flush()
    keys = [f"orders/{order.id}/drawing/plan-{i}.png" for i in range(1, files + 1)]
    history = [
        {"action": "TRANSFER", "by_user_id": drafter_id, "by_user_name": "도면담당", "at": "2026-09-20 01:00:00",
         "note": "1차 전달", "files": [{"key": k, "filename": k.rsplit("/", 1)[-1]} for k in keys]},
    ]
    if revision:
        history.append({
            "action": "REQUEST_REVISION", "by_user_id": 1, "by_user_name": "영업담당", "at": "2026-09-21 01:00:00",
            "note": "오른쪽 문짝 폭 줄여 주세요", "target_drawing_number": files, "files": [],
        })
    order.structured_data = {
        "parties": {"customer": {"name": "S3 고객"}, "manager": {"name": "영업담당"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": status,
        "assignments": {"drawing_assignee_user_ids": [drafter_id]},
        "drawing_current_files": [
            {"key": k, "filename": k.rsplit("/", 1)[-1], "view_url": f"/api/files/view/{k}"} for k in keys
        ],
        "drawing_transfer_history": history,
    }
    db_session.commit()
    return order.id


def _inject(monkeypatch, *, cs: dict | None = None, thread=None) -> None:
    """상세 ctx 를 직접 채운다 — customer_send 를 덮고, 필요하면 스레드 항목을 고친다."""
    # 한 테스트에서 여러 번 불러도 겹겹이 감싸지 않는다 — 늘 원래 함수를 부른다.
    real = getattr(workbench_mod.render_template, "_s3_real", workbench_mod.render_template)

    def fake(template_name, **ctx):
        if cs is not None and "customer_send" in ctx:
            view = dict(ctx["customer_send"])
            view.update(cs)
            ctx["customer_send"] = view
        if thread is not None and "mobile_handoff_thread" in ctx:
            thread(ctx["mobile_handoff_thread"])
        return real(template_name, **ctx)

    fake._s3_real = real
    monkeypatch.setattr(workbench_mod, "render_template", fake)


def _page(client, monkeypatch, who: dict, oid: int, query: str = "") -> BeautifulSoup:
    _login(client, who)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    res = client.get(f"/erp/drawing-workbench/{oid}{query}")
    assert res.status_code == 200, res.status_code
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def _handoff(soup: BeautifulSoup):
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None, "v2 모바일 표면이 렌더되지 않았다"
    return handoff


def _mobile_bar_keys(handoff) -> list[str]:
    return [el["data-cs-bar-key"] for el in handoff.select(".foms-drawing-action-bar [data-cs-bar-key]")]


def _direct_bar_buttons(handoff) -> list:
    bar = handoff.select_one(".foms-drawing-action-bar")
    return [el for el in bar.find_all(recursive=False) if el.name in ("button", "a")]


def _urgent_buttons(handoff) -> list:
    return handoff.select(".foms-drawing-action-bar [data-foms-urgent-call]")


# ── 하단 바 = 서버 목록 순회 ──────────────────────────────────────────────────


def test_default_customer_send_draws_no_bar_items_and_keeps_urgent(client, monkeypatch):
    """S1a 기본값(빈 bar): 새 버튼 0개 · 옛 수정요청/수령 확정/수정요청 취소 블록도 없다 · 긴급 호출은 그대로."""
    drafter = _user("s3_def_drafter", role="STAFF", team="DRAWING")
    sales = _user("s3_def_sales", role="MANAGER", team="SALES")
    oid = _order(drafter["id"])
    handoff = _handoff(_page(client, monkeypatch, sales, oid))
    bar = handoff.select_one(".foms-drawing-action-bar")
    assert _mobile_bar_keys(handoff) == []
    for action in ("revision", "confirm", "cancel-revision"):
        assert bar.select(f'[data-drawing-handoff-action="{action}"]') == [], action
    assert len(_urgent_buttons(handoff)) == 1
    assert bar.select_one(".foms-drawing-action-bar__more") is None


@pytest.mark.parametrize("state", sorted(STATE_BARS))
def test_bar_iterates_server_list_in_order_with_openers(client, monkeypatch, state):
    """모바일 바는 `customer_send.bar` 를 그 순서 그대로 그리고, 키마다 약속한 여는 속성을 단다."""
    drafter = _user(f"s3_it_{state}_d", role="STAFF", team="DRAWING")
    sales = _user(f"s3_it_{state}_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], files=1)
    bar = _bar(STATE_BARS[state])
    _inject(monkeypatch, cs={"bar": bar})
    handoff = _handoff(_page(client, monkeypatch, sales, oid))

    assert _mobile_bar_keys(handoff) == [item["key"] for item in bar]
    selected_key = handoff.get("data-selected-drawing-key")
    for item in bar:
        el = handoff.select_one(f'.foms-drawing-action-bar [data-cs-bar-key="{item["key"]}"]')
        assert item["label"] in el.get_text(" ", strip=True)
        for attr, value in OPENERS.get(item["key"], {}).items():
            assert el.get(attr) == value, (item["key"], attr, el.get(attr))
        if item["key"].startswith("rev_"):
            assert el.get("data-drawing-key") == selected_key
        if item["key"] == "approve_confirm":
            assert el.has_attr("data-customer-approve") and el.get("data-order-id") == str(oid)
        if item["key"] == "production":
            assert el.name == "a" and el["href"] == f"/erp/dashboard?focus_order={oid}"
    # 서버가 안 준 키는 그리지 않는다(템플릿 자체 판정 없음 — 음성 대조).
    for key in set(BAR_KEYS) - {item["key"] for item in bar}:
        assert handoff.select(f'[data-cs-bar-key="{key}"]') == [], key


def test_urgent_after_sent_leaves_bar_and_returns_before_sending(client, monkeypatch):
    """목업: 보내기 전 바는 [내 의견][보내기][확정][긴급] 4개, 보낸 뒤는 3개(긴급 빠짐)."""
    drafter = _user("s3_urg_d", role="STAFF", team="DRAWING")
    sales = _user("s3_urg_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"])

    _inject(monkeypatch, cs={"bar": _bar(STATE_BARS["transferred_unsent"])})
    before = _handoff(_page(client, monkeypatch, sales, oid))
    assert len(_urgent_buttons(before)) == 1
    assert len(_direct_bar_buttons(before)) == 4

    _inject(monkeypatch, cs={"bar": _bar(STATE_BARS["transferred_sent"])})
    after = _handoff(_page(client, monkeypatch, sales, oid))
    assert _urgent_buttons(after) == []
    assert len(_direct_bar_buttons(after)) == 3

    _inject(monkeypatch, cs={"bar": _bar(STATE_BARS["returned"])})
    returned = _handoff(_page(client, monkeypatch, sales, oid))
    assert [el.get("data-cs-bar-key", "urgent") for el in _direct_bar_buttons(returned)] == [
        "edit_revision", "cancel_revision", "urgent"]


def test_urgent_call_from_server_list_is_the_only_urgent_button(client, monkeypatch):
    """도면팀 bar 의 urgent_call(Q5-①)은 모바일에서 기존 긴급 호출 시트를 연다 — 두 번 그리지 않는다."""
    drafter = _user("s3_uc_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"])
    _inject(monkeypatch, cs={"bar": _bar([("urgent_call", "긴급 호출", "urgent")])})
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    urgent = _urgent_buttons(handoff)
    assert len(urgent) == 1
    assert urgent[0].get("data-cs-bar-key") == "urgent_call"
    assert urgent[0].get("data-order-id") == str(oid)


def test_admin_overflow_goes_to_more_dropup(client, monkeypatch):
    """관리자 겸 도면 담당: 도면 쪽 버튼 + 영업 쪽 main 이 바에 3개, 나머지(slot=more)와 긴급은 [더 보기]."""
    admin = _user("s3_more_admin", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"])
    bar = _bar(STATE_BARS["transferred_unsent"], slots={"rev_sales": "more", "ok_no_customer": "more"})
    _inject(monkeypatch, cs={"bar": bar})
    handoff = _handoff(_page(client, monkeypatch, admin, oid))
    action_bar = handoff.select_one(".foms-drawing-action-bar")

    direct = _direct_bar_buttons(handoff)
    assert len(direct) == 3, [el.get_text(" ", strip=True) for el in direct]
    assert direct[-1].get("data-cs-bar-key") == "send"
    more = action_bar.select_one(".foms-drawing-action-bar__more.dropup")
    assert more is not None
    toggle = more.select_one('[data-bs-toggle="dropdown"]')
    assert toggle is not None and "더 보기" in toggle.get_text()
    menu_keys = [el.get("data-cs-bar-key") for el in more.select(".dropdown-menu [data-cs-bar-key]")]
    assert menu_keys == ["rev_sales", "ok_no_customer"]
    assert len(more.select(".dropdown-menu [data-foms-urgent-call]")) == 1
    # 여는 속성은 [더 보기] 안에서도 같다.
    item = more.select_one('[data-cs-bar-key="rev_sales"]')
    assert item.get("data-revision-source") == "sales" and item.get("data-bs-target") == "#dwRevisionModal"


def test_mobile_bar_keys_equal_server_list_for_every_state(client, monkeypatch):
    """파리티(모바일 쪽): 같은 주문·같은 사용자로 모바일 바 키 목록 == 서버 목록(PC 도 같은 목록을 순회)."""
    drafter = _user("s3_par_d", role="STAFF", team="DRAWING")
    sales = _user("s3_par_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"])
    for state, items in STATE_BARS.items():
        bar = _bar(items)
        _inject(monkeypatch, cs={"bar": bar})
        handoff = _handoff(_page(client, monkeypatch, sales, oid))
        assert _mobile_bar_keys(handoff) == [i["key"] for i in bar], state


@pytest.mark.xfail(strict=True, reason="PC 결정 바 순회는 S2 갈래 — 합친 뒤 PC 버튼에 data-cs-bar-key 가 붙으면 이 표시를 지운다")
def test_pc_and_mobile_bar_keys_are_the_same_list(client, monkeypatch):
    """파리티(두 표면): PC 결정 바와 모바일 바가 같은 키 목록을 같은 순서로 그린다."""
    drafter = _user("s3_par2_d", role="STAFF", team="DRAWING")
    sales = _user("s3_par2_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"])
    bar = _bar(STATE_BARS["transferred_sent"])
    _inject(monkeypatch, cs={"bar": bar})
    soup = _page(client, monkeypatch, sales, oid)
    pc = soup.select_one(".dw-legacy-detail")
    pc_keys = [el["data-cs-bar-key"] for el in pc.select("[data-cs-bar-key]")]
    assert pc_keys == _mobile_bar_keys(_handoff(soup)) == [i["key"] for i in bar]


# ── 주문 요약 칸: 회차 기록 줄 · 상태 한 줄 · 리본 부제 ─────────────────────────

STEPS = [
    {"label": "1차 도착", "sub": "도면 2장", "when": "09-27 13:55", "state": "done"},
    {"label": "고객에게 보냄", "sub": "알림톡", "when": "14:03", "state": "done"},
    {"label": "링크 열림", "sub": "2번 · 마지막 16:40", "when": "16:40", "state": "now"},
    {"label": "고객 답", "sub": "", "when": "", "state": "wait"},
]


def _top_block_count(handoff) -> int:
    main = handoff.select_one("main.foms-drawing-handoff__body")
    return len(main.find_all("section", recursive=False)) + len(main.find_all("details", recursive=False))


def test_sales_sees_round_steps_inside_order_summary_without_new_block(client, monkeypatch):
    drafter = _user("s3_steps_d", role="STAFF", team="DRAWING")
    sales = _user("s3_steps_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], files=1)
    baseline = _top_block_count(_handoff(_page(client, monkeypatch, sales, oid)))

    _inject(monkeypatch, cs={"steps": STEPS, "prev_summary": "1차 · 보냄 · 고객 요청 1건",
                             "status_line": "영업 → 고객 · 1차 보냄 14:03 알림톡 · 링크 열림 2번"})
    handoff = _handoff(_page(client, monkeypatch, sales, oid))
    order_box = handoff.select_one("section.foms-drawing-handoff__order")
    steps = order_box.select("ol.foms-drawing-send-steps > li")
    assert [li.get("data-step-state") for li in steps] == ["done", "done", "now", "wait"]
    assert "is-now" in steps[2]["class"]
    assert "링크 열림" in steps[2].get_text(" ", strip=True) and "16:40" in steps[2].get_text(" ", strip=True)
    prev = order_box.select_one("p.foms-drawing-send-steps__prev")
    assert prev is not None and "고객 요청 1건" in prev.get_text()
    # 영업 쪽에는 기록 줄이 상태 한 줄을 대신한다.
    assert order_box.select_one(".foms-drawing-handoff__send-status") is None
    assert _top_block_count(handoff) == baseline == 5


def test_drawing_team_sees_read_only_status_line_not_steps(client, monkeypatch):
    drafter = _user("s3_line_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    line = "영업 → 고객 · 1차 보냄 11:52 알림톡 · 링크 열림 1번"
    _inject(monkeypatch, cs={"steps": STEPS, "status_line": line, "turn_hint": "영업 전용 부제"})
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    order_box = handoff.select_one("section.foms-drawing-handoff__order")
    status = order_box.select_one("p.foms-drawing-handoff__send-status")
    assert status is not None and status.get_text(" ", strip=True) == line
    assert status.select("button, a, input") == []  # 읽기 전용
    assert order_box.select("ol.foms-drawing-send-steps") == []
    assert "영업 전용 부제" not in handoff.select_one("section.foms-drawing-turn").get_text()


def test_empty_status_draws_nothing_in_order_summary(client, monkeypatch):
    """대조: 값이 비면(S1a 기본값) 주문 요약 칸은 지금과 같다."""
    drafter = _user("s3_empty_d", role="STAFF", team="DRAWING")
    sales = _user("s3_empty_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], files=1)
    for who in (drafter, sales):
        order_box = _handoff(_page(client, monkeypatch, who, oid)).select_one("section.foms-drawing-handoff__order")
        assert order_box.select(".foms-drawing-send-steps, .foms-drawing-handoff__send-status, "
                                ".foms-drawing-send-steps__prev") == []


def test_sales_turn_hint_replaces_ribbon_sub(client, monkeypatch):
    drafter = _user("s3_hint_d", role="STAFF", team="DRAWING")
    sales = _user("s3_hint_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], files=1)
    plain_sub = _handoff(_page(client, monkeypatch, sales, oid)).select_one("section.foms-drawing-turn p").get_text()
    _inject(monkeypatch, cs={"turn_hint": "1차 초안 도착 · 고객에게 보여 줄 차례"})
    turn = _handoff(_page(client, monkeypatch, sales, oid)).select_one("section.foms-drawing-turn")
    assert turn.select_one("p").get_text() == "1차 초안 도착 · 고객에게 보여 줄 차례"
    assert plain_sub != "1차 초안 도착 · 고객에게 보여 줄 차례"


# ── 스레드 '고객 요청' ─────────────────────────────────────────────────────────


def test_thread_shows_customer_request_tag_only_for_customer_source(client, monkeypatch):
    drafter = _user("s3_thr_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], status="RETURNED", files=1, revision=True)

    def tag_revision(events):
        for event in events:
            if event.get("action") == "REQUEST_REVISION":
                event["source_tag"] = "고객 요청 · 1차 · 카톡 답장"

    _inject(monkeypatch, thread=tag_revision)
    handoff = _handoff(_page(client, monkeypatch, drafter, oid, "?tab=requests"))
    tags = handoff.select(".foms-drawing-thread__tag")
    customer = [t for t in tags if "foms-drawing-thread__tag--customer" in t["class"]]
    assert len(customer) == 1
    assert customer[0].get_text(" ", strip=True).startswith("고객 요청 · 1차 · 카톡 답장")
    # 대조(모집단 안): 같은 스레드의 전달 말풍선은 태그가 그대로다.
    others = [t for t in tags if t not in customer]
    assert others and all("고객 요청" not in t.get_text() for t in others)


def test_thread_without_source_tag_keeps_old_revision_label(client, monkeypatch):
    drafter = _user("s3_thr2_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], status="RETURNED", files=1, revision=True)
    handoff = _handoff(_page(client, monkeypatch, drafter, oid, "?tab=requests"))
    assert handoff.select(".foms-drawing-thread__tag--customer") == []
    assert any("수정" in t.get_text() for t in handoff.select(".foms-drawing-thread__tag"))


# ── 모바일 전달 취소 경고(Q5-④) ───────────────────────────────────────────────

WARN = "영업이 이 1차 도면을 고객에게 이미 보냈어요(11:52 알림톡 · 링크 열림 1번). 영업에게 먼저 알리려면 긴급 호출을 쓰세요."


def test_mobile_cancel_transfer_opens_warning_sheet_when_sent(client, monkeypatch):
    drafter = _user("s3_cw_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    _inject(monkeypatch, cs={"cancel_warning_text_mobile": WARN, "cancel_warning_text_pc": "PC 문구"})
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    cancel = handoff.select_one(".foms-drawing-action-bar [data-dw-cancel-warn]")
    assert cancel is not None
    assert cancel.get("data-bs-toggle") == "modal" and cancel.get("data-bs-target") == "#dwCancelWarnMobileModal"
    # 대신 누르기(PC 확인창)와 겹치지 않는다 — 확인창 두 번 금지.
    assert not cancel.has_attr("data-drawing-handoff-action")

    sheet = handoff.select_one("#dwCancelWarnMobileModal")
    assert sheet is not None and sheet.get("data-order-id") == str(oid)
    assert WARN in sheet.get_text(" ", strip=True)
    urgent = sheet.select_one("[data-dw-cancel-warn-urgent]")
    assert urgent is not None and "영업에게 먼저 알리기" in urgent.get_text()
    assert sheet.select_one("[data-dw-cancel-warn-confirm]") is not None
    assert sheet.select_one('[data-bs-dismiss="modal"]') is not None
    scripts = [s for s in handoff.select("script[src]") if "drawing-cancel-warn-mobile.js" in s["src"]]
    assert len(scripts) == 1 and scripts[0].has_attr("defer")
    assert "?v=20260929o" in scripts[0]["src"]


def test_mobile_cancel_transfer_without_warning_keeps_proxy(client, monkeypatch):
    """대조: 이번 회차를 보내지 않았으면 지금처럼 PC 버튼 대신 누르기 · 경고 시트 없음."""
    drafter = _user("s3_cw2_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    cancel = handoff.select_one('.foms-drawing-action-bar [data-drawing-handoff-action="cancel"]')
    assert cancel is not None and not cancel.has_attr("data-bs-toggle")
    assert handoff.select_one("#dwCancelWarnMobileModal") is None
    assert handoff.select("[data-dw-cancel-warn]") == []


def test_cancel_warn_js_contract():
    source = CANCEL_WARN_JS.read_text(encoding="utf-8")
    assert "__FOMS_DW_CANCEL_WARN_BOUND" in source
    assert "jQuery" not in source and "$(" not in source
    assert "/cancel-transfer" in source and "/erp/drawing-workbench/" in source
    assert "data.success" in source
    assert "data-foms-urgent-call" in source and "hidden.bs.modal" in source
    for fetch_at in [m.start() for m in re.finditer(r"\bfetch\(", source)]:
        try_at = source.rfind("try {", 0, fetch_at)
        assert try_at != -1 and "catch" not in source[try_at:fetch_at], "fetch 가 try 블록 밖이다"
    assert len(source.splitlines()) <= 300
    node = shutil.which("node")
    if node:
        res = subprocess.run([node, "--check", str(CANCEL_WARN_JS)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


# ── CSS · 규약 ────────────────────────────────────────────────────────────────


def test_new_mobile_classes_have_rules_and_no_inline_style():
    css = MOBILE_CSS.read_text(encoding="utf-8")
    for cls in (".foms-drawing-send-steps", ".foms-drawing-send-steps__prev", ".foms-drawing-handoff__send-status",
                ".foms-drawing-thread__tag--customer", ".foms-drawing-action-bar__more",
                ".foms-drawing-action-bar__btn--success", ".foms-drawing-action-bar__btn--warn",
                ".foms-drawing-action-bar__btn--line", ".foms-drawing-action-bar__btn--wide",
                ".foms-drawing-cancel-warn__text", ".foms-drawing-cancel-warn__actions"):
        assert re.search(r"body\.erp-mobile-v2-layout [^{]*" + re.escape(cls) + r"\b", css), cls
    for tpl in (HANDOFF_TPL, QUEUE_CARD_TPL):
        assert 'style="' not in tpl.read_text(encoding="utf-8"), tpl


def test_empty_view_keys_cover_everything_the_mobile_template_reads():
    """모바일 템플릿이 읽는 customer_send 키는 모두 S1a 기본값에 있다(없는 키 = 합친 뒤 조용한 빈 칸)."""
    text = HANDOFF_TPL.read_text(encoding="utf-8")
    used = set(re.findall(r"\bcs\.([a-z_]+)", text))
    assert used, "모바일 템플릿이 customer_send 를 읽지 않는다"
    assert used <= set(empty_customer_send_view()), used - set(empty_customer_send_view())
