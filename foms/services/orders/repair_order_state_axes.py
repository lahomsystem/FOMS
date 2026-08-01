"""다축 상태 축 **안전 repair** CLI·라이브러리 (STATE-AXES-REPAIR-00, SSOT §5.2·§7.2).

:mod:`foms.services.orders.state_axes_audit` 가 read-only 로 분류한 mirror/projection/
overlay 불일치 중 **safe bucket 만** 명시 apply 한다. 핵심 계약은 audit 와 대칭인 **자동수정 0**:

* dry-run(기본): safe bucket 이 제안한 교정을 **미적용** 미리보기(카운트만).
* apply: safe bucket 만 교정한다 — mirror mismatch 는 ``erp_stage_code`` 를 canonical
  ``workflow.stage`` 로 재동기(:func:`foms.services.erp_sync_columns.sync_erp_flat_columns`
  과 동일 규칙: ``erp_stage_code = workflow.stage`` 원값), projection mismatch 는 legacy
  ``order.status`` 를 canonical projection 으로 재계산. **overlay ambiguity 는 절대 자동
  교정하지 않는다** — manual CSV 승인 전 enforcement 0 (§7.2).
* verify: 적용 후 coverage 100%(모든 order 가 canonical mirror 정합, safe 미분류 0) 검증.
* manual CSV verifier: ambiguous CSV(사람이 채운 결정)를 검증해 적용을 **게이트**한다 —
  빈 칸(미결정)은 통과 거부(자동 선택 0), axis/value 도메인 위반도 거부.

repair 가 건드리는 것은 ``order.status`` · ``order.erp_stage_code`` 두 flat 컬럼뿐이며
``structured_data`` (canonical source) 와 command endpoint·전이 로직은 **변경하지 않는다**
— 순수 저장 데이터 정합화다.

ponytail: assignment_backfill.py 와 동일 판단 — 이 repair 는 두 flat 컬럼 정합이라
BACKFILL-ARTIFACT-00 의 lease/checkpoint/DPAPI run state machine(runs.py)까지 끌어오지
않는다. 대량·재개(resume) apply 가 실제로 필요해지면 그때 ``batch_business_write`` 콜러블로
:func:`foms.services.security.backfill.runs.write_batch` 에 감싼다(그 계약이 이 apply 를
그대로 받는다).
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from foms.services.orders.stage_override import MAIN_PIPELINE_CODES
from foms.services.orders.state_axes import (
    AS_VALUES,
    AXIS_AS,
    AXIS_CONSTRUCTION,
    AXIS_DELETE,
    AXIS_HOLD,
    AXIS_LOGISTICS,
    AXIS_MAIN,
    CONSTRUCTION_VALUES,
    DELETE_VALUES,
    HOLD_VALUES,
    LOGISTICS_VALUES,
)
from foms.services.orders.state_axes_audit import (
    OrderStateAxesAudit,
    audit_order_state_axes,
)

# manual CSV resolved_axis → 허용 canonical value 도메인. verifier 가 사람이 채운 축·값을
# 이 도메인으로 검증한다(도메인 밖 값은 거부).
AXIS_VALUE_DOMAINS: Dict[str, Tuple[str, ...]] = {
    AXIS_MAIN: MAIN_PIPELINE_CODES,
    AXIS_LOGISTICS: LOGISTICS_VALUES,
    AXIS_HOLD: HOLD_VALUES,
    AXIS_AS: AS_VALUES,
    AXIS_DELETE: DELETE_VALUES,
    AXIS_CONSTRUCTION: CONSTRUCTION_VALUES,
}

# to_manual_csv(state_axes_audit) 가 내보내는 헤더와 동일해야 한다(대칭 검증).
MANUAL_CSV_HEADER: List[str] = ["order_id", "status", "reason", "resolved_axis", "resolved_value"]


@dataclass
class RepairResult:
    """safe repair(dry-run/apply) 결과.

    Attributes:
        total: 감사한 order 수.
        mirror_repaired: ``(order_id, from_erp_stage_code, to_workflow_stage)`` 목록.
        projection_repaired: ``(order_id, from_status, to_projection)`` 목록.
        ambiguous_skipped: overlay ambiguity(자동 교정 금지, manual CSV 대상) 건수.
        manual_skipped: safe 아님(비-main workflow.stage·MULTI_AXIS projection) — 수동 판단 건수.
        dry_run: True 면 order 에 아무 것도 쓰지 않았다.
    """

    total: int
    mirror_repaired: List[Tuple[Any, Optional[str], Optional[str]]]
    projection_repaired: List[Tuple[Any, str, str]]
    ambiguous_skipped: int
    manual_skipped: int
    dry_run: bool

    @property
    def safe_count(self) -> int:
        """적용(또는 dry-run 제안)된 safe 교정 총수."""
        return len(self.mirror_repaired) + len(self.projection_repaired)


@dataclass
class CoverageReport:
    """apply 후 coverage 검증 결과.

    Attributes:
        total: 감사한 order 수.
        safe_remaining: 아직 남은 safe 교정 후보 수(``0`` 이면 coverage 100%).
        ambiguous_remaining: overlay ambiguity 잔여(manual CSV 승인 전 정상 잔존).
        manual_remaining: 비-safe mirror/projection 잔여(수동 판단 필요).
    """

    total: int
    safe_remaining: int
    ambiguous_remaining: int
    manual_remaining: int

    @property
    def coverage_ok(self) -> bool:
        """safe bucket 이 완전 소진됐는가(모든 order canonical mirror 정합)."""
        return self.safe_remaining == 0


@dataclass(frozen=True)
class ManualResolution:
    """검증 통과한 manual CSV 결정.

    Attributes:
        resolved: ``order_id(str) -> (axis, canonical_value)`` — 사람이 채워 검증 통과한 결정.
    """

    resolved: Dict[str, Tuple[str, str]]


class ManualCsvError(ValueError):
    """manual CSV 검증 실패(빈 결정·도메인 위반·헤더 불일치 등).

    Attributes:
        problems: 사람이 고쳐야 할 위반 사유 목록.
    """

    def __init__(self, problems: List[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def _manual_skipped_count(audit: OrderStateAxesAudit) -> int:
    """safe 도 ambiguous 도 아닌 잔여(수동 판단) 건수."""
    return sum(1 for m in audit.mirror_mismatch if m.safe_target is None) + sum(
        1 for p in audit.projection_mismatch if not p.recomputable
    )


def apply_safe_repair(orders: Iterable[Any], *, dry_run: bool = True) -> RepairResult:
    """audit safe bucket 만 order 에 적용한다(overlay ambiguity 는 절대 손대지 않음).

    mirror mismatch(safe_target 有)는 ``erp_stage_code`` 를 canonical ``workflow.stage``
    원값으로 재동기하고, projection mismatch(recomputable)는 ``order.status`` 를 canonical
    projection 으로 재계산한다. 두 flat 컬럼만 쓰며 ``structured_data`` 는 읽기만 한다.

    Args:
        orders: ``id``/``status``/``erp_stage_code``/``structured_data`` 를 가진 Order-like 목록.
        dry_run: True(기본)면 아무 것도 쓰지 않고 제안만 카운트한다.

    Returns:
        RepairResult — mirror/projection 교정 목록 + skip 카운트 + dry_run 여부.
        호출자는 apply(``dry_run=False``) 후 세션을 commit 한다.
    """
    orders_list = list(orders)
    by_id: Dict[Any, Any] = {getattr(o, "id", None): o for o in orders_list}
    audit = audit_order_state_axes(orders_list)

    mirror_repaired: List[Tuple[Any, Optional[str], Optional[str]]] = []
    for mismatch in audit.mirror_mismatch:
        if mismatch.safe_target is None:  # 비-main stage → 수동 판단, 자동 교정 금지
            continue
        mirror_repaired.append((mismatch.order_id, mismatch.erp_stage_code, mismatch.workflow_stage))
        if not dry_run:
            by_id[mismatch.order_id].erp_stage_code = mismatch.workflow_stage

    projection_repaired: List[Tuple[Any, str, str]] = []
    for proj in audit.projection_mismatch:
        if not proj.recomputable:  # MULTI_AXIS → 모호, 자동 재계산 금지
            continue
        projection_repaired.append((proj.order_id, proj.actual_status, proj.expected_projection))
        if not dry_run:
            by_id[proj.order_id].status = proj.expected_projection

    return RepairResult(
        total=audit.total,
        mirror_repaired=mirror_repaired,
        projection_repaired=projection_repaired,
        ambiguous_skipped=len(audit.overlay_ambiguity),
        manual_skipped=_manual_skipped_count(audit),
        dry_run=dry_run,
    )


def verify_coverage(orders: Iterable[Any]) -> CoverageReport:
    """order 를 재감사해 safe bucket 소진(coverage 100%)을 검증한다.

    apply 후 호출한다. ``coverage_ok`` 는 safe 교정 잔여가 0 임을 뜻하며, ambiguous/manual
    잔여는 manual CSV 승인 전 정상적으로 남아 있을 수 있다(enforcement 0).

    Args:
        orders: 감사할 Order-like 목록.

    Returns:
        CoverageReport — safe/ambiguous/manual 잔여 카운트.
    """
    audit = audit_order_state_axes(orders)
    return CoverageReport(
        total=audit.total,
        safe_remaining=len(audit.safe),
        ambiguous_remaining=len(audit.ambiguous),
        manual_remaining=_manual_skipped_count(audit),
    )


def verify_manual_csv(
    csv_text: str,
    *,
    audit: Optional[OrderStateAxesAudit] = None,
    require_all: bool = False,
) -> ManualResolution:
    """사람이 채운 ambiguous 결정 CSV 를 검증한다(자동 선택 0 — 빈 칸은 거부).

    ``to_manual_csv`` 가 내보낸 헤더(:data:`MANUAL_CSV_HEADER`)를 그대로 받는다. 각 행은
    ``resolved_axis`` + ``resolved_value`` 가 **모두** 채워지고 :data:`AXIS_VALUE_DOMAINS`
    도메인에 맞아야 통과한다. 빈 결정은 자동 선택하지 않고 위반으로 거부한다.

    Args:
        csv_text: manual CSV 텍스트.
        audit: 주어지면 각 행 order_id 가 실제 overlay ambiguity 집합에 속하는지 대조한다.
        require_all: True 면 audit 의 모든 ambiguous order_id 가 해결됐는지도 요구한다.

    Returns:
        ManualResolution — ``order_id -> (axis, value)`` 검증 통과 결정.

    Raises:
        ManualCsvError: 헤더 불일치·빈 결정·도메인 위반·중복·미해결(require_all) 시.
    """
    rows = list(csv.reader(io.StringIO(csv_text)))
    if not rows or rows[0] != MANUAL_CSV_HEADER:
        raise ManualCsvError(
            [f"header must be {MANUAL_CSV_HEADER}, got {rows[0] if rows else None}"]
        )

    ambiguous_ids: Optional[set] = (
        {str(a.order_id) for a in audit.overlay_ambiguity} if audit is not None else None
    )
    problems: List[str] = []
    resolved: Dict[str, Tuple[str, str]] = {}

    for line_no, row in enumerate(rows[1:], start=2):
        if not any((cell or "").strip() for cell in row):
            continue  # 빈 줄
        if len(row) != len(MANUAL_CSV_HEADER):
            problems.append(f"line {line_no}: expected {len(MANUAL_CSV_HEADER)} columns, got {len(row)}")
            continue
        order_id, _status, _reason, axis, value = (cell.strip() for cell in row)
        if not order_id:
            problems.append(f"line {line_no}: order_id is blank")
            continue
        if ambiguous_ids is not None and order_id not in ambiguous_ids:
            problems.append(f"line {line_no}: order_id {order_id} is not in the audit ambiguous set")
            continue
        if not axis or not value:  # 자동 선택 0 — 빈 결정은 거부
            problems.append(
                f"line {line_no}: order_id {order_id} has a blank resolution (auto-selection refused)"
            )
            continue
        domain = AXIS_VALUE_DOMAINS.get(axis)
        if domain is None:
            problems.append(f"line {line_no}: resolved_axis {axis!r} is not a valid axis")
            continue
        if value not in domain:
            problems.append(f"line {line_no}: resolved_value {value!r} not valid for axis {axis}")
            continue
        if order_id in resolved:
            problems.append(f"line {line_no}: duplicate order_id {order_id}")
            continue
        resolved[order_id] = (axis, value)

    if require_all and ambiguous_ids is not None:
        missing = ambiguous_ids - set(resolved)
        if missing:
            problems.append(f"unresolved ambiguous order_ids: {sorted(missing)}")

    if problems:
        raise ManualCsvError(problems)
    return ManualResolution(resolved=resolved)


# --------------------------------------------------------------------------- #
# CLI (dry-run / apply / verify / verify-csv) — ops 러너
# --------------------------------------------------------------------------- #
def _load_orders(session: Any) -> List[Any]:
    """DB 세션에서 모든 Order 를 로드한다(감사 대상)."""
    from models import Order  # lazy: 모듈 import 시 DB 의존 없음

    return session.query(Order).all()


def _print_repair(result: RepairResult) -> None:
    """RepairResult 요약을 stdout 으로 출력."""
    mode = "dry-run (no writes)" if result.dry_run else "apply (committed)"
    print(f"[repair {mode}] total={result.total}")
    print(f"  mirror_repaired={len(result.mirror_repaired)} projection_repaired={len(result.projection_repaired)}")
    print(f"  ambiguous_skipped={result.ambiguous_skipped} manual_skipped={result.manual_skipped}")
    for oid, frm, to in result.mirror_repaired:
        print(f"  MIRROR order={oid} erp_stage_code {frm!r} -> {to!r}")
    for oid, frm, to in result.projection_repaired:
        print(f"  PROJECTION order={oid} status {frm!r} -> {to!r}")


def main(argv: Optional[List[str]] = None) -> int:
    """repair CLI 진입점. subcommand: dry-run|apply|verify|verify-csv.

    verify 는 coverage 100% 면 exit 0, 아니면 1. verify-csv 는 유효 CSV 면 0, 위반이면 1.
    """
    import argparse

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    parser = argparse.ArgumentParser(prog="repair_order_state_axes", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-run", help="safe 교정 미리보기(미적용)")
    sub.add_parser("apply", help="safe bucket 만 적용하고 commit")
    sub.add_parser("verify", help="coverage 100%(safe 잔여 0) 검증")
    vcsv = sub.add_parser("verify-csv", help="사람이 채운 ambiguous CSV 검증(게이트)")
    vcsv.add_argument("csv_path", help="검증할 manual CSV 경로")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    session = sessionmaker(bind=create_engine(url))()
    try:
        if args.command == "verify-csv":
            with open(args.csv_path, encoding="utf-8") as fh:
                csv_text = fh.read()
            audit = audit_order_state_axes(_load_orders(session))
            try:
                res = verify_manual_csv(csv_text, audit=audit)
            except ManualCsvError as exc:
                print("[verify-csv] INVALID:")
                for problem in exc.problems:
                    print(f"  - {problem}")
                return 1
            print(f"[verify-csv] OK: {len(res.resolved)} resolved decision(s)")
            return 0

        orders = _load_orders(session)
        if args.command == "dry-run":
            _print_repair(apply_safe_repair(orders, dry_run=True))
            return 0
        if args.command == "apply":
            result = apply_safe_repair(orders, dry_run=False)
            session.commit()
            _print_repair(result)
            return 0
        if args.command == "verify":
            report = verify_coverage(orders)
            print(
                f"[verify] total={report.total} safe_remaining={report.safe_remaining} "
                f"ambiguous_remaining={report.ambiguous_remaining} manual_remaining={report.manual_remaining}"
            )
            print(f"[verify] coverage_ok={report.coverage_ok}")
            return 0 if report.coverage_ok else 1
        return 2
    finally:
        session.close()


__all__ = [
    "AXIS_VALUE_DOMAINS",
    "MANUAL_CSV_HEADER",
    "RepairResult",
    "CoverageReport",
    "ManualResolution",
    "ManualCsvError",
    "apply_safe_repair",
    "verify_coverage",
    "verify_manual_csv",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
