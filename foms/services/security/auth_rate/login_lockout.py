"""로그인 실패 잠금 + 로그인 전용 rate bucket 키 (AUTH-LOGIN-LOCK-01).

쓰기 경로 209 라우트는 ``before_request`` SSOT 한 곳이 판정하는데, 정작 가장 흔한
공격면인 **로그인에는 한도도 잠금도 0** 이었다(2026-09-06 검토 R7). 이 모듈이 그 두
가지의 공통 기반을 한 자리에 정의한다.

**버킷 키 = 아이디 + canonical client IP**. 어느 한쪽만 쓰면 안 되는 이유가 대칭으로 있다:

* 아이디만 쓰면 외부인이 남의 아이디로 실패를 쌓아 그 계정을 마음대로 잠글 수 있다(계정 DoS).
* IP 만 쓰면 사무실 PC·현장 태블릿·iOS 웹뷰가 같은 회선을 쓰는 회사라 한 사람의 오타가
  전 직원을 통째로 잠근다.

IP 는 :func:`flask_limiter.util.get_remote_address` (= ProxyFix 가 세운
``request.remote_addr``) 만 쓴다. 원시 ``X-Forwarded-For``/``X-Real-IP`` 를 직접 파싱하면
공격자가 왼쪽 항목을 넣어 자기 버킷을 위조할 수 있다 — ``foms/services/rate_limit.py`` 의
PROXY-01 주석과 같은 결정이다.

**저장소는 limiter 가 이미 쥔 것을 그대로 쓴다**(REDIS_URL 이 있으면 Redis, 없으면 메모리).
연결 풀을 하나 더 만들지 않으므로 replica 여러 대가 같은 카운터를 보고, 테스트는
``limiter.reset()`` 한 번으로 격리된다.

**fail-open 이 규약이다.** 저장소가 죽어 카운터를 못 읽으면 로그인을 **막지 않고**
``logger.warning`` 을 남긴다 — 관측 배선이 로그인을 막는 것은 더 나쁜 실패다. 다만 조용히
넘기지는 않는다(``except ...: pass`` 금지). 잡는 예외는 저장소가 스스로 밝히는
``Storage.base_exceptions`` 뿐이라, 우리 쪽 프로그래밍 오류(TypeError 등)는 그대로 시끄럽게 죽는다.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional

from flask import current_app, has_app_context, request
from flask_limiter.util import get_remote_address

# 본문 상한 매니페스트 SSOT. 여기서 숫자를 복제하면 /login 상한이 바뀔 때 조용히 어긋난다.
from foms.platform.request_limits import resolve_body_cap

logger = logging.getLogger(__name__)

__all__ = [
    "clear_login_failures",
    "is_login_locked",
    "login_bucket_key",
    "login_lockout_seconds",
    "login_lockout_threshold",
    "login_lockout_window_seconds",
    "register_login_failure",
]

#: 연속 실패 임계. 8 = 사람의 오타 습관 밖이다(기억하는 비밀번호 2~3개를 두 번씩 돌려도 6회).
THRESHOLD_ENV = "FOMS_LOGIN_LOCKOUT_THRESHOLD"
DEFAULT_THRESHOLD = 8

#: 실패를 누적하는 창(초). 900 = 15분. 창이 지나면 카운터가 통째로 사라진다.
WINDOW_SECONDS_ENV = "FOMS_LOGIN_LOCKOUT_WINDOW_SECONDS"
DEFAULT_WINDOW_SECONDS = 900

#: 잠금 유지 시간(초). 900 = 15분. 온라인 추측을 시간당 32회로 눌러 무의미하게 만들 만큼
#: 길고, 현장 태블릿 사용자가 관리자 해제 티켓을 끊지 않아도 될 만큼 짧다(운영 부담 0).
LOCK_SECONDS_ENV = "FOMS_LOGIN_LOCKOUT_SECONDS"
DEFAULT_LOCK_SECONDS = 900

#: 버킷 키 접두어. flask-limiter 는 자기 키를 따로 namespacing 하므로 충돌하지 않는다.
_KEY_PREFIX = "foms-login"

#: 로그인 폼 인코딩. 이 밖(multipart 등)은 아이디를 엿보지 않는다.
_FORM_MIMETYPE = "application/x-www-form-urlencoded"


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """정수 env 설정을 읽는다(미설정·파싱 실패면 기본값).

    호출 시점에 읽는다 — 운영 중 값을 바꾸려고 재배포를 하지 않아도 되고, 테스트가
    monkeypatch 로 임계를 낮춰 빠르게 돌 수 있다.

    :param name: 환경변수 이름.
    :param default: 미설정/파싱 실패 시 쓸 값.
    :param minimum: 하한. 설정값이 이보다 작으면 하한으로 올린다(0·음수로 잠금을 꺼서
        조용히 무력화하는 것을 막는다).
    :return: 적용할 정수.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r 를 정수로 읽지 못했다 — 기본값 %d 을 쓴다", name, raw, default)
        return default
    return max(minimum, value)


