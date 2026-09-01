"""HB-S1 — 테이블 단위 쓰기 버전 카운터 (Redis INCR, 읽는 쪽 없음).

셸 하트비트 재검증 스펙(`docs/specs/2026-09-01-shell-heartbeat-cheap-revalidation_SPEC.md`)
의 S1 단계다. 프래그먼트 라우트가 **렌더 전에** 조건부 응답을 끝내려면 "본문이 읽는
테이블이 마지막으로 바뀐 시점"을 값싸게 알아야 한다. 이 모듈은 그 신호원만 만든다 —
읽는 쪽(ETag 키 조립·304 단축)은 S2 이후다.

왜 mutation intent 가 아니라 세션 훅인가
-----------------------------------------
S0 전수조사(원장 `docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md` §P7) 결과
163개 쓰기 경로 중 :func:`foms.services.orders.revision.execute_order_mutation` 를 경유하는
것은 51개(31%)뿐이다. intent 를 신호원으로 쓰면 69% 가 카운터를 못 올려 **낡은 304** 가
나간다(지금 결함보다 나쁘다). 저장소가 이미 답을 적어뒀다 —
`foms/services/order_date_sync.py` 의 `register_date_sync_listener` docstring:
"이 훅은 모든 쓰기가 통과하는 유일 지점이라 … 라우트/서비스별 emit 은 두지 않는다".

따라서 신호원은 **전역 SQLAlchemy 세션 훅**이고, 키는 패밀리가 아니라 **테이블 이름**이다.
테이블 단위로 잡으면 `users`·`system_settings` 처럼 대시보드 패밀리 개념 밖인 축도 같은
장치 하나로 덮인다.

`after_flush` 를 쓰는 이유
--------------------------
`before_flush` 리스너는 서로의 결과를 못 본다. 일정 행의 유일한 생산자
(`order_date_sync.py:271` 의 ``OrderScheduleDate(...)``)가 바로 `before_flush` 훅이라,
우리 리스너가 먼저 등록되면 그 신규 행을 놓친다. `after_flush` 는 모든 `before_flush`
훅이 끝난 뒤 도는데 `session.new/dirty/deleted` 는 아직 flush 이전 상태로 남아 있어
(SQLAlchemy 계약) 안전하게 관측할 수 있다.

남는 구멍 = ORM 을 우회하는 쓰기(query-level ``update()``/``delete()``, raw DML,
``bulk_*_mappings``). 그 경로는 :func:`mark_tables_dirty` 로 **명시 등재**하고,
`tools/harness/orm_bypass_write_scan.py` 가 새 우회 쓰기를 red 로 잡는다.

Redis 가 없거나 오류면 fail-safe: 카운터는 안 올라가고 :func:`get_table_versions` 가
``None`` 을 돌려준다. 읽는 쪽은 그때 "버전 키를 만들 수 없다"로 보고 지금 동작(렌더 후
본문 ETag)으로 간다 — 느릴 뿐 정확하다.
"""

from __future__ import annotations

import logging
from typing import Any, Final, Iterable

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_VERSION",
    "TABLE_VERSION_KEY_PREFIX",
    "VERSIONED_TABLES",
    "SESSION_DIRTY_TABLES_KEY",
    "table_version_key",
    "bump_table_versions",
    "get_table_versions",
    "mark_tables_dirty",
    "collect_dirty_table_names",
    "register_table_version_listener",
    "is_table_version_listener_registered",
]

KEY_VERSION: Final[str] = "v1"
TABLE_VERSION_KEY_PREFIX: Final[str] = f"foms:tabver:{KEY_VERSION}"

#: 하트비트 프래그먼트 본문이 읽는 테이블(S0 조사 결과). 여기 없는 테이블의 쓰기는
#: 카운터를 올리지 않는다 — access_logs 처럼 요청마다 늘어나는 감사 테이블까지 세면
#: Redis 왕복만 늘고 화면 신선도에는 아무 기여가 없다. 화면이 새 테이블을 읽기
#: 시작하면 **여기에 먼저 등재**해야 그 화면을 렌더 전 304 대상에 넣을 수 있다.
VERSIONED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "orders",
        "order_schedule_dates",
        "order_attachments",
        "users",
        "system_settings",
        "order_assignments",
    }
)

#: 커밋 전까지 더러운 테이블 이름을 모아두는 ``Session.info`` 키.
SESSION_DIRTY_TABLES_KEY: Final[str] = "foms_table_version_dirty_tables"

