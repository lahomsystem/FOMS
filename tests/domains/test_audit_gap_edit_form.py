"""주문수정 폼(POST /edit/<id>) 변경 원장 배선 계약 (AUDIT-GAP-01 T3).

2026-08-26 이전 이 라우트는 필드별 old/new 를 모아 놓고도 **한글 자유문장 한 줄**만 남겼다
(``log_access(log_message, user_id)``). ``security_logs`` 의 구조화 컬럼은 전부 NULL 이고
``order_field_changes`` 행은 0이라, 감사 화면의 필터·집계·되돌리기 어디에도 걸리지 않았다.

여기서 고정하는 계약:

1. **ERP 주문의 sd 변경은 canonical sd 경로로** — 실측일은 ``schedule.measurement.date`` 로
   남는다(평면 ``measurement_date`` 가 아니다). ``PUT /structured`` 와 같은 경로여야 감사
   화면 필터가 두 저장 경로를 한 벌로 잡는다.
2. **sd 쌍둥이가 없는 평면 컬럼만** 점 없는 컬럼명으로 남는다(지방 체크리스트·수납장·
   플래그 3종 등). 플래그 path 는 ``PUT /structured``(ORDER-FLAG-01)와 같은 이름이라
   감사 화면 필터가 두 화면을 다 잡는다.
2b. **권한 게이트가 이긴다** — 무권한 사용자의 저장은 ``is_regional`` 을 기존값으로 되돌리므로
   원장에도 행이 생기지 않는다(허위 '변경' 금지).
3. ``is_cabinet`` 은 ``cabinet_status`` 를 파생 변경하므로 **둘 다** 남는다.
4. 무변경 저장은 행 0 — 저장 버튼만 눌러도 쌓이면 진짜 변경이 묻힌다.
5. 헤더(``security_logs``)에 ``action``·``target_type``·``target_id``·
   ``detail['change_set']`` 이 채워진다(원장과 잇는 유일한 열쇠).

``path_label`` 표기는 여기서 단언하지 않는다 — 라벨 등재는 T2 소유다.
"""

from __future__ import annotations

import itertools
from typing import Any

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, SecurityLog, User

_counter = itertools.count(1)
_ADDRESS = "서울 감사구 원장로 12"
_PHONE = "010-2222-3333"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_user(*, role: str = "ADMIN", team: str | None = None) -> int:
    """행위자 1명을 만들고 id 만 돌려준다(요청 teardown 후 detach 회피)."""
    n = next(_counter)
    user = User(
        username=f"audit-gap-t3-{n}",
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"감사{n}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    """테스트 클라이언트 세션에 로그인 상태를 심는다."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _sd(
    *,
    measurement_date: str = "",
    measurement_time: str = "",
    construction_date: str = "",
) -> dict[str, Any]:
    """폼이 실제로 만드는 모양의 최소 ERP structured_data.

    ``site`` 는 **정본 모양**(full==main 합본·detail 빈값)으로 둔다 — 어긋나 있으면 저장이
    주소를 정합시키면서 ``site.address_full`` 변경이 함께 찍혀 무변경 저장 판정이 흐려진다.
    """
    return {
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "원장 고객", "phone": _PHONE}},
        "site": {"address_full": _ADDRESS, "address_main": _ADDRESS, "address_detail": ""},
        "items": [{"product_name": "붙박이장"}],
        "schedule": {
            "measurement": {"date": measurement_date, "time": measurement_time},
            "construction": {"date": construction_date},
        },
        "shipment": {},
    }


def _make_order(**overrides: Any) -> int:
    """ERP 주문 1건을 만들고 id 만 돌려준다."""
    fields: dict[str, Any] = {
        "received_date": "2026-07-01",
        "received_time": "10:00",
        "customer_name": "원장 고객",
        "phone": _PHONE,
        "address": _ADDRESS,
        "product": "붙박이장",
        "status": "RECEIVED",
        "manager_name": "담당",
        "is_erp_order": True,
        "erp_stage_code": "RECEIVED",
        "measurement_date": "",
        "measurement_time": "",
        "scheduled_date": "",
        "structured_data": _sd(),
    }
    fields.update(overrides)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order.id


