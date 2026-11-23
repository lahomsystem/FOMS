"""쌓인 엇갈림 카드 다시 가르기(사장님 2026-11-21 · 11-23) — 판마다 한 번.

**판 3(사장님 11-23 'AI 가 새 판정으로 다시 가르기 — 한 상담뿐인 말은 기다리는 말로, 진짜 부딪침만 카드로')**: 놓을 자리 판정의
첫 밤(11-23) 카드 19장 가운데 13장은 옛 길(두뇌의 고치기 안이 공용 부딪침 관문에 막힘 — :mod:`.handoff_learning_route` 설명 ·
설계서 ``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 2.1 · 3절)에서 나왔다. 글이 '지금 글 + 덧붙인 문장'일 뿐 진짜
부딪침이 아니다. 판 3 은 처음 부른 때 열려 있던 카드를 밤 배우기와 같은 놓을 자리 판정(:func:`.handoff_learning_place.place`)과
되풀이 문턱으로 다시 가른다(넣는 갈래는 밤 배우기의 것을 그대로 쓴다 — :func:`.handoff_learning_route._settle` · ``_repeat``):

- 글 첫 줄에 어긋나는 두 구절(:data:`.handoff_learning_gates.CLASH_HEAD`)이 있는 카드는 놓을 자리 판정자가 이미 만든 것 — 그대로
  둔다(``kept``).
- 그 밖의 카드는 표시 줄을 뺀 글을, 카드가 가리키는 항목을 짚은 안으로 한 번 묻는다(가까운 기다리는 말도 따로 보인다). 그 항목이
  없거나 반영 중이 아니면 둔다(``target``). 넘김 학습이 낸 비슷한 안이 열려 있거나 거절됐으면 묻지 않고 둔다(겹침 관문).
- ``same`` · ``decided`` · ``not_rule`` → 카드를 '합쳐짐'으로 닫는다(감사 ``BRAIN_MERGE``).
- ``adds`` · ``new`` → 밤 배우기와 같은 되풀이 문턱: 카드 근거의 서로 다른 상담이 한 곳이면 기다리는 말로 모으고(``held``) 카드를
  닫는다. 두 곳 이상이면 그 항목 끝에 더한 문장을 붙이거나(``placed_added``) 새 지식으로 넣어(``placed_new``) 바로 반영하고 카드를
  닫는다(반영이 막혀 승인 대기에 남으면 ``_open`` 을 붙여 센다). 카드 글이 그 항목의 지금 글을 그대로 품으면 판정자가 고른 더한
  문장만 쓴다(더한 문장이 없으면 둔다 — ``place_unknown``). 숫자 관문을 못 지나면 둔다(``numbers``).
- ``repeat`` → 그 기다리는 말에 근거를 합친다(두 상담이 되면 지금 지식 기준으로 한 번 더 물어 넣는다). 기다리는 말로 남거나 올라가거나
  버려지면 카드를 닫는다.
- ``contradicts`` → 카드를 열린 채 두고 글 첫 줄에 어긋나는 두 구절을 넣는다(``marked`` — 사장님이 무엇이 다른지 본다). 판정자가
  카드 대상이 아닌 다른 항목과 부딪친다고 하면 그 구절이 카드 대상의 글이 아니라 손대지 않는다(``clash_elsewhere``).
- 판정자를 부를 수 없으면(돈 상한 · 준비 안 됨) 이번 바퀴는 멈추고 다음 바퀴에 다시 한다. 꼴이 틀린 답이면 둔다.

앞 판(11-21): 판 1 은 공용 부딪침 관문으로, 판 2 는 다른 말 판정자(:mod:`.handoff_learning_judge`)로 첫 두 밤 카드를 갈라 부딪치지
않는 것을 새 지식으로 옮겼다. 판(:data:`RESORT_POLICY`)이 바뀌면 가른 표를 비우고 처음부터 다시 가른다(운영에서 판 2 가 끝났어도
판 3 은 한 번 더 돈다).

가를 카드는 처음 부른 때 열려 있던 카드까지다(``until``). 15분 바퀴의 학습 몫이 시각과 상관없이 부르고(:mod:`.learning_pass`), 한
바퀴에 :data:`PER_TICK` 장까지(판정자 부르기가 바퀴를 오래 붙잡지 않게) 한다. 다 가르면 판에 끝 표시를 해 다시 하지 않는다. 패널
'넘긴 상담 배우기' · '배운 것 바로 반영'이 꺼져 있으면 하지 않는다. 숫자 · 코드만 남긴다(글 · 상담 id 없음).
"""

