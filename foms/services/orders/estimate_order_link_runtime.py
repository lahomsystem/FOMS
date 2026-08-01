"""WDC estimate↔order link 의 topology-aware 런타임 canonical reader/writer (WDC-LINK-01, §5.2 line 1041).

WDC-LINK-BACKFILL-00 이 **오프라인 대량**으로 legacy ``EstimateOrderMatch``(V1) → canonical
:class:`~models.EstimateOrderLinkV2`(V2) 를 채운다면, 이 모듈은 **런타임 request 시점**에 위상
(topology)과 cutover 진행도에 따라 read/write 경로를 고르는 정본이다. 두 위상 모두에서 marker
경계 전에는 V1 을 정본으로 읽고(canonical read 금지), 경계 뒤에만 V2 한 tx 로 전환한다.

* **SAME_DATABASE**(COMPATIBLE family — 한 DB·한 tx): 진행도는 generic
  ``feature_cutover_markers`` 의 ``WDC_LINK`` marker 로만 판정한다(:mod:`...cutover.transactional`
  의 ``begin_transactional_mode`` 재사용 — fence ``FOR KEY SHARE`` drain 계약).
  - **marker 전**: legacy(V1) read + **dual write**(V1·V2 한 tx). V2 는 shadow 로 warm 하게
    유지하되 **정본으로 읽지 않는다**.
  - **marker 뒤**: V2 **한 tx** read/write(V1 미기록).
* **SEPARATE_DATABASE**(WDC DB 분리): 진행도는 WDC DB 의 ``wdc_link_runtime_state`` 상태기계
  (:mod:`...cutover.wdc_link_fence` — ``LEGACY → FROZEN → CANONICAL``)로 판정한다.
  - **LEGACY**: legacy(V1) write/read(all-serving).
  - **FROZEN**: all-serving(V1) read, 새 write 는 drain·거부(503) — backfill 이 V2 를 채우는 창.
  - **CANONICAL**(primary ``WDC_LINK`` marker 뒤에만 도달): V2 **한 tx** read/write.

**불변식(엄격)**:

* **marker 전 canonical read/enable 금지** — 경계 전 read 는 항상 V1, ``reads_canonical`` False.
* **Order meta runtime write 0** — 이 모듈은 ``orders.structured_data`` 를 읽지도 쓰지도 않는다
  (link row 만 다룬다). legacy match/unmatch endpoint 의 ``meta.wdc_estimate_id`` 기록과 무관.
* **same-key 1(idempotent)** — 같은 ``(estimate_id, order_id)`` 재기록은 정확히 link 하나
  (V2 unique pair)로 접히고 중복 write 0. PC/mobile 어느 경로에서 불러도 같은 결과.
* **topology 바뀐 artifact 소비 금지** — 넘겨받은 topology 가 live fence 상태와 어긋나면
  (SAME 인데 SEPARATE singleton 존재·그 역, 또는 caller 가 준 fingerprint 불일치) 소비를
  거부한다(:class:`TopologyDriftError`).

session 규약은 backfill(WDC-LINK-BACKFILL-00)과 동일하다: ``session`` 이 V2 + fence/marker 를,
``wd_session`` 이 V1(``EstimateOrderMatch``)을 소유한다(기본 ``wd_session = session``). SAME 위상은
정의상 한 DB 이므로 ``wd_session`` 은 항상 ``session`` 이다.
"""
from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.security.cutover.transactional import begin_transactional_mode
from foms.services.security.cutover.wdc_link_fence import (
    STATE_CANONICAL,
    STATE_FROZEN,
    STATE_LEGACY,
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    WDC_LINK_FAMILY,
    WDC_LINK_STATE_ID,
    WDC_LINK_TOPOLOGIES,
    begin_wdc_link_legacy_write,
)

# read 정본 출처.
READ_SOURCE_LEGACY_V1 = "LEGACY_V1"
READ_SOURCE_CANONICAL_V2 = "CANONICAL_V2"