_listener_registered: bool = False


def table_version_key(table: str) -> str:
    """테이블 이름 → Redis 카운터 키.

    Args:
        table: 테이블 이름(``Order.__tablename__`` 등).

    Returns:
        ``foms:tabver:v1:<table>`` 형태의 Redis 키.
    """
    return f"{TABLE_VERSION_KEY_PREFIX}:{table}"


def _redis() -> Any | None:
    """대시보드 캐시와 **같은** Redis 클라이언트(프로세스당 1개)를 돌려준다.

    새 저장소·새 연결 풀을 만들지 않는다. 클라이언트 초기화 실패 시 ``None``
    (`dashboard_cache.get_dashboard_redis` 가 경고 로그 후 고정 ``None``).

    Returns:
        Redis 클라이언트 또는 ``None``.
    """
    try:
        from foms.services.common.dashboard_cache import get_dashboard_redis

        return get_dashboard_redis()
    except Exception:
        logger.warning("[TableVer] redis client unavailable", exc_info=True)
        return None


def _tracked(tables: Iterable[str]) -> list[str]:
    """추적 대상 테이블만 중복 없이 정렬해 돌려준다."""
    return sorted({t for t in tables if t in VERSIONED_TABLES})


def bump_table_versions(*tables: str) -> int:
    """추적 대상 테이블의 버전 카운터를 즉시 ``INCR`` 한다.

    Redis 가 없거나 오류를 던지면 조용히 0 을 돌려준다(경고 로그만) — 이미 커밋된
    업무 변경을 카운터 실패로 되돌릴 수는 없다. 그 대가는 "그 화면이 잠깐 낡을 수
    있다"가 아니라 "읽는 쪽이 아예 버전 키를 못 만든다"이다(:func:`get_table_versions`
    가 같은 상황에서 ``None`` 을 돌려주므로 조건부 단축이 통째로 꺼진다).

    Args:
        *tables: 테이블 이름들. 추적 대상 밖 이름은 무시된다.

    Returns:
        실제로 증가시킨 테이블 수(실패·비대상은 0).
    """
    names = _tracked(tables)
    if not names:
        return 0
    client = _redis()
    if client is None:
        return 0
    try:
        pipe = client.pipeline()
        for name in names:
            pipe.incr(table_version_key(name))
        pipe.execute()
        return len(names)
    except Exception:
        logger.warning("[TableVer] bump failed (non-fatal): %s", names, exc_info=True)
        return 0


def get_table_versions(tables: Iterable[str]) -> dict[str, int] | None:
    """테이블별 현재 버전값을 한 번의 ``MGET`` 으로 읽는다.

    Args:
        tables: 읽을 테이블 이름들(추적 대상 밖은 무시).

    Returns:
        ``{테이블: 버전}`` 딕셔너리(키가 없으면 0). Redis 가 없거나 오류면 ``None``
        — 호출부는 "버전 키를 만들 수 없다"로 읽고 조건부 단축을 포기해야 한다.
    """
    names = _tracked(tables)
    if not names:
        return {}
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.mget([table_version_key(n) for n in names])
    except Exception:
        logger.warning("[TableVer] mget failed (non-fatal): %s", names, exc_info=True)
        return None
    out: dict[str, int] = {}
    for name, value in zip(names, raw or []):
        try:
            out[name] = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
    return out


def mark_tables_dirty(session: Any, *tables: str) -> None:
    """ORM 을 우회한 쓰기를 **커밋 시점 증가 대상**으로 등재한다.

    query-level ``update()``/``delete()``, raw ``execute(text(...))`` DML,
    ``bulk_insert_mappings`` 는 ORM 엔티티 상태를 거치지 않아 세션 훅이 못 본다.
    그런 경로는 이 함수로 테이블을 직접 등재한다. 등재만 하고 증가는 하지 않으므로
    **커밋이 실패하면 카운터도 안 올라간다**(:func:`bump_table_versions` 직접 호출과
    다른 점이자, 이 함수를 쓰는 이유다).

    한 가지 예외: 등재만 하고 DB 작업이 하나도 없으면 트랜잭션이 시작되지 않아
    SQLAlchemy 가 ``after_soft_rollback`` 을 내지 않는다 — 그 등재분은 다음 커밋까지
    남는다. 과다 증가(재렌더 한 번)라 안전한 방향이다.

    Args:
        session: 해당 쓰기가 속한 SQLAlchemy 세션(``scoped_session`` 도 가능).
        *tables: 바뀐 테이블 이름들.
    """
    names = _tracked(tables)
    if not names:
        return
    info = getattr(session, "info", None)
    if info is None:
        return
    bucket = info.get(SESSION_DIRTY_TABLES_KEY)
    if bucket is None:
        bucket = set()
        info[SESSION_DIRTY_TABLES_KEY] = bucket
    bucket.update(names)


