"""ERP Order 변경 → 도면팀 알림 SSOT 테스트."""
from __future__ import annotations

import copy
import datetime as dt

import pytest

from db import db_session
from models import Notification, Order, User
from foms.services.notifications.drawing_order_change import (
    HISTORY_ACTION,
    NOTIFICATION_TYPE,
    ack_drawing_order_change,
    apply_drawing_order_change_alert,
    compute_drawing_relevant_changes,
    is_order_change_pending,
    should_alert_drawing_team,
    summarize_changes,
)


def _base_sd(**overrides):
    sd = {
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
        "drawing_status": "IN_PROGRESS",
        "site": {"address_full": "서울 강남구 1"},
        "schedule": {
            "measurement": {"date": "2026-07-20"},
            "construction": {"date": "2026-07-25"},
        },
        "items": [{"product_name": "붙박이장", "width": "1200", "height": "2400"}],
        "drawing_transfer_history": [],
    }
    sd.update(overrides)
    return sd


def test_compute_changes_detects_address_and_dims():
    old = _base_sd()
    new = _base_sd()
    new["site"]["address_full"] = "서울 서초구 2"
    new["items"][0]["width"] = "1300"
    changes = compute_drawing_relevant_changes(old, new)
    paths = {c["path"] for c in changes}
    assert "site.address" in paths
    assert "items.0.width" in paths
    width_ch = next(c for c in changes if c["path"] == "items.0.width")
    assert width_ch["from"] == "1200"
    assert width_ch["to"] == "1300"
    assert "W" in width_ch["label"]


def test_compute_changes_detects_manager():
    """담당자(parties.manager) 변경은 도면 타임라인에 반드시 잡혀야 함."""
    old = _base_sd(parties={"manager": {"name": "한용희"}, "customer": {"name": "고객"}})
    new = _base_sd(parties={"manager": {"name": "꿈돌이"}, "customer": {"name": "고객"}})
    changes = compute_drawing_relevant_changes(old, new)
    assert any(c["path"] == "parties.manager.name" for c in changes)
    mgr = next(c for c in changes if c["path"] == "parties.manager.name")
    assert mgr["from"] == "한용희"
    assert mgr["to"] == "꿈돌이"
    assert mgr["label"] == "담당자"


def test_compute_changes_item_option_before_after():
    """색상·옵션 등도 before→after로 표기."""
    old = _base_sd()
    old["items"][0]["color"] = "화이트"
    old["items"][0]["option"] = "푸쉬"
    new = _base_sd()
    new["items"][0]["color"] = "포그그레이"
    new["items"][0]["option"] = "손잡이형"
    changes = compute_drawing_relevant_changes(old, new)
    by_path = {c["path"]: c for c in changes}
    assert by_path["items.0.color"]["from"] == "화이트"
    assert by_path["items.0.color"]["to"] == "포그그레이"
    assert by_path["items.0.option"]["from"] == "푸쉬"
    assert by_path["items.0.option"]["to"] == "손잡이형"
    note = summarize_changes(changes)
    assert "화이트→포그그레이" in note or "색상" in note


def test_compute_changes_empty_when_operational_only():
    """drawing/quest 등 운영 JSON만 바뀌면 주문변경 이력 없음."""
    old = _base_sd()
    new = _base_sd()
    new["drawing"] = {"status": "TRANSFERRED", "order_change_pending": True}
    new["quests"] = {"DRAWING": {"done": True}}
    new["drawing_transfer_history"] = [{"action": "TRANSFER"}]
    assert compute_drawing_relevant_changes(old, new) == []


def test_compute_changes_detects_payment():
    """결제는 필드별 before→after 로 남는다(구 `결제/금액 이전→변경됨` 자리표시 금지)."""
    old = _base_sd(payment={"deposit": 100000, "discount": 0})
    new = _base_sd(payment={"deposit": 250000, "discount": 0})
    changes = compute_drawing_relevant_changes(old, new)
    row = next(c for c in changes if c["path"] == "payment.deposit")
    assert row["label"] == "예약금"
    assert row["from"] == "100,000" and row["to"] == "250,000"
    assert not [c for c in changes if c["to"] == "변경됨"]
    assert not [c for c in changes if c["path"] == "payment.discount"]


