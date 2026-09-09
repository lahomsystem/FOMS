"""AS 영업 전달 배정 API 계약 테스트 (POST /api/orders/<id>/sales-delivery).

스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md §2·§5.
권한(비로그인·ERP 편집)·서버 재조회(클라 ref_date 불채택)·8개 액션의 sd 반영·
AS 타임라인 system 항목이 4개 액션에서만 생기는지·감사 라벨 등재·ERP 폼 PUT 생존을
고정한다.
"""

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User

_TODAY = date.today().strftime("%Y-%m-%d")


def _make_user(username: str, *, role: str = "ADMIN", team: str = "CS",
               name: str = "전달 배정 사용자") -> int:
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


def _login_as_admin(client, username: str = "sd-admin") -> int:
    user_id = _make_user(username, role="ADMIN", name="전달 배정 관리자")
    _login(client, user_id)
    return user_id


def _create_order(*, status: str = "AS_RECEIVED", manager_name: str = "Alice",
                  sd_measurement: str | None = None, manager_in_sd: str | None = None) -> int:
    """전달 건/기준 실측 주문 공용 시드.

    ``sd_measurement`` 를 주면 ``schedule.measurement.date`` 폴백 경로를 태운다
    (``order_schedule_dates`` 행은 :func:`_add_measurement_row` 로 따로 붙인다).
    """
    schedule = {"measurement": {"date": sd_measurement}} if sd_measurement else {}
    parties = {"manager": {"name": manager_in_sd}} if manager_in_sd else {}
    order = Order(
        received_date=_TODAY,
        customer_name="전달 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name=manager_name,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": {},
                         "schedule": schedule, "parties": parties},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _add_measurement_row(order_id: int, value: str) -> None:
    """실측 일정 SSOT(``order_schedule_dates.kind='measurement'``) 행을 붙인다."""
    db_session.add(OrderScheduleDate(
        order_id=order_id, kind="measurement", date=value, source="test"))
    db_session.commit()


def _sd(order_id: int) -> dict:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data


def _shipment(order_id: int) -> dict:
    return _sd(order_id).get("shipment") or {}


def _link(order_id: int):
    return _shipment(order_id).get("sales_delivery_link")


def _system_texts(order_id: int) -> list[str]:
    log = _shipment(order_id).get("as_log") or []
    return [e["text"] for e in log if e.get("type") == "system"]


def _post(client, order_id: int, payload: dict):
    return client.post(f"/api/orders/{order_id}/sales-delivery", json=payload)


def _assigned_pair(client, prefix: str, *, d0: str = "2026-09-15"):
    """배정이 걸린 (전달 건, 기준 실측 주문) 한 쌍을 만든다."""
    _login_as_admin(client, f"{prefix}-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE", manager_name="박실측")
    _add_measurement_row(ref_id, d0)
    assert _post(client, as_id, {"action": "assign", "ref_order_id": ref_id}).status_code == 200
    return as_id, ref_id


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


def test_sales_delivery_requires_login(client):
    """비로그인은 로그인 페이지로 리다이렉트 — 배정이 만들어지지 않는다."""
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE")
    _add_measurement_row(ref_id, "2026-09-15")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": ref_id})

    assert res.status_code == 302
    assert _link(as_id) is None


def test_sales_delivery_requires_erp_edit_permission(client):
    """읽기만 가능한 팀(도면)은 403 — 쓰기는 ERP 편집 권한을 요구한다(스펙 §5)."""
    _login(client, _make_user("sd-no-edit", role="STAFF", team="DRAWING", name="도면팀"))
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE")
    _add_measurement_row(ref_id, "2026-09-15")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": ref_id})

    assert res.status_code == 403 and res.get_json()["success"] is False
    assert _link(as_id) is None


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------


def test_assign_writes_structure_and_single_system_log(client):
    """assign 은 스펙 §2.1 스키마를 sd 에 쓰고 system 항목을 정확히 1건만 남긴다."""
    user_id = _login_as_admin(client, "sd-assign-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE", manager_name="Bob", manager_in_sd="박실측")
    _add_measurement_row(ref_id, "2026-09-15")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": ref_id})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)
    assert data["success"] is True

    saved = _link(as_id)
    assert saved == data["link"]
    assert saved["ref_order_id"] == ref_id
    assert saved["ref_kind"] == "measurement"
    assert saved["ref_date"] == "2026-09-15"
    assert saved["ref_manager"] == "박실측"
    assert saved["status"] == "assigned"
    assert saved["ack_ref_date"] is None and saved["delivered_at"] is None
    assert saved["assigned_by_user_id"] == user_id and saved["assigned_by"] == "전달 배정 관리자"
    assert saved["source"] == "as_sales_delivery_modal"

    assert data["display_state"] == "assigned" and data["method"] == "sales"
    assert data["drift"]["state"] == "ok" and data["drift"]["ref_order_id"] == ref_id
    assert _system_texts(as_id) == [f"전달 배정: 실측 주문 #{ref_id} (2026-09-15)"]


