"""시공 대시보드 마이크로 캐시 키 축 계약.

요약(KPI/step_stats)은 공용 목록(mine=False)일 때 사용자와 무관한 값이고, 첨부 개수는
주문 id 집합에만 의존한다. 그런데도 키에 uid/role/필터를 넣으면 같은 숫자를 사용자·화면마다
다시 계산한다 — 요약 재계산은 60일 주문 전량 순회라 스테이징 실측 ≈ 88ms 였다.
여기서는 "결과를 결정하는 축만 키에 넣는다"를 고정한다.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.web.construction import dashboard as construction_dashboard
from models import Order, User


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _make_user(username: str, role: str, team: str = "SALES") -> dict:
    """세션 detach 를 피하려고 로그인에 필요한 원시값만 돌려준다.

    team 기본값이 SALES 인 이유: 시공팀(team=CONSTRUCTION)은 정책상 항상 mine_only 라
    (erp_mine_only_for_construction) 공용 목록 경로 자체를 탈 수 없다.
    """
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role=role,
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, user: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["username"] = user["username"]
        sess["role"] = user["role"]


def _seed_order(idx: int) -> None:
    order = Order(
        received_date="2026-06-01",
        customer_name=f"시공캐시{idx}",
        phone=f"010-4000-{idx:04d}",
        address=f"서울시 시공구 {idx}",
        product="시공 제품",
        is_erp_order=True,
        erp_stage_code="CONSTRUCTION",
        erp_construction_date=(datetime.date.today() + datetime.timedelta(days=3)).isoformat(),
        structured_data={"workflow": {"stage": "CONSTRUCTION"}},
    )
    db_session.add(order)
    db_session.commit()


def _capture_keys(client, monkeypatch, query: str) -> dict[str, str]:
    """라우트 1회 호출에서 slice 별 캐시 키를 수집한다.

    원본은 서비스 모듈에서 직접 가져온다 — 라우트 모듈 속성을 쓰면 두 번째 호출이 앞서
    설치한 spy 를 감싸(중첩) 이전 호출의 수집 dict 까지 덮어써 비교가 무의미해진다.
    """
    captured: dict[str, str] = {}
    original = dc.build_dashboard_cache_key

    def _spy(page: str, slice_name: str, fingerprint: dict) -> str:
        key = original(page, slice_name, fingerprint)
        captured[slice_name] = key
        return key

    monkeypatch.setattr(construction_dashboard, "build_dashboard_cache_key", _spy)
    resp = client.get(f"/erp/construction/dashboard{query}")
    assert resp.status_code == 200
    return captured


def test_summary_cache_key_is_shared_across_users_for_public_list(client, monkeypatch) -> None:
    """mine=False 요약은 값이 사용자와 무관하므로 키도 공유한다(중복 계산 제거)."""
    _seed_order(1)
    admin = _make_user("cache_share_admin", "ADMIN")
    staff = _make_user("cache_share_staff", "STAFF")

    _login(client, admin)
    admin_keys = _capture_keys(client, monkeypatch, "?view=fragment")
    _login(client, staff)
    staff_keys = _capture_keys(client, monkeypatch, "?view=fragment")

    assert admin_keys["summary_counts"] == staff_keys["summary_counts"]


def test_summary_cache_key_still_separates_mine_only(client, monkeypatch) -> None:
    """mine=True 목록은 사용자마다 집합이 다르므로 키가 갈려야 한다(교차 노출 금지)."""
    _seed_order(2)
    a = _make_user("cache_mine_a", "STAFF")
    b = _make_user("cache_mine_b", "STAFF")

    _login(client, a)
    a_keys = _capture_keys(client, monkeypatch, "?view=fragment&mine=1")
    _login(client, b)
    b_keys = _capture_keys(client, monkeypatch, "?view=fragment&mine=1")

    assert a_keys["summary_counts"] != b_keys["summary_counts"]
    # 공용 목록 키와도 달라야 한다.
    _login(client, a)
    public_keys = _capture_keys(client, monkeypatch, "?view=fragment")
    assert a_keys["summary_counts"] != public_keys["summary_counts"]


def test_attachment_cache_key_depends_only_on_order_ids(client, monkeypatch) -> None:
    """첨부 개수 키는 주문 id 집합만 본다 — 같은 묶음이면 사용자가 달라도 한 번만 집계."""
    _seed_order(3)
    admin = _make_user("cache_att_admin", "ADMIN")
    staff = _make_user("cache_att_staff", "STAFF")

    _login(client, admin)
    admin_keys = _capture_keys(client, monkeypatch, "?view=fragment")
    _login(client, staff)
    staff_keys = _capture_keys(client, monkeypatch, "?view=fragment")

    assert admin_keys["attachment_counts"] == staff_keys["attachment_counts"]


def _seed_non_construction_urgent_order() -> None:
    """시공 단계가 아닌 긴급 주문(실측 단계) — 시공 숫자판에는 잡히면 안 된다."""
    order = Order(
        received_date="2026-06-01",
        customer_name="실측단계긴급",
        phone="010-4999-0001",
        address="서울시 실측구",
        product="실측 제품",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        structured_data={"workflow": {"stage": "MEASURE"}, "flags": {"urgent": True}},
    )
    db_session.add(order)
    db_session.commit()


def _seed_construction_urgent_order() -> None:
    order = Order(
        received_date="2026-06-01",
        customer_name="시공단계긴급",
        phone="010-4999-0002",
        address="서울시 시공구",
        product="시공 제품",
        is_erp_order=True,
        erp_stage_code="CONSTRUCTION",
        structured_data={"workflow": {"stage": "CONSTRUCTION"}, "flags": {"urgent": True}},
    )
    db_session.add(order)
    db_session.commit()


def test_summary_counts_only_construction_stage_orders(client, monkeypatch) -> None:
    """숫자판은 시공 대시보드의 것 — 긴급 발주도 시공 단계 주문만 센다(목록과 같은 모집단)."""
    _seed_non_construction_urgent_order()
    _seed_construction_urgent_order()
    admin = _make_user("summary_scope_admin", "ADMIN")
    _login(client, admin)

    captured: dict[str, int] = {}
    original = construction_dashboard.compute_construction_summary_blob

    def _spy(query):
        blob = original(query)
        captured.update(blob["kpis"])
        return blob

    monkeypatch.setattr(construction_dashboard, "compute_construction_summary_blob", _spy)
    resp = client.get("/erp/construction/dashboard?view=fragment")
    assert resp.status_code == 200

    # 실측 단계 긴급 1건은 제외, 시공 단계 긴급 1건만 계수된다.
    assert captured["urgent_count"] == 1


def test_response_exposes_slice_diagnostics_header(client, monkeypatch) -> None:
    """슬라이스 진단 헤더: 어떤 조각이 hit/miss 였고 재계산에 몇 ms 썼는지 노출한다."""
    _seed_order(4)
    admin = _make_user("slice_header_admin", "ADMIN")
    _login(client, admin)

    resp = client.get("/erp/construction/dashboard?view=fragment")
    assert resp.status_code == 200

    header = resp.headers.get("X-FOMS-DASH-SLICES", "")
    assert "summary_counts=" in header
    assert "attachment_counts=" in header
    # 형식: <slice>=<result>:<ms> — ms 는 정수여야 파싱이 안전하다.
    for entry in header.split(";"):
        name, _, rest = entry.partition("=")
        result, _, ms = rest.partition(":")
        assert name and result
        assert ms.isdigit()


def test_slice_diagnostics_cover_every_return_path() -> None:
    """계측 사각 금지: 캐시 슬라이스의 모든 반환 경로가 관측을 남긴다.

    처음 배선했을 때 miss 본 경로와 singleflight 팔로워(hit_sf)에 관측이 없어,
    스테이징에서 정작 재계산 비용을 못 재는 사각이 있었다.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    src = (root / "foms/services/common/dashboard_cache.py").read_text(encoding="utf-8")

    start = src.index("def get_or_compute_dashboard_slice(")
    body = src[start:]
    # bypass/hit/hit_sf/miss 네 결과가 모두 관측된다(bypass 는 공용 헬퍼 1곳에서 처리).
    for result in ('"hit", 0', '"hit_sf", 0', '"miss", compute_ms'):
        assert f"record_slice_observation(slice_name, {result})" in body
    assert "record_slice_observation(slice_name, result, elapsed_ms)" in body


