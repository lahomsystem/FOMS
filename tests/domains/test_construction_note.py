"""시공 메모 한 줄 더하기(설계서 2026-11-14-foms-graft 3.3 ``add_construction_note``) — 새 쓰기 길.

- 있던 메모 끝에 한 줄 · 깊은 복사(옛 dict 는 그대로) · 판 번호 1 올림 · REV-00 영수증 · 변경 원장 줄(같은 변경 묶음).
- 메모 칸이 없거나 빈 글이면 칸 dict 를 만들고, 다른 칸(주소 메모 등)은 그대로 둔다.
- 글 한 칸 메모(마법사 · 옛 주문)는 더하지 않는다(그 글이 사라지므로) · 빈 글 · 200자 넘음 · 가림 검사 걸림도 거절.
- 도면팀 알림은 시공일 쓰기와 같은 부품(apply → 마무리) — 알림 실패가 저장을 막지 않는다.
합성 주문 · 합성 글만.
"""

from __future__ import annotations

import copy

import pytest
from werkzeug.security import generate_password_hash

import foms.services.orders.construction_note as note_mod
from db import db_session
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.construction_note import (
    NOTE_LIMIT, NoteInputError, add_construction_note, clean_note_line, finalize_note_notifications, note_lines,
    notes_block,
)
from models import Order, OrderFieldChange, OrderMutationReceipt, User


def _user() -> User:
    user = User(username="cn_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _order(notes) -> Order:
    sd = {"workflow": {"stage": "CONFIRM"}, "schedule": {"construction": {"date": "2030-01-10", "time": "오전"}}}
    if notes is not None:
        sd["notes"] = notes
    order = Order(received_date="2030-01-01", customer_name="합성 손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status="CONFIRM", is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture
def quiet_alerts(monkeypatch):
    """도면팀 알림을 기록만 하는 가짜로(푸시 · 실시간 없음)."""
    calls: dict[str, list] = {"apply": [], "finalize": []}

    def _apply(db, order, old_sd, new_sd, **kwargs):
        calls["apply"].append((copy.deepcopy(old_sd), copy.deepcopy(new_sd), kwargs["actor_user_id"]))
        return "알림", True

    monkeypatch.setattr(note_mod, "apply_drawing_order_change_alert", _apply)
    monkeypatch.setattr(note_mod, "finalize_drawing_order_change_alert",
                        lambda db, notif, created_new: calls["finalize"].append((notif, created_new)))
    return calls


def test_appends_one_line_bumps_version_records_ledger(app, quiet_alerts):
    user = _user()
    order = _order({"construction_note": "현관 계단 좁음", "address_note": "합성 주소 메모"})
    old_sd = order.structured_data
    version = order.mutation_version

    result = add_construction_note(db_session, order, user, line="  엘리베이터   없음 ")
    db_session.commit()

    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved.structured_data["notes"] == {"construction_note": "현관 계단 좁음\n엘리베이터 없음",
                                              "address_note": "합성 주소 메모"}
    assert old_sd["notes"]["construction_note"] == "현관 계단 좁음"  # 옛 dict 는 그대로(깊은 복사)
    assert saved.mutation_version == version + 1
    assert db_session.query(OrderMutationReceipt).count() == 1
    rows = db_session.query(OrderFieldChange).filter_by(change_set_id=result.change_set_id).all()
    assert rows and result.change_count == len(rows) and all(r.order_id == order.id for r in rows)
    assert {r.actor_user_id for r in rows} == {user.id}
    assert result.before_lines == 1 and note_lines(saved.structured_data) == ["현관 계단 좁음", "엘리베이터 없음"]
    assert quiet_alerts["apply"][0][2] == user.id and result.notifications == [("drawing", "알림", True)]
    finalize_note_notifications(db_session, result)
    assert quiet_alerts["finalize"] == [("알림", True)]


@pytest.mark.parametrize("notes", [None, "", {"address_note": "합성 메모"}])
def test_missing_or_empty_notes_make_the_note_field(app, quiet_alerts, notes):
    order = _order(notes)
    add_construction_note(db_session, order, _user(), line="자재 먼저 내림")
    db_session.commit()
    db_session.expire_all()
    saved = db_session.get(Order, order.id).structured_data["notes"]
    assert saved["construction_note"] == "자재 먼저 내림"
    if isinstance(notes, dict):
        assert saved["address_note"] == "합성 메모"


def test_text_notes_are_not_overwritten(app, quiet_alerts):
    order = _order("손님이 적은 메모 한 칸")
    with pytest.raises(NoteInputError):
        add_construction_note(db_session, order, _user(), line="자재 먼저 내림")
    db_session.rollback()
    db_session.expire_all()
    saved = db_session.get(Order, order.id)
    assert saved.structured_data["notes"] == "손님이 적은 메모 한 칸"
    assert notes_block(saved.structured_data) is None and note_lines(saved.structured_data) == []
    assert db_session.query(OrderFieldChange).count() == 0


@pytest.mark.parametrize("line", ["", "   ", "가" * (NOTE_LIMIT + 1), "연락처 010-2345-6789 로 전화"])
def test_bad_lines_are_refused_without_echoing_the_text(line):
    with pytest.raises(NoteInputError) as caught:
        clean_note_line(line)
    assert "010" not in str(caught.value)


def test_alert_failure_does_not_block_the_save(app, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("합성 실패")

    monkeypatch.setattr(note_mod, "apply_drawing_order_change_alert", _boom)
    order = _order({})
    result = add_construction_note(db_session, order, _user(), line="자재 먼저 내림")
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(Order, order.id).structured_data["notes"]["construction_note"] == "자재 먼저 내림"
    assert result.notifications == []
