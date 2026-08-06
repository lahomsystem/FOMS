"""독립(detached) 감사 기록기 — AUDIT-LOG T5 신설, T6 공유.

**왜 독립 커밋인가.** 접근거부(403)·CSRF 차단·GET 계열 경로는 본 요청 트랜잭션을
commit 하지 않는다(``before_request`` 단계 차단 → 핸들러 미실행, teardown 은
``close`` 만 한다: 루트 ``db.py:99-102``). 감사 행을 본 세션에 태우면 요청이 끝날 때
같이 사라진다. 그래서 이 모듈은 **자기 트랜잭션으로 즉시 커밋**한다
(선례: :mod:`foms.services.channel_security` 의 ``engine.begin()`` nonce claim).

**왜 전용 engine 인가.** 메인 engine 은 프로세스당 pool 5 + overflow 5,
``pool_timeout`` 10초다(``db.py:52-55``). 요청 처리 도중 같은 engine 에서 커넥션을
한 번 더 checkout 하면 풀 고갈 시 10초 tail 을 만든다. 감사 쓰기는 절대 요청을
느리게 만들면 안 되므로 **pool 2 · overflow 0 · pool_timeout 0.5초** 전용 engine 을
따로 둔다. 커넥션을 못 얻으면 0.5초 안에 실패하고 조용히 포기한다(fail-open).
SQLite(pytest·로컬 실험)는 파일/메모리 DB 라 제2 engine 이 **다른 DB** 를 가리키므로
메인 engine 을 그대로 재사용한다. 이때 pysqlite 는 커넥션 단위 트랜잭션이고
``SingletonThreadPool`` 이 같은 스레드에 같은 커넥션을 내주므로, 감사 커밋이 그 시점의
세션 pending 변경까지 함께 커밋한다(실측). 진짜 트랜잭션 독립성은 PostgreSQL 전용
engine 에서만 성립하며 PG 레인 테스트가 그것을 증명한다 — SQLite 는 dev/테스트 한정
근사다.

**fail-open 규약.** 감사 쓰기 실패는 절대 전파하지 않는다. 실패는 반드시
``logger.warning(exc_info=True)`` 로 남긴다(AGENTS.md: 로깅 없는 fail-open 금지).

**dedupe 한계(v1).** 억제 캐시는 **프로세스 로컬**이다. gunicorn 2 worker 등
다중 프로세스 환경에서는 같은 (주체, endpoint, action) 연타가 프로세스 수만큼
기록될 수 있다(4 프로세스면 억제 효과 1/4). 또한 억제 카운트는 **창 만료 후 첫
후속 호출**이 보고하므로, 폭주가 그대로 끝나거나 캐시 상한 GC 로 키가 밀려나면 마지막
누적분은 보고되지 않는다. Redis 승격은 본 패킷 범위 밖이며 스펙 §4 T5 에서 v1 한계로
명시 수용했다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# 전용 감사 engine 풀 파라미터(스펙 §3-3). 메인 engine 과 절대 공유하지 않는다.
_AUDIT_POOL_SIZE = 2
_AUDIT_MAX_OVERFLOW = 0
_AUDIT_POOL_TIMEOUT = 0.5
_AUDIT_POOL_RECYCLE = 1800

# dedupe 창/캐시 상한. 테스트는 monkeypatch 로 좁힌다(모듈 전역 읽기 시점 참조).
DEDUPE_WINDOW_SECONDS = 60.0
DEDUPE_CACHE_LIMIT = 2048

_engine: Engine | None = None
_engine_lock = threading.Lock()

# key -> [window_start_monotonic, suppressed_count]. LRU(OrderedDict) — 상한 초과 시
# 가장 오래 안 쓰인 키부터 버린다.
_dedupe_cache: "OrderedDict[tuple[str, str, str], list[float]]" = OrderedDict()
_dedupe_lock = threading.Lock()


def _monotonic() -> float:
    """dedupe 창 계산용 단조 시계(테스트가 monkeypatch 하는 단일 지점)."""
    return time.monotonic()


def _build_audit_engine() -> Engine:
    """전용 감사 engine 을 생성한다(sqlite 는 메인 engine 재사용).

    메인 engine 과 동일한 DSN·psycopg2 creator 규약을 쓰되 풀만 소형으로 잡는다
    (``db.py`` 가 percent-encoding 회피를 위해 creator 를 쓰므로 그대로 따른다).

    :return: PostgreSQL 이면 신규 소형 engine, SQLite 면 메인 engine 그 자체.
    """
    from db import DB_URL, engine as main_engine

    url = str(DB_URL)
    if "sqlite" in url:
        # 별도 engine 은 별도 :memory: DB 를 뜻한다 — 로컬/테스트는 메인 재사용.
        return main_engine

    kwargs = {
        "pool_pre_ping": True,
        "echo": False,
        "pool_size": _AUDIT_POOL_SIZE,
        "max_overflow": _AUDIT_MAX_OVERFLOW,
        "pool_timeout": _AUDIT_POOL_TIMEOUT,
        "pool_recycle": _AUDIT_POOL_RECYCLE,
    }
    if url.startswith("postgresql"):
        import psycopg2

        from foms.services.db_url_resolver import (
            postgresql_psycopg2_connect_kwargs_from_url,
        )

        connect_kw = postgresql_psycopg2_connect_kwargs_from_url(url)

        def _creator():
            return psycopg2.connect(**connect_kw)

        return create_engine("postgresql+psycopg2://", creator=_creator, **kwargs)
    return create_engine(url, **kwargs)


def get_audit_engine() -> Engine:
    """전용 감사 engine 의 lazy 싱글톤을 반환한다(double-checked lock).

    :return: 감사 전용 :class:`~sqlalchemy.engine.Engine` (SQLite 는 메인 engine).
    """
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            _engine = _build_audit_engine()
    return _engine


def reset_audit_engine() -> None:
    """감사 engine 싱글톤을 폐기한다(테스트/DSN 교체 전용)."""
    global _engine
    with _engine_lock:
        engine, _engine = _engine, None
    if engine is not None:
        from db import engine as main_engine

        if engine is not main_engine:
            engine.dispose()


def write_security_log_detached(message: str, user_id: int | None = None) -> bool:
    """``security_logs`` 에 **본 요청 트랜잭션과 무관하게** 1건을 즉시 커밋한다.

    :param message: 기록할 메시지(자유 텍스트 1컬럼 — 구조화는 T8 소관).
    :param user_id: 행위 주체 user id(비로그인/미상이면 ``None``).
    :return: 커밋에 성공했으면 True, 실패(로그 후 포기)면 False.
    """
    from foms.services.datetime_kst import now_utc_naive
    from models import SecurityLog

    try:
        engine = get_audit_engine()
        stmt = SecurityLog.__table__.insert().values(
            user_id=user_id,
            message=message,
            timestamp=now_utc_naive(),
        )
        with engine.begin() as conn:
            conn.execute(stmt)
    except SQLAlchemyError:
        # fail-open: 감사 쓰기 실패가 요청을 죽이면 안 된다(스펙 §3 원칙 4). 단, 반드시 로그.
        logger.warning(
            "[AuditWriter] security_logs 독립 기록 실패 — 요청은 계속 진행(fail-open).",
            exc_info=True,
        )
        return False
    return True


def _gc_dedupe_locked() -> None:
    """캐시 상한 초과분을 오래된(LRU) 키부터 제거한다. ``_dedupe_lock`` 보유 상태 전용."""
    limit = max(int(DEDUPE_CACHE_LIMIT), 1)
    while len(_dedupe_cache) > limit:
        _dedupe_cache.popitem(last=False)


def _dedupe_decide(key: tuple[str, str, str]) -> tuple[bool, int]:
    """dedupe 창을 갱신하고 이번 호출을 기록할지 판정한다.

    창(``DEDUPE_WINDOW_SECONDS``) 안의 반복은 기록하지 않고 카운트만 누적한다. 창이
    만료된 뒤 첫 호출이 누적분을 함께 보고하며 새 창을 연다.

    :param key: (주체, endpoint, action) dedupe 키.
    :return: ``(기록 여부, 직전 창에서 억제된 횟수)``.
    """
    now = _monotonic()
    with _dedupe_lock:
        entry = _dedupe_cache.get(key)
        if entry is not None and (now - entry[0]) < float(DEDUPE_WINDOW_SECONDS):
            entry[1] += 1
            _dedupe_cache.move_to_end(key)
            return False, 0
        suppressed = int(entry[1]) if entry is not None else 0
        _dedupe_cache[key] = [now, 0]
        _dedupe_cache.move_to_end(key)
        _gc_dedupe_locked()
    return True, suppressed


def reset_dedupe_cache() -> None:
    """dedupe 캐시를 비운다(테스트 격리 전용 — 운영 호출자 없음)."""
    with _dedupe_lock:
        _dedupe_cache.clear()


def dedupe_cache_size() -> int:
    """현재 dedupe 캐시에 살아 있는 키 수(상한 GC 검증용)."""
    with _dedupe_lock:
        return len(_dedupe_cache)


def record_access_denied(
    message: str,
    *,
    user_id: int | None = None,
    ip: str | None = None,
    endpoint: str | None = None,
    action: str = "",
) -> bool:
    """접근거부 1건을 dedupe 후 ``security_logs`` 에 독립 커밋한다.

    dedupe 키는 ``(user_id or ip, endpoint, action)`` 이다. 로그인 사용자는 user id 로,
    비로그인은 IP 로 묶어 스캐너/재시도 폭주가 감사 테이블을 채우는 것을 막는다.

    :param message: 기본 메시지(억제분이 있으면 ``... (억제 N회)`` 가 덧붙는다).
    :param user_id: 행위 주체 user id(없으면 ``ip`` 가 dedupe 주체가 된다).
    :param ip: 요청 IP(``user_id`` 부재 시 dedupe 주체).
    :param endpoint: Flask endpoint 이름(dedupe 축).
    :param action: 거부 종류 태그(예: ``policy:...``·``write-guard:...``).
    :return: 이번 호출로 실제 행을 기록했으면 True, 억제/실패면 False.
    """
    subject = str(user_id) if user_id is not None else (ip or "-")
    should_write, suppressed = _dedupe_decide((subject, endpoint or "-", action))
    if not should_write:
        return False
    text = f"{message} (억제 {suppressed}회)" if suppressed else message
    return write_security_log_detached(text, user_id=user_id)