def login_lockout_threshold() -> int:
    """잠금이 걸리는 연속 실패 횟수(env ``FOMS_LOGIN_LOCKOUT_THRESHOLD``).

    :return: 임계 횟수(최소 1).
    """
    return _env_int(THRESHOLD_ENV, DEFAULT_THRESHOLD)


def login_lockout_window_seconds() -> int:
    """실패를 누적하는 창의 길이(초, env ``FOMS_LOGIN_LOCKOUT_WINDOW_SECONDS``).

    :return: 창 길이(초, 최소 1).
    """
    return _env_int(WINDOW_SECONDS_ENV, DEFAULT_WINDOW_SECONDS)


def login_lockout_seconds() -> int:
    """잠금 유지 시간(초, env ``FOMS_LOGIN_LOCKOUT_SECONDS``).

    :return: 잠금 시간(초, 최소 1).
    """
    return _env_int(LOCK_SECONDS_ENV, DEFAULT_LOCK_SECONDS)


def _peek_form_username() -> str:
    """limiter 의 pre-dispatch 훅에서 아이디만 **안전하게** 엿본다.

    ``Limiter._check_request_limit`` 는 ``before_request`` 목록의 **첫 번째**라
    ``foms/platform/request_limits.py`` 의 본문 상한 가드보다 먼저 돈다. 여기서 아무 조건
    없이 ``request.form`` 을 건드리면 /login 의 16 KiB pre-parse 상한을 건너뛰고 전역
    50 MiB 까지 파싱돼, 상한을 둔 이유(메모리·temp 파일 DoS)가 통째로 무너진다.

    그래서 **폼 인코딩이고 선언된 Content-Length 가 그 라우트 상한 이내일 때만** 파싱한다.
    그 밖(청크 전송으로 길이를 숨긴 요청·초과 선언·multipart)은 아이디 없이 IP 만으로
    버킷을 잡고, 본문은 기존 가드가 413 으로 끊는다 — 관측이 방어를 깎지 않는다.

    :return: 폼에서 읽은 아이디. 엿보면 안 되는 요청이거나 값이 없으면 빈 문자열.
    """
    if request.mimetype != _FORM_MIMETYPE:
        return ""
    declared = request.content_length
    cap = resolve_body_cap(request.path or "")
    if declared is None or cap is None or declared > cap.max_body_bytes:
        return ""
    return request.form.get("username") or ""


def login_bucket_key(username: Optional[str] = None) -> str:
    """로그인 시도의 rate bucket 키 — ``foms-login:<아이디해시>:<IP>``.

    아이디는 **정규화하지 않는다**. 대소문자·공백을 접으면 서로 다른 계정이 카운터를
    공유해 계정 DoS 가 생기지만, 접지 않으면 인증에 성공할 수 없는 변형이 자기 카운터를
    새로 쓸 뿐이라 공격자가 얻는 게 없다. 해시를 쓰는 이유는 두 가지다 — 아이디 원문이
    Redis 키와 운영 로그에 남지 않고, 아이디에 ``:`` 가 들어가도 구분자가 깨지지 않는다.

    :param username: 시도에 쓰인 아이디 원문. ``None`` 이면 요청 폼에서 안전하게 엿본다
        (limiter 의 ``key_func`` 는 인자를 받지 않으므로 이 기본값 경로로 들어온다).
    :return: 아이디+IP 조합 키. 아이디를 못 읽으면 ``foms-login:-:<IP>``(IP 전용 버킷).
    """
    raw = username if username is not None else _peek_form_username()
    address = get_remote_address()
    if not raw:
        return f"{_KEY_PREFIX}:-:{address}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_KEY_PREFIX}:{digest}:{address}"


def _fail_key(username: str) -> str:
    """연속 실패 카운터 키.

    :param username: 시도에 쓰인 아이디 원문.
    :return: 저장소 키 문자열.
    """
    return f"{login_bucket_key(username)}:fail"


def _lock_key(username: str) -> str:
    """잠금 마커 키(존재하면 잠긴 상태).

    :param username: 시도에 쓰인 아이디 원문.
    :return: 저장소 키 문자열.
    """
    return f"{login_bucket_key(username)}:lock"


def _limiter_storage() -> Optional[Any]:
    """현재 앱의 limiter 저장소(:class:`limits.storage.Storage`)를 돌려준다.

    limiter 가 이미 쥔 저장소를 재사용한다 — Redis 연결 풀을 하나 더 만들지 않고,
    ``limiter.reset()`` 한 번으로 테스트 격리가 끝난다.

    :return: 저장소 인스턴스. 앱 컨텍스트 밖이거나 limiter 미초기화면 ``None``.
    """
    if not has_app_context():
        return None
    for limiter in current_app.extensions.get("limiter") or ():
        try:
            storage = limiter.storage
        except AssertionError:
            # flask-limiter 의 storage property 는 미초기화 상태를 assert 로 표현한다.
            continue
        if storage is not None:
            return storage
    return None


