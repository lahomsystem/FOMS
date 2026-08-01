"""channel key runtime bridge — 활성/dual-accept key 복호화 + rewrap 실행 (CHANNEL-INBOUND-ORDER-01).

worker 가 receipt secret 을 봉인/해제할 때 이 모듈로 활성 channel key material 을 얻는다.
AUTH-ACCOUNT-01 ``auth_rate/key_state.py`` 의 dual-accept 원칙과 동형이다:

* ACTIVE 이면 active key 하나만 accept.
* ROTATING grace 동안은 active(새) + previous(구) 를 함께 accept(dual accept) — 아직 rewrap
  되지 않은 구 key 봉인 secret 도 해제할 수 있다.

key material 은 요청 처리 중 메모리로만 다루고 로그/응답에 남기지 않는다(fingerprint 만 노출).
rewrap(:func:`rewrap_previous_key_references`)이 모든 구 key 참조를 새 key 로 옮긴 뒤에야
:func:`state_ops.key_rotation_finalize` 가 구 key 를 제거할 수 있다.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from foms.services.security.channel_order import crypto
from foms.services.datetime_kst import now_utc_naive
from models import ChannelInboundEventLog, ChannelInboundKeyState

_LIVE_MODES = ("ACTIVE", "ROTATING")


def _decrypt_slot(row: ChannelInboundKeyState, master: bytes, slot: str) -> bytes:
    """row 의 ``{slot}_key_id``/``{slot}_key_ciphertext`` 를 복호화해 material 반환."""
    key_id = getattr(row, f"{slot}_key_id")
    ciphertext = getattr(row, f"{slot}_key_ciphertext")
    envelope = json.loads(ciphertext)
    return crypto.decrypt_key_material(envelope, master, key_id=key_id)


def active_key(
    row: ChannelInboundKeyState, master: bytes
) -> "Optional[tuple[bytes, str]]":
    """활성 channel key ``(material, key_id)``. ACTIVE/ROTATING 이 아니면 None."""
    if row.mode not in _LIVE_MODES or not row.active_key_id:
        return None
    return _decrypt_slot(row, master, "active"), row.active_key_id


def accepted_keys(
    row: ChannelInboundKeyState, master: bytes, *, now: Optional[Any] = None
) -> "list[tuple[bytes, str]]":
    """지금 accept 되는 ``(material, key_id)`` 리스트(fail-closed 복호화).

    ``[active]`` (ACTIVE), ``[active, previous]`` (ROTATING grace 내 dual accept).
    """
    active = active_key(row, master)
    if active is None:
        return []
    keys = [active]
    now = now or now_utc_naive()
    if (
        row.mode == "ROTATING"
        and row.previous_key_id
        and row.previous_key_ciphertext
        and (row.previous_not_after is None or row.previous_not_after > now)
    ):
        keys.append((_decrypt_slot(row, master, "previous"), row.previous_key_id))
    return keys


def count_previous_key_references(session: Session, row: ChannelInboundKeyState) -> int:
    """구 key(현 active generation 미만)를 아직 참조하는 봉인 receipt 수.

    rewrap 이 완료되면 0 이 되어 finalize 가 허용된다. active generation 미만인 모든 stale
    generation 을 세므로 다중 rotation 에도 안전한 superset guard 다.
    """
    active_gen = row.generation or 0
    return int(
        session.query(func.count(ChannelInboundEventLog.id))
        .filter(
            ChannelInboundEventLog.sealed_secret.isnot(None),
            ChannelInboundEventLog.key_generation.isnot(None),
            ChannelInboundEventLog.key_generation < active_gen,
        )
        .scalar()
        or 0
    )


def rewrap_previous_key_references(
    session: Session, row: ChannelInboundKeyState, master: bytes, *, batch_size: int = 500
) -> int:
    """구 key 로 봉인된 receipt secret 을 활성 key 로 재봉인하고 key_generation 을 올린다.

    ROTATING grace 동안 호출한다(active/previous 둘 다 복호화 가능). 한 배치를 재봉인하고
    남은 참조 수를 반환한다(0 이면 finalize 가능). 호출자가 commit 을 소유한다.

    :raises ChannelKeyStateError 계열: mode 가 ROTATING 이 아니거나 key 복호화 실패(fail-closed).
    """
    from foms.services.security.channel_order.state_ops import ChannelKeyStateError

    if row.mode != "ROTATING" or not row.active_key_id or not row.previous_key_id:
        raise ChannelKeyStateError("rewrap requires ROTATING mode with active+previous keys.")
    active_mat = _decrypt_slot(row, master, "active")
    previous_mat = _decrypt_slot(row, master, "previous")
    active_gen = row.generation or 0

    stale = (
        session.query(ChannelInboundEventLog)
        .filter(
            ChannelInboundEventLog.sealed_secret.isnot(None),
            ChannelInboundEventLog.key_generation.isnot(None),
            ChannelInboundEventLog.key_generation < active_gen,
        )
        .order_by(ChannelInboundEventLog.id.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .all()
    )
    for receipt in stale:
        envelope = json.loads(receipt.sealed_secret)
        rewrapped = crypto.rewrap_secret(
            envelope, previous_mat, active_mat,
            old_key_id=row.previous_key_id, new_key_id=row.active_key_id,
        )
        receipt.sealed_secret = json.dumps(rewrapped, sort_keys=True, separators=(",", ":"))
        receipt.key_generation = active_gen
    session.flush()
    return count_previous_key_references(session, row)
