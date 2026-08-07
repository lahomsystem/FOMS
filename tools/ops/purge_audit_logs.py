"""Purge retention-elapsed audit ledger rows (AUDIT-LOG T9).

감사 테이블 4종은 append-only 인데 purge 잡이 하나도 없어 무한 증식한다(스펙 §2 —
"retention: purge 잡 0"). 이 도구가 보존기간을 넘긴 행만 배치 삭제한다.

대상과 기본 보존기간:

===========================  ==================  ==============
table                        시각 컬럼           기본 보존
===========================  ==================  ==============
``security_logs``            ``timestamp``       730일(2년)
``notification_events``      ``created_at``      365일(1년)
``channel_delivery_logs``    ``created_at``      365일(1년)
``access_logs``              ``timestamp``       365일(1년)
===========================  ==================  ==============

**``order_events`` 는 대상이 아니다**(:data:`EXCLUDED_TABLES`). T9 가 방금 그 테이블을
``orders`` 의 ``ON DELETE CASCADE`` 에서 떼어내 독립 감사 원장으로 만든 참이다 — 여기서
다시 지우면 FK 분리가 무의미해진다. ``orders`` 자체도 이 도구의 사정권 밖이다(주문 hard
purge 는 OPS-APPROVAL 게이트가 걸린 ``tools/ops/apply_delete_retention.py`` 소관).

경계·재사용 규칙(``purge_order_mutation_receipts.py`` 와 동일 규율):

* 스키마 변경/마이그레이션 없음 — 기존 테이블·인덱스를 **재사용만** 한다.
* Flask app 을 import 하지 않는다(전체 app 초기화는 Railway cron heartbeat timeout
  원인) — ``DATABASE_URL`` 로 직접 엔진을 만든다.
* 동시 실행은 PostgreSQL **session-level advisory lock** 하나로 전체 run 을 직렬화한다.
  락을 못 잡으면 아무것도 지우지 않고 benign skip.
* 기본은 **dry-run**(``--apply`` 없으면 삭제 0, 대상 수만 보고). 출력은 **카운트만** —
  감사 원장 값(메시지·IP·payload)은 한 글자도 찍지 않는다.
* **resume/crash-safe**: 배치마다 commit 하므로 중단 후 재실행이 곧 resume 이다.

알려진 동반 삭제 1건: ``domain_side_effect_outbox.notification_event_id`` 가
``notification_events.id`` 를 ``ON DELETE CASCADE`` 로 참조한다 — 1년 지난 알림 이벤트를
지우면 그 outbox 행도 함께 사라진다. 그 나이의 outbox 는 이미 소비·DEAD 처리가 끝났고
(SIDEFX-WORKER-01), FK 가 선언한 동작이라 구조적으로 정합이다.

시각 컬럼 규약: 테이블별로 naive-UTC(``now_utc_naive``)와 서버 로컬 naive(``datetime.now``)
가 섞여 있는 과도기 상태다(프로젝트 알려진 사실). 보존기간이 1~2년 단위라 최대 수 시간의
오프셋 차이는 경계 판정에 영향을 주지 않는다 — cutoff 는 naive-UTC 기준으로 계산한다.

exit code: 0 성공(dry-run·apply·lock-skip 포함), 1 오류.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

_LOGGER = logging.getLogger("purge_audit_logs")

DEFAULT_BATCH_SIZE = 1000
# session-level advisory lock 키(문자열 → hashtext). run 전체(4 테이블)를 하나로 묶는다.
ADVISORY_LOCK_KEY = "foms:purge_audit_logs"

# 절대 건드리지 않는 테이블. ``order_events`` 는 T9 가 orders CASCADE 에서 분리한 감사
# 원장이라 retention purge 대상이 아니고, ``orders`` 는 OPS-APPROVAL 게이트 소관이다.
EXCLUDED_TABLES = frozenset({"order_events", "orders"})


@dataclass(frozen=True)
class AuditTableSpec:
    """purge 대상 감사 테이블 1종의 계약.

    Attributes:
        table: 테이블명(모듈 상수 — 외부 입력 아님).
        timestamp_column: 보존기간 판정에 쓰는 시각 컬럼명.
        default_retention_days: 기본 보존기간(일). CLI 로 테이블별 override 가능.
        children_first: True 면 ``id`` 역순으로 지운다. 자기참조 FK 가 있는 테이블에서
            부모가 자식보다 먼저 지워져 FK 를 깨뜨리는 것을 막는다 — 자식 행은 부모의
            id 를 알아야 만들어지므로 SERIAL PK 상 **항상 child.id > parent.id** 다.
            (시각 컬럼이 아니라 id 로 정렬하는 이유: 시각은 clock skew·수기 데이터로
            역전될 수 있지만 id 순서는 삽입 순서 그 자체다.)
        survivor_guard_sql: 대상 술어에 AND 로 덧붙는 추가 조건(빈 문자열이면 없음).
            살아남을 행의 **조상 전체**를 삭제 대상에서 빼는 데 쓴다.
    """

    table: str
    timestamp_column: str
    default_retention_days: int
    children_first: bool = False
    survivor_guard_sql: str = ""

    @property
    def cli_flag(self) -> str:
        """이 테이블 전용 보존기간 override 플래그(``--retention-days-security-logs``)."""
        return f"--retention-days-{self.table.replace('_', '-')}"

    @property
    def arg_name(self) -> str:
        """argparse Namespace 속성명(``retention_days_security_logs``)."""
        return f"retention_days_{self.table}"


# ``channel_delivery_logs.parent_delivery_id`` 는 재전송 체인을 가리키는 자기참조 FK 이며
# ON DELETE 액션이 없다(NO ACTION) — 살아남을 행이 가리키는 부모를 지우면 FK 위반으로
# purge 전체가 죽는다. 체인은 2단계 이상일 수 있으므로(재전송의 재전송) **직속 자식만 보는
# 가드로는 부족하다**: 보존기간 안쪽 행의 **조상 전체**를 재귀로 모아 대상에서 뺀다.
#
# 재귀 anchor 를 "부모가 있는 생존 행"으로 좁힌 이유: 부모가 없는 생존 행은 조상 집합에
# 아무것도 보태지 않고, 자기 자신은 애초에 (``created_at >= cutoff``) 삭제 후보가 아니다.
#
# 이 가드가 만드는 대상 집합은 **하향 폐쇄**다(어떤 행이 대상이면 그 자손도 전부 대상) —
# 따라서 ``children_first`` 정렬만 지키면 배치가 어디서 잘리든 FK 가 깨지지 않는다.
_CHANNEL_DELIVERY_SURVIVOR_GUARD = (
    " AND t.id NOT IN ("
    "WITH RECURSIVE retained AS ("
    " SELECT id, parent_delivery_id FROM channel_delivery_logs"
    " WHERE created_at >= :cutoff AND parent_delivery_id IS NOT NULL"
    " UNION"
    " SELECT p.id, p.parent_delivery_id FROM channel_delivery_logs p"
    " JOIN retained r ON r.parent_delivery_id = p.id)"
    " SELECT id FROM retained)"
)

AUDIT_TABLES: tuple[AuditTableSpec, ...] = (
    # 보안 감사 원장 — 조사 요구가 가장 길다(2년).
    AuditTableSpec("security_logs", "timestamp", 730),
    # 알림 상태 전이 로그 — append-only, 운영 조사는 1년이면 충분.
    AuditTableSpec("notification_events", "created_at", 365),
    # ChannelTalk 전송 로그(Outbox 겸용) — 자기참조 FK 때문에 자식 우선 + survivor guard.
    AuditTableSpec(
        "channel_delivery_logs", "created_at", 365,
        children_first=True, survivor_guard_sql=_CHANNEL_DELIVERY_SURVIVOR_GUARD,
    ),
    # 파일 접근 기록(T6 에서 부활) — 1년.
    AuditTableSpec("access_logs", "timestamp", 365),
)

# 계약: 제외 테이블이 대상 목록에 섞여 들어오면 import 시점에 죽는다(조용한 회귀 차단).
assert not {spec.table for spec in AUDIT_TABLES} & EXCLUDED_TABLES, (
    "AUDIT_TABLES must never include an excluded table"
)


@dataclass(frozen=True)
class TablePurgeResult:
    """테이블 1종의 purge 결과(카운트만 — 원장 값은 담지 않는다).

    Attributes:
        table: 테이블명.
        retention_days: 이번 run 에 적용된 보존기간(일).
        scanned: cutoff 이전이라 삭제 대상인 행 수. dry-run 은 이 값만 보고한다.
        deleted: 실제 삭제된 행 수(dry-run 은 0).
        batches: 실행한 삭제 배치 수.
    """

    table: str
    retention_days: int
    scanned: int
    deleted: int
    batches: int


@dataclass(frozen=True)
class PurgeResult:
    """run 전체 결과.

    Attributes:
        tables: 테이블별 결과(대상 목록 순서).
        locked: advisory lock 을 못 잡아 skip 했으면 True(그 경우 tables 는 빈 튜플).
        applied: ``--apply`` 로 실제 삭제를 수행했으면 True.
    """

    tables: tuple[TablePurgeResult, ...]
    locked: bool
    applied: bool

    @property
    def scanned(self) -> int:
        """전 테이블 삭제 대상 합계."""
        return sum(t.scanned for t in self.tables)

    @property
    def deleted(self) -> int:
        """전 테이블 실제 삭제 합계(dry-run 은 0)."""
        return sum(t.deleted for t in self.tables)


def _now_utc_naive() -> datetime:
    """naive(UTC) 현재 시각. 감사 테이블 시각 컬럼이 naive 이므로 동일 규약."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _target_predicate(spec: AuditTableSpec) -> str:
    """``FROM <table> t`` 기준 삭제 대상 술어(WHERE 절 본문)."""
    return f"t.{spec.timestamp_column} < :cutoff{spec.survivor_guard_sql}"


