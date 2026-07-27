"""D1c 계약: AS 모바일 카드 <details> 상세를 eager 렌더에서 열 때 fetch 주입으로 전환.

성능 목적(fragment payload 잔여 최대 덩어리 제거)이므로 계약의 의도는 세 가지다.
1) 서버 렌더 마크업: 모바일 v2 카드는 상세(시공자·AS 타임라인)를 더 이상 eager 렌더하지 않고
   placeholder(data-as-card-lazy)만 남긴다. PC 테이블은 타임라인 요약 셀(.as-tl-cell)만 싣고,
   타임라인 본체(.as-timeline)는 lazy 표면(상세·확장 fragment) 전용이다.
2) 서버 endpoint: GET /erp/as/card-detail/<id>가 대시보드와 동일한 매크로로 단건 상세를 렌더한다.
   비-AS 주문/없는 주문은 404, 비로그인은 로그인 리다이렉트.
3) 클라이언트: <details> toggle 위임(capture·window 가드) + dataset.loaded 멱등 + 에러/재시도 경로 +
   주입 후 날짜/시공자 재배선 + 검색어 하이라이트 재적용(window.__fomsAsRebindLazyCard).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_ROOT = Path(__file__).resolve().parents[2]


def _login_as_admin(client, username="as_card_lazy_admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Card Lazy Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_order(name, *, status="AS_RECEIVED"):
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today if status.startswith("AS") else None,
        is_erp_order=True,
        structured_data={"shipment": {"as_content": "리페어 요청", "as_content_2": ""}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_mobile_card_content_tabs_are_lazy_placeholder(client, monkeypatch):
    """모바일 v2 카드: 상세(시공자·AS 타임라인) eager 렌더 금지 + placeholder 존재.

    주문 N개 → 모바일 placeholder N개(data-as-card-lazy). 대시보드 응답에는 타임라인 본체
    (.as-timeline)가 하나도 없어야 한다 — PC 셀은 요약(.as-tl-cell)만, 모바일은 placeholder만
    싣기 때문이다. 카드에 render_as_timeline 이 eager 로 재유입되면 이 단언이 깨진다.
    """
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    for i in range(2):
        _create_order(f"카드 AS {i}")

    resp = client.get(
        "/erp/as?tab=incomplete&view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # 모바일 카드마다 lazy placeholder 1개
    assert body.count("data-as-card-lazy") == 2
    assert "erp-as-mobile-card--v2" in body  # v2 카드 렌더 확인
    # T9: PC 셀은 content-tabs 에디터에서 타임라인 요약(주문당 1개)으로 교체됨
    assert "as-tabbed-editor" not in body
    assert body.count('class="as-tl-cell"') == 2
    # 모바일 eager 금지의 진짜 가드: 타임라인 본체는 lazy 상세에서만 렌더된다
    assert 'class="as-timeline"' not in body
    # placeholder 안에는 초기 스켈레톤만, 에디터 폼값 없음
    assert "erp-as-card-lazy__status" in body


def test_card_detail_endpoint_renders_timeline_markup(client, monkeypatch):
    """card-detail endpoint: AS 주문 200 + 타임라인/시공자 마크업 포함, 비-AS/없음 404, 비로그인 리다이렉트."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client, username="as_card_detail_admin")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    # 요청이 세션을 정리하면 ORM 인스턴스가 detach되므로 id를 미리 확보한다.
    as_order_id = _create_order("상세 AS 주문").id
    non_as_order_id = _create_order("일반 주문", status="RECEIVED").id

    resp = client.get(f"/erp/as/card-detail/{as_order_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 대시보드 카드와 동일한 타임라인/시공자 마크업(SSOT 매크로 재사용)
    assert 'class="as-timeline"' in body
    assert "as-timeline__quick-add" in body
    assert "as-construction-worker-list" in body
    assert "as-tabbed-editor" not in body  # T9: content-tabs 퇴역

    # 비-AS 주문 → 404 (AS 상태 화이트리스트 밖)
    assert client.get(f"/erp/as/card-detail/{non_as_order_id}").status_code == 404
    # 없는 주문 → 404
    assert client.get("/erp/as/card-detail/99999999").status_code == 404

    # 비로그인 → 200 아님(로그인 리다이렉트)
    fresh = client.application.test_client()
    unauth = fresh.get(f"/erp/as/card-detail/{as_order_id}")
    assert unauth.status_code != 200
    assert unauth.status_code in (301, 302)


def test_card_lazy_js_contract():
    """클라이언트 lazy 계약: toggle 위임(capture·window 가드)·loaded 멱등·에러/재시도·재배선."""
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    # fetch 대상 endpoint
    assert "/erp/as/card-detail/" in js
    # document 1회 위임(window 가드) + toggle(비버블) capture 수신
    assert "window.__FOMS_AS_CARD_LAZY_BOUND" in js
    assert "'toggle'" in js
    assert "loadAsCardDetail" in js
    # 멱등: 이미 로드된 placeholder 재요청 금지
    assert "dataset.loaded" in js
    # 조용한 실패 금지: 에러 표시 + 재시도 버튼
    assert "as-card-lazy-retry" in js
    # 주입 후 날짜/시공자 재배선(최신 클로저 = 살아있는 AbortController) + 하이라이트 재적용
    assert "__fomsAsRebindLazyCard" in js
    assert "bindAsDateAndWorkerInputs(scope)" in js
    assert "highlightTimelineStatic(scope)" in js


def test_card_detail_partial_reuses_shared_macros():
    """파셜 소스 계약: 타임라인·시공자 매크로를 대시보드 카드와 동일하게 재사용(SSOT)."""
    partial = (_ROOT / "templates/cs/partials/as_card_detail_partial.html").read_text(encoding="utf-8")
    assert "render_as_timeline" in partial
    assert "render_as_construction_workers" in partial
    # 모바일 카드 파셜에는 <details> 안 eager 상세가 없어야 한다(placeholder만)
    card = (_ROOT / "templates/cs/partials/as_mobile_order_card.html").read_text(encoding="utf-8")
    assert "data-as-card-lazy" in card
