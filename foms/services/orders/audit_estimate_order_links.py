"""legacy EstimateOrderMatch(V1) → canonical EstimateOrderLinkV2 audit/분류 (WDC-LINK-BACKFILL-00, §5.2).

legacy ``EstimateOrderMatch``(``wdcalculator_models``)는 estimate↔order 매칭을
``(estimate_id, order_id)`` 로만 기록하고 **unique pair 제약이 없다** — 같은 pair 가 여러 V1 row
로 물리적으로 중복될 수 있다. 이 모듈은 V1 을 **read-only 로 분류**해 canonical
:class:`~models.EstimateOrderLinkV2`(unique pair) 로의 topology-aware backfill plan 을 만든다:

* :func:`audit_estimate_order_links` 는 아무 것도 쓰지 않는다(순수 조회 — V1 row 불변).
* **SAFE**: ``estimate_id``/``order_id`` 가 모두 유효한(positive) pair. 같은 pair 의 중복 V1
  row 는 canonical row **하나**로 정규화(dedup)하며, provenance ``source_match_id`` 는 그 pair
  V1 row 들의 **최소 id**(결정적 source-target equivalence)로 고정한다.
* **MANUAL**: ``estimate_id``/``order_id`` 가 null/비양수인 V1 row(orphan/무결성 위반). 자동
  발급하지 않고 암호화 manual CSV 로 사람 검토에 보낸다(자동 매핑 0).

**topology-agnostic 판독**: audit 는 V1 row 자체만 본다 — order/estimate 를 cross-DB 로
역참조하지 않는다(SEPARATE 위상에서 order 는 다른 DB). SAME/SEPARATE 구분은 backfill 의 phase/
fence gate 소관이고 audit 산출물(snapshot·manifest/mapping/source-composite sha)은 두 위상에서
동일하다 — phase 는 run_id·crypto entropy 층에서만 바인딩된다(phase conflation 금지).

``manifest_sha256`` / ``mapping_sha256`` / ``source_composite_sha256`` / ``masked_counts`` 는
BACKFILL-ARTIFACT-00 공용 인프라(:mod:`foms.services.security.backfill.manifest`)로 run
identity·OPS approval scope·drift 감지를 만든다(display text/PII 0).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

PACKET_ID = "WDC-LINK-BACKFILL-00"
# topology-neutral family phase(artifact/manifest 라벨). RUN 은 topology 별 phase 를 쓴다
# (``V2_BACKFILL_SAME`` / ``V2_BACKFILL_SEPARATE``, backfill 모듈) — run_id·crypto 가 위상을
# 바인딩해 phase conflation 을 구조적으로 차단한다.
PHASE_FAMILY = "V2_BACKFILL"
TOOL_VERSION = 1

# 분류 코드(closed set).
SAFE = "SAFE"
MANUAL = "MANUAL"
CLASSIFICATIONS: Tuple[str, ...] = (SAFE, MANUAL)

# manual 사유.
INVALID_ESTIMATE_ID = "INVALID_ESTIMATE_ID"
INVALID_ORDER_ID = "INVALID_ORDER_ID"

# safe/manual CSV 컬럼 스키마(AAD 바인딩용 — 고정 문자열, PII 0).
_SAFE_COLUMNS: Tuple[str, ...] = (
    "estimate_id", "order_id", "source_match_id", "source_row_ids", "duplicate_count", "pair_sha",
)
_MANUAL_COLUMNS: Tuple[str, ...] = (
    "source_match_id", "estimate_id", "order_id", "reason", "decision", "approved_by_user_id",
)


@dataclass(frozen=True)
class LinkSnapshot:
    """canonical link 1개의 결정적 backfill 스냅샷(V1 pair → V2 unique pair).

    Attributes:
        estimate_id: 견적 id(양수).
        order_id: 주문 id(양수).
        source_match_id: 발급 근거 V1 estimate_order_matches.id(중복 pair 는 최소 id).
        source_row_ids: 이 pair 를 구성한 V1 row id 전체(오름차순 — dedup provenance·drift 기준).
        duplicate_count: 정규화로 접힌 중복 V1 row 수(``len(source_row_ids) - 1``).
    """

    estimate_id: int
    order_id: int
    source_match_id: int
    source_row_ids: Tuple[int, ...]
    duplicate_count: int

    def pair_sha(self) -> str:
        """이 pair 의 source fingerprint(estimate/order/구성 row ids) — batch drift 비교용."""
        return _pair_source_sha(self.estimate_id, self.order_id, self.source_row_ids)


@dataclass(frozen=True)
class ManualLink:
    """자동 매핑 불가한 V1 row 1건(암호화 manual CSV 대상·read-only).

    Attributes:
        source_match_id: V1 estimate_order_matches.id.
        estimate_id: 원문 estimate_id(무결성 위반 값일 수 있음).
        order_id: 원문 order_id(무결성 위반 값일 수 있음).
        reason: :data:`INVALID_ESTIMATE_ID` | :data:`INVALID_ORDER_ID`.
    """

    source_match_id: int
    estimate_id: Optional[int]
    order_id: Optional[int]
    reason: str


def _pair_source_sha(estimate_id: int, order_id: int, source_row_ids: Tuple[int, ...]) -> str:
    """(estimate_id, order_id, 구성 V1 row ids) 의 결정적 sha256(drift 감지 단위)."""
    payload = json.dumps(
        [estimate_id, order_id, sorted(source_row_ids)], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pos_int(value: Any) -> Optional[int]:
    """양의 정수면 그 값, 아니면 None(무결성 판정)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


