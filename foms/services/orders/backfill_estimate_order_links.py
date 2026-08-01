"""topology-aware V1→V2 estimate/order link backfill (WDC-LINK-BACKFILL-00, §5.2 line 1040).

:mod:`~foms.services.orders.audit_estimate_order_links` 가 SAFE(unique pair)로 분류한 legacy
``EstimateOrderMatch`` pair 를 canonical :class:`~models.EstimateOrderLinkV2` 로 발급한다. 위상
(topology)에 따라 게이트가 다르다(§8.2):

* **SAME_DATABASE**: 한 SQLAlchemy transaction 이 정답이라 freeze 가 없다. online 으로(다운타임
  0) SAFE pair 를 V2 로 채운다(atomic dual-write/backfill — V1 은 원자적으로 그대로, V2 를 batch
  당 한 tx 로 정합화). fence 상태기계를 쓰지 않는다.
* **SEPARATE_DATABASE**: WDC DB 의 fence(:mod:`foms.services.security.cutover.wdc_link_fence`)가
  ``FROZEN`` 일 때만 apply 한다. LEGACY/CANONICAL/미seed 면 거부한다(**unfrozen apply 금지**).

**phase conflation 금지**: run phase 를 위상별로 분리한다(``V2_BACKFILL_SAME`` /
``V2_BACKFILL_SEPARATE``). ``run_id = SHA256(LP(packet_id, phase, manifest_sha256,
mapping_sha256))`` 이므로 같은 audit 라도 위상이 다르면 run_id 가 다르고, 암호화 artifact 의
DPAPI entropy·GCM AAD 도 phase 를 바인딩해 SAME↔SEPARATE 산출물이 서로 복호화되지 않는다.

**V1/meta cleanup 0**: 이 모듈은 V1 ``estimate_order_matches`` 를 **읽기만** 하고 삭제/변경하지
않는다(legacy-visible V1 row 불변). V1 정리는 별도 packet(WDC-LINK-CLEANUP-01) 몫이다.

대량 apply 는 BACKFILL 공용 인프라 :mod:`foms.services.security.backfill.runs`
(lease/heartbeat/checkpoint/coverage/STOPPED_DRIFT)로 wrap 한다 — batch 별 V2 write +
checkpoint + heartbeat 를 target DB 한 tx 로 묶고, source pair fingerprint drift(중복 추가/삭제)
면 write 전에 정지한다. 암호화 artifact 는 :func:`write_link_artifact`/:func:`load_link_artifact`
가 DPAPI + AES-256-GCM 으로 조립·검증한다(plaintext/raw key 는 디스크/DB/argv 0).
"""
from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.audit_estimate_order_links import (
    PACKET_ID,
    AuditReport,
    LinkSnapshot,
    SafeTarget,
    _pair_source_sha,
    ambiguous_csv,
    audit_estimate_order_links,
    column_schema_sha256,
    parse_safe_csv,
    safe_csv,
)
from foms.services.security.backfill import crypto, manifest, runs
from foms.services.security.cutover.wdc_link_fence import (
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    begin_wdc_link_legacy_write,
)

# 게이트 분기에서 쓰는 fence topology 별칭(같은 값 — 가독성용).
_FENCE_TOPOLOGY_SAME = TOPOLOGY_SAME
_FENCE_TOPOLOGY_SEPARATE = TOPOLOGY_SEPARATE

# topology 별 RUN phase — phase conflation 을 run_id·crypto entropy 에서 구조적으로 차단한다.
PHASE_SAME = "V2_BACKFILL_SAME"
PHASE_SEPARATE = "V2_BACKFILL_SEPARATE"
_PHASE_BY_TOPOLOGY: Dict[str, str] = {
    _FENCE_TOPOLOGY_SAME: PHASE_SAME,
    _FENCE_TOPOLOGY_SEPARATE: PHASE_SEPARATE,
}

# 암호화 artifact 파일(모두 artifact_dir 아래). ambiguous.csv.enc 는 manifest payload allowlist 이름.
KEY_ENVELOPE_FILE = "key-envelope.json"
SAFE_ENC_FILE = "safe.csv.enc"
MANUAL_ENC_FILE = "ambiguous.csv.enc"
MANIFEST_FILE = "manifest.json"
SHA_FILE = "sha.txt"
APPROVAL_SCOPE_FILE = "approval-scope.json"
SUMMARY_FILE = "summary.json"


class WDCLinkBackfillError(RuntimeError):
    """topology 게이트 위반(SEPARATE unfrozen apply·미seed·알 수 없는 topology)."""


