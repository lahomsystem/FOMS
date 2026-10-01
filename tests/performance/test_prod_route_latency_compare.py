"""운영 경로 지연 전후 비교기(tools/perf/prod_route_latency_compare.py)의 순수 계산 계약.

성능 수정 효과를 운영 실사용 기록으로 판정하는 도구라, 정규화·백분위·창 나누기·배포 고르기·
페이지 넘김이 조용히 틀리면 "개선됐다"는 근거가 거짓이 된다. 네트워크 없이 지킨다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tools.perf.prod_route_latency_compare import (
    Undetermined,
    add_row,
    assert_read_only,
    build_report,
    change_pct,
    collect_logs,
    empty_buckets,
    in_same_hours,
    in_same_weekday,
    iso_z,
    make_windows,
    normalize_path,
    parse_paths,
    parse_utc,
    percentile,
    render_text,
    select_deployments,
    summarize,
    verdict,
)

UTC = timezone.utc
SPLIT = datetime(2026, 10, 1, 7, 25, tzinfo=UTC)


def _w(after_hours: float = 4.0, before_days: float = 7.0):
    return make_windows(SPLIT, before_days, after_hours, now=SPLIT + timedelta(days=30))


def _row(ts: datetime, path: str = "/erp/as", status: int = 200, up: int | None = 100, rid: str | None = None):
    return {"timestamp": iso_z(ts), "requestId": rid or iso_z(ts) + path, "httpStatus": status,
            "path": path, "upstreamRqDuration": up, "totalDuration": 999}


def test_parse_utc_accepts_nanoseconds_and_z():
    assert parse_utc("2026-09-01T00:00:00.108045824Z") == datetime(2026, 9, 1, 0, 0, 0, 108045, tzinfo=UTC)
    assert parse_utc("2026-10-01T16:25:00+09:00") == SPLIT
    assert parse_utc("2026-10-01T07:25:00Z") == SPLIT


@pytest.mark.parametrize(("raw", "want"), [
    ("/erp/as/123", "/erp/as/<id>"),
    ("/erp/as/", "/erp/as"),
    ("/erp/measurement?x=1", "/erp/measurement"),
    ("/api/orders/5/items/77", "/api/orders/<id>/items/<id>"),
    ("/x/0b8f6a3e-1c2d-4e5f-8a9b-0c1d2e3f4a5b/y", "/x/<uuid>/y"),
    ("/", "/"),
    ("/erp/v2abc", "/erp/v2abc"),  # 숫자로만 된 조각만 id 다
])
def test_normalize_path(raw, want):
    assert normalize_path(raw) == want


def test_parse_paths_normalizes_and_rejects_git_bash_mangled_paths():
    """2026-10-01 실측: Git Bash 가 첫 경로를 'C:/Program Files/Git/erp/measurement' 로 바꿔 0건이 나왔다."""
    assert parse_paths(" /erp/as/ , erp/history,/erp/as") == ["/erp/as", "/erp/history"]
    with pytest.raises(Undetermined, match="MSYS_NO_PATHCONV"):
        parse_paths("C:/Program Files/Git/erp/measurement,/erp/as")
    with pytest.raises(Undetermined):
        parse_paths(" , ")


def test_percentile_nearest_rank_and_summary():
    vals = list(range(1, 101))
    s = summarize(reversed(vals))  # 정렬은 summarize 가 한다
    assert (s["n"], s["p50"], s["p95"], s["p99"], s["max"]) == (100, 51, 96, 100, 100)
    assert percentile([], 0.5) is None
    assert summarize([]) == {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}


def test_change_pct():
    assert change_pct(200, 100) == -50.0
    assert change_pct(100, 133) == 33.0
    assert change_pct(0, 0) == 0.0
    assert change_pct(0, 5) is None
    assert change_pct(None, 5) is None


def _stat(n, p50, p95):
    return {"n": n, "p50": p50, "p95": p95}


def test_verdict_holds_small_samples_and_classifies():
    assert verdict(_stat(29, 100, 200), _stat(500, 10, 20)).startswith("판정 보류")
    assert verdict(_stat(500, 100, 200), _stat(29, 10, 20)).startswith("판정 보류")
    assert verdict(_stat(30, 100, 200), _stat(30, 50, 190)) == "개선"
    assert verdict(_stat(30, 100, 200), _stat(30, 100, 260)) == "악화"
    assert verdict(_stat(30, 100, 200), _stat(30, 50, 260)) == "혼재"
    assert verdict(_stat(30, 100, 200), _stat(30, 105, 195)) == "변화 작음"


def test_make_windows_clips_after_to_now_and_rejects_future_split():
    w = make_windows(SPLIT, 7, 24, now=SPLIT + timedelta(hours=5))
    assert w.after_end == SPLIT + timedelta(hours=5)
    assert w.before_start == SPLIT - timedelta(days=7)
    with pytest.raises(Undetermined):
        make_windows(SPLIT, 7, 24, now=SPLIT - timedelta(minutes=1))


def test_same_hours_picks_the_after_clock_window_on_each_earlier_day():
    w = _w(after_hours=4)
    assert in_same_hours(SPLIT - timedelta(days=1) + timedelta(hours=1), w)
    assert in_same_hours(SPLIT - timedelta(days=3) + timedelta(hours=3, minutes=59), w)
    assert in_same_hours(SPLIT - timedelta(days=1), w)  # 창 시작 경계 포함
    assert not in_same_hours(SPLIT - timedelta(days=1) + timedelta(hours=4), w)  # 끝 경계 제외
    assert not in_same_hours(SPLIT - timedelta(hours=1), w)  # 분할 직전 = 다른 시간대
    assert not in_same_hours(SPLIT + timedelta(hours=1), w)  # 후 구간은 대상 아님
    w24 = _w(after_hours=24)
    assert in_same_hours(SPLIT - timedelta(hours=1), w24)  # 24시간 창은 모든 시각을 덮는다


def test_same_weekday_is_exactly_one_week_earlier():
    w = _w(after_hours=4)
    assert in_same_weekday(SPLIT - timedelta(days=7) + timedelta(hours=1), w)
    assert not in_same_weekday(SPLIT - timedelta(days=6) + timedelta(hours=1), w)
    assert not in_same_weekday(SPLIT - timedelta(days=7) + timedelta(hours=5), w)
    short = _w(after_hours=4, before_days=3)
    assert not in_same_weekday(SPLIT - timedelta(days=7) + timedelta(hours=1), short)  # 수집 범위 밖


def test_add_row_buckets_and_exclusions():
    w = _w(after_hours=4)
    b = empty_buckets(["/erp/as/<id>", "/erp/measurement"])
    rows = [
        _row(SPLIT + timedelta(hours=1), "/erp/as/7", up=40),  # 후
        _row(SPLIT + timedelta(hours=2), "/erp/as/8", status=503, up=900),  # 후, 5xx
        _row(SPLIT - timedelta(days=7) + timedelta(hours=1), "/erp/as/9", up=200),  # 전+같은 시간대+같은 요일
        _row(SPLIT - timedelta(days=2) - timedelta(hours=1), "/erp/as/9", up=300),  # 전만
        _row(SPLIT + timedelta(hours=1), "/erp/as/1", status=0),  # WebSocket
        _row(SPLIT + timedelta(hours=1), "/erp/as/1", status=429),  # 속도 제한
        _row(SPLIT + timedelta(hours=1), "/erp/history"),  # 대상 아님
        _row(SPLIT + timedelta(hours=5), "/erp/as/1"),  # 후 창 밖
        _row(SPLIT - timedelta(days=8), "/erp/as/1"),  # 전 창 밖
        _row(SPLIT + timedelta(hours=1), "/erp/measurement", up=None),  # upstream 없음 → total
    ]
    results = [add_row(b, r, w) for r in rows]
    assert results == ["kept", "kept", "kept", "kept", "status", "status", "path", "range", "range", "kept"]
    a = b["/erp/as/<id>"]
    assert sorted(a["after"]["values"]) == [40, 900] and a["after"]["n5xx"] == 1
    assert sorted(a["before"]["values"]) == [200, 300]
    assert a["same_hours"]["values"] == [200]
    assert a["same_weekday"]["values"] == [200]
    assert b["/erp/measurement"]["after"]["values"] == [999]


def test_build_report_and_render_text_show_hold_for_small_samples():
    w = _w(after_hours=4)
    b = empty_buckets(["/erp/as"])
    for i in range(40):
        add_row(b, _row(SPLIT - timedelta(days=1) + timedelta(minutes=i), up=200 + i), w)
    for i in range(5):
        add_row(b, _row(SPLIT + timedelta(minutes=i), up=50), w)
    report = build_report(b, min_n=30)
    comp = {c["base"]: c for c in report[0]["comparisons"]}
    assert comp["before"]["p50_pct"] == change_pct(220, 50)
    assert comp["before"]["verdict"] == "판정 보류(n<30)"
    meta = {"env": "production", "service": "web", "deployments": 1, "rows": 45, "calls": 1,
            "excluded_status": 0, "min_n": 30, "after_hours_requested": 24}
    text = render_text(meta, report, w)
    assert "■ /erp/as" in text and "판정 보류(n<30)" in text and "16:25" in text  # KST 표기
    assert "전·후 모두 0건" not in text
    empty = build_report(empty_buckets(["/erp/typo"]), min_n=30)
    assert "전·후 모두 0건" in render_text(meta, empty, w)  # 철자 틀린 경로는 조용히 0 으로 넘기지 않는다


def _dep(i, created, status="REMOVED"):
    return {"id": f"dep{i}", "status": status, "createdAt": iso_z(created)}


def test_select_deployments_keeps_serving_one_before_window_and_drops_failed_and_future():
    w = _w(after_hours=4)
    deps = [
        _dep(1, SPLIT - timedelta(days=9)),
        _dep(2, SPLIT - timedelta(days=8)),  # 창 시작 때 돌던 배포
        _dep(3, SPLIT - timedelta(days=7, hours=-1), "FAILED"),
        _dep(4, SPLIT - timedelta(days=3)),
        _dep(5, SPLIT + timedelta(seconds=1)),
        _dep(6, SPLIT + timedelta(hours=5), "SUCCESS"),  # 후 창 끝 뒤
    ]
    assert [d["id"] for d in select_deployments(list(reversed(deps)), w)] == ["dep2", "dep4", "dep5"]


def test_collect_logs_pages_forward_from_window_start_and_dedupes():
    w = _w(after_hours=4)
    base = SPLIT - timedelta(days=7)
    page1 = [_row(base + timedelta(minutes=i), rid=f"r{i}") for i in range(3)]
    page2 = [page1[-1]] + [_row(base + timedelta(minutes=10 + i), rid=f"s{i}") for i in range(2)]
    calls = []

    def fetch(dep_id, anchor):
        calls.append(anchor)
        return {0: page1, 1: page2}.get(len(calls) - 1, [])

    seen = []
    n, c = collect_logs(fetch, _dep(1, SPLIT - timedelta(days=30)), w, seen.append, page_limit=3)
    assert (n, c) == (5, 3)  # 2쪽도 꽉 찼으니 3번째 빈 쪽을 받고 멈춘다
    assert [r["requestId"] for r in seen] == ["r0", "r1", "r2", "s0", "s1"]  # 겹친 r2 는 한 번만
    assert parse_utc(calls[0]) == w.before_start  # 옛 배포는 창 시작을 anchor 로
    assert calls[1] == page1[-1]["timestamp"]  # 다음 anchor 는 받은 것 중 가장 늦은 시각
    assert calls[2] == page2[-1]["timestamp"]


def test_collect_logs_stops_after_window_end():
    w = _w(after_hours=4)
    late = [_row(SPLIT + timedelta(hours=5), rid=f"x{i}") for i in range(3)]
    calls = []

    def fetch(dep_id, anchor):
        calls.append(anchor)
        return late

    n, c = collect_logs(fetch, _dep(9, SPLIT + timedelta(minutes=1)), w, lambda r: None, page_limit=3)
    assert (n, c) == (3, 1)
    assert parse_utc(calls[0]) == SPLIT + timedelta(minutes=1)  # 창 안 배포는 createdAt 이 anchor


def test_read_only_guard_refuses_mutations():
    assert_read_only("query($d:String!){ httpLogs(deploymentId:$d){ path } }")
    for bad in ("mutation { serviceInstanceRedeploy(serviceId:\"x\") }", "query{a} MUTATION{b}"):
        with pytest.raises(Undetermined):
            assert_read_only(bad)
