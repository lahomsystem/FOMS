"""STARTUP-BACKFILL-01 — ERP flat 컬럼 정합 read-only audit + 암호화 artifact.

각 주문의 ``structured_data``(SSOT)에서 파생돼야 하는 flat 검색/정렬 컬럼(``erp_stage_code``,
``erp_measurement_date`` 등)의 **현재 DB 값**을 :func:`foms.services.erp_sync_columns.
sync_erp_flat_columns` 이 산출하는 **기대 값**과 대조해 ``CLEAN`` / ``SAFE`` / ``AMBIGUOUS``
로 분류한다. 이 모듈은 **아무 것도 쓰지 않는다**(read-only) — flat 은 파생물이므로
structured_data 를 절대 건드리지 않고, 역방향(flat→structured) 재작성도 하지 않는다.

기대 값 산출은 라이브 라우트가 쓰는 것과 **동일한** ``sync_erp_flat_columns`` 을 재사용한다
— 별도 파생 로직을 복제하지 않아 정의상 drift 가 없다. read-only 를 지키려고 실제 주문
row 대신 read 속성만 복제한 shim 에 sync 를 적용해 기대 값을 포획한다.

분류 규칙(§5.2 STARTUP-BACKFILL-01):

* 대상은 ERP 주문(``is_erp_order``)이고 ``structured_data`` 가 dict 인 주문뿐이다.
  비-ERP·``structured_data is None`` 은 sync 가 no-op 이므로 대상이 아니다(집계 제외).
* ``structured_data`` 가 dict 가 아님(list/str 등) → ``AMBIGUOUS`` (안전 파생 불가·수동).
* 파생 flat 값이 현재 값과 다른 컬럼이 **금전 컬럼(``payment_amount``)** 을 포함 →
  ``AMBIGUOUS`` (금전 필드는 다른 흐름이 설정했을 수 있어 자동 덮어쓰기 금지·수동).
* 그 외 파생 컬럼만 drift → ``SAFE`` (structured_data 가 SSOT 이므로 재동기 안전).
* drift 없음 → ``CLEAN``.

SAFE 만 backfill(:mod:`~foms.services.orders.erp_flat_backfill`)이 재동기하며, artifact 는
DPAPI key-envelope + AES-256-GCM payload 로 암호화한다(repo/profile plaintext 금지).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_sync_columns import sync_erp_flat_columns

PACKET_ID = "STARTUP-BACKFILL-01"
PHASE = "STARTUP_FLAT"
TOOL_VERSION = 1

CLEAN = "CLEAN"
SAFE = "SAFE"
AMBIGUOUS = "AMBIGUOUS"

CLASSIFICATIONS: Tuple[str, ...] = (CLEAN, SAFE, AMBIGUOUS)

# structured_data 에서 sync_erp_flat_columns 가 파생하는 flat 컬럼(비교 대상, 결정적 순서).
# payment_amount 는 금전 필드라 분류에서 특별 취급한다(drift 면 AMBIGUOUS).
DERIVED_COLUMNS: Tuple[str, ...] = (
    "manager_name",
    "erp_measurement_date",
    "erp_construction_date",
    "measurement_date",
    "scheduled_date",
    "erp_stage_code",
    "erp_urgent",
    "erp_drawing_updated_at",
    "erp_stage_updated_at",
    "erp_owner_team_code",
    "erp_phone_digits",
    "payment_amount",
)
_FINANCIAL_COLUMN = "payment_amount"

# ambiguous 사유 코드.
MALFORMED = "MALFORMED_STRUCTURED_DATA"
PAYMENT_DRIFT = "PAYMENT_AMOUNT_DRIFT"


class _DeriveShim:
    """sync_erp_flat_columns 의 기대 파생 값을 read-only 로 포획하는 경량 shim.

    실제 주문 row 를 mutate 하지 않도록 sync 가 읽는 속성(``is_erp_order``·``phone``)만
    복제하고, sync 가 쓰는 flat 컬럼은 현재 값으로 초기화한다. sync 적용 후 각 속성이
    기대 파생 값을 담는다(무조건 덮어쓰는 컬럼은 파생 값, ``payment_amount`` 는 pa=None
    이면 현재 값 유지 — 라이브 sync 동작과 동일).
    """

    def __init__(self, order: Any) -> None:
        self.is_erp_order = True
        self.phone = getattr(order, "phone", None)
        for column in DERIVED_COLUMNS:
            setattr(self, column, getattr(order, column, None))


def column_schema_sha256() -> str:
    """flat 컬럼 스키마의 결정적 sha256(artifact AAD·manifest 바인딩용)."""
    payload = json.dumps(
        {"columns": list(DERIVED_COLUMNS), "tool_version": TOOL_VERSION},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_sha(structured_data: Any) -> str:
    """주문 structured_data(SSOT 소스)의 결정적 sha256(backfill drift 감지)."""
    payload = json.dumps(structured_data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FlatColumnAudit:
    """한 주문의 flat 컬럼 정합 분류 결과(read-only).

    Attributes:
        order_id: 주문 id.
        classification: CLEAN/SAFE/AMBIGUOUS.
        drift_columns: 현재 값 != 파생 값인 컬럼 목록(결정적 순서).
        reason: AMBIGUOUS 사유(MALFORMED/PAYMENT_DRIFT), 그 외 None.
        src_sha: structured_data 소스 fingerprint(drift 감지용).
    """

    order_id: int
    classification: str
    drift_columns: Tuple[str, ...] = ()
    reason: Optional[str] = None
    src_sha: str = ""


def _expected_flat_values(order: Any, structured_data: Dict[str, Any]) -> Dict[str, Any]:
    """read-only shim 에 sync 를 적용해 각 flat 컬럼의 기대 파생 값을 반환한다."""
    shim = _DeriveShim(order)
    sync_erp_flat_columns(shim, structured_data)
    return {column: getattr(shim, column, None) for column in DERIVED_COLUMNS}


def classify_order(order: Any) -> Optional[FlatColumnAudit]:
    """한 주문을 CLEAN/SAFE/AMBIGUOUS 로 분류한다(read-only, 대상 아니면 None).

    Args:
        order: ``id``·``is_erp_order``·``structured_data``·flat 컬럼을 가진 주문 row.

    Returns:
        :class:`FlatColumnAudit` 또는 ``None``(비-ERP/structured_data None → 대상 제외).
    """
    if not is_erp_order_record(order):
        return None
    sd = getattr(order, "structured_data", None)
    if sd is None:
        return None
    order_id = getattr(order, "id", None)
    if not isinstance(sd, dict):
        return FlatColumnAudit(order_id, AMBIGUOUS, reason=MALFORMED, src_sha=source_sha(sd))

    src = source_sha(sd)
    expected = _expected_flat_values(order, sd)
    drift = tuple(
        column for column in DERIVED_COLUMNS
        if expected[column] != getattr(order, column, None)
    )
    if not drift:
        return FlatColumnAudit(order_id, CLEAN, src_sha=src)
    if _FINANCIAL_COLUMN in drift:
        return FlatColumnAudit(order_id, AMBIGUOUS, drift, reason=PAYMENT_DRIFT, src_sha=src)
    return FlatColumnAudit(order_id, SAFE, drift, src_sha=src)


@dataclass
class AuditReport:
    """전체 주문 flat 컬럼 정합 audit 요약(coverage 원장)."""

    total: int = 0
    counts: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in CLASSIFICATIONS})
    safe_audits: List[FlatColumnAudit] = field(default_factory=list)
    ambiguous_audits: List[FlatColumnAudit] = field(default_factory=list)

    def safe_targets(self) -> List[Tuple[int, str]]:
        """SAFE 주문의 ``(order_id, src_sha)`` 목록(order_id 오름차순·apply 입력)."""
        return [(a.order_id, a.src_sha) for a in self.safe_audits]

    def manifest_sha256(self) -> str:
        """run identity 용 manifest sha256(packet/phase/tool/source composite/schema)."""
        from foms.services.security.backfill.manifest import compute_manifest_sha256

        return compute_manifest_sha256(self.manifest_dict())

    def mapping_sha256(self) -> str:
        """SAFE 결정 목록의 canonical mapping sha256(order_id → RESYNC_FLAT)."""
        from foms.services.security.backfill.manifest import compute_mapping_sha256

        entries = [
            {
                "identity_fields": {"order_id": a.order_id},
                "decision": "RESYNC_FLAT",
                "target_ids": [a.order_id],
                "reason_code": "FLAT_DRIFT",
            }
            for a in self.safe_audits
        ]
        return compute_mapping_sha256(entries)

    def source_composite_sha256(self) -> str:
        """SAFE 주문 소스 fingerprint 의 결정적 합성 sha256(전체 drift 감지)."""
        payload = json.dumps(
            [[a.order_id, a.src_sha] for a in self.safe_audits],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def masked_counts(self) -> Dict[str, int]:
        """approval-scope/summary 용 정수 카운트(PII 0)."""
        return {
            "total": self.total,
            "safe": self.counts[SAFE],
            "ambiguous": self.counts[AMBIGUOUS],
            "clean": self.counts[CLEAN],
        }

    def manifest_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": PACKET_ID,
            "phase": PHASE,
            "tool_version": TOOL_VERSION,
            "total_rows": self.total,
            "safe_rows": self.counts[SAFE],
            "ambiguous_rows": self.counts[AMBIGUOUS],
            "clean_rows": self.counts[CLEAN],
            "column_schema_sha256": column_schema_sha256(),
            "source_composite_sha256": self.source_composite_sha256(),
        }


def iter_orders(session, *, batch_size: int = 1000) -> Iterable[Any]:
    """모든 주문 row 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    for order in session.query(Order).order_by(Order.id).yield_per(batch_size):
        yield order