@dataclass
class AuditReport:
    """전체 V1 매칭 audit 요약(coverage 100% 증명 원장·read-only).

    Attributes:
        total_v1_rows: 스캔한 V1 estimate_order_matches row 총수.
        safe_links: SAFE pair 스냅샷(``(estimate_id, order_id)`` 오름차순, unique pair).
        manual_links: 무결성 위반 V1 row 목록(암호화 manual CSV 대상).
    """

    total_v1_rows: int = 0
    safe_links: List[LinkSnapshot] = field(default_factory=list)
    manual_links: List[ManualLink] = field(default_factory=list)

    @property
    def safe_rows(self) -> int:
        """SAFE pair 를 구성한 V1 row 총수(중복 포함)."""
        return sum(len(link.source_row_ids) for link in self.safe_links)

    @property
    def duplicate_rows(self) -> int:
        """정규화로 접힌 중복 V1 row 수(unique pair 증거)."""
        return sum(link.duplicate_count for link in self.safe_links)

    @property
    def unclassified(self) -> int:
        """어느 bucket 에도 안 들어간 V1 row 수(coverage 100% 이면 0)."""
        return self.total_v1_rows - self.safe_rows - len(self.manual_links)

    @property
    def counts(self) -> Dict[str, int]:
        """bucket 카운트(SAFE=고유 pair 수, MANUAL=위반 row 수)."""
        return {SAFE: len(self.safe_links), MANUAL: len(self.manual_links)}

    def masked_counts(self) -> Dict[str, int]:
        """approval-scope masked 카운트(정수만·PII 0)."""
        return {
            "total_v1_rows": self.total_v1_rows,
            "safe_pairs": len(self.safe_links),
            "safe_rows": self.safe_rows,
            "duplicate_rows": self.duplicate_rows,
            "manual_rows": len(self.manual_links),
        }

    def source_composite_sha256(self) -> str:
        """SAFE pair 소스 fingerprint 의 결정적 합성 sha256(전체 drift 감지)."""
        payload = json.dumps(
            [[l.estimate_id, l.order_id, list(l.source_row_ids)] for l in self.safe_links],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def manifest_dict(self) -> Dict[str, Any]:
        """run identity manifest(topology-neutral — phase 는 run/crypto 층 바인딩)."""
        return {
            "packet_id": PACKET_ID,
            "phase": PHASE_FAMILY,
            "tool_version": TOOL_VERSION,
            "column_schema_sha256": column_schema_sha256(),
            "total_v1_rows": self.total_v1_rows,
            "safe_pairs": len(self.safe_links),
            "manual_rows": len(self.manual_links),
            "source_composite_sha256": self.source_composite_sha256(),
        }

    def manifest_sha256(self) -> str:
        """manifest raw bytes 의 canonical sha256(run identity)."""
        from foms.services.security.backfill.manifest import compute_manifest_sha256

        return compute_manifest_sha256(self.manifest_dict())

    def mapping_sha256(self) -> str:
        """SAFE 결정 목록의 canonical mapping sha256(pair → LINK_V2)."""
        from foms.services.security.backfill.manifest import compute_mapping_sha256

        entries = [
            {
                "identity_fields": {"estimate_id": l.estimate_id, "order_id": l.order_id},
                "decision": "LINK_V2",
                "target_ids": [l.source_match_id],
                "reason_code": "PAIR_DEDUP" if l.duplicate_count else "PAIR_UNIQUE",
            }
            for l in self.safe_links
        ]
        return compute_mapping_sha256(entries)


def column_schema_sha256() -> str:
    """safe/manual CSV 컬럼 스키마의 결정적 sha256(payload AAD 바인딩)."""
    payload = json.dumps({"safe": _SAFE_COLUMNS, "manual": _MANUAL_COLUMNS}, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iter_v1_matches(session: Any, *, batch_size: int = 1000) -> Iterable[Tuple[int, Any, Any]]:
    """모든 V1 estimate_order_matches ``(id, estimate_id, order_id)`` 스트리밍(read-only)."""
    from wdcalculator_models import EstimateOrderMatch

    query = (
        session.query(
            EstimateOrderMatch.id,
            EstimateOrderMatch.estimate_id,
            EstimateOrderMatch.order_id,
        )
        .order_by(EstimateOrderMatch.id)
    )
    for row in query.yield_per(batch_size):
        yield row[0], row[1], row[2]


def build_report(rows: Iterable[Tuple[int, Any, Any]]) -> AuditReport:
    """``(match_id, estimate_id, order_id)`` 스트림을 SAFE(unique pair)·manual 로 분류한다(순수).

    DB 접근이 없는 분류 코어 — :func:`audit_estimate_order_links` 가 세션 스트림으로 호출한다.
    같은 유효 pair 의 중복 row 는 canonical row 하나로 dedup 하고, provenance ``source_match_id``
    는 그 pair 의 최소 id 로 고정한다(결정적 source-target equivalence).

    Args:
        rows: ``(match_id, estimate_id, order_id)`` 튜플 이터러블.

    Returns:
        :class:`AuditReport`.
    """
    report = AuditReport()
    # (estimate_id, order_id) → 구성 V1 row id 목록(유효 pair dedup).
    pairs: Dict[Tuple[int, int], List[int]] = {}
    for match_id, raw_estimate, raw_order in rows:
        report.total_v1_rows += 1
        est = _pos_int(raw_estimate)
        order = _pos_int(raw_order)
        if est is None:
            report.manual_links.append(ManualLink(match_id, raw_estimate, raw_order, INVALID_ESTIMATE_ID))
            continue
        if order is None:
            report.manual_links.append(ManualLink(match_id, raw_estimate, raw_order, INVALID_ORDER_ID))
            continue
        pairs.setdefault((est, order), []).append(match_id)

    for (est, order) in sorted(pairs.keys()):
        row_ids = tuple(sorted(pairs[(est, order)]))
        report.safe_links.append(
            LinkSnapshot(
                estimate_id=est,
                order_id=order,
                source_match_id=row_ids[0],
                source_row_ids=row_ids,
                duplicate_count=len(row_ids) - 1,
            )
        )
    report.manual_links.sort(key=lambda m: m.source_match_id)
    return report


def audit_estimate_order_links(source_session: Any, *, batch_size: int = 1000) -> AuditReport:
    """전체 V1 매칭을 분류해 SAFE(unique pair)·manual audit 원장을 만든다(mutation 0).

    Args:
        source_session: V1 ``estimate_order_matches`` 를 읽는 세션(SAME=주 세션, SEPARATE=WDC
            세션). read-only 로만 쓴다 — V1 row 불변.
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        :class:`AuditReport` — SAFE pair 스냅샷·manual row·coverage 원장.
    """
    return build_report(iter_v1_matches(source_session, batch_size=batch_size))


def safe_csv(report: AuditReport) -> str:
    """SAFE pair 를 CSV 문자열로 직렬화(header 포함·PII 0 — id/해시만)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(_SAFE_COLUMNS))
    for link in report.safe_links:
        writer.writerow([
            link.estimate_id,
            link.order_id,
            link.source_match_id,
            json.dumps(list(link.source_row_ids)),
            link.duplicate_count,
            link.pair_sha(),
        ])
    return buf.getvalue()


def ambiguous_csv(report: AuditReport) -> str:
    """manual(무결성 위반) V1 row 를 수동 검토 CSV 로 직렬화(자동 매핑 0·target 공란)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(list(_MANUAL_COLUMNS))
    for m in report.manual_links:
        writer.writerow([
            m.source_match_id,
            "" if m.estimate_id is None else m.estimate_id,
            "" if m.order_id is None else m.order_id,
            m.reason,
            "MANUAL",   # decision: 사람이 결정(자동 발급 금지).
            "",         # approved_by_user_id: 승인 전.
        ])
    return buf.getvalue()


@dataclass(frozen=True)
class SafeTarget:
    """복호화된 SAFE CSV 1행 = apply 입력(source-target equivalence 재확인용).

    Attributes:
        estimate_id: 견적 id.
        order_id: 주문 id.
        source_match_id: provenance V1 id(최소).
        pair_sha: 발급 시점 pair fingerprint(apply 시 live 재계산과 대조).
    """

    estimate_id: int
    order_id: int
    source_match_id: int
    pair_sha: str


def parse_safe_csv(text: str) -> List[SafeTarget]:
    """복호화된 SAFE CSV 를 :class:`SafeTarget` 목록으로 파싱(apply 입력 복원).

    Args:
        text: :func:`safe_csv` 가 만든 CSV 문자열.

    Returns:
        :class:`SafeTarget` 목록((estimate_id, order_id) 오름차순).
    """
    reader = csv.DictReader(io.StringIO(text))
    out: List[SafeTarget] = []
    for row in reader:
        out.append(
            SafeTarget(
                estimate_id=int(row["estimate_id"]),
                order_id=int(row["order_id"]),
                source_match_id=int(row["source_match_id"]),
                pair_sha=row["pair_sha"],
            )
        )
    out.sort(key=lambda t: (t.estimate_id, t.order_id))
    return out


__all__ = [
    "PACKET_ID",
    "PHASE_FAMILY",
    "TOOL_VERSION",
    "SAFE",
    "MANUAL",
    "CLASSIFICATIONS",
    "INVALID_ESTIMATE_ID",
    "INVALID_ORDER_ID",
    "LinkSnapshot",
    "ManualLink",
    "AuditReport",
    "SafeTarget",
    "column_schema_sha256",
    "iter_v1_matches",
    "build_report",
    "audit_estimate_order_links",
    "safe_csv",
    "ambiguous_csv",
    "parse_safe_csv",
]
