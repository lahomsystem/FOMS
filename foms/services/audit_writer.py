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

캐시는 접근거부(T5, 60초)와 파일 열람(T6, 10분)이 **공유**한다 — 키 3요소의 action 이
용도를 구분하므로 오탐은 없지만, 파일 트래픽이 몰리면 LRU 상한 때문에 접근거부 키가 먼저
밀려날 수 있다. 그 결과는 "억제가 덜 되어 행이 더 남는 것"(감사 손실이 아니라 중복)이므로
안전한 방향의 degrade 다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Mapping

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

# 파일 열람(view) 전용 dedupe 창 — 스펙 §8 결정 ③. 접근거부(60초)와 **별도 파라미터**다:
# 같은 사용자가 같은 파일을 다시 여는 것(썸네일→원본, 새로고침, 뷰어 왕복)은 감사 가치가
# 없고 행만 불린다. download/presigned 는 의도적 1회 행위라 dedupe 하지 않는다.
ACCESS_VIEW_DEDUPE_WINDOW_SECONDS = 600.0

# additional_data(Text) 격납 상한 — 감사 컬럼이 비정상 payload 로 부풀지 않게 자른다.
ACCESS_ADDITIONAL_DATA_LIMIT = 2000

# security_logs.detail(JSONB) 격납 상한(직렬화 문자 수) — T8. 감사 1건이 수 MB JSONB 로
# 부푸는 것을 막는다. 초과분은 통째로 버리지 않고 ``truncated`` 플래그 dict 로 대체한다.
SECURITY_DETAIL_LIMIT = 4000

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


