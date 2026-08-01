"""AS 기준 일정 링크 API 계약 테스트 (POST /api/orders/<id>/as/schedule-link).

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md §3·§4·§6.
권한(비로그인·편집권한)·검증(자기 자신·삭제된 기준)·4개 액션의 sd 반영과
AS 타임라인 system 항목 수를 고정한다.
"""

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_TODAY = date.today().strftime("%Y-%m-%d")


def _make_user(username: str, *, role: str = "ADMIN", team: str = "CS",
               name: str = "일정 매칭 사용자") -> int:
    """API 호출자를 만들고 id만 반환(요청 teardown 후 detach 되므로 스칼라만 들고 다닌다)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _login_as_admin(client, username: str = "link-admin") -> int:
    user_id = _make_user(username, role="ADMIN", name="일정 매칭 관리자")
    _login(client, user_id)
    return user_id


def _create_order(*, status: str = "AS_RECEIVED", construction_date: str | None = None,
                  visit_date: str | None = None) -> int:
    """AS 주문/기준 주문 공용 시드. 기준 주문은 construction_date 를 준다."""
    schedule = {"as_visit": {"date": visit_date}} if visit_date else {}
    order = Order(
        received_date=_TODAY,
        customer_name="일정 매칭 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        erp_construction_date=construction_date,
        structured_data={"workflow": {"stage": status}, "shipment": {}, "schedule": schedule},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _sd(order_id: int) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


def _link(order_id: int):
    return ((_sd(order_id).get("schedule") or {}).get("as_visit") or {}).get("schedule_link")


def _system_texts(order_id: int) -> list[str]:
    log = (_sd(order_id).get("shipment") or {}).get("as_log") or []
    return [e["text"] for e in log if e.get("type") == "system"]


def _post(client, order_id: int, payload: dict):
    return client.post(f"/api/orders/{order_id}/as/schedule-link", json=payload)


def _set_construction_date(order_id: int, value: str) -> None:
    """기준 주문의 시공일을 바꾼다(드리프트 발생 — 링크 API 를 거치지 않는 실제 경로)."""
    db_session.get(Order, order_id).erp_construction_date = value
    db_session.commit()


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


def test_schedule_link_requires_login(client):
    """비로그인은 로그인 페이지로 리다이렉트 — 링크가 만들어지지 않는다."""
    as_id = _create_order()
    ref_id = _create_order(status="CONSTRUCTION", construction_date="2026-08-05")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 302
    assert _link(as_id) is None


def test_schedule_link_requires_erp_edit_permission(client):
    """읽기만 가능한 팀(도면)은 403 — 쓰기는 ERP 편집 권한을 요구한다(스펙 §6)."""
    _login(client, _make_user("link-no-edit", role="STAFF", team="DRAWING", name="도면팀"))
    as_id = _create_order()
    ref_id = _create_order(status="CONSTRUCTION", construction_date="2026-08-05")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 403 and res.get_json()["success"] is False
    assert _link(as_id) is None


# ---------------------------------------------------------------------------
# link
# ---------------------------------------------------------------------------


def test_link_writes_structure_and_single_system_log(client):
    """link 은 스펙 §3.1 스키마를 sd 에 쓰고 system 항목을 정확히 1건만 남긴다."""
    user_id = _login_as_admin(client, "link-write-admin")
    as_id = _create_order(visit_date="2026-08-05")
    ref_id = _create_order(status="CONSTRUCTION", construction_date="2026-08-05")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id,
                                "ref_date": "2026-08-05"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)
    assert data["success"] is True

    saved = _link(as_id)
    assert saved == data["link"]
    assert saved["ref_order_id"] == ref_id
    assert saved["ref_kind"] == "construction"
    assert saved["ref_date"] == "2026-08-05"
    assert saved["source"] == "as_nearby_modal"
    assert saved["ack_ref_date"] is None
    assert saved["linked_by_user_id"] == user_id and saved["linked_by"] == "일정 매칭 관리자"
    assert saved["linked_at"]

    assert data["drift"]["state"] == "ok"
    assert data["drift"]["ref_order_id"] == ref_id
    assert _system_texts(as_id) == [f"기준 일정 매칭: 주문 #{ref_id} (2026-08-05)"]


def test_link_overrides_stale_client_ref_date(client):
    """클라 ref_date 는 모달을 연 시점 값이라 stale 일 수 있다 — 서버 재조회 값이 이긴다."""
    _login_as_admin(client, "link-stale-admin")
    as_id = _create_order()
    ref_id = _create_order(status="CONSTRUCTION", construction_date="2026-08-12")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id,
                                "ref_date": "2026-08-05"})  # 옛 날짜
    assert res.status_code == 200, res.get_data(as_text=True)

    assert _link(as_id)["ref_date"] == "2026-08-12"
    assert res.get_json()["drift"]["ref_current_date"] == "2026-08-12"
    assert _system_texts(as_id) == [f"기준 일정 매칭: 주문 #{ref_id} (2026-08-12)"]


def test_link_falls_back_to_scheduled_date(client):
    """erp_construction_date 가 비면 scheduled_date 를 기준일로 쓴다(스펙 §3.3)."""
    _login_as_admin(client, "link-fallback-admin")
    as_id = _create_order()
    ref_id = _create_order(status="CONSTRUCTION")
    db_session.get(Order, ref_id).scheduled_date = "2026-09-01"
    db_session.commit()

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _link(as_id)["ref_date"] == "2026-09-01"


def test_link_to_self_is_rejected(client):
    """자기 자신을 기준으로 매칭하면 400 — 드리프트 판정이 성립하지 않는다."""
    _login_as_admin(client, "link-self-admin")
    as_id = _create_order(construction_date="2026-08-05")

    res = _post(client, as_id, {"action": "link", "ref_order_id": as_id})

    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _link(as_id) is None


def test_link_to_missing_order_is_404(client):
    _login_as_admin(client, "link-404-admin")
    as_id = _create_order()

    res = _post(client, as_id, {"action": "link", "ref_order_id": 999999})

    assert res.status_code == 404 and res.get_json()["success"] is False
    assert _link(as_id) is None


def test_link_to_deleted_order_is_404(client):
    """삭제된 주문은 기준이 될 수 없다 — 곧바로 ref_gone 이 될 링크를 만들지 않는다."""
    _login_as_admin(client, "link-deleted-admin")
    as_id = _create_order()
    ref_id = _create_order(status="DELETED", construction_date="2026-08-05")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 404 and res.get_json()["success"] is False
    assert _link(as_id) is None


def test_link_without_ref_order_id_is_400(client):
    _login_as_admin(client, "link-noref-admin")
    as_id = _create_order()

    assert _post(client, as_id, {"action": "link"}).status_code == 400
    assert _post(client, as_id, {"action": "nope"}).status_code == 400
    assert _link(as_id) is None


def test_link_to_dateless_order_is_400(client):
    """시공일이 없는 주문은 비교 기준선(D0)이 없다 — 링크를 만들지 않는다."""
    _login_as_admin(client, "link-nodate-admin")
    as_id = _create_order()
    ref_id = _create_order(status="CONSTRUCTION")

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _link(as_id) is None


# ---------------------------------------------------------------------------
# relink · ack
# ---------------------------------------------------------------------------


def _linked_pair(client, prefix: str, *, d0: str = "2026-08-05", visit_date=None):
    """링크가 걸린 (AS 주문, 기준 주문) 한 쌍을 만든다."""
    _login_as_admin(client, f"{prefix}-admin")
    as_id = _create_order(visit_date=visit_date)
    ref_id = _create_order(status="CONSTRUCTION", construction_date=d0)
    assert _post(client, as_id, {"action": "link", "ref_order_id": ref_id}).status_code == 200
    return as_id, ref_id


def test_relink_without_link_is_409(client):
    """링크가 없으면 재적용할 대상이 없다 — 409(무결성)."""
    _login_as_admin(client, "relink-none-admin")
    as_id = _create_order()

    res = _post(client, as_id, {"action": "relink"})

    assert res.status_code == 409 and res.get_json()["success"] is False


def test_ack_without_link_is_409(client):
    _login_as_admin(client, "ack-none-admin")
    as_id = _create_order()

    assert _post(client, as_id, {"action": "ack"}).status_code == 409


def test_relink_adopts_current_ref_date_without_new_log(client):
    """재적용은 D0 를 현재 기준일로 끌어올린다. 날짜 기록은 방문일 저장 경로 소관이라 무로그."""
    as_id, ref_id = _linked_pair(client, "relink", visit_date="2026-08-05")
    _set_construction_date(ref_id, "2026-08-19")

    res = _post(client, as_id, {"action": "relink"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    assert _link(as_id)["ref_date"] == "2026-08-19"
    assert _link(as_id)["ack_ref_date"] is None
    assert data["link"]["ref_date"] == "2026-08-19"
    assert data["drift"]["state"] == "ok"
    assert len(_system_texts(as_id)) == 1  # link 1건 그대로 — relink 는 노이즈를 남기지 않는다


def test_ack_records_current_ref_date_without_new_log(client):
    """무시는 현재 기준일을 ack_ref_date 로 굳혀 경고만 숨긴다(D0 는 그대로)."""
    as_id, ref_id = _linked_pair(client, "ack")
    _set_construction_date(ref_id, "2026-08-19")

    res = _post(client, as_id, {"action": "ack"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    saved = _link(as_id)
    assert saved["ack_ref_date"] == "2026-08-19"
    assert saved["ref_date"] == "2026-08-05"  # 기준선은 유지
    assert data["drift"]["state"] == "acked"
    assert len(_system_texts(as_id)) == 1


# ---------------------------------------------------------------------------
# unlink
# ---------------------------------------------------------------------------


def test_unlink_removes_key_and_logs_once(client):
    """해제는 키 자체를 지우고(스펙 §3.1) 타임라인에 해제 사실을 남긴다."""
    as_id, ref_id = _linked_pair(client, "unlink")

    res = _post(client, as_id, {"action": "unlink"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    assert data["cleared"] is True and data["link"] is None
    assert data["drift"]["state"] == "none"
    assert _link(as_id) is None
    assert "schedule_link" not in (_sd(as_id)["schedule"]["as_visit"])
    assert _system_texts(as_id) == [
        f"기준 일정 매칭: 주문 #{ref_id} (2026-08-05)", "기준 일정 매칭 해제"]


def test_unlink_twice_is_idempotent(client):
    """두 번째 해제는 무변경 성공 — cleared=False 이고 해제 로그가 중복되지 않는다."""
    as_id, _ref_id = _linked_pair(client, "unlink-twice")
    assert _post(client, as_id, {"action": "unlink"}).status_code == 200

    res = _post(client, as_id, {"action": "unlink"})
    data = res.get_json()

    assert res.status_code == 200 and data["success"] is True
    assert data["cleared"] is False and data["link"] is None
    assert _system_texts(as_id).count("기준 일정 매칭 해제") == 1


def test_link_after_unlink_starts_fresh(client):
    """해제 후 재매칭은 새 링크(ack 초기화) — 잔여 상태가 남지 않는다."""
    as_id, ref_id = _linked_pair(client, "relink-after-unlink")
    _set_construction_date(ref_id, "2026-08-19")
    assert _post(client, as_id, {"action": "ack"}).status_code == 200
    assert _post(client, as_id, {"action": "unlink"}).status_code == 200

    res = _post(client, as_id, {"action": "link", "ref_order_id": ref_id})

    assert res.status_code == 200, res.get_data(as_text=True)
    saved = _link(as_id)
    assert saved["ref_date"] == "2026-08-19" and saved["ack_ref_date"] is None
