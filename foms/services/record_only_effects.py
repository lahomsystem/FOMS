"""배달할 일이 없는 outbox effect_type 의 handler (SIDEFX-RECORDONLY-01).

`domain_side_effect_outbox` 의 행이 전부 "나중에 무언가를 보낸다"는 뜻은 아니다. 어떤
effect_type 은 **기록·dedupe 그 자체가 목적**이라, 배달 시점에 할 일이 없다.

그런 행에 handler 를 안 붙이면 worker 가 :class:`~foms.services.sidefx_worker.NoHandlerError`
로 10회 재시도한 뒤 `DEAD` 로 쌓는다. 운영 실측(2026-09-02):

* `CHANNEL_PUSH_RECORDED` **1,188행 DEAD**(2026-08-03 이후 전량) + PENDING 2.
  같은 기간 `CHANNELTALK_PUSH` OrderEvent 는 1,190건 — **모든 푸시 행이 죽었다.**

기능 손실은 없었다. 채널톡 전송은 이 outbox 와 무관하게 이미 끝났고(전송이 먼저,
기록이 나중), 이력(`structured_data.channeltalk_push*`)과 OrderEvent 는 같은 트랜잭션에서
쓰인다. outbox 행이 하는 일은 **같은 send 를 두 번 기록하지 않게 막는 dedupe** 뿐이다
(`dedupe_key = CHANNEL_PUSH_RECORDED:<push_kind>:<order_id>:<message_id>`).

문제는 그 1,188행이 **진짜 실패를 덮는다**는 것이다. worker 로그가 NoHandlerError 로
가득 차면 정말 배달돼야 할 effect 의 실패가 그 안에 묻힌다.

그래서 "할 일 없음"을 **명시적으로 등록한다**. 등록을 빼먹어서 죽는 것과, 할 일이 없어서
바로 끝나는 것은 다른 상태여야 한다.
"""
from __future__ import annotations

import logging

from models import DomainSideEffectOutbox

_LOGGER = logging.getLogger("sidefx_record_only")

#: 채널톡 푸시 기록 행. 전송은 이 행이 만들어지기 전에 끝났고, 이력·OrderEvent 는 같은
#: tx 에 쓰였다. 이 행의 유일한 역할은 dedupe 다.
CHANNEL_PUSH_RECORDED_EFFECT_TYPE = "CHANNEL_PUSH_RECORDED"

#: 단계 전이가 남기는 행. **이쪽은 기록 전용이 아니라 소비자 미구현이다.**
#:
#: 전이 9곳(`order_transition_service.py:409` 등)이 이 행을 만들지만 받는 쪽이 없다.
#: 운영 실측(2026-09-08): DEAD 154행, 하루 약 6건 증가. 그리고 `notifications` 에 단계 전이
#: 유형은 **전 기간 0건** — 즉 알림이 유실된 것이 아니라 애초에 구현된 적이 없다
#: (2026-09-01 원장에서 같은 결론, 그때는 118행).
#:
#: 그래도 DEAD 로 쌓게 두면 `dead_count > 0` 이 굳어 준비 판정이 영구히 빨간불이 되고,
#: **진짜 배달 실패가 그 안에 묻힌다**(채널톡 1,188행에서 겪은 그대로다).
STAGE_NOTIFICATION_EFFECT_TYPE = "STAGE_NOTIFICATION"


def handle_record_only(row: DomainSideEffectOutbox) -> None:
    """기록 전용 outbox 행을 즉시 완료 처리한다(부수효과 0).

    Args:
        row: PROCESSING 으로 claim 된 outbox 행.

    Returns:
        None. 정상 반환이므로 worker 가 같은 tx 에서 `DONE` 으로 전이한다.

    아무것도 하지 않는 것이 **맞는** 동작이다. 이 handler 를 지우면 해당 effect_type 이
    다시 NoHandlerError → 재시도 10회 → DEAD 로 쌓인다.
    """
    _LOGGER.debug(
        "[sidefx] record-only effect (type=%s id=%s domain=%s) — nothing to deliver",
        row.effect_type, row.id, row.source_domain,
    )


def handle_unimplemented_consumer(row: DomainSideEffectOutbox) -> None:
    """소비자가 아직 없는 effect 행을 완료 처리한다(부수효과 0).

    :func:`handle_record_only` 와 **뜻이 다르다**. 저쪽은 "배달할 것이 원래 없다" 이고,
    이쪽은 "배달할 것이 있을 수도 있는데 받는 쪽을 아직 안 만들었다" 이다. 두 상태를 한
    함수로 뭉치면 나중에 소비자를 구현하는 사람이 차이를 못 본다.

    **소비자를 구현하면 이 등록을 반드시 걷어내라.** 안 걷으면 진짜 배달이 여기서 조용히
    끝난다. 등록 목록은 닫힌집합 계약(`tests/domains/test_sidefx_record_only_effects.py`)이
    지키므로, 새 handler 를 붙이면 그 테스트가 빨개져 이 문장을 다시 읽게 된다.

    Args:
        row: PROCESSING 으로 claim 된 outbox 행.

    Returns:
        None. 정상 반환이라 worker 가 `DONE` 으로 전이한다 — DEAD 소음이 사라진다.
    """
    _LOGGER.info(
        "[sidefx] consumer not implemented (type=%s id=%s domain=%s) — completing without delivery",
        row.effect_type, row.id, row.source_domain,
    )
