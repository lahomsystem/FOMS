"""AUDIT-GAP-01: 구조화 저장(PUT)이 건드리는 평면 컬럼의 변경 원장 계약 테스트.

``PUT /api/orders/<id>/structured`` 는 ``structured_data`` 밖의 평면 컬럼도 함께 저장한다.
그 중 **자가실측·주문 비고·접수일·접수시간** 4개는 2026-08-26 이전에 어디에도 기록이 남지
않았다(``diff_structured`` 는 ``structured_data`` 만 본다).

여기서 고정하는 것 3가지.

* **바뀌면 남는다**: 4개 각각이 ``order_field_changes`` 에 before/after 와 함께 실린다.
* **안 바뀌면 안 남는다**: 같은 값으로 저장하면 행이 생기지 않는다 — 저장 버튼만 눌러도
  쌓이면 진짜 변경이 묻힌다. 빈값(``None``)과 빈 문자열은 같은 뜻이다.
* **경로가 겹치지 않는다**: ``Order.notes`` 컬럼은 ``order_notes`` 로 적는다. ``notes`` 는
  ``structured_data`` 쪽 비고가 이미 쓰고 있는 경로라, 같이 쓰면 서로 다른 두 필드가 한
  이력으로 합쳐진다.

라벨(``path_label``) 단언은 여기 없다 — 라벨 등재는 별도 task 소유다.
"""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, User


# --------------------------------------------------------------------------
# 픽스처 (tests/domains/test_order_flag_permissions.py 와 같은 패턴)
# --------------------------------------------------------------------------
def _login(client, username, role="ADMIN", team="CS"):
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
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = username
        sess["role"] = role
    return user.id


def _valid_sd(**overrides):
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
    }
    sd.update(overrides)
    return sd


def _create_order(**cols):
    sd = cols.pop("structured_data", None)
    order = Order(
        received_date="2026-08-26",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=sd if sd is not None else _valid_sd(),
    )
    for key, value in cols.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.expire_all()
    return db_session.get(Order, oid)


def _ledger(oid, path):
    db_session.expire_all()
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == oid, OrderFieldChange.path == path)
        .order_by(OrderFieldChange.id)
        .all()
    )


def _put(client, oid, **payload):
    body = {"structured_data": _valid_sd()}
    body.update(payload)
    return client.put(f"/api/orders/{oid}/structured", json=body)


# --------------------------------------------------------------------------
# 1. 자가실측 (Boolean 컬럼)
# --------------------------------------------------------------------------
def test_self_measurement_toggle_lands_in_ledger(client):
    """자가실측을 켜면 원장에 before/after 가 남는다."""
    oid = _create_order(is_self_measurement=False)
    _login(client, "gap-self-on")

    res = _put(client, oid, is_self_measurement=True)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).is_self_measurement is True
    rows = _ledger(oid, "is_self_measurement")
    assert len(rows) == 1
    assert rows[0].before_value == "False"
    assert rows[0].after_value == "True"
    assert rows[0].op == "set"


def test_self_measurement_off_lands_in_ledger(client):
    """끄는 것도 변경이다 — 켠 기록만 남으면 언제 풀렸는지 알 수 없다."""
    oid = _create_order(is_self_measurement=True)
    _login(client, "gap-self-off")

    res = _put(client, oid, is_self_measurement=False)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).is_self_measurement is False
    rows = _ledger(oid, "is_self_measurement")
    assert len(rows) == 1
    assert rows[0].before_value == "True"
    assert rows[0].after_value == "False"


def test_self_measurement_unchanged_writes_no_row(client):
    """값이 그대로면 행을 만들지 않는다."""
    oid = _create_order(is_self_measurement=True)
    _login(client, "gap-self-same")

    res = _put(client, oid, is_self_measurement=True)

    # 저장이 실제로 성공했는지부터 본다 — 403/500 으로 죽은 저장은 "행이 없다"를 공짜로
    # 통과시켜서, 무기록 계약이 아니라 요청 실패를 통과시키는 테스트가 된다.
    assert res.status_code == 200, res.get_data(as_text=True)
    # 성공했더라도 서버가 값을 엉뚱하게 바꿔 놓았다면 그것도 결함이다.
    assert _fresh(oid).is_self_measurement is True, "무변경 저장이 컬럼 값을 바꿨다"
    assert _ledger(oid, "is_self_measurement") == []


