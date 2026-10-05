"""생산 탭 렌더 전 304 키 계약 (하트비트 설계서 2026-10-05 §5.1, 1단계).

1. 입력 기록 계약 — 생산 탭 렌더가 읽은 인자·쿠키·헤더·세션 키·env·표·설정 키를 실제로 기록해,
   전부 키 명세 안에 있어야 한다(``tests/support/render_input_recorder.py``).
2. 행동 계약(변이표) — 입력을 하나씩 바꿔 "본문이 바뀌었으면 키도 바뀌었다"를 단언한다. 변이마다
   본문이 실제로 바뀌는지도 단언한다(안 바뀌는 변이는 아무것도 증명하지 못한다).
3. 음성 대조군 — 재료 하나를 뺀 약한 키·약한 명세로 1·2 를 돌리면 **반드시** 실패해야 한다.

키는 실제 요청 경로에서 뽑는다: 그림자 관측을 켜고(env + Redis 대역 + If-None-Match) 뷰가
``observe_shadow`` 에 넘기는 키를 가로챈다 — 렌더와 같은 요청에서 만든 키다.
"""

from __future__ import annotations

import datetime
from typing import Callable

import pytest
from flask import request

from db import engine
from foms.services import production_fragment_version as pfv
from foms.services.common import dashboard_cache
from foms.services.common import fragment_prerender as fp
from foms.services.datetime_kst import get_today_kst
from tests.support.production_prerender_board import (  # noqa: F401 - 픽스처는 이름으로 등록된다
    KANBAN_COOKIES,
    PATH,
    PC_COOKIES,
    _clean_process_caches,
    _login,
    _m_attachment_add,
    _m_attachment_delete,
    _m_cookie,
    _m_customer_name,
    _m_env,
    _m_event_only,
    _m_impersonation,
    _m_nav_badge,
    _m_role,
    _m_run_add,
    _m_schedule_date,
    _m_setting,
    _m_stage,
    _m_tombstone,
    _m_tombstone_only,
    _m_user_name,
    _render,
    _run_mutation,
    _seed,
    _set_cookies,
    _sqlite_attachment_counts,
    _v2_cohort,
    _weaken,
    shadow,
)
from tests.support.render_input_recorder import ALL, RenderInputLog, record_render_inputs


# --------------------------------------------------------------------------- 1. 입력 기록 계약

#: 키 명세 — 키가 실제로 담는 재료. ``*``(인자 통째 읽기)는 원래 쿼리 문자열 전체가 키에 있고
#: 모르는 인자면 키를 포기하므로 덮인다.
def _key_spec() -> dict[str, set[str]]:
    return {
        "args": set(pfv.KEY_ARGS) | set(fp.SHELL_ARGS) | {"view", ALL},
        "cookies": set(fp.SHELL_COOKIES),
        "headers": set(fp.SHELL_HEADERS),
        "session_keys": set(fp.SHELL_SESSION_KEYS),
        # 그림자 플래그는 관측만 켠다 — 본문 불변은 test_production_prerender_shadow.py 가 고정한다.
        "env": set(fp.SHELL_ENV) | {fp.SHADOW_ENV_FLAG},
        "tables": set(pfv.KEY_TABLES),
        "setting_keys": set(pfv.KEY_SETTING_KEYS),
    }


def _violations(log: RenderInputLog, spec: dict[str, set[str]]) -> dict[str, list[str]]:
    out = {bucket: sorted(getattr(log, bucket) - allowed) for bucket, allowed in spec.items()}
    out = {bucket: names for bucket, names in out.items() if names}
    if log.writes:
        out["writes"] = log.writes
    return out


def _record(app, client, monkeypatch, cookies: dict[str, str], path: str = PATH) -> RenderInputLog:
    _set_cookies(client, cookies)
    with record_render_inputs(app, "erp_production_page.erp_production_dashboard", monkeypatch, engine) as log:
        resp = client.get(path, headers={"X-FOMS-ERP-SHELL": "1"})
    assert resp.status_code == 200
    return log


@pytest.mark.parametrize(
    ("v2", "cookies", "path"),
    [
        (True, KANBAN_COOKIES, PATH),
        (True, PC_COOKIES, PATH + "&stage=제작중&sort=measure_date&dir=desc&page=1"),
        (False, PC_COOKIES, PATH + "&mine=1&q=고객"),
        (False, {}, PATH + "&tower_mine=1&search=고객"),
    ],
)
def test_every_render_input_is_in_the_key_spec(app, client, monkeypatch, v2, cookies, path):
    if v2:
        _v2_cohort(monkeypatch)
    _login(client, _seed()["admin"])
    log = _record(app, client, monkeypatch, cookies, path)
    assert log.tables >= {"orders"}, "기록기가 SQL 을 못 본다"
    assert log.cookies, "기록기가 쿠키 읽기를 못 본다"
    assert _violations(log, _key_spec()) == {}


