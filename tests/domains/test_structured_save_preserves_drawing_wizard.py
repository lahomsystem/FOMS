"""폼 저장이 도면 마법사 캔버스 상태를 지우지 않는지 (2026-09-10 운영 실사례 회귀).

실사례(주문 5177): 2026-09-10 07:56:39(UTC) 영업 담당자의 ERP 주문 **전체 폼 저장 1회**가
``structured_data['drawing_wizard']`` 를 통째로 지웠다. 시트 2장의 ``objects`` 와
``pending``·``versions`` 가 함께 사라졌는데, 감사 원장에는
``{"mode":"full","changes":[],"change_count":0}`` — **변경 0건**으로 남았다.

원인은 두 가지가 겹친 것이다.

1. 보존 목록 ``_OPERATIONAL_TOP_LEVEL_KEYS``(``foms/api/erp_orders_structured.py``)에 다른
   도면 키(``drawing``·``drawing_status``·``drawing_current_files``·
   ``drawing_transfer_history``)는 다 있는데 ``drawing_wizard`` 만 없었다.
2. allowlist(``enforce_form_allowlist``)는 **들어온 dict 에서 낯선 키를 걷어낼 뿐 빠진 옛 키를
   되살리지 않는다**. 폼은 이 키를 아예 보내지 않으므로 strip 목록에도 안 남아 로그조차 없었다.

16시간 뒤 도면 담당자가 마법사를 열었을 때 GET 은 ``state: null`` 을 줬고, 클라이언트는 빈
상태에서 새 시트를 만들어 저장했다 — 그림이 죽은 시각은 09-10 07:56:39 이다.

이 계열 사고는 이번이 여섯 번째다(``source``·``naver``·``pricing``·``alimtalk_measurement``·
``schedule.as_visit``). 그래서 이 파일은 **이름을 목록에 적어야만 사는 구조**가 끝났다는 것까지
검증한다 — ``preserve_non_form_keys`` 의 일반 규칙이 미지의 서버 소유 키도 지킨다.
"""

import pytest

from foms.api.erp_orders_structured import _preserve_operational_structured_state
from foms.services.orders.structured_form_projection import project_structured_form


def _saved_wizard() -> dict:
    """저장 전 서버값의 ``drawing_wizard`` — 시트 1장에 pen 오브젝트, pending·versions 포함."""
    return {
        "v": 1,
        "sheets": [
            {
                "id": "s-a",
                "form": {"customer_name": "임인경", "color": "화이트"},
                "product_index": 0,
                "objects": [
                    {"type": "pen", "id": "o1", "pts": [[10, 10], [20, 20], [30, 15]]}
                ],
            }
        ],
        "pending": {"s-a": {"key": "orders/5177/drawing_wizard/pending/s-a.png"}},
        "versions": [
            {"v": 1, "key": "orders/5177/drawing_wizard/versions/v1_s-a.json"}
        ],
        "updated_at": "2026-09-10 00:15:17",
        "updated_by": 42,
    }


def _server_state() -> dict:
    """저장 전 서버 structured_data(마법사 상태가 살아 있는 주문 5177 모양)."""
    return {
        "drawing_wizard": _saved_wizard(),
        "drawing_status": "RETURNED",
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "임인경"}},
    }


def _form_payload() -> dict:
    """편집 폼이 실제로 보내는 모양 — ``drawing_wizard`` 는 아예 없다."""
    return {
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "임인경"}},
        "site": {},
        "workflow": {},
        "schedule": {},
        "notes": "",
        "flags": {},
        "payment": {},
        "shipment": {},
        "entity_type": "order_structured",
    }


def _run_full_form_save(old: dict, incoming: dict) -> list:
    """route 가 하는 순서 그대로 태운다(운영상태 보존 → DATA-01 projection)."""
    _preserve_operational_structured_state(old, incoming)
    return project_structured_form(old, incoming)