def count_sql(spec: AuditTableSpec) -> str:
    """삭제 대상 수 집계 SQL. dry-run 보고와 ``--apply`` 삭제가 **같은 술어**를 쓴다."""
    return f"SELECT COUNT(*) FROM {spec.table} t WHERE {_target_predicate(spec)}"


def delete_batch_sql(spec: AuditTableSpec) -> str:
    """keyset 배치 삭제 SQL(``:cutoff``·``:lim`` 바인드).

    테이블·컬럼명은 모듈 상수(외부 입력 아님)라 f-string 으로 조립하고, 값은 전부 바인드
    파라미터다(주입 표면 0).

    정렬은 두 갈래다. 기본은 시각 오름차순(가장 오래된 것부터, 시각 인덱스를 탄다).
    ``children_first`` 테이블은 ``id`` 내림차순 — 자기참조 FK 를 배치 경계에서 깨지 않도록
    자식(항상 더 큰 id)을 부모보다 먼저 지운다.
    """
    order_by = (
        "t.id DESC" if spec.children_first
        else f"t.{spec.timestamp_column} ASC, t.id ASC"
    )
    return (
        f"DELETE FROM {spec.table} WHERE id IN ("
        f" SELECT t.id FROM {spec.table} t"
        f" WHERE {_target_predicate(spec)}"
        f" ORDER BY {order_by}"
        f" LIMIT :lim)"
    )