# write 경로.
WRITE_PATH_DUAL = "DUAL_V1_V2"          # SAME marker 전: V1+V2 한 tx.
WRITE_PATH_LEGACY_V1 = "LEGACY_V1"      # SEPARATE LEGACY: V1 만.
WRITE_PATH_CANONICAL_V2 = "CANONICAL_V2"  # marker/CANONICAL 뒤: V2 한 tx.


class WDCLinkRuntimeError(RuntimeError):
    """런타임 reader/writer 전제 위반(알 수 없는 topology·비양수 id·미seed fence)."""


class TopologyDriftError(WDCLinkRuntimeError):
    """넘겨받은 topology/fingerprint 가 live fence 상태와 어긋남(stale artifact 소비 거부)."""


class LinkWriteFrozenError(WDCLinkRuntimeError):
    """SEPARATE FROZEN 창에서 새 link write 거부(drain 중 — 호출자는 503)."""


# --------------------------------------------------------------------------- #
# rollout 상태 (rollout checker 결과)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LinkRolloutState:
    """현 fence 상태에서 파생한 read/write 경로 결정(rollout checker 산출).

    Attributes:
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`.
        fence_mode: SEPARATE 의 ``LEGACY|FROZEN|CANONICAL``; SAME 은 None.
        marker_present: canonical cutover 경계 도달 여부(SAME=marker, SEPARATE=CANONICAL).
        reads_canonical: read 를 V2 에서 하는가(marker 경계 뒤에만 True).
        writes_canonical: write 를 V2 한 tx 로 하는가(= ``reads_canonical``).
        dual_writes: SAME marker 전 V1·V2 dual write 창인가.
        legacy_writes_open: 새 legacy(V1) write 를 받는가(SAME marker 전 / SEPARATE LEGACY).
        writes_frozen: SEPARATE FROZEN — 새 write 를 drain·거부하는가.
        fingerprint: topology+경계+fence_mode 결정 fingerprint(artifact drift 감지 키).
    """

    topology: str
    fence_mode: Optional[str]
    marker_present: bool
    reads_canonical: bool
    writes_canonical: bool
    dual_writes: bool
    legacy_writes_open: bool
    writes_frozen: bool
    fingerprint: str

    @property
    def read_source(self) -> str:
        """정본 read 출처(:data:`READ_SOURCE_CANONICAL_V2` | :data:`READ_SOURCE_LEGACY_V1`)."""
        return READ_SOURCE_CANONICAL_V2 if self.reads_canonical else READ_SOURCE_LEGACY_V1


@dataclass(frozen=True)
class LinkReceipt:
    """link write 1건의 receipt(무마이그레이션 — 반환 정본, 지속 증거는 V2 row provenance).

    Attributes:
        estimate_id / order_id: 기록한 pair.
        topology: 기록 시 위상.
        write_path: :data:`WRITE_PATH_DUAL` | :data:`WRITE_PATH_LEGACY_V1` | :data:`WRITE_PATH_CANONICAL_V2`.
        idempotent_hit: 이미 존재해 신규 write 0(same-key 1) 인가.
        wrote_v1 / wrote_v2: 각 테이블에 실제 insert 했는가.
        v1_match_id: 이 pair 의 V1 ``estimate_order_matches.id``(dual/legacy 경로·기존 포함).
        v2_id: 이 pair 의 V2 ``estimate_order_links_v2.id``.
        fence_mode / marker_present: 판정에 쓴 fence 상태(경계 증거).
        fingerprint: 판정 시점 rollout fingerprint(drift 감지).
        at: 기록 시각(naive UTC).
    """

    estimate_id: int
    order_id: int
    topology: str
    write_path: str
    idempotent_hit: bool
    wrote_v1: bool
    wrote_v2: bool
    v1_match_id: Optional[int]
    v2_id: Optional[int]
    fence_mode: Optional[str]
    marker_present: bool
    fingerprint: str
    at: datetime.datetime


