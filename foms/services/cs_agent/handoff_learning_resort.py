"""쌓인 엇갈림 카드 다시 가르기(사장님 2026-11-21 '새 내용은 바로 넣기' · 상담 원장 D276) — 한 번만.

첫 두 밤(11-20 · 21)에는 두뇌가 '다른 말'로 낸 안 가운데 한 손님 것이 모두 엇갈림 카드가 됐다. 읽어 보니 대부분 지금 지식과
부딪치지 않는 새 내용이었다(「실측」 · 「시공」 같은 큰 항목에 붙일 내용 — 고칠 수 없는 항목이라 카드로 빠졌다). 11-21 규칙
(다른 말 판정자 — 밤 배우기는 11-22 부터 놓을 자리 판정 :mod:`.handoff_learning_place`)으로 그때 카드를 한 번 다시 가른다:

- **숫자**: 이름 · 글의 숫자 조각이 회사 지식 · 근거 상담의 직원 답에 그대로 있어야 한다(없으면 카드로 둔다).
- **부딪침**: 그 카드가 가리키는 항목 + 가까운 승인 지식에 더함인가 부딪침인가(:func:`.handoff_learning_judge.differs_verdict`
  — 밤 배우기와 같은 판정자 · 학습 돈 줄) — 부딪치거나 한 번 부르기가 실패하면 카드로 둔다. 부를 수 없으면(돈 상한 · 준비 안 됨)
  이번 바퀴는 멈추고 다음 바퀴에 다시 한다.
- **판 2(11-21)**: 판 1 은 공용 부딪침 관문(보조 모델 · 두 순서 가운데 하나라도)으로 갈라 첫 바퀴 16장을 모두 부딪침으로 봤다 —
  판이 바뀌면 가른 표를 비우고 처음부터 다시 가른다.
- 부딪치지 않으면 **새 지식**(사실 · 정책 — 글이 응대 절차면 정책)으로 넣고 바로 반영한 뒤 카드를 '합쳐짐'으로 닫는다(감사
  ``BRAIN_MERGE``). 같은 말을 한 카드가 여럿이면 처음 것만 새 지식이 되고 나머지는 그 지식에 합쳐 닫는다. 지식에 이미 아주
  비슷한 글이 있으면(같음 관문) 넣지도 닫지도 않는다(조금 다른 값이 묻힐 수 있어 사람이 본다).

가를 카드는 처음 부른 때 열려 있던 카드까지다(``until`` — 그 뒤 카드는 새 규칙이 이미 가른 진짜 엇갈림). 15분 바퀴의 학습 몫이
시각과 상관없이 부르고(:mod:`.learning_pass`), 한 바퀴에 :data:`PER_TICK` 장까지(판정자 부르기가 바퀴를 오래 붙잡지 않게) 한다. 다
가르면 판(:data:`RESORT_POLICY`)에 끝 표시를 해 다시 하지 않는다. 패널 '넘긴 상담 배우기' · '배운 것 바로 반영'이 꺼져 있으면
하지 않는다. 숫자 · 코드만 남긴다(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChange
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.photo_cards import ABOUT_PREFIX
from foms.services.brain.proposals import Proposer, after_values, known_text
from foms.services.cs_agent.case_memory import text_similarity
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learn_settings import HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning import auto_learn
from foms.services.cs_agent.handoff_learning_gates import (
    AGENT, CARD_PREFIX, DUP_SIMILARITY, MAX_TITLE, _card_rows, _filer, _numbers_ok, _store_code, apply_now, close_cards, seen_proposals,
)
from foms.services.cs_agent.handoff_learning_judge import ADDS, CONTRADICTS, UNAVAILABLE, differs_verdict
from foms.services.cs_agent.handoff_learning_prompt import knowledge_rows
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import off_reason
from foms.services.cs_agent.send import SEND_BRAND
from models import CsAgentTurn, SystemSetting

logger = logging.getLogger(__name__)

__all__ = ["PER_TICK", "RESORT_POLICY", "STORE_KEY", "resort_cards"]

STORE_KEY = "cs_agent_card_resort"
RESORT_POLICY = 2
PER_TICK = 16
REASON = "넘긴 상담 배우기 · 지금 지식과 부딪치지 않는 새 내용 — 엇갈림 카드에서 새 지식으로 옮김(사장님 11-21)"
#: 응대 절차 글(무엇을 묻고 · 안내하고 · 넘기는지)이면 정책, 아니면 사실(지시문 3번과 같은 가름).
_PROCEDURE = re.compile(r"(안내|묻|물어|권|답|보내|알리|넘기|확인)[가-힣]*(한다|는다|했다|준다|드린다)")


def _doc(row: Any) -> dict[str, Any]:
    """저장 값 → ``{"policy": 판, "until": 가를 카드 id 끝, "checked": [가른 카드 id], "done": 끝남}`` 사본."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    until = value.get("until")
    checked = value.get("checked") if isinstance(value.get("checked"), list) else []
    return {"policy": value.get("policy") if isinstance(value.get("policy"), int) else 0,
            "until": until if isinstance(until, int) and not isinstance(until, bool) else None,
            "checked": [i for i in checked if isinstance(i, int) and not isinstance(i, bool)],
            "done": value.get("done") is True}


