"""생산 작업 시트 [패킹] 칸 재료(설계서 2026-11-23 '승인 때 고친 것' 6 ④) — 템플릿 전역 함수, 쿼리 0.

생산팀은 태블릿 작업 시트에서 패킹을 연다(폰 출고 · 시공 카드가 아니라). 그 시트 템플릿(``templates/production/sheet.html``)은
다른 일꾼 파일이라 이 묶음은 끼울 조각(``templates/shipment/partials/packing_prod_entry.html``)만 만들고, 조각이 이 함수를 부른다.
주문 행은 라우트가 이미 읽은 것을 세션 identity map 에서 꺼낸다(없으면 칸을 안 그린다 — 새로 읽지 않는다).
"""

from __future__ import annotations

from typing import Any, Optional

from flask import g, has_request_context
from sqlalchemy.orm.util import identity_key

from db import get_db
from foms.services.production.factory_constants import DEFAULT_FACTORY
from foms.services.shipment.packing_access import packing_factories
from foms.services.shipment.packing_factory import factory_groups, packing_glance, stored_packing
from models import Order


def packing_prod_entry(order_id: Any) -> Optional[dict[str, Any]]:
    """[패킹] 칸을 그릴지 · 무엇을 쓸지 — 패킹을 체크하는 사람이고 이 주문에 내 공장 줄이 있을 때만.

    Args:
        order_id: 작업 시트 주문 번호.

    Returns:
        ``{order_id, split, text, departed}`` 또는 None. split = 공장 꼴(새 모듈이 연다) · 아니면 지금 목록(옛 모듈).
        text = 숫자 글 — 공장 꼴은 내 공장 몫("2공장 2/3", 관리자는 "1공장 3/4 · 2공장 0/3"), 지금 목록은 "3/6", 저장 전이면 빈 글.
    """
    user = getattr(g, "current_user", None) if has_request_context() else None
    mine = packing_factories(user)
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return None
    if not mine:
        return None
    order = get_db().identity_map.get(identity_key(Order, oid))
    if order is None:
        return None
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    packing = stored_packing(sd)
    departed = bool((packing or {}).get("departed_at"))
    glance = packing_glance(sd)
    if glance is None:  # 1공장뿐 — 모든 줄이 1공장 몫
        if DEFAULT_FACTORY not in mine:
            return None
        items = [r for r in (packing or {}).get("items") or [] if isinstance(r, dict)]
        text = f"{sum(1 for r in items if r.get('checked'))}/{len(items)}" if items else ""
        return {"order_id": oid, "split": False, "text": text, "departed": departed}
    own = [grp for grp in factory_groups(sd) if grp["factory"] in mine]
    if not own:
        return None
    # 단추 칸이 좁아 내 공장 몫만("2공장 2/3") — 두 공장을 다 체크하는 사람(관리자)은 둘 다
    text = " · ".join(f"{grp['label']} {grp['checked']}/{grp['total']}" for grp in own) if glance["present"] else ""
    return {"order_id": oid, "split": True, "text": text, "departed": departed}