def test_assign_ignores_client_ref_date_and_manager(client):
    """클라가 보낸 ref_date/ref_manager 는 stale 일 수 있다 — 서버 재조회 값이 이긴다."""
    _login_as_admin(client, "sd-stale-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE", manager_name="Bob", manager_in_sd="박실측")
    _add_measurement_row(ref_id, "2026-09-22")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": ref_id,
                                "ref_date": "2026-09-01", "ref_manager": "가짜담당"})
    assert res.status_code == 200, res.get_data(as_text=True)

    saved = _link(as_id)
    assert saved["ref_date"] == "2026-09-22"
    assert saved["ref_manager"] == "박실측"
    assert res.get_json()["drift"]["ref_current_date"] == "2026-09-22"


def test_assign_uses_earliest_row_and_sd_fallback(client):
    """실측일 SSOT 는 order_schedule_dates 최솟값, 행이 없을 때만 sd 폴백(스펙 §5)."""
    _login_as_admin(client, "sd-earliest-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE", sd_measurement="2026-12-01")
    _add_measurement_row(ref_id, "2026-10-20")
    _add_measurement_row(ref_id, "2026-10-05")

    assert _post(client, as_id, {"action": "assign", "ref_order_id": ref_id}).status_code == 200
    assert _link(as_id)["ref_date"] == "2026-10-05"

    fallback_id = _create_order(status="MEASURE", sd_measurement="2026-11-11")
    assert _post(client, as_id, {"action": "reassign",
                                 "ref_order_id": fallback_id}).status_code == 200
    assert _link(as_id)["ref_date"] == "2026-11-11"


def test_assign_to_self_is_rejected(client):
    """자기 자신에게 배정하면 400 — 동선 배정이 성립하지 않는다."""
    _login_as_admin(client, "sd-self-admin")
    as_id = _create_order()
    _add_measurement_row(as_id, "2026-09-15")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": as_id})

    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _link(as_id) is None


def test_assign_to_missing_or_deleted_order_is_404(client):
    """없는·삭제된 기준 주문은 404 — 곧바로 ref_gone 이 될 배정을 만들지 않는다."""
    _login_as_admin(client, "sd-404-admin")
    as_id = _create_order()
    gone_id = _create_order(status="MEASURE")
    _add_measurement_row(gone_id, "2026-09-15")
    db_session.get(Order, gone_id).status = "DELETED"
    db_session.commit()

    assert _post(client, as_id, {"action": "assign", "ref_order_id": gone_id}).status_code == 404
    assert _post(client, as_id, {"action": "assign",
                                 "ref_order_id": gone_id + 100000}).status_code == 404
    assert _link(as_id) is None


def test_assign_without_ref_or_bad_action_is_400(client):
    _login_as_admin(client, "sd-noref-admin")
    as_id = _create_order()

    assert _post(client, as_id, {"action": "assign"}).status_code == 400
    assert _post(client, as_id, {"action": "nope"}).status_code == 400
    assert _post(client, as_id, {}).status_code == 400
    assert _link(as_id) is None


def test_assign_to_dateless_order_is_400(client):
    """실측일이 없는 주문은 태울 동선이 없다 — 배정을 만들지 않는다."""
    _login_as_admin(client, "sd-nodate-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE")

    res = _post(client, as_id, {"action": "assign", "ref_order_id": ref_id})

    assert res.status_code == 400 and res.get_json()["success"] is False
    assert _link(as_id) is None


# ---------------------------------------------------------------------------
# reassign · ack
# ---------------------------------------------------------------------------


def test_reassign_and_ack_without_link_are_409(client):
    """배정이 없으면 재배정·확인할 대상이 없다 — 409(무결성)."""
    _login_as_admin(client, "sd-409-admin")
    as_id = _create_order()
    ref_id = _create_order(status="MEASURE")
    _add_measurement_row(ref_id, "2026-09-15")

    assert _post(client, as_id, {"action": "reassign",
                                 "ref_order_id": ref_id}).status_code == 409
    assert _post(client, as_id, {"action": "ack"}).status_code == 409
    assert _post(client, as_id, {"action": "deliver"}).status_code == 409
    assert _post(client, as_id, {"action": "undeliver"}).status_code == 409
    assert _link(as_id) is None


