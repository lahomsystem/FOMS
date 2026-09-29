"""S2 — 도면 작업실 PC 결정 바의 S1 연결 쪽(설계서 2026-09-29 §3.0·§3.3·§3.4 · 리뷰 P1·P2).

- 빈 bar(S1 읽기 모델 없이 S2 만 올라간 경우)면 옛 [수정 요청]·[수령 확정]·[수정요청 취소] 를 같은 id 로 대신 그린다.
- 회차 기록 줄은 영업 쪽 항목이 있을 때만(도면팀 bar=[urgent_call] 에는 상태 한 줄만).
- S1 이 합쳐진 뒤에만 도는 상태별 통합 테스트(상세 라우트가 build_customer_send_view 를 실제로 쓰는지로 판정).
"""

from __future__ import annotations

import pytest

from tests.support.drawing_tab_send_pc_helpers import (
    S1_MERGED, _bar, _bar_keys, _inject, _legacy, _order, _page, _pc, make_people,
)


@pytest.fixture
def people():
    return make_people()


# --------------------------------------------------------------------------- 빈 bar(S1 읽기 모델 없음) 대체


def test_empty_bar_draws_legacy_buttons_as_fallback(client, monkeypatch, people):
    """bar 가 빈 값이면(S2 만 올라가 S1 읽기 모델이 없을 때) 옛 [수정 요청]·[수령 확정] 을 같은 id 로 대신 그린다.

    이게 없으면 PC 결정 바에서 두 버튼이 사라지고, 모바일 바의 [수령 확정] 대신 누르기(#btn-confirm-receipt)가
    조용히 아무 일도 안 한다(리뷰 P2). 새 버튼·보내기 시트는 여전히 안 보인다."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {})
    soup = _page(client, people["sales"], oid)
    assert _legacy(soup) == ["rev_sales", "ok_no_customer"]
    ok = soup.select("#btn-confirm-receipt")
    assert len(ok) == 1 and ok[0]["data-bs-target"] == "#dwCustomerOkModal" and "수령 확정" in ok[0].get_text()
    assert soup.select_one("#dwCustomerOkModal") is not None
    rev = _pc(soup).select_one('[data-bar-legacy][data-bar-key="rev_sales"]')
    assert rev["data-bs-target"] == "#dwRevisionModal" and "수정 요청" in rev.get_text()
    assert soup.select_one("#dwCustomerSendModal") is None
    assert soup.select_one("#dwRevisionEditModal") is None
    assert soup.select_one("#dwUrgentCallModal") is None


def test_empty_bar_returned_draws_legacy_cancel_revision(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")
    _inject(monkeypatch, {})
    soup = _page(client, people["sales"], oid)
    assert _legacy(soup) == ["cancel_revision"]
    assert len(soup.select("#btn-cancel-revision")) == 1
    assert soup.select_one("#btn-confirm-receipt") is None


def test_empty_bar_drawing_team_gets_no_legacy_sales_buttons(client, monkeypatch, people):
    """대조군: 도면팀은 옛 블록 조건(영업 쪽)이 거짓이라 대체 버튼도 없다."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {})
    soup = _page(client, people["drafter"], oid)
    assert _legacy(soup) == [] and soup.select_one("#btn-confirm-receipt") is None


def test_bar_with_sales_keys_never_adds_legacy(client, monkeypatch, people):
    """bar 에 같은 역할 키가 있으면 대체는 절대 붙지 않는다(두 번 그리지 않게 · 확정 id 한 번)."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("rev_sales", "send", "ok_no_customer")})
    soup = _page(client, people["sales"], oid)
    assert _legacy(soup) == [] and len(soup.select("#btn-confirm-receipt")) == 1


def test_status_line_absent_when_empty(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {})
    soup = _page(client, people["drafter"], oid)
    assert soup.select_one("[data-customer-send-status]") is None


_STEPS = [{"label": "1차 도착", "sub": "", "when": "09-20 10:00", "state": "done"},
          {"label": "고객에게 보내기", "sub": "", "when": "", "state": "now"}]


def test_steps_hidden_for_drawing_team_urgent_only_bar(client, monkeypatch, people):
    """도면팀 bar=[urgent_call] 이어도 영업용 회차 기록 줄은 안 보인다(§3.3·§3.4 — 상태 한 줄만)."""
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("urgent_call"), "steps": _STEPS, "status_line": "영업 → 고객 · 1차 아직 안 보냄"})
    soup = _page(client, people["drafter"], oid)
    assert soup.select_one("[data-customer-send-steps]") is None
    assert soup.select_one("[data-customer-send-status]") is not None


def test_steps_shown_for_sales_bar(client, monkeypatch, people):
    oid = _order(people["drafter"]["id"])
    _inject(monkeypatch, {"bar": _bar("rev_sales", "send"), "steps": _STEPS})
    soup = _page(client, people["sales"], oid)
    assert len(soup.select("[data-customer-send-steps] li")) == 2


# --------------------------------------------------------------------------- S1 합친 뒤 통합(상태 → bar → PC)

_S1_MERGED = S1_MERGED
_SALES_KEYS = {"send", "resend", "rev_customer", "rev_sales", "ok", "ok_no_customer", "rev_post",
               "approve_confirm", "production", "cancel_revision", "edit_revision"}


@pytest.mark.skipif(not _S1_MERGED, reason="S1 읽기 모델(build_customer_send_view)이 아직 합쳐지지 않았다")
def test_integration_sales_transferred_not_sent(client, people):
    oid = _order(people["drafter"]["id"])
    soup = _page(client, people["sales"], oid)
    keys = _bar_keys(soup)
    assert {"send", "ok_no_customer", "rev_sales"} <= set(keys)
    assert "resend" not in keys and "ok" not in keys
    assert keys.count("ok_no_customer") == 1
    assert _legacy(soup) == []  # S1 이 있으면 옛 블록 대체는 붙지 않는다
    assert soup.select_one("[data-customer-send-steps]") is not None


@pytest.mark.skipif(not _S1_MERGED, reason="S1 읽기 모델(build_customer_send_view)이 아직 합쳐지지 않았다")
def test_integration_drawing_team_status_line_not_sent_without_steps(client, people):
    """S1 합친 뒤 기대값: 도면팀도 '영업 → 고객 · 1차 아직 안 보냄' 한 줄은 보고, 영업용 회차 기록 줄은 안 본다."""
    oid = _order(people["drafter"]["id"])
    soup = _page(client, people["drafter"], oid)
    line = soup.select_one("[data-customer-send-status]")
    assert line is not None and "아직 안 보냄" in line.get_text()
    assert soup.select_one("[data-customer-send-steps]") is None


@pytest.mark.skipif(not _S1_MERGED, reason="S1 읽기 모델(build_customer_send_view)이 아직 합쳐지지 않았다")
def test_integration_returned_has_no_send(client, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")
    soup = _page(client, people["sales"], oid)
    keys = _bar_keys(soup)
    assert "cancel_revision" in keys and "send" not in keys and "resend" not in keys
    assert len(soup.select("#btn-cancel-revision")) == 1
    assert _legacy(soup) == []


@pytest.mark.skipif(not _S1_MERGED, reason="S1 읽기 모델(build_customer_send_view)이 아직 합쳐지지 않았다")
def test_integration_drawing_team_gets_no_sales_buttons(client, people):
    oid = _order(people["drafter"]["id"])
    keys = _bar_keys(_page(client, people["drafter"], oid))
    assert not (set(keys) & _SALES_KEYS)
