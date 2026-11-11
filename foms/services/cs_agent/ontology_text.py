"""바꿔 묻기 대응 프롬프트 글 — 지시문 8번 · 지식 머리말 · 다른 말 줄 · 덧붙인 용어 칸(:mod:`.ontology` 의 글 몫).

:mod:`.brain_prompt` 가 부른다(:mod:`.ontology` 는 설정 · DB 를 읽어 거꾸로 부르면 돌고 돈다 — 이 모듈은 아무것도 읽지 않는다).
재료는 :attr:`.knowledge_doc.ApprovedKnowledge.onto` (:class:`.ontology.Ontology` — 없으면 예전 글 그대로).
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["ALIAS_HEAD", "EXTRA_HEAD", "OLD_HEAD", "OLD_RULE", "ONTO_HEAD", "ONTO_RULE", "alias_line", "extra_lines",
           "head_line", "rule_text"]

ALIAS_HEAD = "다른 말:"
EXTRA_HEAD = "용어 · 규격 · 절차(승인 지식 — 사실로 써도 된다, 근거 id 로는 고르지 않는다):"
#: 지시문 8번(예전 · 바뀐 글) — :func:`.brain_prompt.instructions` 가 바꿔 낀다(시험이 예전 글이 지시문에 있는지 본다).
OLD_RULE = "8. 확실하지 않거나 승인 지식에 근거가 없으면 지어내지 말고 사람에게 넘긴다. 틀린 답보다 넘김이 낫다."
ONTO_RULE = ("8. 손님 말이 승인 지식과 낱말 · 단위 · 맞춤법이 달라도 뜻이 같으면(다른 말 · 줄임말 · 2주와 14일 · 35cm 와 "
             "350mm) 그 항목으로 답한다. 승인 지식 어디에도 그 사실이 정말 없거나 뜻이 같은지 확실하지 않을 때만 지어내지 말고 "
             "사람에게 넘긴다.")
#: 지식 머리말(같은 뜻이면 답하기 켬).
ONTO_HEAD = ("승인 지식 — 근거는 이 항목만 쓴다. 손님 말이 달라도 뜻이 같은 항목이면 그 항목이 근거다(줄 맨 앞 대괄호 안이 "
             "항목 id):")
OLD_HEAD = "승인 지식 — 근거는 이 항목만 쓴다(줄 맨 앞 대괄호 안이 항목 id):"


def _prompt_on(knowledge: Any) -> bool:
    onto = getattr(knowledge, "onto", None)
    return bool(onto is not None and onto.flags.prompt)


def rule_text(text: str, knowledge: Any) -> str:
    """지시문 — '같은 뜻이면 답하기' 켬이면 8번을 바꿔 낀다."""
    return text.replace(OLD_RULE, ONTO_RULE) if _prompt_on(knowledge) else text


def head_line(knowledge: Any) -> str:
    """지식 머리말."""
    return ONTO_HEAD if _prompt_on(knowledge) else OLD_HEAD


def alias_line(knowledge: Any, item_id: str, indent: str) -> list[str]:
    """지식 문서 항목 줄 아래 '다른 말' 한 줄(없으면 빈 목록)."""
    onto = knowledge.onto
    labels = onto.aliases.get(item_id) if onto is not None else None
    return [f"{indent}{ALIAS_HEAD} {' · '.join(labels)}"] if labels else []


def extra_lines(knowledge: Any, block: Callable[[str, str], list[str]]) -> list[str]:
    """덧붙인 용어 · 규격 · 절차 칸(없으면 빈 목록). ``block`` 은 :func:`.brain_prompt._block`(머리표 흉내 막기)."""
    onto = knowledge.onto
    if onto is None or not onto.extra:
        return []
    lines = [EXTRA_HEAD]
    for item in onto.extra:
        tail = f" ({ALIAS_HEAD} {' · '.join(item.aliases)})" if item.aliases else ""
        lines += block(f"[onto:{item.key}] ({item.kind}) {item.name} —", f"{item.text}{tail}")
    return lines