def _rows(order_id: int) -> list[OrderFieldChange]:
    """해당 주문의 변경 원장 행(기록순)."""
    db_session.expire_all()
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == order_id)
        .order_by(OrderFieldChange.id.asc())
        .all()
    )


def _paths(order_id: int) -> set[str]:
    """원장에 남은 경로 집합."""
    return {row.path for row in _rows(order_id)}


def _row(order_id: int, path: str) -> OrderFieldChange | None:
    """경로 1건의 원장 행(없으면 ``None``)."""
    return next((row for row in _rows(order_id) if row.path == path), None)


def _latest_log(order_id: int) -> SecurityLog | None:
    """이 주문을 대상으로 남은 가장 최근 감사 헤더."""
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.target_type == "order", SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id.desc())
        .first()
    )


def _post(client, order_id: int, data: dict[str, Any]):
    """주문수정 폼 저장(리다이렉트를 따라가지 않는다)."""
    return client.post(f"/edit/{order_id}", data=data, follow_redirects=False)


# --------------------------------------------------------------------------- #
# 1. 갈래 1 — ERP 주문의 sd 변경은 canonical sd 경로로
# --------------------------------------------------------------------------- #
def test_measurement_date_lands_on_structured_path_not_flat_column(client):
    """실측일 변경은 ``schedule.measurement.date`` 로 남는다(평면 ``measurement_date`` 아님)."""
    _login(client, _make_user())
    order_id = _make_order(
        measurement_date="2026-07-10",
        structured_data=_sd(measurement_date="2026-07-10"),
    )

    resp = _post(client, order_id, {"measurement_date": "2026-08-01"})
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]

    row = _row(order_id, "schedule.measurement.date")
    assert row is not None, f"원장 경로: {sorted(_paths(order_id))}"
    assert (row.before_value, row.after_value) == ("2026-07-10", "2026-08-01")
    # 평면 컬럼명으로 두 번 적으면 감사 화면 필터가 반쪽만 잡는다.
    assert "measurement_date" not in _paths(order_id)


def test_construction_date_lands_on_structured_path(client):
    """시공일(폼 ``scheduled_date``)도 sd 경로 ``schedule.construction.date`` 로 남는다."""
    _login(client, _make_user())
    order_id = _make_order(
        scheduled_date="2026-07-20",
        structured_data=_sd(construction_date="2026-07-20"),
    )

    _post(client, order_id, {"scheduled_date": "2026-08-05"})

    row = _row(order_id, "schedule.construction.date")
    assert row is not None, f"원장 경로: {sorted(_paths(order_id))}"
    assert (row.before_value, row.after_value) == ("2026-07-20", "2026-08-05")
    assert "scheduled_date" not in _paths(order_id)


# --------------------------------------------------------------------------- #
# 2. 갈래 2 — sd 쌍둥이가 없는 평면 컬럼
# --------------------------------------------------------------------------- #
def test_regional_checklist_on_and_off_records_each_column_path(client):
    """지방 체크리스트는 켤 때·끌 때 모두 컬럼명 path 로 before/after 가 남는다."""
    _login(client, _make_user())
    order_id = _make_order(is_regional=True, construction_type="하우드 시공")
    regional_form = {"is_regional": "on", "construction_type": "하우드 시공"}

    # 켜기 — 폼에 실린 체크박스만 True 가 된다.
    _post(client, order_id, {
        **regional_form,
        "regional_blueprint_sent": "on",
        "measurement_completed": "on",
    })
    turned_on = _paths(order_id)
    assert {"regional_blueprint_sent", "measurement_completed"} <= turned_on
    for path in ("regional_blueprint_sent", "measurement_completed"):
        row = _row(order_id, path)
        assert (row.before_value, row.after_value) == ("False", "True"), path
    # 안 건드린 4종은 행이 없다(허위 변경 금지).
    assert "regional_cargo_sent" not in turned_on
    assert "regional_sales_order_upload" not in turned_on

    # 끄기 — 체크박스를 빼고 저장하면 해제로 기록된다.
    _post(client, order_id, {**regional_form, "measurement_completed": "on"})
    off_row = [r for r in _rows(order_id) if r.path == "regional_blueprint_sent"][-1]
    assert (off_row.before_value, off_row.after_value) == ("True", "False")