def test_shell_material_echoes_full_path_so_arg_iteration_is_covered(app):
    """``request.args`` 통째 읽기(페이저 링크)는 원래 쿼리 문자열 전체로 덮는다."""
    with app.test_request_context("/erp/production/dashboard?b=1&view=fragment&a=2"):
        assert fp.normalized_args(request, ("a", "b")) == [["a", "2"], ["b", "1"], ["view", "fragment"]]
        assert fp.normalized_args(request, ("a",)) is None


@pytest.mark.parametrize(
    ("bucket", "drop"),
    [("cookies", "foms_vw"), ("args", "tower_mine"), ("tables", "order_events"), ("session_keys", "impersonating_from")],
)
def test_negative_control_weakened_spec_fails_input_contract(app, client, monkeypatch, bucket, drop):
    """명세에서 실제 재료 하나를 빼면 기록 계약이 반드시 실패한다(계약이 무언가를 잡는다는 증거)."""
    _v2_cohort(monkeypatch)
    _login(client, _seed()["admin"])
    path = PATH + "&tower_mine=1" if drop == "tower_mine" else PATH
    cookies = PC_COOKIES if drop == "foms_vw" else KANBAN_COOKIES
    log = _record(app, client, monkeypatch, cookies, path)
    spec = _key_spec()
    spec[bucket] = spec[bucket] - {drop}
    assert drop in _violations(log, spec).get(bucket, []), _violations(log, spec)


# --------------------------------------------------------------------------- 2. 행동 계약(변이표)


MUTATIONS: list[tuple[str, Callable, dict[str, str]]] = [
    ("customer_name", _m_customer_name, KANBAN_COOKIES),
    ("stage", _m_stage, KANBAN_COOKIES),
    ("schedule_date", _m_schedule_date, KANBAN_COOKIES),
    ("attachment_add", _m_attachment_add, KANBAN_COOKIES),
    ("attachment_delete", _m_attachment_delete, KANBAN_COOKIES),
    ("user_name", _m_user_name, KANBAN_COOKIES),
    ("role", _m_role, KANBAN_COOKIES),
    ("setting", _m_setting, KANBAN_COOKIES),
    ("run_add", _m_run_add, KANBAN_COOKIES),
    ("event_only", _m_event_only, KANBAN_COOKIES),
    ("tombstone", _m_tombstone, KANBAN_COOKIES),
    ("tombstone_only", _m_tombstone_only, KANBAN_COOKIES),
    ("cookie_ptr", _m_cookie("foms_ptr", "fine"), KANBAN_COOKIES),
    ("cookie_vw", _m_cookie("foms_vw", "narrow"), PC_COOKIES),
    ("cookie_scr", _m_cookie("foms_scr", "700"), PC_COOKIES),
    ("cookie_mine", _m_cookie("erp_mine_only", "1"), KANBAN_COOKIES),
    ("env_offline_sw", _m_env("FOMS_OFFLINE_SW_ENABLED", "1"), KANBAN_COOKIES),
    ("env_bottom_nav", _m_env("FOMS_BOTTOM_NAV_HTMX_ENABLED", "1"), KANBAN_COOKIES),
    ("env_v2_off", _m_env("ERP_MOBILE_V2_ENABLED", "false"), KANBAN_COOKIES),
    ("impersonation", _m_impersonation, KANBAN_COOKIES),
    ("nav_badge", _m_nav_badge, KANBAN_COOKIES),
]


