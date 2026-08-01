"""PACK-01: packing 제출 one-tx·중복 제출 0·shell GET 0·권한 계약 (red→green).

packing 제출(체크/항목 추가/출발 보고)을 REV-00 :func:`execute_order_mutation` 경유
정본 command 로 확정한다: §2.1 policy(``PACKING_WRITE``) + If-Match(mutation_version 낙관
잠금) + version bump + idempotency receipt + OrderEvent 를 **한 transaction** 에 묶고,
같은 ``Idempotency-Key`` 재요청은 replay(중복 제출 0)로 수렴한다. 다른 상태 축
(main/logistics/hold/AS/delete)은 절대 불변(orthogonal write)이다.

"submit 1회 = POST 1"(더블탭 방지·button disable)과 "shell GET 0"(제출이 erp-shell
fragment 재조회를 유발하지 않음)은 JS 런타임이 없는 CI 에서 정적 소스 계약(fixture)으로
고정한다: ``foms-packing.js`` 는 제출 응답을 in-place 반영하고 shell navigation API 를
호출하지 않으며(shell GET 0), add 제출은 진행 중 재제출을 차단한다(POST 1).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from foms.services.orders.state_axes import read_state_axes
from models import Order, OrderEvent, OrderMutationReceipt, User

PACKING_WRITE_POLICY_ID = "PACKING_WRITE"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKING_JS = _REPO_ROOT / "static" / "js" / "shipment" / "foms-packing.js"
_RUNTIME_SHELL = _REPO_ROOT / "static" / "js" / "runtime" / "erp-shell.js"
_SHIPMENT_DASH = _REPO_ROOT / "templates" / "shipment" / "dashboard.html"
_CONSTRUCTION_DASH = _REPO_ROOT / "templates" / "construction" / "dashboard.html"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 AUTH-01 정책 가드를 강제 활성화하고 원복한다(test_call_log 준용)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _login(client, *, username, role, team=None):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return user


def _make_order(structured_data=None, status="IN_CONSTRUCTION") -> int:
    today = get_today_kst().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="패킹 고객",
        phone="010-2000-3000",
        address="서울시 패킹구 1",
        product="싱크대",
        status=status,
        scheduled_date=today,
        is_erp_order=True,
        erp_stage_code=status,
        structured_data=structured_data
        if structured_data is not None
        else {
            "workflow": {"stage": "SHIPMENT"},
            "items": [{"product_name": "싱크대"}, {"product_name": "붙박이장"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _url(order_id: int) -> str:
    return f"/api/erp/shipment/packing/{order_id}"


def _derived_keys(client, oid):
    return [r["key"] for r in client.get(_url(oid)).get_json()["data"]["items"]]


# --------------------------------------------------------------------------
# one-tx: policy + version bump + receipt + OrderEvent (한 tx)
# --------------------------------------------------------------------------
def test_packing_save_bumps_version_and_writes_receipt(client, app):
    """체크 저장은 mutation_version++ · receipt 1 · OrderEvent(PACKING_UPDATED) 1 을 한 tx 에."""
    _login(client, username="pk-onetx", role="STAFF", team="SHIPMENT")
    oid = _make_order()
    before = _fresh(oid).mutation_version
    key = _derived_keys(client, oid)[0]

    resp = client.post(_url(oid), json={"updates": [{"key": key, "checked": True}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["data"]["checked_count"] == 1
    # 읽기-이후-쓰기 receipt 토큰이 응답에 실린다.
    assert body["data"]["mutation_receipt"]
    # write 응답은 캐시되지 않는다(no-store).
    assert "no-store" in (resp.headers.get("Cache-Control") or "")

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1  # 정확히 1회 bump

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PACKING_UPDATED").all()
    assert len(events) == 1
    receipts = db_session.query(OrderMutationReceipt).filter_by(policy_id=PACKING_WRITE_POLICY_ID)
    assert receipts.count() == 1


def test_packing_save_leaves_other_axes_unchanged(client, app):
    """packing 갱신 후 canonical 5축(main/logistics/hold/AS/delete) 완전 불변(orthogonal)."""
    _login(client, username="pk-orth", role="STAFF", team="SHIPMENT")
    oid = _make_order(
        structured_data={
            "workflow": {"stage": "SHIPMENT", "hold": {"active": True, "reason": "대기"}},
            "shipment": {"logistics_status": "SCHEDULED"},
            "items": [{"product_name": "싱크대"}],
        }
    )
    axes_before = read_state_axes(_fresh(oid))
    key = _derived_keys(client, oid)[0]

    resp = client.post(_url(oid), json={"updates": [{"key": key, "checked": True}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    axes_after = read_state_axes(_fresh(oid))
    assert axes_after.main == axes_before.main
    assert axes_after.logistics == axes_before.logistics
    assert axes_after.hold == axes_before.hold
    assert axes_after.as_status == axes_before.as_status
    assert axes_after.deleted == axes_before.deleted


# --------------------------------------------------------------------------
# idempotency: same key → 제출 1회 = POST 1 (replay, 중복 없음)
# --------------------------------------------------------------------------
def test_packing_save_same_idempotency_key_writes_once(client, app):
    """같은 Idempotency-Key 재요청은 replay — 항목 추가 1 · event 1 · version 1회 bump."""
    _login(client, username="pk-idem", role="STAFF", team="SHIPMENT")
    oid = _make_order()
    before = _fresh(oid).mutation_version
    base_total = client.get(_url(oid)).get_json()["data"]["total"]
    headers = {"Idempotency-Key": "22222222-2222-2222-2222-222222222222"}
    body = {"add": {"label": "상판 유리", "qty": 2}}

    r1 = client.post(_url(oid), json=body, headers=headers)
    r2 = client.post(_url(oid), json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200, (
        r1.get_data(as_text=True), r2.get_data(as_text=True),
    )
    # 두 응답 모두 같은 total(추가 1회만 반영) — 재요청이 두 번째 항목을 추가하지 않는다.
    assert r1.get_json()["data"]["total"] == base_total + 1
    assert r2.get_json()["data"]["total"] == base_total + 1

    fresh = _fresh(oid)
    packing_items = (fresh.structured_data.get("shipment") or {}).get("packing", {}).get("items", [])
    assert sum(1 for it in packing_items if it.get("label") == "상판 유리") == 1  # append 1
    assert fresh.mutation_version == before + 1  # 1회만 bump
    assert (
        db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PACKING_UPDATED").count()
        == 1
    )


# --------------------------------------------------------------------------
# If-Match(mutation_version) 낙관 잠금
# --------------------------------------------------------------------------
def test_packing_save_stale_if_match_conflicts_and_no_change(client, app):
    """stale If-Match → 409 · packing/version/event 완전 불변."""
    _login(client, username="pk-stale", role="STAFF", team="SHIPMENT")
    oid = _make_order()
    before = _fresh(oid).mutation_version
    key = _derived_keys(client, oid)[0]

    resp = client.post(
        _url(oid),
        json={"updates": [{"key": key, "checked": True}]},
        headers={"If-Match": str(before + 5)},  # stale
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert "packing" not in (fresh.structured_data.get("shipment") or {})  # 상태 불변
    assert fresh.mutation_version == before  # version 불변
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


def test_packing_save_matching_if_match_succeeds(client, app):
    """정확한 If-Match(현재 version) → 200 저장."""
    _login(client, username="pk-match", role="STAFF", team="SHIPMENT")
    oid = _make_order()
    current = _fresh(oid).mutation_version
    key = _derived_keys(client, oid)[0]

    resp = client.post(
        _url(oid),
        json={"updates": [{"key": key, "checked": True}]},
        headers={"If-Match": str(current)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).mutation_version == current + 1


# --------------------------------------------------------------------------
# 출발 보고 게이트(전 항목 체크)는 새 경로에서도 400 + 미저장
# --------------------------------------------------------------------------
def test_departed_gate_400_leaves_no_write(client, app):
    """전 항목 체크 전 출발 보고 → 400 · departed 미기록 · version 불변 · event 0(우회 차단)."""
    _login(client, username="pk-depart-gate", role="STAFF", team="SHIPMENT")
    oid = _make_order()
    before = _fresh(oid).mutation_version
    key = _derived_keys(client, oid)[0]
    client.post(_url(oid), json={"updates": [{"key": key, "checked": True}]})  # 6항 중 1항만
    ver_after_one = _fresh(oid).mutation_version

    resp = client.post(_url(oid), json={"departed": True})
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.get_json()["error"] == "전 항목 체크 후 출발 보고"

    fresh = _fresh(oid)
    packing = (fresh.structured_data.get("shipment") or {}).get("packing") or {}
    assert not packing.get("departed_at")
    assert fresh.mutation_version == ver_after_one  # 게이트 실패는 version bump 안 함
    assert (
        db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PACKING_DEPARTED").count()
        == 0
    )
    assert before is not None


# --------------------------------------------------------------------------
# 권한 (AUTH-01 PACKING_WRITE) — SHIPMENT team-wide + CONSTRUCTION, 그 외 deny
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("STAFF", "SHIPMENT"),
    ("STAFF", "CONSTRUCTION"),
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("ADMIN", None),
    ("MANAGER", None),
])
def test_packing_allows_eligible_actors(client, app, policy_on, role, team):
    """SHIPMENT/CONSTRUCTION/CS/SALES STAFF · ADMIN · MANAGER 는 packing 제출 200.

    파생 key 는 결정적(``item{idx}_body`` 등)이라 GET(로컬 read 게이트) 없이 직접 쓴다 —
    write 정책과 read 게이트의 대상 팀이 달라 GET 을 헬퍼로 쓰면 write 권한 판정이 오염된다.
    """
    _login(client, username=f"ok-{role}-{team}", role=role, team=team)
    oid = _make_order()
    resp = client.post(_url(oid), json={"updates": [{"key": "item0_body", "checked": True}]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") is None


@pytest.mark.parametrize("role,team", [
    ("VIEWER", None),
    ("VIEWER", "SHIPMENT"),  # VIEWER 는 team 무관 hard deny(현 로컬 게이트의 team-only 허점 봉합)
    ("STAFF", "DRAWING"),
    ("STAFF", "PRODUCTION"),
])
def test_packing_denies_ineligible_actors(client, app, policy_on, role, team):
    """VIEWER·타팀(DRAWING/PRODUCTION) STAFF 는 403 · DB/event/receipt 0."""
    _login(client, username=f"no-{role}-{team}", role=role, team=team)
    oid = _make_order()
    resp = client.post(_url(oid), json={"updates": [{"key": "item0_body", "checked": True}]})
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") == "denied"

    fresh = _fresh(oid)
    assert "packing" not in (fresh.structured_data.get("shipment") or {})
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0


# --------------------------------------------------------------------------
# JS 정적 소스 계약 (erp-shell.js fixture): shell GET 0 · submit 1 = POST 1
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def packing_js() -> str:
    assert _PACKING_JS.is_file(), f"missing {_PACKING_JS}"
    return _PACKING_JS.read_text(encoding="utf-8")


def test_erp_shell_exposes_navigation_fixture():
    """fixture: erp-shell.js 는 fragment GET(navigateByShell) 을 공개한다 — packing 이 안 부른다는
    "shell GET 0" 계약이 의미를 가지려면 그 메커니즘이 실제로 존재해야 한다."""
    shell = _RUNTIME_SHELL.read_text(encoding="utf-8")
    assert "window.FOMS_ERP_SHELL.navigateByShell" in shell
    assert "function fetchFragment" in shell


def test_packing_submit_reflects_response_no_shell_get(packing_js: str):
    """shell GET 0: 제출 성공은 POST 응답을 in-place 반영(applyData)하고, shell fragment
    재조회 API 를 호출하지 않는다(제출이 erp-shell GET 을 유발하지 않음)."""
    # 응답 반영 경로가 존재한다.
    assert "applyData(el, data)" in packing_js
    # shell navigation / 전체 리로드 / fragment 캐시 무효화 API 를 부르지 않는다.
    forbidden = [
        "FOMS_ERP_SHELL",
        "navigateByShell",
        "prefetchShellFragment",
        "invalidateFragmentCache",
        "location.reload",
        "location.assign",
        "location.href =",
        "window.location =",
    ]
    for token in forbidden:
        assert token not in packing_js, f"packing 제출이 shell GET 을 유발할 수 있는 호출: {token}"


def test_packing_add_submit_guards_double_post(packing_js: str):
    """submit 1회 = POST 1: add 폼 제출은 진행 중 재제출(더블탭·Enter)을 차단한다
    (submitting 가드 + submit 버튼 disable)."""
    submit_block = packing_js.split("addEventListener('submit'")[1]
    assert "form.dataset.submitting === '1'" in submit_block  # 진행 중 재제출 무시
    assert "form.dataset.submitting = '1'" in submit_block     # 진행 표식 세팅
    assert "submitBtn.disabled = true" in submit_block          # 버튼 비활성


def test_packing_js_version_bumped_in_dashboards():
    """foms-packing.js 변경 → SW staticCacheFirst 무력화용 ?v 범프(구 20260714a 이탈)."""
    for tpl in (_SHIPMENT_DASH, _CONSTRUCTION_DASH):
        src = tpl.read_text(encoding="utf-8")
        assert "foms-packing.js') }}?v=20260725a" in src, str(tpl)
        # JS 핀만 검사 — 무관한 foms-packing.css 핀(20260714a)까지 잡지 않도록 스코프한다.
        assert "foms-packing.js') }}?v=20260714a" not in src, f"구 JS 버전 핀 잔존: {tpl}"
