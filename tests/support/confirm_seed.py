"""테스트용 도면 확정 시드 헬퍼 — 고객컨펌 → 생산 도면 게이트(2차 묶음 2a-2) 뒤 공용.

게이트는 허용 목록이다(M3): ``drawing_status == 'CONFIRMED'`` 일 때만 고객컨펌 승인·제작 시작
(CONFIRM 호환)·전이 엔진 CUSTOMER_CONFIRM/PRODUCTION_START 가 통과한다. 그래서 도면 기록 없이
CONFIRM 주문을 시드해 그 경로를 부르던 테스트는 이 헬퍼로 "영업이 수령 확정한 최신본" 을 얹는다.

모양은 실제 라우트(전달 → 수령 확정)가 남기는 키와 같다 — 최상위 ``drawing_status``·현재본·
TRANSFER·CONFIRM_RECEIPT 이력.
"""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_DRAWING_KEY = "orders/0/drawing_wizard/exports/v1.png"


def confirmed_drawing_sd(**overrides: Any) -> dict:
    """도면이 수령 확정(CONFIRMED)된 상태의 structured_data 조각.

    ``overrides`` 는 마지막에 얹어 아무 키나 덮어쓴다(예: ``drawing_status='RETURNED'``).
    """
    files = [{"key": DEFAULT_DRAWING_KEY, "filename": "v1.png"}]
    sd: dict[str, Any] = {
        "drawing_status": "CONFIRMED",
        "drawing_confirmed_at": "2026-09-16T09:00:00",
        "drawing_confirmed_by": "영업",
        "drawing_current_files": copy.deepcopy(files),
        "drawing_transfer_history": [
            {"action": "TRANSFER", "transferred_at": "2026-09-15 10:00:00",
             "files": copy.deepcopy(files), "files_count": 1},
            {"action": "CONFIRM_RECEIPT", "at": "2026-09-16 09:00:00",
             "files": copy.deepcopy(files), "files_count": 1},
        ],
    }
    sd.update(overrides)
    return sd


def with_confirmed_drawing(sd: dict | None, **overrides: Any) -> dict:
    """``sd`` 사본에 :func:`confirmed_drawing_sd` 를 얹어 돌려준다(원본은 그대로 둔다)."""
    merged = copy.deepcopy(sd or {})
    merged.update(confirmed_drawing_sd(**overrides))
    return merged


def drawing_for_stage(stage: str | None, **overrides: Any) -> dict:
    """고객컨펌(영문 ``CONFIRM``·한글 ``고객컨펌``) 단계면 확정 도면 조각, 아니면 빈 dict.

    파일마다 있는 주문 시드 헬퍼에 ``sd.update(drawing_for_stage(stage))`` 한 줄로 얹는다 —
    다른 단계 시드는 그대로 둔다.
    """
    if str(stage or "").strip() not in ("CONFIRM", "고객컨펌"):
        return {}
    return confirmed_drawing_sd(**overrides)


# --------------------------------------------------------------------------- #
# 라우트 테스트 공용 — 사용자·로그인·고객컨펌 주문 시드(2a-2 게이트 테스트 두 파일이 같이 쓴다)
# --------------------------------------------------------------------------- #
class SeedActor:
    """요청 사이에 세션이 닫혀도 안전한 사용자 식별값 묶음."""

    def __init__(self, user: Any) -> None:
        self.id = int(user.id)
        self.username = user.username
        self.role = user.role
        self.team = user.team
        self.name = user.name


def seed_user(username: str, *, role: str = "STAFF", team: str | None = "SALES") -> SeedActor:
    """활성 사용자 1명을 커밋하고 :class:`SeedActor` 로 돌려준다."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return SeedActor(user)


def login_as(client: Any, actor: SeedActor) -> None:
    """테스트 클라이언트 세션을 ``actor`` 로 바꾼다."""
    with client.session_transaction() as sess:
        sess["user_id"] = actor.id
        sess["username"] = actor.username
        sess["role"] = actor.role


def seed_erp_order(stage: str, *, sales: SeedActor | None = None, drafter: SeedActor | None = None,
                   erp_stage: str | None = None, **sd_extra: Any) -> int:
    """ERP 주문 1건(영업·도면 담당 명시 지정)을 커밋하고 id 를 돌려준다.

    ``stage`` 는 ``workflow.stage`` 원문(한글 '고객컨펌' 가능), ``erp_stage`` 는 색인 컬럼 값
    (없으면 ``stage``). ``sd_extra`` 는 structured_data 최상위에 얹는다.
    """
    from db import db_session
    from models import Order

    assignments: dict[str, Any] = {}
    if sales is not None:
        assignments["sales_assignee_user_ids"] = [sales.id]
    if drafter is not None:
        assignments["drawing_assignee_user_ids"] = [drafter.id]
    sd: dict[str, Any] = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": "게이트 고객"},
                    "manager": {"name": sales.name if sales else "영업"}},
        "assignments": assignments,
    }
    sd.update(sd_extra)
    order = Order(
        received_date="2026-09-29", customer_name="게이트 고객", phone="010-2929-2929",
        address="서울 테헤란로 29", product="붙박이장", status=erp_stage or stage,
        manager_name=sales.name if sales else "영업", is_erp_order=True,
        erp_stage_code=erp_stage or stage, structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def reload_order(order_id: int) -> Any:
    """identity map 을 비우고 DB 값을 다시 읽는다."""
    from db import db_session
    from models import Order

    db_session.expire_all()
    return db_session.get(Order, order_id)


def order_events(order_id: int, event_type: str) -> list:
    """주문의 ``event_type`` 이벤트 전부(id 순)."""
    from db import db_session
    from models import OrderEvent

    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id)
        .all()
    )
