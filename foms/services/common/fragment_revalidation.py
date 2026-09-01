"""HB-S2a — 프래그먼트 버전 키 + 그림자 관측 (동작 변경 0).

스펙: `docs/specs/2026-09-01-shell-heartbeat-cheap-revalidation_SPEC.md` §8.

셸 하트비트는 인접 탭 프래그먼트를 시간당 약 260회 재검증하는데, ETag 가 **렌더가 끝난
뒤** 붙어서 304 여도 서버는 화면을 전부 렌더한다(`erp_shell_http.py` 참조). 렌더 전에
끝내려면 "본문이 안 바뀌었다"를 렌더 없이 판정할 키가 필요하다.

이 모듈은 그 키를 만들고, **그 키가 정말 본문을 결정하는지 실측으로 검증한다** — 아직
304 를 내지는 않는다.

왜 그림자 모드가 먼저인가
--------------------------
키에 빠진 축이 하나라도 있으면 **낡은 304** 가 나간다(스펙 §5-1: 지금 결함보다 나쁘다).
그런데 축의 목록은 소스 독해로 안 닫힌다 — 프래그먼트는 전역 컨텍스트 프로세서
(`inject_foms_flags` 코호트 플래그 12종, `inject_foms_nav_badges` 주문 건수)를 그대로
받고, 템플릿이 그중 무엇을 실제로 쓰는지 세는 것은 "전수 확인인 척하는 확인"이다.

그래서 S2a 는 키를 만들되 렌더는 지금 그대로 하고, **같은 키로 온 요청에 다른 본문이
나오는지**만 대조한다. mismatch 가 0 이라는 증거를 얻은 뒤에야 S2b 에서 렌더 전 304 를
켠다(위험을 감수한 뒤 증거를 모으는 순서를 뒤집는다).

Flask-Compress 와의 관계
------------------------
`flask_compress.py:229-237` 은 `status_code >= 300` 이면 압축도 ETag 재작성도 하지 않고
조기 반환한다. 즉 **304 에는 `:br` 접미사가 붙지 않는다.** 200 만 `"K"` → `"K:br"` 로
재작성된다(`:263-268`). 따라서 클라가 에코하는 검증자를 비교할 때는
:func:`strip_content_encoding_suffix` 로 접미사를 벗긴다. S2a 에서는 아직 안 쓰지만
규칙을 여기에 함께 고정한다(S2b 가 이 함수를 쓴다).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Final, Iterable, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "KEY_VERSION",
    "SHADOW_KEY_PREFIX",
    "SHADOW_MISMATCH_COUNTER_KEY",
    "SHADOW_HEADER",
    "SHADOW_STATE_NEW",
    "SHADOW_STATE_MATCH",
    "SHADOW_STATE_MISMATCH",
    "is_shadow_revalidation_enabled",
    "strip_content_encoding_suffix",
    "build_fragment_version_key",
    "record_shadow_observation",
]

KEY_VERSION: Final[str] = "v1"
SHADOW_KEY_PREFIX: Final[str] = f"foms:fragver:{KEY_VERSION}"
SHADOW_MISMATCH_COUNTER_KEY: Final[str] = f"{SHADOW_KEY_PREFIX}:mismatch"

#: 진단 헤더. 값은 아래 세 상태 중 하나(업무 데이터 없음 — EPT-B7 render_ms 와 같은 성격).
SHADOW_HEADER: Final[str] = "X-FOMS-FRAGVER"
SHADOW_STATE_NEW: Final[str] = "new"
SHADOW_STATE_MATCH: Final[str] = "match"
SHADOW_STATE_MISMATCH: Final[str] = "MISMATCH"

#: 관측 기록 TTL(초). 하트비트 주기(50s/240s)보다 넉넉히 길어 같은 키가 반복 관측되게 하고,
#: 하루 관측이 끝나면 저절로 사라질 만큼 짧다.
_SHADOW_TTL_S: Final[int] = 3600

_ENV_FLAG: Final[str] = "FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED"

#: Flask-Compress 가 ETag 뒤에 붙이는 알고리즘 접미사.
_COMPRESS_ALGORITHMS: Final[frozenset[str]] = frozenset(
    {"br", "gzip", "deflate", "zstd"}
)


def _env_truthy(name: str) -> bool:
    """환경변수가 켜짐으로 해석되는지 (1/true/yes/on, 대소문자 무시)."""
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def is_shadow_revalidation_enabled() -> bool:
    """그림자 관측이 켜져 있는지.

    기본 off. **스테이징 전용**이다 — 관측 비용(본문 해시 + Redis 왕복)이 첫 페인트
    경로에 얹히므로 운영에서는 켜지 않는다(스펙 §8.4).
    """
    return _env_truthy(_ENV_FLAG)


def strip_content_encoding_suffix(validator: str) -> str:
    """ETag 값에서 Flask-Compress 알고리즘 접미사를 벗긴다.

    ``"abc:br"`` → ``"abc"``. 따옴표·``W/`` 약한 표식도 함께 정규화한다. 알려진
    알고리즘 이름이 아닌 접미사는 **벗기지 않는다**(키 안에 콜론이 들어가도 안전).

    Args:
        validator: ``If-None-Match`` / ``ETag`` 헤더의 값 하나.

    Returns:
        정규화된 검증자 문자열.
    """
    value = validator.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    head, sep, tail = value.rpartition(":")
    if sep and tail in _COMPRESS_ALGORITHMS:
        return head
    return value


def _normalized_args(req: Any, allowed_args: Sequence[str]) -> list[list[str]] | None:
    """요청 인자를 정규화한다. 미등재 인자가 하나라도 있으면 ``None``.

    "모르는 인자가 오면 단축을 포기한다"가 규칙이다 — 새 필터가 추가됐는데 키에
    반영이 안 되면 그 필터를 바꿔도 같은 키가 나와 낡은 본문이 재사용된다.
    ``view`` 는 셸 프래그먼트 표식이라 언제나 허용하되 키 재료에서는 뺀다
    (같은 본문을 fragment/critical/heavy 로 나눠 받는 축은 tier 헤더가 담당).

    Args:
        req: Flask ``Request``.
        allowed_args: 그 라우트가 실제로 읽는 인자 이름들.

    Returns:
        ``[[이름, 값], ...]`` 정렬 목록, 또는 미등재 인자가 있으면 ``None``.
    """
    allowed = set(allowed_args) | {"view"}
    out: list[list[str]] = []
    for name in sorted(req.args.keys()):
        if name not in allowed:
            return None
        if name == "view":
            continue
        values = sorted(req.args.getlist(name))
        out.append([name, "\x1f".join(values)])
    return out


_COHORT_CACHE_ATTR: Final[str] = "_foms_fragver_cohort_cache"


def _cohort_material() -> dict[str, Any]:
    """코호트·플래그 축을 통째로 키 재료에 넣는다(요청당 1회 캐시).

    어떤 플래그를 템플릿이 실제로 쓰는지 골라내는 대신 **전부 넣는다**. 골라내려면
    템플릿을 읽어서 세야 하는데, 그 셈이 틀리면 낡은 304 가 나간다(스펙 §8.1-b).
    과다 포함의 대가는 재렌더 한 번이고, 과소 포함의 대가는 조용히 낡은 화면이다.

    렌더에서 이미 `inject_foms_flags` 가 돌므로 여기서 또 부르면 env·쿠키 파싱이
    한 요청에 두 벌 난다. `resolve_shell_variant_cached` 와 같은 방식으로 `flask.g`
    에 요청당 1회만 캐시한다(첫 페인트 경로에 일을 더하지 않는다는 P4 교훈).

    Returns:
        JSON 직렬화 가능한 플래그 딕셔너리. 만들 수 없으면 표식을 담아 돌려준다
        (빈 딕셔너리로 조용히 같아지지 않게).
    """
    try:
        from flask import g, has_request_context

        cached = getattr(g, _COHORT_CACHE_ATTR, None) if has_request_context() else None
        if cached is not None:
            return cached

        from foms.services.context_processors import (
            _current_shell_variant,
            inject_foms_flags,
        )

        flags = dict(inject_foms_flags())
        flags["_shell_variant"] = _current_shell_variant()
        material = {k: v for k, v in sorted(flags.items()) if _json_safe(v)}
        if has_request_context():
            setattr(g, _COHORT_CACHE_ATTR, material)
        return material
    except Exception:
        logger.warning("[FragVer] cohort material unavailable", exc_info=True)
        return {"_cohort": "unavailable"}


def _json_safe(value: Any) -> bool:
    """값이 안정적으로 직렬화되는 스칼라인지(객체 주소가 키에 섞이지 않게)."""
    return value is None or isinstance(value, (bool, int, float, str))


def build_fragment_version_key(
    *,
    route_id: str,
    req: Any,
    user: Any,
    tables: Iterable[str],
    allowed_args: Sequence[str],
    mine_only: bool,
) -> str | None:
    """렌더 전에 만들 수 있는 프래그먼트 본문 버전 키.

    재료: 라우트 · 정규화된 요청 인자 · 사용자 축(id/role/team/mine) · 코호트 플래그 ·
    KST 오늘 · 그 화면이 읽는 테이블들의 쓰기 카운터.

    Args:
        route_id: 라우트 식별자(경로별 네임스페이스).
        req: Flask ``Request``.
        user: 현재 사용자(``None`` 가능).
        tables: 그 화면이 읽는 테이블 이름들.
        allowed_args: 그 라우트가 읽는 요청 인자 이름들.
        mine_only: 그 요청에 적용된 mine 필터 판정값(쿠키·팀 강제 포함).

    Returns:
        16자 hex 키. 아래 중 하나라도 참이면 ``None``(= 조건부 단축 포기, 지금 동작 유지):
        미등재 요청 인자가 왔다 / Redis 가 없어 테이블 카운터를 못 읽는다.
    """
    from foms.services.common.table_version_counter import get_table_versions
    from foms.services.datetime_kst import get_today_kst

    args = _normalized_args(req, allowed_args)
    if args is None:
        return None
    versions = get_table_versions(tables)
    if versions is None:
        return None

    material = {
        "v": KEY_VERSION,
        "route": route_id,
        "args": args,
        "uid": getattr(user, "id", None) if user else None,
        "role": getattr(user, "role", None) if user else None,
        "team": getattr(user, "team", None) if user else None,
        "mine": bool(mine_only),
        "cohort": _cohort_material(),
        "today": get_today_kst().isoformat(),
        "tables": dict(sorted(versions.items())),
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def record_shadow_observation(key: str, body: bytes, *, route_id: str) -> str:
    """같은 키로 온 요청이 정말 같은 본문을 내는지 대조한다(관측만).

    Redis 에 ``키 → 본문 해시`` 를 짧은 TTL 로 적어두고, 다음에 같은 키가 오면 그때의
    본문 해시와 비교한다. 어긋나면 **키에 빠진 축이 있다는 증거**이므로 경고 로그와
    mismatch 카운터를 남긴다. 이 함수는 응답을 바꾸지 않는다.

    Args:
        key: :func:`build_fragment_version_key` 가 만든 키.
        body: 렌더된 응답 본문(압축 전).
        route_id: 로그에 남길 라우트 식별자.

    Returns:
        :data:`SHADOW_STATE_NEW` / :data:`SHADOW_STATE_MATCH` /
        :data:`SHADOW_STATE_MISMATCH`. Redis 가 없거나 오류면 ``SHADOW_STATE_NEW``
        (관측 실패는 관측 없음과 같게 취급 — 응답은 어차피 안 바뀐다).
    """
    from foms.services.common.dashboard_cache import get_dashboard_redis

    digest = hashlib.sha256(body).hexdigest()[:16]
    client = get_dashboard_redis()
    if client is None:
        return SHADOW_STATE_NEW
    redis_key = f"{SHADOW_KEY_PREFIX}:{route_id}:{key}"
    try:
        # GET + SETEX 를 파이프라인으로 묶어 왕복 1회로 끝낸다. 관측은 첫 페인트
        # 경로에 얹히므로 왕복 수가 그대로 응답 시간이다(P4 교훈).
        pipe = client.pipeline()
        pipe.get(redis_key)
        pipe.setex(redis_key, _SHADOW_TTL_S, digest)
        previous = (pipe.execute() or [None])[0]
    except Exception:
        logger.warning("[FragVer] shadow observation failed (non-fatal)", exc_info=True)
        return SHADOW_STATE_NEW
    if previous is None:
        return SHADOW_STATE_NEW
    if str(previous) == digest:
        return SHADOW_STATE_MATCH
    try:
        client.incr(SHADOW_MISMATCH_COUNTER_KEY)
    except Exception:
        logger.warning("[FragVer] mismatch counter failed (non-fatal)", exc_info=True)
    logger.warning(
        "[FragVer] MISMATCH route=%s key=%s prev=%s now=%s — "
        "키에 빠진 축이 있다(렌더 전 304 를 켜면 낡은 본문이 나간다)",
        route_id,
        key,
        previous,
        digest,
    )
    return SHADOW_STATE_MISMATCH