def test_flat_columns_without_structured_twin_are_recorded(client):
    """AS 접수일·상차 예정일·결제금액·주문 비고는 점 없는 컬럼명 path 로 남는다."""
    _login(client, _make_user())
    order_id = _make_order(notes="이전 비고")

    _post(client, order_id, {
        "as_received_date": "2026-08-03",
        "shipping_scheduled_date": "2026-08-09",
        "payment_amount": "1,250,000",
        "notes": "새 비고",
        "status": "MEASURED",
    })

    paths = _paths(order_id)
    assert {"as_received_date", "shipping_scheduled_date", "payment_amount",
            "order_notes", "status"} <= paths, sorted(paths)
    assert _row(order_id, "payment_amount").after_value == "1250000"
    notes_row = _row(order_id, "order_notes")
    assert (notes_row.before_value, notes_row.after_value) == ("이전 비고", "새 비고")
    # status 는 자기 축으로 남는다 — workflow.stage 로 매핑하면 두 축 어휘가 섞인다.
    assert _row(order_id, "status").after_value == "MEASURED"
    assert "notes" not in paths  # sd 의 notes(문자열 SSOT)와 다른 값이다.


def test_is_cabinet_records_derived_cabinet_status_too(client):
    """수납장 체크는 ``is_cabinet`` 과 파생값 ``cabinet_status`` 를 **둘 다** 남긴다."""
    _login(client, _make_user())
    order_id = _make_order()

    _post(client, order_id, {"is_cabinet": "on"})

    paths = _paths(order_id)
    assert {"is_cabinet", "cabinet_status"} <= paths, sorted(paths)
    assert _row(order_id, "is_cabinet").after_value == "True"
    assert _row(order_id, "cabinet_status").after_value == "RECEIVED"

    # 해제하면 파생값도 함께 지워진 사실이 남는다.
    _post(client, order_id, {})
    cleared = [r for r in _rows(order_id) if r.path == "cabinet_status"][-1]
    assert (cleared.before_value, cleared.after_value) == ("RECEIVED", None)
    assert cleared.op == "clear"


def test_order_flags_are_recorded_with_the_same_paths_as_structured_put(client):
    """지방주문·시공구분·자가실측 3종도 컬럼명 path 로 남는다(PUT 과 같은 이름)."""
    _login(client, _make_user())
    order_id = _make_order()

    resp = _post(client, order_id, {
        "is_regional": "on",
        "construction_type": "하우드 시공",
        "is_self_measurement": "on",
    })
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]

    paths = _paths(order_id)
    assert {"is_regional", "construction_type", "is_self_measurement"} <= paths, sorted(paths)
    assert (_row(order_id, "is_regional").before_value,
            _row(order_id, "is_regional").after_value) == ("False", "True")
    assert (_row(order_id, "is_self_measurement").before_value,
            _row(order_id, "is_self_measurement").after_value) == ("False", "True")
    ct_row = _row(order_id, "construction_type")
    assert (ct_row.before_value, ct_row.after_value) == (None, "하우드 시공")
    assert ct_row.op == "add"


def test_order_flags_unchanged_save_records_no_rows(client):
    """이미 켜진 플래그를 그대로 다시 저장하면 행 0(컬럼 NULL→False 허위 행 포함 금지)."""
    _login(client, _make_user())
    order_id = _make_order(
        is_regional=True,
        construction_type="하우드 시공",
        is_self_measurement=True,
    )

    resp = _post(client, order_id, {
        "is_regional": "on",
        "construction_type": "하우드 시공",
        "is_self_measurement": "on",
    })
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]

    # 저장이 살아서 값을 유지한 결과여야 한다(죽은 저장의 공짜 0행이 아니다).
    db_session.expire_all()
    assert db_session.get(Order, order_id).is_regional is True
    assert _rows(order_id) == []