class LinkArtifactError(RuntimeError):
    """artifact 조립/검증 계약 위반(무결성·바인딩 실패)."""


def phase_for_topology(topology: str) -> str:
    """topology → RUN phase(``V2_BACKFILL_SAME`` | ``V2_BACKFILL_SEPARATE``).

    :raises WDCLinkBackfillError: 알 수 없는 topology(phase conflation 방어).
    """
    try:
        return _PHASE_BY_TOPOLOGY[topology]
    except KeyError:
        raise WDCLinkBackfillError(
            f"unknown topology {topology!r} (one of {sorted(_PHASE_BY_TOPOLOGY)})."
        )


def assert_backfill_gate(fence_session: Session, topology: str) -> None:
    """apply 전 위상 게이트. SAME 은 통과, SEPARATE 은 fence ``FROZEN`` 을 강제한다.

    Args:
        fence_session: SEPARATE 위상 fence(``wdc_link_runtime_state``) 를 읽는 세션.
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`.

    Raises:
        WDCLinkBackfillError: SEPARATE 인데 fence 가 FROZEN 이 아니거나 미seed(unfrozen apply
            금지), 또는 알 수 없는 topology.
    """
    if topology == _FENCE_TOPOLOGY_SAME:
        return  # 한 tx / no-freeze — 상태기계를 쓰지 않는다.
    if topology != _FENCE_TOPOLOGY_SEPARATE:
        raise WDCLinkBackfillError(
            f"unknown topology {topology!r} (one of "
            f"{[_FENCE_TOPOLOGY_SAME, _FENCE_TOPOLOGY_SEPARATE]})."
        )
    # SEPARATE: singleton 을 잠그고 mode 를 읽는다(미seed 면 fence 가 예외 → 미프로비저닝 거부).
    from foms.services.security.cutover.wdc_link_fence import WDCLinkFenceError

    try:
        state = begin_wdc_link_legacy_write(fence_session)
    except WDCLinkFenceError as exc:
        raise WDCLinkBackfillError(
            "SEPARATE backfill requires a seeded FROZEN fence (singleton absent)."
        ) from exc
    if not state.is_frozen:
        raise WDCLinkBackfillError(
            f"SEPARATE backfill apply requires FROZEN fence (got mode={state.mode!r}); "
            "unfrozen apply is forbidden."
        )


# --------------------------------------------------------------------------- #
# 암호화 artifact (DPAPI key-envelope + AES-256-GCM payload) — phase 바인딩
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoadedArtifact:
    """복호화·검증된 artifact 의 apply 입력.

    Attributes:
        safe_targets: SAFE pair 목록(:class:`~foms.services.orders.audit_estimate_order_links.SafeTarget`).
        topology: artifact 를 만든 위상(phase 로부터 역바인딩).
        manifest_sha256: run identity manifest sha(approval-scope 바인딩).
        mapping_sha256: run identity mapping sha.
        approval_scope: OPS approval 이 커밋하는 exact scope dict.
        masked_counts: 정수 카운트(PII 0).
    """

    safe_targets: List[SafeTarget]
    topology: str
    manifest_sha256: str
    mapping_sha256: str
    approval_scope: Dict[str, Any]
    masked_counts: Dict[str, int]


