"""네이버 수집용 시스템 계정 정책 (NAVER-INGEST-01 §3.5 / T0).

수집에는 사람 actor 가 없는데 :func:`~foms.services.orders.order_create.create_order` 는
actor 와 **활성 SALES owner** 를 요구한다(ASSIGNMENT-00: owner row 가 authorization 근거).
그 자리를 메우는 전용 계정 2개의 목표 상태와 보정 로직을 여기 둔다.

**로그인 잠금 방식**: ``is_active=False`` 로 잠글 수 없다 — owner 계약이 활성 SALES 를
요구하기 때문이다. 대신 아무도 모르는 난수 비밀번호를 해시해 넣는다. 원문은 생성 즉시 버려
어디에도 저장·출력하지 않으므로 로그인 경로로 들어올 수 없다.

앱 부팅 없이 세션만 있으면 돌아간다(``app`` 을 import 하지 않는다) — 부팅 시 AUTO-INIT
backfill 이 공유 DB 에 쓰는 부작용 없이 운영 DB 에도 적용할 수 있어야 하기 때문이다.
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from foms.services.integrations.naver_commerce.constants import (
    ACTOR_USERNAME,
    OWNER_USERNAME,
)
from models import User

#: 계정별 목표 상태. 여기서 벗어나면 :func:`ensure_account` 가 바로잡는다.
SPECS: tuple[dict[str, str], ...] = (
    {
        "username": ACTOR_USERNAME,
        "name": "네이버 수집봇",
        "role": "MANAGER",
        "team": "CS",
        "why": "수집 주문의 이벤트 author / assigned_by",
    },
    {
        "username": OWNER_USERNAME,
        "name": "미배정 (네이버 수집)",
        "role": "STAFF",
        "team": "SALES",
        "why": "미배정 보류함 owner — 활성 SALES 여야 create_order 계약을 만족한다",
    },
)


def locked_password_hash() -> str:
    """아무도 모르는 난수 비밀번호의 해시(원문은 반환하지 않는다)."""
    return generate_password_hash(secrets.token_urlsafe(48))


def ensure_account(session: Session, spec: dict, *, reset_password: bool = False) -> dict[str, Any]:
    """계정 하나를 목표 상태로 맞춘다(멱등). 무엇을 했는지 보고한다.

    기존 계정의 비밀번호는 건드리지 않는다 — 운영자가 일부러 바꿔 쓰는 경우를 덮지 않기
    위해서다(``reset_password=True`` 로 명시할 때만 재잠금).

    Args:
        session: DB 세션(커밋은 호출자).
        spec: :data:`SPECS` 항목.
        reset_password: 기존 계정도 난수 비밀번호로 재잠금할지.

    Returns:
        ``{"username", "action"("created"|"repaired"|"ok"), "id", "fixed"[]}``.
    """
    user = session.query(User).filter(User.username == spec["username"]).first()
    if user is None:
        user = User(
            username=spec["username"], password=locked_password_hash(),
            name=spec["name"], role=spec["role"], team=spec["team"],
            is_active=True, approval_status="ACTIVE",
        )
        session.add(user)
        session.flush()
        return {"username": spec["username"], "action": "created",
                "id": int(user.id), "fixed": []}

    fixed: list[str] = []
    for field in ("role", "team"):
        if (getattr(user, field) or "") != spec[field]:
            setattr(user, field, spec[field])
            fixed.append(field)
    if not user.is_active:
        user.is_active = True
        fixed.append("is_active")
    if (user.approval_status or "ACTIVE") != "ACTIVE":
        user.approval_status = "ACTIVE"
        fixed.append("approval_status")
    if reset_password:
        user.password = locked_password_hash()
        fixed.append("password(잠금 재설정)")
    session.flush()
    return {
        "username": spec["username"],
        "action": "repaired" if fixed else "ok",
        "id": int(user.id), "fixed": fixed,
    }


def ensure_ingest_accounts(session: Session, *, reset_password: bool = False) -> list[dict[str, Any]]:
    """계정 2개를 모두 목표 상태로 맞춘다(커밋은 호출자)."""
    return [ensure_account(session, spec, reset_password=reset_password) for spec in SPECS]


class IngestAccountError(RuntimeError):
    """수집용 시스템 계정이 없거나 정책에 맞지 않는다 — 주문을 만들지 않는다."""


def resolve_ingest_account_ids(session: Session) -> tuple[int, int]:
    """actor(봇)·owner(미배정 보류함) user id 를 확정한다.

    owner 는 ``create_order`` 의 owner 계약(활성 SALES)을 그대로 만족해야 한다. 아니면
    주문을 만들지 않는다 — 계정이 잘못된 채로 만들면 엉뚱한 사람에게 배정된다.

    이 함수가 ``ingest`` 가 아니라 여기 있는 이유: 주문 생성은 web 에서도 일어나는데
    (관리 화면 "주문 만들기") web 이 ``ingest`` 를 import 하면 "네이버 HTTP 는 WORKER
    단일 출구" 계약 테스트가 red 가 된다. 이 모듈은 DB 만 본다.

    Args:
        session: DB 세션.

    Returns:
        ``(actor_user_id, owner_user_id)``.

    Raises:
        IngestAccountError: 계정 부재·비활성·비SALES owner.
    """
    from foms.services.orders.order_mutation_policy import normalize_team

    actor = session.query(User).filter(User.username == ACTOR_USERNAME).first()
    owner = session.query(User).filter(User.username == OWNER_USERNAME).first()
    if actor is None:
        raise IngestAccountError(f"수집 actor 계정이 없다: {ACTOR_USERNAME} (T0 선행 작업)")
    if owner is None:
        raise IngestAccountError(f"미배정 보류함 계정이 없다: {OWNER_USERNAME} (T0 선행 작업)")
    if not owner.is_active or normalize_team(owner.team) != "SALES":
        raise IngestAccountError(
            f"{OWNER_USERNAME} 는 활성 SALES 여야 한다(현재 active={owner.is_active}, team={owner.team})."
        )
    return (int(actor.id), int(owner.id))


__all__ = ["IngestAccountError", "SPECS", "ensure_account", "ensure_ingest_accounts",
           "locked_password_hash", "resolve_ingest_account_ids"]
