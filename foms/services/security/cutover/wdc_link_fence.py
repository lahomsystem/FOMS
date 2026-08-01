"""WDC link cutover fence (WDC-LINK-FENCE-00, SSOT §5.2 line 219 / §8.2 line 730-736).

CUTOVER-MODE-01 fence 체계 위에 WDC(WDCalculator) link migration 전용 fence 를 **additive**
로 얹는다. legacy ``EstimateOrderMatch`` / Order meta projection → canonical
``estimate_order_links_v2`` cutover 를 topology(``SAME_DATABASE`` | ``SEPARATE_DATABASE``)에
따라 게이트한다. 이 packet 은 **fence 정의만** 제공한다 — topology inspector artifact, 실
dual-write / backfill, freeze / canonical / abort CLI 는 WDC-LINK-BACKFILL-00 / WDC-LINK-01
하류 몫이다.

* ``SAME_DATABASE``: 한 SQLAlchemy transaction 이 정답이며 freeze 가 없다. CUTOVER-MODE-01 의
  generic ``WDC_LINK`` family fence + marker 만 쓰고 이 모듈의 상태기계는 쓰지 않는다.
* ``SEPARATE_DATABASE``: WDC DB 의 ``wdc_link_runtime_state`` singleton
  (``LEGACY → FROZEN → CANONICAL``)이 fence 다. 세 fence 연산이 상태를 전이한다:

  - ``WDC_LINK_FREEZE``    — ``LEGACY → FROZEN``. legacy writer(``FOR KEY SHARE``)를
    ``FOR UPDATE`` 로 drain 한 뒤 FROZEN 을 commit 하고 Order legacy-meta source fingerprint
    + consumer rollout artifact + prepared consumer generation 을 기록(crash-resume).
  - ``WDC_LINK_CANONICAL`` — ``FROZEN → CANONICAL``. primary ``WDC_LINK`` marker 이후에만
    (marker gate). 이후 V2 + receipt 만 WDC DB 한 tx 로 쓴다.
  - ``WDC_LINK_ABORT``     — ``FROZEN → LEGACY``, ``generation + 1``. primary marker 前
    failure-only 복구. source fingerprint drift 가 없을 때만(있으면 STOP / roll-forward only).

세 fence 는 WDC-LINK-FENCE-00 이 소유하는 ops-approval operation
(``WDC_LINK_FREEZE|ABORT|CANONICAL``, :data:`WDC_LINK_FENCES`)과 exact 일치한다(§4.4
closed-set). SEPARATE topology 에서 그 operation 은 ``db_mode=TARGET_RESERVED``(WDC DB 는
primary 에 대해 예약된 target)로 소비되고, SAME 은 이 상태기계를 쓰지 않으므로 예약 대상이
없다 — :func:`db_mode_for_topology` 참조.

fence 전이는 순수 DB 연산이며 commit 하지 않는다(호출자 CLI 가 approval 소비와 한 tx 에
commit). ``updated_by_admin_user_id`` 는 CLI 가 소비된 approval row 에서 복사해 전달하는
optional 값이다(CUTOVER-MODE-01 ``mark_cutover`` 의 ``approved_by_admin_user_id`` 와 동일
패턴). 이 packet 은 fence 정의만이라 seed / model / 전이 helper 까지만 소유한다.
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive

# generic WDC_LINK family(CUTOVER-MODE-01 15-family closed set 의 일원). 이 fence 는 그
# family 의 primary marker 를 canonical / abort 게이트로 재사용한다.
WDC_LINK_FAMILY = "WDC_LINK"

# WDC-LINK-FENCE-00 이 소유하는 세 ops-approval operation = fence 3종(closed set).
# foms.services.security.ops_approval_manifest.EXPECTED_OWNER_OPERATIONS["WDC-LINK-FENCE-00"]
# 과 exact 일치해야 하며 test 가 양방향 검증한다(§4.4 closed-set).
WDC_LINK_FENCES: tuple[str, ...] = (
    "WDC_LINK_FREEZE",
    "WDC_LINK_ABORT",
    "WDC_LINK_CANONICAL",
)

# SEPARATE topology 의 wdc_link_runtime_state.mode 상태(§8.2 line 734).
STATE_LEGACY = "LEGACY"
STATE_FROZEN = "FROZEN"
STATE_CANONICAL = "CANONICAL"
WDC_LINK_STATE_MODES: tuple[str, ...] = (STATE_LEGACY, STATE_FROZEN, STATE_CANONICAL)

# topology(§8.2 line 730). 각 deploy / production artifact 가 다시 산출한다.
TOPOLOGY_SAME = "SAME_DATABASE"
TOPOLOGY_SEPARATE = "SEPARATE_DATABASE"
WDC_LINK_TOPOLOGIES: tuple[str, ...] = (TOPOLOGY_SAME, TOPOLOGY_SEPARATE)

# ops-approval db_mode literal(foms_ops_approval_operations.json 과 동일).
DB_MODE_SAME = "SAME"
DB_MODE_TARGET_RESERVED = "TARGET_RESERVED"

# wdc_link_runtime_state singleton PK — 항상 1.
WDC_LINK_STATE_ID = 1


def db_mode_for_topology(topology: str) -> str:
    """topology → ops-approval db_mode. SEPARATE 만 ``TARGET_RESERVED``, SAME 은 ``SAME``.

    SEPARATE 에서 WDC DB 는 primary 에 대해 예약된 target(cross-DB RESERVED consume)이고,
    SAME 은 한 tx 이므로 예약 대상이 없다. 이 값은 ``foms_ops_approval_operations.json`` 의
    WDC_LINK operation seed 와 test 가 대조한다.

    :param topology: :data:`WDC_LINK_TOPOLOGIES` 중 하나.
    :returns: ``"TARGET_RESERVED"``(SEPARATE) 또는 ``"SAME"``(SAME).
    :raises ValueError: 알 수 없는 topology.
    """
    if topology == TOPOLOGY_SEPARATE:
        return DB_MODE_TARGET_RESERVED
    if topology == TOPOLOGY_SAME:
        return DB_MODE_SAME
    raise ValueError(f"unknown WDC link topology {topology!r} (one of {WDC_LINK_TOPOLOGIES}).")


class WDCLinkFenceError(RuntimeError):
    """fence 전이 전제(state / row_version / generation / marker / fingerprint) 위반(변화 0)."""


# --------------------------------------------------------------------------- #
# state read + seed
# --------------------------------------------------------------------------- #
_SELECT_STATE = (
    "SELECT mode, generation, row_version, prepared_consumer_generation, "
    "freeze_source_fingerprint, freeze_rollout_artifact_sha256 "
    "FROM wdc_link_runtime_state WHERE id = :id"
)


@dataclass(frozen=True)
class WDCLinkFenceState:
    """``wdc_link_runtime_state`` singleton 판독 결과(FOR KEY SHARE 시 호출자 tx 가 lock 보유)."""

    mode: str
    generation: int
    row_version: int
    prepared_consumer_generation: Optional[int]
    freeze_source_fingerprint: Optional[str]
    freeze_rollout_artifact_sha256: Optional[str]

    @property
    def accepts_new_legacy(self) -> bool:
        """legacy match / unmatch writer 가 새 legacy write 를 해도 되는가(LEGACY 만 True).

        FROZEN / CANONICAL 은 legacy writer 를 받지 않는다(match/unmatch 503, V2 만).
        """
        return self.mode == STATE_LEGACY

    @property
    def is_frozen(self) -> bool:
        return self.mode == STATE_FROZEN

    @property
    def is_canonical(self) -> bool:
        return self.mode == STATE_CANONICAL


def _row_to_state(row) -> WDCLinkFenceState:
    return WDCLinkFenceState(
        mode=row[0],
        generation=row[1],
        row_version=row[2],
        prepared_consumer_generation=row[3],
        freeze_source_fingerprint=row[4],
        freeze_rollout_artifact_sha256=row[5],
    )


def _lock_state(session: Session, lock: str) -> WDCLinkFenceState:
    """singleton 을 ``lock``(FOR KEY SHARE / FOR UPDATE)으로 잠그고 상태 반환(부재면 예외)."""
    row = session.execute(text(f"{_SELECT_STATE} {lock}"), {"id": WDC_LINK_STATE_ID}).first()
    if row is None:
        raise WDCLinkFenceError(
            "wdc_link_runtime_state singleton is absent "
            "(unseeded, or SAME_DATABASE topology which does not use this state machine)."
        )
    return _row_to_state(row)


def _wdc_link_marker_exists(session: Session) -> bool:
    """primary ``WDC_LINK`` feature-cutover marker(canonical / abort 게이트) 존재 여부."""
    return session.execute(
        text("SELECT 1 FROM feature_cutover_markers WHERE family = :f"),
        {"f": WDC_LINK_FAMILY},
    ).first() is not None


def _canonical(payload: dict) -> bytes:
    """연산 결과를 결정적 JSON bytes 로 직렬화(consume result_sha256 용, CUTOVER 와 동형)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seed_wdc_link_runtime_state(
    session: Session, *, now: Optional[datetime.datetime] = None,
) -> bool:
    """SEPARATE topology WDC DB 에 singleton(id=1, mode=LEGACY, generation=0) seed(idempotent).

    SAME topology 는 이 상태기계를 쓰지 않으므로 seed 하지 않는다(호출자 topology 판정 책임 —
    그래서 create_all / migration 은 auto-seed 하지 않는다). 이미 있으면 no-op. 미commit.

    :returns: 새로 insert 했으면 True, 이미 존재하면 False.
    """
    now = now or now_utc_naive()
    res = session.execute(
        text(
            "INSERT INTO wdc_link_runtime_state (id, mode, generation, row_version, updated_at) "
            "VALUES (:id, :mode, 0, 1, :now) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": WDC_LINK_STATE_ID, "mode": STATE_LEGACY, "now": now},
    )
    return res.rowcount == 1