def test_response_exposes_route_phase_timings(client, monkeypatch) -> None:
    """구간 계측 헤더: 렌더 밖 시간이 어디로 가는지(목록 쿼리·행 조립·payload) 보여준다.

    render_ms 만으로는 "렌더 30ms 인데 응답 250ms" 의 나머지를 알 수 없어 최적화 대상을
    추정으로 고르게 된다 — 실제로 초기 추정(요약 88ms)이 계측값(27ms)과 크게 어긋났다.
    """
    _seed_order(5)
    admin = _make_user("phase_header_admin", "ADMIN")
    _login(client, admin)

    resp = client.get("/erp/construction/dashboard?view=fragment")
    assert resp.status_code == 200

    header = resp.headers.get("X-FOMS-EPT-B7-PHASES", "")
    # detail_payloads 구간은 preload 폐지(lazy fetch 전환)로 사라졌다 — 계측 대상 아님.
    for name in ("summary_slice", "list_query", "attachment_slice", "row_dtos"):
        assert f"{name}=" in header, header
    for entry in header.split(";"):
        name, _, ms = entry.partition("=")
        assert name and ms.isdigit()


def test_construction_fragment_no_longer_preloads_order_detail_payload(client) -> None:
    """시공 fragment는 행별 상세 payload를 선적재하지 않는다(주문·생산 대시보드와 동일 계약).

    50행분 detail_payload JSON 선적재가 스테이징 실측 174KB(전체 923KB의 18.9%)였다.
    상세 패널을 처음 열 때 /api/orders/<id>/detail-payload 로 lazy fetch 한다.
    """
    _seed_order(11)
    admin = _make_user("constr_preload_admin", "ADMIN")
    _login(client, admin)

    resp = client.get("/erp/construction/dashboard?view=fragment")
    assert resp.status_code == 200

    body = resp.get_data(as_text=True)
    assert "order-detail-preload-" not in body
    # 패널 컨테이너 자체는 남아야 한다(lazy fetch 결과를 여기에 렌더).
    assert "order-detail-content-" in body


def test_construction_dashboard_js_uses_lazy_detail_payload_endpoint() -> None:
    """시공 대시보드 JS는 preload <script> 파싱이 아니라 lazy fetch 경로를 쓴다."""
    js = (
        pathlib.Path(__file__).resolve().parents[2]
        / "static/js/construction/dashboard.js"
    ).read_text(encoding="utf-8")

    assert "/detail-payload`" in js
    assert "order-detail-preload-" not in js