def write_link_artifact(
    artifact_dir: Path,
    report: AuditReport,
    *,
    topology: str,
    db_instance_id: str,
    expected_run_row_version: int = 1,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, str]:
    """audit 결과를 위상-바인딩 암호화 artifact 로 ``artifact_dir`` 에 기록한다(디렉터리 전제).

    DPAPI key-envelope + AES-256-GCM payload 의 entropy/AAD 가 packet/**phase**/db/dir 를
    바인딩하므로, SAME 산출물은 SEPARATE phase 로 복호화되지 않는다(phase conflation 차단).

    Args:
        artifact_dir: artifact 를 쓸 디렉터리(호출자가 protected root 하위로 검증·생성).
        report: :func:`~foms.services.orders.audit_estimate_order_links.audit_estimate_order_links` 결과.
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`(phase 로 매핑).
        db_instance_id: target DB 식별자(entropy·AAD 바인딩).
        expected_run_row_version: apply 시 소비할 run row_version(fresh run=1).
        now: 결정적 타임스탬프(테스트 주입).

    Returns:
        ``{"manifest_sha256", "mapping_sha256", "source_composite_sha256", "phase"}``.
    """
    phase = phase_for_topology(topology)
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name
    col_schema = column_schema_sha256()
    src_composite = report.source_composite_sha256()

    envelope, data_key = crypto.create_key_envelope(
        packet_id=PACKET_ID, phase=phase, db_instance_id=db_instance_id,
        artifact_dir_id=artifact_dir_id, now=now,
    )
    key_id = envelope["key_id"]

    for relative_path, plaintext in (
        (SAFE_ENC_FILE, safe_csv(report)),
        (MANUAL_ENC_FILE, ambiguous_csv(report)),
    ):
        payload_env = crypto.encrypt_payload(
            plaintext.encode("utf-8"), data_key, key_id=key_id,
            packet_id=PACKET_ID, phase=phase, relative_path=relative_path,
            db_instance_id=db_instance_id, source_fingerprint=src_composite,
            column_schema_sha256=col_schema,
        )
        _write_json(artifact_dir / relative_path, payload_env)

    manifest_dict = report.manifest_dict()
    manifest_dict["phase"] = phase  # 위상별 manifest 분리(추가 conflation 방어).
    (artifact_dir / MANIFEST_FILE).write_bytes(manifest.manifest_bytes(manifest_dict))
    (artifact_dir / SHA_FILE).write_text(manifest.sha_txt_contents(manifest_dict), encoding="utf-8")

    manifest_sha = manifest.compute_manifest_sha256(manifest_dict)
    mapping_sha = report.mapping_sha256()
    approval_scope = manifest.build_approval_scope(
        packet_id=PACKET_ID, phase=phase, manifest_sha256=manifest_sha, mapping_sha256=mapping_sha,
        db_instance_id=db_instance_id, source_composite_sha256=src_composite,
        expected_run_row_version=expected_run_row_version, masked_counts=report.masked_counts(),
    )
    _write_json(artifact_dir / APPROVAL_SCOPE_FILE, approval_scope)
    _write_json(artifact_dir / SUMMARY_FILE, {
        "packet_id": PACKET_ID, "phase": phase, "db_instance_id": db_instance_id,
        "column_schema_sha256": col_schema, "source_composite_sha256": src_composite,
        "masked_counts": report.masked_counts(),
        "generated_at": (now or now_utc_naive()).isoformat(),
    })
    _write_json(artifact_dir / KEY_ENVELOPE_FILE, envelope)

    return {
        "manifest_sha256": manifest_sha, "mapping_sha256": mapping_sha,
        "source_composite_sha256": src_composite, "phase": phase,
    }


def load_link_artifact(artifact_dir: Path, *, topology: str, db_instance_id: str) -> LoadedArtifact:
    """artifact 무결성을 검증하고 SAFE 대상 + approval-scope 를 복원한다(apply 입력).

    Args:
        artifact_dir: :func:`write_link_artifact` 가 기록한 디렉터리.
        topology: 산출 위상(phase 로 매핑) — 다른 위상 phase 면 entropy/AAD 불일치로 fail-closed.
        db_instance_id: target DB 식별자(envelope entropy·AAD 재계산).

    Returns:
        :class:`LoadedArtifact`.

    Raises:
        LinkArtifactError: manifest sha 불일치(변조) 또는 approval-scope 바인딩 불일치.
        crypto.BackfillCryptoError: DPAPI unwrap/GCM 인증 실패(다른 host/변조/phase drift).
    """
    phase = phase_for_topology(topology)
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name

    manifest_bytes = (artifact_dir / MANIFEST_FILE).read_bytes()
    sha_txt = (artifact_dir / SHA_FILE).read_text(encoding="utf-8").strip()
    disk_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if sha_txt != disk_manifest_sha:
        raise LinkArtifactError("sha.txt does not match manifest.json bytes (tampered artifact).")

    manifest_dict = json.loads(manifest_bytes.decode("utf-8"))
    col_schema = manifest_dict.get("column_schema_sha256")
    if manifest_dict.get("phase") != phase:
        raise LinkArtifactError(
            f"artifact phase {manifest_dict.get('phase')!r} != requested {phase!r} "
            "(topology/phase conflation)."
        )

    approval_scope = json.loads((artifact_dir / APPROVAL_SCOPE_FILE).read_text(encoding="utf-8"))
    if approval_scope.get("manifest_sha256") != disk_manifest_sha:
        raise LinkArtifactError("approval-scope manifest_sha256 does not bind on-disk manifest.")
    src_composite = approval_scope["source_composite_sha256"]

    envelope = json.loads((artifact_dir / KEY_ENVELOPE_FILE).read_text(encoding="utf-8"))
    data_key = crypto.load_data_key(
        envelope, packet_id=PACKET_ID, phase=phase,
        db_instance_id=db_instance_id, artifact_dir_id=artifact_dir_id,
    )
    safe_env = json.loads((artifact_dir / SAFE_ENC_FILE).read_text(encoding="utf-8"))
    safe_plaintext = crypto.decrypt_payload(
        safe_env, data_key, packet_id=PACKET_ID, phase=phase, relative_path=SAFE_ENC_FILE,
        db_instance_id=db_instance_id, source_fingerprint=src_composite,
        column_schema_sha256=col_schema,
    ).decode("utf-8")

    return LoadedArtifact(
        safe_targets=parse_safe_csv(safe_plaintext),
        topology=topology,
        manifest_sha256=approval_scope["manifest_sha256"],
        mapping_sha256=approval_scope["mapping_sha256"],
        approval_scope=approval_scope,
        masked_counts=dict(approval_scope.get("masked_counts") or {}),
    )


