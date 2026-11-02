"""master brain 시험 재료 — 합성 사람 · 합성 항목 · 링크(세션을 받아 SQLite · PostgreSQL 레인이 같이 쓴다).

손으로 꾸민 합성 이름 · 글만 쓴다 — 금액 · 손님 글 · 직원 이름 · 비밀값 없음. 글에 숫자를 넣지 않는다(숫자 관문은 따로 시험).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from werkzeug.security import generate_password_hash

from foms.services.brain.apply import apply_change
from foms.services.brain.proposals import Proposer, propose_create, propose_link
from foms.services.brain.store import current_object
from models import User

#: UTC naive — 한국 2026-11-02(월) 10시.
NOW = datetime.datetime(2026, 11, 2, 1, 0)
REASON = "합성 시험 까닭"


def person(session: Any, username: str, *, role: str = "ADMIN", team: Optional[str] = None, active: bool = True,
           partner_org_id: Optional[int] = None) -> User:
    """합성 계정(이름은 늘 '합성')."""
    user = User(username=username, password=generate_password_hash("pw"), name="합성", role=role, team=team,
                is_active=active, partner_org_id=partner_org_id)
    session.add(user)
    session.flush()
    return user


def values(name: str, *, text: Optional[str] = None, status: str = "active", confidence: str = "confirmed",
           visibility: str = "all", **extra: Any) -> dict[str, Any]:
    """값 칸(나머지는 비움)."""
    return {"name": name, "text": text if text is not None else f"합성 설명 {name}", "status": status,
            "confidence": confidence, "visibility": visibility, **extra}


def create(session: Any, actor: Any, key: str, *, item_type: str = "product_line", layer: str = "common",
           brand: str = "COMMON", now: datetime.datetime = NOW, **vals: Any) -> Any:
    """만들기 제안 → 반영(커밋은 하지 않음). 지금 줄을 돌려준다."""
    change = propose_create(session, key=key, brand=brand, layer=layer, item_type=item_type,
                            values=values(vals.pop("name", key.split("/")[-1]), **vals), reason=REASON,
                            proposer=Proposer.user(actor.id), now=now, known="")
    apply_change(session, change.id, actor=actor, now=now)
    return current_object(session, key)


def link(session: Any, actor: Any, kind: str, from_key: str, to_key: str, *, now: datetime.datetime = NOW) -> Any:
    """링크 더하기 제안 → 반영."""
    change = propose_link(session, op="link_add", kind=kind, from_key=from_key, to_key=to_key, reason=REASON,
                          proposer=Proposer.user(actor.id), now=now)
    return apply_change(session, change.id, actor=actor, now=now)
