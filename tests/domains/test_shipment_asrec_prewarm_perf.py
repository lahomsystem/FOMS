"""출고 AS 추천 예열(prewarm) 성능 계약 — 2026-10-01 성능 검사 P1-4.

운영 30일 예열 835건, p50 7.9초. 고친 원인마다 계약 하나씩:

* 연결 목록 작업자 이름 N+1 → 배치 1회(쿼리 수가 연결 건수에 비례하지 않음).
* 예열은 결과를 버리므로 연결 목록(DB 재조회)을 만들지 않는다.
* 카카오(지오코딩·길찾기) 부르기 전에 DB 트랜잭션을 끝내 연결을 돌려준다.
* 길찾기 캐시는 AS 수정 무효화로 지워지지 않는다(좌표 쌍만으로 정해지는 값).
* 후보 풀은 카카오를 부르지 않고, 지오코딩은 DB 좌표가 없는 대상만 한다(결과 좌표는 같다).
* 같은 타깃을 다른 요청이 계산 중이면 예열은 건너뛴다(single-flight).
* 화면 쪽 예열은 진행 중 표식으로 같은 예열을 나란히 두 번 보내지 않는다.
* 자동 예열은 광폭 마우스 PC 에서만 돈다(2026-10-01 사용자 결정 — 30일 추천 창 열기·적용 0건,
  예열 835건 중 61% 휴대폰). 판정은 서버 wants_mobile_width_surfaces 와 같은 뜻, 추천 창 경로는 판정 없음.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from sqlalchemy import event
from werkzeug.security import generate_password_hash

import foms.api.shipment.recommendations as shipment_rec_api
import foms.services.shipment_as_recommendation_cache as asrec_cache
from db import db_session, engine
from foms.services import feature_flags
from foms.services.schedule_recommendations import recommend_nearby_schedules_for_targets
from models import InstallationWorker, Order, User

ROOT = Path(__file__).resolve().parents[2]
TODAY = date.today().strftime("%Y-%m-%d")


def _login(client, username: str) -> None:
    user = User(
        username=username, password=generate_password_hash("secret"), role="STAFF",
        team="CS", name="prewarm perf", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _ship(recs: list[dict[str, Any]] | None = None, *, coords: bool = True) -> int:
    order = Order(
        received_date=TODAY, customer_name="출고", phone="010", address="경기 화성시 출고로 1",
        product="장", status="IN_CONSTRUCTION", is_erp_order=True,
        lat=37.20 if coords else None, lng=127.07 if coords else None,
        geocode_status="success" if coords else None,
        structured_data={
            "schedule": {"construction": {"date": TODAY}},
            "shipment": {"construction_workers": ["A"], "recommendations": recs or []},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _as_order(name: str, *, coords: bool, visit: str = "") -> int:
    sd: dict[str, Any] = {"workflow": {"stage": "CS"}, "as_info": [{"id": 1, "status": "OPEN"}]}
    if visit:
        sd["schedule"] = {"as_visit": {"date": visit}}
    order = Order(
        received_date=TODAY, customer_name=name, phone="010", address=f"경기 화성시 {name}",
        product="AS", status="AS_RECEIVED", is_erp_order=True,
        lat=37.21 if coords else None, lng=127.08 if coords else None,
        geocode_status="success" if coords else None, structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _workers(n: int, tag: str = "w") -> list[int]:
    ids = []
    for i in range(n):
        w = InstallationWorker(external_worker_id=f"PW-{tag}-{i}", display_name=f"작업자{i}", is_active=True)
        db_session.add(w)
        db_session.commit()
        ids.append(w.id)
    return ids


class _CountingConverter:
    """카카오 대역. 지오코딩·길찾기 호출을 센다."""

    def __init__(self) -> None:
        self.geocoded: list[str] = []
        self.routes = 0

    def analyze_address(self, address: str):
        self.geocoded.append(address)
        return (37.30, 127.10, "ok", None)

    def calculate_route(self, slat, slng, elat, elng, timeout=None):
        self.routes += 1
        return {"status": "success", "distance_km": 3.0, "duration_min": 9, "route_coords": [[1, 2]] * 50}


def _count_sql(fn) -> tuple[Any, int]:
    seen = {"n": 0}

    def on_sql(*_a, **_k):
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", on_sql)
    try:
        out = fn()
    finally:
        event.remove(engine, "before_cursor_execute", on_sql)
    return out, seen["n"]


# --- N+1 -----------------------------------------------------------------------------------


def _linked_fixture(n_recs: int) -> tuple[list[int], list[int]]:
    wids = _workers(3, f"link{n_recs}")
    ships = []
    for i in range(n_recs):
        aid = _as_order(f"연결AS{n_recs}-{i}", coords=True)
        ships.append(_ship([{
            "as_order_id": aid, "as_cycle_id": "c1", "applied_visit_date": TODAY,
            "applied_crew_ids": [wids[i % 3], wids[(i + 1) % 3]],
        }]))
    return ships, wids


def test_linked_schedules_query_count_does_not_grow_with_links(app) -> None:
    """연결 1건이든 6건이든 쿼리 수가 같다(작업자 이름 배치 1회). 예전: 연결마다 +1."""
    ships1, _ = _linked_fixture(1)
    ships6, wids = _linked_fixture(6)

    _, q1 = _count_sql(lambda: shipment_rec_api._build_linked_schedules_for_targets(db_session, ships1, {}))
    out6, q6 = _count_sql(lambda: shipment_rec_api._build_linked_schedules_for_targets(db_session, ships6, {}))

    assert q6 == q1, (q1, q6)
    # 동작 동일: 연결마다 지정 순서대로 작업자 이름
    first = out6[ships6[0]][0]
    assert first["applied_workers"] == ["작업자0", "작업자1"]
    assert first["applied_date"] == TODAY and first["can_cancel_link"] is True
    assert [len(out6[s]) for s in ships6] == [1] * 6


# --- 예열 경로: 연결 목록 생략 · DB 연결 반납 · 구간 헤더 -------------------------------------


def _stub_pool_and_cache(monkeypatch, candidates: list[dict[str, Any]] | None = None) -> None:
    monkeypatch.setattr(
        shipment_rec_api, "get_or_compute_candidate_pool",
        lambda *a, **k: (
            {"candidates": candidates or [], "link_as_to_shipment": {}, "pool_version": "pv"},
            {"candidate_pool_hit": True, "candidate_count": len(candidates or [])},
        ),
    )
    monkeypatch.setattr(shipment_rec_api, "get_cached_target", lambda _ck: None)
    monkeypatch.setattr(shipment_rec_api, "set_cached_target", lambda _ck, _row: None)


def _spy_recommend(monkeypatch) -> list[dict[str, Any]]:
    """추천 계산(카카오를 부르는 구간) 진입 시점의 DB 트랜잭션 상태를 기록한다."""
    calls: list[dict[str, Any]] = []

    def fake(**kwargs):
        calls.append({"in_tx": db_session().in_transaction(), "n": len(kwargs.get("targets") or [])})
        return {
            "targets": [
                {"order_id": t["order_id"], "recommendations": [], "message": "", "workers": []}
                for t in kwargs.get("targets") or []
            ],
            "partial": False, "warnings": [],
        }

    monkeypatch.setattr(shipment_rec_api, "recommend_nearby_schedules_for_targets", fake)
    return calls


def test_prewarm_releases_db_before_kakao_and_skips_linked(client, monkeypatch) -> None:
    _login(client, "prewarm-release")
    _stub_pool_and_cache(monkeypatch)
    calls = _spy_recommend(monkeypatch)
    linked_calls: list[int] = []
    real_linked = shipment_rec_api._build_linked_schedules_for_targets
    monkeypatch.setattr(
        shipment_rec_api, "_build_linked_schedules_for_targets",
        lambda db, ids, lm: linked_calls.append(1) or real_linked(db, ids, lm),
    )
    sid = _ship()

    res = client.post("/api/erp/shipment/as-recommendations/prewarm", json={"order_ids": [sid]})

    assert res.status_code == 200, res.data
    body = res.get_json()
    assert body["success"] is True and body["warmed_targets"] == 1 and body["prewarmed"] is True
    assert calls == [{"in_tx": False, "n": 1}]  # 카카오 구간 진입 때 트랜잭션(연결) 없음
    assert linked_calls == []  # 예열은 연결 목록을 만들지 않는다
    assert res.headers.get("X-FOMS-EPT-B7-ROUTE") == "shipment_asrec_prewarm"
    phases = res.headers.get("X-FOMS-EPT-B7-PHASES") or ""
    assert "asrec_pool=" in phases and "asrec_targets=" in phases and "asrec_recommend=" in phases


def test_modal_post_releases_db_before_kakao_and_still_builds_linked(client, monkeypatch) -> None:
    _login(client, "asrec-post-release")
    _stub_pool_and_cache(monkeypatch)
    calls = _spy_recommend(monkeypatch)
    wid = _workers(1)[0]
    aid = _as_order("모달연결", coords=True)
    sid = _ship([{"as_order_id": aid, "as_cycle_id": "c9", "applied_visit_date": TODAY, "applied_crew_ids": [wid]}])

    res = client.post("/api/erp/shipment/as-recommendations", json={"order_ids": [sid]})

    assert res.status_code == 200, res.data
    tgt = res.get_json()["targets"][0]
    assert calls == [{"in_tx": False, "n": 1}]
    # 반납 뒤에도 DB 를 다시 써서 연결 목록을 만든다(동작 동일)
    assert tgt["linked_as_schedules"][0]["as_order_id"] == aid
    assert tgt["linked_as_schedules"][0]["applied_workers"] == ["작업자0"]
    assert res.headers.get("X-FOMS-EPT-B7-ROUTE") == "shipment_asrec_batch"


# --- 길찾기 캐시 --------------------------------------------------------------------------------


def test_route_cache_survives_as_invalidation_and_drops_coords() -> None:
    asrec_cache.reset_asrec_cache_runtime_for_tests()
    conv = _CountingConverter()
    stats: dict[str, Any] = {}
    provider = asrec_cache.make_route_provider(conv, stats)

    first = provider(37.2, 127.07, 37.21, 127.08)
    asrec_cache.invalidate_shipment_as_recommendation_cache(reason="test_as_edit")
    second = provider(37.2, 127.07, 37.21, 127.08)

    assert conv.routes == 1  # 무효화 뒤에도 카카오를 다시 부르지 않는다
    assert stats == {"route_misses": 1, "route_hits": 1}
    assert first["duration_min"] == second["duration_min"] == 9
    assert "route_coords" not in first and "route_coords" not in second
    assert not asrec_cache.ROUTE_KEY_PREFIX.startswith(asrec_cache.KEY_PREFIX + ":")
    asrec_cache.reset_asrec_cache_runtime_for_tests()


# --- 지오코딩 -----------------------------------------------------------------------------------


def test_candidate_pool_does_not_call_kakao(app) -> None:
    """후보 풀은 DB 만 읽는다 — 좌표 없는 후보도 여기서 변환하지 않는다(예전: 한 건씩 직렬)."""
    asrec_cache.reset_asrec_cache_runtime_for_tests()
    _as_order("좌표없음", coords=False)
    _as_order("좌표있음", coords=True)
    conv = _CountingConverter()

    pool, _ = asrec_cache.get_or_compute_candidate_pool(
        db_session, conv, source_value="x", as_statuses=("AS", "AS_RECEIVED"),
    )

    assert conv.geocoded == []
    by_name = {c["customer_name"]: c for c in pool["candidates"]}
    assert "cached_lat" not in by_name["좌표없음"]
    assert by_name["좌표있음"]["cached_lat"] == 37.21
    asrec_cache.reset_asrec_cache_runtime_for_tests()


def test_recommend_geocodes_only_rows_without_db_coords() -> None:
    """DB 좌표가 있는 행·방문일이 잡힌 후보는 변환하지 않는다. 좌표 없는 후보는 변환 좌표로 추천된다."""
    conv = _CountingConverter()
    out = recommend_nearby_schedules_for_targets(
        converter=conv,
        targets=[{"order_id": 1, "address": "경기 출고", "target_date": TODAY, "workers": [],
                  "cached_lat": 37.20, "cached_lng": 127.07}],
        candidates=[
            {"order_id": 10, "address": "경기 좌표있음", "current_visit_date": "", "cached_lat": 37.21, "cached_lng": 127.08},
            {"order_id": 11, "address": "경기 좌표없음", "current_visit_date": ""},
            {"order_id": 12, "address": "경기 방문일있음", "current_visit_date": TODAY},
        ],
        include_workers=True,
    )

    assert conv.geocoded == ["경기 좌표없음"]
    recs = {r["as_order_id"]: r for r in out["targets"][0]["recommendations"]}
    assert set(recs) == {10, 11}
    assert (recs[10]["lat"], recs[10]["lng"]) == (37.21, 127.08)
    assert (recs[11]["lat"], recs[11]["lng"]) == (37.30, 127.10)
    assert (out["targets"][0]["lat"], out["targets"][0]["lng"]) == (37.20, 127.07)


# --- single-flight ----------------------------------------------------------------------------


def test_prewarm_skips_target_being_computed_elsewhere(client, monkeypatch) -> None:
    _login(client, "prewarm-sf")
    _stub_pool_and_cache(monkeypatch)
    calls = _spy_recommend(monkeypatch)
    busy, free = _ship(), _ship()
    targets = shipment_rec_api._build_targets_for_order_ids(db_session, [busy])
    busy_key = asrec_cache.build_target_cache_key(targets[0], "pv", shipment_rec_api.RULE_VERSION)
    ok, token = asrec_cache.try_acquire_target_lock(busy_key)  # 다른 요청이 계산 중
    assert ok and token
    try:
        res = client.post("/api/erp/shipment/as-recommendations/prewarm", json={"order_ids": [busy, free]})
    finally:
        asrec_cache.release_target_lock(busy_key, token)

    body = res.get_json()
    assert body["target_inflight_skips"] == 1 and body["warmed_targets"] == 2
    assert calls == [{"in_tx": False, "n": 1}]  # 계산 중인 1건은 건너뛰고 나머지만
    # 예열이 잡은 락은 끝나면 풀린다
    free_t = shipment_rec_api._build_targets_for_order_ids(db_session, [free])
    free_key = asrec_cache.build_target_cache_key(free_t[0], "pv", shipment_rec_api.RULE_VERSION)
    ok2, token2 = asrec_cache.try_acquire_target_lock(free_key)
    assert ok2
    asrec_cache.release_target_lock(free_key, token2)


def test_modal_post_does_not_skip_inflight_target(client, monkeypatch) -> None:
    """모달(결과를 화면에 돌려주는 요청)은 single-flight 로 건너뛰지 않는다."""
    _login(client, "asrec-post-sf")
    _stub_pool_and_cache(monkeypatch)
    calls = _spy_recommend(monkeypatch)
    sid = _ship()
    tgt = shipment_rec_api._build_targets_for_order_ids(db_session, [sid])[0]
    key = asrec_cache.build_target_cache_key(tgt, "pv", shipment_rec_api.RULE_VERSION)
    ok, token = asrec_cache.try_acquire_target_lock(key)
    try:
        res = client.post("/api/erp/shipment/as-recommendations", json={"order_ids": [sid]})
    finally:
        asrec_cache.release_target_lock(key, token)
    assert ok and res.status_code == 200
    assert calls == [{"in_tx": False, "n": 1}]
    assert res.get_json()["cache"]["target_inflight_skips"] == 0


# --- 화면 쪽 중복 예열 --------------------------------------------------------------------------


def test_client_prewarm_has_inflight_guard_before_run() -> None:
    js = (ROOT / "static/js/shipment/shipment-dashboard.js").read_text(encoding="utf-8")
    start = js.index("function scheduleShipmentAsRecPrewarm()")
    body = js[start:js.index("scheduleShipmentAsRecPrewarm();", start)]
    guard = body.index("if (inflight[key]) return;")
    assert "window.__shipmentAsRecPrewarmInflight" in body
    assert guard < body.index("inflight[key] = true;") < body.index("function run()")
    assert "delete inflight[key];" in body  # 끝나면 표식을 지운다(완료 표식은 sessionStorage)
    tpl = (ROOT / "templates/shipment/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert "js/shipment/shipment-dashboard.js') }}?v=20261001b" in tpl


# --- 자동 예열은 광폭 마우스 PC 에서만 ------------------------------------------------------------

_SHIP_JS = ROOT / "static/js/shipment/shipment-dashboard.js"
_PTR_BOOT = ROOT / "static/js/runtime/foms-pointer-hint-boot.js"
_VW_BOOT = ROOT / "static/js/runtime/foms-viewport-hint-boot.js"
_PC_GUARD = "if (!isWideMousePc()) return;"


def _js_function(js: str, name: str) -> str:
    """IIFE 안(6칸 들여쓰기) 함수 하나의 원문 — 선언부터 같은 들여쓰기의 닫는 괄호까지."""
    start = js.index(f"      function {name}(")
    closing = "\n      }\n"
    end = js.index(closing, start) + len(closing) - 1
    return js[start:end]


def test_client_prewarm_checks_wide_mouse_pc_before_anything() -> None:
    """예열 함수의 첫 문장이 PC 판정이다 — 대상 수집·sessionStorage·진행 중 표식·fetch 보다 먼저."""
    js = _SHIP_JS.read_text(encoding="utf-8")
    start = js.index("function scheduleShipmentAsRecPrewarm() {")
    body = js[start:js.index("scheduleShipmentAsRecPrewarm();", start)]
    first_stmt = body.split("{", 1)[1].strip().splitlines()[0].strip()
    assert first_stmt == _PC_GUARD, first_stmt
    guard = body.index(_PC_GUARD)
    for later in ("collectTargetOrderIds()", "sessionStorage.getItem(key)", "inflight[key] = true;",
                  "/api/erp/shipment/as-recommendations/prewarm"):
        assert guard < body.index(later), later


def test_modal_path_does_not_go_through_pc_check() -> None:
    """추천 창을 직접 여는 경로(버튼 클릭 → loadRecommendations)는 판정 없이 그때 계산한다.

    판정 함수는 정의 1곳 + 예열 1곳에서만 쓰인다.
    """
    js = _SHIP_JS.read_text(encoding="utf-8")
    assert js.count("isWideMousePc(") == 2
    assert js.count(_PC_GUARD) == 1
    load = js[js.index("function loadRecommendations()"):js.index("function parseJsonResponse(")]
    assert "isWideMousePc" not in load
    assert "fetch('/api/erp/shipment/as-recommendations'" in load
    click = js[js.index("var openBtn = ev.target.closest"):]
    click = click[:click.index("return;")]
    assert "loadRecommendations();" in click
    assert "isWideMousePc" not in click


_PC_HARNESS = r"""
var window = {};
var cases = __CASES__;
__FUNC__
var out = cases.map(function (c) {
  if (c.no_mm) {
    delete window.matchMedia;
  } else {
    window.matchMedia = function (q) {
      if (q === '(pointer: coarse)') return { matches: c.coarse };
      if (q === '(min-width: 992px)') return { matches: c.wide };
      throw new Error('부트와 다른 미디어 쿼리: ' + q);
    };
  }
  return isWideMousePc();
});
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_client_pc_check_matches_server_wants_mobile_width_surfaces() -> None:
    """JS 판정 == not 서버 판정. 같은 기기 상태에서 부트가 심을 쿠키로 서버 함수를 부른다.

    부트(SSOT 사본)가 묻는 미디어 쿼리 문자열만 스텁이 답한다 — 다른 식을 쓰면 실행이 깨진다.
    """
    assert "window.matchMedia('(pointer: coarse)')" in _PTR_BOOT.read_text(encoding="utf-8")
    assert "window.matchMedia('(min-width: 992px)')" in _VW_BOOT.read_text(encoding="utf-8")
    cases = [{"no_mm": False, "coarse": c, "wide": w} for c in (False, True) for w in (False, True)]
    cases.append({"no_mm": True, "coarse": False, "wide": True})
    func = _js_function(_SHIP_JS.read_text(encoding="utf-8"), "isWideMousePc")
    script = _PC_HARNESS.replace("__CASES__", json.dumps(cases)).replace("__FUNC__", func)
    with tempfile.TemporaryDirectory(prefix="asrec-pc-") as tmp:
        path = Path(tmp) / "pc_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([shutil.which("node"), str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = json.loads(proc.stdout)

    class _Req:
        def __init__(self, cookies: dict[str, str]) -> None:
            self.cookies = cookies

    for case, js_pc in zip(cases, got):
        cookies = {} if case["no_mm"] else {
            "foms_ptr": "coarse" if case["coarse"] else "fine",
            "foms_vw": "wide" if case["wide"] else "narrow",
        }
        server_pc = not feature_flags.wants_mobile_width_surfaces(_Req(cookies))
        assert js_pc is server_pc, (case, cookies, js_pc, server_pc)
    assert got == [False, True, False, False, False]  # 광폭 마우스 PC 한 칸만 예열