def resolve_retention_days(
    overrides: Optional[Mapping[str, int]] = None,
) -> dict[str, int]:
    """테이블별 보존기간을 확정한다(기본값 + override).

    Args:
        overrides: ``{table: days}`` override. None/미지정 테이블은 기본값을 쓴다.

    Returns:
        모든 대상 테이블에 대한 ``{table: retention_days}``.

    Raises:
        ValueError: 대상 테이블이 아닌 이름이 오거나 보존기간이 음수.
    """
    resolved = {spec.table: spec.default_retention_days for spec in AUDIT_TABLES}
    for table, days in (overrides or {}).items():
        if table not in resolved:
            raise ValueError(f"unknown audit table {table!r}")
        if days < 0:
            raise ValueError(f"retention_days for {table!r} must be >= 0")
        resolved[table] = days
    return resolved


def run_table(
    connection: Connection,
    spec: AuditTableSpec,
    *,
    retention_days: int,
    batch_size: int,
    apply: bool,
    now: datetime,
    logger: logging.Logger,
) -> TablePurgeResult:
    """테이블 1종의 만료 행을 세고(그리고 ``apply`` 면) keyset 배치 삭제한다.

    Args:
        connection: commit-as-you-go Connection(배치마다 commit — advisory lock 은
            session-level 이라 같은 물리 연결 위에서 계속 살아 있다).
        spec: 대상 테이블 계약.
        retention_days: ``now - retention_days`` 보다 과거인 행만 대상(0 이상).
        batch_size: 한 배치에서 삭제할 최대 행 수(≥1).
        apply: True 면 실제 삭제, False 면 dry-run(삭제 0).
        now: cutoff 계산 기준 시각(naive UTC).
        logger: 진행 로그용.

    Returns:
        TablePurgeResult(카운트만).
    """
    cutoff = now - timedelta(days=retention_days)
    params = {"cutoff": cutoff}

    scanned = connection.execute(text(count_sql(spec)), params).scalar() or 0

    deleted = 0
    batches = 0
    if apply and scanned:
        delete_batch = text(delete_batch_sql(spec))
        while True:
            n = connection.execute(
                delete_batch, {**params, "lim": batch_size}
            ).rowcount or 0
            connection.commit()
            if n == 0:
                break
            deleted += n
            batches += 1
            logger.info(
                "[purge_audit_logs] table=%s batch=%d deleted=%d total=%d",
                spec.table, batches, n, deleted,
            )
            if n < batch_size:
                break

    return TablePurgeResult(
        table=spec.table, retention_days=retention_days,
        scanned=scanned, deleted=deleted, batches=batches,
    )


