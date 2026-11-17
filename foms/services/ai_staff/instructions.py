"""AI 직원 지시문 보기 — ADMIN 이 읽기만(사용자 결정 D233 · 목업 판 ⑪ 머리 [지시문 보기], 점검 2차 w3-17).

직원마다 지시문이 오는 곳이 다르다. 여기서는 **코드에 있는 글**만 모아 보이고, 아무것도 바꾸지 않는다(쓰기 길 없음).

- 상담 AI(``cs``): 초안 두뇌의 지시문 블록 — :func:`foms.services.cs_agent.brain_prompt.instructions` 를 지금 관리 설정(답 길이 ·
  사진 칸 · '같은 뜻이면 답하기')으로 그대로 부른다(실제로 보내는 글과 같은 바이트). 관리 칸 '주문 확인해 답하기'가 켜졌으면 주문을
  찾았을 때 붙는 칸 규칙(:data:`foms.services.cs_agent.order_block.ORDER_RULES`)을 따로 보인다. 승인 지식 블록 · 손님 글 · 주문
  값은 싣지 않는다(지식은 회사 지식 화면에서 본다).
- 지식 물어보기(``ask``): :data:`foms.services.brain.chat_prompt.SYSTEM` + ERP 주문 칸 머리 규칙(:data:`.chat_prompt.ERP_RULES` —
  주문 키 자리는 '주문 키'로).
- 운영 AI · 일정 AI(``ops`` · ``schedule``): 모델을 부르지 않아 지시문이 없다 — 훑기 규칙(:data:`.sweeps.RULES`)을 쉬운 글 한 줄씩
  (규칙 이름 · 조건 → 만드는 제안 · 지금 수준).
- 도면 AI 팀원(``drawing``): 저장소 밖 주 1회 루틴이라 여기서 볼 수 없다는 한 줄만.

지시문 글에는 열쇠 · 주소 · 손님 자료가 없다(코드가 정한 글 · 브랜드 이름 · 관리 설정의 답 길이 문장뿐) — 시험이 비밀 꼴을 다시 본다.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from foms.services.ai_staff.registry import AGENTS, level_table
from foms.services.erp_actions.registry import ACTIONS, LEVEL_LABELS
from foms.services.cs_agent.brain_prompt import ENABLED_BRANDS, instructions
from foms.services.cs_agent.image_settings import MODE_DRAFT, image_mode
from foms.services.cs_agent.onto_settings import onto_flags, order_lookup_on
from foms.services.cs_agent.order_block import ORDER_RULES
from foms.services.cs_agent.settings import read_settings
from foms.services.brain.chat_prompt import ERP_HEAD, ERP_RULES, SYSTEM
from foms.services.ai_staff.sweeps import RULES

__all__ = ["OUTSIDE_NOTE", "RULES_NOTE", "instructions_view"]

OUTSIDE_NOTE = "도면 AI 팀원의 지시문은 FOMS 저장소 밖의 주 1회 루틴에 있어서 여기서 볼 수 없어요."
RULES_NOTE = "이 직원은 모델을 부르지 않아 지시문이 없어요. 아래 규칙대로만 주문을 훑고 제안을 만들어요(한 번에 30개까지 — 규칙마다 고르게 나눠요)."
PROMPT_NOTE = "AI 에 보내는 지시문 그대로예요. 여기서는 읽기만 하고, 고치려면 코드를 바꿔야 해요."


def _cs_sections(session: Any) -> list[dict[str, str]]:

    cfg = read_settings(session, log=False)
    knowledge = SimpleNamespace(onto=SimpleNamespace(flags=onto_flags(cfg)))  # '같은 뜻이면 답하기' 판정만 읽는다
    photos = image_mode(cfg) == MODE_DRAFT
    out = [{"title": f"초안 지시문 — {label}", "text": instructions(brand, cfg.get("draft_length"), photos, knowledge)}
           for brand, label in ENABLED_BRANDS.items()]
    if order_lookup_on(cfg):
        out.append({"title": "주문을 찾았을 때 붙는 규칙", "text": "\n".join(ORDER_RULES)})
    return out


def _ask_sections() -> list[dict[str, str]]:

    rules = "\n".join(rule.replace("{key}", "주문 키") for rule in ERP_RULES)
    return [{"title": "물어보기 지시문", "text": SYSTEM},
            {"title": "주문을 읽었을 때 붙는 규칙", "text": f"{ERP_HEAD}\n{rules}"}]


def _rule_sections(session: Any, key: str) -> list[dict[str, str]]:

    levels = level_table(session)[key]
    lines = []
    for rule in RULES.values():
        if rule.agent != key:
            continue
        spec = ACTIONS.get(rule.action)
        level = levels.get(rule.action)
        now = "못 함" if level is None else LEVEL_LABELS[level]
        lines.append(f"{rule.key} · {rule.label} → '{spec.label if spec else rule.action}' 제안 (지금 수준 {now})")
    return [{"title": "훑기 규칙", "text": "\n".join(lines)}]


def instructions_view(session: Any, key: Any) -> Optional[dict[str, Any]]:
    """직원 하나의 지시문(읽기만). 모르는 열쇠면 ``None``(API 404).

    Returns:
        ``{"key", "label", "kind", "note", "sections": [{"title", "text"}]}`` — ``kind`` 는 ``prompt``(모델 지시문) ·
        ``rules``(규칙 직원) · ``outside``(저장소 밖).
    """
    agent = AGENTS.get(key) if isinstance(key, str) else None
    if agent is None:
        return None
    if agent.key == "cs":
        kind, note, sections = "prompt", PROMPT_NOTE, _cs_sections(session)
    elif agent.key == "ask":
        kind, note, sections = "prompt", PROMPT_NOTE, _ask_sections()
    elif agent.trial:
        kind, note, sections = "rules", RULES_NOTE, _rule_sections(session, agent.key)
    else:
        kind, note, sections = "outside", OUTSIDE_NOTE, []
    return {"key": agent.key, "label": agent.label, "kind": kind, "note": note, "sections": sections}