def test_flag_gate_denies_regional_change_so_no_ledger_row(client):
    """무권한(비 CS·비 ADMIN) 저장은 ``is_regional`` 을 기존값으로 되돌린다 → 행 0.

    ORDER-FLAG-01 게이트는 거부(403)가 아니라 **무시**다. 값이 안 바뀌었으니 원장에도 남을
    것이 없다 — 여기서 행이 생기면 그건 '바뀌지 않은 것을 바뀌었다고 적는' 허위 기록이다.
    게이트가 없는 자가실측은 같은 저장에서 정상 기록되므로, 저장 자체는 살아 있었음이 함께 증명된다.
    """
    # 영업팀 MANAGER: ERP 주문 수정은 되지만 플래그 토글 권한은 없다.
    _login(client, _make_user(role="MANAGER", team="SALES"))
    order_id = _make_order()

    resp = _post(client, order_id, {
        "is_regional": "on",
        "construction_type": "하우드 시공",
        "is_self_measurement": "on",
    })
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]

    db_session.expire_all()
    assert db_session.get(Order, order_id).is_regional is not True
    paths = _paths(order_id)
    assert "is_regional" not in paths, sorted(paths)
    assert "construction_type" not in paths
    # 게이트 밖 값은 같은 저장에서 정상 기록된다(저장이 죽어서 행이 없는 게 아니다).
    assert "is_self_measurement" in paths


# --------------------------------------------------------------------------- #
# 3. 허위 기록 0 · 경로 2벌 금지
# --------------------------------------------------------------------------- #
def test_save_without_changes_records_no_rows(client):
    """무변경 저장은 원장 행 0 — 저장 버튼만 눌러도 쌓이면 진짜 변경이 묻힌다."""
    _login(client, _make_user())
    order_id = _make_order(
        measurement_date="2026-07-10",
        scheduled_date="2026-07-20",
        structured_data=_sd(measurement_date="2026-07-10", construction_date="2026-07-20"),
    )

    resp = _post(client, order_id, {})
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]
    assert _rows(order_id) == []


def test_customer_name_is_not_recorded_as_flat_path(client):
    """고객명은 평면 path 로 남기지 않는다 — sd 쌍둥이가 있어 경로가 2벌이 되면 필터가 반쪽만 잡는다."""
    _login(client, _make_user())
    order_id = _make_order()

    resp = _post(client, order_id, {"customer_name": "바뀐 고객"})
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]
    # 저장이 실제로 일어났는지부터 확인한다 — 500 으로 죽은 저장은 "행이 없다"를 공짜로 통과시킨다.
    db_session.expire_all()
    assert db_session.get(Order, order_id).customer_name == "바뀐 고객"

    paths = _paths(order_id)
    assert "customer_name" not in paths, sorted(paths)
    assert "phone" not in paths
    assert "manager_name" not in paths
    assert "product" not in paths


# --------------------------------------------------------------------------- #
# 4. 감사 헤더 — 구조화 컬럼 + change_set 조인 열쇠
# --------------------------------------------------------------------------- #
def test_audit_header_carries_structured_columns_and_change_set(client):
    """헤더에 ``action``·``target_id``·``detail['change_set']`` 이 채워지고 원장과 이어진다."""
    user_id = _make_user()
    _login(client, user_id)
    order_id = _make_order()

    _post(client, order_id, {"as_completed_date": "2026-08-12"})

    log = _latest_log(order_id)
    assert log is not None
    assert log.action == "ORDER_FIELD_UPDATED"
    assert log.target_type == "order"
    assert log.target_id == order_id
    assert log.user_id == user_id
    change_set = (log.detail or {}).get("change_set")
    assert change_set, log.detail
    # 관리자 감사 화면은 이 값으로 헤더↔원장을 조인한다.
    rows = _rows(order_id)
    assert rows and {row.change_set_id for row in rows} == {change_set}
    assert rows[0].actor_user_id == user_id
    # 사람이 읽는 한글 문장은 대체가 아니라 유지다.
    assert "수정" in (log.message or "")


def test_audit_header_message_is_preserved_on_unchanged_save(client):
    """무변경 저장도 헤더는 남는다(문장 유지) — 원장만 비어 있다."""
    _login(client, _make_user())
    order_id = _make_order(
        measurement_date="2026-07-10",
        structured_data=_sd(measurement_date="2026-07-10"),
    )

    _post(client, order_id, {})

    log = _latest_log(order_id)
    assert log is not None
    assert "변경내용 없음" in (log.message or "")
    assert (log.detail or {}).get("change_count") == 0


