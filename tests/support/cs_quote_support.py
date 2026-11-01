"""견적(C10-6) 시험 재료 — 처음 채우기 파일(공개)의 제품 · 옵션, 견적 재료 · 계산기 · 확인 날 · 가짜 뽑기 두뇌.

시험 파일에는 금액 숫자를 적지 않는다 — 기대값은 서버 계산(계약 시험이 화면 계산과 원 단위로 맞춘 함수)이나 node 화면
계산을 그 자리에서 돌려 얻는다. 손님 글은 합성 글이다. 초안 바퀴 재료(가짜 두뇌 · 채널톡)는 ``tests/domains/test_cs_drafting.py``.
"""

from __future__ import annotations

import datetime
import functools
import itertools
import json
from decimal import Decimal
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.cs_agent import quote_brain as qb
from foms.services.cs_agent import quote_calc as qc
from foms.services.cs_agent import quote_check as qk
from foms.services.cs_agent import quote_rules as qr
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.drafting_pass import DraftPass
from foms.services.cs_agent.knowledge_doc import KnowledgeItem
from foms.services.wdcalculator import catalog as cat
from foms.services.wdcalculator import pricing
from models import SystemSetting, User
from tests.support.cs_agent_fakes import at

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))["products"]
CATEGORIES = json.loads((ROOT / "data" / "additional_options.json").read_text(encoding="utf-8"))["categories"]
LAHOM = [p for p in PRODUCTS if pricing.product_brand(p) == pricing.BRAND_LAHOM]
#: 라홈 30cm 제품 — 규칙 칸이 비고 이름에 '슬라이딩'이 없어 '모름'(2400mm 미만은 사람에게).
MOLD = next(p for p in LAHOM if p["pricing_type"] == "30cm" and qr.rule_of(p) == qr.RULE_UNKNOWN)
#: 라홈 30cm 슬라이딩(이름으로 slide).
SLIDING = next(p for p in LAHOM if p["pricing_type"] == "30cm" and qr.rule_of(p) == qr.RULE_SLIDE)
OTHER = next(p for p in LAHOM if p["pricing_type"] == "1m")
HAUD = next(p for p in PRODUCTS if pricing.product_brand(p) == pricing.BRAND_HAUD)
OPTION = next(f"{c['id']}:{o['id']}" for c in CATEGORIES for o in c["options"] if (o.get("price") or 0) > 0)
NOW = at(2, 9)  # 2026-11-02 월요일 09:00 KST(초안 바퀴 시험과 같은 때)
QUOTE_TEXT = "주황고래손님표지 슬라이딩장 가로 2400mm 견적 부탁드려요"


def catalog(*, extra=(), categories=(), seed=False, products=None):
    """계산기 설정(처음 채우기 파일 값 + 합성 제품 · 옵션)."""
    return cat.Catalog(tuple([*(PRODUCTS if products is None else products), *extra]),
                       tuple([*CATEGORIES, *categories]), seed)


def checked(days=1.0, **kw):
    """확인 날 판정 재료 — ``days`` 일 전에 버튼을 누름."""
    return qk.PriceCheck(checked_at=NOW - datetime.timedelta(days=days), **kw)


def space(pid=MOLD["id"], width=2400, **kw):
    values = dict(space="안방", product_ids=() if pid is None else (pid,), width_mm=width, width_max_mm=0,
                  height_mm=0, door="unknown", handle="unknown", options=())
    return qb.QuoteSpace(**{**values, **kw})


def ask(*spaces, brand="LAHOM", **kw):
    return qb.QuoteAsk(quote_request=True, brand=brand, spaces=spaces or (space(),), cost_usd=Decimal("0.002"),
                       input_tokens=300, output_tokens=40, latency_ms=900, **kw)


def won(pid, width, options=(), products=None):
    """서버 화면 계산 값(원) — 제품 하나 · 가로 하나(규칙 층 없이)."""
    rows = pricing.option_rows(options, CATEGORIES)
    got = pricing.compute_estimate([{"mode": "select", "productId": pid, "widthMm": width}],
                                   products if products is not None else LAHOM, rows)
    return pricing.won(got.total_price_collect)


def evaluate(quote, cat_=None, rules=(), check=None):
    return qc.evaluate(quote, cat_ or catalog(), rules, check=check or checked(), now=NOW)


def rule_item(text, kind=qc.KIND_BUILD_RULE, item_id="rule-1"):
    return KnowledgeItem(item_id=item_id, kind=kind, status="approved", text=text)


def amount_draft(width=2400):
    return f"고객님, 가로 {width:,}mm 기준 계산기 금액은 {won(MOLD['id'], width):,}원입니다."


class FakeQuoter:
    """뽑기 두뇌 대역 — 받은 재료를 남기고 정한 결과(예외도)를 낸다."""

    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def __call__(self, request, catalog_, *, session, now):
        self.calls.append(request)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def switch(on=True, **extra):
    """관리 화면 설정 줄 — '견적 계산 넣기' 켬 · 끔(나머지는 처음 값)."""
    value = {**st.DEFAULTS, "quote_calc_enabled": on, **extra}
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, version=1, setting_value=value))
    else:
        row.setting_value = value
    db_session.commit()


_ADMINS = itertools.count(1)


def admin(name="price"):
    row = User(username=f"quote-{name}-{next(_ADMINS)}", password=generate_password_hash("pw"), role="ADMIN",
               team="CS", name=f"합성 {name}", is_active=True)
    db_session.add(row)
    db_session.commit()
    return row


def confirm_prices(catalog_=None, *, when=NOW, user=None):
    """[계산기 값 확인했어요]를 누른 것처럼 — 지금 값 지문 · 확인한 때를 적는다."""
    actor = user or admin()
    qk.confirm(db_session, catalog_ or catalog(), actor_user_id=actor.id, now=when)
    db_session.commit()
    return actor


def quoting(quoter, catalog_=None):
    """초안 차례 꼴 — 가짜 뽑기 두뇌 · 계산기 설정."""
    return functools.partial(DraftPass, quoter=quoter, catalog_reader=lambda: catalog_ or catalog())
