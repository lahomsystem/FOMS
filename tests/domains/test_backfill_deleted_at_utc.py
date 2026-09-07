"""``tools/ops/backfill_deleted_at_utc.py`` 마커 선별·보정·멱등 계약.

이 백필의 위험은 "두 번 돌리면 9시간이 또 깎인다" 이다. 초안 폐기가 남긴 ISO 행은
``status='DELETED'`` + ``original_status='DRAFT'`` + delete meta 없음이라, ``iso`` 마커가
고정폭으로 정규화해 놓으면 2회차에 ``legacy_kst`` 술어에 그대로 걸린다. 그래서 아래
:func:`test_iso_draft_row_survives_two_applies` 가 이 파일의 중심이다.

SQLite ``db_session`` 픽스처만 쓴다. 운영 DB 에 접속하지 않는다.
"""
from __future__ import annotations

import datetime
import json

import pytest
from pathlib import Path
from typing import Any, Optional

from db import db_session
from models import Order

import tools.ops.backfill_deleted_at_utc as backfill_tool
from tools.ops.backfill_deleted_at_utc import (
    BACKFILL_KEY,
    MARKER_ISO,
    MARKER_LEGACY_KST,
    main,
    run_backfill,
    run_revert,
)


def _make_order(
    *,
    deleted_at: str,
    status: str = "RECEIVED",
    original_status: Optional[str] = None,
    structured_data: Optional[dict[str, Any]] = None,
) -> Order:
    """휴지통 행 하나를 만든다(``deleted_at`` 문자열 컬럼을 직접 채운다)."""
    order = Order(
        received_date="2026-09-01",
        customer_name="휴지통 백필 대상",
        phone="010-0000-0000",
        address="서울시 강남구",
        product="장",
        status=status,
        original_status=original_status,
        deleted_at=deleted_at,
        created_at=datetime.datetime(2026, 9, 1, 0, 0, 0),
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else {},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _reload(order_id: int) -> Order:
    """커밋/롤백 뒤 DB 에 실제로 남은 행을 다시 읽는다."""
    db_session.expire_all()
    return db_session.query(Order).filter(Order.id == order_id).one()


def _journal_lines(path: Path) -> list[dict[str, Any]]:
    """저널 JSONL 을 리스트로 읽는다(파일이 없으면 예외 — 저널은 항상 생겨야 한다)."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_legacy_kst_row_shifts_back_nine_hours(app, tmp_path) -> None:
    """legacy 일괄 삭제 표식 행은 -9시간 보정되고 표식이 남는다."""
    order = _make_order(
        deleted_at="2026-09-07 17:41:00", status="DELETED", original_status="RECEIVED"
    )
    journal = tmp_path / "run1.jsonl"

    summary = run_backfill(db_session, apply=True, journal_path=str(journal))

    assert summary["markers"][MARKER_LEGACY_KST] == {"scanned": 1, "changed": 1, "skipped": 0}
    assert summary["markers"][MARKER_ISO]["scanned"] == 0
    saved = _reload(order.id)
    assert saved.deleted_at == "2026-09-07 08:41:00"
    # 판정 축은 건드리지 않는다.
    assert saved.status == "DELETED"
    assert saved.original_status == "RECEIVED"
    assert "delete" not in saved.structured_data
    assert saved.structured_data[BACKFILL_KEY]["marker"] == MARKER_LEGACY_KST
    assert saved.structured_data[BACKFILL_KEY]["before"] == "2026-09-07 17:41:00"
    assert _journal_lines(journal) == [
        {
            "order_id": order.id,
            "marker": MARKER_LEGACY_KST,
            "before": "2026-09-07 17:41:00",
            "after": "2026-09-07 08:41:00",
        }
    ]


def test_iso_row_is_format_normalized_without_moving_the_clock(app, tmp_path) -> None:
    """ISO 행은 형식만 바뀐다 — 시계는 한 초도 움직이지 않는다(문자열로 확인)."""
    order = _make_order(
        deleted_at="2026-09-07T08:41:00", status="DELETED", original_status="DRAFT"
    )

    summary = run_backfill(db_session, apply=True, journal_path=str(tmp_path / "run1.jsonl"))

    assert summary["markers"][MARKER_ISO] == {"scanned": 1, "changed": 1, "skipped": 0}
    assert summary["markers"][MARKER_LEGACY_KST]["scanned"] == 0
    assert _reload(order.id).deleted_at == "2026-09-07 08:41:00"


def test_iso_draft_row_survives_two_applies(app, tmp_path) -> None:
    """교차 오염 금지 — 정규화된 ISO 행이 2회차에 legacy 마커로 또 깎이지 않는다."""
    order = _make_order(
        deleted_at="2026-09-07T08:41:00", status="DELETED", original_status="DRAFT"
    )

    run_backfill(db_session, apply=True, journal_path=str(tmp_path / "run1.jsonl"))
    after_first = _reload(order.id).deleted_at
    second = run_backfill(db_session, apply=True, journal_path=str(tmp_path / "run2.jsonl"))

    assert after_first == "2026-09-07 08:41:00"
    assert _reload(order.id).deleted_at == after_first  # 9시간이 더 깎이지 않았다
    assert second["changed"] == 0
    assert second["skipped"] == {"already_backfilled": 1}


def test_second_apply_changes_nothing_and_journal_is_empty(app, tmp_path) -> None:
    """멱등 — 2회차는 changed=0 이고 2회차 저널이 0행이다."""
    legacy = _make_order(
        deleted_at="2026-09-07 17:41:00", status="DELETED", original_status="RECEIVED"
    )
    iso = _make_order(
        deleted_at="2026-09-06T23:10:30", status="DELETED", original_status="DRAFT"
    )
    first_journal = tmp_path / "run1.jsonl"
    second_journal = tmp_path / "run2.jsonl"

    first = run_backfill(db_session, apply=True, journal_path=str(first_journal))
    frozen = {legacy.id: _reload(legacy.id).deleted_at, iso.id: _reload(iso.id).deleted_at}
    second = run_backfill(db_session, apply=True, journal_path=str(second_journal))

    assert first["changed"] == 2
    assert second["changed"] == 0
    assert second["journal_rows"] == 0
    assert _journal_lines(second_journal) == []
    # 문자 그대로 같아야 한다.
    assert {oid: _reload(oid).deleted_at for oid in frozen} == frozen


def test_canonical_projection_rows_match_no_marker(app, tmp_path) -> None:
    """음성 대조군 (a) — 정본 projection 행은 어느 마커에도 걸리지 않는다."""
    canonical = _make_order(
        deleted_at="2026-09-07 08:41:00",
        status="RECEIVED",  # soft_delete 정본은 status 를 덮지 않는다
        structured_data={"delete": {"deleted_by": 1, "deleted_at": "2026-09-07 08:41:00"}},
    )
    legacy_shaped_but_canonical = _make_order(
        deleted_at="2026-09-07 08:42:00",
        status="DELETED",
        original_status="RECEIVED",
        structured_data={"delete": {"deleted_by": 1, "deleted_at": "2026-09-07 08:42:00"}},
    )

    summary = run_backfill(db_session, apply=True, journal_path=str(tmp_path / "run1.jsonl"))

    assert summary["changed"] == 0
    assert summary["markers"][MARKER_ISO]["scanned"] == 0
    assert summary["markers"][MARKER_LEGACY_KST]["scanned"] == 0
    assert summary["skipped"] == {"not_legacy_status": 1, "has_delete_projection": 1}
    assert _reload(canonical.id).deleted_at == "2026-09-07 08:41:00"
    assert _reload(legacy_shaped_but_canonical.id).deleted_at == "2026-09-07 08:42:00"


def test_unparsable_value_is_only_counted_as_skipped(app, tmp_path) -> None:
    """음성 대조군 (b) — 파싱 불가 쓰레기 값은 skipped 로만 세고 값이 안 바뀐다."""
    garbage_iso = _make_order(
        deleted_at="2026-99-99T99:99:99", status="DELETED", original_status="DRAFT"
    )
    garbage_shape = _make_order(
        deleted_at="삭제됨", status="DELETED", original_status="RECEIVED"
    )
    journal = tmp_path / "run1.jsonl"

    summary = run_backfill(db_session, apply=True, journal_path=str(journal))

    assert summary["changed"] == 0
    assert summary["markers"][MARKER_ISO] == {"scanned": 1, "changed": 0, "skipped": 1}
    assert summary["skipped"] == {f"{MARKER_ISO}:unparsable": 1, "unknown_shape": 1}
    assert _journal_lines(journal) == []
    assert _reload(garbage_iso.id).deleted_at == "2026-99-99T99:99:99"
    assert _reload(garbage_shape.id).deleted_at == "삭제됨"
    assert BACKFILL_KEY not in _reload(garbage_iso.id).structured_data


def test_dry_run_writes_journal_but_not_the_row(app, tmp_path) -> None:
    """dry-run 은 값·structured_data 를 안 바꾸고 저널(미리보기)만 남긴다."""
    order = _make_order(
        deleted_at="2026-09-07 17:41:00", status="DELETED", original_status="RECEIVED"
    )
    journal = tmp_path / "preview.jsonl"

    summary = run_backfill(db_session, apply=False, journal_path=str(journal))

    assert summary["mode"] == "dry-run"
    assert summary["changed"] == 1
    saved = _reload(order.id)
    assert saved.deleted_at == "2026-09-07 17:41:00"
    assert BACKFILL_KEY not in saved.structured_data
    assert _journal_lines(journal) == [
        {
            "order_id": order.id,
            "marker": MARKER_LEGACY_KST,
            "before": "2026-09-07 17:41:00",
            "after": "2026-09-07 08:41:00",
        }
    ]


def test_revert_restores_original_value_and_removes_marker(app, tmp_path) -> None:
    """되돌리기 — 저널의 before 로 복원하고 표식을 지운다."""
    order = _make_order(
        deleted_at="2026-09-07 17:41:00", status="DELETED", original_status="RECEIVED"
    )
    journal = tmp_path / "run1.jsonl"
    run_backfill(db_session, apply=True, journal_path=str(journal))
    assert _reload(order.id).deleted_at == "2026-09-07 08:41:00"

    preview = run_revert(db_session, str(journal), apply=False)
    assert preview == {"mode": "revert-dry-run", "scanned": 1, "reverted": 1, "skipped": {}}
    assert _reload(order.id).deleted_at == "2026-09-07 08:41:00"

    summary = run_revert(db_session, str(journal), apply=True)

    assert summary == {"mode": "revert", "scanned": 1, "reverted": 1, "skipped": {}}
    restored = _reload(order.id)
    assert restored.deleted_at == "2026-09-07 17:41:00"
    assert BACKFILL_KEY not in restored.structured_data


def test_dry_run_and_apply_together_exit_2() -> None:
    """플래그 오용은 DB 를 열기 전에 exit 2 로 죽는다."""
    assert main(["--dry-run", "--apply"]) == 2


def test_tz_aware_iso_row_is_handed_to_a_human(app, tmp_path) -> None:
    """음성 대조군 (c) — 오프셋이 붙은 ISO 행은 자동 보정하지 않고 사람에게 넘긴다.

    ``fromisoformat`` 뒤 ``replace(tzinfo=None)`` 은 오프셋을 말없이 버린다 —
    ``+09:00`` 행이면 KST 벽시계를 UTC 라고 다시 적어 9시간 오차를 영구히 못박는다.
    운영 28건은 전부 naive 라 지금은 안 터지지만, 잠재 결함을 빨강으로 고정한다.
    """
    order = _make_order(
        deleted_at="2026-09-07T17:41:00+09:00", status="DELETED", original_status="DRAFT"
    )
    journal = tmp_path / "run1.jsonl"

    summary = run_backfill(db_session, apply=True, journal_path=str(journal))

    assert summary["changed"] == 0
    assert summary["markers"][MARKER_ISO] == {"scanned": 1, "changed": 0, "skipped": 1}
    assert summary["skipped"] == {f"{MARKER_ISO}:tz_aware": 1}
    saved = _reload(order.id)
    assert saved.deleted_at == "2026-09-07T17:41:00+09:00"  # 한 글자도 안 바뀐다
    assert BACKFILL_KEY not in saved.structured_data
    assert _journal_lines(journal) == []


def test_rerun_refuses_to_overwrite_the_journal(app, tmp_path) -> None:
    """음성 대조군 (d) — 같은 저널 경로로 두 번 돌리면 막히고 1회차 행이 그대로 남는다.

    되돌리기 자료가 이 파일 하나뿐인데 2회차는 멱등이라 ``changed=0`` 이다.
    ``"w"`` 로 열었다면 그 0행 실행이 1회차 원값을 0바이트로 잘라 영구히 날린다 —
    그래서 **파일이 비지 않았는지**까지 봐야 대조군이다.
    """
    order = _make_order(
        deleted_at="2026-09-07 17:41:00", status="DELETED", original_status="RECEIVED"
    )
    journal = tmp_path / "run1.jsonl"

    run_backfill(db_session, apply=True, journal_path=str(journal))
    first_rows = _journal_lines(journal)
    assert len(first_rows) == 1

    with pytest.raises(FileExistsError):
        run_backfill(db_session, apply=True, journal_path=str(journal))

    assert _journal_lines(journal) == first_rows
    assert first_rows[0]["before"] == "2026-09-07 17:41:00"
    assert first_rows[0]["order_id"] == order.id


def test_main_exits_2_when_journal_already_exists(tmp_path, monkeypatch) -> None:
    """CLI 는 저널 덮어쓰기를 exit 2 로 막고 기존 파일을 건드리지 않는다."""
    journal = tmp_path / "run1.jsonl"
    journal.write_text('{"order_id": 1}' + "\n", encoding="utf-8")

    def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """run_backfill 대신 저널 충돌만 재현한다(DB 를 태우지 않는다)."""
        raise FileExistsError(17, "File exists", str(journal))

    monkeypatch.setattr(backfill_tool, "run_backfill", _boom)

    assert backfill_tool.main(["--journal", str(journal)]) == 2
    assert journal.read_text(encoding="utf-8") == '{"order_id": 1}' + "\n"