@pytest.mark.parametrize(("name", "mutate", "cookies"), MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_mutation_that_changes_the_body_changes_the_key(client, monkeypatch, shadow, name, mutate, cookies):
    body_a, key_a, body_b, key_b = _run_mutation(client, monkeypatch, shadow, mutate, cookies)
    assert body_a != body_b, f"{name}: 변이가 본문을 안 바꾼다 — 이 변이는 아무것도 증명하지 못한다"
    assert key_a.key != key_b.key, f"{name}: 본문이 바뀌었는데 키가 그대로다 — 키에 빠진 재료가 있다"


def test_arg_order_alone_changes_body_and_key(client, monkeypatch, shadow):
    """셸 머리가 ``request.full_path`` 를 본문에 박으므로 인자 순서만 달라도 본문이 갈린다."""
    body_a, key_a, body_b, key_b = _run_mutation(
        client, monkeypatch, shadow, lambda *a: None, KANBAN_COOKIES,
        path=PATH + "&stage=&mine=0", path_after="/erp/production/dashboard?mine=0&stage=&view=fragment",
    )
    assert body_a != body_b
    assert key_a.key != key_b.key


def test_same_inputs_give_the_same_key_and_body(client, monkeypatch, shadow):
    body_a, key_a, body_b, key_b = _run_mutation(client, monkeypatch, shadow, lambda *a: None, KANBAN_COOKIES)
    assert body_a == body_b
    assert key_a.key == key_b.key and key_a.controls == key_b.controls


def test_stale_summary_slice_cannot_be_trapped(client, monkeypatch, shadow):
    """조각 갇힘(§3.3): 무효화를 빠뜨려 낡은 숫자판이 렌더되다가 TTL·무효화로 새로 계산되면, 행은 그대로라도
    키가 바뀌어야 한다 — 조각 값 digest 가 키에 있어서다."""
    monkeypatch.setenv("REDIS_URL", "redis://fake")
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _v2_cohort(monkeypatch)
    ctx = _seed()
    _login(client, ctx["admin"])
    _set_cookies(client, KANBAN_COOKIES)
    _render(client, shadow)  # 숫자판 조각이 캐시에 든다
    _m_run_add(ctx, client, monkeypatch)  # 제작대기→제작중 — 숫자판이 바뀌어야 하지만 무효화는 없다
    body_stale, key_stale = _render(client, shadow)  # 낡은 숫자판 + 새 행
    dashboard_cache.invalidate_dashboard_family("production")  # TTL 만료와 같은 효과
    body_fresh, key_fresh = _render(client, shadow)  # 행은 그대로, 숫자판만 새로 계산
    assert body_stale != body_fresh, "숫자판이 새로 계산됐는데 본문이 그대로다 — 시나리오가 성립하지 않는다"
    assert key_stale.key != key_fresh.key
    assert key_stale.controls["no_order_rows"] != key_fresh.controls["no_order_rows"]


# --------------------------------------------------------------------------- 3. 음성 대조군


@pytest.mark.parametrize(
    ("control", "mutate"),
    [("no_order_rows", _m_customer_name), ("no_order_events", _m_event_only)],
)
def test_negative_control_weakened_key_misses_a_real_change(client, monkeypatch, shadow, control, mutate):
    """대조 키(재료 한 갈래를 뺀 키)는 같은 변이에서 본문이 바뀌어도 그대로여야 한다 — 계약이 잡는다는 증거."""
    body_a, key_a, body_b, key_b = _run_mutation(client, monkeypatch, shadow, mutate, KANBAN_COOKIES)
    assert body_a != body_b
    assert key_a.key != key_b.key
    assert key_a.controls[control] == key_b.controls[control], "대조 키가 변화를 잡았다 — 대조군이 약하지 않다"


@pytest.mark.parametrize(
    ("path", "mutate", "query"),
    [
        ((("full_path",),), None, ("&stage=&mine=0", "/erp/production/dashboard?mine=0&stage=&view=fragment")),
        ((("nav_badges",),), _m_nav_badge, None),
        ((("data", "att"), ("data", "att_slice")), _m_attachment_add, None),
        ((("data", "tomb"),), _m_tombstone_only, None),
    ],
    ids=["full_path", "nav_badges", "attachments", "tombstones"],
)
def test_negative_control_weakened_material_breaks_the_mutation_contract(client, monkeypatch, shadow, path, mutate, query):
    """실제 재료 한 갈래를 뺀 키로 변이표를 돌리면 "본문은 바뀌었는데 키는 그대로"가 나와야 한다."""
    _weaken(monkeypatch, path)
    if query:
        body_a, key_a, body_b, key_b = _run_mutation(
            client, monkeypatch, shadow, lambda *a: None, KANBAN_COOKIES, path=PATH + query[0], path_after=query[1]
        )
    else:
        body_a, key_a, body_b, key_b = _run_mutation(client, monkeypatch, shadow, mutate, KANBAN_COOKIES)
    assert body_a != body_b
    assert key_a.key == key_b.key, f"{path} 를 뺐는데도 키가 바뀌었다 — 이 대조군으로는 빠뜨림을 못 잡는다"


# --------------------------------------------------------------------------- 시간 축


def test_time_bucket_flips_within_c_seconds_and_spreads_users():
    base = 1_790_000_000.0
    for uid in (1, 2, 58):
        start = fp.time_bucket(uid, base)
        assert fp.time_bucket(uid, base + fp.FRESHNESS_BUCKET_S) == start + 1
        assert fp.time_bucket(uid, base + 3600) != start
        assert fp.time_bucket(uid, base + 86400) != start
        assert fp.time_bucket(uid, base + 60 * 86400) != start
    offsets = {fp.time_bucket(uid, base) - int(base) // fp.FRESHNESS_BUCKET_S for uid in range(1, 40)}
    assert offsets == {0, 1}, "uid 별 어긋남이 경계를 흩어야 한다"


def test_clock_and_kst_date_are_key_material(client, monkeypatch, shadow):
    _v2_cohort(monkeypatch)
    ctx = _seed()
    _login(client, ctx["admin"])
    _set_cookies(client, KANBAN_COOKIES)
    _, key_a = _render(client, shadow)
    monkeypatch.setattr(fp, "_now_s", lambda: 1_790_000_000.0 + fp.FRESHNESS_BUCKET_S)
    _, key_b = _render(client, shadow)
    assert key_a.key != key_b.key, "300초가 지나면 키가 바뀌어야 한다(신선도 상한)"
    monkeypatch.setattr(fp, "get_today_kst", lambda: get_today_kst() + datetime.timedelta(days=1))
    _, key_c = _render(client, shadow)
    assert key_b.key != key_c.key, "KST 날짜가 넘어가면 키가 바뀌어야 한다"
