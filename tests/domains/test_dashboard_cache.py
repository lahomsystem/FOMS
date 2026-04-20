"""Tests for foms.services.common.dashboard_cache (DMC-B1 contract)."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from foms.services.common import dashboard_cache as dc


@pytest.fixture(autouse=True)
def _reset_runtime():
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def test_build_dashboard_cache_key_stable():
    fp = {"user_id": 1, "q": {"page": "1", "tab": "all"}}
    k1 = dc.build_dashboard_cache_key("orders", "summary_counts", fp)
    k2 = dc.build_dashboard_cache_key("orders", "summary_counts", fp)
    assert k1 == k2
    assert k1.startswith(f"{dc.CACHE_KEY_PREFIX}:orders:summary_counts:")


def test_build_dashboard_cache_key_differs_on_fingerprint():
    a = dc.build_dashboard_cache_key("orders", "summary_counts", {"u": 1})
    b = dc.build_dashboard_cache_key("orders", "summary_counts", {"u": 2})
    assert a != b


def test_is_enabled_requires_redis_url_and_flag():
    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "1"},
        clear=False,
    ):
        assert dc.is_dashboard_micro_cache_enabled() is True
    with patch.dict(os.environ, {"REDIS_URL": ""}, clear=False):
        assert dc.is_dashboard_micro_cache_enabled() is False
    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://x", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "0"},
        clear=False,
    ):
        assert dc.is_dashboard_micro_cache_enabled() is False


def test_get_or_compute_bypass_when_disabled():
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"a": 1}

    with patch.object(dc, "is_dashboard_micro_cache_enabled", return_value=False):
        out = dc.get_or_compute_dashboard_slice(
            "foms:dashcache:v1:orders:x:abc",
            30,
            compute,
            page="orders",
            slice_name="x",
        )
    assert out == {"a": 1}
    assert calls["n"] == 1


def test_get_or_compute_uses_redis_when_enabled():
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, k: str):
            return store.get(k)

        def setex(self, k: str, ttl: int, v: str):
            store[k] = v

        def ping(self):
            return True

    fake = FakeRedis()
    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "true"},
        clear=False,
    ):
        with patch.object(dc, "get_dashboard_redis", return_value=fake):
            key = dc.build_dashboard_cache_key("orders", "t", {"u": 1})
            c1 = {"n": 0}

            def compute():
                c1["n"] += 1
                return {"v": 42}

            r1 = dc.get_or_compute_dashboard_slice(
                key, 30, compute, page="orders", slice_name="t"
            )
            r2 = dc.get_or_compute_dashboard_slice(
                key, 30, compute, page="orders", slice_name="t"
            )
    assert r1 == {"v": 42}
    assert r2 == {"v": 42}
    assert c1["n"] == 1
    raw = store[key]
    assert json.loads(raw) == {"v": 42}


def test_get_or_compute_skips_cache_on_non_json_result():
    calls = {"n": 0}

    class FakeRedis:
        def get(self, k: str):
            return None

        def setex(self, k: str, ttl: int, v: str):
            raise AssertionError("should not cache non-JSON")

        def ping(self):
            return True

    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "1"},
        clear=False,
    ):
        with patch.object(dc, "get_dashboard_redis", return_value=FakeRedis()):
            key = dc.build_dashboard_cache_key("orders", "bad", {"u": 1})

            def compute():
                calls["n"] += 1
                return object()

            out = dc.get_or_compute_dashboard_slice(
                key, 30, compute, page="orders", slice_name="bad"
            )
    assert isinstance(out, object)
    assert calls["n"] == 1


def test_invalidate_all_dashboard_slice_caches_calls_three_families():
    calls = []

    def fake_invalidate(fam: str) -> int:
        calls.append(fam)
        return 1

    with patch.object(dc, "invalidate_dashboard_family", side_effect=fake_invalidate):
        n = dc.invalidate_all_dashboard_slice_caches()
    assert n == 3
    assert calls == ["orders", "measurement", "shipment"]


def test_invalidate_dashboard_family_deletes_matching_keys():
    store = {
        "foms:dashcache:v1:orders:a:1": "1",
        "foms:dashcache:v1:orders:b:2": "2",
        "foms:dashcache:v1:measurement:x:3": "3",
    }

    class FakeRedis:
        def scan_iter(self, match: str, count: int = 500):
            import fnmatch

            for k in list(store):
                if fnmatch.fnmatch(k, match):
                    yield k

        def delete(self, k: str):
            store.pop(k, None)

        def ping(self):
            return True

    fake = FakeRedis()
    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "yes"},
        clear=False,
    ):
        with patch.object(dc, "get_dashboard_redis", return_value=fake):
            n = dc.invalidate_dashboard_family("orders")
    assert n == 2
    assert "foms:dashcache:v1:measurement:x:3" in store


def test_get_dashboard_redis_none_without_redis_url():
    with patch.dict(os.environ, {"REDIS_URL": ""}, clear=False):
        dc.reset_dashboard_cache_runtime_for_tests()
        assert dc.get_dashboard_redis() is None


def test_get_or_compute_logs_compute_ms_hit_and_miss(caplog):
    """§1.2.9: info 로그에 compute_ms(히트 시 0)가 포함된다."""
    import logging

    caplog.set_level(logging.INFO, logger="foms.services.common.dashboard_cache")
    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, k: str):
            return store.get(k)

        def setex(self, k: str, ttl: int, v: str):
            store[k] = v

        def ping(self):
            return True

    fake = FakeRedis()
    key = dc.build_dashboard_cache_key("orders", "timing", {"u": 1})

    def compute():
        return {"x": 1}

    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "1"},
        clear=False,
    ):
        with patch.object(dc, "get_dashboard_redis", return_value=fake):
            dc.get_or_compute_dashboard_slice(
                key, 30, compute, page="orders", slice_name="timing"
            )
            dc.get_or_compute_dashboard_slice(
                key, 30, compute, page="orders", slice_name="timing"
            )
    text = " ".join(caplog.messages)
    assert "result=miss" in text and "compute_ms=" in text
    assert "result=hit" in text and "compute_ms=0" in text


def test_dmc_b6_differential_same_payload_cache_on_vs_off():
    """Deterministic JSON payload matches whether micro-cache is on (Redis hit) or off."""
    key = dc.build_dashboard_cache_key("orders", "differential", {"u": 42})
    expected = {"a": 1, "b": ["x", "y"]}

    def compute():
        return dict(expected)

    with patch.object(dc, "is_dashboard_micro_cache_enabled", return_value=False):
        off1 = dc.get_or_compute_dashboard_slice(
            key, 30, compute, page="orders", slice_name="differential"
        )
        off2 = dc.get_or_compute_dashboard_slice(
            key, 30, compute, page="orders", slice_name="differential"
        )
    assert off1 == off2 == expected

    store: dict[str, str] = {}

    class FakeRedis:
        def get(self, k: str):
            return store.get(k)

        def setex(self, k: str, ttl: int, v: str):
            store[k] = v

        def ping(self):
            return True

    calls = {"n": 0}

    def compute_tracked():
        calls["n"] += 1
        return dict(expected)

    with patch.dict(
        os.environ,
        {"REDIS_URL": "redis://localhost:6379/0", "FOMS_DASHBOARD_MICRO_CACHE_ENABLED": "1"},
        clear=False,
    ):
        with patch.object(dc, "get_dashboard_redis", return_value=FakeRedis()):
            on1 = dc.get_or_compute_dashboard_slice(
                key, 30, compute_tracked, page="orders", slice_name="differential"
            )
            on2 = dc.get_or_compute_dashboard_slice(
                key, 30, compute_tracked, page="orders", slice_name="differential"
            )
    assert on1 == on2 == expected
    assert calls["n"] == 1
