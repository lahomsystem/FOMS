"""운영 실사용 HTTP 로그로 성능 수정 전후를 비교한다 (읽기 전용).

Railway ``httpLogs`` 에서 분할 시각 전 N일과 후 M시간의 요청을 모아, 경로별 서버 처리
시간(``upstreamRqDuration``, ms)의 요청 수·p50·p95·p99·최대와 변화율을 낸다.

요일·시간대 효과를 상쇄하려고 비교 기준을 셋 둔다.
- 전 N일 전체.
- 같은 시간대: 전 N일 각 날에서 "후" 구간과 같은 시각대(24시간 단위로 민 창)만.
- 같은 요일·시간대: 정확히 7일 전의 같은 창만.

사실(2026-10-01 실측):
- ``totalDuration``·``upstreamRqDuration`` 은 싱가포르 엣지→오리진 구간이다(한국↔싱가포르
  네트워크 미포함). 판정은 ``upstreamRqDuration`` 기준.
- ``path`` 에 쿼리스트링이 없다. 숫자 id 는 ``<id>``, UUID 는 ``<uuid>`` 로 정규화한다.
- 옛 배포에서 ``beforeLimit`` 로 뒤로 넘기면 일부만 온다. 배포 ``createdAt``(또는 수집 시작)
  을 anchor 로 ``afterLimit`` 앞으로 넘겨야 전부 온다.
- User-Agent 가 없으면 같은 토큰도 403 이다.

읽기 전용: GraphQL query 만 보낸다(mutation 은 보내기 전에 거부). 토큰은 실행 시점에
``~/.railway/config.json`` 의 ``user.token`` 을 읽고 출력·저장하지 않는다. ``railway link``
를 쓰지 않는다(id 를 명시해 조회).

사용(Git Bash 는 ``/erp/...`` 인자를 ``C:/Program Files/Git/erp/...`` 로 바꾸므로
``MSYS_NO_PATHCONV=1`` 을 앞에 붙인다. 바뀐 채로 들어오면 도구가 멈추고 알려 준다):
    MSYS_NO_PATHCONV=1 python tools/perf/prod_route_latency_compare.py --split 2026-10-01T07:25:00Z \\
        --paths /erp/measurement,/erp/as --before-days 7 --after-hours 24 [--env staging] [--json]

종료 코드: 0=정상 · 2=판정 불가(토큰·API·인자 문제).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
USER_AGENT = "railwayapp/4.0.0"  # 없으면 403
PAGE_LIMIT = 5000
MIN_N_DEFAULT = 30
CHANGE_THRESHOLD_PCT = 10.0  # p50·p95 가 이만큼 움직여야 개선·악화로 본다
EXCLUDED_STATUS = frozenset({0, 429})  # 0 = WebSocket, 429 = 속도 제한(앱 처리 아님)
NEVER_SERVED = frozenset({"FAILED", "SKIPPED"})
LOG_FIELDS = "timestamp requestId httpStatus path totalDuration upstreamRqDuration"
UTC = timezone.utc
KST = timezone(timedelta(hours=9))
DAY = timedelta(days=1)
WEEK = timedelta(days=7)

ENVS: dict[str, dict[str, str]] = {
    "production": {
        "project": "cbe0af66-875b-460c-88f6-780dd705f45c",
        "environment": "57587e48-dc52-42f7-9991-e70895a0ee50",
        "service": "web",
    },
    "staging": {
        "project": "65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a",
        "environment": "d7156ab5-8d7d-4a55-99ed-1054d0a02f7d",
        "service": "FOMS",
    },
}

BUCKETS = ("before", "after", "same_hours", "same_weekday")
BUCKET_LABEL = {
    "before": "전 {days}일",
    "after": "후 {hours:.1f}시간",
    "same_hours": "같은 시간대(전 {days}일)",
    "same_weekday": "같은 요일·시간대(7일 전)",
}

_UUID = re.compile(r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)")
_NUM = re.compile(r"/\d+(?=/|$)")
_FRACTION = re.compile(r"\.(\d+)")
_WIN_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_MUTATION = re.compile(r"\bmutation\b", re.IGNORECASE)


class Undetermined(RuntimeError):
    """판정 불가 — 토큰·API·인자 문제."""


# ---------------------------------------------------------------- 순수 계산


def parse_utc(text: str) -> datetime:
    """ISO 시각(``Z``·나노초 허용)을 UTC aware datetime 으로 바꾼다."""
    s = text.strip().replace("Z", "+00:00")
    s = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), s, count=1)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def normalize_path(path: str) -> str:
    """쿼리 제거, UUID→``<uuid>``, 숫자 조각→``<id>``, 끝 슬래시 제거."""
    p = (path or "").split("?", 1)[0].strip() or "/"
    if not p.startswith("/"):
        p = "/" + p
    p = _UUID.sub("/<uuid>", p)
    p = _NUM.sub("/<id>", p)
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/") or "/"
    return p


def parse_paths(text: str) -> list[str]:
    """``--paths`` 쉼표 목록을 정규화한다. Git Bash 가 윈도 경로로 바꾼 항목은 거부한다."""
    items = [t.strip() for t in (text or "").split(",") if t.strip()]
    mangled = [t for t in items if _WIN_DRIVE.match(t)]
    if mangled:
        raise Undetermined(
            f"경로가 윈도 경로로 바뀌어 들어왔다: {mangled[0]!r} — Git Bash 의 자동 변환이다."
            " 명령 앞에 MSYS_NO_PATHCONV=1 을 붙여라"
        )
    paths = list(dict.fromkeys(normalize_path(t) for t in items))
    if not paths:
        raise Undetermined("--paths 가 비었다")
    return paths


def percentile(sorted_values: list[float], q: float) -> float | None:
    """nearest-rank 백분위(125만 건 분석과 같은 식): ``L[min(n-1, int(q*n))]``."""
    if not sorted_values:
        return None
    n = len(sorted_values)
    return sorted_values[min(n - 1, int(q * n))]


def summarize(values: Iterable[float]) -> dict[str, Any]:
    vals = sorted(values)
    return {
        "n": len(vals),
        "p50": percentile(vals, 0.50),
        "p95": percentile(vals, 0.95),
        "p99": percentile(vals, 0.99),
        "max": vals[-1] if vals else None,
    }


def change_pct(before: float | None, after: float | None) -> float | None:
    """(후-전)/전 ×100, 소수 1자리. 전이 0 이거나 값이 없으면 None(0→0 은 0.0)."""
    if before is None or after is None:
        return None
    if before == 0:
        return 0.0 if after == 0 else None
    return round((after - before) / before * 100.0, 1)


def verdict(base: dict[str, Any], after: dict[str, Any], min_n: int = MIN_N_DEFAULT) -> str:
    """표본이 적으면 보류, 아니면 p50·p95 변화율로 개선·악화·혼재·변화 작음."""
    if base["n"] < min_n or after["n"] < min_n:
        return f"판정 보류(n<{min_n})"
    moves = [change_pct(base[k], after[k]) for k in ("p50", "p95")]
    better = any(m is not None and m <= -CHANGE_THRESHOLD_PCT for m in moves)
    worse = any(m is not None and m >= CHANGE_THRESHOLD_PCT for m in moves)
    return {(True, True): "혼재", (True, False): "개선", (False, True): "악화"}.get((better, worse), "변화 작음")


@dataclass(frozen=True)
class Windows:
    """비교 창. 모두 UTC. 전=[before_start, split), 후=[split, after_end)."""

    split: datetime
    before_start: datetime
    after_end: datetime

    @property
    def after_hours(self) -> float:
        return (self.after_end - self.split).total_seconds() / 3600.0

    @property
    def before_days(self) -> float:
        return (self.split - self.before_start).total_seconds() / 86400.0


def make_windows(split: datetime, before_days: float, after_hours: float, now: datetime) -> Windows:
    end = min(split + timedelta(hours=after_hours), now)
    if end <= split:
        raise Undetermined(f"후 구간이 비어 있다 — 분할 {iso_z(split)} 이 지금({iso_z(now)})보다 뒤다")
    return Windows(split=split, before_start=split - timedelta(days=before_days), after_end=end)


def in_same_hours(ts: datetime, w: Windows) -> bool:
    """전 구간 시각 ts 를 하루 단위로 앞으로 밀었을 때 "후" 창에 들어가는가."""
    if not (w.before_start <= ts < w.split):
        return False
    gap = w.split - ts  # > 0
    k = math.ceil(gap / DAY)
    return k * DAY < gap + (w.after_end - w.split)


def in_same_weekday(ts: datetime, w: Windows) -> bool:
    """정확히 7일 전의 같은 창(요일·시각 같음)에 들어가는가."""
    return max(w.before_start, w.split - WEEK) <= ts < min(w.split, w.after_end - WEEK)


def empty_buckets(paths: Iterable[str]) -> dict[str, dict[str, dict[str, Any]]]:
    return {p: {b: {"values": [], "n5xx": 0} for b in BUCKETS} for p in paths}


def add_row(buckets: dict[str, dict[str, dict[str, Any]]], row: dict[str, Any], w: Windows) -> str:
    """로그 1건을 버킷에 넣는다. 돌려주는 값: 'kept'·'status'(0·429)·'path'·'range'."""
    status = row.get("httpStatus")
    if status in EXCLUDED_STATUS:
        return "status"
    path = normalize_path(row.get("path") or "")
    if path not in buckets:
        return "path"
    ts = parse_utc(row["timestamp"])
    if not (w.before_start <= ts < w.after_end):
        return "range"
    dur = row.get("upstreamRqDuration")
    if dur is None:
        dur = row.get("totalDuration")
    if dur is None:
        return "range"
    names = ["after"] if ts >= w.split else ["before"]
    if ts < w.split:
        if in_same_hours(ts, w):
            names.append("same_hours")
        if in_same_weekday(ts, w):
            names.append("same_weekday")
    for name in names:
        slot = buckets[path][name]
        slot["values"].append(dur)
        if isinstance(status, int) and 500 <= status < 600:
            slot["n5xx"] += 1
    return "kept"


def build_report(buckets: dict[str, dict[str, dict[str, Any]]], min_n: int) -> list[dict[str, Any]]:
    out = []
    for path, slots in buckets.items():
        stats = {b: {**summarize(slots[b]["values"]), "n5xx": slots[b]["n5xx"]} for b in BUCKETS}
        comps = [
            {"base": base, "verdict": verdict(stats[base], stats["after"], min_n),
             **{f"{k}_pct": change_pct(stats[base][k], stats["after"][k]) for k in ("p50", "p95", "p99")}}
            for base in ("before", "same_hours", "same_weekday")
        ]
        out.append({"path": path, "stats": stats, "comparisons": comps})
    return out


def select_deployments(deps: list[dict[str, Any]], w: Windows) -> list[dict[str, Any]]:
    """수집 창과 겹치는 배포만: 창 안에서 만든 것 + 창 시작 때 돌던 직전 1개. 실패·건너뜀 제외."""
    live = sorted((d for d in deps if d.get("status") not in NEVER_SERVED), key=lambda d: parse_utc(d["createdAt"]))
    inside = [d for d in live if w.before_start <= parse_utc(d["createdAt"]) < w.after_end]
    earlier = [d for d in live if parse_utc(d["createdAt"]) < w.before_start]
    return ([earlier[-1]] if earlier else []) + inside


def collect_logs(
    fetch: Callable[[str, str], list[dict[str, Any]]],
    dep: dict[str, Any],
    w: Windows,
    on_row: Callable[[dict[str, Any]], None],
    page_limit: int = PAGE_LIMIT,
) -> tuple[int, int]:
    """한 배포의 로그를 anchor 앞으로 넘기며 모은다. (고유 건수, 호출 수)."""
    anchor_dt = max(parse_utc(dep["createdAt"]), w.before_start)
    anchor = iso_z(anchor_dt)
    seen: set[str] = set()
    calls = 0
    while True:
        batch = fetch(dep["id"], anchor)
        calls += 1
        new = 0
        latest_dt, latest = None, None
        for r in batch:
            ts = parse_utc(r["timestamp"])
            if latest_dt is None or ts > latest_dt:
                latest_dt, latest = ts, r["timestamp"]
            rid = r.get("requestId") or f"{r['timestamp']}|{r.get('path')}"
            if rid in seen:
                continue
            seen.add(rid)
            new += 1
            on_row(r)
        if len(batch) < page_limit or new == 0 or latest_dt is None or latest_dt >= w.after_end:
            return len(seen), calls
        anchor = latest


# ---------------------------------------------------------------- 출력


def _fmt_ms(v: float | None) -> str:
    return "-" if v is None else f"{v:.0f}"


def _fmt_pct(v: float | None) -> str:
    return "  -   " if v is None else f"{v:+.1f}%"


def _kst(dt: datetime, fmt: str = "%m-%d %H:%M") -> str:
    return dt.astimezone(KST).strftime(fmt)


def render_text(meta: dict[str, Any], report: list[dict[str, Any]], w: Windows) -> str:
    days, hours = round(w.before_days, 2), w.after_hours
    label = {b: BUCKET_LABEL[b].format(days=f"{days:g}", hours=hours) for b in BUCKETS}
    week_ago = (w.split - WEEK, w.after_end - WEEK)
    lines = [
        f"FOMS {meta['env']} {meta['service']} — 경로별 서버 처리 시간(upstreamRqDuration, ms) 전후 비교",
        f"분할 {_kst(w.split, '%Y-%m-%d %H:%M')} KST ({iso_z(w.split)})",
        f"전: {_kst(w.before_start)} ~ {_kst(w.split)} KST ({days:g}일)",
        f"후: {_kst(w.split)} ~ {_kst(w.after_end)} KST ({hours:.1f}시간, 요청 {meta['after_hours_requested']:g}시간)",
        f"같은 시간대: 전 {days:g}일 각 날의 {_kst(w.split, '%H:%M')}~{_kst(w.after_end, '%H:%M')} KST"
        f" / 같은 요일·시간대: {_kst(week_ago[0])} ~ {_kst(week_ago[1])} KST",
        f"배포 {meta['deployments']}개, 로그 {meta['rows']:,}건(호출 {meta['calls']}회), "
        f"상태 0·429 제외 {meta['excluded_status']:,}건, nearest-rank 백분위, 표본 n<{meta['min_n']} 은 판정 보류",
    ]
    for item in report:
        lines += ["", f"■ {item['path']}", f"{'n':>8} {'p50':>6} {'p95':>6} {'p99':>6} {'max':>7} {'5xx':>4}  구간"]
        if not any(item["stats"][b]["n"] for b in ("before", "after")):
            lines.append("  ※ 전·후 모두 0건 — 경로 철자나 정규화(숫자 → <id>)를 확인하라")
        for b in BUCKETS:
            s = item["stats"][b]
            lines.append(
                f"{s['n']:>8,} {_fmt_ms(s['p50']):>6} {_fmt_ms(s['p95']):>6} {_fmt_ms(s['p99']):>6}"
                f" {_fmt_ms(s['max']):>7} {s['n5xx']:>4}  {label[b]}"
            )
        for c in item["comparisons"]:
            lines.append(
                f"  p50 {_fmt_pct(c['p50_pct']):>7}  p95 {_fmt_pct(c['p95_pct']):>7}"
                f"  p99 {_fmt_pct(c['p99_pct']):>7}  {c['verdict']}  ← 후 vs {label[c['base']]}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------- 네트워크 (읽기 전용)


def assert_read_only(query: str) -> None:
    """``mutation`` 이라는 단어가 어디든 있으면 보내기 전에 거부한다."""
    if _MUTATION.search(query):
        raise Undetermined("mutation 은 보내지 않는다 (읽기 전용 도구)")


def read_token(config: Path | None = None) -> str:
    path = config or Path.home() / ".railway" / "config.json"
    try:
        obj, _ = json.JSONDecoder().raw_decode(path.read_text(encoding="utf-8").lstrip())
        return obj["user"]["token"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Undetermined(f"railway 토큰을 읽지 못했다({type(exc).__name__}) — `railway login` 필요") from None


def graphql(token: str, query: str, variables: dict[str, Any] | None = None, retries: int = 4) -> dict[str, Any]:
    assert_read_only(query)
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"}
    last = "재시도 소진"
    for attempt in range(retries):
        if attempt:
            time.sleep(5 * attempt)  # 429·5xx·연결 실패·속도 제한 오류만 다시 시도한다
        req = urllib.request.Request(GRAPHQL_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in (429, 502, 503, 504):
                continue
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = f"연결 실패: {exc}"
            continue
        if data.get("errors") and not data.get("data"):
            last = "오류: " + json.dumps(data["errors"], ensure_ascii=False)[:300]
            if "rate" in last.lower():
                continue
            break
        return data.get("data") or {}
    raise Undetermined(f"GraphQL {last}")


def fetch_service_id(token: str, env: dict[str, str]) -> str:
    data = graphql(token, "query($p:String!){ project(id:$p){ services{ edges{ node{ id name } } } } }", {"p": env["project"]})
    services = {e["node"]["name"]: e["node"]["id"] for e in data["project"]["services"]["edges"]}
    if env["service"] not in services:
        raise Undetermined(f"서비스 '{env['service']}' 가 없다 (있는 것: {sorted(services)})")
    return services[env["service"]]


def fetch_deployments(token: str, env: dict[str, str], service_id: str, older_than: datetime) -> list[dict[str, Any]]:
    """최신부터 넘기다가 ``older_than`` 보다 오래된 배포를 2개 넘게 보면 멈춘다."""
    query = (
        "query($i:DeploymentListInput!,$a:String){ deployments(input:$i, first:50, after:$a){"
        " pageInfo{ hasNextPage endCursor } edges{ node{ id status createdAt } } } }"
    )
    inp = {"projectId": env["project"], "environmentId": env["environment"], "serviceId": service_id}
    out: list[dict[str, Any]] = []
    cursor = None
    while True:
        conn = graphql(token, query, {"i": inp, "a": cursor})["deployments"]
        out += [e["node"] for e in conn["edges"]]
        old = sum(1 for d in out if parse_utc(d["createdAt"]) < older_than and d.get("status") not in NEVER_SERVED)
        if old >= 2 or not conn["pageInfo"]["hasNextPage"]:
            return out
        cursor = conn["pageInfo"]["endCursor"]


def _http_fetcher(token: str) -> Callable[[str, str], list[dict[str, Any]]]:
    query = (
        "query($d:String!,$a:String){ httpLogs(deploymentId:$d, anchorDate:$a, afterLimit:%d){ %s } }"
        % (PAGE_LIMIT, LOG_FIELDS)
    )

    def fetch(dep_id: str, anchor: str) -> list[dict[str, Any]]:
        return graphql(token, query, {"d": dep_id, "a": anchor}).get("httpLogs") or []

    return fetch


def run(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], Windows]:
    env = ENVS[args.env]
    paths = parse_paths(args.paths)
    w = make_windows(parse_utc(args.split), args.before_days, args.after_hours, datetime.now(UTC))
    token = read_token()
    service_id = fetch_service_id(token, env)
    deps = select_deployments(fetch_deployments(token, env, service_id, w.before_start), w)
    if not deps:
        raise Undetermined("수집 창과 겹치는 배포가 없다")
    buckets = empty_buckets(paths)
    counts = {"kept": 0, "status": 0, "path": 0, "range": 0}
    fetch = _http_fetcher(token)
    rows = calls = 0

    def on_row(r: dict[str, Any]) -> None:
        counts[add_row(buckets, r, w)] += 1

    for i, dep in enumerate(deps, 1):
        n, c = collect_logs(fetch, dep, w, on_row)
        rows += n
        calls += c
        print(f"[배포 {i}/{len(deps)}] {dep['id'][:8]} {dep['createdAt'][:16]}Z {dep['status']}"
              f" — {n:,}건 (호출 {c}회, 누적 {rows:,}건)", file=sys.stderr, flush=True)
    meta = {
        "env": args.env, "service": env["service"], "deployments": len(deps), "rows": rows, "calls": calls,
        "excluded_status": counts["status"], "kept": counts["kept"], "min_n": args.min_n,
        "after_hours_requested": args.after_hours,
        "windows": {"split": iso_z(w.split), "before_start": iso_z(w.before_start), "after_end": iso_z(w.after_end)},
    }
    return meta, build_report(buckets, args.min_n), w


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # cp949 콘솔에서도 한글·대시가 죽지 않게
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="운영 HTTP 로그로 경로별 서버 처리 시간 전후 비교 (읽기 전용)")
    ap.add_argument("--split", required=True, help="분할 시각 ISO (예 2026-10-01T07:25:00Z)")
    ap.add_argument("--paths", required=True, help="쉼표로 구분한 경로 (숫자 id 는 <id> 로 정규화)")
    ap.add_argument("--before-days", type=float, default=7.0)
    ap.add_argument("--after-hours", type=float, default=24.0)
    ap.add_argument("--env", choices=sorted(ENVS), default="production")
    ap.add_argument("--min-n", type=int, default=MIN_N_DEFAULT, help="이보다 적은 표본은 판정 보류")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    args = ap.parse_args(argv)
    try:
        meta, report, w = run(args)
    except (Undetermined, ValueError) as exc:
        print(f"판정 불가: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"meta": meta, "paths": report}, ensure_ascii=False, indent=1))
    else:
        print(render_text(meta, report, w))
    return 0


if __name__ == "__main__":
    sys.exit(main())
