"""시공 대시보드 마이크로 캐시 키 축 계약.

요약(KPI/step_stats)은 공용 목록(mine=False)일 때 사용자와 무관한 값이고, 첨부 개수는
주문 id 집합에만 의존한다. 그런데도 키에 uid/role/필터를 넣으면 같은 숫자를 사용자·화면마다
다시 계산한다 — 요약 재계산은 60일 주문 전량 순회라 스테이징 실측 ≈ 88ms 였다.
여기서는 "결과를 결정하는 축만 키에 넣는다"를 고정한다.
"""

from __future__ import annotations

import datetime

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