# --------------------------------------------------------------------------- #
# 6. 신원 컬럼(고객명·전화)의 정본 정합 — 2026-09-02
#
# 이 폼은 flat ``customer_name``·``phone`` 만 쓰고 sd ``parties`` 는 건드리지 않았다.
# 결과 두 가지:
#   * 전화 변경이 원장에 **아무 흔적도 남지 않았다**(_LEDGER_FLAT_PATHS 에도 없고,
#     sd diff 가 싣는다는 전제였는데 sd 를 안 고쳤다).
#   * flat 만 새 값이 되어 정본과 어긋났고, 그 어긋남은 방향을 알 수 없는 채 쌓였다
#     (운영 48건). 네이버 자동 매칭이 이 두 컬럼을 축으로 쓰다가 사고가 났다.
# --------------------------------------------------------------------------- #
def test_phone_change_lands_on_structured_path(client):
    """전화 변경은 ``parties.customer.phone`` 로 원장에 남는다."""
    _login(client, _make_user())
    order_id = _make_order()

    resp = _post(client, order_id, {"phone": "010-9999-0000"})
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:400]

    row = _row(order_id, "parties.customer.phone")
    assert row is not None, f"원장 경로: {sorted(_paths(order_id))}"
    assert (row.before_value, row.after_value) == (_PHONE, "010-9999-0000")


def test_phone_change_keeps_flat_column_and_structured_together(client):
    """저장 뒤 flat 컬럼과 정본(sd)이 같은 값이어야 한다."""
    _login(client, _make_user())
    order_id = _make_order()

    _post(client, order_id, {"phone": "010-9999-0000"})

    db_session.expire_all()
    order = db_session.query(Order).get(order_id)
    assert order.phone == "010-9999-0000"
    assert order.structured_data["parties"]["customer"]["phone"] == "010-9999-0000"


def test_customer_name_change_lands_on_structured_path(client):
    """고객명 변경도 ``parties.customer.name`` 로 남고 두 자리가 같이 움직인다."""
    _login(client, _make_user())
    order_id = _make_order()

    _post(client, order_id, {"customer_name": "바뀐 고객"})

    row = _row(order_id, "parties.customer.name")
    assert row is not None, f"원장 경로: {sorted(_paths(order_id))}"
    assert (row.before_value, row.after_value) == ("원장 고객", "바뀐 고객")
    db_session.expire_all()
    order = db_session.query(Order).get(order_id)
    assert order.customer_name == "바뀐 고객"
    assert order.structured_data["parties"]["customer"]["name"] == "바뀐 고객"


def test_partial_save_does_not_push_stale_flat_value_into_structured(client):
    """폼이 안 보낸 칸의 기본값은 **정본** 이다 — 옛 flat 값이 정본을 덮으면 안 된다.

    운영에 이미 어긋난 주문이 130건 있다(flat 이 옛 번호, sd 가 새 번호). 그 상태에서
    다른 칸만 고치는 저장 한 번이 옛 번호를 정본으로 되돌려 쓰면, 알림톡 발송처럼 sd 를
    보는 경로까지 옛 번호로 끌려간다.
    """
    _login(client, _make_user())
    sd = _sd()
    sd["parties"]["customer"]["phone"] = "010-7777-8888"  # 정본 = 새 번호
    order_id = _make_order(phone="010-1111-2222", structured_data=sd)  # flat = 옛 번호

    # 전화 칸을 아예 안 보내는 저장(접수시간만 고친다)
    _post(client, order_id, {"received_time": "11:00"})

    db_session.expire_all()
    order = db_session.query(Order).get(order_id)
    assert order.structured_data["parties"]["customer"]["phone"] == "010-7777-8888"
    assert order.phone == "010-7777-8888"
    assert _row(order_id, "parties.customer.phone") is None


def test_edit_form_prefills_customer_from_structured_not_stale_column(client):
    """편집 폼이 보여주는 값은 정본이어야 한다 — 옛 flat 값을 그대로 띄우면
    담당자가 그걸 보고 저장해 어긋남이 정본 쪽으로 되돌아간다."""
    _login(client, _make_user())
    sd = _sd()
    sd["parties"]["customer"]["phone"] = "010-7777-8888"
    order_id = _make_order(phone="010-1111-2222", structured_data=sd)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)
    assert "010-7777-8888" in html
    assert "010-1111-2222" not in html