def _incr(storage: Any, key: str, expiry: int) -> Optional[int]:
    """카운터를 1 올리고 **올린 뒤의 값**을 돌려준다.

    :param storage: limiter 저장소.
    :param key: 카운터 키.
    :param expiry: 키 수명(초). 첫 증가 때만 적용된다(고정 창).
    :return: 증가 후 값. 저장소 장애면 ``None``(fail-open — 호출부는 잠그지 않는다).
    """
    try:
        return int(storage.incr(key, expiry))
    except storage.base_exceptions:
        logger.warning(
            "로그인 잠금 카운터 증가 실패 (key=%s) — 잠금 없이 진행한다(fail-open)",
            key,
            exc_info=True,
        )
        return None


def _get(storage: Any, key: str) -> Optional[int]:
    """카운터 현재 값을 읽는다.

    :param storage: limiter 저장소.
    :param key: 카운터 키.
    :return: 현재 값(없으면 0). 저장소 장애면 ``None``(fail-open).
    """
    try:
        return int(storage.get(key))
    except storage.base_exceptions:
        logger.warning(
            "로그인 잠금 상태 조회 실패 (key=%s) — 잠기지 않은 것으로 본다(fail-open)",
            key,
            exc_info=True,
        )
        return None


def _clear(storage: Any, key: str) -> None:
    """카운터를 지운다(실패해도 로그인 흐름을 막지 않는다).

    :param storage: limiter 저장소.
    :param key: 카운터 키.
    :return: 없음.
    """
    try:
        storage.clear(key)
    except storage.base_exceptions:
        logger.warning("로그인 잠금 카운터 삭제 실패 (key=%s)", key, exc_info=True)


def is_login_locked(username: str) -> bool:
    """이 (아이디, IP) 쌍이 지금 잠겨 있는가.

    :param username: 시도에 쓰인 아이디 원문.
    :return: 잠겨 있으면 ``True``. 저장소가 없거나 조회에 실패하면 ``False``(fail-open).
    """
    storage = _limiter_storage()
    if storage is None:
        logger.warning("limiter 저장소가 없어 로그인 잠금을 판정할 수 없다(fail-open)")
        return False
    return bool(_get(storage, _lock_key(username)))


def register_login_failure(username: str) -> bool:
    """실패 1건을 세고, **이번 실패로 새로 잠겼는지** 알려준다.

    임계에 닿으면 잠금 마커를 세우고 실패 카운터는 비운다 — 잠금이 풀린 뒤 다시 임계만큼의
    기회로 시작하게 하려는 것이다(PAM faillock 과 같은 모양). 잠금 마커는 ``incr`` 로
    세우므로 **1 을 돌려받은 요청 하나만** "처음 잠근" 요청이 된다. replica 가 여러 대여도
    ``LOGIN_LOCKED`` 감사가 중복되지 않는다.

    :param username: 시도에 쓰인 아이디 원문(계정 존재 여부와 무관하게 센다 — 아이디
        열거 시도도 무차별 대입이다).
    :return: 이번 실패가 잠금을 새로 걸었으면 ``True``. 임계 미만이거나 이미 잠겼거나
        저장소 장애로 셀 수 없으면 ``False``(fail-open — 로그인을 막지 않는다).
    """
    storage = _limiter_storage()
    if storage is None:
        logger.warning("limiter 저장소가 없어 로그인 실패를 셀 수 없다(fail-open)")
        return False
    count = _incr(storage, _fail_key(username), login_lockout_window_seconds())
    if count is None or count < login_lockout_threshold():
        return False
    locked = _incr(storage, _lock_key(username), login_lockout_seconds())
    _clear(storage, _fail_key(username))
    return locked == 1


def clear_login_failures(username: str) -> None:
    """인증에 성공한 (아이디, IP) 쌍의 실패 흔적을 지운다.

    성공은 그 행위자가 자격증명을 쥐고 있다는 증거이므로, 그때까지 쌓인 실패는 더 이상
    공격의 증거가 아니다. 지우지 않으면 오타를 7번 낸 뒤 로그인에 성공한 사람이 같은 15분
    안에 한 번 더 틀렸다는 이유로 잠긴다. 방어가 약해지지도 않는다 — 성공을 한 번이라도
    만들 수 있는 공격자는 이미 비밀번호를 쥐고 있다.

    :param username: 인증에 성공한 아이디 원문.
    :return: 없음.
    """
    storage = _limiter_storage()
    if storage is None:
        return
    _clear(storage, _fail_key(username))
    _clear(storage, _lock_key(username))
