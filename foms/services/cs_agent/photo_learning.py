"""주마다 읽은 손님 사진으로 회사 지식 제안 만들기 — master brain 제안 길로만(설계서 17.11.1 의 7 · 사장님 D172 '읽은 사진을
학습해서 온톨로지에 저장하고 지식을 업그레이드').

WORKER 15분 바퀴 학습 몫(:mod:`.learning_pass`)이 주간 고침 안과 같은 때(**월요일 새벽 KST** — :func:`.weekly_fix.in_window`)에
부르고, 주(ISO)마다 한 번만 돈다(부르기 전에 주 표를 남긴다 — :func:`claim_week`). 끄고 켜기는 :func:`.learning_brain.off_reason`
(패널 '사진 학습 → 회사 지식 제안' — 처음 끔 · 비상 정지 · 초안 끔 · 학습 돈 상한).

1. **읽기(가린 글만)**: 지난 7일 끝난 꼴 고침 · 직접 답 · 그대로(복사 · 버림 · 떼어 둔 줄 제외) 차례 가운데, 그 차례가 읽은 손님
   사진 설명(:func:`.image_summaries.summaries_by_turn` — 차례 번호로 잇는다)이 있는 것. 차례마다 가린 질문 · 직원이 보낸 가린
   답 · 사진 설명 · 의도.
2. **묶기 · 근거 관문**: (사진 종류, 의도)로 묶고(사진 종류가 여럿인 차례는 종류마다), 서로 다른 손님 2 **그리고** 직원 2 이상인
   묶음만(:func:`.weekly_fix_gates.evidence_ok` — 주간 고침 안과 같은 규칙) 학습 두뇌에 보낸다. 못 넘은 묶음은 수만 센다.
   **전체 대화(설계서 17.11.2 · D173)**: 패널 '전체 대화 글 수 상한'이 0 이 아니고 읽기 도우미가 있으면(감시 바퀴) 묶음마다
   최근 사례부터 '사진 학습 묶음당 사례 수'만 남긴 뒤 관문을 보고, 보낼 사례마다 그 상담 전체 대화(가린 글 · 상한 — :mod:`.full_conversation`)에 사진 표시 줄
   (``▶ 사진 N (손님) 종류: 설명``)을 그 사진이 온 글 자리(모르면 질문 뒤)에 끼워 싣는다. 못 읽은 사례는 예전 재료 그대로.
3. **두뇌(학습 모델 — 주간 고침 안 모델 칸)**: 회사 지식 목록과 견줘 제안 안(상황 · 제작 조건 새로 만들기 · 고치기, 제품 ·
   옵션에 '비슷한 말', 상황 → 제품 링크)을 구조화 출력으로(:mod:`.photo_learning_prompt`).
4. **관문(우리 쪽)**: 꼴 · 가림(개인정보 꼴 · 가림 표시 0) · 숫자(회사 지식 · 상담 승인 지식에 이미 있는 숫자만 — 학습한 숫자
   세탁 막기 R10-19) · 근거(고른 근거 차례가 그 묶음 안 · 그 근거만으로도 손님 2 · 직원 2).
5. **넣기 — 제안 길로만**: :mod:`foms.services.brain.proposals` 의 ``propose_create`` · ``propose_update`` · ``propose_link`` 에
   제안한 이 ``agent:cs_photo``(에이전트 — 글 관문 · 부딪침 · 근거 관문이 실제로 돈다)로 넣는다. 근거는 차례 번호(``case:<id>``)
   뿐이다(직원 번호 · 상담 id 는 싣지 않는다). 직접 쓰기는 없다 — '승인 대기' 카드가 되고 승인한 것만 다음 초안의 지식이 된다.
   막힌 안은 까닭 코드별 수만 센다. 같은 안이 열려 있으면 다시 넣지 않는다.

로그 · 결과에는 숫자 · 코드만 싣는다(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from foms.persistence.brain.models import BrainChange
from foms.services.brain.constants import CHANGE_OPEN, OP_CREATE, OP_LINK_ADD, OP_UPDATE
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.proposals import Proposer, after_values, known_text, propose_create, propose_link, propose_update
from foms.services.brain.store import current_object
from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent.case_memory import LEARNING_OUTCOMES
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.checks_rules import mask_marker_count
from foms.services.cs_agent.edit_detail_settings import PHOTO_LEARN_FIELD, WEEKLY_MODEL_FIELD
from foms.services.cs_agent.full_conversation import learn_cases, talk_on, with_talks
from foms.services.cs_agent.image_summaries import summaries_by_turn
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import call_learning, off_reason
from foms.services.cs_agent.masking import MaskLeak, leak_counts
from foms.services.cs_agent.photo_learning_prompt import (
    MAX_CASES, build_params, knowledge_lines, knowledge_rows, raw_proposals,
)
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.weekly_fix import LOOKBACK, in_window, staff_of, week_id
from foms.services.cs_agent.weekly_fix_gates import evidence_ok
from models import CsAgentTurn, SystemSetting

logger = logging.getLogger(__name__)

__all__ = ["AGENT", "WEEKS_KEY", "PhotoGroup", "claim_week", "collect_photo_groups", "file_proposals",
           "run_photo_learning"]

AGENT = "cs_photo"
WEEKS_KEY = "cs_agent_photo_learn_weeks"
MAX_GROUPS, MAX_FILED, MAX_WEEKS, TIMEOUT_S = 8, 10, 12, 120
MAX_NAME, MAX_TEXT, MAX_WHY, MAX_ALIASES, MAX_ALIAS = 60, 2000, 300, 20, 60
SITUATION_TYPES = frozenset({"situation", "build_rule"})
PRODUCT_TYPES = frozenset({"product_line", "option"})
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass(frozen=True)
class PhotoGroup:
    """(사진 종류, 의도) 묶음 — 사례 dict(차례 id · 상담 id · 직원 번호 · 가린 질문 · 가린 답 · 그 종류 사진 설명)."""

    kind: str
    intent: str
    cases: tuple[dict[str, Any], ...]


def _turn_rows(session: Any, since: datetime.datetime) -> list[Any]:
    """지난 7일 끝난 꼴(고침 · 직접 답 · 그대로) 차례 — 떼어 둔 줄 제외, 가린 칸 · 코드만."""
    turn = CsAgentTurn
    stmt = (select(turn.id, turn.chat_id, turn.sent_by_user_id, turn.desk_manager_id, turn.intent,
                   turn.masked_question, turn.staff_reply_masked, turn.last_user_message_id)
            .where(turn.brand == SEND_BRAND, turn.outcome.in_(LEARNING_OUTCOMES), turn.held_out.is_(False),
                   turn.staff_reply_masked.isnot(None), turn.updated_at >= since)
            .order_by(turn.id))
    return list(session.execute(stmt))


def _marks(lines: Sequence[Any]) -> dict[str, list[str]]:
    """차례가 읽은 사진들 → 메시지 id → 전체 대화에 끼울 표시 줄 ``▶ 사진 N (손님) 종류: 설명``(설계서 17.11.2)."""
    marks: dict[str, list[str]] = defaultdict(list)
    for number, line in enumerate(lines, start=1):
        marks[line.message_id].append(f"▶ 사진 {number} (손님) {line.text}")
    return dict(marks)


def collect_photo_groups(session: Any, now: datetime.datetime, *, cases_cap: Optional[int] = None) -> list[PhotoGroup]:
    """읽기 · 묶기(모듈 설명 1 · 2) — 근거 관문 전 묶음 전부((사진 종류, 의도) 순). ``cases_cap`` 이면 묶음마다 최근 사례부터
    그 수만(전체 대화를 실을 때 — 설계서 17.11.2)."""
    rows = _turn_rows(session, naive_utc(now - LOOKBACK))
    seen = summaries_by_turn(session, [row.id for row in rows])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_kind: dict[str, list[str]] = defaultdict(list)
        for line in seen.get(row.id, []):
            by_kind[line.kind].append(line.text)
        for kind, texts in by_kind.items():
            groups[(kind, row.intent or "unknown")].append({
                "turn_id": row.id, "chat_id": row.chat_id, "staff": staff_of(row), "question": row.masked_question,
                "sent": row.staff_reply_masked, "photos": texts[:2], "marks": _marks(seen[row.id]),
                "anchor": row.last_user_message_id})
    return [PhotoGroup(kind, intent, tuple(cases[-cases_cap:] if cases_cap else cases))
            for (kind, intent), cases in sorted(groups.items())]


def claim_week(session: Any, week: str) -> bool:
    """이 주에 처음이면 주 표를 남기고(커밋) 참 — 이미 돌았으면 거짓(두 컨테이너가 겹쳐도 한 번)."""
    if session.get(SystemSetting, WEEKS_KEY) is None:
        session.add(SystemSetting(setting_key=WEEKS_KEY, setting_value={"weeks": []},
                                  description="AI 상담팀원 사진 학습 — 주마다 한 번 표(설계서 17.11.1 의 7)"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    row = session.get(SystemSetting, WEEKS_KEY, populate_existing=True, with_for_update=True)
    weeks = list((row.setting_value or {}).get("weeks") or []) if isinstance(row.setting_value, dict) else []
    if week in weeks:
        session.rollback()
        return False
    row.setting_value = {"weeks": [*weeks, week][-MAX_WEEKS:]}
    session.commit()
    return True


# ── 우리 쪽 관문 ─────────────────────────────────────────────────────────
def _line(value: Any, limit: int) -> Optional[str]:
    """한 줄 글(앞뒤 빈칸 뺌 · 상한 · 줄 나눔 없음) — 아니면 ``None``."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\n" in value.strip():
        return None
    return value.strip()