from __future__ import annotations

import copy
import datetime
import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import CHANGE_OPEN, STATUS_ACTIVE
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.photo_cards import ABOUT_PREFIX
from foms.services.brain.proposals import Proposer, after_values, known_text
from foms.services.brain.store import current_object
from foms.services.cs_agent import handoff_learning_held as held
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learn_settings import HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning import auto_learn
from foms.services.cs_agent.handoff_learning_gates import (
    AGENT, CARD_PREFIX, CLASH_HEAD, MAX_TITLE, _card_rows, _duplicate, _store_code, close_cards, seen_proposals,
)
from foms.services.cs_agent.handoff_learning_place import (
    CONTRADICTS, DECIDED, NOT_RULE, REPEAT, SAME, UNAVAILABLE, Placement, learned_vector, place,
)
from foms.services.cs_agent.handoff_learning_prompt import DIFFERS, REASON_WORDS, knowledge_rows
from foms.services.cs_agent.handoff_learning_route import Said, _flat, _repeat, _settle, after_filed, clash_line
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import off_reason
from foms.services.cs_agent.send import SEND_BRAND
from models import CsAgentTurn, SystemSetting

logger = logging.getLogger(__name__)

__all__ = ["PER_TICK", "RESORT_POLICY", "STORE_KEY", "resort_cards"]

STORE_KEY = "cs_agent_card_resort"
RESORT_POLICY = 3
PER_TICK = 16
#: 넣은 안의 까닭 글 — 앞 조각은 밤 배우기와 같다(더함이면 그 뒤에 '지금 지식에 더함'이 붙는다).
REASON = "넘긴 상담 배우기 · 쌓인 엇갈림 카드를 놓을 자리 판정으로 다시 가름(사장님 11-23)"
WHY = "쌓인 엇갈림 카드 다시 가르기(사장님 11-23)"
_DROP = (SAME, DECIDED, NOT_RULE)  # 카드를 닫는 판정 답
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


def _turns(session: Any, evidence: list[Any]) -> tuple[list[int], dict[str, list[str]], set[str]]:
    """카드 근거 차례(``case:<id>``) — (있는 차례 id, 상담마다 가린 직원 답, 넘긴 까닭 말)."""
    wanted = {int(e[5:]) for e in evidence if isinstance(e, str) and e.startswith("case:") and e[5:].isdigit()}
    ids: list[int] = []
    replies: dict[str, list[str]] = {}
    reasons: set[str] = set()
    if wanted:
        for turn_id, chat, reply, reason in session.execute(
                select(CsAgentTurn.id, CsAgentTurn.chat_id, CsAgentTurn.staff_reply_masked, CsAgentTurn.handoff_reason)
                .where(CsAgentTurn.id.in_(wanted)).order_by(CsAgentTurn.id)):
            ids.append(int(turn_id))
            replies.setdefault(str(chat), []).append(reply or "")
            reasons.add(REASON_WORDS.get(reason, "그 밖"))
    return ids, replies, reasons


def _title(change: Any, text: str) -> str:
    """카드에 적힌 짧은 이름(없거나 길면 글 앞 :data:`MAX_TITLE` 자)."""
    values = after_values(change.fields)
    payload = values.get("payload") if isinstance(values.get("payload"), dict) else {}
    label = str(payload.get("pref_label") or "").strip()
    return label if label and len(label) <= MAX_TITLE and "\n" not in label else text.split("\n", 1)[0][:MAX_TITLE].strip()


def _mark(session: Any, change: Any, verdict: Placement) -> None:
    """부딪침 — 카드 글 첫 줄에 어긋나는 두 구절을 넣는다(열린 채 · 커밋)."""
    fields = copy.deepcopy(change.fields)
    fields["text"]["after"] = "\n".join((clash_line(verdict), str(fields["text"].get("after") or "")))
    change.fields = fields
    flag_modified(change, "fields")
    session.commit()


