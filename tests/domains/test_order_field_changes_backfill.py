"""ORDER-DIFF-01 백필 계약 — 1안 기록을 원장으로 옮기되 두 번 돌려도 중복 0.

백필은 운영에서 한 번 돌리고 끝나는 코드라 테스트가 없으면 **첫 실행이 곧 검증**이 된다.
여기서 고정하는 것: dry-run 이 아무 것도 쓰지 않는가, 반영이 정확한가, 재실행이 멱등인가,
원장의 시간축이 백필 실행 시각이 아니라 원 감사 시각인가.
"""

import datetime
import importlib.util
import pathlib

from db import db_session
from models import OrderFieldChange, SecurityLog

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ops" / "backfill_order_field_changes.py"
)
_spec = importlib.util.spec_from_file_location("backfill_order_field_changes", _SCRIPT)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def _seed_legacy_log(order_id: int = 4321) -> SecurityLog:
    """change_set 없이 detail.changes 만 있는 1안 시기 감사 행."""
    entry = SecurityLog(
        message=f"주문 #{order_id} — 주문 저장: 전체 저장",
        action="ORDER_STRUCTURED_SAVED",
        target_type="order",
        target_id=order_id,
        timestamp=datetime.datetime(2026, 8, 11, 3, 30, 0),
        detail={
            "mode": "full",
            "change_count": 2,
            "truncated": 0,
            "changes": [
                {"path": "schedule.measurement.date", "before": "2026-08-12",
                 "after": "2026-08-14", "op": "set"},
                {"path": "items.1.price", "before": None, "after": "620000",
                 "op": "add", "item": "붙박이장"},
            ],
        },
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def _ledger(order_id: int):
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == order_id)
        .order_by(OrderFieldChange.id)
        .all()
    )


def test_dry_run_writes_nothing(client, monkeypatch, capsys):
    """기본은 dry-run — 건수만 세고 원장은 그대로다."""
    entry_id = _seed_legacy_log(order_id=4401).id
    monkeypatch.setattr("sys.argv", ["backfill_order_field_changes.py"])

    assert backfill.main() == 0

    assert _ledger(4401) == []
    assert "dry-run" in capsys.readouterr().out
    # 스크립트가 세션을 닫으므로 원본은 다시 읽어 확인한다(무접촉 여부).
    assert db_session.get(SecurityLog, entry_id).detail["change_count"] == 2


def test_apply_moves_changes_into_ledger(client, monkeypatch):
    """--apply 는 변경을 원장 행으로 옮기고, 시간축은 원 감사 시각을 쓴다."""
    _seed_legacy_log(order_id=4402)
    monkeypatch.setattr("sys.argv", ["backfill_order_field_changes.py", "--apply"])

    assert backfill.main() == 0

    rows = _ledger(4402)
    assert [row.path for row in rows] == ["schedule.measurement.date", "items.1.price"]
    assert rows[1].path_template == "items.*.price"
    assert rows[1].item_index == 1
    assert rows[1].item_name == "붙박이장"
    # 백필 실행 시각이 아니라 그 저장이 일어난 시각이어야 이력이 시간순으로 읽힌다.
    assert rows[0].created_at == datetime.datetime(2026, 8, 11, 3, 30, 0)
    # change_set 이 없던 행은 결정적 대체 id 로 묶인다.
    assert {row.change_set_id for row in rows} == {f"seclog:{rows[0].change_set_id.split(':')[1]}"}


def test_rerun_is_idempotent(client, monkeypatch):
    """두 번 돌려도 중복이 생기지 않는다(결정적 change set id)."""
    _seed_legacy_log(order_id=4403)
    monkeypatch.setattr("sys.argv", ["backfill_order_field_changes.py", "--apply"])

    backfill.main()
    first = len(_ledger(4403))
    backfill.main()

    assert first == 2
    assert len(_ledger(4403)) == first
