"""영업 → 고객 상태 읽기 모델 — S1 리뷰 반영(2026-09-30).

* 추가 전달(수정요청 없이 더 올린 전달) 뒤에도 같은 회차의 앞 발송이 사라지지 않는다
  (``sent_earlier_text`` · 상태 줄 '추가 전달분은 아직 안 보냄').
* 앞 회차 요약은 표지 없는 옛 발송도 앞 회차 전달 구간(시각)으로 센다.
* 마지막 시도 결과를 화면이 기계적으로 읽는 값 ``last_attempt_state``.
* 전달 취소 경고는 Q5-④ 버튼([영업에게 먼저 알리기])과 맞는 한 문구(PC·모바일 같음).

도우미는 상태 읽기 모델 테스트(``test_drawing_customer_send_status``)의 것을 그대로 쓴다.
"""
from __future__ import annotations

import datetime

from db import db_session
from foms.services.orders.drawing_customer_send import empty_customer_send_view
from models import OrderEvent
from tests.domains.test_drawing_customer_send_status import (  # noqa: F401 — ata 는 fixture
    R1_AT,
    R2_AT,
    _cs,
    _events,
    _login,
    _mutate_sd,
    _order,
    _send,
    _transfer,
    _user,
    ata,
)


def _append_transfer(oid, at=R2_AT):
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].append(_transfer(at, k)))


def _legacy_sent(oid, created_at, share_id=998001):
    db_session.add(OrderEvent(order_id=oid, event_type="SHARE_ALIMTALK",
                              payload={"share_id": share_id, "kind": "drawing", "status": "sent"},
                              created_at=created_at))
    db_session.commit()


# ── 추가 전달 뒤 같은 회차 앞 발송 ──────────────────────────────────────────
def test_append_after_send_keeps_earlier_send_visible(app, client, ata):
    _login(client, _user("rv_a"))
    oid = _order()
    _send(client, oid)
    assert _cs(app, client, oid)["sent_this_round"] is True
    _append_transfer(oid)
    cs = _cs(app, client, oid)
    assert cs["round"] == 1 and cs["is_append"] is True
    assert cs["sent_this_round"] is False  # 추가분은 아직 안 보냈다 — 보내기 주 버튼 유지
    assert cs["sent_earlier_text"] and "알림톡" in cs["sent_earlier_text"]
    assert cs["status_line"].startswith("영업 → 고객 · 1차 보냄 ")
    assert cs["status_line"].endswith("· 추가 전달분은 아직 안 보냄")
    assert "아직 안 보냄" in cs["steps"][1]["sub"] and "보냄" in cs["steps"][1]["sub"]
    keys = [b["key"] for b in cs["bar"]]
    assert "send" in keys
    # 전달 취소 경고: 고객은 이미 링크를 받았고, 취소하면 추가분이 빠진다.
    assert "이번에 더 올린 도면이 빠지고" in cs["cancel_warning_text_pc"]


def test_append_without_earlier_send_is_plain_unsent(app, client):
    """대조군(같은 모집단): 1차에 보낸 적 없으면 추가 전달 뒤에도 '아직 안 보냄' 그대로."""
    _login(client, _user("rv_b"))
    oid = _order()
    _append_transfer(oid)
    cs = _cs(app, client, oid)
    assert cs["sent_earlier_text"] == ""
    assert cs["status_line"] == "영업 → 고객 · 1차 아직 안 보냄"
    assert cs["cancel_warning_text_pc"] == ""


def test_send_of_cancelled_round_is_not_earlier_send(app, client, ata):
    """2차에 보냄 → 2차 전달 취소 → 1차 추가 전달: 2차 표지 발송은 1차 앞 발송이 아니다."""
    _login(client, _user("rv_c"))
    oid = _order()
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].extend(
        [{"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00"}, _transfer(R2_AT, k)]))
    _send(client, oid)

    def _cancel_round2_and_append(sd):
        hist = sd["drawing_transfer_history"]
        del hist[1:]  # 수정요청 취소 + 2차 전달 취소를 합친 결과(1차 전달만)
        hist.append(_transfer("2026-09-23 01:00:00", k))
    _mutate_sd(oid, _cancel_round2_and_append)
    cs = _cs(app, client, oid)
    assert cs["round"] == 1 and cs["sent_earlier_text"] == ""


