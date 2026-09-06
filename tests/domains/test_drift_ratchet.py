"""드리프트 감사 게이트가 **기준선 래칫**인지 잠근다.

절대 0건 기준으로 두면 게이트가 첫날부터 매일 빨간불이고(2026-09-07 운영 실측 ERP flat
1,750건), 매일 오는 빨간불은 곧 아무도 안 본다. 그래서 판정은 순증만 본다. 이 파일은 그
계약이 조용히 뒤집히지 않게 한다 — 특히 "기준선이 없으면 통과" 로 무너지는 경로를 막는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.ops.drift_report_http import (
    BASELINE_PATH,
    compare_to_baseline,
    load_baseline,
    render_summary,
)


def _report(as_axis_drift: int, flat_drift: int) -> dict:
    """엔드포인트 ``data`` 모양의 최소 응답을 만든다."""
    return {
        "as_axis": {
            "checked": 659, "drift": as_axis_drift, "mismatch": as_axis_drift,
            "missing_projection": 0, "legacy_only": 0, "samples": [],
        },
        "erp_flat": {
            "total": 3001, "clean": 1251, "safe": 825, "ambiguous": 925,
            "drift": flat_drift, "ambiguous_reasons": {}, "samples": [],
        },
        "drift_total": as_axis_drift + flat_drift,
        "truncated": False,
        "elapsed_ms": 681,
    }


def test_committed_baseline_is_readable_and_matches_schema() -> None:
    """저장소에 든 기준선이 실제로 읽히고 스키마가 맞다."""
    baseline = load_baseline()
    assert baseline["schema"] == "drift-ratchet/1"
    assert baseline["as_axis"]["must_stay_zero"] is True
    assert baseline["as_axis"]["drift"] == 0
    assert isinstance(baseline["erp_flat"]["drift"], int)


def test_current_equal_to_baseline_is_not_a_regression() -> None:
    """기준선과 같은 값은 통과 — 이게 래칫의 핵심이다(절대 0건이 아니다)."""
    baseline = load_baseline()
    comparison = compare_to_baseline(_report(0, baseline["erp_flat"]["drift"]), baseline)
    assert comparison["regressed"] is False


def test_drift_below_baseline_passes() -> None:
    """줄어든 값도 통과(음성 대조군 — 줄어드는 게 목표 방향이다)."""
    baseline = load_baseline()
    comparison = compare_to_baseline(_report(0, baseline["erp_flat"]["drift"] - 100), baseline)
    assert comparison["regressed"] is False
    row = next(r for r in comparison["rows"] if r["key"] == "erp_flat")
    assert row["delta"] == -100


def test_one_more_than_baseline_is_a_regression() -> None:
    """기준선보다 1건이라도 늘면 실패한다."""
    baseline = load_baseline()
    comparison = compare_to_baseline(_report(0, baseline["erp_flat"]["drift"] + 1), baseline)
    assert comparison["regressed"] is True
    row = next(r for r in comparison["rows"] if r["key"] == "erp_flat")
    assert row["regressed"] is True and row["delta"] == 1


def test_as_axis_must_stay_zero_even_though_flat_has_a_budget() -> None:
    """AS 축은 기준선이 0이라 1건도 허용하지 않는다(축마다 규칙이 다르다)."""
    baseline = load_baseline()
    comparison = compare_to_baseline(_report(1, baseline["erp_flat"]["drift"]), baseline)
    assert comparison["regressed"] is True
    row = next(r for r in comparison["rows"] if r["key"] == "as_axis")
    assert row["regressed"] is True


def test_missing_baseline_raises_instead_of_passing_silently(tmp_path: Path) -> None:
    """기준선이 없으면 **예외**다 — 조용히 통과하면 게이트가 죽은 것을 아무도 모른다."""
    with pytest.raises(RuntimeError):
        load_baseline(tmp_path / "does-not-exist.json")


def test_wrong_schema_raises(tmp_path: Path) -> None:
    """스키마가 바뀌면 예외 — 모양이 달라진 파일을 옛 규칙으로 읽지 않는다."""
    bad = tmp_path / "drift_baseline.json"
    bad.write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_baseline(bad)


def test_summary_shows_baseline_and_delta() -> None:
    """리포트가 절대값과 기준선·증감을 함께 보여준다(절대값을 숨기지 않는다)."""
    baseline = load_baseline()
    current = baseline["erp_flat"]["drift"]
    report = _report(0, current)
    summary = render_summary(report, compare_to_baseline(report, baseline))
    assert "기준선" in summary
    assert str(current) in summary
    assert "순증 없음" in summary


def test_baseline_path_points_next_to_the_tool() -> None:
    """기준선 경로가 도구 옆이라 워크플로가 requests 만 설치하고도 읽는다."""
    assert BASELINE_PATH.name == "drift_baseline.json"
    assert BASELINE_PATH.parent.name == "ops"
    assert BASELINE_PATH.is_file()
