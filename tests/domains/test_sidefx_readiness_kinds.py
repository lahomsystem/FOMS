"""OPS-HEARTBEAT-01: readiness 판정이 outbox 밖 loop kind 도 읽는지 못박는다.

2026-09-07 실측(F-9): ``NAVER_AUTO_DISPATCH``·``GEOCODE_SWEEP`` 루프는 하트비트를
``side_effect_worker_heartbeats`` 에 쓰지만 판정부가 ``WORKER_KINDS`` 3종만 순회해
**아무도 읽지 않았다** — 루프가 멎어도 어떤 게이트도 빨개지지 않는다.

여기서 지키는 계약:

* 기본 판정 대상은 여전히 outbox 3종이다(release gate 의 뜻을 바꾸지 않는다).
* ``kinds`` 로 고른 kind 는 누락·stale 이 실제로 not-ready 가 된다.
* outbox 밖 kind 는 자기 tick 예산(등록부)을 쓴다 — CLI flag(3종 기준 30초)를 씌우지 않는다.
* outbox 를 하나도 안 고른 판정은 PENDING lag·DEAD 를 세지 않는다(무관한 이유의 red 금지).
* 하트비트를 **쓰는 쪽**(러너 2종)이 등록부 상수를 그대로 쓴다 — 이름이 갈리면 red.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from foms.services.sidefx_worker import (
    WORKER_KIND_DELIVERY,
    WORKER_KIND_EXPIRY_SCAN,
    WORKER_KIND_GEOCODE_SWEEP,
    WORKER_KIND_NAVER_AUTO_DISPATCH,
    WORKER_KIND_RETENTION,
    WORKER_KIND_SPECS,
    WORKER_KINDS,
    ReadinessThresholds,
    evaluate_readiness,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 하트비트를 쓰는 러너 → 그 러너가 써야 하는 등록부 상수 이름.
_EMITTERS = {
    "scripts/maintenance/run_naver_auto_dispatch.py": "WORKER_KIND_NAVER_AUTO_DISPATCH",
    "scripts/maintenance/run_geocode_sweep.py": "WORKER_KIND_GEOCODE_SWEEP",
}


def _obs(**over):
    """outbox 3종이 건강한 관측치. ``over`` 로 필요한 축만 갈아 끼운다."""
    base = {
        "heartbeats": {
            WORKER_KIND_DELIVERY: {"age_seconds": 5, "oldest_lag_seconds": 2},
            WORKER_KIND_EXPIRY_SCAN: {"age_seconds": 5, "oldest_lag_seconds": 30},
            WORKER_KIND_RETENTION: {"age_seconds": 5, "oldest_lag_seconds": 100},
        },
        "oldest_pending_lag": 4,
        "dead_count": 0,
    }
    base.update(over)
    return base


def _checks(report) -> set:
    return {f["check"] for f in report.failures}


def test_new_loop_kinds_are_registered():
    """등록부에 없는 kind 는 판정 대상이 될 수 없다 — 두 루프가 등록돼 있어야 한다."""
    assert WORKER_KIND_NAVER_AUTO_DISPATCH in WORKER_KIND_SPECS
    assert WORKER_KIND_GEOCODE_SWEEP in WORKER_KIND_SPECS
    assert not WORKER_KIND_SPECS[WORKER_KIND_NAVER_AUTO_DISPATCH].outbox_scoped
    assert not WORKER_KIND_SPECS[WORKER_KIND_GEOCODE_SWEEP].outbox_scoped


def test_default_selection_stays_outbox_three():
    """기본 판정은 outbox 3종 그대로 — 새 kind 가 없어도 ready 다(기존 게이트 불변)."""
    assert WORKER_KINDS == (WORKER_KIND_DELIVERY, WORKER_KIND_EXPIRY_SCAN,
                            WORKER_KIND_RETENTION)
    report = evaluate_readiness(_obs(), ReadinessThresholds())
    assert report.ready and report.failures == []


def test_selected_new_kind_missing_heartbeat_is_not_ready():
    """루프가 하트비트를 한 번도 안 썼으면 not-ready(누락 = 안 도는 것)."""
    report = evaluate_readiness(_obs(), ReadinessThresholds(),
                                kinds=[WORKER_KIND_GEOCODE_SWEEP])
    assert not report.ready
    assert _checks(report) == {"heartbeat_present"}


def test_selected_new_kind_stale_heartbeat_is_not_ready():
    """멎은 루프는 stale 로 잡힌다 — 예산은 등록부 값(180초)이 그대로 보고된다."""
    hb = dict(_obs()["heartbeats"])
    hb[WORKER_KIND_NAVER_AUTO_DISPATCH] = {"age_seconds": 999, "oldest_lag_seconds": None}
    report = evaluate_readiness(_obs(heartbeats=hb), ReadinessThresholds(),
                                kinds=[WORKER_KIND_NAVER_AUTO_DISPATCH])
    assert not report.ready
    assert _checks(report) == {"heartbeat_fresh"}
    assert report.failures[0]["limit"] == 180


def test_new_kind_uses_own_budget_not_outbox_flag():
    """tick 60초 루프에 outbox 3종 예산(30초)을 씌우면 산 루프를 죽었다고 한다."""
    hb = dict(_obs()["heartbeats"])
    hb[WORKER_KIND_GEOCODE_SWEEP] = {"age_seconds": 61, "oldest_lag_seconds": None}
    report = evaluate_readiness(_obs(heartbeats=hb), ReadinessThresholds(),
                                kinds=[WORKER_KIND_GEOCODE_SWEEP])
    assert report.ready, report.failures


def test_explicit_flag_overrides_every_selected_kind():
    """운영자가 간격을 env 로 바꿨을 때의 탈출구 — 준 값이 대상 kind 전부에 적용된다."""
    hb = dict(_obs()["heartbeats"])
    hb[WORKER_KIND_GEOCODE_SWEEP] = {"age_seconds": 61, "oldest_lag_seconds": None}
    report = evaluate_readiness(_obs(heartbeats=hb),
                                ReadinessThresholds(max_heartbeat_age=30),
                                kinds=[WORKER_KIND_GEOCODE_SWEEP])
    assert not report.ready
    assert report.failures[0]["limit"] == 30


def test_new_kind_has_no_scan_lag_check():
    """scan 루프가 아닌 kind 에 scan lag 를 요구하면 영원히 not-ready 가 된다."""
    hb = dict(_obs()["heartbeats"])
    hb[WORKER_KIND_GEOCODE_SWEEP] = {"age_seconds": 5, "oldest_lag_seconds": None}
    report = evaluate_readiness(_obs(heartbeats=hb), ReadinessThresholds(),
                                kinds=[WORKER_KIND_GEOCODE_SWEEP])
    assert report.ready, report.failures


def test_non_outbox_selection_skips_pending_and_dead():
    """outbox 를 안 고른 판정은 outbox 표 상태로 red 가 되지 않는다."""
    hb = dict(_obs()["heartbeats"])
    hb[WORKER_KIND_GEOCODE_SWEEP] = {"age_seconds": 5, "oldest_lag_seconds": None}
    report = evaluate_readiness(
        _obs(heartbeats=hb, oldest_pending_lag=9999, dead_count=7),
        ReadinessThresholds(), kinds=[WORKER_KIND_GEOCODE_SWEEP])
    assert report.ready, report.failures


def test_outbox_selection_still_counts_pending_and_dead():
    """앞 계약의 음성 대조군 — outbox kind 를 고르면 PENDING lag·DEAD 는 그대로 센다."""
    report = evaluate_readiness(_obs(oldest_pending_lag=9999, dead_count=7),
                                ReadinessThresholds(), kinds=[WORKER_KIND_DELIVERY])
    assert not report.ready
    assert _checks(report) == {"oldest_pending_lag", "dead_count"}


def test_unknown_kind_is_rejected():
    """오타 kind 를 조용히 통과시키면 '아무도 안 읽는' 상태로 되돌아간다."""
    with pytest.raises(ValueError):
        evaluate_readiness(_obs(), ReadinessThresholds(), kinds=["NO_SUCH_KIND"])


def test_empty_selection_is_rejected():
    """빈 kinds 는 볼 게 없어 ready 로 떨어진다 — 판정부에서도 막는다."""
    with pytest.raises(ValueError):
        evaluate_readiness(_obs(), ReadinessThresholds(), kinds=[])


def test_cli_default_is_all_kinds_none_and_empty_selection_is_rejected():
    """빈 선택은 판정할 게 없어 **무조건 ready** 가 된다 — fail-open 이라 거부해야 한다."""
    from tools.ops.check_sidefx_readiness import _parse_args, _parse_kinds

    assert _parse_args([]).kinds is None
    assert _parse_kinds(None) is None
    assert _parse_kinds(" NAVER_AUTO_DISPATCH , GEOCODE_SWEEP ") == [
        WORKER_KIND_NAVER_AUTO_DISPATCH, WORKER_KIND_GEOCODE_SWEEP]
    with pytest.raises(ValueError):
        _parse_kinds(" , ")


@pytest.mark.parametrize("rel_path,const_name", sorted(_EMITTERS.items()))
def test_emitter_uses_registry_constant(rel_path, const_name):
    """쓰는 쪽이 문자열 리터럴을 다시 박으면 읽는 쪽과 이름이 갈린다(F-9 의 형태)."""
    tree = ast.parse((_REPO_ROOT / rel_path).read_text(encoding="utf-8"))

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "foms.services.sidefx_worker"
        for alias in node.names
    }
    assert const_name in imported, f"{rel_path} 가 {const_name} 를 등록부에서 안 가져온다"

    assigned = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "HEARTBEAT_WORKER_KIND"
                for t in node.targets)
    ]
    assert len(assigned) == 1, f"{rel_path} 의 HEARTBEAT_WORKER_KIND 대입이 1개가 아니다"
    value = assigned[0]
    assert isinstance(value, ast.Name) and value.id == const_name, (
        f"{rel_path} 는 HEARTBEAT_WORKER_KIND 를 {const_name} 로 둬야 한다")