def run(
    connection: Connection,
    *,
    retention_overrides: Optional[Mapping[str, int]] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    apply: bool = False,
    now: Optional[datetime] = None,
    logger: Optional[logging.Logger] = None,
) -> PurgeResult:
    """감사 테이블 4종의 만료 행을 advisory lock 아래에서 순차 purge 한다.

    Args:
        connection: commit-as-you-go Connection(``engine.connect()`` 결과).
        retention_overrides: ``{table: days}`` 테이블별 보존기간 override.
        batch_size: 한 배치에서 삭제할 최대 행 수(≥1, 기본 1000).
        apply: True 면 실제 삭제, False(기본)면 dry-run.
        now: 테스트용 시각 주입(기본 ``_now_utc_naive()``).
        logger: 진행 로그용(기본 모듈 로거).

    Returns:
        PurgeResult(테이블별 카운트 + lock/apply 상태).

    Raises:
        ValueError: batch_size<1, 또는 override 가 미지의 테이블/음수 보존기간.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    retentions = resolve_retention_days(retention_overrides)
    log = logger or _LOGGER
    moment = now or _now_utc_naive()

    got = connection.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:k))"),
        {"k": ADVISORY_LOCK_KEY},
    ).scalar()
    if not got:
        log.warning(
            "[purge_audit_logs] advisory lock busy; another purge is running "
            "— skipping (no rows touched)"
        )
        return PurgeResult(tables=(), locked=True, applied=False)

    try:
        results = tuple(
            run_table(
                connection, spec,
                retention_days=retentions[spec.table],
                batch_size=batch_size, apply=apply, now=moment, logger=log,
            )
            for spec in AUDIT_TABLES
        )
        return PurgeResult(tables=results, locked=False, applied=apply)
    finally:
        connection.execute(
            text("SELECT pg_advisory_unlock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        )
        connection.commit()


def _make_engine() -> Engine:
    """``DATABASE_URL`` 로 bare SQLAlchemy 엔진 생성(Flask app 미import)."""
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if url.startswith("postgres://"):  # Railway 표기 → SQLAlchemy 표기
        url = "postgresql://" + url[len("postgres://"):]
    engine_kwargs: dict = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    return create_engine(url, **engine_kwargs)


def build_parser() -> argparse.ArgumentParser:
    """CLI 파서(테이블별 보존기간 override 플래그를 대상 목록에서 생성)."""
    parser = argparse.ArgumentParser(
        description=(
            "Purge retention-elapsed audit ledger rows (AUDIT-LOG T9). "
            "order_events is never touched. Default is dry-run; pass --apply to delete."
        )
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Rows deleted per batch/commit (default {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete. Without this flag, only counts (dry-run).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Explicit dry-run alias (default behaviour; no deletes).",
    )
    for spec in AUDIT_TABLES:
        parser.add_argument(
            spec.cli_flag, dest=spec.arg_name, type=int, default=None,
            help=(f"Retention override for {spec.table} "
                  f"(default {spec.default_retention_days})."),
        )
    return parser


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI flags. dry-run(기본) vs --apply, batch, 테이블별 retention."""
    return build_parser().parse_args(argv)


def _overrides_from_args(args: argparse.Namespace) -> dict[str, int]:
    """Namespace 에서 실제로 지정된 테이블별 보존기간 override 만 추린다."""
    return {
        spec.table: getattr(args, spec.arg_name)
        for spec in AUDIT_TABLES
        if getattr(args, spec.arg_name, None) is not None
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Exit 0 성공, 1 오류."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    if args.dry_run and args.apply:
        _LOGGER.error("[purge_audit_logs] --dry-run and --apply are mutually exclusive")
        return 1

    mode = "apply" if args.apply else "dry-run"
    started = time.monotonic()
    try:
        engine = _make_engine()
        try:
            with engine.connect() as conn:
                result = run(
                    conn,
                    retention_overrides=_overrides_from_args(args),
                    batch_size=args.batch_size,
                    apply=args.apply,
                )
        finally:
            engine.dispose()
        elapsed = time.monotonic() - started
        if result.locked:
            _LOGGER.info(
                "[purge_audit_logs] mode=%s SKIPPED (advisory lock busy) elapsed=%.1fs",
                mode, elapsed,
            )
            return 0
        for table_result in result.tables:
            _LOGGER.info(
                "[purge_audit_logs] table=%s retention_days=%d scanned=%d deleted=%d "
                "batches=%d",
                table_result.table, table_result.retention_days,
                table_result.scanned, table_result.deleted, table_result.batches,
            )
        _LOGGER.info(
            "[purge_audit_logs] mode=%s batch_size=%d tables=%d scanned=%d deleted=%d "
            "elapsed=%.1fs",
            mode, args.batch_size, len(result.tables),
            result.scanned, result.deleted, elapsed,
        )
        return 0
    except Exception:
        _LOGGER.exception("[purge_audit_logs] failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
