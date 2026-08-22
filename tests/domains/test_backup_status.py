"""백업 상황판 판정·심박 인증 테스트 (RESTORE-GUI-01 F7)."""

import datetime

import pytest

from foms.services.backup_status import (
    STALE_AFTER_HOURS,
    evaluate_backup_status,
    verify_heartbeat_signature,
)

_NOW = datetime.datetime(2026, 8, 20, 12, 0, 0)


def _beat(hours_ago: float) -> dict:
    """`hours_ago` 시간 전에 수신된 심박."""
    stamp = _NOW - datetime.timedelta(hours=hours_ago)
    return {
        "finished_at": stamp.isoformat(timespec="seconds") + "Z",
        "received_at": stamp.isoformat(timespec="seconds"),
        "key": "db/2026/08/foms_prod.dump.age",
        "size_bytes": 5_600_000,
        "sha256": "a" * 64,
        "toc_entries": 929,
    }


def test_missing_heartbeat_is_red():
    """심박이 없으면 빨강 — '한 번도 성공한 적 없음'은 정상이 아니다(2026-08-13~19 실제 상태)."""
    result = evaluate_backup_status(None, now=_NOW)
    assert result["state"] == "missing"


def test_fresh_heartbeat_is_ok():
    """최근 성공은 정상."""
    result = evaluate_backup_status(_beat(3), now=_NOW)
    assert result["state"] == "ok"
    assert result["age_hours"] == pytest.approx(3, abs=0.01)


def test_old_heartbeat_is_stale():
    """기준 시간을 넘기면 빨강 — 워크플로가 아예 돌지 않는 침묵도 이걸로 잡는다."""
    result = evaluate_backup_status(_beat(STALE_AFTER_HOURS + 1), now=_NOW)
    assert result["state"] == "stale"


def test_boundary_just_inside_is_ok():
    """기준 시간 직전은 정상(경계에서 깜빡이지 않게)."""
    assert evaluate_backup_status(_beat(STALE_AFTER_HOURS - 0.1), now=_NOW)["state"] == "ok"


def test_corrupt_timestamp_is_red():
    """시각을 못 읽으면 정상으로 넘기지 않는다."""
    result = evaluate_backup_status({"received_at": "not-a-time", "finished_at": ""}, now=_NOW)
    assert result["state"] == "missing"


def test_signature_fails_closed_without_secret(monkeypatch):
    """공유 비밀이 없으면 어떤 서명도 통과하지 못한다 — 열어 두면 누구나 '정상'을 써넣는다."""
    monkeypatch.delenv("FOMS_BACKUP_HEARTBEAT_SECRET", raising=False)
    assert verify_heartbeat_signature(b"{}", "deadbeef") is False


def test_signature_roundtrip(monkeypatch):
    """올바른 HMAC 만 통과한다."""
    import hashlib
    import hmac

    monkeypatch.setenv("FOMS_BACKUP_HEARTBEAT_SECRET", "s3cret")
    body = b'{"key":"db/x.dump.age"}'
    good = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert verify_heartbeat_signature(body, good) is True
    assert verify_heartbeat_signature(body, "0" * 64) is False
    assert verify_heartbeat_signature(b'{"key":"other"}', good) is False
