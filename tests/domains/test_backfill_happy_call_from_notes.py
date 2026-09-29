"""tools/ops/backfill_happy_call_from_notes.py — 비고 '부재'·'콜백'을 flags.happy_call 로 옮기는 1회성 백필."""
import importlib.util
from pathlib import Path

from db import db_session
from models import Order

_SPEC = importlib.util.spec_from_file_location(
    "backfill_happy_call_from_notes",
    Path(__file__).resolve().parents[2] / "tools" / "ops" / "backfill_happy_call_from_notes.py",
)
backfill = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backfill)


def _order(notes, flags=None):
    order = Order(customer_name="테스트", phone="010-0000-0000", address="서울", product="장",
                  received_date="2026-09-29", status="MEASURE", is_erp_order=True, notes=notes,
                  structured_data={"workflow": {"stage": "MEASURE"}, "flags": flags or {"urgent": False}})
    db_session.add(order)
    db_session.commit()
    return order.id


def test_moves_only_exact_words_and_is_idempotent(app):
    absent = _order(" 부재 ")
    callback = _order("콜백", flags={"happy_call": "부재"})
    mixed = _order("고객님 해외 출장 부재 / 카카오톡")
    plain = _order("엘리베이터 없음")

    dry = backfill.run_backfill(db_session, execute=False)
    assert dry["written"] == 2
    db_session.expire_all()
    assert db_session.get(Order, absent).notes == " 부재 "  # dry-run 은 쓰지 않는다

    done = backfill.run_backfill(db_session, execute=True)
    assert sorted(m["id"] for m in done["moved"]) == sorted([absent, callback])
    db_session.expire_all()
    a = db_session.get(Order, absent)
    assert a.notes is None
    assert a.structured_data["flags"] == {"urgent": False, "happy_call": "부재"}
    # 이미 드롭다운 값이 있으면 덮지 않는다.
    assert db_session.get(Order, callback).structured_data["flags"]["happy_call"] == "부재"
    # 음성 대조군: 섞인 비고·일반 비고는 그대로.
    assert db_session.get(Order, mixed).notes == "고객님 해외 출장 부재 / 카카오톡"
    assert db_session.get(Order, plain).notes == "엘리베이터 없음"

    assert backfill.run_backfill(db_session, execute=False)["written"] == 0


def test_values_match_the_save_api():
    from foms.api.erp_orders_structured import HAPPY_CALL_VALUES

    assert backfill.HAPPY_CALL_VALUES == HAPPY_CALL_VALUES
