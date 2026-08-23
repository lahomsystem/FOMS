"""P1-03: OrderDraft API + wizard shell wiring."""

from __future__ import annotations

import json
import io
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _login(client, app, username: str = "wizard_api_user") -> None:
    from db import db_session
    from models import User

    with app.app_context():
        if not db_session.query(User).filter_by(username=username).first():
            db_session.add(
                User(
                    username=username,
                    password=generate_password_hash("admin"),
                    role="ADMIN",
                    team="CS",
                    name="Wizard User",
                )
            )
            db_session.commit()
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def test_wizard_template_contract() -> None:
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert 'id="foms-wizard-root"' in shell
    assert "data-draft-key" in shell
    assert "step1_basic.html" in shell
    assert "js/foms/draft.js" in shell
    assert "js/foms/wizard.js" in shell
    assert "js/foms/wizard-attachments.js" in shell
    assert "js/foms/photo-capture.js" in shell
    assert 'data-conflict="merge"' in shell
    assert 'data-exit-href=' in shell
    assert "erp_dashboard.erp_dashboard" in shell
    css = (ROOT / "static/css/components/foms-wizard.css").read_text(encoding="utf-8")
    assert ".foms-wizard" in css
    assert "foms-wizard.css" in shell
    step2 = (ROOT / "templates/orders/wizard/step2_products.html").read_text(encoding="utf-8")
    assert "data-foms-photo-capture" in step2
    assert "data-wizard-attachment-input" in step2
    assert 'id="wiz-deposit-amount"' in step2
    assert "예약금(선금)" in step2
    step4 = (ROOT / "templates/orders/wizard/step4_confirm.html").read_text(encoding="utf-8")
    assert 'id="foms-wizard-summary-deposit"' in step4
    assert 'id="foms-wizard-summary-balance"' in step4
    js = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    assert "mergeDraftPayload" in js
    assert 'action === "merge"' in js
    assert "FomsWizardMergeDraftPayload" in js
    assert "readWizardExitHref" in js
    assert "collectPayment" in js
    assert "bindWizardDepositInput" in js
    assert "buildWizardTotals" in js
    assert '"/orders/"' not in js


def test_order_draft_get_empty(client, app, wizard_enabled) -> None:
    _login(client, app)
    response = client.get("/api/erp/order-draft?key=new.test-empty")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["draft"] is None