def test_legacy_untagged_send_before_append_counts_as_earlier(app, client):
    _login(client, _user("rv_d"))
    oid = _order()
    _legacy_sent(oid, datetime.datetime(2026, 9, 21, 0, 0, 0))  # 1차 전달(09-20) 뒤, 추가 전달 앞
    _append_transfer(oid)
    cs = _cs(app, client, oid)
    assert cs["sent_this_round"] is False and cs["sent_earlier_text"]


# ── 앞 회차 요약: 표지 없는 옛 발송 ─────────────────────────────────────────
def _to_round2(oid):
    k = f"orders/{oid}/drawing_wizard/exports/v1.png"
    _mutate_sd(oid, lambda sd: sd["drawing_transfer_history"].extend(
        [{"action": "REQUEST_REVISION", "at": "2026-09-21 01:00:00", "source": "customer"},
         _transfer(R2_AT, k)]))


def test_prev_summary_counts_legacy_untagged_send_in_prev_window(app, client):
    _login(client, _user("rv_e"))
    oid = _order()
    _legacy_sent(oid, datetime.datetime(2026, 9, 20, 5, 0, 0))  # 1차 전달 뒤, 2차 전달 앞
    _to_round2(oid)
    cs = _cs(app, client, oid)
    assert cs["round"] == 2
    assert cs["prev_summary"] == "1차 · 보냄 · 고객 요청 1건"


def test_prev_summary_legacy_send_outside_window_is_not_sent(app, client):
    """대조군: 1차 전달 앞(09-19)에 보낸 옛 발송은 1차 발송이 아니다."""
    _login(client, _user("rv_f"))
    oid = _order()
    _legacy_sent(oid, datetime.datetime(2026, 9, 19, 5, 0, 0))
    _to_round2(oid)
    assert _cs(app, client, oid)["prev_summary"] == "1차 · 안 보냄 · 고객 요청 1건"


# ── 마지막 시도 결과(기계용) ─────────────────────────────────────────────────
def test_last_attempt_state_values(app, client, ata):
    _login(client, _user("rv_g"))
    oid = _order()
    assert _cs(app, client, oid)["last_attempt_state"] == ""
    _send(client, oid)
    assert _cs(app, client, oid)["last_attempt_state"] == "sent"
    ata["raise"] = ValueError("invalid receiver phone")
    _send(client, oid)
    assert _cs(app, client, oid)["last_attempt_state"] == "failed"
    ata["raise"] = TimeoutError("timed out")
    _send(client, oid)
    assert _cs(app, client, oid)["last_attempt_state"] == "unsure"
    ev = _events(oid)[-1]
    ev.payload = {**ev.payload, "status": "in_flight", "error": "in_flight"}
    db_session.commit()
    assert _cs(app, client, oid)["last_attempt_state"] == "unsure"


def test_new_keys_in_empty_view():
    view = empty_customer_send_view()
    assert view["last_attempt_state"] == "" and view["sent_earlier_text"] == ""


# ── 전달 취소 경고 문구(Q5-④) ───────────────────────────────────────────────
def test_cancel_warning_matches_notify_sales_button(app, client, ata):
    _login(client, _user("rv_h"))
    oid = _order()
    _send(client, oid)
    cs = _cs(app, client, oid)
    assert cs["cancel_warning_text_pc"] == cs["cancel_warning_text_mobile"]
    assert "[영업에게 먼저 알리기]" in cs["cancel_warning_text_pc"]
    assert "[취소]를 누르" not in cs["cancel_warning_text_pc"]
    assert cs["cancel_warning_text_pc"].endswith("그래도 전달을 취소할까요?")