def _clean(texts: Sequence[str], known: str) -> bool:
    """가림 관문 — 개인정보 꼴 · 가림 표시 0, 숫자는 이미 있는 지식 글에 있는 것만."""
    plain = known.replace(",", "")
    for text in texts:
        if any(leak_counts(text).values()) or mask_marker_count(text):
            return False
        if not all(number.replace(",", "") in plain for number in _NUMBER.findall(text)):
            return False
    return True


def _evidence(raw: dict[str, Any], group: PhotoGroup) -> list[int]:
    """근거 관문 — 통과면 근거 차례 id(정렬), 아니면 빈 목록."""
    ids = raw.get("evidence_turn_ids")
    if not isinstance(ids, list) or not ids or any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        return []
    by_id = {case["turn_id"]: case for case in group.cases}
    if not set(ids) <= set(by_id):
        return []
    return sorted(set(ids)) if evidence_ok(by_id[i] for i in set(ids)) else []


def _open(session: Any, op: str, key: Optional[str], after: dict[str, Any]) -> bool:
    """같은 안이 이미 열려 있나(같은 동작 · 키(만들기는 사진 학습이 낸 것 전부) · 같은 새 값)."""
    stmt = select(BrainChange.fields, BrainChange.link_to).where(BrainChange.status == CHANGE_OPEN, BrainChange.op == op)
    stmt = (stmt.where(BrainChange.proposed_by == Proposer.agent_named(AGENT).name) if key is None
            else stmt.where(BrainChange.item_key == key))
    for fields, link_to in session.execute(stmt):
        values = after_values(fields)
        if all(values.get(name) == value for name, value in after.items() if name != "link_to") and (
                "link_to" not in after or link_to == after["link_to"]):
            return True
    return False