# --------------------------------------------------------------------------
# 2. 주문 비고 (Order.notes 컬럼 — 경로는 order_notes)
# --------------------------------------------------------------------------
def test_order_notes_change_lands_in_ledger_under_order_notes_path(client):
    """주문 비고 변경은 ``order_notes`` 로 남는다(``notes`` 는 sd 비고 몫이다)."""
    oid = _create_order(notes="기존 비고")
    _login(client, "gap-notes-set")

    res = _put(client, oid, notes="바뀐 비고")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).notes == "바뀐 비고"
    rows = _ledger(oid, "order_notes")
    assert len(rows) == 1
    assert rows[0].before_value == "기존 비고"
    assert rows[0].after_value == "바뀐 비고"
    assert rows[0].op == "set"
    assert _ledger(oid, "notes") == [], "컬럼 비고가 sd 비고 경로를 덮어쓰면 두 이력이 섞인다"


def test_order_notes_added_and_cleared_use_add_and_clear_ops(client):
    """빈값→값은 ``add``, 값→빈값은 ``clear`` 다."""
    oid = _create_order(notes=None)
    _login(client, "gap-notes-add")

    res = _put(client, oid, notes="새 비고")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).notes == "새 비고"
    added = _ledger(oid, "order_notes")
    assert len(added) == 1
    assert added[0].before_value is None
    assert added[0].after_value == "새 비고"
    assert added[0].op == "add"

    res = _put(client, oid, notes="")
    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).notes is None
    cleared = _ledger(oid, "order_notes")
    assert len(cleared) == 2
    assert cleared[1].before_value == "새 비고"
    assert cleared[1].after_value is None
    assert cleared[1].op == "clear"


def test_order_notes_unchanged_writes_no_row(client):
    """같은 비고로 저장하면 행이 없다."""
    oid = _create_order(notes="기존 비고")
    _login(client, "gap-notes-same")

    res = _put(client, oid, notes="기존 비고")

    # 죽은 저장이 "행이 없다"로 위장하지 못하게 상태부터 못 박는다.
    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).notes == "기존 비고", "무변경 저장이 컬럼 값을 바꿨다"
    assert _ledger(oid, "order_notes") == []


def test_order_notes_blank_to_blank_writes_no_row(client):
    """``None`` 과 빈 문자열은 같은 뜻이다 — 빈값→빈값은 무변경이다."""
    oid = _create_order(notes=None)
    _login(client, "gap-notes-blank")

    res = _put(client, oid, notes="")

    assert res.status_code == 200, res.get_data(as_text=True)
    # 빈 문자열은 ``None`` 으로 접혀 저장된다 — 빈값끼리라 컬럼도 그대로다.
    assert _fresh(oid).notes is None, "빈값→빈값 저장이 컬럼 값을 바꿨다"
    assert _ledger(oid, "order_notes") == []


# --------------------------------------------------------------------------
# 3. 접수일 / 접수시간 (문자열 컬럼)
# --------------------------------------------------------------------------
def test_received_date_change_lands_in_ledger(client):
    """접수일 변경이 원장에 남는다."""
    oid = _create_order(received_date="2026-08-26")
    _login(client, "gap-rdate-set")

    res = _put(client, oid, received_date="2026-08-27")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).received_date == "2026-08-27"
    rows = _ledger(oid, "received_date")
    assert len(rows) == 1
    assert rows[0].before_value == "2026-08-26"
    assert rows[0].after_value == "2026-08-27"
    assert rows[0].op == "set"


def test_received_date_unchanged_writes_no_row(client):
    """같은 접수일로 저장하면 행이 없다."""
    oid = _create_order(received_date="2026-08-26")
    _login(client, "gap-rdate-same")

    res = _put(client, oid, received_date="2026-08-26")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).received_date == "2026-08-26", "무변경 저장이 컬럼 값을 바꿨다"
    assert _ledger(oid, "received_date") == []


def test_received_time_added_lands_in_ledger(client):
    """비어 있던 접수시간을 채우면 ``add`` 로 남는다."""
    oid = _create_order(received_time=None)
    _login(client, "gap-rtime-add")

    res = _put(client, oid, received_time="14:30")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).received_time == "14:30"
    rows = _ledger(oid, "received_time")
    assert len(rows) == 1
    assert rows[0].before_value is None
    assert rows[0].after_value == "14:30"
    assert rows[0].op == "add"


