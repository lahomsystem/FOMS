"""primary-DB legacy retirement 준비 cleanup audit (WDC-LINK-CLEANUP-01, §5.2 line 1042).

WDC-LINK-BACKFILL-00 이 legacy ``EstimateOrderMatch``(V1) → canonical
:class:`~models.EstimateOrderLinkV2`(V2) 를 채우고, WDC-LINK-01 이 marker/CANONICAL 경계 뒤에
V2 를 정본으로 읽기 시작하면, **old generation**(V1 row + ``orders.structured_data.meta.
wdc_estimate_id`` 링크)은 언젠가 은퇴(retire)해야 한다. 이 모듈은 그 **은퇴 준비를 검증만**
한다 — 실제 삭제·drop 은 하지 않는다(마이그레이션 없음·verify only).

**엄격 불변식**:

* **marker/CANONICAL effective 뒤에만 유효** — canonical 이 effective 하지 않으면(marker 전)
  cleanup audit/run 은 거부한다(marker/state 전 cleanup 금지). :func:`assert_cleanup_gate`.
* **V2 checkpoint 확인** — V2 backfill run 이 DONE(checkpoint 존재)이어야 은퇴 준비 검증이
  의미를 가진다. 아니면 거부.
* **verify only(실 삭제 0)** — V1/Order meta/V2 어느 것도 삭제·변경하지 않는다. run 은
  :mod:`foms.services.security.backfill.runs` checkpoint 원장에만 batch 진행을 남기고 domain
  business write 는 no-op 다.
* **separate run/artifact(V2 재사용 금지)** — packet/phase 가 V2 backfill 과 달라(``WDC-LINK-
  CLEANUP-01`` / ``LEGACY_CLEANUP``) run_id·암호화 entropy·AAD 가 구조적으로 분리된다.
* **safe 만·ambiguous 는 보류** — legacy datum 이 canonical V2 에 있으면 VERIFIED(나중에 안전히
  은퇴 가능), 없으면 AMBIGUOUS 로 **보류**한다(자동 제거 금지·사람 검토).
* **old generation nonzero** — 은퇴 대상 legacy(V1 pair + Order meta 링크)가 0 이면 검증할
  것이 없다(잘못된 DB/topology 신호)므로 run 을 거부한다.

session 규약은 WDC-LINK-01 과 동일하다: ``session`` 이 V2 + fence/marker(canonical 판정)를,
``wd_session`` 이 V1(``EstimateOrderMatch``)을, ``foms_session`` 이 Order meta(``orders``)를
소유한다. SAME 위상은 한 DB 라 셋 다 ``session`` 이다(기본값).
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.audit_estimate_order_links import (
    _pos_int,
    audit_estimate_order_links,
)
from foms.services.orders.estimate_order_link_runtime import (
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    resolve_rollout,
)
from foms.services.security.backfill import crypto, manifest, runs

# 이 packet 은 V2 backfill(WDC-LINK-BACKFILL-00 / V2_BACKFILL_*)과 **다른** packet/phase 를
# 쓴다 — run_id = SHA256(LP(packet_id, phase, ...)) 이므로 run·암호화 artifact 가 구조적으로
# 분리되어 V2 run/artifact 재사용이 불가능하다(separate run/checkpoint/artifact).
PACKET_ID = "WDC-LINK-CLEANUP-01"
PHASE = "LEGACY_CLEANUP"
TOOL_VERSION = 1

# V2 population 증거로 확인할 backfill packet(그 DONE run 이 있어야 은퇴 준비 검증이 의미).
V2_BACKFILL_PACKET_ID = "WDC-LINK-BACKFILL-00"

# 분류 코드(closed set).
VERIFIED = "VERIFIED"    # canonical V2 에 대응 pair 존재 → 나중에 안전히 은퇴 가능.
AMBIGUOUS = "AMBIGUOUS"  # 대응 V2 없음 → 보류(자동 제거 금지·사람 검토).
CLASSIFICATIONS: Tuple[str, ...] = (VERIFIED, AMBIGUOUS)

# old-generation legacy datum 출처(closed set).
SOURCE_V1 = "V1_MATCH"        # legacy EstimateOrderMatch pair(V1 retirement 후보).
SOURCE_ORDER_META = "ORDER_META"  # orders.structured_data.meta.wdc_estimate_id 링크.
SOURCES: Tuple[str, ...] = (SOURCE_V1, SOURCE_ORDER_META)

# ambiguous 사유.
NO_CANONICAL_V2 = "NO_CANONICAL_V2"      # 대응 V2 pair 부재.
INVALID_META_ESTIMATE_ID = "INVALID_META_ESTIMATE_ID"  # Order meta 링크 값이 비양수/비정수.

# 암호화 artifact 파일(모두 artifact_dir 아래).
KEY_ENVELOPE_FILE = "key-envelope.json"
VERIFIED_ENC_FILE = "verified.csv.enc"
AMBIGUOUS_ENC_FILE = "ambiguous.csv.enc"
MANIFEST_FILE = "manifest.json"
SHA_FILE = "sha.txt"
APPROVAL_SCOPE_FILE = "approval-scope.json"
SUMMARY_FILE = "summary.json"

# CSV 컬럼 스키마(AAD 바인딩용 — 고정 문자열, PII 0).
_VERIFIED_COLUMNS: Tuple[str, ...] = ("source", "estimate_id", "order_id", "provenance_id", "item_sha")
_AMBIGUOUS_COLUMNS: Tuple[str, ...] = (
    "source", "estimate_id", "order_id", "provenance_id", "reason", "decision", "approved_by_user_id",
)


class WDCLinkCleanupError(RuntimeError):
    """cleanup 전제 위반(old generation 0·알 수 없는 topology 등)."""


class WDCLinkCleanupGateError(WDCLinkCleanupError):
    """marker/CANONICAL effective 또는 V2 checkpoint 전제 미충족(cleanup 거부·변화 0)."""


class CleanupArtifactError(RuntimeError):
    """artifact 조립/검증 계약 위반(무결성·바인딩 실패)."""


# --------------------------------------------------------------------------- #
# 분류 데이터 구조
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LegacyItem:
    """은퇴 후보 old-generation legacy datum 1건(read-only 스냅샷).

    Attributes:
        source: :data:`SOURCE_V1` | :data:`SOURCE_ORDER_META`.
        estimate_id: 견적 id(양수).
        order_id: 주문 id(양수).
        provenance_id: 근거 id(V1=최소 match id·ORDER_META=order id).
    """

    source: str
    estimate_id: int
    order_id: int
    provenance_id: int

    def item_sha(self) -> str:
        """이 item 의 결정적 source fingerprint(batch drift 비교 단위)."""
        return _item_source_sha(self.source, self.estimate_id, self.order_id, self.provenance_id)


@dataclass(frozen=True)
class AmbiguousItem:
    """canonical V2 에 대응이 없어 보류된 legacy datum(자동 제거 금지·사람 검토).

    Attributes:
        source: :data:`SOURCE_V1` | :data:`SOURCE_ORDER_META`.
        estimate_id: 원문 estimate_id(무결성 위반 값일 수 있음·None 가능).
        order_id: 주문 id.
        provenance_id: 근거 id.
        reason: :data:`NO_CANONICAL_V2` | :data:`INVALID_META_ESTIMATE_ID`.
    """

    source: str
    estimate_id: Optional[int]
    order_id: int
    provenance_id: int
    reason: str


def _item_source_sha(source: str, estimate_id: int, order_id: int, provenance_id: int) -> str:
    """(source, estimate_id, order_id, provenance_id) 의 결정적 sha256(drift 감지 단위)."""
    payload = json.dumps([source, estimate_id, order_id, provenance_id], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CleanupReport:
    """전체 old-generation 은퇴 준비 audit 요약(coverage 원장·read-only).

    Attributes:
        total_v1_pairs: SAFE V1 pair 수(dedup unique pair — V1 retirement 후보).
        total_order_meta_links: Order meta ``wdc_estimate_id`` 링크 수.
        verified: canonical V2 대응이 있는 legacy item(은퇴 안전·(source,estimate,order) 오름차순).
        ambiguous: 대응 V2 없음/무결성 위반으로 보류된 item.
    """

    total_v1_pairs: int = 0
    total_order_meta_links: int = 0
    verified: List[LegacyItem] = field(default_factory=list)
    ambiguous: List[AmbiguousItem] = field(default_factory=list)

    @property
    def old_generation_rows(self) -> int:
        """은퇴 대상 old-generation legacy 총수(V1 pair + Order meta 링크)."""
        return self.total_v1_pairs + self.total_order_meta_links

    @property
    def unclassified(self) -> int:
        """어느 bucket 에도 안 들어간 legacy 수(coverage 100% 이면 0)."""
        return self.old_generation_rows - len(self.verified) - len(self.ambiguous)

    @property
    def counts(self) -> Dict[str, int]:
        """bucket 카운트."""
        return {VERIFIED: len(self.verified), AMBIGUOUS: len(self.ambiguous)}

    def masked_counts(self) -> Dict[str, int]:
        """approval-scope masked 카운트(정수만·PII 0)."""
        return {
            "total_v1_pairs": self.total_v1_pairs,
            "total_order_meta_links": self.total_order_meta_links,
            "old_generation_rows": self.old_generation_rows,
            "verified_rows": len(self.verified),
            "ambiguous_rows": len(self.ambiguous),
        }

    def source_composite_sha256(self) -> str:
        """VERIFIED item source fingerprint 의 결정적 합성 sha256(전체 drift 감지)."""
        payload = json.dumps(
            [[i.source, i.estimate_id, i.order_id, i.provenance_id] for i in self.verified],
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def manifest_dict(self) -> Dict[str, Any]:
        """run identity manifest."""
        return {
            "packet_id": PACKET_ID,
            "phase": PHASE,
            "tool_version": TOOL_VERSION,
            "column_schema_sha256": column_schema_sha256(),
            "old_generation_rows": self.old_generation_rows,
            "verified_rows": len(self.verified),
            "ambiguous_rows": len(self.ambiguous),
            "source_composite_sha256": self.source_composite_sha256(),
        }

    def manifest_sha256(self) -> str:
        """manifest raw bytes 의 canonical sha256(run identity)."""
        return manifest.compute_manifest_sha256(self.manifest_dict())

    def mapping_sha256(self) -> str:
        """VERIFIED 은퇴 결정 목록의 canonical mapping sha256(legacy → RETIRE_SAFE)."""
        entries = [
            {
                "identity_fields": {"source": i.source, "estimate_id": i.estimate_id, "order_id": i.order_id},
                "decision": "RETIRE_SAFE",
                "target_ids": [i.provenance_id],
                "reason_code": i.source,
            }
            for i in self.verified
        ]
        return manifest.compute_mapping_sha256(entries)


def column_schema_sha256() -> str:
    """verified/ambiguous CSV 컬럼 스키마의 결정적 sha256(payload AAD 바인딩)."""
    payload = json.dumps({"verified": _VERIFIED_COLUMNS, "ambiguous": _AMBIGUOUS_COLUMNS}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# read (read-only) + 분류 코어
# --------------------------------------------------------------------------- #
def iter_order_meta_links(foms_session: Session) -> List[Tuple[int, Any]]:
    """모든 ``orders.structured_data.meta.wdc_estimate_id`` 링크 ``(order_id, raw_estimate)``.

    read-only — orders 를 읽기만 한다(Order meta write 0). JSONB null 값은 ``#>>`` 가 SQL
    NULL 로 접어 제외한다. order_id 오름차순.
    """
    rows = foms_session.execute(
        text(
            "SELECT id, (structured_data #>> '{meta,wdc_estimate_id}') "
            "FROM orders WHERE (structured_data #>> '{meta,wdc_estimate_id}') IS NOT NULL "
            "ORDER BY id"
        )
    ).all()
    return [(int(r[0]), r[1]) for r in rows]


def _v2_pair_set(session: Session) -> set:
    """canonical V2 의 모든 ``(estimate_id, order_id)`` 집합(멤버십 판정 — read-only)."""
    rows = session.execute(text("SELECT estimate_id, order_id FROM estimate_order_links_v2")).all()
    return {(int(e), int(o)) for e, o in rows}


def _parse_meta_estimate_id(raw: Any) -> Optional[int]:
    """Order meta ``wdc_estimate_id`` 텍스트를 양의 정수로 파싱(무결성 판정·아니면 None)."""
    try:
        return _pos_int(int(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def build_cleanup_report(
    v1_pairs: List[Tuple[int, int, int]],
    order_meta_links: List[Tuple[int, Any]],
    v2_pairs: set,
) -> CleanupReport:
    """legacy 후보를 canonical V2 멤버십으로 VERIFIED/AMBIGUOUS 분류한다(순수·DB 무접근).

    Args:
        v1_pairs: SAFE V1 ``(estimate_id, order_id, source_match_id)`` 목록(dedup unique pair).
        order_meta_links: ``(order_id, raw_estimate_id)`` 목록.
        v2_pairs: canonical V2 ``(estimate_id, order_id)`` 집합.

    Returns:
        :class:`CleanupReport` — coverage 100% 원장.
    """
    report = CleanupReport(total_v1_pairs=len(v1_pairs), total_order_meta_links=len(order_meta_links))
    for estimate_id, order_id, match_id in v1_pairs:
        if (estimate_id, order_id) in v2_pairs:
            report.verified.append(LegacyItem(SOURCE_V1, estimate_id, order_id, match_id))
        else:
            report.ambiguous.append(AmbiguousItem(SOURCE_V1, estimate_id, order_id, match_id, NO_CANONICAL_V2))
    for order_id, raw_estimate in order_meta_links:
        estimate_id = _parse_meta_estimate_id(raw_estimate)
        if estimate_id is None:
            report.ambiguous.append(
                AmbiguousItem(SOURCE_ORDER_META, None, order_id, order_id, INVALID_META_ESTIMATE_ID)
            )
        elif (estimate_id, order_id) in v2_pairs:
            report.verified.append(LegacyItem(SOURCE_ORDER_META, estimate_id, order_id, order_id))
        else:
            report.ambiguous.append(
                AmbiguousItem(SOURCE_ORDER_META, estimate_id, order_id, order_id, NO_CANONICAL_V2)
            )
    report.verified.sort(key=lambda i: (i.source, i.estimate_id, i.order_id))
    report.ambiguous.sort(key=lambda a: (a.source, a.order_id, a.provenance_id))
    return report


def audit_wdc_link_cleanup(
    session: Session, *, wd_session: Optional[Session] = None, foms_session: Optional[Session] = None,
) -> CleanupReport:
    """old-generation legacy(V1 SAFE pair + Order meta 링크)를 V2 대응으로 분류한다(mutation 0).

    Args:
        session: canonical V2 를 읽는 세션.
        wd_session: V1 ``estimate_order_matches`` 세션(기본 ``session``). read-only.
        foms_session: Order meta(``orders``) 세션(기본 ``session``). read-only.

    Returns:
        :class:`CleanupReport`.
    """
    wd_session = wd_session if wd_session is not None else session
    foms_session = foms_session if foms_session is not None else session
    v1_audit = audit_estimate_order_links(wd_session)
    v1_pairs = [(l.estimate_id, l.order_id, l.source_match_id) for l in v1_audit.safe_links]
    order_meta_links = iter_order_meta_links(foms_session)
    return build_cleanup_report(v1_pairs, order_meta_links, _v2_pair_set(session))


# --------------------------------------------------------------------------- #
# 게이트 (marker/CANONICAL effective + V2 checkpoint)
# --------------------------------------------------------------------------- #
def _v2_backfill_checkpoint_present(session: Session) -> bool:
    """V2 backfill(WDC-LINK-BACKFILL-00)의 DONE run 이 있어(checkpoint 원장 존재) V2 가 채워졌나."""
    row = session.execute(
        text(
            "SELECT 1 FROM maintenance_backfill_runs r "
            "JOIN maintenance_backfill_checkpoints c ON c.run_id = r.run_id "
            "WHERE r.packet_id = :p AND r.state = 'DONE' LIMIT 1"
        ),
        {"p": V2_BACKFILL_PACKET_ID},
    ).first()
    return row is not None


def assert_cleanup_gate(
    session: Session, *, topology: str, wd_session: Optional[Session] = None,
) -> None:
    """cleanup 전제 게이트. canonical effective + V2 checkpoint 가 아니면 거부(변화 0).

    Args:
        session: V2 + fence/marker canonical 세션.
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`(deploy artifact 산출값).
        wd_session: V1 세션(rollout 시그니처 정합용). 기본 ``session``.

    Raises:
        WDCLinkCleanupGateError: canonical 이 effective 하지 않음(marker/state 전) 또는 V2
            backfill checkpoint 부재.
        TopologyDriftError / WDCLinkRuntimeError: :func:`resolve_rollout` 위반(topology drift 등).
    """
    state = resolve_rollout(session, topology=topology, wd_session=wd_session)
    if not state.reads_canonical:
        raise WDCLinkCleanupGateError(
            "canonical is not effective (marker/CANONICAL absent); "
            "legacy cleanup is forbidden before cutover boundary."
        )
    if not _v2_backfill_checkpoint_present(session):
        raise WDCLinkCleanupGateError(
            "no DONE V2 backfill run/checkpoint; cleanup requires a populated canonical V2."
        )


# --------------------------------------------------------------------------- #
# separate 암호화 artifact (phase LEGACY_CLEANUP — V2 phase 와 비호환)
# --------------------------------------------------------------------------- #
def verified_csv(report: CleanupReport) -> str:
    """VERIFIED(은퇴 안전) item 을 CSV 로 직렬화(header 포함·PII 0 — id/해시만)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(_VERIFIED_COLUMNS))
    for i in report.verified:
        writer.writerow([i.source, i.estimate_id, i.order_id, i.provenance_id, i.item_sha()])
    return buf.getvalue()


def ambiguous_csv(report: CleanupReport) -> str:
    """보류(AMBIGUOUS) item 을 사람 검토 CSV 로 직렬화(자동 제거 0·decision=HOLD)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(_AMBIGUOUS_COLUMNS))
    for a in report.ambiguous:
        writer.writerow([
            a.source,
            "" if a.estimate_id is None else a.estimate_id,
            a.order_id,
            a.provenance_id,
            a.reason,
            "HOLD",  # decision: 보류(자동 제거 금지·사람 검토).
            "",      # approved_by_user_id: 검토 전.
        ])
    return buf.getvalue()


def _write_json(path: Path, obj: Any) -> None:
    """dict 를 UTF-8 JSON 으로 기록(안정적 key 순서)."""
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def write_cleanup_artifact(
    artifact_dir: Path,
    report: CleanupReport,
    *,
    db_instance_id: str,
    expected_run_row_version: int = 1,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, str]:
    """cleanup audit 결과를 **separate** 암호화 artifact 로 기록한다(phase ``LEGACY_CLEANUP``).

    entropy/AAD 가 ``WDC-LINK-CLEANUP-01`` / ``LEGACY_CLEANUP`` 를 바인딩하므로 V2 backfill
    (``V2_BACKFILL_*``) artifact 로 복호화되지 않는다(V2 artifact 재사용 구조적 0).

    Args:
        artifact_dir: artifact 를 쓸 디렉터리(호출자가 protected root 하위로 검증·생성).
        report: :func:`audit_wdc_link_cleanup` 결과.
        db_instance_id: target DB 식별자(entropy·AAD 바인딩).
        expected_run_row_version: apply 시 소비할 run row_version(fresh run=1).
        now: 결정적 타임스탬프(테스트 주입).

    Returns:
        ``{"manifest_sha256", "mapping_sha256", "source_composite_sha256", "phase"}``.
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name
    col_schema = column_schema_sha256()
    src_composite = report.source_composite_sha256()

    envelope, data_key = crypto.create_key_envelope(
        packet_id=PACKET_ID, phase=PHASE, db_instance_id=db_instance_id,
        artifact_dir_id=artifact_dir_id, now=now,
    )
    key_id = envelope["key_id"]
    for relative_path, plaintext in (
        (VERIFIED_ENC_FILE, verified_csv(report)),
        (AMBIGUOUS_ENC_FILE, ambiguous_csv(report)),
    ):
        payload_env = crypto.encrypt_payload(
            plaintext.encode("utf-8"), data_key, key_id=key_id,
            packet_id=PACKET_ID, phase=PHASE, relative_path=relative_path,
            db_instance_id=db_instance_id, source_fingerprint=src_composite,
            column_schema_sha256=col_schema,
        )
        _write_json(artifact_dir / relative_path, payload_env)

    manifest_dict = report.manifest_dict()
    (artifact_dir / MANIFEST_FILE).write_bytes(manifest.manifest_bytes(manifest_dict))
    (artifact_dir / SHA_FILE).write_text(manifest.sha_txt_contents(manifest_dict), encoding="utf-8")

    manifest_sha = manifest.compute_manifest_sha256(manifest_dict)
    mapping_sha = report.mapping_sha256()
    approval_scope = manifest.build_approval_scope(
        packet_id=PACKET_ID, phase=PHASE, manifest_sha256=manifest_sha, mapping_sha256=mapping_sha,
        db_instance_id=db_instance_id, source_composite_sha256=src_composite,
        expected_run_row_version=expected_run_row_version, masked_counts=report.masked_counts(),
    )
    _write_json(artifact_dir / APPROVAL_SCOPE_FILE, approval_scope)
    _write_json(artifact_dir / SUMMARY_FILE, {
        "packet_id": PACKET_ID, "phase": PHASE, "db_instance_id": db_instance_id,
        "column_schema_sha256": col_schema, "source_composite_sha256": src_composite,
        "masked_counts": report.masked_counts(),
        "generated_at": (now or now_utc_naive()).isoformat(),
    })
    _write_json(artifact_dir / KEY_ENVELOPE_FILE, envelope)
    return {
        "manifest_sha256": manifest_sha, "mapping_sha256": mapping_sha,
        "source_composite_sha256": src_composite, "phase": PHASE,
    }


@dataclass(frozen=True)
class LoadedCleanupArtifact:
    """복호화·검증된 cleanup artifact.

    Attributes:
        verified_csv_text: VERIFIED CSV 평문.
        manifest_sha256 / mapping_sha256: run identity.
        approval_scope: OPS approval 이 커밋하는 exact scope dict.
        masked_counts: 정수 카운트(PII 0).
    """

    verified_csv_text: str
    manifest_sha256: str
    mapping_sha256: str
    approval_scope: Dict[str, Any]
    masked_counts: Dict[str, int]


def load_cleanup_artifact(artifact_dir: Path, *, db_instance_id: str) -> LoadedCleanupArtifact:
    """cleanup artifact 무결성을 검증하고 VERIFIED 평문 + approval-scope 를 복원한다.

    Raises:
        CleanupArtifactError: manifest sha 불일치(변조) 또는 approval-scope 바인딩 불일치.
        crypto.BackfillCryptoError: DPAPI unwrap/GCM 인증 실패(다른 host/변조/phase drift).
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir_id = artifact_dir.name

    manifest_bytes = (artifact_dir / MANIFEST_FILE).read_bytes()
    sha_txt = (artifact_dir / SHA_FILE).read_text(encoding="utf-8").strip()
    disk_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if sha_txt != disk_manifest_sha:
        raise CleanupArtifactError("sha.txt does not match manifest.json bytes (tampered artifact).")

    manifest_dict = json.loads(manifest_bytes.decode("utf-8"))
    if manifest_dict.get("phase") != PHASE:
        raise CleanupArtifactError(
            f"artifact phase {manifest_dict.get('phase')!r} != {PHASE!r} (phase conflation)."
        )
    col_schema = manifest_dict.get("column_schema_sha256")

    approval_scope = json.loads((artifact_dir / APPROVAL_SCOPE_FILE).read_text(encoding="utf-8"))
    if approval_scope.get("manifest_sha256") != disk_manifest_sha:
        raise CleanupArtifactError("approval-scope manifest_sha256 does not bind on-disk manifest.")
    src_composite = approval_scope["source_composite_sha256"]

    envelope = json.loads((artifact_dir / KEY_ENVELOPE_FILE).read_text(encoding="utf-8"))
    data_key = crypto.load_data_key(
        envelope, packet_id=PACKET_ID, phase=PHASE,
        db_instance_id=db_instance_id, artifact_dir_id=artifact_dir_id,
    )
    verified_env = json.loads((artifact_dir / VERIFIED_ENC_FILE).read_text(encoding="utf-8"))
    verified_plaintext = crypto.decrypt_payload(
        verified_env, data_key, packet_id=PACKET_ID, phase=PHASE, relative_path=VERIFIED_ENC_FILE,
        db_instance_id=db_instance_id, source_fingerprint=src_composite,
        column_schema_sha256=col_schema,
    ).decode("utf-8")
    return LoadedCleanupArtifact(
        verified_csv_text=verified_plaintext,
        manifest_sha256=approval_scope["manifest_sha256"],
        mapping_sha256=approval_scope["mapping_sha256"],
        approval_scope=approval_scope,
        masked_counts=dict(approval_scope.get("masked_counts") or {}),
    )


# --------------------------------------------------------------------------- #
# separate verify-only run (checkpoint 원장 — 실 삭제 0)
# --------------------------------------------------------------------------- #
@dataclass
class CleanupRunReport:
    """cleanup verify run 결과 요약."""

    run_id: str = ""
    phase: str = ""
    topology: str = ""
    state: str = ""
    old_generation_rows: int = 0
    verified_rows: int = 0
    ambiguous_rows: int = 0
    verified_batches: int = 0
    deletions: int = 0          # 항상 0 — verify only(V1/Order meta/V2 삭제·변경 0).
    stopped_drift: bool = False


def _chunks(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _batch_fingerprint(quads: List[Tuple[str, int, int, bool]]) -> str:
    """(source, estimate_id, order_id, in_v2) 목록의 결정적 fingerprint(batch drift 비교용)."""
    payload = json.dumps(sorted([[s, e, o, m] for s, e, o, m in quads]), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _live_in_v2(session: Session, item: LegacyItem) -> bool:
    """이 item 의 pair 가 현재 canonical V2 에 있나(live 재검증 — read-only)."""
    return session.execute(
        text("SELECT 1 FROM estimate_order_links_v2 WHERE estimate_id = :e AND order_id = :o"),
        {"e": item.estimate_id, "o": item.order_id},
    ).first() is not None


def _verify_noop(_session: Session) -> None:
    """verify-only batch business write — domain mutation 0(실 삭제/변경 0).

    은퇴 준비 검증은 assertion(fingerprint drift 대조)이지 mutation 이 아니다. checkpoint 원장
    만 진행을 남긴다.
    """
    # ponytail: verify-only 라 domain write 없음. 실제 은퇴/drop 은 후속 packet 몫(마이그레이션 없음).
    return None


def _run_verify_batches(
    session: Session, run_id: str, raw_token: bytes, verified: List[LegacyItem], *,
    batch_size: int, now: datetime.datetime, report: CleanupRunReport,
) -> None:
    """VERIFIED item 을 batch 로 검증하고 checkpoint 를 남긴다(domain write 0·drift 면 정지)."""
    for seq, batch in enumerate(_chunks(verified, batch_size), start=1):
        expected_fp = _batch_fingerprint([(i.source, i.estimate_id, i.order_id, True) for i in batch])
        live_fp = _batch_fingerprint(
            [(i.source, i.estimate_id, i.order_id, _live_in_v2(session, i)) for i in batch]
        )
        checkpoint = hashlib.sha256(
            f"{run_id}:{seq}:{sorted((i.source, i.estimate_id, i.order_id) for i in batch)}".encode("utf-8")
        ).hexdigest()
        outcome = runs.write_batch(
            session, run_id, raw_token=raw_token,
            expected_fingerprint=expected_fp, live_fingerprint=live_fp,
            batch_business_write=_verify_noop,
            completed_delta=len(batch), batch_seq=seq, checkpoint_sha256=checkpoint, now=now,
        )
        session.commit()
        report.verified_batches += 1
        if outcome.stopped_drift:
            report.stopped_drift = True
            report.state = "STOPPED_DRIFT"
            return


def run_cleanup_verify(
    session: Session,
    *,
    topology: str,
    db_instance_id: str,
    owner_identity: str,
    wd_session: Optional[Session] = None,
    foms_session: Optional[Session] = None,
    batch_size: int = 100,
    now: Optional[datetime.datetime] = None,
    activate_approval: Optional[Callable[[Session, Any], None]] = None,
) -> CleanupRunReport:
    """canonical effective 뒤에만, old-generation 은퇴 준비를 **verify only** 로 검증한다(삭제 0).

    게이트(marker/CANONICAL effective + V2 checkpoint)를 먼저 강제하고, old generation 이 0 이면
    거부한다. VERIFIED item 만 separate run/checkpoint 로 batch 검증하며(V2 재사용 금지 phase),
    ambiguous 는 보류한다(제거 0). domain(V1/Order meta/V2)은 읽기만 한다.

    Args:
        session: V2 + fence/marker canonical target 세션(호출자가 batch 마다 commit).
        topology: :data:`TOPOLOGY_SAME` | :data:`TOPOLOGY_SEPARATE`.
        db_instance_id: run identity 의 target DB 식별자.
        owner_identity: lease owner 식별자(원문 저장 0 — hash 만).
        wd_session: V1 세션(기본 ``session``).
        foms_session: Order meta 세션(기본 ``session``).
        batch_size: batch 당 VERIFIED item 수.
        now: 결정적 타임스탬프(테스트 주입).
        activate_approval: ensure_run 직후 approval seq≥1 을 활성화하는 훅(운영은
            ``runs.consume_backfill_apply``; 없으면 acquire_lease 가 거부).

    Returns:
        :class:`CleanupRunReport` — run 상태·old generation·verified/ambiguous 수·deletions=0.

    Raises:
        WDCLinkCleanupGateError: canonical 미effective / V2 checkpoint 부재.
        WDCLinkCleanupError: old generation 0.
    """
    now = now or now_utc_naive()
    # 1) 게이트: marker/CANONICAL effective + V2 checkpoint(전 실행 거부).
    assert_cleanup_gate(session, topology=topology, wd_session=wd_session)

    # 2) audit(read-only) + old generation nonzero.
    audit = audit_wdc_link_cleanup(session, wd_session=wd_session, foms_session=foms_session)
    if audit.old_generation_rows == 0:
        raise WDCLinkCleanupError(
            "old generation is zero (no legacy V1/Order-meta rows to retire); "
            "refusing cleanup verify (wrong DB/topology?)."
        )

    report = CleanupRunReport(
        phase=PHASE, topology=topology, old_generation_rows=audit.old_generation_rows,
        verified_rows=len(audit.verified), ambiguous_rows=len(audit.ambiguous),
    )

    # 3) separate run(WDC-LINK-CLEANUP-01 / LEGACY_CLEANUP — V2 run 과 다른 run_id).
    run = runs.ensure_run(
        session, packet_id=PACKET_ID, phase=PHASE, db_instance_id=db_instance_id,
        manifest_sha256=audit.manifest_sha256(), mapping_sha256=audit.mapping_sha256(),
        total_rows=len(audit.verified), now=now,
    )
    run_id = run.run_id
    report.run_id = run_id
    if activate_approval is not None:
        activate_approval(session, run)
    session.flush()

    raw_token, _ = runs.new_lease_token()
    runs.acquire_lease(
        session, run_id, owner_identity_hash=runs.owner_hash(owner_identity),
        raw_token=raw_token, now=now,
    )
    session.commit()

    # 4) VERIFIED batch 검증(domain write 0). ambiguous 는 보류(제거 0).
    _run_verify_batches(session, run_id, raw_token, audit.verified,
                        batch_size=batch_size, now=now, report=report)
    if report.stopped_drift:
        return report

    completed = runs.complete_run(session, run_id, raw_token=raw_token, now=now)
    session.commit()
    report.state = completed.state
    return report


__all__ = [
    "PACKET_ID",
    "PHASE",
    "V2_BACKFILL_PACKET_ID",
    "VERIFIED",
    "AMBIGUOUS",
    "SOURCE_V1",
    "SOURCE_ORDER_META",
    "NO_CANONICAL_V2",
    "INVALID_META_ESTIMATE_ID",
    "TOPOLOGY_SAME",
    "TOPOLOGY_SEPARATE",
    "LegacyItem",
    "AmbiguousItem",
    "CleanupReport",
    "CleanupRunReport",
    "LoadedCleanupArtifact",
    "WDCLinkCleanupError",
    "WDCLinkCleanupGateError",
    "CleanupArtifactError",
    "column_schema_sha256",
    "iter_order_meta_links",
    "build_cleanup_report",
    "audit_wdc_link_cleanup",
    "assert_cleanup_gate",
    "verified_csv",
    "ambiguous_csv",
    "write_cleanup_artifact",
    "load_cleanup_artifact",
    "run_cleanup_verify",
]