# ── 넣기 — 제안 길로만 ───────────────────────────────────────────────────
def _filer(session: Any, raw: dict[str, Any], *, key: str, reason: str, evidence: list[str],
           now: datetime.datetime, known: str) -> tuple[Optional[str], Optional[Callable[[], Any]]]:
    """안 하나 → (막힌 까닭 코드, 넣는 함수). 꼴 · 대상이 틀리면 까닭만."""
    agent, kind = Proposer.agent_named(AGENT), raw.get("kind")
    common = dict(reason=reason, proposer=agent, evidence=evidence, now=naive_utc(now), known=known)
    name, text = _line(raw.get("name"), MAX_NAME), raw.get("text")
    text = text.strip() if isinstance(text, str) and text.strip() and len(text) <= MAX_TEXT else None
    if kind in ("new_situation", "new_build_rule"):
        if name is None or text is None:
            return "form", None
        values = {"name": name, "text": text, "status": "active", "visibility": "all", "evidence_kind": "case"}
        if _open(session, OP_CREATE, None, {"name": name, "text": text}):
            return "open_proposal", None
        item_type, layer = ("situation", "cs") if kind == "new_situation" else ("build_rule", "common")
        return None, lambda: propose_create(session, key=key, brand=SEND_BRAND, layer=layer, item_type=item_type,
                                            values=values, **common)
    target = current_object(session, str(raw.get("key") or "")) if raw.get("key") else None
    if kind == "update":
        if target is None or target.item_type not in SITUATION_TYPES or (name is None and text is None):
            return "target", None
        after = {field: value for field, value in (("name", name), ("text", text)) if value is not None}
        if _open(session, OP_UPDATE, target.item_key, after):
            return "open_proposal", None
        return None, lambda: propose_update(session, key=target.item_key, base_version=target.version, after=after,
                                            **common)
    if kind == "alias":
        words = [w for w in (_line(a, MAX_ALIAS) for a in raw.get("aliases") or [] if isinstance(a, str)) if w]
        if target is None or target.item_type not in PRODUCT_TYPES or not words:
            return "target", None
        payload = dict(target.payload or {})
        merged = list(dict.fromkeys([*(payload.get("aliases") or []), *words]))[:MAX_ALIASES]
        if merged == list(payload.get("aliases") or []):
            return "same", None
        after = {"payload": {**payload, "aliases": merged}}
        if _open(session, OP_UPDATE, target.item_key, after):
            return "open_proposal", None
        return None, lambda: propose_update(session, key=target.item_key, base_version=target.version, after=after,
                                            **common)
    if kind == "link":
        end = current_object(session, str(raw.get("target_key") or "")) if raw.get("target_key") else None
        if target is None or target.item_type != "situation" or end is None or end.item_type not in PRODUCT_TYPES:
            return "target", None
        if _open(session, OP_LINK_ADD, target.item_key, {"link_to": end.item_key}):
            return "open_proposal", None
        link = {name: common[name] for name in ("reason", "proposer", "evidence", "now")}
        return None, lambda: propose_link(session, op=OP_LINK_ADD, kind="applies_to", from_key=target.item_key,
                                          to_key=end.item_key, **link)
    return "form", None