def _one(session: Any, card: tuple[int, str, str, str, list[Any]], ctx: dict[str, Any]) -> str:
    """카드 하나(모듈 설명) — 센 코드. ``unavailable`` 이면 부르는 쪽이 이 바퀴를 멈춘다."""
    change_id, _key, target_key, body, evidence = card
    now = ctx["now"]
    change = session.get(BrainChange, change_id, populate_existing=True)
    if change is None or change.status != CHANGE_OPEN:  # 이 바퀴 앞 카드에 합쳐 닫혔다
        return "merged"
    if str(after_values(change.fields).get("text") or "").startswith(CLASH_HEAD):  # 놓을 자리 판정자가 만든 카드
        return "kept"
    target = current_object(session, target_key)
    if target is None or target.status != STATUS_ACTIVE:
        return "target"
    dup = _duplicate(body, ctx["seen"])
    if dup is not None:
        return dup
    ids, replies, reasons = _turns(session, evidence)
    if not replies:
        return "evidence"
    title = _title(change, body)
    vector = learned_vector(session, title=title, text=body, now=now)
    waiting = held.near(session, brand=SEND_BRAND, text=body, vector=vector)
    verdict = place(session, key=target_key, title=title, text=body, cfg=ctx["cfg"], now=now, vector=vector, held=waiting)
    session.commit()  # 판정자 부르기가 연 트랜잭션을 닫는다
    if verdict.verdict == UNAVAILABLE:
        return "unavailable"
    if verdict.verdict == CONTRADICTS:
        if verdict.target != target_key:
            return "clash_elsewhere"
        _mark(session, change, verdict)
        return "marked"
    said = Said(tuple(ids), frozenset(replies), tuple(sorted(reasons)), WHY, len(replies))
    allowed = "\n".join([ctx["known"], *(one for told in replies.values() for one in told)])
    common = dict(reason=REASON, proposer=Proposer.agent_named(AGENT), now=naive_utc(now), known=allowed,
                  evidence=[e for e in evidence if not (isinstance(e, str) and e.startswith(ABOUT_PREFIX))])
    whole = _flat(target.text)
    route = dict(raw={"op": DIFFERS, "item_type": _kind(body), "key": target_key},
                 card=dict(title=title, text=body, number=change_id, common=common, now=now, seen=ctx["seen"]),
                 replies=replies, known=ctx["known"], approved=ctx["approved"], pointing=True, vector=vector,
                 wraps=bool(whole) and whole in _flat(body))
    if verdict.verdict == REPEAT:
        if held.held_row(session, verdict.target) is None:
            return "place_unknown"
        placed = _repeat(session, verdict, said, pointed=target_key, cfg=ctx["cfg"], client=None, **route)
        settled = placed[0] == "held" or held.held_row(session, verdict.target) is None  # 기다림 · 올라감 · 버려짐
    else:
        placed = _settle(session, verdict, said, **route)
        settled = verdict.verdict in _DROP or placed[0] == "held"
    code, make, merged, done, waited = placed
    if make is None:
        if code == "place_unavailable":  # 다시 물을 때 판정자를 못 부름 — 다음 바퀴에 다시
            return "unavailable"
        if settled:
            close_cards(session, [change_id], now)
            session.commit()
        return code or "kept"
    try:
        made = make()
        session.commit()
    except BrainStoreError as exc:  # 글 · 숫자 · 근거 관문 — 카드로 둔다
        session.rollback()
        return _store_code(exc)
    extra = after_filed(session, made, waited=waited, merged=merged, auto=ctx["auto"], now=now)
    if extra != "applied" or change_id not in merged:  # 지식(반영 · 승인 대기)으로 옮겼다 — 같은 말이 두 곳에 남지 않게
        close_cards(session, [change_id], now)
    session.commit()
    return done if extra == "applied" else f"{done}_open"


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
           "seen": [s for s in seen_proposals(session) if not str(s[1] or "").startswith(CARD_PREFIX)]}
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