def normalize_security_detail(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """``security_logs.detail``(JSONB) 에 넣어도 안전한 dict 로 정규화한다(T8 SSOT).

    감사 payload 는 호출부가 만든 임의 dict 라 두 가지 사고를 낼 수 있다: ① JSON 직렬화
    불가 값(``datetime``·모델 객체)이 섞여 **원 요청이 커밋에서 죽는 것**, ② 비정상적으로
    큰 payload 가 JSONB 컬럼을 부풀리는 것. 둘 다 감사 부가정보 하나 때문에 업무를 죽이는
    것이므로 여기서 흡수한다(스펙 §3 원칙 4).

    직렬화는 ``json.dumps(default=str)`` 왕복으로 검증한다 — 통과한 결과만 돌려주므로
    호출부는 "이 dict 는 반드시 저장 가능"을 보장받는다.

    :param payload: 격납할 dict(``None``/빈 dict 면 ``None`` 반환 — 컬럼 NULL).
    :return: JSON 직렬화가 보장된 dict, 또는 격납할 게 없으면 ``None``.
    """
    if not payload:
        return None
    limit = max(int(SECURITY_DETAIL_LIMIT), 1)
    try:
        encoded = json.dumps(dict(payload), ensure_ascii=False, default=str)
        if len(encoded) > limit:
            return {"truncated": True, "size": len(encoded)}
        return json.loads(encoded)
    except (TypeError, ValueError):
        # 직렬화 자체가 불가능한 payload(순환 참조 등) — 감사행은 남기되 detail 만 표식으로.
        logger.warning(
            "[AuditWriter] security_logs detail 직렬화 실패 — detail 을 표식으로 대체.",
            exc_info=True,
        )
        return {"unserializable": True}


def write_security_log_detached(
    message: str,
    user_id: int | None = None,
    *,
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: Mapping[str, Any] | None = None,
) -> bool:
    """``security_logs`` 에 **본 요청 트랜잭션과 무관하게** 1건을 즉시 커밋한다.

    :param message: 기록할 메시지(사람이 읽는 요약 — 의미 불변).
    :param user_id: 행위 주체 user id(비로그인/미상이면 ``None``).
    :param action: 행위 종류 태그(``ACCESS_DENIED``·``WRITE_BLOCKED`` 등, T8 구조화).
    :param target_type: 행위 대상 종류(``user`` 등). 대상이 없으면 ``None``.
    :param target_id: 행위 대상 PK. 대상이 없으면 ``None``.
    :param detail: 구조화 부가정보 dict(**비밀번호·PII 원문 금지**).
    :return: 커밋에 성공했으면 True, 실패(로그 후 포기)면 False.
    """
    from foms.services.datetime_kst import now_utc_naive
    from models import SecurityLog

    try:
        engine = get_audit_engine()
        stmt = SecurityLog.__table__.insert().values(
            user_id=user_id,
            message=message,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=normalize_security_detail(detail),
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


def _dedupe_decide(
    key: tuple[str, str, str], window_seconds: float | None = None
) -> tuple[bool, int]:
    """dedupe 창을 갱신하고 이번 호출을 기록할지 판정한다.

    창 안의 반복은 기록하지 않고 카운트만 누적한다. 창이 만료된 뒤 첫 호출이 누적분을
    함께 보고하며 새 창을 연다. 캐시는 용도별로 나누지 않고 공유한다 — 키 3요소 중
    action 이 용도(``policy:*`` vs ``FILE_VIEW``)를 구분하므로 충돌하지 않는다.

    :param key: (주체, 대상, action) dedupe 키.
    :param window_seconds: 이 호출에 쓸 창 길이(초). ``None`` 이면 접근거부 기본값
        ``DEDUPE_WINDOW_SECONDS``(60초). 파일 열람은 10분을 넘긴다(결정 ③).
    :return: ``(기록 여부, 직전 창에서 억제된 횟수)``.
    """
    window = float(DEDUPE_WINDOW_SECONDS if window_seconds is None else window_seconds)
    now = _monotonic()
    with _dedupe_lock:
        entry = _dedupe_cache.get(key)
        if entry is not None and (now - entry[0]) < window:
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
    structured_action: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> bool:
    """접근거부 1건을 dedupe 후 ``security_logs`` 에 독립 커밋한다.

    dedupe 키는 ``(user_id or ip, endpoint, action)`` 이다. 로그인 사용자는 user id 로,
    비로그인은 IP 로 묶어 스캐너/재시도 폭주가 감사 테이블을 채우는 것을 막는다.

    :param message: 기본 메시지(억제분이 있으면 ``... (억제 N회)`` 가 덧붙는다).
    :param user_id: 행위 주체 user id(없으면 ``ip`` 가 dedupe 주체가 된다).
    :param ip: 요청 IP(``user_id`` 부재 시 dedupe 주체).
    :param endpoint: Flask endpoint 이름(dedupe 축).
    :param action: **dedupe 축** 태그(예: ``policy:CODE``·``write-guard:reason``).
        열 이름과 겹치지만 의미가 다르다 — 저장되는 ``security_logs.action`` 은
        ``structured_action`` 이다(기존 dedupe 계약을 깨지 않으려 이름을 분리했다).
    :param structured_action: ``security_logs.action`` 에 저장할 행위 종류(T8 구조화).
    :param detail: ``security_logs.detail`` 에 저장할 부가정보(endpoint·reason 등).
        억제분이 있으면 ``suppressed`` 키가 **복사본에** 추가된다(호출부 dict 무변경).
    :return: 이번 호출로 실제 행을 기록했으면 True, 억제/실패면 False.
    """
    subject = str(user_id) if user_id is not None else (ip or "-")
    should_write, suppressed = _dedupe_decide((subject, endpoint or "-", action))
    if not should_write:
        return False
    text = f"{message} (억제 {suppressed}회)" if suppressed else message
    payload = dict(detail) if detail else {}
    if suppressed:
        payload["suppressed"] = suppressed
    return write_security_log_detached(
        text,
        user_id=user_id,
        action=structured_action,
        detail=payload or None,
    )


def _encode_additional_data(payload: Mapping[str, Any] | None) -> str | None:
    """감사 payload 를 ``access_logs.additional_data``(Text) 용 JSON 문자열로 만든다.

    직렬화 불가 값은 ``default=str`` 로 흡수한다 — 감사 보조 정보 하나 때문에 파일 응답이
    죽으면 안 되기 때문이다(스펙 §3 원칙 4).

    ``ACCESS_ADDITIONAL_DATA_LIMIT`` 초과분은 **문자열 값을 잘라** 줄인다. 인코딩 결과를
    그냥 자르면 깨진 JSON 이 남아 조회 화면 없는 이 원장(SQL 전용)을 아예 못 읽게 되므로,
    어떤 경로로도 **유효한 JSON** 만 반환한다(잘렸으면 ``truncated`` 플래그).

    :param payload: 격납할 dict(``None``/빈 dict 면 기록 생략).
    :return: JSON 문자열, 또는 격납할 게 없으면 ``None``.
    """
    if not payload:
        return None
    limit = max(int(ACCESS_ADDITIONAL_DATA_LIMIT), 1)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) <= limit:
        return encoded

    head = max(limit // 8, 32)
    trimmed: dict[str, Any] = {
        key: (value[:head] if isinstance(value, str) else value)
        for key, value in payload.items()
    }
    trimmed["truncated"] = True
    encoded = json.dumps(trimmed, ensure_ascii=False, sort_keys=True, default=str)
    return encoded if len(encoded) <= limit else json.dumps({"truncated": True})


def write_access_log_detached(
    action: str,
    *,
    user_id: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    additional_data: Mapping[str, Any] | None = None,
) -> bool:
    """``access_logs`` 에 **본 요청 트랜잭션과 무관하게** 1건을 즉시 커밋한다.

    ``write_security_log_detached`` 와 동일 계약이다(전용 engine · ``engine.begin()``
    Core INSERT · ``SQLAlchemyError`` 만 catch · 실패는 로그 후 fail-open). 파일 라우트는
    GET 이라 본 트랜잭션 commit 이 없어 동승 기록이 소실되므로 독립 커밋이 필수다.

    :param action: 접근 종류 태그(``FILE_VIEW``·``FILE_PRESIGNED``·``FILE_DOWNLOAD``).
    :param user_id: 행위 주체 user id(비로그인/미상이면 ``None``).
    :param ip: 요청 IP(``request.remote_addr``).
    :param user_agent: 요청 User-Agent 원문.
    :param additional_data: 부가 정보 dict(**PII 금지** — 파일 key·주문 id·파일명만).
    :return: 커밋에 성공했으면 True, 실패(로그 후 포기)면 False.
    """
    from foms.services.datetime_kst import now_utc_naive
    from models import AccessLog

    try:
        engine = get_audit_engine()
        stmt = AccessLog.__table__.insert().values(
            user_id=user_id,
            action=action,
            ip_address=ip,
            user_agent=user_agent,
            additional_data=_encode_additional_data(additional_data),
            timestamp=now_utc_naive(),
        )
        with engine.begin() as conn:
            conn.execute(stmt)
    except SQLAlchemyError:
        # fail-open: 감사 쓰기 실패가 파일 응답을 죽이면 안 된다(스펙 §3 원칙 4). 단, 반드시 로그.
        logger.warning(
            "[AuditWriter] access_logs 독립 기록 실패 — 요청은 계속 진행(fail-open).",
            exc_info=True,
        )
        return False
    return True


def record_file_access(
    action: str,
    *,
    storage_key: str,
    user_id: int | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    order_id: int | None = None,
    dedupe_window_seconds: float | None = None,
) -> bool:
    """파일 접근 1건을 (선택적 dedupe 후) ``access_logs`` 에 독립 커밋한다.

    dedupe 키는 ``(user_id or ip, storage_key, action)`` 이다 — 같은 주체가 같은 파일을
    같은 방식으로 반복 접근하는 것만 묶는다. **``dedupe_window_seconds`` 를 주지 않으면
    dedupe 하지 않는다**(download/presigned 는 매 건 기록이 정답).

    :param action: ``FILE_VIEW``·``FILE_PRESIGNED``·``FILE_DOWNLOAD``.
    :param storage_key: 접근 대상 object key(dedupe 축 겸 감사 대상 식별자).
    :param user_id: 행위 주체 user id(없으면 ``ip`` 가 dedupe 주체가 된다).
    :param ip: 요청 IP.
    :param user_agent: 요청 User-Agent 원문.
    :param order_id: canonical key 에서 파싱된 주문 id(파싱 불가면 ``None``).
    :param dedupe_window_seconds: dedupe 창(초). ``None`` 이면 dedupe 없음.
    :return: 이번 호출로 실제 행을 기록했으면 True, 억제/실패면 False.
    """
    suppressed = 0
    if dedupe_window_seconds is not None:
        subject = str(user_id) if user_id is not None else (ip or "-")
        should_write, suppressed = _dedupe_decide(
            (subject, storage_key, action), dedupe_window_seconds
        )
        if not should_write:
            return False

    payload: dict[str, Any] = {"storage_key": storage_key}
    if order_id is not None:
        payload["order_id"] = order_id
    if suppressed:
        payload["suppressed"] = suppressed
    return write_access_log_detached(
        action,
        user_id=user_id,
        ip=ip,
        user_agent=user_agent,
        additional_data=payload,
    )