def test_received_time_cleared_lands_in_ledger(client):
    """접수시간을 지우면 ``clear`` 로 남는다."""
    oid = _create_order(received_time="14:30")
    _login(client, "gap-rtime-clear")

    res = _put(client, oid, received_time="")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).received_time is None
    rows = _ledger(oid, "received_time")
    assert len(rows) == 1
    assert rows[0].before_value == "14:30"
    assert rows[0].after_value is None
    assert rows[0].op == "clear"


def test_received_time_unchanged_writes_no_row(client):
    """같은 접수시간으로 저장하면 행이 없다."""
    oid = _create_order(received_time="14:30")
    _login(client, "gap-rtime-same")

    res = _put(client, oid, received_time="14:30")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _fresh(oid).received_time == "14:30", "무변경 저장이 컬럼 값을 바꿨다"
    assert _ledger(oid, "received_time") == []


# --------------------------------------------------------------------------
# 4. 무변경 저장 · 기존 계약 회귀
# --------------------------------------------------------------------------
def test_save_without_flat_changes_writes_no_flat_rows(client):
    """평면 컬럼을 그대로 둔 저장은 네 경로 모두 행을 만들지 않는다."""
    oid = _create_order(
        is_self_measurement=True,
        notes="기존 비고",
        received_date="2026-08-26",
        received_time="14:30",
    )
    _login(client, "gap-noop")

    res = _put(
        client, oid,
        is_self_measurement=True,
        notes="기존 비고",
        received_date="2026-08-26",
        received_time="14:30",
    )

    assert res.status_code == 200, res.get_data(as_text=True)
    # 무변경 저장이 값을 조용히 갈아엎었는데 원장만 비어 있으면 그것도 결함이다.
    saved = _fresh(oid)
    assert saved.is_self_measurement is True
    assert saved.notes == "기존 비고"
    assert saved.received_date == "2026-08-26"
    assert saved.received_time == "14:30"
    for path in ("is_self_measurement", "order_notes", "received_date", "received_time"):
        assert _ledger(oid, path) == [], f"{path} 가 무변경인데 원장에 쌓였다"


def test_regional_flat_columns_still_land_in_ledger(client):
    """ORDER-FLAG-01 회귀 방지 — 지방주문·시공구분 기록이 그대로 남아야 한다."""
    oid = _create_order()
    _login(client, "gap-regional")

    res = _put(client, oid, is_regional=True, construction_type="협력사 시공")

    assert res.status_code == 200, res.get_data(as_text=True)
    saved = _fresh(oid)
    assert saved.is_regional is True
    assert saved.construction_type == "협력사 시공"
    regional_rows = _ledger(oid, "is_regional")
    assert len(regional_rows) == 1
    assert regional_rows[0].before_value == "False"
    assert regional_rows[0].after_value == "True"
    ctype_rows = _ledger(oid, "construction_type")
    assert len(ctype_rows) == 1
    assert ctype_rows[0].after_value == "협력사 시공"


def test_flat_changes_share_the_save_change_set(client):
    """한 저장에서 생긴 평면 컬럼 행들은 같은 ``change_set_id`` 로 묶인다."""
    oid = _create_order(is_self_measurement=False, notes=None, received_time=None)
    _login(client, "gap-changeset")

    res = _put(client, oid, is_self_measurement=True, notes="새 비고", received_time="09:00")

    assert res.status_code == 200, res.get_data(as_text=True)
    saved = _fresh(oid)
    assert saved.is_self_measurement is True
    assert saved.notes == "새 비고"
    assert saved.received_time == "09:00"
    ledgers = [
        _ledger(oid, "is_self_measurement"),
        _ledger(oid, "order_notes"),
        _ledger(oid, "received_time"),
    ]
    # 세 경로가 다 실렸는지 먼저 본다 — 하나만 실려도 change_set 집합 크기는 1 이라 통과한다.
    assert all(ledgers), [len(rows) for rows in ledgers]
    ids = {rows[0].change_set_id for rows in ledgers}
    assert len(ids) == 1, "같은 저장인데 change_set 이 갈라졌다"