def _write_json(path: Path, obj: Any) -> None:
    """dict 를 UTF-8 JSON 으로 기록(안정적 key 순서)."""
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


# --------------------------------------------------------------------------- #
# runs.py-wrapped topology-aware apply
# --------------------------------------------------------------------------- #
@dataclass
class LinkBackfillReport:
    """backfill apply 결과 요약."""

    run_id: str = ""
    phase: str = ""
    topology: str = ""
    state: str = ""
    total_pairs: int = 0
    completed_rows: int = 0
    minted: int = 0
    skipped_existing: int = 0
    batches: int = 0
    stopped_drift: bool = False


def _chunks(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _batch_fingerprint(triples: List[Tuple[int, int, str]]) -> str:
    """(estimate_id, order_id, pair_sha) 목록의 결정적 fingerprint(batch drift 비교용)."""
    payload = json.dumps(sorted(triples), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _live_pair_sha(source_session: Session, link: LinkSnapshot) -> str:
    """현재 V1 의 이 pair 구성 row ids 로 재계산한 fingerprint(audit 대비 drift 감지)."""
    from wdcalculator_models import EstimateOrderMatch

    ids = [
        row[0]
        for row in source_session.query(EstimateOrderMatch.id).filter(
            EstimateOrderMatch.estimate_id == link.estimate_id,
            EstimateOrderMatch.order_id == link.order_id,
        ).all()
    ]
    return _pair_source_sha(link.estimate_id, link.order_id, tuple(sorted(ids)))


def _existing_pairs(session: Session, batch: List[LinkSnapshot]) -> set:
    """batch pair 중 이미 V2 에 있는 ``(estimate_id, order_id)`` 집합(멱등 resume)."""
    from models import EstimateOrderLinkV2

    keys = [(l.estimate_id, l.order_id) for l in batch]
    rows = session.query(
        EstimateOrderLinkV2.estimate_id, EstimateOrderLinkV2.order_id
    ).filter(
        tuple_(EstimateOrderLinkV2.estimate_id, EstimateOrderLinkV2.order_id).in_(keys)
    ).all()
    return {(e, o) for e, o in rows}


def _mint_batch(
    session: Session, batch: List[LinkSnapshot], *,
    topology: str, run_id: str, now: datetime.datetime, report: LinkBackfillReport,
) -> None:
    """batch SAFE pair 를 canonical V2 로 발급(멱등·source-target equivalence·V1 무접근).

    이미 V2 에 있는 pair 는 건너뛴다(resume). V1 은 읽지도 쓰지도 않는다 — 이 콜백은 target
    session 에만 write 한다(V1 cleanup 0·legacy-visible row 불변).
    """
    from models import EstimateOrderLinkV2

    existing = _existing_pairs(session, batch)
    for link in batch:
        if (link.estimate_id, link.order_id) in existing:
            report.skipped_existing += 1
            continue
        row = EstimateOrderLinkV2(
            estimate_id=link.estimate_id,
            order_id=link.order_id,
            source_topology=topology,
            source_match_id=link.source_match_id,
            backfill_run_id=run_id,
            linked_at=now,
        )
        # source-target equivalence: target pair == source pair(방어적 자기검증).
        assert (row.estimate_id, row.order_id) == (link.estimate_id, link.order_id)
        session.add(row)
        report.minted += 1
    session.flush()


def run_backfill(
    session: Session,
    *,
    topology: str,
    db_instance_id: str,
    owner_identity: str,
    audit: Optional[AuditReport] = None,
    source_session: Optional[Session] = None,
    batch_size: int = 100,
    now: Optional[datetime.datetime] = None,
    activate_approval: Optional[Callable[[Session, Any], None]] = None,
) -> LinkBackfillReport:
    """SAFE pair 를 위상별 게이트로 canonical V2 에 backfill 하고 coverage 100% 로 DONE 처리한다.

    Args:
        session: V2(및 SEPARATE fence)를 쓰는 target 세션(호출자가 batch 마다 commit).
        topology: :data:`TOPOLOGY_SAME`(no-freeze online) | :data:`TOPOLOGY_SEPARATE`(FROZEN 필수).
        db_instance_id: run identity 의 target DB 식별자.
        owner_identity: lease owner 식별자(원문 저장 0 — hash 만).
        audit: 미리 계산한 audit(없으면 ``source_session`` 에서 read-only 로 새로 audit).
        source_session: V1 을 읽는 세션(SAME=``session``, SEPARATE=WDC 세션). 기본은 ``session``.
        batch_size: batch 당 pair 수.
        now: 결정적 타임스탬프(테스트 주입).
        activate_approval: ensure_run 직후 approval seq≥1 을 활성화하는 훅(운영은
            ``runs.consume_backfill_apply``; 없으면 seq<1 이라 acquire_lease 가 거부).

    Returns:
        :class:`LinkBackfillReport` — run 상태·coverage·발급/멱등 skip 수.

    Raises:
        WDCLinkBackfillError: SEPARATE unfrozen apply 또는 알 수 없는 topology.
    """
    now = now or now_utc_naive()
    phase = phase_for_topology(topology)  # 알 수 없는 topology 면 여기서 거부(phase conflation 방어).
    source_session = source_session or session
    audit = audit or audit_estimate_order_links(source_session)
    safe = list(audit.safe_links)

    # 위상 게이트: SEPARATE 은 FROZEN fence 필수(unfrozen apply 금지). SAME 은 통과.
    assert_backfill_gate(session, topology)

    run = runs.ensure_run(
        session, packet_id=PACKET_ID, phase=phase, db_instance_id=db_instance_id,
        manifest_sha256=audit.manifest_sha256(), mapping_sha256=audit.mapping_sha256(),
        total_rows=len(safe), now=now,
    )
    run_id = run.run_id
    if activate_approval is not None:
        activate_approval(session, run)
    session.flush()

    report = LinkBackfillReport(
        run_id=run_id, phase=phase, topology=topology, total_pairs=len(safe),
    )
    raw_token, _ = runs.new_lease_token()
    runs.acquire_lease(
        session, run_id, owner_identity_hash=runs.owner_hash(owner_identity),
        raw_token=raw_token, now=now,
    )
    session.commit()

    for seq, batch in enumerate(_chunks(safe, batch_size), start=1):
        expected_fp = _batch_fingerprint([(l.estimate_id, l.order_id, l.pair_sha()) for l in batch])
        live_fp = _batch_fingerprint(
            [(l.estimate_id, l.order_id, _live_pair_sha(source_session, l)) for l in batch]
        )
        checkpoint = hashlib.sha256(
            f"{run_id}:{seq}:{sorted((l.estimate_id, l.order_id) for l in batch)}".encode("utf-8")
        ).hexdigest()
        outcome = runs.write_batch(
            session, run_id, raw_token=raw_token,
            expected_fingerprint=expected_fp, live_fingerprint=live_fp,
            batch_business_write=lambda s, b=batch: _mint_batch(
                s, b, topology=topology, run_id=run_id, now=now, report=report
            ),
            completed_delta=len(batch), batch_seq=seq, checkpoint_sha256=checkpoint, now=now,
        )
        session.commit()
        report.batches += 1
        if outcome.stopped_drift:
            report.stopped_drift = True
            report.state = "STOPPED_DRIFT"
            report.completed_rows = outcome.completed_rows
            return report

    completed = runs.complete_run(session, run_id, raw_token=raw_token, now=now)
    session.commit()
    report.state = completed.state
    report.completed_rows = completed.completed_rows or 0
    return report


__all__ = [
    "PHASE_SAME",
    "PHASE_SEPARATE",
    "TOPOLOGY_SAME",
    "TOPOLOGY_SEPARATE",
    "KEY_ENVELOPE_FILE",
    "SAFE_ENC_FILE",
    "MANUAL_ENC_FILE",
    "MANIFEST_FILE",
    "SHA_FILE",
    "APPROVAL_SCOPE_FILE",
    "SUMMARY_FILE",
    "WDCLinkBackfillError",
    "LinkArtifactError",
    "LoadedArtifact",
    "LinkBackfillReport",
    "phase_for_topology",
    "assert_backfill_gate",
    "write_link_artifact",
    "load_link_artifact",
    "run_backfill",
]
