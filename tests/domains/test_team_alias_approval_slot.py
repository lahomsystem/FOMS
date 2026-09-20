"""C-A1 팀 별칭 승인 슬롯 — 누른 팀이 아니라 **필수 팀** 칸이 채워진다.

경리팀(ACCOUNTING)은 CS 와 같은 업무 권한을 갖는다(order_mutation_policy 의 capability
별칭). 그런데 승인 기록을 누른 팀 이름으로 적으면 ``team_approvals["ACCOUNTING"]`` 이
남고, 완료 판정(:func:`check_quest_approvals_complete`)은 필수 팀 이름을 **정확 일치**로만
보기 때문에 CS 칸은 영원히 비어 있다 — 눌렀는데 단계가 안 넘어가는 막다른 길이었다.

여기서 못박는 것: 슬롯 키 = 필수 팀 중 actor 가 자격을 갖는 팀, 값의 ``by_team`` =
실제로 누른 팀(정규화 전 원문). 읽기 술어는 손대지 않는다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _make_user(*, role: str, team: str, username: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _team_quest(stage_code: str, teams: list[str], approved: list[str] | None = None) -> dict:
    done = set(approved or [])
    return {
        "stage": stage_code,
        "title": f"{stage_code} quest",
        "description": "",
        "owner_team": teams[0] if teams else "",
        "owner_person": "",
        "status": "OPEN",
        "required_approvals": list(teams),
        "team_approvals": {
            t: {
                "approved": t in done,
                "approved_by": None,
                "approved_by_name": None,
                "approved_at": None,
            }
            for t in teams
        },
        "approval_mode": "team",
        "assignee_approval": None,
        "created_at": "2026-09-20T00:00:00",
        "updated_at": "2026-09-20T00:00:00",
    }


def _create_order(*, stage: str, quests: list[dict], status: str | None = None) -> Order:
    order = Order(
        received_date="2026-09-20",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status=status or stage,
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage}, "quests": quests},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _quest_of(order_id: int, stage_code: str) -> dict:
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved is not None
    quests = (saved.structured_data or {}).get("quests") or []
    matched = [q for q in quests if q.get("stage") == stage_code]
    assert matched, quests
    return matched[-1]


def test_경리팀_승인이_CS_칸을_채우고_단계를_넘긴다(client):
    """경리팀이 CS 필수 quest 를 승인하면 슬롯은 CS, by_team 은 ACCOUNTING 이고 단계가 넘어간다."""
    user = _make_user(role="STAFF", team="ACCOUNTING", username="acc-staff")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])],
                          status="RECEIVED")
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data["all_approved"] is True, data

    quest = _quest_of(order_id, "RECEIVED")
    assert "ACCOUNTING" not in quest["team_approvals"], quest["team_approvals"]
    assert quest["team_approvals"]["CS"]["approved"] is True
    assert quest["team_approvals"]["CS"]["by_team"] == "ACCOUNTING"

    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "MEASURE"


def test_대조군_도면팀은_CS_필수_quest_를_승인하지_못한다(client):
    """음성 대조군 — 자격 없는 팀은 403 이고 승인 칸이 하나도 바뀌지 않는다."""
    user = _make_user(role="STAFF", team="DRAWING", username="drw-staff")
    _login(client, user)
    order = _create_order(stage="RECEIVED", quests=[_team_quest("RECEIVED", ["CS"])],
                          status="RECEIVED")
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 403, resp.get_json()
    quest = _quest_of(order_id, "RECEIVED")
    assert quest["team_approvals"]["CS"]["approved"] is False
    assert "DRAWING" not in quest["team_approvals"], quest["team_approvals"]


def test_대조군_실측팀은_영업_칸을_채우고_by_team_은_MEASURE_로_남는다(client):
    """MEASURE 는 SALES 로 정규화되는 별칭이다 — 슬롯은 SALES, 누른 팀은 MEASURE 로 보존."""
    user = _make_user(role="STAFF", team="MEASURE", username="mea-staff")
    _login(client, user)
    order = _create_order(stage="MEASURE", quests=[_team_quest("MEASURE", ["CS", "SALES"])])
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    quest = _quest_of(order_id, "MEASURE")
    assert quest["team_approvals"]["SALES"]["approved"] is True
    assert quest["team_approvals"]["SALES"]["by_team"] == "MEASURE"
    assert "MEASURE" not in quest["team_approvals"], quest["team_approvals"]


def test_대조군_관리자가_팀을_지정하면_그_팀_칸이_채워진다(client):
    """ADMIN 이 payload team 을 명시하면 현행 그대로 그 팀 슬롯에 적는다."""
    user = _make_user(role="ADMIN", team="CS", username="admin-slot")
    _login(client, user)
    order = _create_order(stage="MEASURE", quests=[_team_quest("MEASURE", ["CS", "SALES"])])
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={"team": "SALES"})

    assert resp.status_code == 200, resp.get_json()
    quest = _quest_of(order_id, "MEASURE")
    assert quest["team_approvals"]["SALES"]["approved"] is True
    assert quest["team_approvals"]["CS"]["approved"] is False


def test_대조군_자격이_둘이면_아직_승인_안_된_팀_칸에_들어간다(client):
    """필수 팀 2개에 모두 자격이 있으면 이미 승인된 칸을 덮지 않고 남은 칸을 채운다."""
    user = _make_user(role="ADMIN", team="CS", username="admin-both")
    _login(client, user)
    order = _create_order(
        stage="MEASURE",
        quests=[_team_quest("MEASURE", ["CS", "SALES"], approved=["CS"])],
    )
    order_id = order.id
    before = _quest_of(order_id, "MEASURE")["team_approvals"]["CS"]

    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    quest = _quest_of(order_id, "MEASURE")
    assert quest["team_approvals"]["SALES"]["approved"] is True
    assert quest["team_approvals"]["CS"]["approved_by"] == before["approved_by"]


def test_대조군_이미_승인된_칸은_같은_자격의_다른_사람이_눌러도_보존된다(client):
    """CS 만 승인된 2팀 quest 를 CS 자격만 가진 경리팀이 다시 눌러도 원래 승인 기록이 남는다.

    남은 후보가 없으면 슬롯 팀은 ``None`` 이 되고 라우트가 actor 팀으로 폴백하므로,
    필수 팀 CS 칸의 ``approved_by``·``approved_by_name``·``approved_at`` 은 그대로다.
    """
    first = _make_user(role="STAFF", team="CS", username="cs-first")
    first_id = first.id
    _login(client, first)
    order = _create_order(stage="MEASURE", quests=[_team_quest("MEASURE", ["CS", "SALES"])])
    order_id = order.id

    assert client.post(f"/api/orders/{order_id}/quest/approve", json={}).status_code == 200
    before = _quest_of(order_id, "MEASURE")["team_approvals"]["CS"]
    assert before["approved"] is True and before["approved_by"] == first_id

    second = _make_user(role="STAFF", team="ACCOUNTING", username="acc-second")
    _login(client, second)
    resp = client.post(f"/api/orders/{order_id}/quest/approve", json={})

    assert resp.status_code == 200, resp.get_json()
    after = _quest_of(order_id, "MEASURE")["team_approvals"]["CS"]
    assert after["approved_by"] == before["approved_by"]
    assert after["approved_by_name"] == before["approved_by_name"]
    assert after["approved_at"] == before["approved_at"]
    # 필수 팀 SALES 칸은 경리팀 자격 밖이라 여전히 비어 있다(완료로 둔갑 금지).
    assert _quest_of(order_id, "MEASURE")["team_approvals"]["SALES"]["approved"] is False
