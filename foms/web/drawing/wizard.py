"""도면 작업실 "도면 마법사" 페이지 라우트 (P1 골격).

기존 ``erp_drawing_workbench_bp`` 에 위저드 에디터 페이지 라우트를 부착한다
(신규 Blueprint 없음). 실제 데이터는 페이지 JS가 GET API로 가져오므로 템플릿에는
최소 ``wizard_config`` 만 전달한다. P2에서 템플릿/에디터를 전면 교체한다.
"""

from typing import Any

from flask import flash, g, redirect, render_template, url_for

from db import get_db
from models import Order
from foms.web.auth import login_required
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.web.drawing.workbench import erp_drawing_workbench_bp


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
    wizard_config = {'order_id': order.id, 'can_save': can_save}
    return render_template(
        'drawing/wizard.html',
        order=order,
        customer_name=customer_name,
        can_save=can_save,
        wizard_config=wizard_config,
    )