@dataclass(frozen=True)
class LinkReadResult:
    """order 의 link read 결과(topology-aware).

    Attributes:
        order_id: 조회 order.
        estimate_ids: 연결된 견적 id(오름차순·중복 제거).
        read_source: 정본 출처(V1/V2).
        fingerprint: 판정 시점 rollout fingerprint.
    """

    order_id: int
    estimate_ids: Tuple[int, ...]
    read_source: str
    fingerprint: str


# --------------------------------------------------------------------------- #
# 내부 상태 판독 (unlocked — rollout checker / read 경로)
# --------------------------------------------------------------------------- #
def _pos_int(value: object, field: str) -> int:
    """양의 정수만 통과(trust boundary — garbage link 발급 차단)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WDCLinkRuntimeError(f"{field} must be a positive int (got {value!r}).")
    return value


def _assert_topology(topology: str) -> None:
    if topology not in WDC_LINK_TOPOLOGIES:
        raise WDCLinkRuntimeError(
            f"unknown WDC link topology {topology!r} (one of {WDC_LINK_TOPOLOGIES})."
        )


def _separate_fence_mode(session: Session) -> Optional[str]:
    """SEPARATE fence(``wdc_link_runtime_state``) mode 를 lock 없이 읽는다(부재면 None)."""
    row = session.execute(
        text("SELECT mode FROM wdc_link_runtime_state WHERE id = :id"),
        {"id": WDC_LINK_STATE_ID},
    ).first()
    return row[0] if row is not None else None


def _same_marker_present(session: Session) -> bool:
    """generic ``feature_cutover_markers`` 의 ``WDC_LINK`` marker 존재 여부(lock 없이)."""
    return session.execute(
        text("SELECT 1 FROM feature_cutover_markers WHERE family = :f"),
        {"f": WDC_LINK_FAMILY},
    ).first() is not None


def _fingerprint(topology: str, marker_present: bool, fence_mode: Optional[str]) -> str:
    """topology+경계+fence_mode 의 결정적 fingerprint(artifact drift 감지 키)."""
    payload = json.dumps(
        {"topology": topology, "marker_present": marker_present, "fence_mode": fence_mode},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _derive_state(topology: str, marker_present: bool, fence_mode: Optional[str]) -> LinkRolloutState:
    """(topology, 경계, fence_mode) → read/write 경로 booleans(순수 파생)."""
    reads_canonical = marker_present
    dual_writes = topology == TOPOLOGY_SAME and not marker_present
    writes_frozen = topology == TOPOLOGY_SEPARATE and fence_mode == STATE_FROZEN
    if topology == TOPOLOGY_SAME:
        legacy_writes_open = not marker_present  # marker 전엔 dual(=legacy 포함), 뒤엔 V2 only.
    else:
        legacy_writes_open = fence_mode == STATE_LEGACY
    return LinkRolloutState(
        topology=topology,
        fence_mode=fence_mode,
        marker_present=marker_present,
        reads_canonical=reads_canonical,
        writes_canonical=reads_canonical,
        dual_writes=dual_writes,
        legacy_writes_open=legacy_writes_open,
        writes_frozen=writes_frozen,
        fingerprint=_fingerprint(topology, marker_present, fence_mode),
    )


def _guard_drift(topology: str, singleton_present: bool, expected_fingerprint: Optional[str],
                 fingerprint: str) -> None:
    """topology↔singleton 정합 + caller fingerprint 대조(어긋나면 소비 거부)."""
    if topology == TOPOLOGY_SAME and singleton_present:
        raise TopologyDriftError(
            "SAME topology requested but a SEPARATE wdc_link_runtime_state singleton is present "
            "(topology drift — refusing stale artifact)."
        )
    if topology == TOPOLOGY_SEPARATE and not singleton_present:
        raise TopologyDriftError(
            "SEPARATE topology requested but wdc_link_runtime_state singleton is absent "
            "(unseeded or topology drift — refusing stale artifact)."
        )
    if expected_fingerprint is not None and expected_fingerprint != fingerprint:
        raise TopologyDriftError(
            f"rollout fingerprint drift (expected {expected_fingerprint}, got {fingerprint}); "
            "refusing stale artifact."
        )


def resolve_rollout(
    session: Session, *, topology: str,
    wd_session: Optional[Session] = None,
    expected_fingerprint: Optional[str] = None,
) -> LinkRolloutState:
    """현 fence 상태를 lock 없이 읽어 read/write 경로를 파생한다(rollout checker).

    Args:
        session: V2 + fence/marker 를 소유하는 canonical 세션.
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`(deploy artifact 산출값).
        wd_session: V1 세션(경로 판정에는 미사용 — 시그니처 정합용). 기본 ``session``.
        expected_fingerprint: caller 가 든 artifact fingerprint(불일치면 drift 거부).

    Returns:
        :class:`LinkRolloutState`.

    Raises:
        TopologyDriftError: topology↔singleton 불일치 또는 fingerprint drift.
        WDCLinkRuntimeError: 알 수 없는 topology.
    """
    _assert_topology(topology)
    fence_mode = _separate_fence_mode(session)
    singleton_present = fence_mode is not None
    if topology == TOPOLOGY_SAME:
        marker_present = _same_marker_present(session)
        state = _derive_state(topology, marker_present, None)
    else:
        marker_present = fence_mode == STATE_CANONICAL
        state = _derive_state(topology, marker_present, fence_mode)
    _guard_drift(topology, singleton_present, expected_fingerprint, state.fingerprint)
    return state


# --------------------------------------------------------------------------- #
# read (topology-aware)
# --------------------------------------------------------------------------- #
def _read_v1_estimate_ids(wd_session: Session, order_id: int) -> Tuple[int, ...]:
    """order 의 V1 매칭 견적 id(중복 제거·오름차순 — legacy all-serving read)."""
    rows = wd_session.execute(
        text("SELECT DISTINCT estimate_id FROM estimate_order_matches WHERE order_id = :oid"),
        {"oid": order_id},
    ).all()
    return tuple(sorted(r[0] for r in rows))


def _read_v2_estimate_ids(session: Session, order_id: int) -> Tuple[int, ...]:
    """order 의 V2 canonical 견적 id(unique pair·오름차순)."""
    rows = session.execute(
        text("SELECT estimate_id FROM estimate_order_links_v2 WHERE order_id = :oid"),
        {"oid": order_id},
    ).all()
    return tuple(sorted(r[0] for r in rows))


def read_links(
    session: Session, order_id: int, *, topology: str,
    wd_session: Optional[Session] = None,
    expected_fingerprint: Optional[str] = None,
) -> LinkReadResult:
    """order 의 연결 견적을 topology-aware 로 읽는다(marker 전 canonical read 금지).

    marker/CANONICAL 경계 전에는 항상 V1 을 정본으로 읽는다 — V2 shadow row 가 있어도 소비하지
    않는다. 경계 뒤에만 V2 를 읽는다. PC/mobile 어느 호출자든 같은 fence 상태면 같은 결과.

    Args:
        session: V2 + fence/marker canonical 세션.
        order_id: 조회 order(양수).
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`.
        wd_session: V1 세션. 기본 ``session``.
        expected_fingerprint: artifact fingerprint(불일치면 drift 거부).

    Returns:
        :class:`LinkReadResult`.

    Raises:
        TopologyDriftError / WDCLinkRuntimeError: :func:`resolve_rollout` 와 동일.
    """
    order_id = _pos_int(order_id, "order_id")
    wd_session = wd_session if wd_session is not None else session
    state = resolve_rollout(
        session, topology=topology, wd_session=wd_session, expected_fingerprint=expected_fingerprint,
    )
    if state.reads_canonical:
        ids = _read_v2_estimate_ids(session, order_id)
    else:
        ids = _read_v1_estimate_ids(wd_session, order_id)
    return LinkReadResult(
        order_id=order_id, estimate_ids=ids, read_source=state.read_source,
        fingerprint=state.fingerprint,
    )


# --------------------------------------------------------------------------- #
# write (topology-aware · idempotent · Order meta 무접근)
# --------------------------------------------------------------------------- #
def _existing_v1_match_id(wd_session: Session, estimate_id: int, order_id: int) -> Optional[int]:
    """이 pair 의 V1 row id(중복 시 최소 — 결정적 provenance). 없으면 None."""
    row = wd_session.execute(
        text(
            "SELECT id FROM estimate_order_matches "
            "WHERE estimate_id = :e AND order_id = :o ORDER BY id LIMIT 1"
        ),
        {"e": estimate_id, "o": order_id},
    ).first()
    return row[0] if row is not None else None


def _existing_v2_id(session: Session, estimate_id: int, order_id: int) -> Optional[int]:
    """이 pair 의 V2 row id(unique pair). 없으면 None."""
    row = session.execute(
        text("SELECT id FROM estimate_order_links_v2 WHERE estimate_id = :e AND order_id = :o"),
        {"e": estimate_id, "o": order_id},
    ).first()
    return row[0] if row is not None else None


def _insert_v1(wd_session: Session, estimate_id: int, order_id: int) -> int:
    """V1 ``EstimateOrderMatch`` 발급(legacy write). 발급 id 반환."""
    from wdcalculator_models import EstimateOrderMatch

    m = EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id)
    wd_session.add(m)
    wd_session.flush()
    return m.id


def _insert_v2(session: Session, estimate_id: int, order_id: int, *, topology: str,
               source_match_id: Optional[int], now: datetime.datetime) -> int:
    """V2 canonical ``EstimateOrderLinkV2`` 발급(런타임 — backfill_run_id=None). 발급 id 반환."""
    from models import EstimateOrderLinkV2

    row = EstimateOrderLinkV2(
        estimate_id=estimate_id, order_id=order_id, source_topology=topology,
        source_match_id=source_match_id, backfill_run_id=None, linked_at=now,
    )
    session.add(row)
    session.flush()
    return row.id


def _commit_both(session: Session, wd_session: Session) -> None:
    """canonical 세션(+ 다른 객체면 V1 세션)을 commit(SAME 은 한 세션·한 tx)."""
    session.commit()
    if wd_session is not session:
        wd_session.commit()


def write_link(
    session: Session, estimate_id: int, order_id: int, *, topology: str,
    wd_session: Optional[Session] = None,
    now: Optional[datetime.datetime] = None,
    expected_fingerprint: Optional[str] = None,
) -> LinkReceipt:
    """estimate↔order link 를 topology-aware·idempotent 로 기록하고 receipt 를 반환한다.

    fence 를 locked read(``begin_transactional_mode`` / ``begin_wdc_link_legacy_write``)로 잡아
    marker 경계를 같은 tx 에서 판정한다. 경로별:

    * SAME marker 전 → dual write(V1+V2 한 tx). marker 뒤 → V2 한 tx.
    * SEPARATE LEGACY → V1. FROZEN → 거부(:class:`LinkWriteFrozenError`). CANONICAL → V2 한 tx.

    같은 pair 재기록은 신규 write 0(``idempotent_hit``). ``orders.structured_data`` 는 읽지도
    쓰지도 않는다(Order meta runtime write 0).

    Args:
        session: V2 + fence/marker canonical 세션.
        estimate_id / order_id: 기록 pair(양수).
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`.
        wd_session: V1 세션. SAME 은 강제로 ``session``(한 DB). 기본 ``session``.
        now: 결정적 타임스탬프(테스트 주입).
        expected_fingerprint: artifact fingerprint(불일치면 drift 거부·write 0).

    Returns:
        :class:`LinkReceipt`.

    Raises:
        LinkWriteFrozenError: SEPARATE FROZEN 창.
        TopologyDriftError / WDCLinkRuntimeError: topology drift / 전제 위반.
    """
    _assert_topology(topology)
    estimate_id = _pos_int(estimate_id, "estimate_id")
    order_id = _pos_int(order_id, "order_id")
    now = now or now_utc_naive()
    if topology == TOPOLOGY_SAME:
        wd_session = session  # SAME = 한 DB·한 tx.
    else:
        wd_session = wd_session if wd_session is not None else session

    if topology == TOPOLOGY_SAME:
        return _write_same(session, estimate_id, order_id, now=now,
                           expected_fingerprint=expected_fingerprint)
    return _write_separate(session, wd_session, estimate_id, order_id, now=now,
                           expected_fingerprint=expected_fingerprint)


def _write_same(session: Session, estimate_id: int, order_id: int, *,
                now: datetime.datetime, expected_fingerprint: Optional[str]) -> LinkReceipt:
    """SAME 위상 write(locked marker read → dual write 또는 V2 한 tx)."""
    if _separate_fence_mode(session) is not None:
        raise TopologyDriftError(
            "SAME topology but a SEPARATE fence singleton is present (topology drift)."
        )
    mode = begin_transactional_mode(session, WDC_LINK_FAMILY)  # fence FOR KEY SHARE + marker read.
    fp = _fingerprint(TOPOLOGY_SAME, mode.has_marker, None)
    if expected_fingerprint is not None and expected_fingerprint != fp:
        raise TopologyDriftError(
            f"rollout fingerprint drift (expected {expected_fingerprint}, got {fp}); refusing write."
        )
    if mode.has_marker:
        receipt = _apply_canonical_v2(
            session, estimate_id, order_id, topology=TOPOLOGY_SAME, now=now,
            fence_mode=None, marker_present=True, fingerprint=fp,
        )
    else:
        receipt = _apply_dual(session, estimate_id, order_id, now=now, fingerprint=fp)
    _commit_both(session, session)
    return receipt


def _write_separate(session: Session, wd_session: Session, estimate_id: int, order_id: int, *,
                    now: datetime.datetime, expected_fingerprint: Optional[str]) -> LinkReceipt:
    """SEPARATE 위상 write(locked fence read → LEGACY V1 / FROZEN 거부 / CANONICAL V2)."""
    if _separate_fence_mode(session) is None:
        raise TopologyDriftError(
            "SEPARATE topology but wdc_link_runtime_state singleton is absent "
            "(unseeded or topology drift — refusing write)."
        )
    state = begin_wdc_link_legacy_write(session)  # singleton FOR KEY SHARE + mode(부재면 예외).
    mode = state.mode
    marker_present = mode == STATE_CANONICAL
    fp = _fingerprint(TOPOLOGY_SEPARATE, marker_present, mode)
    if expected_fingerprint is not None and expected_fingerprint != fp:
        raise TopologyDriftError(
            f"rollout fingerprint drift (expected {expected_fingerprint}, got {fp}); refusing write."
        )
    if mode == STATE_FROZEN:
        raise LinkWriteFrozenError(
            "SEPARATE fence is FROZEN; new link writes are drained (503 — retry after CANONICAL)."
        )
    if mode == STATE_CANONICAL:
        receipt = _apply_canonical_v2(
            session, estimate_id, order_id, topology=TOPOLOGY_SEPARATE, now=now,
            fence_mode=mode, marker_present=True, fingerprint=fp,
        )
    else:  # STATE_LEGACY
        receipt = _apply_legacy_v1(
            wd_session, estimate_id, order_id, fence_mode=mode, fingerprint=fp, now=now,
        )
    _commit_both(session, wd_session)
    return receipt


def _apply_dual(session: Session, estimate_id: int, order_id: int, *,
                now: datetime.datetime, fingerprint: str) -> LinkReceipt:
    """SAME marker 전 dual write(V1+V2 한 tx·idempotent). V1 은 dedup provenance 로 V2 에 연결."""
    v1_id = _existing_v1_match_id(session, estimate_id, order_id)
    wrote_v1 = v1_id is None
    if wrote_v1:
        v1_id = _insert_v1(session, estimate_id, order_id)
    v2_id = _existing_v2_id(session, estimate_id, order_id)
    wrote_v2 = v2_id is None
    if wrote_v2:
        v2_id = _insert_v2(session, estimate_id, order_id, topology=TOPOLOGY_SAME,
                           source_match_id=v1_id, now=now)
    return LinkReceipt(
        estimate_id=estimate_id, order_id=order_id, topology=TOPOLOGY_SAME,
        write_path=WRITE_PATH_DUAL, idempotent_hit=not (wrote_v1 or wrote_v2),
        wrote_v1=wrote_v1, wrote_v2=wrote_v2, v1_match_id=v1_id, v2_id=v2_id,
        fence_mode=None, marker_present=False, fingerprint=fingerprint, at=now,
    )


def _apply_legacy_v1(wd_session: Session, estimate_id: int, order_id: int, *,
                     fence_mode: str, fingerprint: str, now: datetime.datetime) -> LinkReceipt:
    """SEPARATE LEGACY write(V1 만·idempotent). V2 미기록(canonical 아님)."""
    v1_id = _existing_v1_match_id(wd_session, estimate_id, order_id)
    wrote_v1 = v1_id is None
    if wrote_v1:
        v1_id = _insert_v1(wd_session, estimate_id, order_id)
    return LinkReceipt(
        estimate_id=estimate_id, order_id=order_id, topology=TOPOLOGY_SEPARATE,
        write_path=WRITE_PATH_LEGACY_V1, idempotent_hit=not wrote_v1,
        wrote_v1=wrote_v1, wrote_v2=False, v1_match_id=v1_id, v2_id=None,
        fence_mode=fence_mode, marker_present=False, fingerprint=fingerprint, at=now,
    )


def _apply_canonical_v2(session: Session, estimate_id: int, order_id: int, *,
                        topology: str, now: datetime.datetime, fence_mode: Optional[str],
                        marker_present: bool, fingerprint: str) -> LinkReceipt:
    """marker/CANONICAL 뒤 V2 한 tx write(idempotent·V1 미기록)."""
    v2_id = _existing_v2_id(session, estimate_id, order_id)
    wrote_v2 = v2_id is None
    if wrote_v2:
        v2_id = _insert_v2(session, estimate_id, order_id, topology=topology,
                           source_match_id=None, now=now)
    return LinkReceipt(
        estimate_id=estimate_id, order_id=order_id, topology=topology,
        write_path=WRITE_PATH_CANONICAL_V2, idempotent_hit=not wrote_v2,
        wrote_v1=False, wrote_v2=wrote_v2, v1_match_id=None, v2_id=v2_id,
        fence_mode=fence_mode, marker_present=marker_present, fingerprint=fingerprint, at=now,
    )


__all__ = [
    "TOPOLOGY_SAME",
    "TOPOLOGY_SEPARATE",
    "READ_SOURCE_LEGACY_V1",
    "READ_SOURCE_CANONICAL_V2",
    "WRITE_PATH_DUAL",
    "WRITE_PATH_LEGACY_V1",
    "WRITE_PATH_CANONICAL_V2",
    "WDCLinkRuntimeError",
    "TopologyDriftError",
    "LinkWriteFrozenError",
    "LinkRolloutState",
    "LinkReceipt",
    "LinkReadResult",
    "resolve_rollout",
    "read_links",
    "write_link",
]
