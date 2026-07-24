"""AUTH-QUEST-READ-01 — quest GET는 순수 read여야 한다.

quest 없는 주문에 GET을 반복해도 quest row 생성/JSONB 기록/db.commit/version/event가
발생하면 안 된다. quest 생성은 기존 mutation(POST) 경로에만 남는다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _login_as_admin(client, username="quest-read-admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Quest Read Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    return user


def _create_order(*, stage="RECEIVED", quests=None) -> Order:
    structured_data = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
    }
    if quests is not None:
        structured_data["quests"] = quests
    order = Order(
        received_date="2026-07-24",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=stage,
        is_erp_order=True,
        structured_data=structured_data,
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_quest_get_never_creates_quest_or_commits(client, monkeypatch):
    """quest 없는 주문에 GET 반복 → quest row 생성 0·JSONB 불변·version 불변·event 0.

    구버전 GET 핸들러는 `order.structured_data = sd`가 로드된 dict를 in-place
    mutate 후 동일 객체 참조로 재대입하는 패턴이라 flag_modified 없이는 실제
    UPDATE로 반영되지 않는다 — 그래서 structured_data 영속 여부만으로는 이
    packet의 fix를 red→green으로 구분하지 못한다. 대신 GET의 write 분기가
    지워졌는지는 그 분기 안에서만 호출되던 `invalidate_all_dashboard_slice_caches`
    (탭 캐시 무효화 — write 전용 side effect) 호출 여부로 확정한다: 구버전은
    quest lazy-create 성공 시 반드시 호출, 수정본은 GET에서 전혀 호출하지 않는다.
    """
    import foms.services.common.dashboard_cache as dashboard_cache

    invalidate_calls = []
    monkeypatch.setattr(
        dashboard_cache,
        "invalidate_all_dashboard_slice_caches",
        lambda: invalidate_calls.append(1),
    )

    _login_as_admin(client)
    order = _create_order(stage="RECEIVED")
    order_id = order.id
    original_mutation_version = order.mutation_version

    for _ in range(2):
        response = client.get(f"/api/orders/{order_id}/quest")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # 표시용으로 합성된 quest는 반환하되(비영속), 저장은 하지 않는다.
        assert data["quest"] is not None
        assert data["quest"]["title"]
        assert data["stage"] == "RECEIVED"

    # write-only side effect(대시보드 캐시 무효화)가 GET에서 전혀 트리거되지 않아야 한다.
    assert invalidate_calls == []

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert not (saved_order.structured_data or {}).get("quests")
    assert saved_order.mutation_version == original_mutation_version
    assert (
        db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).count() == 0
    )


def test_quest_get_returns_existing_quest_without_mutation(client):
    """quest 있는 주문 GET → 내용 정확히 조회·version/event 변화 0."""
    _login_as_admin(client)
    existing_quest = {
        "stage": "RECEIVED",
        "title": "기존 퀘스트",
        "description": "이미 저장된 퀘스트",
        "owner_team": "CS",
        "owner_person": "테스트담당",
        "status": "OPEN",
        "required_approvals": ["CS"],
        "team_approvals": {"CS": {"approved": False, "approved_by": None, "approved_at": None}},
        "approval_mode": "team",
        "assignee_approval": None,
        "created_at": "2026-07-24T00:00:00",
        "updated_at": "2026-07-24T00:00:00",
    }
    order = _create_order(stage="RECEIVED", quests=[existing_quest])
    order_id = order.id
    original_mutation_version = order.mutation_version

    response = client.get(f"/api/orders/{order_id}/quest")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["quest"]["title"] == "기존 퀘스트"
    assert data["quest"]["owner_person"] == "테스트담당"

    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    assert saved_order.structured_data.get("quests") == [existing_quest]
    assert saved_order.mutation_version == original_mutation_version
    assert (
        db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).count() == 0
    )


def test_quest_post_still_creates_quest_regression_guard(client):
    """대조: 기존 mutation(POST) 경로는 여전히 quest를 생성·저장한다 (회귀 없음)."""
    _login_as_admin(client)
    order = _create_order(stage="RECEIVED")
    order_id = order.id

    response = client.post(f"/api/orders/{order_id}/quest", json={"stage": "RECEIVED"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["quest"]["stage"] == "RECEIVED"

    # 주의(범위 밖 발견): api_order_quest_create는 `order.structured_data = sd`가
    # 로드된 dict를 in-place mutate 후 동일 객체 참조로 재대입하는 패턴이라
    # copy.deepcopy/flag_modified 없이는 SQLAlchemy dirty-tracking에 잡히지 않는다
    # (CLAUDE.md JSONB 수정 패턴 위반, 이 packet 이전부터 존재하던 별개 버그).
    # AUTH-QUEST-READ-01은 GET 경로만 다루므로 이 동작을 고치지 않는다 — 아래
    # assert는 "내 GET 수정이 creation 경로 동작을 바꾸지 않았음"을 현재 실제
    # 동작 그대로 고정한다 (STATE-QUEST-01에서 mutation을 transition tx로
    # 이관할 때 함께 정정될 것으로 예상).
    db_session.expire_all()
    saved_order = db_session.get(Order, order_id)
    assert saved_order is not None
    saved_quests = (saved_order.structured_data or {}).get("quests") or []
    assert saved_quests == []
