"""도면 탭 고객 보내기 — 모바일 도면 방·목록 카드·고객 링크 화면(S3, 설계서 2026-09-29 §3.1·§3.3·§4.5·§7.1).

서버 판정(`customer_send.*`)은 S1 이 채운다. 이 파일은 S1a 기본값(빈 값)과 **직접 채운 ctx** 로
모바일 템플릿이 그 값을 어떻게 그리는지만 고정한다 — 판정을 템플릿에 따로 쓰지 않았는지가 핵심이다.

직접 채우는 방법: `foms.web.drawing.workbench.render_template` 를 감싸 ctx 의 `customer_send` 를
덮는다(S1 이 빌더 이름을 바꿔도 이 자리는 그대로다). 같은 응답에 숨은 PC 마크업이 함께 오므로
모바일 표면(`.erp-mobile-shell.foms-drawing-handoff`)을 파서로 잘라 본다(조각: tests/support/drawing_mobile_handoff_page.py).

주입 값은 S1 빌더 어휘(키·tone·slot·urgent_call)를 그대로 따른다. 실제 빌더 출력이 모바일 템플릿을
거치는 경로·PC 와의 파리티는 test_drawing_tab_send_mobile_merged.py(S1·S2 합친 뒤에만 돈다)가 본다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.orders.drawing_customer_send import BAR_KEYS, empty_customer_send_view
from tests.support.drawing_mobile_handoff_page import (
    assert_sheet_names_only_its_own_buttons,
    bar_items as _bar,
    direct_bar_buttons as _direct_bar_buttons,
    fetch_page as _page,
    inject as _inject,
    make_order as _order,
    make_user as _user,
    mobile_bar_keys as _mobile_bar_keys,
    mobile_surface as _handoff,
    urgent_buttons as _urgent_buttons,
)

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

# §3.0 상태별 영업 쪽 버튼 — 키·라벨·tone 은 S1 빌더(drawing_customer_send_bar._LABELS) 어휘 그대로다.
# (예전엔 'warn'·'line' 을 지어내 넣어서 S1 과 어휘가 어긋나도 초록이었다 — S3 리뷰 P3.)
STATE_BARS = {
    "transferred_unsent": [("rev_sales", "내 의견", "secondary"), ("send", "고객에게 보내기", "primary"),
                           ("ok_no_customer", "확정", "secondary")],
    "transferred_sent": [("resend", "다시 보내기", "secondary"), ("rev_customer", "고객이 고쳐 달래요", "warning"),
                         ("ok", "고객 OK · 확정", "success")],
    "returned": [("edit_revision", "요청 고치기", "secondary"), ("cancel_revision", "수정요청 취소", "secondary")],
    "confirmed_approve": [("rev_post", "고객이 또 바꿔 달래요", "warning"), ("send", "고객에게 보내기", "secondary"),
                          ("approve_confirm", "고객 컨펌하고 생산으로", "success")],
    "confirmed_other": [("rev_post", "고객이 또 바꿔 달래요", "warning"), ("send", "고객에게 보내기", "secondary"),
                        ("production", "생산 현황 보기", "link")],
}
URGENT_CALL = ("urgent_call", "긴급 호출", "urgent")  # S1: 도면 쪽(도면팀·관리자)에게 늘 slot=main 으로 붙는다


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
        el = handoff.select_one(f'.foms-drawing-action-bar [data-bar-key="{item["key"]}"]')
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
        assert handoff.select(f'[data-bar-key="{key}"]') == [], key


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
    assert [el.get("data-bar-key", "urgent") for el in _direct_bar_buttons(returned)] == [
        "edit_revision", "cancel_revision", "urgent"]


def test_urgent_call_item_is_pc_only_and_drawing_team_keeps_fixed_urgent(client, monkeypatch):
    """urgent_call(Q5-①)은 PC 전용 항목 — 모바일은 순회에서 빼고 고정 [긴급 호출] 한 벌만 그린다."""
    drafter = _user("s3_uc_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"])
    _inject(monkeypatch, cs={"bar": _bar([URGENT_CALL])})
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    urgent = _urgent_buttons(handoff)
    assert len(urgent) == 1
    assert not urgent[0].has_attr("data-bar-key")  # 서버 항목이 아니라 고정 버튼
    assert urgent[0].get("data-order-id") == str(oid)
    assert handoff.select('[data-bar-key="urgent_call"]') == []


def test_admin_overflow_goes_to_more_dropup(client, monkeypatch):
    """관리자 겸 도면 담당: 도면 쪽 버튼 + 영업 쪽 main 이 바에 3개, 나머지(slot=more)와 긴급은 [더 보기].

    bar 는 S1 모양 그대로 — ADMIN 은 참여자라 urgent_call(slot=main)이 붙는다. 예전 테스트는 이 항목을
    빼고 주입해서, 모바일 바가 5칸이 되는 결함(S3 리뷰 P2)을 초록으로 통과시켰다.
    """
    admin = _user("s3_more_admin", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"])
    bar = _bar(STATE_BARS["transferred_unsent"] + [URGENT_CALL],
               slots={"rev_sales": "more", "ok_no_customer": "more"})
    _inject(monkeypatch, cs={"bar": bar})
    handoff = _handoff(_page(client, monkeypatch, admin, oid))
    action_bar = handoff.select_one(".foms-drawing-action-bar")

    direct = _direct_bar_buttons(handoff)
    assert len(direct) == 3, [el.get_text(" ", strip=True) for el in direct]
    assert direct[-1].get("data-bar-key") == "send"
    more = action_bar.select_one(".foms-drawing-action-bar__more.dropup")
    assert more is not None
    toggle = more.select_one('[data-bs-toggle="dropdown"]')
    assert toggle is not None and "더 보기" in toggle.get_text()
    menu_keys = [el.get("data-bar-key") for el in more.select(".dropdown-menu [data-bar-key]")]
    assert menu_keys == ["rev_sales", "ok_no_customer"]
    assert len(more.select(".dropdown-menu [data-foms-urgent-call]")) == 1
    # 여는 속성은 [더 보기] 안에서도 같다.
    item = more.select_one('[data-bar-key="rev_sales"]')
    assert item.get("data-revision-source") == "sales" and item.get("data-bs-target") == "#dwRevisionModal"
    assert len(_urgent_buttons(handoff)) == 1


def test_admin_after_sent_has_no_urgent_and_three_bar_buttons(client, monkeypatch):
    """관리자 겸 도면 담당 · 보낸 뒤: 바 3칸 + [더 보기], 긴급은 어디에도 없다(§3.1 보낸 뒤 긴급 빠짐)."""
    admin = _user("s3_sent_admin", role="ADMIN", team="DRAWING")
    oid = _order(admin["id"])
    bar = _bar(STATE_BARS["transferred_sent"] + [URGENT_CALL], slots={"resend": "more", "rev_customer": "more"})
    _inject(monkeypatch, cs={"bar": bar})
    handoff = _handoff(_page(client, monkeypatch, admin, oid))
    direct = _direct_bar_buttons(handoff)
    assert len(direct) == 3, [el.get_text(" ", strip=True) for el in direct]
    assert direct[-1].get("data-bar-key") == "ok"
    more = handoff.select_one(".foms-drawing-action-bar__more")
    assert [el.get("data-bar-key") for el in more.select("[data-bar-key]")] == ["resend", "rev_customer"]
    assert _urgent_buttons(handoff) == []


# tone(S1 어휘) → 모바일 모양 클래스. secondary 는 수식 없음, [확정](고객 답 없이)은 키로 line.
TONE_CLASSES = {
    "send": {"primary", "wide"}, "rev_sales": {"slim"}, "ok_no_customer": {"line", "slim"},
    "resend": {"slim"}, "rev_customer": {"warn", "mid"}, "ok": {"success", "mid"},
    "rev_post": {"warn"}, "approve_confirm": {"success"}, "production": {"primary", "wide"},
    "edit_revision": set(), "cancel_revision": set(),
}
_MODS = ("primary", "success", "warn", "line", "urgent", "slim", "mid", "wide")


@pytest.mark.parametrize("state", sorted(STATE_BARS))
def test_bar_tone_maps_to_mockup_shape(client, monkeypatch, state):
    """서버 tone 이 목업 모양으로 옮겨진다 — 매핑을 비우면 여기서 실패한다(음성 대조)."""
    drafter = _user(f"s3_tone_{state}_d", role="STAFF", team="DRAWING")
    sales = _user(f"s3_tone_{state}_s", role="MANAGER", team="SALES")
    oid = _order(drafter["id"], files=1)
    bar = _bar(STATE_BARS[state])
    _inject(monkeypatch, cs={"bar": bar})
    handoff = _handoff(_page(client, monkeypatch, sales, oid))
    for item in bar:
        el = handoff.select_one(f'.foms-drawing-action-bar [data-bar-key="{item["key"]}"]')
        mods = {m for m in _MODS if f"foms-drawing-action-bar__btn--{m}" in el["class"]}
        # CONFIRMED 의 [고객에게 보내기]는 secondary — 주 버튼 모양이 아니다.
        expected = set() if (item["key"] == "send" and item["tone"] == "secondary") else TONE_CLASSES[item["key"]]
        assert mods == expected, (state, item["key"], mods)


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


# 두 표면 파리티(PC 결정 바 == 모바일 바)는 S1 빌더·S2 PC 바가 있어야 뜻이 있다 —
# test_drawing_tab_send_mobile_merged.py 가 실제 빌더 출력으로 본다(합치기 전에는 건너뜀).


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

# 시트 본문 = 무엇이 일어나는지만(S1 _cancel_warnings 의 base + 결과 문장). 무엇을 누를지는 시트가 말한다.
WARN = ("영업이 이 1차 도면을 고객에게 이미 보냈어요(11:52 알림톡 · 링크 열림 1번). "
        "취소하면 고객 화면에서도 도면이 사라져요.")
def test_mobile_cancel_transfer_opens_warning_sheet_when_sent(client, monkeypatch):
    drafter = _user("s3_cw_d", role="STAFF", team="DRAWING")
    oid = _order(drafter["id"], files=1)
    _inject(monkeypatch, cs={"cancel_warning_text_mobile": WARN, "cancel_warning_text_pc": "PC 문구",
                             "round_text": "1차"})
    handoff = _handoff(_page(client, monkeypatch, drafter, oid))
    cancel = handoff.select_one(".foms-drawing-action-bar [data-dw-cancel-warn]")
    assert cancel is not None
    assert cancel.get("data-bs-toggle") == "modal" and cancel.get("data-bs-target") == "#dwCancelWarnMobileModal"
    # 대신 누르기(PC 확인창)와 겹치지 않는다 — 확인창 두 번 금지.
    assert not cancel.has_attr("data-drawing-handoff-action")

    sheet = handoff.select_one("#dwCancelWarnMobileModal")
    assert sheet is not None and sheet.get("data-order-id") == str(oid)
    assert WARN in sheet.get_text(" ", strip=True)
    assert_sheet_names_only_its_own_buttons(sheet)
    urgent = sheet.select_one("[data-dw-cancel-warn-urgent]")
    assert urgent is not None and "영업에게 먼저 알리기" in urgent.get_text()
    # 긴급 호출 시트의 사유 칸을 미리 채운다(PC 창과 같은 문구 · 회차 포함).
    assert urgent.get("data-urgent-message", "").startswith("고객에게 보낸 1차 도면을 전달 취소하려고 해요")
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
    # 열리는 중에 누르면 hide() 가 무시된다 — 다 열린 뒤 다시 닫고, 기다리는 동안 버튼을 잠근다(리뷰 P3).
    assert "shown.bs.modal" in source and "__fomsAskPending" in source
    assert "data-urgent-message" in source and "[data-foms-urgent-message]" in source
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
                ".foms-drawing-cancel-warn__text", ".foms-drawing-cancel-warn__hint",
                ".foms-drawing-cancel-warn__actions"):
        assert re.search(r"body\.erp-mobile-v2-layout [^{]*" + re.escape(cls) + r"\b", css), cls
    for tpl in (HANDOFF_TPL, QUEUE_CARD_TPL):
        assert 'style="' not in tpl.read_text(encoding="utf-8"), tpl


def test_empty_view_keys_cover_everything_the_mobile_template_reads():
    """모바일 템플릿이 읽는 customer_send 키는 모두 S1a 기본값에 있다(없는 키 = 합친 뒤 조용한 빈 칸)."""
    text = HANDOFF_TPL.read_text(encoding="utf-8")
    used = set(re.findall(r"\bcs\.([a-z_]+)", text))
    assert used, "모바일 템플릿이 customer_send 를 읽지 않는다"
    assert used <= set(empty_customer_send_view()), used - set(empty_customer_send_view())
