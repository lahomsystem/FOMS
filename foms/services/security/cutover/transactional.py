"""transactional mode helper (§8.2 line 1520).

business mutation 이 자기 transaction 시작 직후 fence 를 ``FOR KEY SHARE`` 로 잠그고
같은 tx 에서 marker 를 읽어 effective mode 를 판정하도록 하는 **재사용 helper**. lock 은
호출자의 tx 가 끝날 때까지(commit/rollback) 유지되며, 이 helper 는 commit 하지 않는다.

이 패킷은 **메커니즘만** 제공한다 — 실제 business mutation 을 이 mode 로 게이트하는 것은
각 family packet 몫이다. 여기서는 lock 획득 + marker read + effective mode 계산까지다.

계약(§8.2 line 1520):

* fence ``FOR KEY SHARE`` = 동시 business tx 간 공유(높은 throughput), mark 의
  ``FOR UPDATE`` 와 충돌 → mark 는 모든 in-flight business tx 가 끝날 때까지 대기(drain).
* marker read 는 **같은 tx** 에서 DB 를 직접 조회한다(process cache 0). marker 가 있으면
  effective mode 는 ``CUTOVER`` — 호출자는 legacy business commit 을 하지 않는다.
* DB fault / fence 행 부재는 예외를 던져 호출자가 business 변경 0 으로 503 하게 한다
  (marker DB 장애 때 legacy 로 fail-open 금지).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# effective mode literal.
MODE_OPEN = "OPEN"
MODE_DRAINING = "DRAINING"
MODE_CUTOVER = "CUTOVER"


class CutoverModeError(RuntimeError):
    """fence 행 부재 등 mode 판정 전 조건 위반(호출자는 business 변경 0 으로 처리)."""


@dataclass(frozen=True)
class CutoverModeState:
    """fence FOR KEY SHARE + marker read 결과(호출자 tx 가 lock 을 계속 보유)."""

    family: str
    fence_mode: str
    fence_generation: int
    fence_row_version: int
    has_marker: bool
    effective_mode: str
    minimum_compatibility_generation: Optional[int]
    cutover_generation: Optional[int]

    @property
    def is_cutover(self) -> bool:
        """marker 가 존재해 legacy business mutation 이 금지되는 상태인가."""
        return self.effective_mode == MODE_CUTOVER

    @property
    def accepts_new_business(self) -> bool:
        """새 affected business mutation 을 받아도 되는가(OPEN 만 True).

        DRAINING/CUTOVER 는 새 business 를 받지 않는다(각 family packet 이 503/hidden).
        """
        return self.effective_mode == MODE_OPEN


def begin_transactional_mode(session: Session, family: str) -> CutoverModeState:
    """호출자 tx 안에서 fence 를 ``FOR KEY SHARE`` 로 잠그고 marker 를 읽어 effective mode 반환.

    호출자는 이미 열린 transaction 을 가져야 하고, 이 함수 반환 뒤 business·receipt·event·
    outbox 를 같은 tx 에 commit 할 때까지 lock 을 유지한다(이 함수는 commit 하지 않는다).

    :param session: 호출자의 active SQLAlchemy Session(이 tx 에 lock 이 걸림).
    :param family: 15 family literal 중 하나.
    :returns: :class:`CutoverModeState` — fence mode/generation/row_version, marker 유무,
        effective mode.
    :raises CutoverModeError: fence 행이 없다(family 미seed / 알 수 없는 family).
    """
    fence = session.execute(
        text(
            "SELECT mode, generation, row_version "
            "FROM feature_cutover_fences WHERE family = :family "
            "FOR KEY SHARE"
        ),
        {"family": family},
    ).first()
    if fence is None:
        raise CutoverModeError(
            f"feature_cutover_fences has no row for family {family!r} "
            "(unknown family or unseeded); refusing business mutation."
        )

    marker = session.execute(
        text(
            "SELECT cutover_generation, minimum_compatibility_generation "
            "FROM feature_cutover_markers WHERE family = :family"
        ),
        {"family": family},
    ).first()

    fence_mode = fence[0]
    if marker is not None:
        effective_mode = MODE_CUTOVER
    elif fence_mode == MODE_DRAINING:
        effective_mode = MODE_DRAINING
    else:
        effective_mode = MODE_OPEN

    return CutoverModeState(
        family=family,
        fence_mode=fence_mode,
        fence_generation=fence[1],
        fence_row_version=fence[2],
        has_marker=marker is not None,
        effective_mode=effective_mode,
        minimum_compatibility_generation=(marker[1] if marker is not None else None),
        cutover_generation=(marker[0] if marker is not None else None),
    )