def test_reassign_replaces_link_and_resets_ack_without_log(client):
    """재배정은 기준을 갈아끼우고 ack 를 리셋한다. 정정이라 타임라인엔 남기지 않는다."""
    as_id, _ref_id = _assigned_pair(client, "sd-reassign")
    assert _post(client, as_id, {"action": "ack"}).status_code == 200
    other_id = _create_order(status="MEASURE")
    _add_measurement_row(other_id, "2026-09-25")

    res = _post(client, as_id, {"action": "reassign", "ref_order_id": other_id})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    saved = _link(as_id)
    assert saved["ref_order_id"] == other_id and saved["ref_date"] == "2026-09-25"
    assert saved["ack_ref_date"] is None
    assert data["drift"]["state"] == "ok"
    assert len(_system_texts(as_id)) == 1  # assign 1건 그대로


def test_ack_records_current_ref_date(client):
    """확인은 현재 실측일을 ack_ref_date 로 굳혀 경고만 숨긴다(D0 는 그대로, 무로그)."""
    as_id, ref_id = _assigned_pair(client, "sd-ack")
    _add_measurement_row(ref_id, "2026-09-11")  # 실측일이 앞당겨짐(최솟값 이동)

    res = _post(client, as_id, {"action": "ack"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    saved = _link(as_id)
    assert saved["ack_ref_date"] == "2026-09-11"
    assert saved["ref_date"] == "2026-09-15"
    assert data["drift"]["state"] == "acked"
    assert len(_system_texts(as_id)) == 1


# ---------------------------------------------------------------------------
# unassign (멱등)
# ---------------------------------------------------------------------------


def test_unassign_removes_key_and_logs_once(client):
    """해제는 키 자체를 지우고 타임라인에 해제 사실을 남긴다."""
    as_id, ref_id = _assigned_pair(client, "sd-unassign")

    res = _post(client, as_id, {"action": "unassign"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    assert data["link"] is None and data["display_state"] == "unassigned"
    assert data["drift"]["state"] == "none"
    assert "sales_delivery_link" not in _shipment(as_id)
    assert _system_texts(as_id) == [
        f"전달 배정: 실측 주문 #{ref_id} (2026-09-15)", "전달 배정 해제"]


def test_unassign_twice_is_idempotent(client):
    """두 번째 해제는 무변경 성공 — sd 도 REV 도 그대로다(멱등 계약)."""
    as_id, _ref_id = _assigned_pair(client, "sd-unassign-twice")
    assert _post(client, as_id, {"action": "unassign"}).status_code == 200
    db_session.expire_all()
    before = db_session.get(Order, as_id)
    before_sd, before_rev = dict(before.structured_data), before.mutation_version

    res = _post(client, as_id, {"action": "unassign"})
    data = res.get_json()
    assert res.status_code == 200 and data["success"] is True
    assert data["link"] is None

    db_session.expire_all()
    after = db_session.get(Order, as_id)
    assert after.structured_data == before_sd
    assert after.mutation_version == before_rev
    assert _system_texts(as_id).count("전달 배정 해제") == 1


# ---------------------------------------------------------------------------
# deliver · undeliver
# ---------------------------------------------------------------------------


def test_deliver_then_undeliver(client):
    """전달 완료는 상태·시각·행위자를 남기고, 되돌리기는 흔적을 지우되 로그는 안 남긴다."""
    as_id, _ref_id = _assigned_pair(client, "sd-deliver")

    res = _post(client, as_id, {"action": "deliver"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)
    saved = _link(as_id)
    assert saved["status"] == "delivered" and saved["delivered_at"]
    assert saved["delivered_by"] == "전달 배정 관리자"
    assert data["display_state"] == "delivered"
    assert _system_texts(as_id)[-1] == "전달 완료"

    res2 = _post(client, as_id, {"action": "undeliver"})
    assert res2.status_code == 200, res2.get_data(as_text=True)
    back = _link(as_id)
    assert back["status"] == "assigned"
    assert back["delivered_at"] is None and back["delivered_by"] is None
    assert res2.get_json()["display_state"] == "assigned"
    assert _system_texts(as_id).count("전달 완료") == 1  # undeliver 는 무로그


# ---------------------------------------------------------------------------
# parcel · parcel_cancel
# ---------------------------------------------------------------------------


def test_parcel_clears_link_and_records_tracking(client):
    """택배 전환은 배정을 지우고(유령 배정 방지) 송장 정보를 남긴다."""
    as_id, _ref_id = _assigned_pair(client, "sd-parcel")

    res = _post(client, as_id, {"action": "parcel", "carrier": "CJ대한통운",
                                "tracking_no": "1234567890"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    assert data["method"] == "parcel" and data["display_state"] == "parcel"
    assert data["link"] is None and _link(as_id) is None
    parcel = _shipment(as_id)["sales_delivery_parcel"]
    assert parcel["carrier"] == "CJ대한통운" and parcel["tracking_no"] == "1234567890"
    assert parcel["sent_by"] == "전달 배정 관리자" and parcel["sent_at"]
    assert _system_texts(as_id)[-1] == "택배 전환: CJ대한통운 1234567890"


def test_parcel_cancel_returns_to_sales(client):
    """택배 전환 취소는 method 만 되돌린다(무로그, 배정은 되살아나지 않는다)."""
    as_id, _ref_id = _assigned_pair(client, "sd-parcel-cancel")
    assert _post(client, as_id, {"action": "parcel"}).status_code == 200

    res = _post(client, as_id, {"action": "parcel_cancel"})
    data = res.get_json()
    assert res.status_code == 200, res.get_data(as_text=True)

    assert data["method"] == "sales" and data["display_state"] == "unassigned"
    assert "sales_delivery_parcel" not in _shipment(as_id)
    assert _system_texts(as_id).count("택배 전환") == 1


def test_timeline_logs_only_four_actions(client):
    """system 항목은 assign·unassign·deliver·parcel 4개에서만 생긴다(스펙 §5)."""
    as_id, ref_id = _assigned_pair(client, "sd-timeline")
    _add_measurement_row(ref_id, "2026-09-11")

    for payload in ({"action": "ack"},
                    {"action": "reassign", "ref_order_id": ref_id},
                    {"action": "deliver"},
                    {"action": "undeliver"},
                    {"action": "parcel"},
                    {"action": "parcel_cancel"},
                    {"action": "unassign"}):
        assert _post(client, as_id, payload).status_code == 200, payload

    assert _system_texts(as_id) == [
        f"전달 배정: 실측 주문 #{ref_id} (2026-09-15)",
        "전달 완료",
        "택배 전환",
    ]  # unassign 은 이미 택배 전환이 링크를 지워 무변경 → 로그 없음


# ---------------------------------------------------------------------------
# 감사 라벨 · ERP 폼 PUT 생존
# ---------------------------------------------------------------------------


def test_audit_action_label_is_registered(client):
    """감사 action 은 라벨이 없으면 감사 화면이 빈다 — 등재를 계약으로 고정한다."""
    from foms.services.audit_message_display import ACTION_LABELS, describe_order_action

    assert ACTION_LABELS["AS_SALES_DELIVERY_CHANGED"] == "AS 전달 배정"

    as_id, _ref_id = _assigned_pair(client, "sd-audit")
    sentence = describe_order_action(order_id=as_id, action="AS_SALES_DELIVERY_CHANGED",
                                     note="배정")
    assert "AS 전달 배정" in sentence and "AS_SALES_DELIVERY_CHANGED" not in sentence


def test_erp_form_put_cannot_clobber_sales_delivery(client):
    """폼의 stale shipment 스냅샷이 배정·택배 수단을 지우지 못한다(서버 전용 키 등재).

    deep-merge 는 shipment 를 incoming 으로 병합하므로, 등재가 없으면 편집 탭 한 번
    저장에 방금 만든 배정이 통째로 사라진다(스펙 §2.3).
    """
    as_id, ref_id = _assigned_pair(client, "sd-form-put")
    assert _post(client, as_id, {"action": "parcel", "carrier": "CJ"}).status_code == 200
    assert _post(client, as_id, {"action": "parcel_cancel"}).status_code == 200
    assert _post(client, as_id, {"action": "assign", "ref_order_id": ref_id}).status_code == 200
    saved = dict(_link(as_id))

    res = client.put(f"/api/orders/{as_id}/structured", json={"structured_data": {
        "workflow": {"stage": "AS_RECEIVED"},
        "shipment": {"as_content": "문틀"},  # 배정 3키가 없는 페이지 로드 스냅샷
        "parties": {"customer": {"name": "전달 고객", "phone": "010-1234-5678"}},
        "items": [{"product_name": "붙박이장"}],
        "site": {"address_full": "Seoul", "address_main": "Seoul", "address_detail": ""},
    }})
    assert res.status_code == 200 and res.get_json()["success"] is True

    assert _link(as_id) == saved
    assert _shipment(as_id)["sales_delivery_method"] == "sales"
