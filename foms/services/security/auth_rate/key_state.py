"""auth-rate key runtime bridge (AUTH-ACCOUNT-01).

anti-abuse rate limiter 가 요청마다 이 모듈로 활성 rate key 를 읽어 bucket 키를 서명한다.
signing runtime(``signing/signing_keys.py``)의 BRIDGE 원칙과 동형이다:

* **미engage**(env ``FOMS_AUTH_RATE_KEY_ENGAGED`` 부재) 또는 mode EMPTY/READY 이면
  bucket 키를 **byte-identical** 로 통과시킨다 — 상태기계 배포만으로 runtime 의미가 변하지
  않고 기존 rate bucket 이 강제 무효화되지 않는다(seed 외 runtime 의미 변경 0).
* engage + ACTIVE/ROTATING 이면 활성 key 로 bucket 을 HMAC 서명하고 generation 으로
  namespacing 한다. ROTATING grace 동안은 previous key 도 accept 집합에 포함해 dual accept
  한다(:func:`accepted_key_material`).

rate limiting 은 advisory(fail-open) 이므로 :func:`sign_rate_bucket` 은 어떤 오류에서도
예외를 던지지 않고 미서명 base 키로 폴백한다(로그 기록). key material 은 요청 처리 중
메모리로만 다루고 로그/응답에 남기지 않는다(fingerprint/generation 만 노출).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.auth_rate.crypto import (
    decrypt_key_material,
    resolve_master_key,
)

logger = logging.getLogger(__name__)

# presence engages the state machine at runtime (signing 의 FOMS_SIGNING_KEY_CURRENT 대응).
ENV_ENGAGED = "FOMS_AUTH_RATE_KEY_ENGAGED"

_LIVE_MODES = ("ACTIVE", "ROTATING")


def _engaged() -> bool:
    """cutover 가 시작돼 runtime 이 상태기계를 소비해야 하는가(env engage 플래그)."""
    return bool((os.environ.get(ENV_ENGAGED) or "").strip())


def _load_row():
    """auth-rate state singleton(id=1)을 요청 시점에 읽는다(process cache 0).

    :returns: :class:`~models.AuthRateKeyState` 또는 None(미seed).
    """
    from db import db_session  # 지연 import(app import 순환 회피).
    from models import AuthRateKeyState

    return db_session.query(AuthRateKeyState).filter(AuthRateKeyState.id == 1).one_or_none()


def _decrypt_slot(row, master: bytes, slot: str) -> bytes:
    """row 의 ``{slot}_key_id``/``{slot}_key_ciphertext`` 를 복호화해 material 반환."""
    key_id = getattr(row, f"{slot}_key_id")
    ciphertext = getattr(row, f"{slot}_key_ciphertext")
    envelope = json.loads(ciphertext)
    return decrypt_key_material(envelope, master, key_id=key_id)


def accepted_key_material(
    *,
    row: Any = None,
    master: Optional[bytes] = None,
    engaged: Optional[bool] = None,
    now: Optional[Any] = None,
) -> "list[bytes]":
    """지금 accept 되는 rate key material 리스트(fail-closed 복호화).

    반환: ``[]`` (미engage/EMPTY/READY), ``[active]`` (ACTIVE),
    ``[active, previous]`` (ROTATING grace 내 dual accept). 리스트 첫 원소가 서명 key.

    :param row: 명시 state row(테스트/ops). None 이면 db_session 에서 읽는다.
    :param master: 명시 master key. None 이면 env 에서 해석.
    :param engaged: 명시 engage 여부. None 이면 env 플래그.
    :raises AuthRateCryptoError: master 부재/복호화 실패(fail-closed).
    """
    is_engaged = _engaged() if engaged is None else engaged
    if not is_engaged:
        return []
    row = _load_row() if row is None else row
    if row is None or row.mode not in _LIVE_MODES:
        return []
    now = now or now_utc_naive()
    master = resolve_master_key() if master is None else master

    keys: "list[bytes]" = [_decrypt_slot(row, master, "active")]
    if (
        row.mode == "ROTATING"
        and row.previous_key_id
        and row.previous_key_ciphertext
        and (row.previous_not_after is None or row.previous_not_after > now)
    ):
        keys.append(_decrypt_slot(row, master, "previous"))
    return keys


def active_key_material(
    *,
    row: Any = None,
    master: Optional[bytes] = None,
    engaged: Optional[bool] = None,
    now: Optional[Any] = None,
) -> "Optional[bytes]":
    """서명에 쓰는 활성 rate key material(accepted 첫 원소), 없으면 None."""
    keys = accepted_key_material(row=row, master=master, engaged=engaged, now=now)
    return keys[0] if keys else None


def sign_rate_bucket(
    base_key: str,
    *,
    row: Any = None,
    master: Optional[bytes] = None,
    engaged: Optional[bool] = None,
) -> str:
    """rate-limit bucket base 키를 활성 rate key 로 서명(engage 시), 아니면 byte-identical.

    미engage/EMPTY/READY/미seed → base 키 그대로(BRIDGE, 강제 무효화 0). engage+활성 →
    ``g{generation}:{HMAC-SHA256(active, base)[:24]}``. rate limiting 은 advisory 이므로
    어떤 오류(master 부재·복호화 실패·DB 오류)에서도 예외 없이 base 로 fail-open 한다.

    ponytail: engage 순간 bucket namespace 가 바뀌어 그 시점 카운터가 리셋된다 — anti-abuse
              window(시간/일)는 ephemeral 이라 무해하다. 무중단 dual-bucket 평가가 필요하면
              limiter 를 key_func→dual-key 평가로 확장.
    """
    is_engaged = _engaged() if engaged is None else engaged
    if not is_engaged:
        return base_key  # BRIDGE: byte-identical (fast path, DB 접근 0).
    try:
        row = _load_row() if row is None else row
        if row is None or row.mode not in _LIVE_MODES:
            return base_key
        material = active_key_material(row=row, master=master, engaged=True)
        if material is None:
            return base_key
        mac = hmac.new(material, base_key.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return f"g{row.generation}:{mac}"
    except Exception as exc:  # noqa: BLE001
        # failopen: intentional — rate limiting 은 advisory. 서명 실패를 로그로 기록하고
        # 미서명 base 로 폴백(요청을 500 으로 깨지 않는다).
        logger.warning("auth-rate bucket signing failed, falling back to unsigned bucket: %s", exc)
        return base_key
