"""생산팀 첫 화면 — 전체 주문 한 줄(설계서 §12, 2026-11-09 D10·D12).

``dashboard.py`` 와 같은 Blueprint(``erp_production_page``)에 라우트만 더한다(파일 500줄 래칫).
``foms/web/production/__init__.py`` 가 이 모듈을 import 해야 라우트가 붙는다.
"""

from __future__ import annotations

import datetime

from flask import abort, g, render_template

from db import get_db
from models import Order
from foms.api.production.orders import _PRODUCTION_DEFECT_REASONS
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.production_sheet_view import build_production_sheet_view
from foms.services.production_home_read_model import (
    build_production_home_rows,
    production_home_counts,
    production_home_groups,
)
from foms.web.auth import login_required
from foms.web.production.dashboard import erp_production_page_bp

_HOME_TEAMS = ('CS', 'SALES', 'PRODUCTION')
_KST = datetime.timezone(datetime.timedelta(hours=9))


def _require_home_user():
    """생산 홈·전체 화면 시트를 볼 수 있는 사람(관리자·CS·영업·생산, 협력사 제외). 아니면 403."""
    user = getattr(g, 'current_user', None)
    allowed = bool(user) and getattr(user, 'partner_org_id', None) is None and (
        user.role == 'ADMIN' or team_has_capability(getattr(user, 'team', None), _HOME_TEAMS)
    )
    if not allowed:
        abort(403)
    return user


@erp_production_page_bp.route('/production/home')
@login_required
def erp_production_home():
    """생산팀 첫 화면 — 전체 주문 한 줄(시공일 순, 큰 글자 = 지금 단계). 설계서 §12 · D10·D12.

    볼 수 있는 사람 = 공정 체크를 할 수 있는 사람과 같다(관리자·CS·영업·생산, ``_PRODUCTION_STEPS_EDIT_TEAMS``
    와 같은 답). 협력사 계정은 없다. 금액은 뷰 모델에 싣지 않는다(D7).
    """
    db = get_db()
    user = _require_home_user()
    rows = build_production_home_rows(db, user)
    today = get_today_kst()
    now_kst = datetime.datetime.now(_KST)
    return render_template(
        'production/home.html',
        rows=rows,
        groups=production_home_groups(rows),
        counts=production_home_counts(rows),
        today_label=f"{today.month}월 {today.day}일 ({'월화수목금토일'[today.weekday()]})",
        loaded_at_hm=now_kst.strftime('%H:%M'),
        loaded_at_iso=now_kst.isoformat(timespec='seconds'),
    )


@erp_production_page_bp.route('/production/sheet/<int:order_id>')
@login_required
def erp_production_sheet_page(order_id: int):
    """전체 화면 작업 시트(설계서 §12.2, 안 2) — 도면 6할 + 고객·만들 것·공정·불량·단추.

    옆 시트(``erp_production_tablet_sheet``)와 같은 뷰 모델에 전체 화면 키를 더한다(``full=True``).
    단추는 옆 시트와 같은 ``data-tablet-sheet-action`` 계약(tablet-domain-sheets.js, 이 페이지는 기기 무관).
    """
    db = get_db()
    user = _require_home_user()
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None:
        abort(404)
    sheet = build_production_sheet_view(db, order, user, full=True)
    return render_template(
        'production/sheet.html',
        order=sheet,
        is_admin=bool(user and user.role == 'ADMIN'),
        defect_reasons=_PRODUCTION_DEFECT_REASONS,
    )