def test_full_form_save_preserves_drawing_wizard():
    """폼 저장 한 번으로 마법사 상태가 통째로 사라지지 않는다(주문 5177 회귀)."""
    old = _server_state()
    expected = _saved_wizard()
    incoming = _form_payload()

    _run_full_form_save(old, incoming)

    assert "drawing_wizard" in incoming, "폼 저장 한 번에 drawing_wizard 가 통째로 사라졌다"
    assert incoming["drawing_wizard"] == expected


def test_full_form_save_preserves_wizard_objects_pending_versions():
    """캔버스 오브젝트·pending·versions 를 각각 따로 확인한다(빈 껍데기 보존 금지)."""
    old = _server_state()
    incoming = _form_payload()

    _run_full_form_save(old, incoming)

    wizard = incoming["drawing_wizard"]
    sheets = wizard["sheets"]
    assert len(sheets) == 1
    assert sheets[0]["objects"] == [
        {"type": "pen", "id": "o1", "pts": [[10, 10], [20, 20], [30, 15]]}
    ], "시트는 남았는데 objects 가 비었다 — 09-10 사고와 같은 결과다"
    assert wizard["pending"] == {
        "s-a": {"key": "orders/5177/drawing_wizard/pending/s-a.png"}
    }
    assert wizard["versions"] == [
        {"v": 1, "key": "orders/5177/drawing_wizard/versions/v1_s-a.json"}
    ]


def test_preserved_wizard_is_a_copy_not_the_old_object():
    """보존은 deepcopy 여야 한다 — 저장본을 고치다 old_sd(감사 비교 기준)까지 바뀌면 안 된다."""
    old = _server_state()
    incoming = _form_payload()

    _run_full_form_save(old, incoming)

    incoming["drawing_wizard"]["sheets"][0]["objects"].append({"type": "rect"})
    assert len(old["drawing_wizard"]["sheets"][0]["objects"]) == 1


def test_full_form_save_preserves_unknown_server_owned_key():
    """목록에 이름을 적어야만 사는 구조를 끝냈다는 증거 — 미지의 서버 소유 키도 살아남는다."""
    old = _server_state()
    old["some_future_server_key"] = {"created_by": "another_api", "rows": [1, 2, 3]}
    incoming = _form_payload()

    _run_full_form_save(old, incoming)

    assert incoming["some_future_server_key"] == {
        "created_by": "another_api",
        "rows": [1, 2, 3],
    }


def test_as_lifecycle_is_still_removable():
    """음성 대조군: 폼 저장이 **의도적으로** 지우는 as_lifecycle 은 여전히 제거된다.

    ``_force_preserve_as_lifecycle``(erp_orders_structured.py:505-519)은 서버값이 dict 가
    아니면 폼이 보낸 stale 스냅샷을 pop 한다. 보존 규칙이 "전부 되살리는" 과잉 수정이었다면
    이 pop 이 무효가 된다.
    """
    old = _server_state()
    old["as_lifecycle"] = None
    incoming = _form_payload()
    incoming["as_lifecycle"] = {"current_cycle_id": "stale", "cycles": []}

    _run_full_form_save(old, incoming)

    assert "as_lifecycle" not in incoming, "의도적 제거 대상이 보존 규칙에 되살아났다"


def test_form_owned_keys_still_overwritten():
    """음성 대조군 2: 폼이 소유한 키(items·parties)는 클라이언트 값이 이긴다."""
    old = _server_state()
    incoming = _form_payload()
    incoming["items"] = [{"price": 7000}]
    incoming["parties"] = {"customer": {"name": "바뀐이름"}}

    _run_full_form_save(old, incoming)

    assert incoming["items"] == [{"price": 7000}]
    assert incoming["parties"]["customer"]["name"] == "바뀐이름"


def test_absent_wizard_is_not_invented():
    """마법사를 한 번도 안 쓴 주문에 키를 만들어 넣지 않는다."""
    old = {"items": [], "parties": {}}
    incoming = _form_payload()

    _run_full_form_save(old, incoming)

    assert "drawing_wizard" not in incoming