def test_payment_block_first_creation_is_silent():
    """첫 저장에서 폼이 결제 블록을 통째로 만드는 건 변경이 아니다(모든 주문에 뜨던 원인)."""
    old = _base_sd()
    new = _base_sd(payment={
        "deposit": 985800, "discount": 0, "free_input": "", "balance_note": "",
        "cash_receipt": "", "deposit_confirmed": False, "balance_confirmed": False,
        "deposit_confirmed_at": None, "deposit_confirmed_by": None,
    })
    changes = compute_drawing_relevant_changes(old, new)
    assert not [c for c in changes if c["path"].startswith("payment")]


def test_payment_confirm_flag_is_human_readable():
    """확인 플래그는 1/0 이 아니라 확인/미확인으로 적는다."""
    old = _base_sd(payment={"deposit_confirmed": False})
    new = _base_sd(payment={"deposit_confirmed": True})
    changes = compute_drawing_relevant_changes(old, new)
    row = next(c for c in changes if c["path"] == "payment.deposit_confirmed")
    assert (row["from"], row["to"]) == ("미확인", "확인")


def test_humanize_drops_legacy_payment_placeholder():
    """과거 이력에 박힌 `결제/금액 이전→변경됨` 줄은 읽기 시점에 사라진다."""
    from foms.services.notifications.drawing_order_change import humanize_order_change_changes

    rows = humanize_order_change_changes([
        {"path": "payment", "label": "결제/금액", "from": "이전", "to": "변경됨"},
        {"path": "site.address", "label": "주소", "from": "서울 강남", "to": "서울 서초"},
    ])
    assert [r["path"] for r in rows] == ["site.address"]


def test_gate_blocks_pending_without_assignee():
    order = Order(id=1, status="RECEIVED")
    sd = _base_sd(workflow={"stage": "RECEIVED"}, drawing={"status": "PENDING"}, drawing_status="PENDING")
    assert should_alert_drawing_team(order, sd) is False


def test_gate_allows_drawing_stage():
    order = Order(id=1, status="DRAWING")
    sd = _base_sd()
    assert should_alert_drawing_team(order, sd) is True


def test_summarize_and_pending_flag():
    changes = [
        {"path": "schedule.construction.date", "label": "시공일", "from": "A", "to": "B"},
        {"path": "items.0.width", "label": "항목1 W(가로)", "from": "1200", "to": "1300"},
    ]
    note = summarize_changes(changes)
    assert "시공일" in note
    assert "1200→1300" in note
    sd = _base_sd()
    sd["drawing"]["order_change_pending"] = True
    assert is_order_change_pending(sd) is True


