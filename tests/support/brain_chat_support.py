"""회사 지식 물어보기(⑤-5) 시험 재료 — 가짜 모델(SDK 응답 꼴 그대로) · 설정 켜기 · 합성 사람 · 합성 지식.

손으로 꾸민 합성 이름 · 글만 쓴다(손님 글 · 직원 이름 · 실제 가격 · 비밀값 없음). 모델 · 벡터 · 판정자는 모두 가짜다 —
네트워크를 부르지 않는다.
"""

from __future__ import annotations

import copy
import datetime
import json
import re
from types import SimpleNamespace
from typing import Any, Callable, Optional

from anthropic.types.beta import BetaMessage

from foms.services.brain.chat_settings import DEFAULTS, SETTINGS_KEY
from foms.services.cs_agent.state import KST
from models import PartnerOrg, SystemSetting
from tests.support.brain_support import create, person

#: 한국 2026-11-02(월) 10시 — 돈 줄 날(KST)과 오늘이 같다.
NOW_KST = datetime.datetime(2026, 11, 2, 10, 0, tzinfo=KST)
MODEL_ID = "claude-sonnet-5-5"


def chat_on(session: Any, **overrides: Any) -> None:
    """설정 줄을 직접 넣는다(켬 · 하루 상한 · 나머지 처음 값). 커밋한다."""
    value = {**DEFAULTS, "enabled": True, "daily_cap_usd": "5.00", **overrides}
    row = session.get(SystemSetting, SETTINGS_KEY)
    if row is None:
        session.add(SystemSetting(setting_key=SETTINGS_KEY, setting_value=value, description="합성"))
    else:
        row.setting_value = value
    session.commit()


def reply(**fields: Any) -> str:
    """구조화 출력 글(처음 값 = 모름)."""
    out = {"answer": "", "evidence_ids": [], "check_ids": [], "unknown": True, "kind": "knowledge",
           "ask_team": "owner", "layer": "common", "confidence": "medium"}
    out.update(fields)
    return json.dumps(out, ensure_ascii=False)


def message(text: str, *, stop: str = "end_turn") -> BetaMessage:
    """SDK 실제 응답 형(BetaMessage)."""
    return BetaMessage.model_validate({
        "id": "msg_synthetic", "type": "message", "role": "assistant", "model": MODEL_ID,
        "content": [{"type": "thinking", "thinking": "", "signature": "sig-synthetic"}, {"type": "text", "text": text}],
        "stop_reason": stop, "stop_sequence": None, "stop_details": None,
        "usage": {"input_tokens": 800, "output_tokens": 200, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0}})


class FakeMessages:
    """``beta.messages`` 흉내 — 받은 인자를 적고 ``answer(params)`` 의 글을 응답으로 낸다."""

    def __init__(self, answer: Callable[[dict[str, Any]], Any]) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(copy.deepcopy(kwargs))
        out = self.answer(kwargs)
        if isinstance(out, BaseException):
            raise out
        return out if isinstance(out, BetaMessage) else message(out)


class FakeClient:
    """``anthropic.Anthropic`` 흉내."""

    def __init__(self, answer: Callable[[dict[str, Any]], Any]) -> None:
        self.beta = SimpleNamespace(messages=FakeMessages(answer))
        self.options: list[dict[str, Any]] = []

    def with_options(self, **options: Any) -> "FakeClient":
        self.options.append(options)
        return self

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.beta.messages.calls


def fixed(text: str) -> FakeClient:
    """늘 같은 글을 내는 가짜."""
    return FakeClient(lambda _params: text)


_BLOCK = re.compile(r"\[후보 항목[^\]]*\]\n(.*)\n\n위 규칙대로", re.S)


def candidates_of(params: dict[str, Any]) -> dict[str, Any]:
    """두뇌에 간 후보 묶음(JSON) — 사용자 칸에서 꺼낸다."""
    content = params["messages"][0]["content"]
    match = _BLOCK.search(content)
    return json.loads(match.group(1)) if match else {"usable": [], "needs_check": []}


def reader(params: dict[str, Any]) -> str:
    """결정적 가짜 두뇌 — 쓸 수 있는 첫 후보의 글을 근거 하나로 답한다(없으면 모름). 평가 묶음 실행기 시험용."""
    block = candidates_of(params)
    if not block["usable"]:
        return reply()
    top = block["usable"][0]
    return reply(answer=top["text"] or top["name"], evidence_ids=[top["key"]], unknown=False, confidence="high")