def _row(session: Any) -> Any:
    """표 줄을 잠가 읽는다(없으면 먼저 만들어 커밋)."""
    if session.get(SystemSetting, STORE_KEY) is None:
        session.add(SystemSetting(setting_key=STORE_KEY, setting_value={},
                                  description="AI 상담팀원 넘긴 상담 배우기 — 쌓인 엇갈림 카드 다시 가르기(한 번)"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, STORE_KEY, populate_existing=True, with_for_update=True)


def _save(session: Any, doc: dict[str, Any]) -> None:
    """잠가 다시 읽은 줄에 쓰고 커밋한다(가른 id 는 같은 판의 앞 값과 합친다)."""
    row = _row(session)
    old = _doc(row)
    before = old["checked"] if old["policy"] == doc["policy"] else []
    row.setting_value = {**doc, "checked": sorted({*before, *doc["checked"]})}
    flag_modified(row, "setting_value")
    session.commit()


def _kind(text: str) -> str:
    """새 지식 유형 — 응대 절차면 정책, 아니면 사실."""
    return "policy" if _PROCEDURE.search(text) else "fact"


def _replies(session: Any, evidence: list[Any]) -> dict[str, list[str]]:
    """카드 근거 차례(``case:<id>``)의 가린 직원 답 — 상담(손님)마다."""
    ids = [int(e[5:]) for e in evidence if isinstance(e, str) and e.startswith("case:") and e[5:].isdigit()]
    out: dict[str, list[str]] = {}
    if ids:
        for chat, reply in session.execute(select(CsAgentTurn.chat_id, CsAgentTurn.staff_reply_masked)
                                           .where(CsAgentTurn.id.in_(ids))):
            out.setdefault(str(chat), []).append(reply or "")
    return out


def _title(session: Any, change_id: int, text: str) -> str:
    """카드에 적힌 짧은 이름(없거나 길면 글 앞 :data:`MAX_TITLE` 자)."""
    values = after_values(session.get(BrainChange, change_id).fields)
    payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
    label = str(payload.get("pref_label") or "").strip()
    return label if label and len(label) <= MAX_TITLE and "\n" not in label else text.split("\n", 1)[0][:MAX_TITLE].strip()


def _one(session: Any, card: tuple[int, str, str, str, list[Any]], ctx: dict[str, Any]) -> str:
    """카드 하나 — ``moved`` · ``moved_open`` · ``merged``(앞 카드와 같은 말 — 닫음) · 둔 까닭 코드 · ``unavailable``."""
    change_id, _key, target, text, evidence = card
    now, auto = ctx["now"], ctx["auto"]
    if any(text_similarity(text, said) >= DUP_SIMILARITY for said in ctx["moved"]):  # 방금 옮긴 카드와 같은 말
        close_cards(session, [change_id], now)
        session.commit()
        return "merged"
    title = _title(session, change_id, text)
    replies = _replies(session, evidence)
    if not _numbers_ok([title, text], ctx["known"], replies):
        return "numbers"
    verdict = differs_verdict(session, target_key=target, title=title, text=text, cfg=ctx["cfg"], now=now)
    session.commit()  # 판정자 부르기가 연 트랜잭션을 닫는다
    if verdict != ADDS:
        return {CONTRADICTS: "conflict", UNAVAILABLE: "unavailable"}.get(verdict, "judge_failed")
    allowed = "\n".join([ctx["known"], *(one for said in replies.values() for one in said)])
    common = dict(reason=REASON, proposer=Proposer.agent_named(AGENT), now=naive_utc(now), known=allowed,
                  evidence=[e for e in evidence if not (isinstance(e, str) and e.startswith(ABOUT_PREFIX))])
    code, make = _filer(session, {"op": "create", "item_type": _kind(text)}, title=title, text=text, number=change_id,
                        common=common, now=now, seen=ctx["seen"], approved=ctx["approved"], skip_gates=("conflict",))
    if make is None:  # 같음 · 겹침 — 카드로 둔다
        return code or "kept"
    try:
        change = make()
        session.commit()
    except BrainStoreError as exc:  # 글 · 숫자 · 근거 관문 — 카드로 둔다
        session.rollback()
        return _store_code(exc)
    blocked = apply_now(session, change, auto, now)
    close_cards(session, [change_id], now)  # 새 지식(반영 · 승인 대기)으로 옮겼다 — 같은 글이 두 곳에 남지 않게
    session.commit()
    ctx["seen"].insert(0, ("open", None, title, text))
    ctx["moved"].append(text)
    return "moved_open" if blocked else "moved"


def resort_cards(session: Any, *, now: datetime.datetime) -> dict[str, Any]:
    """쌓인 엇갈림 카드 다시 가르기 한 바퀴(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다."""
    off, cfg = off_reason(session, HANDOFF_LEARN_FIELD)
    if off is not None:
        session.rollback()
        return {"off": off}
    doc = _doc(_row(session))
    session.commit()
    if doc["policy"] < RESORT_POLICY:  # 판이 바뀌었다 — 가른 표를 비우고 처음부터(모듈 설명)
        doc = {"policy": RESORT_POLICY, "until": None, "checked": [], "done": False}
    if doc["done"] and doc["policy"] >= RESORT_POLICY:
        return {"off": "done"}
    auto = auto_learn(session, cfg)
    if auto is None:  # 바로 반영이 꺼져 있으면 사장님이 카드로 고른다
        session.rollback()
        return {"off": "no_auto"}
    cards = _card_rows(session)
    if doc["until"] is None:
        doc["until"] = max((card[0] for card in cards), default=0)
    seen_ids = set(doc["checked"])
    todo = [card for card in cards if card[0] <= doc["until"] and card[0] not in seen_ids]
    rows = knowledge_rows(session)
    approved_cs = [item.text for item in load_approved(session, SEND_BRAND).items]
    ctx = {"now": now, "auto": auto, "cfg": cfg, "known": "\n".join([known_text(session), *approved_cs]),
           "approved": [row.text for row in rows if row.text] + approved_cs,
           "seen": [s for s in seen_proposals(session) if not str(s[1] or "").startswith(CARD_PREFIX)], "moved": []}
    session.commit()
    counts: dict[str, Any] = {"checked": 0, "left": 0, "halted": None}
    checked: list[int] = []
    for card in todo[:PER_TICK]:
        code = _one(session, card, ctx)
        if code == "unavailable":  # 판정자를 못 부른다 — 이 카드는 다음 바퀴에 다시
            counts["halted"] = "judge_unavailable"
            break
        checked.append(card[0])
        counts[code] = counts.get(code, 0) + 1
    counts["checked"] = len(checked)
    counts["left"] = len(todo) - len(checked)
    done = counts["left"] == 0
    _save(session, {"policy": RESORT_POLICY, "until": doc["until"], "checked": checked, "done": done})
    logger.info("[CS 엇갈림 카드 다시 가르기] %s", " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return counts


def card_resort_state(session: Any) -> Optional[dict[str, Any]]:
    """저장된 진행(시험 · 진단)."""
    row = session.get(SystemSetting, STORE_KEY, populate_existing=True)
    return _doc(row) if row is not None else None