def _entity_table_name(obj: Any) -> str | None:
    """ORM 인스턴스 → 테이블 이름(매핑되지 않은 객체는 ``None``)."""
    table = getattr(obj, "__table__", None)
    name = getattr(table, "name", None)
    if isinstance(name, str):
        return name
    tablename = getattr(obj, "__tablename__", None)
    return tablename if isinstance(tablename, str) else None


def collect_dirty_table_names(session: Any) -> set[str]:
    """flush 대상 엔티티에서 추적 대상 테이블 이름을 모은다.

    ``session.dirty`` 는 "UPDATE 가 날 수도 있는" 후보라 실제 변경이 없는 객체도
    들어온다. 과다 증가는 재렌더 한 번 낭비로 끝나지만 누락은 낡은 304 를 만들므로
    후보를 그대로 받는다(과무효화 우선).

    Args:
        session: SQLAlchemy 세션.

    Returns:
        추적 대상 테이블 이름 집합.
    """
    names: set[str] = set()
    for bucket in (session.new, session.dirty, session.deleted):
        for obj in bucket:
            name = _entity_table_name(obj)
            if name in VERSIONED_TABLES:
                names.add(name)
    return names


def register_table_version_listener() -> None:
    """테이블 버전 카운터를 올리는 전역 세션 훅을 등록한다(멱등).

    - ``after_flush``: 더러운 엔티티의 테이블 이름을 ``Session.info`` 에 누적한다.
      한 트랜잭션이 여러 번 flush 해도 합집합으로 쌓인다.
    - ``after_commit``: 누적분을 꺼내 ``INCR`` 한다. 커밋이 성공한 뒤에만 돌므로
      롤백된 변경은 카운터를 올리지 않는다.
    - ``after_soft_rollback``: 누적분을 폐기해 다음 트랜잭션으로 새지 않게 한다.

    **web 과 worker 양쪽 프로세스에서 모두 불려야 한다.** worker 는
    ``rq worker default`` 로 뜨느라 ``app.py`` 를 import 하지 않아
    :func:`foms.services.app_init.run_auto_init` 가 돌지 않는다(Procfile 참조).
    그래서 worker 진입 모듈(:mod:`foms.services.jobs.tasks`)도 import 시점에 이
    함수를 부른다. 등록이 한쪽만 되면 썸네일·지오코딩·네이버 워터마크 쓰기가
    카운터를 못 올려 그 축을 읽는 화면이 낡은 304 를 받는다.
    """
    global _listener_registered
    if _listener_registered:
        return

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    @event.listens_for(Session, "after_flush")
    def _tabver_collect(session, flush_context):
        names = collect_dirty_table_names(session)
        if not names:
            return
        bucket = session.info.get(SESSION_DIRTY_TABLES_KEY)
        if bucket is None:
            session.info[SESSION_DIRTY_TABLES_KEY] = set(names)
        else:
            bucket.update(names)

    @event.listens_for(Session, "after_commit")
    def _tabver_bump(session):
        names = session.info.pop(SESSION_DIRTY_TABLES_KEY, None)
        if not names:
            return
        try:
            bump_table_versions(*names)
        except Exception:
            # fail-safe: 카운터 실패가 이미 커밋된 업무 변경을 되돌릴 수는 없다.
            logger.warning("[TableVer] after_commit bump failed", exc_info=True)

    @event.listens_for(Session, "after_soft_rollback")
    def _tabver_drop(session, previous_transaction):
        session.info.pop(SESSION_DIRTY_TABLES_KEY, None)

    _listener_registered = True


def is_table_version_listener_registered() -> bool:
    """이 프로세스에 세션 훅이 등록됐는지(배선 계약 테스트·진단용).

    리셋 함수는 일부러 두지 않는다 — SQLAlchemy 리스너는 ``Session`` 클래스 전역이라
    플래그만 되돌리면 재등록 시 훅이 두 벌 붙어 카운터가 2씩 오른다.
    """
    return _listener_registered