def reader_client() -> FakeClient:
    """:func:`reader` 가짜."""
    return FakeClient(reader)


def _partner(session: Any) -> Any:
    """합성 협력사 계정(PARTNER 는 협력사 번호가 꼭 있다)."""
    org = PartnerOrg(name="합성 협력사")
    session.add(org)
    session.flush()
    return person(session, "bc_partner", role="PARTNER", partner_org_id=org.id)


def chat_people(session: Any) -> dict[str, Any]:
    """역할 × 팀 — ADMIN · CS MANAGER · SALES MANAGER · CS STAFF · VIEWER · PARTNER · 꺼진 ADMIN."""
    return {"admin": person(session, "bc_admin"), "admin2": person(session, "bc_admin2"),
            "cs_mgr": person(session, "bc_cs_mgr", role="MANAGER", team="CS"),
            "dr_mgr": person(session, "bc_dr_mgr", role="MANAGER", team="DRAWING"),
            "sales_mgr": person(session, "bc_sales_mgr", role="MANAGER", team="SALES"),
            "staff": person(session, "bc_staff", role="STAFF", team="CS"),
            "viewer": person(session, "bc_viewer", role="VIEWER", team="CS"),
            "partner": _partner(session),
            "off": person(session, "bc_off", active=False)}


def chat_items(session: Any, admin: Any) -> None:
    """합성 지식 — 모두 · 도면팀 · 가격 재량 범위, 용어(다른 이름), 낡은 항목. 커밋한다."""
    create(session, admin, "common/sliding", item_type="spec", name="슬라이딩 깊이",
           text="슬라이딩 문 장의 몸통 깊이는 합성 규격 650mm 입니다.", payload={"value": 650, "unit": "mm"})
    create(session, admin, "common/hinge", item_type="build_rule", name="여닫이 경첩 조건",
           text="여닫이 문은 경첩 셋을 단다는 합성 조건입니다.", checked_at="2026-10-30")
    create(session, admin, "drawing/bom", item_type="drawing_rule", layer="drawing", name="도면 재단 여유",
           text="재단 여유는 도면팀 합성 규칙입니다.", visibility="team:DRAWING")
    create(session, admin, "common/discount", item_type="price_rule", name="재량 할인 폭",
           text="재량 할인 폭은 합성 비밀 규칙입니다.", visibility="price", checked_at="2026-10-30",
           payload={"doc_id": "discount", "approved_by": "합성", "approved_at": "2026-10-30"})
    create(session, admin, "common/term-builtin", item_type="term", name="붙박이장",
           text="벽에 붙여 짜 넣는 장을 이르는 합성 용어입니다.", payload={"aliases": ["빌트인장", "벽장"], "broader": "가구"})
    create(session, admin, "common/old-rule", item_type="build_rule", name="옛 몰딩 조건",
           text="몰딩 높이는 합성 값 40mm 입니다.", checked_at="2026-01-05")
    session.commit()


def chat_world(session: Any, **settings: Any) -> dict[str, Any]:
    """사람 · 지식 · 설정(켬)."""
    people = chat_people(session)
    chat_items(session, people["admin"])
    chat_on(session, **settings)
    return people


def fake_embedder(table: dict[str, list[float]], calls: Optional[list] = None,
                  fail: Optional[BaseException] = None) -> Callable[[list[str], str, float], tuple[list[list[float]], int]]:
    """가짜 벡터 — 글에 든 낱말(표의 키)로 벡터를 정한다(없으면 영 벡터에 가까운 값). 받은 글 · 꼴을 ``calls`` 에 적는다."""
    from foms.persistence.brain.vectors import DIMENSION

    def embed(texts: list[str], input_type: str, timeout: float) -> tuple[list[list[float]], int]:
        if calls is not None:
            calls.append({"texts": list(texts), "input_type": input_type, "timeout": timeout})
        if fail is not None:
            raise fail
        out = []
        for body in texts:
            base = [0.001] * DIMENSION
            for word, vector in table.items():
                if word in body:
                    base = [a + b for a, b in zip(base, vector)]
            out.append(base)
        return out, sum(len(t) for t in texts)

    return embed


def axis(index: int) -> list[float]:
    """한 축만 1 인 벡터(가짜 뜻 방향)."""
    from foms.persistence.brain.vectors import DIMENSION

    vec = [0.0] * DIMENSION
    vec[index] = 1.0
    return vec
