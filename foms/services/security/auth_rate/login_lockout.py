"""로그인 실패 잠금 + 로그인 전용 rate bucket 키 (AUTH-LOGIN-LOCK-01).

쓰기 경로 209 라우트는 ``before_request`` SSOT 한 곳이 판정하는데, 정작 가장 흔한
공격면인 **로그인에는 한도도 잠금도 0** 이었다(2026-09-06 검토 R7). 이 모듈이 그 두
가지의 공통 기반을 한 자리에 정의한다.

**카운터는 두 개다** (설계서 ``docs/specs/2026-10-19-login-lockout-key_SPEC.md``):

* **(아이디, IP) 카운터** — 임계 8. IP 만 쓰면 사무실 PC·현장 태블릿·iOS 웹뷰가 같은 회선을
  쓰는 회사라 한 사람의 오타가 전 직원을 통째로 잠근다. 한 사람이 한 자리에서 틀리면 이쪽이
  먼저 걸리고, 잠긴 자리의 시도는 더 세지 않는다.
* **계정 카운터(정규화한 아이디, IP 없음)** — 임계 20. 앱이 보는 IP 가 요청마다 바뀌면
  (손님 출구 IP 회전, 또는 프록시 체인이 신뢰 홉 수보다 길어 ``remote_addr`` 가 엣지 주소가
  되는 경우) (아이디, IP) 카운터는 매번 1에서 다시 시작해 절대 잠기지 않았다(2026-10-19
  스테이징 200×9). 대가는 남의 아이디로 그 계정을 잠그는 남용이다 — 임계를 (아이디, IP) 의
  2.5배로 두고 잠금을 15분으로 짧게 둬서 받아들인다(근거는 설계서 §변경 3).

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
한 요청 안에서 첫 저장소 호출이 실패하면 그 요청의 나머지 호출은 건너뛴다 — 같은 장애로
요청마다 경고가 여러 줄 쌓이지 않게, 경고는 요청당 1건이다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import unicodedata
from typing import Any, Optional

from flask import current_app, g, has_app_context, has_request_context, request
from flask_limiter.util import get_remote_address

# 본문 상한 매니페스트 SSOT. 여기서 숫자를 복제하면 /login 상한이 바뀔 때 조용히 어긋난다.
from foms.platform.request_limits import resolve_body_cap

logger = logging.getLogger(__name__)

__all__ = [
    "LOCK_SCOPE_ACCOUNT",
    "LOCK_SCOPE_PAIR",
    "clear_login_failures",
    "is_login_locked",
    "login_account_lockout_threshold",
    "login_bucket_key",
    "login_lockout_seconds",
    "login_lockout_threshold",
    "login_lockout_window_seconds",
    "normalize_login_username",
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

#: 계정 카운터 임계(IP 와 무관). 20 = (아이디, IP) 임계 8 의 2.5배 — 한 사람의 오타는 늘
#: (아이디, IP) 잠금이 먼저 걸리고, 두 자리에서 7번씩 틀려도(14회) 계정 잠금까지 여유가 있다.
#: IP 를 바꾸는 추측기는 15분에 19번으로 묶인다. 창·잠금 시간은 위 두 env 를 같이 쓴다.
ACCOUNT_THRESHOLD_ENV = "FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD"
DEFAULT_ACCOUNT_THRESHOLD = 20

#: 잠금 범위 이름 — 감사 ``LOGIN_LOCKED`` detail 의 ``scope`` 값.
LOCK_SCOPE_PAIR = "ip"
LOCK_SCOPE_ACCOUNT = "account"

#: 버킷 키 접두어. flask-limiter 는 자기 키를 따로 namespacing 하므로 충돌하지 않는다.
_KEY_PREFIX = "foms-login"

#: 계정 카운터 키 접두어. (아이디, IP) 키(``foms-login:<해시>:<IP>``)와 모양이 겹치지 않게 따로 둔다.
_ACCOUNT_KEY_PREFIX = "foms-login-acct"

#: 이 요청에서 저장소 호출이 이미 실패했음을 표시하는 ``flask.g`` 속성 이름.
_STORAGE_FAILED_FLAG = "_foms_login_lockout_storage_failed"

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


def login_account_lockout_threshold() -> int:
    """계정 카운터의 잠금 임계(env ``FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD``).

    :return: 임계 횟수(최소 1).
    """
    return _env_int(ACCOUNT_THRESHOLD_ENV, DEFAULT_ACCOUNT_THRESHOLD)


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


def normalize_login_username(raw: str) -> str:
    """계정 카운터용 아이디 정규화 — NFKC → 앞뒤 공백 제거 → 대소문자 접기.

    (아이디, IP) 키와 달리 접는다. 계정 카운터의 목적은 "이 계정을 노리는 시도" 를 한데
    모으는 것이라, 표기만 다른 변형이 카운터를 새로 쓰면 그만큼 추측 기회가 늘어난다.
    접어서 서로 다른 두 계정이 카운터를 공유하는 경우(대소문자만 다른 아이디)는 그 둘의
    잠금이 함께 걸릴 뿐 인증에는 영향이 없다.

    :param raw: 시도에 쓰인 아이디 원문.
    :return: 정규화한 아이디.
    """
    return unicodedata.normalize("NFKC", raw).strip().casefold()


def _account_key(username: str, suffix: str) -> str:
    """계정 카운터 키 — ``foms-login-acct:<정규화 아이디 해시>:<suffix>`` (IP 없음).

    :param username: 시도에 쓰인 아이디 원문.
    :param suffix: ``fail`` 또는 ``lock``.
    :return: 저장소 키 문자열.
    """
    normalized = normalize_login_username(username)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{_ACCOUNT_KEY_PREFIX}:{digest}:{suffix}"


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


def _storage_failed_this_request() -> bool:
    """이 요청에서 저장소 호출이 이미 실패했는가(그렇다면 나머지 호출은 건너뛴다).

    :return: 실패 표시가 있으면 ``True``. 요청 컨텍스트 밖이면 늘 ``False``.
    """
    return has_request_context() and bool(g.get(_STORAGE_FAILED_FLAG, False))


def _mark_storage_failed() -> None:
    """이 요청의 저장소 실패를 표시한다(요청 컨텍스트 밖이면 아무 것도 하지 않는다).

    :return: 없음.
    """
    if has_request_context():
        setattr(g, _STORAGE_FAILED_FLAG, True)


def _incr(storage: Any, key: str, expiry: int) -> Optional[int]:
    """카운터를 1 올리고 **올린 뒤의 값**을 돌려준다.

    :param storage: limiter 저장소.
    :param key: 카운터 키.
    :param expiry: 키 수명(초). 첫 증가 때만 적용된다(고정 창).
    :return: 증가 후 값. 저장소 장애면 ``None``(fail-open — 호출부는 잠그지 않는다).
    """
    if _storage_failed_this_request():
        return None
    try:
        return int(storage.incr(key, expiry))
    except storage.base_exceptions:
        _mark_storage_failed()
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
    if _storage_failed_this_request():
        return None
    try:
        return int(storage.get(key))
    except storage.base_exceptions:
        _mark_storage_failed()
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
    if _storage_failed_this_request():
        return
    try:
        storage.clear(key)
    except storage.base_exceptions:
        _mark_storage_failed()
        logger.warning(
            "로그인 잠금 카운터 삭제 실패 (key=%s) — 지우지 못하고 진행한다(fail-open)",
            key,
            exc_info=True,
        )


def _lock_on_threshold(
    storage: Any, fail_key: str, lock_key: str, count: Optional[int], threshold: int
) -> bool:
    """실패 수가 임계에 닿았으면 잠금 마커를 세우고 실패 카운터를 비운다.

    잠금 마커는 ``incr`` 로 세우므로 **1 을 돌려받은 요청 하나만** "처음 잠근" 요청이 된다.
    replica·워커가 여러 개여도 ``LOGIN_LOCKED`` 감사가 중복되지 않는다. 실패 카운터를 비우는
    것은 잠금이 풀린 뒤 다시 임계만큼의 기회로 시작하게 하려는 것이다(PAM faillock 과 같은 모양).

    :param storage: limiter 저장소.
    :param fail_key: 실패 카운터 키.
    :param lock_key: 잠금 마커 키.
    :param count: 이번 증가 후 실패 수(저장소 장애면 ``None``).
    :param threshold: 이 카운터의 임계.
    :return: 이번 호출이 잠금을 새로 걸었으면 ``True``.
    """
    if count is None or count < threshold:
        return False
    locked = _incr(storage, lock_key, login_lockout_seconds())
    _clear(storage, fail_key)
    return locked == 1


def is_login_locked(username: str) -> bool:
    """이 시도가 지금 잠겨 있는가 — (아이디, IP) 잠금 **또는** 계정 잠금.

    두 잠금은 같은 응답(429)으로 나가므로 어느 쪽이 걸렸는지, 계정이 있는지는 드러나지 않는다.

    :param username: 시도에 쓰인 아이디 원문.
    :return: 어느 하나라도 잠겨 있으면 ``True``. 저장소가 없거나 조회에 실패하면 ``False``(fail-open).
    """
    storage = _limiter_storage()
    if storage is None:
        logger.warning("limiter 저장소가 없어 로그인 잠금을 판정할 수 없다(fail-open)")
        return False
    return any(
        bool(_get(storage, key))
        for key in (_lock_key(username), _account_key(username, "lock"))
    )


def register_login_failure(username: str) -> Optional[str]:
    """실패 1건을 두 카운터에 세고, **이번 실패로 새로 잠긴 범위**를 알려준다.

    (아이디, IP) 카운터와 계정 카운터를 함께 올린다. 둘 다 이번에 새로 잠기면 더 넓은
    ``account`` 를 돌려준다 — 관리자에게 더 중요한 신호다. 잠긴 시도는 호출부가 이 함수
    앞에서 끊으므로, 한 자리에서 잠긴 사람의 시도는 계정 카운터에도 더 쌓이지 않는다.

    :param username: 시도에 쓰인 아이디 원문(계정 존재 여부와 무관하게 센다 — 아이디
        열거 시도도 무차별 대입이다).
    :return: 새로 잠긴 범위(:data:`LOCK_SCOPE_ACCOUNT` / :data:`LOCK_SCOPE_PAIR`). 임계 미만이거나
        이미 잠겼거나 저장소 장애로 셀 수 없으면 ``None``(fail-open — 로그인을 막지 않는다).
    """
    storage = _limiter_storage()
    if storage is None:
        logger.warning("limiter 저장소가 없어 로그인 실패를 셀 수 없다(fail-open)")
        return None
    window = login_lockout_window_seconds()

    pair_fail = _fail_key(username)
    pair_locked = _lock_on_threshold(
        storage,
        pair_fail,
        _lock_key(username),
        _incr(storage, pair_fail, window),
        login_lockout_threshold(),
    )
    account_fail = _account_key(username, "fail")
    account_locked = _lock_on_threshold(
        storage,
        account_fail,
        _account_key(username, "lock"),
        _incr(storage, account_fail, window),
        login_account_lockout_threshold(),
    )
    if account_locked:
        return LOCK_SCOPE_ACCOUNT
    if pair_locked:
        return LOCK_SCOPE_PAIR
    return None


def clear_login_failures(username: str) -> None:
    """인증에 성공한 시도의 실패 흔적을 지운다 — (아이디, IP) 카운터·잠금 + 계정 실패 카운터.

    성공은 그 행위자가 자격증명을 쥐고 있다는 증거이므로, 그때까지 쌓인 실패는 더 이상
    공격의 증거가 아니다. 지우지 않으면 오타를 7번 낸 뒤 로그인에 성공한 사람이 같은 15분
    안에 한 번 더 틀렸다는 이유로 잠긴다. 방어가 약해지지도 않는다 — 성공을 한 번이라도
    만들 수 있는 공격자는 이미 비밀번호를 쥐고 있다.

    계정 **잠금** 마커는 지우지 않는다. 계정이 잠긴 동안에는 비밀번호 대조까지 가지 않으므로
    여기 올 수 없고, 잠금은 시간이 지나야 풀린다.

    :param username: 인증에 성공한 아이디 원문.
    :return: 없음.
    """
    storage = _limiter_storage()
    if storage is None:
        return
    _clear(storage, _fail_key(username))
    _clear(storage, _lock_key(username))
    _clear(storage, _account_key(username, "fail"))
