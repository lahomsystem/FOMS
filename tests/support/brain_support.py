"""master brain 시험 재료 — 합성 사람 · 합성 항목 · 링크 · 합성 계산기 정본 · 합성 설정(세션을 받아 SQLite · PostgreSQL 레인이
같이 쓴다).

손으로 꾸민 합성 이름 · 글만 쓴다 — 손님 글 · 직원 이름 · 비밀값 없음. 글에 숫자를 넣지 않는다(숫자 관문은 따로 시험).
계산기 정본은 따로 DB 라 시험에서는 합성 목록(:data:`SYNTH_CATALOG` — 값은 꾸민 수)을 끼운다(:func:`link`).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from werkzeug.security import generate_password_hash

from foms.services.brain.apply import apply_change
from foms.services.brain.external import catalog_source
from foms.services.brain.proposals import Proposer, propose_create, propose_link
from foms.services.brain.store import current_object
from foms.services.wdcalculator.catalog import Catalog
from models import SystemSetting, User

#: UTC naive — 한국 2026-11-02(월) 10시.
NOW = datetime.datetime(2026, 11, 2, 1, 0)
REASON = "합성 시험 까닭"
#: 합성 계산기 정본 — 제품 1 · 7, 옵션 3:5(``calc:product/<id>`` · ``calc:option/<카테고리>:<옵션>``). 값은 꾸민 수.
SYNTH_CATALOG = Catalog(
    products=({"id": 1, "name": "합성 제품 하나", "pricing_type": "30cm", "price_30cm": 1000, "price_1cm": 40},
              {"id": 7, "name": "합성 문짝 제품", "pricing_type": "1m", "price_1m": 2000}),
    option_categories=({"id": 3, "name": "합성 옵션 묶음", "options": [{"id": 5, "name": "합성 손잡이", "price": 300}]},))


def synth_catalog() -> Catalog:
    """합성 계산기 정본(읽는 함수 꼴)."""
    return SYNTH_CATALOG


def setting(session: Any, key: str, value: Any = None) -> SystemSetting:
    """합성 설정 한 줄(``setting:<키>`` 가리킴이 실재하게)."""
    row = SystemSetting(setting_key=key, setting_value=value if value is not None else {"합성": []}, description="합성")
    session.add(row)
    session.flush()
    return row


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
    """링크 더하기 제안 → 반영(계산기 정본은 합성 목록 — :data:`SYNTH_CATALOG`)."""
    with catalog_source(synth_catalog):
        change = propose_link(session, op="link_add", kind=kind, from_key=from_key, to_key=to_key, reason=REASON,
                              proposer=Proposer.user(actor.id), now=now)
        return apply_change(session, change.id, actor=actor, now=now)
