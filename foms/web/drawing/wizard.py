"""도면 작업실 "도면 마법사" 페이지 라우트 (P1 골격).

기존 ``erp_drawing_workbench_bp`` 에 위저드 에디터 페이지 라우트를 부착한다
(신규 Blueprint 없음). 실제 데이터는 페이지 JS가 GET API로 가져오므로 템플릿에는
최소 ``wizard_config`` 만 전달한다. P2에서 템플릿/에디터를 전면 교체한다.
"""

from typing import Any

from flask import flash, g, redirect, render_template, request, url_for

from db import get_db
from models import Order
from foms.web.auth import login_required
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.services.drawing_wizard_part_memory import load_policy as load_part_memory_policy
from foms.services.orders.as_drawing_views import wizard_config_view
from foms.services.orders.drawing_transfer import is_drawing_hotfix_stage
from foms.services.orders.erp_policy_permissions import can_transfer_drawing
from foms.web.drawing.workbench import erp_drawing_workbench_bp


_WIZARD_UIS = ('v1', 'v2')
_WIZARD_UI_COOKIE = 'dws_ui'


def _wizard_ui() -> str:
    """화면 갈래 — ``?ui=v1|v2`` 가 먼저, 없으면 쿠키 ``dws_ui``(wizard-ui-switch.js 가 기억), 없으면 v1.

    V2(칸 자동 배치 화면)는 같은 도면 데이터를 다른 화면으로 보여 준다(설계서
    ``docs/plans/2026-10-26-drawing-wizard-v2-spec.md``) — 저장·권한은 갈래와 무관하다.
    """
    for raw in (request.args.get('ui'), request.cookies.get(_WIZARD_UI_COOKIE)):
        if raw in _WIZARD_UIS:
            return raw
    return 'v1'


def _save_send_config(current_user: Any, order: Order) -> dict:
    """[저장] 창(save-send.js)이 칸을 잠그고 숨기는 데 쓰는 값 — 화면 표시용이다. 전달·PUSH 권한은 서버가 다시 검사한다.

    설계서 ``docs/specs/2026-11-05-wizard-save-send-options_SPEC.md`` §5.
    """
    return {
        'user_id': int(getattr(current_user, 'id', 0) or 0),
        'can_transfer': bool(current_user and can_transfer_drawing(current_user, order)),
        'hotfix_stage': bool(is_drawing_hotfix_stage(order)),
        'is_partner': bool(getattr(order, 'partner_org_id', None)),
    }


@erp_drawing_workbench_bp.route('/drawing-workbench/<int:order_id>/wizard')
@login_required
def erp_drawing_workbench_wizard(order_id: int) -> Any:
    """도면 마법사 에디터 페이지(데스크톱 전용). 주문 로드→404 리다이렉트→렌더."""
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    order = db.query(Order).filter(
        Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True)
    ).first()
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('erp_drawing_workbench.erp_drawing_workbench_dashboard'))

    sd = _ensure_dict(order.structured_data)
    customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    can_save = bool(
        current_user
        and (current_user.role == 'ADMIN' or is_drawing_workbench_participant(current_user, order))
    )
    wizard_ui = _wizard_ui()
    # 그림 종류 기억(실시간 학습) 켜고 끄기 — 문턱은 서버가 판정한다(설계서 2026-10-26-drawing-part-memory-spec §3.7).
    memory = load_part_memory_policy(db)
    wizard_config = {'order_id': order.id, 'can_save': can_save, 'ui': wizard_ui,
                     'part_memory': {k: bool(memory[k]) for k in ('store', 'follow', 'spread')},
                     'save_send': _save_send_config(current_user, order),
                     # 완료 주문 AS 도면(설계서 2026-11-11-as-drawing-after-completion §4.3) — 아니면 None.
                     'as_drawing': wizard_config_view(order, sd)}
    return render_template(
        'drawing/wizard.html',
        order=order,
        customer_name=customer_name,
        can_save=can_save,
        wizard_config=wizard_config,
        wizard_ui=wizard_ui,
    )
