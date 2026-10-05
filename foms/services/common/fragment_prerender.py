"""렌더 전 304 — 버전 키 공용 재료와 그림자 관측 (하트비트 설계서 2026-10-05, 1단계).

설계서: ``docs/specs/2026-10-05-heartbeat-304-before-render_SPEC.md`` §3·§5.

하트비트가 50초마다 부르는 탭 프래그먼트는 304 여도 렌더를 끝까지 한다(ETag 가 렌더 **뒤**에
붙는다). 렌더 **전**에 "본문이 그대로다"를 판정하려면, 렌더가 쓰는 모든 입력의 함수인 키가
필요하다. 이 모듈은 그 키의 공용 재료(요청·쿠키·세션·사용자·코호트·env·릴리스·시간)와 행 지문
도구를 주고, **그림자 관측**으로 "이 키로 렌더 전 304 를 냈다면 맞았을까"를 센다.

이번 단계는 304 를 **내지 않는다** — 렌더는 지금 그대로다. 켜는 조건(셋 다 참이어야 한다):

1. env ``FOMS_FRAGMENT_PRERENDER_SHADOW_ENABLED`` (기본 꺼짐)
2. Redis 런타임 끄기 키 ``foms:fragver:v2:off`` · ``foms:fragver:v2:off:<route>`` 가 없음
   (읽기 실패 = 꺼짐). 배포 없이 즉시 끈다.
3. 셸 프래그먼트 GET 이고 ``If-None-Match`` 가 있음 — 뒤에서 도는 재검증에서만 키를 만든다.
   사용자가 기다리는 화면 전환에는 일을 더하지 않는다(설계서 §3.5-1).

관측 방법: 응답마다 "이 본문(ETag) ← 이 키" 를 Redis 에 적어 둔다. 다음 재검증에서 클라가 들고 온
ETag 로 그때의 키를 찾아 지금 키와 비교한다 — 켠 뒤라면 클라가 들고 있을 키 ETag 를 그대로
흉내 낸다. 키가 같은데 본문이 달라졌으면 그 키로 낸 304 는 **옛 화면**이었다(MISMATCH). 단,
키를 만든 뒤 렌더하는 사이에 커밋이 끼면 본문만 새것이 된다 — 켠 뒤라면 키 시점의 판정이 맞으므로
키를 한 번 더 만들어 달라졌으면 ``race`` 로 따로 센다.

데이터 지문은 PostgreSQL ``xmin``(행이 바뀌면 반드시 바뀐다 — 쓰기 경로·프로세스 무관)으로 뜬다.
그 밖의 DB(SQLite 테스트)는 행의 모든 열 값을 이은 문자열로 대신한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from flask import has_request_context, session
from sqlalchemy import String, Table, cast, func, literal_column
from sqlalchemy.sql.elements import ColumnElement

from foms.services.common import dashboard_cache
from foms.services.common.erp_shell_http import get_erp_shell_view_mode
from foms.services.common.fragment_revalidation import RELEASE_ID, strip_content_encoding_suffix
from foms.services.context_processors import (
    inject_foms_flags,
    inject_foms_nav_badges,
    inject_menu,
    inject_status_list,
)
from foms.services.datetime_kst import get_today_kst, now_utc_naive

logger = logging.getLogger(__name__)

KEY_VERSION: Final[str] = "v2"
REDIS_PREFIX: Final[str] = f"foms:fragver:{KEY_VERSION}"
KILL_SWITCH_KEY: Final[str] = f"{REDIS_PREFIX}:off"
SHADOW_ENV_FLAG: Final[str] = "FOMS_FRAGMENT_PRERENDER_SHADOW_ENABLED"
SHADOW_HEADER: Final[str] = "X-FOMS-FRAGVER-SHADOW"
#: 신선도 상한 C(초) — 재료를 하나 빠뜨려도 옛 화면은 최대 C초 + 재검증 주기로 끝난다(§3.6).
FRESHNESS_BUCKET_S: Final[int] = 300
#: 다음 단계로 넘어가는 기준(§3.7 1단계) — :func:`judge_shadow_stats` 가 쓴다.
GATE_MIN_OBSERVATIONS: Final[int] = 1000
GATE_MIN_HIT_RATE: Final[float] = 0.5
GATE_MAX_KEY_TO_RENDER: Final[float] = 0.3
#: 셸 공통 재료 — 모든 탭 프래그먼트가 싣는 셸 머리·서랍·nav 가 읽는 것(§3.2).
SHELL_ARGS: Final[tuple[str, ...]] = ("mine", "tower_mine")
SHELL_COOKIES: Final[tuple[str, ...]] = ("erp_mine_only", "foms_ptr", "foms_vw", "foms_scr")
SHELL_SESSION_KEYS: Final[tuple[str, ...]] = ("user_id", "impersonating_from")
SHELL_HEADERS: Final[tuple[str, ...]] = ("x-foms-erp-shell",)
#: 렌더 중 읽히는 env(기록 계약이 모은 목록). 값은 해시로만 키에 들어간다.
SHELL_ENV: Final[tuple[str, ...]] = (
    "ERP_MOBILE_V2_ENABLED", "ERP_ORDER_ENABLED", "FOMS_BOTTOM_NAV_HTMX_ENABLED",
    "FOMS_DESIGN_TOKENS_V2_ENABLED", "FOMS_ERP_SPEC_CALC_ENABLED", "FOMS_ERP_SPEC_PICKER_ENABLED",
    "FOMS_INLINE_EDIT_ENABLED", "FOMS_OFFLINE_SW_ENABLED", "FOMS_RUM_BASELINE_ENABLED",
    "FOMS_TABLET_SPLIT_VIEW_ENABLED", "FOMS_V3_SHELL_COHORT", "FOMS_WIZARD_NEW_ORDER_ENABLED",
    "KAKAO_SHARE_JS_KEY", "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_NAME",
    "REDIS_URL", "STORAGE_TYPE", "UPLOAD_FOLDER", "USE_DIRECT_UPLOAD",
    "FOMS_DASHBOARD_MICRO_CACHE_ENABLED",
)
#: 시계(테스트가 바꿔 끼운다).
_now_s: Callable[[], float] = time.time

_STATUS_FLAG_NAMES: Final[tuple[str, ...]] = (
    "erp_order_enabled", "can_toggle_order_flags", "can_toggle_factory2_flag", "erp_mobile_v2_enabled",
    "coarse_pointer_surfaces", "wide_only_surfaces", "mobile_width_surfaces", "shell_variant",
    "use_direct_upload", "impersonating_from_id",
)
_DK_TTL_S: Final[int] = 2 * 3600
_STATS_TTL_S: Final[int] = 35 * 86400
_MISMATCH_LOG_KEY: Final[str] = f"{REDIS_PREFIX}:mismatch_log"
_MISMATCH_LOG_MAX: Final[int] = 100

STATE_NEW: Final[str] = "new"
STATE_HIT: Final[str] = "hit"
STATE_MISS: Final[str] = "miss"
STATE_MISS_SAME_BODY: Final[str] = "miss_same_body"
STATE_MISMATCH: Final[str] = "MISMATCH"
STATE_RACE: Final[str] = "race"
STATE_ABANDON: Final[str] = "abandon"


@dataclass
class PrerenderKey:
    """렌더 전에 만든 키와, 렌더가 다시 읽지 않도록 넘겨받을 값들."""

    key: str
    controls: dict[str, str]
    key_ms: float
    rows: int = 0
    reuse: dict[str, Any] = field(default_factory=dict)


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def digest(value: Any) -> str:
    """JSON 직렬화한 값의 16자 sha256(키 재료용 — 순서 고정)."""
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def digest_rows(rows: Iterable[Sequence[Any]]) -> str:
    """행 목록(순서 그대로)의 ``"행수:지문"``."""
    hasher = hashlib.sha256()
    count = 0
    for row in rows:
        hasher.update(json.dumps(list(row), ensure_ascii=False, default=str).encode("utf-8"))
        hasher.update(b"\n")
        count += 1
    return f"{count}:{hasher.hexdigest()[:16]}"


def values_version(columns: Iterable[Any]) -> ColumnElement:
    """열 값들을 이은 문자열 식 — 작은 공용 표는 ``xmin`` 대신 화면에 쓰는 열의 값으로 뜬다(§3.3)."""
    parts = [func.coalesce(cast(col, String), "~") for col in columns]
    expr: ColumnElement = parts[0]
    for part in parts[1:]:
        expr = expr + "|" + part
    return expr


def row_version(table: Table, dialect_name: str) -> ColumnElement:
    """행 버전 식 — PostgreSQL 은 ``xmin``, 그 밖(SQLite 테스트)은 모든 열 값을 이은 문자열.

    ``xmin`` 은 행이 갱신·삽입될 때마다 새 값이다(쓰기 경로·프로세스 무관). 값이 같은데 바뀌는
    경우(no-op UPDATE)는 키가 쓸데없이 바뀌는 쪽이라 안전하다(§3.3 C 세부 규칙). 고르는 열이 id 와
    ``xmin`` 뿐이라 JSONB 를 풀지 않는다.
    """
    if dialect_name == "postgresql":
        return cast(literal_column(f"{table.name}.xmin"), String)
    return values_version(table.columns)


def time_bucket(user_id: Any, now_s: float, size_s: int = FRESHNESS_BUCKET_S) -> int:
    """``floor((지금 + uid 별 어긋남) / C)`` — 모두가 같은 순간 재렌더하지 않게 경계를 흩는다."""
    offset = int(hashlib.sha256(f"fragver:{user_id}".encode("utf-8")).hexdigest()[:8], 16) % size_s
    return (int(now_s) + offset) // size_s


def normalized_args(req: Any, allowed: Sequence[str]) -> list[list[str]] | None:
    """허용 목록으로 정규화한 요청 인자. 모르는 인자가 하나라도 있으면 ``None``(키 포기)."""
    known = set(allowed) | {"view"}
    out: list[list[str]] = []
    for name in sorted(req.args.keys()):
        if name not in known:
            return None
        out.append([name, "\x1f".join(sorted(req.args.getlist(name)))])
    return out


def shell_material(req: Any, user: Any, allowed_args: Sequence[str], env_names: Sequence[str]) -> dict[str, Any] | None:
    """모든 탭에 공통인 키 재료(§3.2). 모르는 인자가 오면 ``None``.

    셸 머리는 ``request.full_path`` 를 "내 일" 링크에 그대로 박으므로 정렬하지 않은 원래 쿼리
    문자열을 넣는다(인자 순서만 다른 요청이 같은 키·다른 본문이 되지 않게).
    """
    args = normalized_args(req, tuple(allowed_args) + SHELL_ARGS)
    if args is None:
        return None
    status = inject_status_list()
    flags = dict(inject_foms_flags())
    flags.update({f"status.{name}": status.get(name) for name in _STATUS_FLAG_NAMES})
    cohort = {k: v for k, v in sorted(flags.items()) if v is None or isinstance(v, (bool, int, float, str))}
    uid = getattr(user, "id", None) if user else None
    return {
        "v": KEY_VERSION,
        "mode": get_erp_shell_view_mode(req),
        "args": args,
        "full_path": req.full_path,
        "cookies": {name: req.cookies.get(name) for name in SHELL_COOKIES},
        "user": [uid, getattr(user, "role", None), getattr(user, "team", None),
                 getattr(user, "is_active", None), getattr(user, "name", None),
                 getattr(user, "username", None)] if user else None,
        "session": {name: session.get(name) for name in SHELL_SESSION_KEYS} if has_request_context() else {},
        "cohort": cohort,
        "nav_badges": inject_foms_nav_badges().get("foms_nav_badges"),
        "menu": digest(inject_menu().get("menu")),
        "env": {name: digest(os.environ.get(name)) for name in env_names},
        "release": [os.environ.get("RAILWAY_DEPLOYMENT_ID"), os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
                    os.environ.get("FOMS_RELEASE_ID"), RELEASE_ID],
        "today": get_today_kst().isoformat(),
        "bucket": time_bucket(uid, _now_s()),
    }


def finish_key(material: Mapping[str, Any], controls: Mapping[str, Sequence[str]]) -> tuple[str, dict[str, str]]:
    """재료 → 본 키 + 대조 키들(재료 한 갈래씩 뺀 것, §3.7 1단계 "약하게 만든 대조 키")."""
    key = digest(material)
    out: dict[str, str] = {}
    for name, path in controls.items():
        weakened = json.loads(json.dumps(material, default=str))
        node = weakened
        for part in path[:-1]:
            node = node[part]
        node.pop(path[-1], None)
        out[name] = digest(weakened)
    return key, out


def shadow_requested(req: Any, route_id: str) -> bool:
    """이 요청에서 그림자 관측(=렌더 전 키 계산)을 할지. 실패·모름은 전부 ``False``."""
    if not _env_truthy(SHADOW_ENV_FLAG):
        return False
    if req.method != "GET" or get_erp_shell_view_mode(req) is None:
        return False
    if not (req.headers.get("If-None-Match") or "").strip():
        return False
    client = dashboard_cache.get_dashboard_redis()
    if client is None:
        return False
    try:
        flags = client.mget([KILL_SWITCH_KEY, f"{KILL_SWITCH_KEY}:{route_id}"])
    except Exception:
        logger.warning("[FragVer2] kill switch read failed — shadow off for this request", exc_info=True)
        return False
    return not any(flags or ())


def _held_validator(req: Any) -> str:
    raw = (req.headers.get("If-None-Match") or "").split(",")[0]
    return strip_content_encoding_suffix(raw) if raw.strip() else ""


def _classify(prev: Mapping[str, Any] | None, result: PrerenderKey, same_body: bool,
              recheck: Callable[[], PrerenderKey | None]) -> tuple[str, dict[str, str]]:
    if prev is None:
        return STATE_NEW, {name: STATE_NEW for name in result.controls}
    same_key = prev.get("k") == result.key
    if same_key and same_body:
        state = STATE_HIT
    elif same_key:
        # 다시 만든 키가 달라졌을 때만 경합으로 본다 — 다시 만들지 못하면(오류) 빠뜨림을 숨기지 않게 MISMATCH.
        again = recheck()
        state = STATE_RACE if again is not None and again.key != result.key else STATE_MISMATCH
    else:
        state = STATE_MISS_SAME_BODY if same_body else STATE_MISS
    controls: dict[str, str] = {}
    prev_controls = prev.get("c") or {}
    for name, ckey in result.controls.items():
        if prev_controls.get(name) != ckey:
            controls[name] = STATE_MISS
        elif same_body:
            controls[name] = STATE_HIT
        else:
            controls[name] = STATE_RACE if state == STATE_RACE else STATE_MISMATCH.lower()
    return state, controls


def _stats_key(route_id: str) -> str:
    return f"{REDIS_PREFIX}:stats:{route_id}:{get_today_kst().isoformat()}"


def observe_shadow(*, route_id: str, req: Any, response: Any, user_id: Any, result: PrerenderKey | None,
                   view_ms: float, recheck: Callable[[], PrerenderKey | None], abandon: str = "") -> str:
    """렌더가 끝난 응답으로 "렌더 전 304 였다면 맞았을까"를 판정해 센다(응답 본문·상태 불변).

    Args:
        route_id: 라우트 식별자.
        req: Flask 요청.
        response: ETag 를 단 응답(:func:`apply_erp_shell_fragment_headers` 뒤).
        user_id: 현재 사용자 id(ETag→키 기록의 이름공간).
        result: 렌더 전에 만든 키. ``None`` 이면 키를 포기한 요청(``abandon`` 사유).
        view_ms: 뷰 전체 소요(키 계산 포함). 렌더 몫 = ``view_ms - key_ms``.
        recheck: 키를 다시 만드는 함수(MISMATCH 후보가 경합이었는지 가린다).
        abandon: 키를 포기한 사유(인자 이름·상태 단어만).

    Returns:
        판정 상태 단어. Redis 가 없으면 빈 문자열.
    """
    client = dashboard_cache.get_dashboard_redis()
    if client is None:
        return ""
    stats_key = _stats_key(route_id)
    if result is None:
        _bump(client, stats_key, {"obs": 1, STATE_ABANDON: 1}, {})
        logger.info("[FragVer2] route=%s state=abandon reason=%s view_ms=%.1f", route_id, abandon, view_ms)
        response.headers[SHADOW_HEADER] = STATE_ABANDON
        return STATE_ABANDON
    etag_now = response.get_etag()[0] or ""
    held = _held_validator(req)
    deploy = os.environ.get("RAILWAY_DEPLOYMENT_ID") or RELEASE_ID
    record = json.dumps({"k": result.key, "c": result.controls, "d": deploy}, separators=(",", ":"))
    try:
        pipe = client.pipeline()
        pipe.get(f"{REDIS_PREFIX}:dk:{route_id}:{user_id}:{held[:64]}")
        pipe.setex(f"{REDIS_PREFIX}:dk:{route_id}:{user_id}:{etag_now[:64]}", _DK_TTL_S, record)
        prev_raw = (pipe.execute() or [None])[0]
        prev = json.loads(prev_raw) if prev_raw else None
    except Exception:
        logger.warning("[FragVer2] shadow lookup failed (non-fatal)", exc_info=True)
        return ""
    state, controls = _classify(prev, result, bool(etag_now) and etag_now == held, recheck)
    render_ms = max(view_ms - result.key_ms, 0.0)
    counts = {"obs": 1, state.lower(): 1, "ratio_n": 1,
              "ratio_ok": int(result.key_ms <= GATE_MAX_KEY_TO_RENDER * render_ms)}
    counts.update({f"ctl.{name}.{st}": 1 for name, st in controls.items()})
    _bump(client, stats_key, counts, {"key_ms_sum": result.key_ms, "render_ms_sum": render_ms})
    if state == STATE_MISMATCH:
        _record_mismatch(client, route_id, req, result, prev or {}, deploy)
    log = logger.warning if state == STATE_MISMATCH else logger.info
    log("[FragVer2] route=%s state=%s ctl=%s key_ms=%.1f render_ms=%.1f rows=%s",
        route_id, state, ",".join(f"{k}:{v}" for k, v in sorted(controls.items())),
        result.key_ms, render_ms, result.rows)
    response.headers[SHADOW_HEADER] = state
    return state


def _bump(client: Any, stats_key: str, counts: Mapping[str, int], floats: Mapping[str, float]) -> None:
    try:
        pipe = client.pipeline()
        for name, value in counts.items():
            if value:
                pipe.hincrby(stats_key, name, int(value))
        for name, value in floats.items():
            pipe.hincrbyfloat(stats_key, name, round(float(value), 3))
        pipe.expire(stats_key, _STATS_TTL_S)
        pipe.execute()
    except Exception:
        logger.warning("[FragVer2] shadow stats write failed (non-fatal)", exc_info=True)


def _record_mismatch(client: Any, route_id: str, req: Any, result: PrerenderKey,
                     prev: Mapping[str, Any], deploy: str) -> None:
    """원인 판정 재료를 남긴다 — 인자 **이름**·대리 접속 여부·두 관측의 배포 id(업무 데이터 없음)."""
    entry = json.dumps({
        "at": now_utc_naive().isoformat(), "route": route_id, "key": result.key,
        "args": sorted(req.args.keys()), "impersonating": bool(session.get("impersonating_from")),
        "deploy_prev": prev.get("d"), "deploy_now": deploy,
    }, ensure_ascii=False)
    try:
        pipe = client.pipeline()
        pipe.lpush(_MISMATCH_LOG_KEY, entry)
        pipe.ltrim(_MISMATCH_LOG_KEY, 0, _MISMATCH_LOG_MAX - 1)
        pipe.execute()
    except Exception:
        logger.warning("[FragVer2] mismatch log write failed (non-fatal)", exc_info=True)


def read_shadow_stats(client: Any, route_id: str, days: Iterable[str]) -> dict[str, float]:
    """여러 날(KST ``YYYY-MM-DD``)의 관측 카운터를 합친다."""
    total: dict[str, float] = {}
    for day in days:
        raw = client.hgetall(f"{REDIS_PREFIX}:stats:{route_id}:{day}") or {}
        for name, value in raw.items():
            total[str(name)] = total.get(str(name), 0.0) + float(value)
    return total


def judge_shadow_stats(stats: Mapping[str, float]) -> dict[str, Any]:
    """1단계 → 2단계 기준(§3.7)으로 판정한다.

    기준: 관측 1,000건 이상 · 본 키 MISMATCH 0 · 대조 키 mismatch 1건 이상(계기가 빠뜨림을 잡는다는
    증거) · 적중률 50% 이상 · 키 계산이 렌더의 30% 이하인 요청이 절반 이상(= p50 비율 30% 이하).
    적중률 분모는 판정 가능한 관측(hit + miss + miss_same_body + MISMATCH)이다 — ``new`` 는 앞 응답의
    키를 몰라 판정할 수 없고, 켠 뒤에도 그 요청은 렌더한다(``hit_rate_all`` 로 함께 보인다).
    """
    def get(name: str) -> float:
        return float(stats.get(name, 0.0))

    decided = get("hit") + get("miss") + get("miss_same_body") + get("mismatch")
    ratio_n = get("ratio_n")
    control_mismatch = sum(v for k, v in stats.items() if k.startswith("ctl.") and k.endswith(".mismatch"))
    out = {
        "observations": get("obs"),
        "mismatch": get("mismatch"),
        "race": get("race"),
        "abandon": get("abandon"),
        "control_mismatch": control_mismatch,
        "hit_rate": get("hit") / decided if decided else 0.0,
        "hit_rate_all": get("hit") / (get("obs") - get("abandon")) if get("obs") > get("abandon") else 0.0,
        "key_ratio_ok_share": get("ratio_ok") / ratio_n if ratio_n else 0.0,
        "key_ms_avg": get("key_ms_sum") / ratio_n if ratio_n else 0.0,
        "render_ms_avg": get("render_ms_sum") / ratio_n if ratio_n else 0.0,
    }
    out["passed"] = bool(
        out["observations"] >= GATE_MIN_OBSERVATIONS
        and out["mismatch"] == 0
        and control_mismatch > 0
        and out["hit_rate"] >= GATE_MIN_HIT_RATE
        and out["key_ratio_ok_share"] >= 0.5
    )
    return out
