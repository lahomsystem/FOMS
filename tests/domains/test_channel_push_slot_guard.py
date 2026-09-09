"""동시 클릭 슬롯 가드의 dialect 분기·라우트 배선 계약.

PostgreSQL 자문 잠금 자체는 `tests/postgres/test_channel_push_slot_lock.py`
(PG 레인)에서 검증한다. 여기서는 자문 잠금이 없는 dialect 에서
- 조용히 삼키지 않고 사유를 로그로 남긴 뒤 통과하는지
- 5종 push 진입점 두 곳(수동·견적서)에 가드가 실제로 배선돼 있는지
를 본다.
"""
from __future__ import annotations

import inspect
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from foms.api.channel.channel_integration import (
    _PUSH_KIND_CONFIG,
    _PUSH_SLOT_BUSY_MESSAGE,
    _try_claim_push_slot,
    api_channel_push_manual,
    api_channel_push_estimate,
)


def _sqlite_session():
    """메모리 SQLite 세션을 만든다(자문 잠금 미지원 dialect 대역)."""
    return sessionmaker(bind=create_engine("sqlite://"))()


def test_non_postgres_passes_but_logs_the_reason(caplog) -> None:
    """자문 잠금이 없는 dialect 는 통과시키되 사실을 로그로 남긴다."""
    session = _sqlite_session()
    try:
        with caplog.at_level(logging.INFO):
            assert _try_claim_push_slot(session, 4035, "drawing_room") is True
    finally:
        session.close()

    assert any(
        "advisory lock 미지원" in record.getMessage() for record in caplog.records
    ), "fail-open 사유가 묵시적으로 삼켜졌다"


def test_kind_key_does_not_collide_across_push_kinds() -> None:
    """push 종류별 잠금 키가 서로 겹치면 무관한 push 가 막힌다."""
    import hashlib

    keys = {
        kind: int.from_bytes(
            hashlib.blake2s(kind.encode("utf-8"), digest_size=4).digest(),
            "big",
            signed=True,
        )
        for kind in list(_PUSH_KIND_CONFIG) + ["estimate"]
    }
    assert len(set(keys.values())) == len(keys), f"잠금 키 충돌: {keys}"


def test_both_push_entrypoints_claim_a_slot() -> None:
    """수동 push(4종)와 견적서 push 모두 판정 전에 슬롯을 잡는다."""
    for route in (api_channel_push_manual, api_channel_push_estimate):
        source = inspect.getsource(route)
        assert "_try_claim_push_slot" in source, f"{route.__name__} 에 가드가 없다"
        claim_at = source.index("_try_claim_push_slot")
        resend_at = source.index("is_resend = bool(prev_push")
        assert claim_at < resend_at, (
            f"{route.__name__}: is_resend 판정 뒤에 슬롯을 잡으면 경합 창이 그대로 남는다"
        )
        assert "409" in source, f"{route.__name__}: 슬롯 실패 응답 코드가 없다"


def test_busy_message_is_actionable() -> None:
    """차단 문구는 사용자가 다음에 뭘 할지 알 수 있어야 한다."""
    assert "다시 시도" in _PUSH_SLOT_BUSY_MESSAGE