def audit_orders(session, *, batch_size: int = 1000) -> AuditReport:
    """전체 주문을 분류해 SAFE/ambiguous 목록과 coverage 원장을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`AuditReport`.
    """
    report = AuditReport()
    for order in iter_orders(session, batch_size=batch_size):
        result = classify_order(order)
        if result is None:
            continue  # 비-ERP / structured_data None → 대상 아님.
        report.total += 1
        report.counts[result.classification] += 1
        if result.classification == SAFE:
            report.safe_audits.append(result)
        elif result.classification == AMBIGUOUS:
            report.ambiguous_audits.append(result)
    report.safe_audits.sort(key=lambda a: a.order_id)
    report.ambiguous_audits.sort(key=lambda a: a.order_id)
    return report


# --------------------------------------------------------------------------- #
# CSV payloads (암호화 전 plaintext — PII 없이 order_id/사유/컬럼명만)
# --------------------------------------------------------------------------- #
def safe_csv(report: AuditReport) -> str:
    """SAFE 주문 CSV(order_id, src_sha, drift_columns, decision). 암호화 대상."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_id", "src_sha", "drift_columns", "decision"])
    for a in report.safe_audits:
        writer.writerow([a.order_id, a.src_sha, ";".join(a.drift_columns), "RESYNC_FLAT"])
    return buf.getvalue()


def ambiguous_csv(report: AuditReport) -> str:
    """AMBIGUOUS 주문 CSV(order_id, src_sha, reason, drift_columns). 암호화 대상·수동 검토."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_id", "src_sha", "reason", "drift_columns"])
    for a in report.ambiguous_audits:
        writer.writerow([a.order_id, a.src_sha, a.reason or "", ";".join(a.drift_columns)])
    return buf.getvalue()


def parse_safe_csv(plaintext: str) -> List[Tuple[int, str]]:
    """복호화한 safe.csv 를 ``(order_id, src_sha)`` 목록으로 파싱(apply 입력)."""
    targets: List[Tuple[int, str]] = []
    for row in csv.DictReader(io.StringIO(plaintext)):
        targets.append((int(row["order_id"]), row["src_sha"]))
    return targets


__all__ = [
    "PACKET_ID",
    "PHASE",
    "TOOL_VERSION",
    "CLEAN",
    "SAFE",
    "AMBIGUOUS",
    "CLASSIFICATIONS",
    "DERIVED_COLUMNS",
    "MALFORMED",
    "PAYMENT_DRIFT",
    "FlatColumnAudit",
    "AuditReport",
    "column_schema_sha256",
    "source_sha",
    "classify_order",
    "audit_orders",
    "safe_csv",
    "ambiguous_csv",
    "parse_safe_csv",
]
