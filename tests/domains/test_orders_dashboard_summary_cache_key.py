"""주문 대시보드 숫자판(summary_counts) 캐시 키 축 계약.

숫자판(KPI·단계별 건수)은 ``build_orders_dashboard_queries`` 가 만든 ``_q_stats`` 에서 센다.
그 쿼리는 검색어·내 담당·오늘·날짜(+현장 구분)·위험·상태·팀 필터를 **복제 전에** 건다.
키가 그중 하나라도 빠뜨리면, 필터를 바꿔도 TTL(300초) 동안 먼저 계산된 숫자가 나온다 —
2026-10-05 스테이징 실화면에서 status=ON_HOLD 목록은 0건인데 단계 합계는 필터 없는 값(532)이었다
(키 v4 에 date·field·risk·status 가 없었다).

여기서는 두 가지를 고정한다.
1. 결과를 바꾸는 필터는 키를 바꾼다. 복제 **뒤에** 거는 단계(stage) 필터는 키를 바꾸지 않는다
   (숫자판은 단계 칩 전체를 보여 주므로 단계마다 따로 셀 이유가 없다 — 공유 유지).
2. 정적 계약: 복제 전에 읽는 ``filters.<이름>`` 은 모두 키에 들어 있다. 새 필터를 추가하고
   키를 잊으면 이 테스트가 빨개진다(음성 대조 포함).
"""

from __future__ import annotations

import pathlib
import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.web.orders import dashboard as orders_dashboard
from models import User

ROOT = pathlib.Path(__file__).resolve().parents[2]
READ_MODEL = ROOT / "foms" / "services" / "orders" / "dashboard_read_model.py"
VIEW = ROOT / "foms" / "web" / "orders" / "dashboard.py"


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_admin(client) -> None:
    user = User(
        username="summary_key_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="SALES",
        name="summary_key_admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _summary_key(client, monkeypatch, query: str) -> str:
    """라우트 1회 호출에서 summary_counts 캐시 키를 받는다(서비스 원본을 감싼다 — 중첩 방지)."""
    captured: dict[str, str] = {}
    original = dc.build_dashboard_cache_key

    def _spy(page: str, slice_name: str, fingerprint: dict) -> str:
        key = original(page, slice_name, fingerprint)
        captured[slice_name] = key
        return key

    monkeypatch.setattr(orders_dashboard, "build_dashboard_cache_key", _spy)
    resp = client.get(f"/erp/dashboard{query}")
    assert resp.status_code == 200
    return captured["summary_counts"]


def test_filters_that_change_the_counted_set_change_the_key(client, monkeypatch) -> None:
    _login_admin(client)
    base = _summary_key(client, monkeypatch, "?view=fragment")
    variants = {
        "status": "?view=fragment&status=ON_HOLD",
        "risk": "?view=fragment&risk=balance_due",
        "date": "?view=fragment&date=2026-10-06",
        "date+field": "?view=fragment&date=2026-10-06&field=measure",
        "today": "?view=fragment&today=1",
    }
    keys = {name: _summary_key(client, monkeypatch, q) for name, q in variants.items()}
    for name, key in keys.items():
        assert key != base, f"{name} 필터가 숫자판 키를 바꾸지 않는다(필터 없는 숫자가 나온다)"
    assert keys["date"] != keys["date+field"], "현장 구분(field)이 키에 없다"
    assert len(set(keys.values())) == len(keys), "서로 다른 필터가 같은 키를 쓴다"


def test_same_filters_share_the_key_and_stage_does_not_split_it(client, monkeypatch) -> None:
    """음성 대조: 같은 필터는 같은 키, 복제 뒤에 거는 단계 필터는 키를 바꾸지 않는다."""
    _login_admin(client)
    first = _summary_key(client, monkeypatch, "?view=fragment&status=RECHECK")
    again = _summary_key(client, monkeypatch, "?view=fragment&status=RECHECK")
    assert first == again
    base = _summary_key(client, monkeypatch, "?view=fragment")
    with_stage = _summary_key(client, monkeypatch, "?view=fragment&stage=MEASURE")
    assert base == with_stage


def _filters_read_before_stats_clone(source: str) -> set[str]:
    body = source.split("def build_orders_dashboard_queries", 1)[1]
    body = body.split("_q_stats = _q.order_by(None)", 1)[0]
    return set(re.findall(r"filters\.([a-z_]+)", body))


def _summary_fingerprint_filter_keys(source: str) -> set[str]:
    block = source.split("_summary_fp = {", 1)[1].split("_summary_key = ", 1)[0]
    filters_block = block.split('"filters": {', 1)[1].split("}", 1)[0]
    return set(re.findall(r'"([a-z_]+)":', filters_block))


def test_every_filter_feeding_the_stats_query_is_in_the_key() -> None:
    read_before = _filters_read_before_stats_clone(READ_MODEL.read_text(encoding="utf-8"))
    key_axes = _summary_fingerprint_filter_keys(VIEW.read_text(encoding="utf-8"))
    assert read_before, "읽은 필터를 하나도 못 찾았다 — 파서 전제가 깨졌다"
    missing = read_before - key_axes
    assert not missing, f"숫자판 키에 빠진 필터: {sorted(missing)}"


def test_static_contract_negative_control() -> None:
    """키에서 status 를 지운 사본은 계약이 잡는다."""
    view = VIEW.read_text(encoding="utf-8")
    broken = view.replace('"status": _filters.status,', "", 1)
    assert broken != view, "음성 대조 전제(키에 status 줄)가 사라졌다"
    read_before = _filters_read_before_stats_clone(READ_MODEL.read_text(encoding="utf-8"))
    assert "status" in read_before - _summary_fingerprint_filter_keys(broken)
