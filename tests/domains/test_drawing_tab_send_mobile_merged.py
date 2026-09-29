"""도면 탭 고객 보내기 — 모바일 도면 방 × 실제 S1 빌더 출력(합친 뒤 테스트, 설계서 2026-09-29 §3.0·§3.1·§3.4·§7.1).

S3 의 다른 테스트는 손으로 만든 ``customer_send`` 를 주입한다. 그러면 S1 빌더가 실제로 내는 값
(관리자에게 붙는 ``urgent_call``, tone 어휘, 전달 취소 경고 문구)이 모바일 템플릿을 거치는 경로가
하나도 없어서, 갈래 사이 약속이 어긋나도 초록으로 남았다(S3 리뷰 P2 세 건).

이 파일은 **주입 없이** 실제 상세 라우트·실제 공유 발송 라우트로 상태를 만들고 모바일 표면을 본다.

* S1(``drawing_customer_send_view``·S1 상태 테스트 도우미)이 없으면 파일 전체를 건너뛴다.
* PC 결정 바와의 파리티·시트 id 존재는 S2(``workbench_customer_send_modals.html``)도 있어야 돈다.
  PC 는 ``urgent_call`` 을 결정 바 항목으로 그리고 모바일은 고정 [긴급] 한 벌로 그리므로, 파리티
  비교에서는 ``urgent_call`` 을 뺀다(모바일 긴급 규칙은 따로 단언한다).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_status = pytest.importorskip(
    "tests.domains.test_drawing_customer_send_status",
    reason="S1(도면 탭 고객 보내기 읽기 모델)을 합친 뒤에만 돈다",
)
from foms.services.orders import drawing_customer_send_bar as bar_mod  # noqa: E402
from tests.support.drawing_mobile_handoff_page import (  # noqa: E402
    assert_sheet_names_only_its_own_buttons,
    direct_bar_buttons,
    fetch_page,
    login,
    mobile_bar_keys,
    mobile_surface,
    urgent_buttons,
)

ata = _status.ata  # 알림톡 벤더 가짜(fixture) — S1 상태 테스트와 같은 것

ROOT = Path(__file__).resolve().parents[2]
HANDOFF_TPL = ROOT / "templates/drawing/partials/workbench_mobile_handoff.html"
S2_MODALS = ROOT / "templates/drawing/partials/workbench_customer_send_modals.html"
needs_s2 = pytest.mark.skipif(not S2_MODALS.exists(), reason="S2(PC 결정 바·공용 시트)를 합친 뒤에만 돈다")


def _who(user) -> dict:
    # 요청이 끝나면 세션이 닫혀 ORM 객체 속성을 못 읽는다 — 만든 직후 값만 들고 다닌다.
    return {"id": user.id, "username": user.username, "role": user.role}


def _people():
    return {
        "sales": _who(_status._user("s3m_sales")),
        "drafter": _who(_status._user("s3m_drafter", role="STAFF", team="DRAWING", name="도면담당S3")),
        "admin": _who(_status._user("s3m_admin", role="ADMIN", team="DRAWING", name="관리자S3")),
    }


def _mobile(client, monkeypatch, who, oid):
    soup = fetch_page(client, monkeypatch, who, oid)
    return soup, mobile_surface(soup)


def _send_as(client, who, oid):
    login(client, who)
    _, res = _status._send(client, oid)
    assert res.status_code == 200, res.get_json()


def _assert_urgent_rule(handoff, *, sent: bool) -> None:
    """§3.0·§3.1: 바는 앞 3칸 + [더 보기] · urgent_call 항목은 모바일에 없다 · 긴급은 보내기 전 한 벌, 보낸 뒤 없음."""
    direct = direct_bar_buttons(handoff)
    assert len(direct) <= 3, [el.get_text(" ", strip=True) for el in direct]
    assert handoff.select('[data-bar-key="urgent_call"]') == []
    urgent = urgent_buttons(handoff)
    if sent:
        assert urgent == []
        return
    assert len(urgent) == 1
    more = handoff.select_one(".foms-drawing-action-bar__more")
    if more is not None:
        assert more.select("[data-foms-urgent-call]") == urgent


def test_admin_real_bar_keeps_three_slots_and_urgent_rule(client, monkeypatch, ata):
    """관리자 겸 도면 담당(참여자 → S1 이 urgent_call 을 붙임): 보내기 전·보낸 뒤 모두 바 3칸 규칙."""
    p = _people()
    oid = _status._order(assignees=[p["admin"]["id"]])
    _, before = _mobile(client, monkeypatch, p["admin"], oid)
    assert "send" in mobile_bar_keys(before)
    _assert_urgent_rule(before, sent=False)

    _send_as(client, p["admin"], oid)
    _, after = _mobile(client, monkeypatch, p["admin"], oid)
    assert "ok" in mobile_bar_keys(after)
    _assert_urgent_rule(after, sent=True)


def test_drawing_team_real_bar_draws_only_fixed_urgent(client, monkeypatch):
    p = _people()
    oid = _status._order(assignees=[p["drafter"]["id"]])
    _, handoff = _mobile(client, monkeypatch, p["drafter"], oid)
    assert mobile_bar_keys(handoff) == []
    _assert_urgent_rule(handoff, sent=False)


def test_real_cancel_warning_sheet_names_only_its_own_buttons(client, monkeypatch, ata):
    """영업이 이번 회차를 보냄 → 도면 담당 모바일 [전달 취소]는 경고 시트. 본문(S1 실제 문구)에
    확인창용 '[취소]를 누르세요' 가 없고, 부르는 [버튼]은 모두 시트에 있다(리뷰 P2)."""
    p = _people()
    oid = _status._order(assignees=[p["drafter"]["id"]])
    _send_as(client, p["sales"], oid)
    _, handoff = _mobile(client, monkeypatch, p["drafter"], oid)
    cancel = handoff.select_one(".foms-drawing-action-bar [data-dw-cancel-warn]")
    assert cancel is not None and cancel.get("data-bs-target") == "#dwCancelWarnMobileModal"
    sheet = handoff.select_one("#dwCancelWarnMobileModal")
    assert sheet is not None
    assert "1차" in sheet.select_one(".foms-drawing-cancel-warn__text").get_text()
    assert_sheet_names_only_its_own_buttons(sheet)


def test_every_server_tone_has_a_mobile_shape():
    """S1 tone 어휘가 모바일 매핑표(_cs_tone_class)에 모두 있다 — secondary 는 기본 모양이라 표 밖."""
    text = HANDOFF_TPL.read_text(encoding="utf-8")
    table = re.search(r"_cs_tone_class = \{(.*?)\} %\}", text, re.S)
    assert table is not None
    mapped = set(re.findall(r"'([a-z_]+)':", table.group(1)))
    tones = {tone for _label, tone in bar_mod._LABELS.values()}
    assert tones - {"secondary"} <= mapped, tones - {"secondary"} - mapped


# ── S2 까지 합친 뒤: PC 결정 바 파리티 · 여는 시트 존재 ─────────────────────────


def _pc_keys(soup) -> list[str]:
    pc = soup.select_one(".dw-legacy-detail .dw-sidebar-actions")
    assert pc is not None
    return [el["data-bar-key"] for el in pc.select("[data-bar-key]") if el["data-bar-key"] != "urgent_call"]


def _returned_history():
    return [_status._transfer(_status.R1_AT, "x"),
            {"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00", "note": "문짝 폭", "files": [],
             "by_user_name": _status.SALES}]


@needs_s2
@pytest.mark.parametrize("case", ["sales_unsent", "sales_sent", "sales_returned", "drafter", "admin"])
def test_pc_and_mobile_draw_the_same_server_list(client, monkeypatch, ata, case):
    p = _people()
    viewer = {"drafter": p["drafter"], "admin": p["admin"]}.get(case, p["sales"])
    kwargs = {"assignees": [p["admin"]["id"] if case == "admin" else p["drafter"]["id"]]}
    if case == "sales_returned":
        kwargs.update(history=_returned_history(), drawing_status="RETURNED")
    oid = _status._order(**kwargs)
    if case == "sales_sent":
        _send_as(client, p["sales"], oid)
    soup, handoff = _mobile(client, monkeypatch, viewer, oid)
    pc = _pc_keys(soup)
    # 같은 목록 — 모바일은 앞 칸(main)을 바에, 나머지(more)를 [더 보기]에 두므로 순서는 칸 안에서만 같다.
    assert sorted(mobile_bar_keys(handoff)) == sorted(pc), case
    more = handoff.select_one(".foms-drawing-action-bar__more")
    in_more = [el["data-bar-key"] for el in more.select("[data-bar-key]")] if more is not None else []
    in_bar = [k for k in mobile_bar_keys(handoff) if k not in in_more]
    for group in (in_bar, in_more):
        assert group == [k for k in pc if k in group], (case, group, pc)
    # 모바일 바가 여는 시트는 모두 같은 응답 안에 있다(S1a 만 합쳤을 때의 빈 버튼 방지 — 리뷰 P3).
    for el in handoff.select(".foms-drawing-action-bar [data-bs-target]"):
        assert soup.select_one(el["data-bs-target"]) is not None, (case, el["data-bs-target"])
