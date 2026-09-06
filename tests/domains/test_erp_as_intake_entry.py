"""AS-INTAKE-01 — ERP 주문 화면에 **첫 AS 접수** 입구가 살아 있는지 잠근다.

원래 입구는 본공정 드롭다운의 'AS접수' 옵션이었고, 저장 시 `nextStage === 'AS_RECEIVED'`
를 보고 AS 접수 모달을 열었다. 2026-09-04 `308366961` 이 그 옵션을 지웠다 — 값을 실제로
쓰면 `workflow.stage` 가 덮여 도면·생산·시공 큐에서 주문이 영구 이탈했기 때문이다(운영
실측 62건). 옳은 판단이었지만 **그 옵션에만 의존하던 트리거가 남아** 첫 AS 접수 경로가
통째로 사라졌고, 시공 화면과 AS 대시보드 재접수만 남았다(2026-09-07 사용자 제보).

그래서 stage 를 건드리지 않는 버튼으로 같은 모달을 연다. 이 계약은 그 버튼과 배선이
다시 조용히 사라지지 않게 한다 — 사라져도 화면을 안 열어보면 아무도 모르는 종류의 결함이다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PC_TPL = REPO_ROOT / "templates" / "orders" / "partials" / "erp_order_tab.html"
MOBILE_TPL = REPO_ROOT / "templates" / "orders" / "partials" / "erp_order_tab_mobile.html"
SHARED_JS = REPO_ROOT / "static" / "js" / "orders" / "erp-order-shared.js"
JS_INCLUDE = REPO_ROOT / "templates" / "orders" / "partials" / "erp_order_js.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("tpl", [PC_TPL, MOBILE_TPL], ids=["pc", "mobile"])
def test_as_intake_button_exists(tpl: Path) -> None:
    """PC·모바일 양쪽에 첫 AS 접수 버튼이 있다."""
    html = _read(tpl)
    assert "data-erp-as-receive-open" in html, f"{tpl.name} 에 AS 접수 입구가 없다"
    assert "erp_as_can_receive" in html


@pytest.mark.parametrize("tpl", [PC_TPL, MOBILE_TPL], ids=["pc", "mobile"])
def test_intake_and_reregister_are_mutually_exclusive(tpl: Path) -> None:
    """AS 가 열려 있으면 '접수 수정', 아니면 '접수' — 둘이 동시에 뜨지 않는다."""
    html = _read(tpl)
    assert "{% elif erp_as_can_receive %}" in html, (
        f"{tpl.name}: 접수 버튼이 재접수와 elif 로 갈려 있어야 한다"
    )


@pytest.mark.parametrize("tpl", [PC_TPL, MOBILE_TPL], ids=["pc", "mobile"])
def test_intake_guard_excludes_open_as_and_unsaved_orders(tpl: Path) -> None:
    """저장된 주문이고 AS 가 열려 있지 않을 때만 입구를 낸다."""
    html = _read(tpl)
    assert "not erp_as_can_reregister" in html
    assert "order.id" in html


def test_js_binds_the_intake_button() -> None:
    """버튼이 실제로 AS 접수 모달을 연다(배선 없는 버튼은 더 나쁘다)."""
    js = _read(SHARED_JS)
    assert "data-erp-as-receive-open" in js, "버튼 배선이 없다"
    marker = js.index("data-erp-as-receive-open")
    tail = js[marker:marker + 1600]
    assert "erpOpenAsReceiveModal" in tail, "버튼이 AS 접수 모달을 열지 않는다"
    assert "erpAsReceiveBound" in tail, "중복 바인딩 가드가 없다"


def test_intake_binding_does_not_touch_workflow_stage() -> None:
    """입구가 stage 를 쓰지 않는다 — 그게 2026-09-04 에 옵션을 지운 이유다."""
    js = _read(SHARED_JS)
    marker = js.index("data-erp-as-receive-open")
    tail = js[marker:marker + 1600]
    for forbidden in ("erp-workflow-stage", "workflow.stage ="):
        assert forbidden not in tail, f"AS 접수 입구가 stage 를 건드린다: {forbidden}"


def test_stage_dropdown_has_no_as_options() -> None:
    """음성 대조군 — 드롭다운에 AS 옵션이 **다시 생기지 않았다**(그 자리로 돌아가면 안 된다)."""
    for tpl in (PC_TPL, MOBILE_TPL):
        html = _read(tpl)
        for forbidden in ('<option value="AS_RECEIVED"', '<option value="AS_COMPLETED"',
                          '<option value="AS">'):
            assert forbidden not in html, f"{tpl.name}: {forbidden} 가 되살아났다"


def test_shared_js_pin_moved_past_the_removal_commit() -> None:
    """JS 를 고쳤으면 ``?v`` 핀이 올라가야 한다(SW staticCacheFirst 가 낡은 파일을 준다)."""
    include = _read(JS_INCLUDE)
    assert "erp-order-shared.js" in include
    line = next(l for l in include.splitlines() if "erp-order-shared.js" in l)
    pin = line.split("?v=")[1].split('"')[0]
    assert pin > "20260904c", f"핀이 안 올라갔다: {pin}"
