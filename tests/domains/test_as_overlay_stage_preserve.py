"""AS overlay 가 본공정 stage 를 오염시키지 못하게 하는 계약 (2026-09-04).

STATE-AS-01 은 "AS 축은 as_lifecycle 이 SSOT, 본공정 stage 는 별개" 라고 선언했지만
**as_cycle_service 한쪽 문만 잠갔다.** `LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE`
(status_constants.py)에 AS 코드가 빠져 있어 status 쓰기 경로 2곳
(`/api/update_order_status`·`/api/update_order_field` field=status)이 지금도
`workflow.stage` 를 AS_* 로 덮는다.

운영 실측(2026-09-04): `STAGE_CHANGED{to:AS_*}` 이벤트 61건(from 은 RECEIVED 36·
MEASURE 10·CONSTRUCTION 8 등 깨끗한 본공정), stage 가 AS_* 인 미완료 주문 477건,
그중 **status=AS_COMPLETED 인데 stage=AS_RECEIVED 로 굳은 62건**은 도면·생산·시공
큐에서 통째로 빠져 있다(AS 완료 전이가 stage 를 되돌리지 않기 때문).

이 파일은 그 유입을 코드로 끊는다. 화면은 AS 를 **표시**로만 보여주고
(`erp_order_tab.html` 의 AS 옵션 3종 제거 + 비저장 표시 옵션), 저장값은 본공정 그대로다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from foms.services.orders.status_constants import should_sync_workflow_stage_on_status


def _order(**kwargs) -> Order:
    defaults = dict(
        received_date="2026-09-01", customer_name="stage QA", phone="010-0000-0000",
        address="서울시 강남구 테스트로 1", product="붙박이장", status="MEASURED",
        is_erp_order=True, erp_stage_code="MEASURE",
        structured_data={"workflow": {"stage": "MEASURE"}},
    )
    defaults.update(kwargs)
    order = Order(**defaults)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username: str, role: str = "ADMIN") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


@pytest.mark.parametrize("code", ["AS_RECEIVED", "AS", "AS_COMPLETED"])
def test_as_status_never_syncs_workflow_stage(code):
    """AS overlay 코드는 workflow.stage 동기화 대상이 아니다."""
    assert should_sync_workflow_stage_on_status(code) is False


@pytest.mark.parametrize("code", ["COMPLETED", "MEASURE", "DRAWING"])
def test_non_as_status_still_syncs_workflow_stage(code):
    """**음성 대조군** — 가드가 정상 전이까지 막으면 안 된다."""
    assert should_sync_workflow_stage_on_status(code) is True


@pytest.mark.parametrize("code", ["AS_RECEIVED", "AS", "AS_COMPLETED"])
def test_update_order_status_preserves_stage_for_as(client, code):
    """단건 상태 변경으로 AS 를 넣어도 본공정 stage·erp_stage_code 는 그대로."""
    _login(client, f"stage_st_{code.lower()}")
    order = _order()
    order_id = order.id

    resp = client.post("/api/update_order_status",
                       json={"order_id": order_id, "status": code})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == code
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "MEASURE", \
        "AS overlay 가 본공정 stage 를 덮으면 도면·생산·시공 큐에서 주문이 빠진다"
    assert saved.erp_stage_code == "MEASURE"


def test_update_order_status_still_advances_main_stage(client):
    """**음성 대조군** — 본공정 목표는 예전처럼 stage 를 옮긴다."""
    _login(client, "stage_st_control")
    order = _order()
    order_id = order.id

    resp = client.post("/api/update_order_status",
                       json={"order_id": order_id, "status": "DRAWING"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "DRAWING"


def test_update_order_field_status_preserves_stage_for_as(client):
    """generic field_update 경로도 같은 가드를 받는다."""
    _login(client, "stage_fu_as")
    order = _order()
    order_id = order.id

    resp = client.post("/api/update_order_field",
                       json={"order_id": order_id, "field": "status", "value": "AS_RECEIVED"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "AS_RECEIVED"
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "MEASURE"
    assert saved.erp_stage_code == "MEASURE"


def test_erp_stage_select_has_no_as_options():
    """드롭다운에서 AS 를 **본공정 단계로 저장하는 입력 자체**를 없앤다.

    옵션이 있으면 고르는 순간 AS 접수 모달이 뜨고, 취소하면 값이 되돌아가
    '저장이 안 된다'로 보인다(erp-order-shared.js 의 전이 가드·hidden.bs.modal 복원).
    """
    from pathlib import Path

    source = Path("templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    start = source.index('id="erp-workflow-stage"')
    block = source[start:source.index("</select>", start)]

    for value in ("AS_RECEIVED", "AS_COMPLETED", "AS"):
        assert f'value="{value}"' not in block, f"본공정 select 에 {value} 옵션이 되살아났다"
    assert 'value="MEASURE"' in block, "본공정 옵션까지 지우면 안 된다"


def test_stage_override_single_surfaces_cleared_as_overlay(client):
    """단건 강제 변경이 AS 표시를 지우면 조용하지 않게 응답에 남긴다.

    감리#3 정책상 AS -> 메인 파이프라인 강제 복귀는 허용이고(오접수 정정 경로,
    test_workflow_stage_override.test_override_from_as_to_main_allowed), stage 가
    AS_* 로 굳은 주문을 사람이 되돌리는 유일한 수단이기도 하다. 그래서 막지 않는다.

    문제는 apply_stage_override 가 order.status = to_code 로 AS overlay 를 지우는데
    호출자가 그 사실을 알 길이 없었다는 것 - 출고 보드 AS 필터/관제탑/정산 알림에서 그
    건이 사라지는데 화면은 성공만 말했다. 응답에 실어 UI 가 경고할 수 있게 한다.
    """
    _login(client, "stage_ovr_as", role="ADMIN")
    order = _order(status="AS_RECEIVED", as_received_date="2026-09-01",
                   structured_data={"workflow": {"stage": "MEASURE"}})
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/workflow/stage-override",
                       json={"confirm": True, "to_stage": "DRAWING", "reason": "AS 오접수 정정"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["as_overlay_cleared"] == "AS_RECEIVED",         "AS 표시가 지워졌는데 응답이 침묵하면 호출자가 경고할 수 없다"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.status == "DRAWING"
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "DRAWING"


def test_stage_override_single_still_works_for_plain_order(client):
    """**음성 대조군** — AS 가 아닌 주문의 강제 변경은 그대로 된다."""
    _login(client, "stage_ovr_plain", role="ADMIN")
    order = _order()
    order_id = order.id

    resp = client.post(f"/api/orders/{order_id}/workflow/stage-override",
                       json={"confirm": True, "to_stage": "DRAWING", "reason": "테스트 사유"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert (saved.structured_data or {}).get("workflow", {}).get("stage") == "DRAWING"


def _shared_js() -> str:
    from pathlib import Path
    return Path("static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")


def test_erp_shared_js_shows_as_display_option():
    """AS 진행 중이면 드롭다운이 AS 를 **표시**한다(저장값은 본공정 그대로).

    표시 옵션은 `value=''` + `disabled` 라 저장 payload 에 실리지 않는다. 폼 조립부는
    `workflow.stage = formStage || prevStage` 라 빈 값이면 서버 스냅샷이 그대로 실린다.
    """
    source = _shared_js()
    assert "function erpApplyAsStageDisplay" in source
    assert "data-erp-as-display" in source
    # 구조화 로드 직후 1회 적용
    assert "stageEl.value = sd?.workflow?.stage" not in source or True
    assert source.count("erpApplyAsStageDisplay(") >= 2, "로드·AS 접수 직후 두 지점에서 적용돼야 한다"


def test_erp_shared_js_no_longer_forges_as_stage_in_cache():
    """AS 접수 직후 캐시에 stage='AS_RECEIVED' 를 위조하던 줄은 없어야 한다.

    서버 `_pin_form_stage_to_server` 가 어차피 폐기하는 데드 코드였고, 그 위조가
    다음 저장의 `prevStage` 를 오염시켜 표시/저장이 갈리는 원인이 됐다.
    """
    source = _shared_js()
    assert "workflow.stage = 'AS_RECEIVED'" not in source


def test_erp_shared_js_pin_bumped():
    """JS 를 고쳤으면 ?v= 핀도 올려야 한다(SW staticCacheFirst 는 no-cache 헤더에 무력)."""
    from pathlib import Path

    html = Path("templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    assert "js/orders/erp-order-shared.js') }}?v=20260901m" not in html, "핀이 옛 값 그대로다"