def begin_wdc_link_legacy_write(session: Session) -> WDCLinkFenceState:
    """legacy writer 가 singleton 을 ``FOR KEY SHARE`` 로 잠그고 상태를 읽는다(§8.2 line 734).

    legacy match / unmatch writer 는 이 lock 을 Order DB legacy-meta commit 까지 보유해
    freeze 의 ``FOR UPDATE`` 와 충돌(drain)한다. LEGACY 가 아니면 writer 는 503(변화 0).
    이 함수는 commit 하지 않는다 — 호출자 tx 가 lock 을 계속 보유한다.

    :raises WDCLinkFenceError: singleton 부재(미seed / SAME topology 오용).
    """
    return _lock_state(session, "FOR KEY SHARE")


# --------------------------------------------------------------------------- #
# fence 전이 (LEGACY → FROZEN → CANONICAL / FROZEN → LEGACY)
# --------------------------------------------------------------------------- #
def freeze_wdc_link(
    session: Session, expected_version: int, *,
    freeze_source_fingerprint: str,
    freeze_rollout_artifact_sha256: str,
    prepared_consumer_generation: int,
    updated_by_admin_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """``LEGACY → FROZEN`` (WDC_LINK_FREEZE). ``FOR UPDATE`` 로 in-flight legacy writer 를
    drain 한 뒤 FROZEN 을 기록하고 source fingerprint(drift 감지 기준) + consumer rollout
    artifact + prepared consumer generation 을 남긴다(crash-resume). 미commit.

    :raises WDCLinkFenceError: mode!=LEGACY, primary marker 존재, row_version 불일치.
    """
    now = now or now_utc_naive()
    st = _lock_state(session, "FOR UPDATE")
    if _wdc_link_marker_exists(session):
        raise WDCLinkFenceError("primary WDC_LINK marker already exists; cannot freeze after cutover.")
    if st.mode != STATE_LEGACY:
        raise WDCLinkFenceError(f"WDC link fence mode must be LEGACY to freeze (got {st.mode!r}).")
    if st.row_version != expected_version:
        raise WDCLinkFenceError(
            f"state row_version mismatch (expected {expected_version}, got {st.row_version})."
        )

    new_version = st.row_version + 1
    session.execute(
        text(
            "UPDATE wdc_link_runtime_state SET mode='FROZEN', row_version=:nv, "
            "prepared_consumer_generation=:pcg, frozen_at=:now, "
            "freeze_source_fingerprint=:fp, freeze_rollout_artifact_sha256=:art, "
            "updated_at=:now, updated_by_admin_user_id=:uid WHERE id=:id"
        ),
        {
            "nv": new_version, "pcg": prepared_consumer_generation, "now": now,
            "fp": freeze_source_fingerprint, "art": freeze_rollout_artifact_sha256,
            "uid": updated_by_admin_user_id, "id": WDC_LINK_STATE_ID,
        },
    )
    return _canonical({
        "op": "freeze", "mode": STATE_FROZEN,
        "generation": st.generation, "row_version": new_version,
    })


def canonicalize_wdc_link(
    session: Session, expected_version: int, *,
    updated_by_admin_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """``FROZEN → CANONICAL`` (WDC_LINK_CANONICAL). primary ``WDC_LINK`` marker 이후에만
    (marker gate — marker 前 canonical read/enable 금지). 미commit.

    :raises WDCLinkFenceError: mode!=FROZEN, primary marker 부재, row_version 불일치.
    """
    now = now or now_utc_naive()
    st = _lock_state(session, "FOR UPDATE")
    if st.mode != STATE_FROZEN:
        raise WDCLinkFenceError(f"WDC link fence mode must be FROZEN to canonicalize (got {st.mode!r}).")
    if not _wdc_link_marker_exists(session):
        raise WDCLinkFenceError("primary WDC_LINK marker absent; canonicalize only after marker.")
    if st.row_version != expected_version:
        raise WDCLinkFenceError(
            f"state row_version mismatch (expected {expected_version}, got {st.row_version})."
        )

    new_version = st.row_version + 1
    session.execute(
        text(
            "UPDATE wdc_link_runtime_state SET mode='CANONICAL', row_version=:nv, "
            "updated_at=:now, updated_by_admin_user_id=:uid WHERE id=:id"
        ),
        {"nv": new_version, "now": now, "uid": updated_by_admin_user_id, "id": WDC_LINK_STATE_ID},
    )
    return _canonical({
        "op": "canonicalize", "mode": STATE_CANONICAL,
        "generation": st.generation, "row_version": new_version,
    })


def abort_wdc_link(
    session: Session, expected_version: int, *,
    expected_generation: int,
    expected_freeze_fingerprint: str,
    updated_by_admin_user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> bytes:
    """``FROZEN → LEGACY``, ``generation + 1`` (WDC_LINK_ABORT). primary marker 前 failure-only
    복구다. source fingerprint drift 가 없을 때만(있으면 STOP / roll-forward only). generation
    을 +1 하고 frozen_at / fingerprint / rollout 을 clear 해 재개 시 stale artifact 를
    무효화한다. 미commit.

    :raises WDCLinkFenceError: primary marker 존재(marker 뒤 abort 0), mode!=FROZEN,
        row_version / generation 불일치, freeze fingerprint drift.
    """
    now = now or now_utc_naive()
    st = _lock_state(session, "FOR UPDATE")
    if _wdc_link_marker_exists(session):
        raise WDCLinkFenceError(
            "primary WDC_LINK marker exists; abort is forbidden after cutover (roll-forward only)."
        )
    if st.mode != STATE_FROZEN:
        raise WDCLinkFenceError(f"WDC link fence mode must be FROZEN to abort (got {st.mode!r}).")
    if st.row_version != expected_version:
        raise WDCLinkFenceError(
            f"state row_version mismatch (expected {expected_version}, got {st.row_version})."
        )
    if st.generation != expected_generation:
        raise WDCLinkFenceError(
            f"state generation mismatch (expected {expected_generation}, got {st.generation})."
        )
    if st.freeze_source_fingerprint != expected_freeze_fingerprint:
        raise WDCLinkFenceError("freeze source fingerprint drift; abort STOP (roll-forward only).")

    new_version = st.row_version + 1
    new_generation = st.generation + 1
    session.execute(
        text(
            "UPDATE wdc_link_runtime_state SET mode='LEGACY', row_version=:nv, generation=:ng, "
            "prepared_consumer_generation=NULL, frozen_at=NULL, freeze_source_fingerprint=NULL, "
            "freeze_rollout_artifact_sha256=NULL, updated_at=:now, updated_by_admin_user_id=:uid "
            "WHERE id=:id"
        ),
        {"nv": new_version, "ng": new_generation, "now": now,
         "uid": updated_by_admin_user_id, "id": WDC_LINK_STATE_ID},
    )
    return _canonical({
        "op": "abort", "mode": STATE_LEGACY,
        "generation": new_generation, "row_version": new_version,
    })