def file_proposals(session: Any, raw: Sequence[dict[str, Any]], groups: Sequence[PhotoGroup], *, week: str,
                   now: datetime.datetime, known: str) -> dict[str, int]:
    """관문(우리 쪽) → 제안 길. 넣은 수(``filed``)와 막힌 까닭별 수. 커밋은 부르는 쪽."""
    counts: dict[str, int] = {"filed": 0}
    for number, item in enumerate(raw[:MAX_FILED * 2], start=1):
        index, why = item.get("group"), _line(item.get("why"), MAX_WHY)
        code: Optional[str] = None
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(groups) or why is None:
            code = "form"
        elif not _clean([str(item.get(n) or "") for n in ("name", "text", "why")]
                        + [str(a) for a in item.get("aliases") or []], known):
            code = "mask"
        elif not (ids := _evidence(item, groups[index])):
            code = "evidence"
        elif counts["filed"] >= MAX_FILED:
            code = "cap"
        if code is None:
            group = groups[index]
            reason = f"사진 학습({group.kind} · 의도 {group.intent}) — {why}"[:500]
            code, make = _filer(session, item, key=f"lahom/photo-{week.lower()}-{index}-{number}", reason=reason,
                                evidence=[f"case:{i}" for i in ids], now=now, known=known)
            if make is not None:
                try:
                    make()
                except BrainStoreError as exc:  # 글 관문 · 부딪침 · 근거 · 거절 · 대상 — 넣지 않고 센다
                    code = str(getattr(exc, "code", "brain")).lower()
        counts[code or "filed"] = counts.get(code or "filed", 0) + 1
    return counts


def _known(session: Any) -> str:
    """숫자 허용 글 — 회사 지식(반영 · 확정) + 라홈 상담 승인 지식."""
    cs = load_approved(session, SEND_BRAND)
    return "\n".join([known_text(session), *(item.text for item in cs.items)])


def run_photo_learning(session: Any, *, now: datetime.datetime, client: Any = None,
                       reader: Any = None) -> dict[str, Any]:
    """사진 학습 한 번(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다 — 반영하는 일은 하지 않는다(승인은 사람).

    ``reader`` 는 전체 대화를 읽는 채널톡 읽기 도우미(감시 바퀴가 넘긴다 — 없으면 전체 대화 없이 예전 재료)."""
    if not in_window(now):
        return {"off": "not_window"}
    off, cfg = off_reason(session, PHOTO_LEARN_FIELD)
    if off is not None:
        session.rollback()
        return {"off": off}
    week = week_id(now)
    if not claim_week(session, week):
        return {"off": "already_this_week"}
    talks = talk_on(cfg) and reader is not None  # 전체 대화를 실을 때만 묶음당 사례 수를 줄인다(아니면 예전 그대로)
    groups = collect_photo_groups(session, now, cases_cap=learn_cases(cfg) if talks else None)
    session.commit()  # 채널톡 읽기 동안 읽기 트랜잭션을 열어 두지 않는다
    ready = [group for group in groups if evidence_ok(group.cases)][:MAX_GROUPS]
    ready = with_talks(ready, reader, cfg, brand=SEND_BRAND, shown=MAX_CASES) if ready and talks else ready
    counts: dict[str, Any] = {"week": week, "groups": len(groups), "evidence_ok": len(ready), "proposed": 0,
                              "filed": 0, "blocked": {}, "halted": None}
    if ready:
        try:
            params = build_params(ready, knowledge_lines(knowledge_rows(session)), model=str(cfg.get(WEEKLY_MODEL_FIELD)),
                                  cfg=cfg)
            session.commit()
            called = call_learning(session, params, cfg=cfg, now=now, timeout_s=TIMEOUT_S, client=client)
            raw = raw_proposals(called.response)
            counts["proposed"] = len(raw)
            got = file_proposals(session, raw, ready, week=week, now=now, known=_known(session))
            session.commit()
            counts["filed"] = got.pop("filed")
            counts["blocked"] = got
        except MaskLeak:
            session.rollback()
            counts["halted"] = "mask_leak"
        except BrainError as exc:
            session.rollback()
            counts["halted"] = exc.code
    logger.info("[CS 사진 학습] week=%s groups=%d evidence_ok=%d proposed=%d filed=%d blocked=%s halted=%s", week,
                counts["groups"], counts["evidence_ok"], counts["proposed"], counts["filed"], counts["blocked"],
                counts["halted"])
    return counts