def test_order_draft_put_and_get(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_put_user")
    body = {
        "draft_key": "new.test-put",
        "step": 2,
        "payload": {
            "schema_version": 1,
            "step": 2,
            "data": {"customer_name": "고명옥", "phone": "010-1111-2222", "address": "Seoul"},
        },
    }
    put = client.put(
        "/api/erp/order-draft",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert put.status_code == 200
    put_json = put.get_json()
    assert put_json["success"] is True
    assert put_json["updated_at"]

    get_resp = client.get("/api/erp/order-draft?key=new.test-put")
    assert get_resp.status_code == 200
    got = get_resp.get_json()
    assert got["draft"]["step"] == 2
    assert got["draft"]["payload"]["data"]["customer_name"] == "고명옥"


def test_order_draft_conflict_409(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_conflict_user")
    key = "new.test-conflict"
    base = {
        "draft_key": key,
        "step": 1,
        "payload": {"schema_version": 1, "step": 1, "data": {"customer_name": "A"}},
    }
    first = client.put(
        "/api/erp/order-draft",
        data=json.dumps(base),
        content_type="application/json",
    )
    updated_at = first.get_json()["updated_at"]

    stale = client.put(
        "/api/erp/order-draft",
        data=json.dumps(
            {
                "draft_key": key,
                "step": 1,
                "payload": {"schema_version": 1, "step": 1, "data": {"customer_name": "B"}},
            }
        ),
        content_type="application/json",
        headers={"X-If-Match": "1999-01-01 00:00:00"},
    )
    assert stale.status_code == 409
    conflict = stale.get_json()
    assert conflict["error"] == "CONFLICT"
    assert conflict["current"]["updated_at"] == updated_at


def test_order_draft_delete(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_delete_user")
    key = "new.test-delete"
    client.put(
        "/api/erp/order-draft",
        data=json.dumps(
            {
                "draft_key": key,
                "step": 1,
                "payload": {"schema_version": 1, "step": 1, "data": {}},
            }
        ),
        content_type="application/json",
    )
    deleted = client.delete(f"/api/erp/order-draft?key={key}")
    assert deleted.status_code == 200
    assert client.get(f"/api/erp/order-draft?key={key}").get_json()["draft"] is None


def test_order_draft_submit_creates_order(client, app, wizard_enabled) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "wizard_submit_user")
    key = "new.test-submit"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "제출테스트",
            "phone": "010-9999-8888",
            "address": "경기도 성남시",
            "received_date": "2026-05-30",
            "items": [
                {
                    "product_name": "주방장",
                    "spec_rows": [{"spec_width": "3000", "spec_depth": "600", "spec_height": "2300"}],
                }
            ],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.customer_name == "제출테스트"
        assert order.is_erp_order is True
        assert (order.structured_data or {}).get("workflow", {}).get("stage") == "RECEIVED"
        assert order.status == "RECEIVED"
        assert order.erp_stage_code == "RECEIVED"
    assert client.get(f"/api/erp/order-draft?key={key}").get_json()["draft"] is None


def test_wizard_step3_flag_inputs_contract() -> None:
    """일정·담당 단계에서 지방주문·라홈시스템·긴급을 입력할 수 있어야 한다."""
    step3 = (ROOT / "templates/orders/wizard/step3_schedule.html").read_text(encoding="utf-8")
    assert 'id="wiz-flag-regional"' in step3
    assert 'id="wiz-flag-factory2"' in step3
    assert 'id="wiz-flag-urgent"' in step3
    assert 'id="wiz-regional-construction-type"' in step3
    assert 'id="wiz-urgent-reason"' in step3
    assert 'id="wiz-load-date"' in step3
    js = (ROOT / "static/js/foms/wizard.js").read_text(encoding="utf-8")
    assert "collectFlags" in js
    assert "syncFlagFieldVisibility" in js
    # 추가 버튼으로 만든 카드는 접힌 채로 두지 않는다.
    assert "revealEmptyProductCard(addedCard)" in js
    css = (ROOT / "static/css/components/foms-wizard.css").read_text(encoding="utf-8")
    assert ".foms-wizard__flag" in css


def test_order_draft_submit_persists_order_flags(client, app, wizard_enabled) -> None:
    """지방주문(컬럼)·라홈시스템/긴급(structured flags)이 주문에 저장된다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_flags_user")
    key = "new.test-flags"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "구분테스트",
            "phone": "010-1111-2222",
            "address": "강원도 원주시",
            "received_date": "2026-08-23",
            "items": [{"product_name": "붙박이장", "spec_rows": []}],
            "schedule": {},
            "flags": {
                "regional_order": True,
                "regional_construction_type": "협력사 시공",
                "factory2": True,
                "urgent": True,
                "urgent_reason": "시공일 임박",
            },
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.is_regional is True
        assert order.construction_type == "협력사 시공"
        flags = (order.structured_data or {}).get("flags") or {}
        assert flags.get("factory2") is True
        assert flags.get("urgent") is True
        assert flags.get("urgent_reason") == "시공일 임박"
        assert order.erp_urgent is True


def test_order_draft_submit_persists_regional_load_date(client, app, wizard_enabled) -> None:
    """지방주문 상차일은 shipping_scheduled_date 컬럼과 structured schedule.load 로 간다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_load_date_user")
    key = "new.test-load-date"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "상차테스트",
            "phone": "010-5555-6666",
            "address": "전라북도 전주시",
            "items": [{"product_name": "주방장", "spec_rows": []}],
            "schedule": {"load_date": "2026-09-01"},
            "flags": {"regional_order": True, "regional_construction_type": "하우드 시공"},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.shipping_scheduled_date == "2026-09-01"
        assert ((order.structured_data or {}).get("schedule") or {}).get("load") == {
            "date": "2026-09-01"
        }


def test_order_draft_submit_drops_load_date_when_not_regional(client, app, wizard_enabled) -> None:
    """지방주문이 아니면 남아 있던 상차일은 저장하지 않는다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_load_date_nonregional_user")
    key = "new.test-load-date-off"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "비지방테스트",
            "phone": "010-7777-8888",
            "address": "서울시 송파구",
            "items": [{"product_name": "신발장", "spec_rows": []}],
            "schedule": {"load_date": "2026-09-01"},
            "flags": {"regional_order": False},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert not order.shipping_scheduled_date
        assert "load" not in ((order.structured_data or {}).get("schedule") or {})


def test_order_draft_submit_rejects_regional_without_construction_type(
    client, app, wizard_enabled
) -> None:
    """지방주문인데 구분(하우드/협력사)이 없으면 400."""
    _login(client, app, "wizard_flags_reject_user")
    key = "new.test-flags-reject"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "구분누락",
            "phone": "010-3333-4444",
            "address": "충청북도 청주시",
            "items": [{"product_name": "신발장", "spec_rows": []}],
            "schedule": {},
            "flags": {"regional_order": True, "regional_construction_type": ""},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 400
    body = submit.get_json()
    assert body["error"] == "VALIDATION"
    assert any("지방주문 구분" in f for f in body["fields"])


def test_order_draft_submit_sets_measure_for_haud_orderer(client, app, wizard_enabled) -> None:
    """하우드 발주사는 실측일 없어도 주문 단계가 실측(MEASURE)이어야 한다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_haud_user")
    key = "new.test-haud-stage"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "하우드단계",
            "phone": "010-2222-3333",
            "address": "서울시",
            "orderer": "하우드",
            "items": [{"product_name": "붙박이", "spec_rows": [{}]}],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.structured_data["workflow"]["stage"] == "MEASURE"
        assert order.status == "MEASURE"
        assert order.erp_stage_code == "MEASURE"


def test_order_draft_submit_sets_measure_for_custom_orderer(client, app, wizard_enabled) -> None:
    """직접 입력 발주사도 실측 단계로 생성되어야 한다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_custom_user")
    key = "new.test-custom-stage"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "직접입력단계",
            "phone": "010-4444-5555",
            "address": "부산시",
            "orderer": "협력사X",
            "items": [{"product_name": "주방", "spec_rows": [{}]}],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.structured_data["workflow"]["stage"] == "MEASURE"
        assert order.status == "MEASURE"
        assert order.erp_stage_code == "MEASURE"


def test_order_draft_submit_sets_measure_for_lahom_with_measurement_date(
    client, app, wizard_enabled
) -> None:
    """라홈도 실측일 입력 시 실측 단계로 생성되어야 한다."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_meas_user")
    key = "new.test-lahom-meas"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "라홈실측",
            "phone": "010-6666-7777",
            "address": "대전시",
            "orderer": "라홈",
            "items": [{"product_name": "드레스룸", "spec_rows": [{}]}],
            "schedule": {"measurement_date": "2026-06-30"},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.structured_data["workflow"]["stage"] == "MEASURE"
        assert order.erp_stage_code == "MEASURE"


def test_order_draft_submit_persists_deposit_and_totals(client, app, wizard_enabled) -> None:
    """Wizard submit maps deposit to ERP structured_data payment/totals."""
    from db import db_session
    from models import Order

    _login(client, app, "wizard_deposit_user")
    key = "new.test-deposit"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "예약금테스트",
            "phone": "010-1111-2222",
            "address": "서울시 강남구",
            "received_date": "2026-06-26",
            "deposit": "100,000원",
            "items": [
                {
                    "product_name": "붙박이장",
                    "spec_rows": [{}],
                    "price": "655,000",
                }
            ],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = order.structured_data or {}
        assert sd.get("payment", {}).get("deposit") == 100000
        totals = sd.get("totals") or {}
        assert totals.get("items_total") == 655000
        assert totals.get("deposit_amount") == 100000
        assert totals.get("balance_amount") == 555000
        assert totals.get("final_amount") == 555000


def test_add_order_renders_wizard_when_flag_on(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_page_user")
    response = client.get("/add?wizard=1")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-wizard-root" in body
    assert 'data-exit-href="/erp/dashboard"' in body
    assert "wizard_shell" not in body  # rendered, not raw path leak required — ok if template name absent


def test_orders_index_alias_redirects_mobile_wizard_to_erp_dashboard(
    client, app, wizard_enabled
) -> None:
    _login(client, app, "wizard_orders_alias_user")
    response = client.get("/orders/", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/erp/dashboard")


def test_orders_index_alias_keeps_desktop_on_legacy_home(client, app, wizard_enabled) -> None:
    _login(client, app, "wizard_orders_desktop_user")
    response = client.get(
        "/orders/",
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_add_order_renders_desktop_form_on_pc_when_cohort_on(client, app, monkeypatch) -> None:
    """Mobile v2 cohort must not force wizard on desktop browsers."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    _login(client, app, "wizard_desktop_user")
    response = client.get("/add?open=erp-order")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-wizard-root" not in body
    assert 'id="erp-order"' in body


def test_order_draft_attachment_upload(client, app, wizard_enabled, monkeypatch) -> None:
    _login(client, app, "wizard_attach_user")

    class DummyStorage:
        storage_type = "local"

        def upload_file(self, file_obj, filename, folder):
            return {"success": True, "key": f"{folder}/{filename}"}

        def object_exists(self, key):
            return True

    monkeypatch.setattr("foms.api.erp_order_draft.get_storage", lambda: DummyStorage())

    response = client.post(
        "/api/erp/order-draft/attachments",
        data={
            "draft_key": "new.test-attach",
            "item_index": "0",
            "file": (io.BytesIO(b"fake image"), "measure.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["tmp_key"].endswith("measure.jpg")
    assert payload["data"]["filename"] == "measure.jpg"


def test_order_draft_submit_promotes_attachments(client, app, wizard_enabled, monkeypatch) -> None:
    from db import db_session
    from models import OrderAttachment

    _login(client, app, "wizard_attach_submit")

    class DummyStorage:
        storage_type = "local"

        def object_exists(self, key):
            return key.startswith("order-drafts/")

        def get_file_type(self, filename):
            return "image"

    monkeypatch.setattr("foms.api.erp_order_draft.get_storage", lambda: DummyStorage())
    monkeypatch.setattr("foms.services.order_draft_attachments.get_storage", lambda: DummyStorage())

    key = "new.test-attach-submit"
    tmp_key = "order-drafts/1/new.test-attach-submit/measure.jpg"
    payload = {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "첨부테스트",
            "phone": "010-1234-5678",
            "address": "서울",
            "received_date": "2026-05-30",
            "items": [
                {
                    "product_name": "주방",
                    "spec_rows": [{}],
                    "attachments": [{"tmp_key": tmp_key, "filename": "measure.jpg"}],
                }
            ],
            "schedule": {},
        },
    }
    client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    submit = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert submit.status_code == 200
    order_id = submit.get_json()["data"]["order_id"]
    with app.app_context():
        attachment = (
            db_session.query(OrderAttachment)
            .filter(OrderAttachment.order_id == order_id)
            .one()
        )
        assert attachment.filename == "measure.jpg"
        assert attachment.item_index == 0


def test_wizard_disabled_returns_403(client, app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOMS_WIZARD_NEW_ORDER_ENABLED", raising=False)
    _login(client, app, "wizard_off_user")
    response = client.get("/api/erp/order-draft?key=new.off")
    assert response.status_code == 403