@pytest.fixture
def drawing_order(app):
    """DRAWING stage ERP order fixture."""
    with app.app_context():
        db = db_session()
        order = Order(
            customer_name="테스트고객",
            phone="010",
            address="서울",
            product="붙박이장",
            status="DRAWING",
            received_date="2026-07-01",
            is_erp_order=True,
            structured_data=_base_sd(),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        yield order
        db.rollback()


def test_apply_creates_history_notification_and_pending(app, drawing_order):
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        new = copy.deepcopy(old)
        new["items"][0]["width"] = "1500"
        notif, created = apply_drawing_order_change_alert(
            db,
            order,
            old,
            new,
            actor_user_id=None,
            actor_name="실측담당",
        )
        assert created is True
        assert notif is not None
        assert notif.notification_type == NOTIFICATION_TYPE
        assert notif.target_team == "DRAWING"
        history = new.get("drawing_transfer_history") or []
        assert history[-1]["action"] == HISTORY_ACTION
        assert is_order_change_pending(new) is True
        db.rollback()


def test_debounce_merges_within_60s(app, drawing_order):
    with app.app_context():
        db = db_session()
        # 실 User FK(Notification.created_by_user_id) — 하드코딩 7은 FK-ON 워커에서 red.
        actor = User(username="debounce_actor", password="x", role="STAFF", name="A", is_active=True)
        db.add(actor)
        db.commit()
        actor_id = actor.id
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        new = copy.deepcopy(old)
        new["schedule"]["construction"]["date"] = "2026-07-28"
        n1, c1 = apply_drawing_order_change_alert(
            db, order, old, new, actor_user_id=actor_id, actor_name="A"
        )
        assert c1 is True
        mid = copy.deepcopy(new)
        new2 = copy.deepcopy(new)
        new2["site"]["address_full"] = "부산"
        n2, c2 = apply_drawing_order_change_alert(
            db, order, mid, new2, actor_user_id=actor_id, actor_name="A"
        )
        assert c2 is False
        assert n2 is not None and n1 is not None and n2.id == n1.id
        history = new2.get("drawing_transfer_history") or []
        assert len([h for h in history if h.get("action") == HISTORY_ACTION]) == 1
        note = history[-1]["note"]
        assert "시공일" in note and "주소" in note
        db.rollback()


def test_ack_clears_pending(app, drawing_order):
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        sd = copy.deepcopy(order.structured_data)
        sd["drawing_transfer_history"] = [{
            "action": HISTORY_ACTION,
            "note": "치수 변경",
            "acked": False,
            "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }]
        sd["drawing"]["order_change_pending"] = True
        order.structured_data = sd
        assert ack_drawing_order_change(db, order, actor_user_id=1, actor_name="도면") is True
        assert is_order_change_pending(order.structured_data) is False
        db.rollback()


def test_deep_link_includes_erp_order_changed(app):
    from foms.api.notifications import _resolve_notification_deep_link

    notif = Notification(
        order_id=4364,
        notification_type=NOTIFICATION_TYPE,
        title="t",
        message="m",
    )
    sd = {
        "drawing_transfer_history": [{
            "action": HISTORY_ACTION,
            "at": "2026-07-15 12:00:00",
            "by_user_id": 1,
        }]
    }
    link = _resolve_notification_deep_link(notif, sd)
    assert link["deep_tab"] == "timeline"
    assert "/erp/drawing-workbench/4364" in (link["deep_link_url"] or "")
    assert "tab=timeline" in (link["deep_link_url"] or "")


def test_compute_changes_spec_rows_human_not_json():
    """스펙행 변경은 JSON 금지 — WxDxH 사람 표기. 스펙과 동일하면 스펙행 행 생략."""
    from foms.services.notifications.drawing_order_change import (
        format_spec_rows_display,
        humanize_order_change_changes,
    )

    assert (
        format_spec_rows_display(
            [{"spec_depth": "620", "spec_height": "2350", "spec_width": "3920"}]
        )
        == "3920x620x2350"
    )
    legacy = humanize_order_change_changes(
        [
            {
                "path": "items.0.spec_rows",
                "label": "항목1 스펙행",
                "from": '[{"spec_depth": "620", "spec_height": "2350", "spec_width": "3920"}]',
                "to": '[{"spec_depth": "620", "spec_height": "2350", "spec_width": "4000"}]',
            }
        ]
    )
    assert legacy[0]["from"] == "3920x620x2350"
    assert legacy[0]["to"] == "4000x620x2350"
    assert "{" not in legacy[0]["from"] and "[" not in legacy[0]["to"]

    old = _base_sd()
    old["items"][0] = {
        "product_name": "붙박이장",
        "spec": "3920x620x2350",
        "spec_width": "3920",
        "spec_depth": "620",
        "spec_height": "2350",
        "spec_rows": [{"spec_width": "3920", "spec_depth": "620", "spec_height": "2350"}],
    }
    new = _base_sd()
    new["items"][0] = {
        "product_name": "붙박이장",
        "spec": "4000x620x2350",
        "spec_width": "4000",
        "spec_depth": "620",
        "spec_height": "2350",
        "spec_rows": [{"spec_width": "4000", "spec_depth": "620", "spec_height": "2350"}],
    }
    changes = compute_drawing_relevant_changes(old, new)
    by_path = {c["path"]: c for c in changes}
    assert "items.0.spec_rows" not in by_path  # 스펙과 동일 → 중복 숨김
    assert by_path["items.0.spec"]["from"] == "3920x620x2350"
    assert by_path["items.0.spec"]["to"] == "4000x620x2350"
    for c in changes:
        assert "{" not in c["from"] and "{" not in c["to"]
        assert not str(c["from"]).lstrip().startswith("[")
        assert not str(c["to"]).lstrip().startswith("[")


def test_all_change_values_forbid_json():
    """결제·비고·옵션 list 등 모든 from/to 에 JSON 표기 금지."""
    from foms.services.notifications.drawing_order_change import (
        format_value_for_display,
        humanize_order_change_changes,
    )

    assert format_value_for_display({"amount": 1000, "method": "카드"}) == "금액 1000, 결제방법 카드"
    assert "{" not in format_value_for_display([{"a": 1}, {"b": 2}])

    old = _base_sd(notes={"address_note": "엘리베이터 없음", "phone_note": "오후만"})
    new = _base_sd(notes={"address_note": "엘리베이터 있음", "phone_note": "오후만"})
    changes = compute_drawing_relevant_changes(old, new)
    for c in changes:
        for side in ("from", "to"):
            v = str(c[side])
            assert not v.lstrip().startswith("{"), c
            assert not v.lstrip().startswith("["), c
            assert '"address_note"' not in v

    legacy = humanize_order_change_changes(
        [
            {
                "path": "notes.object",
                "label": "비고(상세)",
                "from": '{"phone_note": "a", "address_note": "b"}',
                "to": '{"phone_note": "a", "address_note": "c"}',
            }
        ]
    )
    assert "{" not in legacy[0]["from"] and "{" not in legacy[0]["to"]
    assert "주소 특이사항" in legacy[0]["to"] or "c" in legacy[0]["to"]


def test_first_fill_rows_are_not_changes():
    """빈칸·'상담' placeholder 에서 첫 값이 들어온 줄은 변경이 아니다(2026-08-20 소음 제거)."""
    old = _base_sd()
    old["schedule"]["construction"] = {}
    old["items"] = [{"product_name": "라운드 핏 냉장고장 외", "color": "상담", "handle": "상담"}]
    new = _base_sd()
    new["schedule"]["construction"] = {"date": "2026-08-27", "time": "오전"}
    new["items"] = [{"product_name": "냉장고장 리폼", "color": "클린화이트", "handle": "푸쉬"}]

    changes = compute_drawing_relevant_changes(old, new)
    paths = {c["path"] for c in changes}
    assert "items.0.product_name" in paths, "실값→실값 수정은 남아야 한다"
    assert "schedule.construction.date" not in paths
    assert "schedule.construction.time" not in paths
    assert "items.0.color" not in paths
    assert "items.0.handle" not in paths


def test_item_add_row_survives_without_field_noise():
    """항목 추가/삭제 줄은 최초 입력이어도 남기고, 그 항목의 필드 줄은 남기지 않는다."""
    old = _base_sd()
    new = _base_sd()
    new["items"].append({"product_name": "몰딩 파우더장", "color": "클린화이트", "width": "1225"})

    changes = compute_drawing_relevant_changes(old, new)
    paths = {c["path"] for c in changes}
    assert "items.1" in paths
    add_row = next(c for c in changes if c["path"] == "items.1")
    assert add_row["to"] == "몰딩 파우더장"
    assert not [p for p in paths if p.startswith("items.1.")]


def test_clearing_a_real_value_is_still_a_change():
    """값→빈칸(지움)은 최초 입력이 아니라 진짜 변경 — 계속 표시한다."""
    old = _base_sd()
    new = _base_sd()
    new["schedule"]["construction"] = {}
    changes = compute_drawing_relevant_changes(old, new)
    row = next(c for c in changes if c["path"] == "schedule.construction.date")
    assert row["from"] == "2026-07-25"
    assert row["to"] == "(없음)"


def test_humanize_drops_legacy_first_fill_rows():
    """이미 쌓인 과거 이력도 읽기 시점에 정리된다(항목 추가 줄은 유지)."""
    from foms.services.notifications.drawing_order_change import humanize_order_change_changes

    rows = humanize_order_change_changes([
        {"path": "items.1", "label": "항목2 추가", "from": "(없음)", "to": "몰딩 파우더장"},
        {"path": "items.1.color", "label": "항목2 색상", "from": "(없음)", "to": "클린화이트"},
        {"path": "items.0.color", "label": "항목1 색상", "from": "상담", "to": "클린화이트"},
        {"path": "site.address", "label": "주소", "from": "경기 파주시 청석로 350", "to": "경기 파주시 물향기2로 9"},
    ])
    assert [r["path"] for r in rows] == ["items.1", "site.address"]


def test_apply_skips_alert_when_only_first_fill(app, drawing_order):
    """최초 입력만 있는 저장은 알림·pending 을 만들지 않는다."""
    with app.app_context():
        db = db_session()
        order = db.get(Order, drawing_order.id)
        old = copy.deepcopy(order.structured_data)
        old["items"][0]["color"] = "상담"
        new = copy.deepcopy(old)
        new["items"][0]["color"] = "클린화이트"
        notif, created = apply_drawing_order_change_alert(
            db, order, old, new, actor_user_id=None, actor_name="실측담당",
        )
        assert notif is None and created is False
        assert not (new.get("drawing_transfer_history") or [])
        assert is_order_change_pending(new) is False
        db.rollback()


def test_item_add_row_hidden_before_drawing_starts():
    """도면 착수 전 품목 추가는 접수 내용 채우기 — 변경 이력에 남기지 않는다.

    운영 실측(2026-08-20, 주문 4637): 실측 최종 승인 3분 15초 뒤 저장에서 항목2가 추가됐고
    도면 전달 이력은 0건이었다. 단계만 보면 'DRAWING 이후'라 사고처럼 보이지만 실제로는
    도면이 그려지기 전이다.
    """
    old = _base_sd(drawing={"status": "PENDING"}, drawing_status="PENDING")
    new = _base_sd(drawing={"status": "PENDING"}, drawing_status="PENDING")
    new["items"].append({"product_name": "몰딩 파우더장", "color": "클린화이트"})

    changes = compute_drawing_relevant_changes(old, new)
    assert not [c for c in changes if c["path"].startswith("items.1")]


def test_item_add_row_kept_after_transfer():
    """도면을 전달한 뒤 품목이 추가되면 그건 도면이 틀어지는 변경 — 반드시 남긴다."""
    transferred = [{"action": "TRANSFER", "at": "2026-08-19 01:00:00", "by_user_name": "도면"}]
    old = _base_sd(drawing={"status": "TRANSFERRED"}, drawing_status="TRANSFERRED",
                   drawing_transfer_history=list(transferred))
    new = _base_sd(drawing={"status": "TRANSFERRED"}, drawing_status="TRANSFERRED",
                   drawing_transfer_history=list(transferred))
    new["items"].append({"product_name": "몰딩 파우더장"})

    changes = compute_drawing_relevant_changes(old, new)
    add_row = next(c for c in changes if c["path"] == "items.1")
    assert add_row["to"] == "몰딩 파우더장"


def test_item_delete_row_survives_before_drawing_starts():
    """품목 삭제는 도면 착수 전이라도 남는다 — 사라진 사실은 최초 입력이 아니다."""
    old = _base_sd(drawing={"status": "PENDING"}, drawing_status="PENDING")
    old["items"].append({"product_name": "몰딩 파우더장"})
    new = _base_sd(drawing={"status": "PENDING"}, drawing_status="PENDING")

    changes = compute_drawing_relevant_changes(old, new)
    row = next(c for c in changes if c["path"] == "items.1")
    assert row["label"].endswith("삭제") and row["from"] == "몰딩 파우더장"


def test_humanize_drops_legacy_item_add_before_drawing_start():
    """과거 이력도 그 시점 기준으로 정리된다 — 도면 착수 전 저장의 추가 줄은 접힌다."""
    from foms.services.notifications.drawing_order_change import humanize_order_change_changes

    rows = [
        {"path": "items.1", "label": "항목2 추가", "from": "(없음)", "to": "몰딩 파우더장"},
        {"path": "site.address", "label": "주소", "from": "경기 파주시 청석로 350", "to": "경기 파주시 물향기2로 9"},
    ]
    assert [r["path"] for r in humanize_order_change_changes(rows, keep_item_add_rows=False)] == [
        "site.address"
    ]
    assert [r["path"] for r in humanize_order_change_changes(rows)] == ["items.1", "site.address"]


def test_drawing_work_started_uses_transfer_not_stage():
    """도면 착수 판정은 전달 이력·도면 상태 — 단계(DRAWING)만으로는 착수가 아니다."""
    from foms.services.notifications.drawing_order_change import drawing_work_started

    stage_only = _base_sd(drawing={"order_change_pending": True}, drawing_status="PENDING")
    assert drawing_work_started(stage_only) is False

    assert drawing_work_started(_base_sd(drawing_status="IN_PROGRESS")) is True

    history = [
        {"action": "ERP_ORDER_CHANGED", "at": "2026-08-01 00:00:00"},
        {"action": "TRANSFER", "at": "2026-08-02 00:00:00"},
        {"action": "ERP_ORDER_CHANGED", "at": "2026-08-03 00:00:00"},
    ]
    sd = _base_sd(drawing_status="PENDING", drawing_transfer_history=history)
    assert drawing_work_started(sd, before_index=0) is False  # 전달 전 이벤트
    assert drawing_work_started(sd, before_index=2) is True   # 전달 후 이벤트


def test_same_dimension_value_is_one_row():
    """ERP 폼이 스펙 문자열을 spec·width 양쪽에 넣어 생긴 중복은 한 줄로 접는다."""
    old = _base_sd()
    old["items"] = [{"product_name": "붙박이장", "spec": "2400", "width": "2400"}]
    new = _base_sd()
    new["items"] = [{"product_name": "붙박이장", "spec": "2450*700*2400", "width": "2450*700*2400"}]

    changes = compute_drawing_relevant_changes(old, new)
    dim_rows = [c for c in changes if c["path"].startswith("items.0.")]
    assert [c["path"] for c in dim_rows] == ["items.0.spec"]
    assert dim_rows[0]["to"] == "2450*700*2400"


def test_different_dimension_values_both_survive():
    """가로만 바뀐 저장은 두 줄 다 남긴다 — 값이 다르면 감추지 않는다."""
    old = _base_sd()
    old["items"] = [{"product_name": "붙박이장", "spec": "4435", "width": "4435"}]
    new = _base_sd()
    new["items"] = [{"product_name": "붙박이장", "spec": "4450x570x2300", "width": "4450"}]

    changes = compute_drawing_relevant_changes(old, new)
    paths = {c["path"] for c in changes}
    assert "items.0.spec" in paths and "items.0.width" in paths


def test_humanize_dedupes_legacy_dimension_rows():
    """과거 이력에 이미 쌓인 중복도 읽기 시점에 한 줄로 접힌다."""
    from foms.services.notifications.drawing_order_change import humanize_order_change_changes

    rows = humanize_order_change_changes([
        {"path": "items.0.spec", "label": "항목1 스펙", "from": "2400", "to": "2450*700*2400"},
        {"path": "items.0.width", "label": "항목1 W(가로)", "from": "2400", "to": "2450*700*2400"},
        {"path": "items.1.spec", "label": "항목2 스펙", "from": "1060", "to": "1590"},
        {"path": "items.0.color", "label": "항목1 색상", "from": "화이트", "to": "그레이"},
    ])
    assert [r["path"] for r in rows] == ["items.0.spec", "items.1.spec", "items.0.color"]
