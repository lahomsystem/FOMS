"""생산 탭 렌더 전 304 그림자 관측 — 켜는 조건·응답 불변·판정·카운터 (하트비트 설계서 2026-10-05 §3.5·§3.7·§5.1).

이번 단계는 304 를 **내지 않는다**. 고정하는 것:

- 끄기 세 겹: env 기본 꺼짐 · Redis 끄기 키(전체·탭별) · Redis 없음 → 키를 아예 만들지 않는다.
- 조건부 요청(If-None-Match)에서만 키를 만든다 — 화면 전환(조건 없음)에는 일을 더하지 않는다.
- 켜도 응답(상태·본문·ETag·304)은 꺼졌을 때와 같다.
- 판정: new → hit, 본문이 바뀌면 miss(대조 키는 mismatch), 빠진 재료가 있으면 MISMATCH(+상세 기록),
  키 계산과 렌더 사이 커밋은 race 이고 다음 요청은 hit 이 아니다(순서 계약 §5.1-4).
- 포기: focus_order · 모르는 인자 · 키 계산 오류 → abandon, 응답은 그대로.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

import foms.web.production.dashboard as pd
from db import db_session
from foms.services import production_fragment_version as pfv
from foms.services.common import dashboard_cache
from foms.services.common import fragment_prerender as fp
from foms.services.datetime_kst import get_today_kst
from models import Order
from tests.support.production_prerender_board import (  # noqa: F401 - autouse 픽스처는 이름으로 등록된다
    KANBAN_COOKIES,
    PATH,
    _clean_process_caches,
    _get,
    _login,
    _m_customer_name,
    _seed,
    _set_cookies,
    _sqlite_attachment_counts,
    _v2_cohort,
    _weaken,
)
from tests.support.fragver_fake_redis import FakeRedis

SHELL = {"X-FOMS-ERP-SHELL": "1"}


@pytest.fixture
def redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: fake)
    monkeypatch.setattr(fp, "_now_s", lambda: 1_790_000_000.0)
    return fake


@pytest.fixture
def board(client, monkeypatch) -> dict[str, Any]:
    _v2_cohort(monkeypatch)
    ctx = _seed()
    _login(client, ctx["admin"])
    _set_cookies(client, KANBAN_COOKIES)
    return ctx


@pytest.fixture
def key_calls(monkeypatch) -> list[int]:
    calls: list[int] = []
    original = pd.compute_production_key

    def _counting(*args: Any, **kwargs: Any):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pd, "compute_production_key", _counting)
    return calls


def _get_fragment(client, validator: str | None = '"seed"', path: str = PATH):
    headers = dict(SHELL)
    if validator:
        headers["If-None-Match"] = validator
    return client.get(path, headers=headers)


def _stats(redis: FakeRedis) -> dict[str, float]:
    return fp.read_shadow_stats(redis, pfv.ROUTE_ID, [get_today_kst().isoformat()])


# --------------------------------------------------------------------------- 끄기·켜는 조건


def test_flag_is_off_by_default(client, board, redis, key_calls, monkeypatch):
    monkeypatch.delenv(fp.SHADOW_ENV_FLAG, raising=False)
    resp = _get_fragment(client)
    assert resp.status_code == 200
    assert key_calls == []
    assert fp.SHADOW_HEADER not in resp.headers
    assert redis.hashes == {}


def test_unconditional_request_never_computes_a_key(client, board, redis, key_calls, monkeypatch):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    resp = _get_fragment(client, validator=None)
    assert resp.status_code == 200 and key_calls == []
    assert fp.SHADOW_HEADER not in resp.headers


@pytest.mark.parametrize("kill_key", [fp.KILL_SWITCH_KEY, f"{fp.KILL_SWITCH_KEY}:{pfv.ROUTE_ID}"])
def test_redis_kill_switch_turns_shadow_off_without_deploy(client, board, redis, key_calls, monkeypatch, kill_key):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    redis.set(kill_key, "1")
    resp = _get_fragment(client)
    assert resp.status_code == 200 and key_calls == []
    assert fp.SHADOW_HEADER not in resp.headers


def test_no_redis_means_off(client, board, key_calls, monkeypatch):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: None)
    resp = _get_fragment(client)
    assert resp.status_code == 200 and key_calls == []


def test_kill_switch_read_failure_means_off(client, board, key_calls, monkeypatch):
    class _Broken(FakeRedis):
        def mget(self, keys):
            raise ConnectionError("redis down")

    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    broken = _Broken()
    monkeypatch.setattr(dashboard_cache, "get_dashboard_redis", lambda: broken)
    assert _get_fragment(client).status_code == 200
    assert key_calls == []


# --------------------------------------------------------------------------- 응답 불변


def test_shadow_does_not_change_the_response(client, board, redis, monkeypatch):
    off = _get_fragment(client)
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    on = _get_fragment(client)
    assert (on.status_code, on.data, on.headers.get("ETag")) == (off.status_code, off.data, off.headers.get("ETag"))
    # 진짜 검증자를 들고 오면 지금처럼 렌더 후 304 — 그림자는 판정만 남긴다.
    again = _get_fragment(client, validator=on.headers["ETag"])
    assert again.status_code == 304 and again.data == b""
    assert again.headers.get(fp.SHADOW_HEADER) == fp.STATE_HIT


# --------------------------------------------------------------------------- 판정·카운터


def test_new_then_hit_and_counters(client, board, redis, monkeypatch):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    first = _get_fragment(client)
    assert first.headers[fp.SHADOW_HEADER] == fp.STATE_NEW
    second = _get_fragment(client, validator=first.headers["ETag"])
    assert second.headers[fp.SHADOW_HEADER] == fp.STATE_HIT
    stats = _stats(redis)
    assert stats["obs"] == 2 and stats["new"] == 1 and stats["hit"] == 1
    assert stats["ctl.no_order_rows.hit"] == 1 and stats["ctl.no_order_events.hit"] == 1
    assert stats["ratio_n"] == 2 and "key_ms_sum" in stats and "render_ms_sum" in stats


def test_changed_body_is_a_miss_and_the_weak_control_reports_mismatch(client, board, redis, monkeypatch):
    """본 키는 변화를 잡아 miss, 주문 창 지문을 뺀 대조 키는 같은 변화를 못 잡아 mismatch — 계기가 산다."""
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    first = _get_fragment(client)
    _m_customer_name(board, client, monkeypatch)
    second = _get_fragment(client, validator=f'{first.headers["ETag"][:-1]}:zstd"')  # 압축 접미사를 벗겨 비교한다
    assert second.status_code == 200
    assert second.headers[fp.SHADOW_HEADER] == fp.STATE_MISS
    stats = _stats(redis)
    assert stats["miss"] == 1 and stats.get("mismatch", 0) == 0
    assert stats["ctl.no_order_rows.mismatch"] == 1
    assert fp.judge_shadow_stats(stats)["control_mismatch"] == 1


def test_missing_ingredient_is_reported_as_mismatch_with_detail(client, board, redis, monkeypatch, caplog):
    """키에서 주문 창 지문을 빼면(빠뜨림 재현) 같은 키·다른 본문 → MISMATCH 와 원인 판정 재료."""
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    _weaken(monkeypatch, (("data", "window"),))
    first = _get_fragment(client, path=PATH + "&stage=")
    _m_customer_name(board, client, monkeypatch)
    with caplog.at_level(logging.WARNING, logger=fp.__name__):
        second = _get_fragment(client, validator=first.headers["ETag"], path=PATH + "&stage=")
    assert second.status_code == 200
    assert second.headers[fp.SHADOW_HEADER] == fp.STATE_MISMATCH
    assert _stats(redis)["mismatch"] == 1
    entry = json.loads(redis.lists[f"{fp.REDIS_PREFIX}:mismatch_log"][0])
    assert entry["route"] == pfv.ROUTE_ID and entry["args"] == ["stage", "view"]
    assert entry["impersonating"] is False and "deploy_prev" in entry
    assert "대기고객" not in json.dumps(entry, ensure_ascii=False), "상세에 업무 데이터가 새면 안 된다"
    assert any("MISMATCH" in r.getMessage() for r in caplog.records)
    assert fp.judge_shadow_stats(_stats(redis))["passed"] is False


def test_commit_between_key_and_render_is_race_and_next_request_renders(client, board, redis, monkeypatch):
    """순서 계약(§5.1-4): 키를 만든 뒤 데이터를 읽기 전에 커밋이 끼면 그 요청은 race, 다음 요청은 hit 이 아니다."""
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    first = _get_fragment(client)
    original = pd.compute_production_key
    state = {"done": False}

    def _key_then_commit(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        if not state["done"]:
            state["done"] = True
            order = _get(Order, board["orders"][1])
            sd = dict(order.structured_data)
            sd["parties"] = {**sd["parties"], "customer": {"name": "끼어든고객"}}
            order.structured_data = sd
            db_session.commit()
        return result

    monkeypatch.setattr(pd, "compute_production_key", _key_then_commit)
    second = _get_fragment(client, validator=first.headers["ETag"])
    assert second.headers[fp.SHADOW_HEADER] == fp.STATE_RACE
    third = _get_fragment(client, validator=second.headers["ETag"])
    assert third.headers[fp.SHADOW_HEADER] in (fp.STATE_MISS, fp.STATE_MISS_SAME_BODY)
    assert _stats(redis).get("mismatch", 0) == 0


@pytest.mark.parametrize(
    ("path", "reason"),
    [(PATH + "&focus_order=1", "focus_order"), (PATH + "&utm=1", "unknown_arg")],
)
def test_unknown_or_unsupported_args_abandon(client, board, redis, monkeypatch, caplog, path, reason):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    with caplog.at_level(logging.INFO, logger=fp.__name__):
        resp = _get_fragment(client, path=path)
    assert resp.status_code == 200
    assert resp.headers[fp.SHADOW_HEADER] == fp.STATE_ABANDON
    assert _stats(redis)["abandon"] == 1
    assert any(f"reason={reason}" in r.getMessage() for r in caplog.records)


def test_key_failure_never_breaks_the_page(client, board, redis, monkeypatch):
    monkeypatch.setenv(fp.SHADOW_ENV_FLAG, "1")
    baseline = _get_fragment(client)

    def _boom(*args: Any, **kwargs: Any):
        raise RuntimeError("fingerprint SQL failed")

    monkeypatch.setattr(pfv, "_production_material", _boom)
    resp = _get_fragment(client)
    assert resp.status_code == 200 and resp.data == baseline.data
    assert resp.headers[fp.SHADOW_HEADER] == fp.STATE_ABANDON


# --------------------------------------------------------------------------- 넘어가는 기준


def _good_stats(**over: float) -> dict[str, float]:
    stats = {"obs": 1200, "new": 100, "hit": 800, "miss": 300, "ratio_n": 1100, "ratio_ok": 900,
             "ctl.no_order_rows.mismatch": 4, "key_ms_sum": 11000, "render_ms_sum": 99000}
    stats.update(over)
    return stats


def test_judge_passes_only_when_every_threshold_holds():
    assert fp.judge_shadow_stats(_good_stats())["passed"] is True
    assert fp.judge_shadow_stats(_good_stats(mismatch=1))["passed"] is False
    assert fp.judge_shadow_stats(_good_stats(obs=999))["passed"] is False
    assert fp.judge_shadow_stats(_good_stats(**{"ctl.no_order_rows.mismatch": 0}))["passed"] is False
    assert fp.judge_shadow_stats(_good_stats(hit=200, miss=900))["passed"] is False
    assert fp.judge_shadow_stats(_good_stats(ratio_ok=500))["passed"] is False
    verdict = fp.judge_shadow_stats(_good_stats())
    assert verdict["hit_rate"] == pytest.approx(800 / 1100)
    assert verdict["key_ms_avg"] == pytest.approx(10.0)
