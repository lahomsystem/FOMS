"""CHANNEL-PUSH-SLOT-01 동시 클릭 직렬화 PostgreSQL 계약 테스트 (PGTEST-00 lane).

`is_resend` 는 structured_data 에서 읽는데 판정과 기록 사이에 채널톡 HTTP 발송이
끼어 수 초가 열린다. 그 창에서 두 번째 클릭이 같은 "첫 발송"으로 통과하면 같은
메시지가 두 번 나가고 변경 내용 입력도 건너뛴다. 잠금이 실제 PostgreSQL 에서
- 같은 (주문, push 종류) 를 직렬화하고
- 다른 주문·다른 종류는 막지 않으며
- 트랜잭션이 끝나면 풀리는지
를 검증한다. `FOMS_TEST_DATABASE_URL` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from foms.api.channel.channel_integration import _try_claim_push_slot

ORDER_A = 940_001
ORDER_B = 940_002
KIND = "drawing_room"


def test_same_order_and_kind_is_serialized(pg_engine) -> None:
    """같은 주문·같은 종류의 두 번째 요청은 슬롯을 못 잡는다."""
    factory = sessionmaker(bind=pg_engine)
    first, second = factory(), factory()
    try:
        assert _try_claim_push_slot(first, ORDER_A, KIND) is True
        assert _try_claim_push_slot(second, ORDER_A, KIND) is False, (
            "동시 클릭 두 번째가 첫 발송으로 통과했다"
        )
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


def test_other_order_or_kind_is_not_blocked(pg_engine) -> None:
    """잠금은 (주문, 종류) 단위다 — 무관한 push 를 막으면 안 된다."""
    factory = sessionmaker(bind=pg_engine)
    first, second = factory(), factory()
    try:
        assert _try_claim_push_slot(first, ORDER_A, KIND) is True
        assert _try_claim_push_slot(second, ORDER_A, "measurement") is True
        second.rollback()
        assert _try_claim_push_slot(second, ORDER_B, KIND) is True
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()


def test_lock_releases_when_transaction_ends(pg_engine) -> None:
    """첫 요청 트랜잭션이 끝나면 다음 요청이 정상적으로 슬롯을 잡는다."""
    factory = sessionmaker(bind=pg_engine)
    first, second = factory(), factory()
    try:
        assert _try_claim_push_slot(first, ORDER_A, KIND) is True
        assert _try_claim_push_slot(second, ORDER_A, KIND) is False
        second.rollback()
        first.commit()  # 실제 경로에서는 push 이력 커밋 시점

        assert _try_claim_push_slot(second, ORDER_A, KIND) is True, (
            "트랜잭션이 끝났는데도 잠금이 남았다"
        )
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
