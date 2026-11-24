"""넘긴 상담 배우기 — 직원이 직접 한 답을 날마다 회사 지식으로(사장님 11-11 '넘긴 것을 학습해서 다음엔 AI 가 답하게' · 11-19
'매일 학습하고 온톨로지 만들고 계속 업그레이드 — 매번 승인 대신 즉시 반영' · 11-20 'AI 초안 끄고 배움에 모든 하루 비용 · 학습 모델은
난이도에 따라 · 뭐든지 다 배워서 자동 적용').

직원이 데스크에서 직접 답한 차례(사례 기억 :mod:`.case_memory` 가 가린 직원 답을 붙인다)에서 사실 · 정책 · 응대 절차 · 상황 · 제작
조건 · 비슷한 말을 회사 지식으로 만든다(사진 학습 :mod:`.photo_learning` 과 같은 제안 길).

WORKER 15분 바퀴 학습 몫(:mod:`.learning_pass`)이 부르고, **밤(KST :data:`WINDOW_HOURS`) 창 안에서 남은 사례가 없을 때까지**
바퀴마다 한 번씩 돈다(:data:`MAX_RUNS` 번까지 — 부르기 전에 횟수와 잠깐 잠금을 남긴다, :func:`claim_day`. 재시작 · 두 컨테이너가
겹쳐도 같은 사례를 두 번 읽지 않게). 읽을 사례가 없거나 부르기가 실패하면(돈 상한 포함) 그 밤을 닫는다(:func:`close_day`). 끄고
켜기는 :func:`.learning_brain.off_reason`(패널 '넘긴 상담 배우기' · 비상 정지 · 초안 스위치 '끔' · 학습 돈 상한) — 초안 스위치가
'배우기만'(:data:`.turns.DRAFT_LEARN`)이면 초안 두뇌 없이 차례 줄만 모이고 이 길은 그대로 돈다.

1. **읽기(가린 글만 — 뭐든지 다)**: 지난 :data:`LEARN_LOOKBACK` 라홈 차례 가운데 가린 직원 답이 있고 끝난 꼴이 고침 · 직접 답이며
   (복사 · 버림 · 초안 그대로 보냄 제외) 떼어 둔 줄이 아닌 것 — 건너뛴 차례는 넘긴 까닭을 가리지 않고 모두(불만 · 주문 조회 ·
   할인 환불 · 사람이 정하는 금액 · 견적 계산 · 배우기만 포함. 그 손님 사정을 빼는 일은 지시문이 맡는다), 'AI 냐 사람이냐' 차례만
   뺀다(:data:`.send_record.NOT_TAUGHT_REASONS`). 패널 '초안이 나간 상담도 배우기'가 켜져 있으면 AI 초안이 나간 차례도 읽는다.
   **이미 읽은 차례는 다시 읽지 않는다**(:func:`used_ids`) — 읽는 규칙이 바뀌면(:data:`POLICY`) 읽은 표를 한 번 비워 지난 사례를
   새 규칙으로 다시 읽는다(:func:`fresh_policy`). **새 것부터** 읽는다.
2. **묶음 · 모델(:mod:`.handoff_learning_pick`)**: 새 것부터 :data:`POOL` 개를 보고 상담마다 어려움을 가른 뒤, 가장 새 사례의 갈래
   하나만 이번 묶음으로 담는다. 어려운 묶음(고쳐 보냄 · 불만 · 금액 · 사진 · 긴 상담)은 작게 · 가장 센 모델로, 쉬운 묶음은 패널
   '한 번에 읽는 사례 수'만큼 · 한 단계 아래 모델로.
3. **재료 — 상담 전체 대화 · 사진(사장님 11-19)**: 상담마다 전체 대화(:func:`.full_conversation.read_talk` — 가린 글)를 한 번
   읽고, 그 상담의 차례들이 읽은 손님 사진 설명(:func:`.image_summaries.summaries_by_turn`)을 그 사진이 온 글 자리에 ``▶`` 줄로
   끼운다. 자 수 상한 안이면 전체를 한 번만 싣고 같은 상담의 다른 사례는 그 대화를 가리킨다. 넘으면 사례마다 그 손님 글을 가운데
   둔 앞뒤 대화 창. 대화를 못 읽으면 질문 앞 6줄. 조각마다 가림 검사 — 하나라도 걸리면 그 사례만 뺀다(``mask_dropped``).
   이번 묶음 상담의 손님 사진 · 직원 그림은 사진 그 자체도 같이 보낸다(:mod:`.handoff_learning_photos` — 사장님 11-24).
4. **두뇌**: 회사 지식 · 온톨로지 목록 · 이미 모아 둔 다른 말과 견줘 안을 구조화 출력으로. 부르기가 끝나면 보낸 차례를 '읽음'으로
   적는다(부르기가 실패하면 적지 않아 다음 바퀴 · 다음 밤에 다시 본다).
5. **관문 · 넣기**(:mod:`.handoff_learning_route` · :mod:`.handoff_learning_onto`): 꼴 · 가림 · 근거 · 숫자 · 대상 · 같음 · 겹침 ·
   놓을 자리(같음 · 더함 · 새 지식 · 부딪침 · 이미 정함 · 규칙 아님 — 11-22) → 되풀이 문턱(한 상담뿐인 말은 '기다리는 말' — 11-23)
   → 제안 길. 패널 '배운 것 바로 반영'이 켜져 있으면 관문을 지난 안을 그 자리에서 반영한다(:func:`auto_learn`). 지금 지식과 다른
   말은 서로 다른 손님 둘 이상이면 그 항목을 바로 고친다.

로그 · 결과에는 숫자 · 코드만 싣는다(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.brain.apply import AutoLearn
from foms.services.brain.constants import CHANGE_OPEN
from foms.services.brain.proposals import known_text
from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent import photo_learning_prompt as onto_prompt
from foms.services.cs_agent.case_memory import OUTCOME_DIRECT, OUTCOME_EDITED
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.drafting import SKIP_CHECK, SKIP_HANDOFF
from foms.services.cs_agent.full_conversation import MIN_CASE_CHARS, case_limit, read_talk, talk_on, talk_text
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD, CASES_FIELD, EDIT_LEARN_FIELD, HANDOFF_LEARN_FIELD
from foms.services.cs_agent.handoff_learning_gates import EVIDENCE_MIN_CHATS, open_cards, seen_proposals
from foms.services.cs_agent.handoff_learning_onto import file_ontology
from foms.services.cs_agent.handoff_learning_photos import BatchPhotos, batch_photos
from foms.services.cs_agent.handoff_learning_pick import model_for, pick_batch
from foms.services.cs_agent.handoff_learning_route import file_proposals
from foms.services.cs_agent.handoff_learning_prompt import (
    anchor_mark, build_params, case_lines, complete, differs_lines, knowledge_lines, knowledge_rows, pending_lines,
    raw_ontology, raw_proposals, talk_window,
)
from foms.services.cs_agent.image_summaries import summaries_by_turn
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.learning_brain import call_learning, off_reason
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.send import SEND_BRAND
from foms.services.cs_agent.send_record import NOT_TAUGHT_REASONS, SEND_SENT
from foms.services.cs_agent.state import KST
from foms.services.cs_agent.turns import SKIP_LEARN_ONLY, STATE_SKIPPED
from models import CsAgentTurn, SecurityLog, SystemSetting, User

logger = logging.getLogger(__name__)

__all__ = [
    "LEARN_LOOKBACK", "POLICY", "POOL", "STORE_KEY", "WINDOW_HOURS",
    "DIRECT", "EDITED", "LEASE", "MAX_RUNS", "auto_learn", "claim_day", "close_day", "collect_cases", "day_id",
    "fresh_policy", "in_window", "mark_used", "release", "run_handoff_learning", "used_ids",
]

STORE_KEY = "cs_agent_handoff_learn"
WINDOW_HOURS = (0, 7)  # 날마다 KST 0시 ~ 7시 앞(상담이 없는 시간 — 월요일 3 ~ 6시 주간 고침 안 · 사진 학습 창과 겹쳐도 길이 다르다)
#: 읽는 창 — 차례 줄이 남아 있는 동안(운영 차례 줄은 10월 말부터). 읽은 차례 표가 같은 사례를 두 번 막는다.
LEARN_LOOKBACK = datetime.timedelta(days=30)
MAX_DAYS, MAX_USED, MAX_SCAN, MAX_PENDING, TIMEOUT_S = 14, 8000, 4000, 30, 420
EDITED = "edited"  # 사례 갈래 — AI 초안을 직원이 고쳐 보낸 차례(패널 '초안이 나간 상담도 배우기')
DIRECT = "direct"  # 사례 갈래 — AI 초안을 안 쓰고 직원이 직접 답한 차례(같은 칸)
#: 한 밤에 부르는 횟수 상한(창 7시간 · 15분 바퀴) · 부르는 동안의 잠깐 잠금(겹친 컨테이너가 같은 사례를 읽지 않게).
MAX_RUNS, LEASE = 28, datetime.timedelta(minutes=10)
#: 읽는 규칙 판 — 바뀌면 읽은 차례 표를 한 번 비운다(:func:`fresh_policy`). 2 = 11-20 '뭐든지 다'(모든 까닭 · 30일 · 난이도별 모델).
POLICY = 2
POOL = 200  # 한 번에 갈래를 가를 사례 수(새 것부터)
#: 답이 출력 상한에 끊기거나 시간을 넘기면 다음 바퀴는 묶음을 반으로 줄인다(이 횟수까지 — 같은 묶음에 밤마다 걸려 멈추지 않게). 성공하면 되돌린다.
MAX_SHRINK = 4
CUT_CODES: frozenset[str] = frozenset({"incomplete", "timeout"})


def day_id(now: datetime.datetime) -> str:
    """KST 날 이름(예 ``2026-11-11``)."""
    return now.astimezone(KST).date().isoformat()


def in_window(now: datetime.datetime) -> bool:
    """KST :data:`WINDOW_HOURS` 안인가(날마다)."""
    return WINDOW_HOURS[0] <= now.astimezone(KST).hour < WINDOW_HOURS[1]


# ── 날 표 · 읽은 차례 표(SystemSetting 한 줄) ─────────────────────────────
def _doc(row: Any) -> dict[str, Any]:
    """저장 값 → ``{"days": [닫은 KST 날], "used": [차례 id], "runs": {KST 날: 부른 횟수}, "lease": 잠금 끝 시각, "policy":
    읽는 규칙 판}`` 사본(틀린 칸은 빈 값)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    days = [d for d in value.get("days") or [] if isinstance(d, str)] if isinstance(value.get("days"), list) else []
    used = ([i for i in value.get("used") or [] if isinstance(i, int) and not isinstance(i, bool)]
            if isinstance(value.get("used"), list) else [])
    runs = value.get("runs") if isinstance(value.get("runs"), dict) else {}
    runs = {d: n for d, n in runs.items() if isinstance(d, str) and isinstance(n, int) and not isinstance(n, bool)}
    lease = value.get("lease") if isinstance(value.get("lease"), str) else None
    policy = value.get("policy") if isinstance(value.get("policy"), int) and not isinstance(value.get("policy"), bool) else 1
    shrink = value.get("shrink") if isinstance(value.get("shrink"), int) and not isinstance(value.get("shrink"), bool) else 0
    return {"days": days, "used": used, "runs": runs, "lease": lease, "policy": policy, "shrink": max(0, min(shrink, MAX_SHRINK))}


def _locked(session: Any) -> Any:
    """표 줄을 잠가 읽는다(없으면 먼저 만들어 커밋)."""
    if session.get(SystemSetting, STORE_KEY) is None:
        session.add(SystemSetting(setting_key=STORE_KEY, setting_value={"days": [], "used": []},
                                  description="AI 상담팀원 넘긴 상담 배우기 — 날마다 한 번 표 · 읽은 차례"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, STORE_KEY, populate_existing=True, with_for_update=True)


def _put(row: Any, doc: dict[str, list[Any]]) -> None:
    row.setting_value = doc
    flag_modified(row, "setting_value")


def _leased(doc: dict[str, Any], now: datetime.datetime) -> bool:
    """다른 부르기가 아직 도는가(잠금 끝 시각이 지금보다 뒤)."""
    try:
        return doc["lease"] is not None and datetime.datetime.fromisoformat(doc["lease"]) > now
    except ValueError:
        return False


def claim_day(session: Any, day: str, now: Optional[datetime.datetime] = None) -> bool:
    """이 밤에 한 번 더 불러도 되면 횟수 · 잠깐 잠금을 남기고(커밋) 참 — 그 밤을 닫았거나(:func:`close_day`) :data:`MAX_RUNS` 번
    불렀거나 다른 부르기가 도는 중이면 거짓(두 컨테이너가 겹쳐도 같은 사례를 두 번 읽지 않는다)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    row = _locked(session)
    doc = _doc(row)
    done = doc["runs"].get(day, 0)
    if day in doc["days"] or done >= MAX_RUNS or _leased(doc, now):
        session.rollback()
        return False
    runs = dict(sorted({**doc["runs"], day: done + 1}.items())[-MAX_DAYS:])
    _put(row, {**doc, "runs": runs, "lease": (now + LEASE).isoformat()})
    session.commit()
    return True


def release(session: Any) -> None:
    """잠깐 잠금을 푼다(커밋) — 한 번 부르기가 끝났다."""
    row = _locked(session)
    _put(row, {**_doc(row), "lease": None})
    session.commit()


def close_day(session: Any, day: str) -> None:
    """그 밤을 닫는다(커밋) — 읽을 사례가 없거나 부르기가 실패했다. 다음 바퀴는 다음 밤까지 부르지 않는다."""
    row = _locked(session)
    doc = _doc(row)
    if day not in doc["days"]:
        _put(row, {**doc, "days": [*doc["days"], day][-MAX_DAYS:]})
    session.commit()


def fresh_policy(session: Any) -> bool:
    """읽는 규칙 판이 바뀌었으면 읽은 차례 표를 한 번 비우고(커밋) 참 — 지난 사례를 새 규칙으로 다시 읽는다. 이미 넣은 지식과 같은
    안은 같음 · 겹침 관문이 막는다."""
    row = _locked(session)
    doc = _doc(row)
    if doc["policy"] == POLICY:
        session.rollback()
        return False
    _put(row, {**doc, "used": [], "policy": POLICY})
    session.commit()
    return True


def _shrink(session: Any, *, grow: bool) -> None:
    """묶음 줄이기 횟수를 하나 올리거나(``grow``) 하나 내린다(커밋 — 바뀔 때만 쓴다. 한 번 성공했다고 곧바로 큰 묶음으로
    돌아가면 실패 · 성공이 번갈아 나와 실패 때마다 최악값이 학습 돈에 잡힌다)."""
    row = _locked(session)
    doc = _doc(row)
    wanted = min(MAX_SHRINK, doc["shrink"] + 1) if grow else max(0, doc["shrink"] - 1)  # 한 번에 하나씩 되돌린다
    if wanted != doc["shrink"]:
        _put(row, {**doc, "shrink": wanted})
    session.commit()


def used_ids(session: Any) -> frozenset[int]:
    """이미 두뇌에 보낸(또는 가림 검사로 뺀) 차례 id."""
    return frozenset(_doc(session.get(SystemSetting, STORE_KEY, populate_existing=True))["used"])


def mark_used(session: Any, ids: Iterable[int]) -> None:
    """차례를 '읽음'으로 적고 커밋한다(최근 :data:`MAX_USED` 개 — 7일 창 밖 차례는 어차피 다시 안 고른다)."""
    fresh = [int(i) for i in ids]
    if not fresh:
        return
    row = _locked(session)
    doc = _doc(row)
    merged = list(dict.fromkeys([*doc["used"], *fresh]))[-MAX_USED:]
    _put(row, {**doc, "used": merged})
    session.commit()


# ── 읽기 ─────────────────────────────────────────────────────────────────
def _turn_rows(session: Any, since: datetime.datetime, *, edits: bool = False) -> list[Any]:
    """지난 창의 직원이 직접 답한 차례(가린 직원 답이 있는 것 · 떼어 둔 줄 제외) — 가린 칸 · 코드만, **새 것부터**. 건너뛴 차례는
    넘긴 까닭을 가리지 않고 모두('AI 냐' 차례만 뺀다). ``edits`` 면 AI 초안이 나간 차례 가운데 직원이 고쳐 보냈거나 직접 답한 것도."""
    turn = CsAgentTurn
    picked = and_(turn.state == STATE_SKIPPED,
                  or_(turn.handoff_reason.is_(None), turn.handoff_reason.notin_(NOT_TAUGHT_REASONS)))
    if edits:  # 사장님 11-11 고친 답 + 까닭 · 11-19 '모든 대화' — 초안을 안 쓰고 직접 답한 것도
        picked = or_(picked, turn.state != STATE_SKIPPED)
    stmt = (select(turn.id, turn.chat_id, turn.intent, turn.error_code, turn.handoff_reason, turn.check_codes,
                   turn.masked_question, turn.staff_reply_masked, turn.masked_context, turn.last_user_message_id,
                   turn.desk_manager_id, turn.send_state, turn.state, turn.masked_draft, turn.edit_reason,
                   turn.edit_detail_masked, turn.sent_by_user_id, turn.outcome)
            .where(turn.brand == SEND_BRAND, picked,
                   turn.outcome.in_((OUTCOME_EDITED, OUTCOME_DIRECT)), turn.held_out.is_(False),
                   turn.staff_reply_masked.isnot(None), turn.updated_at >= since)
            .order_by(turn.id.desc()).limit(MAX_SCAN))
    return list(session.execute(stmt))


def _staff(row: Any) -> Optional[str]:
    """답한 직원 표지 — 채널톡 상담원 번호, 없으면 FOMS 직원 번호(FOMS 화면으로 고쳐 보낸 차례)."""
    if row.desk_manager_id:
        return str(row.desk_manager_id)
    return f"user-{int(row.sent_by_user_id)}" if row.sent_by_user_id is not None else None


def _case(row: Any) -> dict[str, Any]:
    """사례 dict — 넘김 · 검사 걸림 · 고쳐 보냄(``reason`` = ``edited`` · AI 초안 · 고친 까닭) · 초안 안 씀(``direct`` · AI 초안)."""
    drafted = row.state != STATE_SKIPPED
    edited = drafted and row.outcome == OUTCOME_EDITED
    reason = (EDITED if edited else DIRECT if drafted else row.handoff_reason if row.error_code == SKIP_HANDOFF
              else row.error_code if row.error_code in (SKIP_CHECK, SKIP_LEARN_ONLY) else "other")
    return {"turn_id": row.id, "chat_id": row.chat_id, "intent": row.intent, "reason": reason,
            "question": row.masked_question, "reply": row.staff_reply_masked, "context": row.masked_context,
            "anchor": row.last_user_message_id, "staff": _staff(row), "taught": row.send_state == SEND_SENT and not drafted,
            "draft": row.masked_draft if drafted else None, "why": row.edit_detail_masked if edited else None,
            "chip": row.edit_reason if edited else None}


def collect_cases(session: Any, now: datetime.datetime, *, cap: int, edits: bool = False) -> list[dict[str, Any]]:
    """읽기(모듈 설명 1) — 사례 dict(차례 id · 상담 id · 의도 · 넘긴 까닭 · 가린 질문 · 가린 직원 답 · 질문 앞 6줄 · 기준 글 id)."""
    used = used_ids(session)
    out = []
    for row in _turn_rows(session, naive_utc(now - LEARN_LOOKBACK), edits=edits):
        if row.id in used or not (row.staff_reply_masked or "").strip():
            continue
        out.append(_case(row))
        if len(out) >= cap:
            break
    return out


def _photo_marks(session: Any, chats: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    """상담 → (메시지 id → 사진 줄) — 그 상담의 모든 차례가 읽은 손님 사진 설명(가린 글 · 같은 사진은 한 번)."""
    rows = session.execute(select(CsAgentTurn.id, CsAgentTurn.chat_id).where(
        CsAgentTurn.brand == SEND_BRAND, CsAgentTurn.chat_id.in_(list(chats))).order_by(CsAgentTurn.id)).all() if chats else []
    seen = summaries_by_turn(session, [row.id for row in rows])
    out: dict[str, dict[str, list[str]]] = {}
    shown: set[tuple[str, str, str]] = set()
    for row in rows:
        for line in seen.get(row.id, ()):
            chat = str(row.chat_id)
            if (chat, line.message_id, line.text) in shown:
                continue
            shown.add((chat, line.message_id, line.text))
            marks = out.setdefault(chat, {})
            number = sum(len(lines) for lines in marks.values()) + 1
            marks.setdefault(line.message_id, []).append(f"▶ 사진 {number} (손님) {line.text}")
    return out


def _talks(reader: Any, cfg: Any, cases: Sequence[dict[str, Any]],
           photos: Optional[dict[str, dict[str, list[str]]]] = None) -> dict[int, dict[str, Any]]:
    """사례마다 대화 재료 — 차례 id → ``{"talk": 글, "whole": 전체인가}`` 또는 ``{"talk_ref": 그 대화를 실은 사례}``(모듈 설명 2).
    상담마다 한 번만 읽는다(이 부르기 메모리에서만). 끔 · 읽기 도우미 없음 · 못 읽음 · 그 손님 글을 못 찾음이면 빠진다(그 사례는
    질문 앞 6줄)."""
    if not talk_on(cfg) or reader is None or not cases:
        return {}
    by_chat: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        by_chat.setdefault(str(case["chat_id"] or ""), []).append(case)
    limit = case_limit(cfg, len(by_chat))
    out: dict[int, dict[str, Any]] = {}
    for chat, mine in by_chat.items():
        talk = read_talk(reader, SEND_BRAND, chat, cfg) if chat else None
        if talk is None:
            continue
        pictures = (photos or {}).get(chat) or {}
        if sum(len(text) for _, text in talk.turns) <= limit:  # 전체가 들어간다 — 한 번만 싣고 나머지는 가리킨다
            marks = {key: list(lines) for key, lines in pictures.items()}
            for case in mine:
                if str(case["anchor"] or "") in talk.ids:
                    marks.setdefault(str(case["anchor"]), []).append(anchor_mark(case["turn_id"]))
            whole = talk_text(talk, limit=limit, marks=marks)
            if whole:
                out[mine[0]["turn_id"]] = {"talk": whole, "whole": True}
                out.update({case["turn_id"]: {"talk_ref": mine[0]["turn_id"]} for case in mine[1:]})
                continue
        share = max(MIN_CASE_CHARS, limit // len(mine))
        for case in mine:
            text = talk_window(talk, str(case["anchor"] or ""), share, pictures)
            if text:
                out[case["turn_id"]] = {"talk": text}
    return out


def _blocks(cases: Sequence[dict[str, Any]], talks: dict[int, dict[str, Any]],
            ) -> tuple[list[dict[str, Any]], list[list[str]], list[int]]:
    """사례 줄 만들기 — (보낼 사례, 사례 줄, 가림 검사로 뺀 차례 id). 전체 대화를 실은 사례가 빠지면 같은 상담의 다음 사례가
    대신 싣는다."""
    sent, blocks, dropped = [], [], []
    holder: dict[int, int] = {}
    for case in cases:
        extra = dict(talks.get(case["turn_id"]) or {})
        first = extra.get("talk_ref")
        if first is not None:
            extra = {"talk_ref": holder[first]} if first in holder else dict(talks.get(first) or {})
        try:
            blocks.append(case_lines({**case, **extra}))
        except MaskLeak:  # 그 사례만 뺀다(가림 검사 — 글은 남기지 않는다)
            dropped.append(case["turn_id"])
            continue
        sent.append(case)
        if extra.get("whole"):
            holder[first if first is not None else case["turn_id"]] = case["turn_id"]
    return sent, blocks, dropped


def auto_learn(session: Any, cfg: Any) -> Optional[AutoLearn]:
    """패널 '배운 것 바로 반영'이 켜져 있으면 그 길(:class:`foms.services.brain.apply.AutoLearn`), 아니면 ``None``.

    누구 이름으로 감사 · 판 줄을 남기나 — 그 칸을 마지막으로 바꾼 사람이 지금도 켜진 ADMIN 이면 그 사람, 아니면 가장 먼저 만든
    켜진 ADMIN. 켜진 ADMIN 이 하나도 없으면 ``None``(승인 대기로만)."""
    if cfg.get(AUTO_FIELD) is not True:
        return None
    admins = [int(i) for i in session.execute(select(User.id).where(
        func.upper(User.role) == "ADMIN", User.is_active.is_(True)).order_by(User.id)).scalars()]
    last = session.execute(select(SecurityLog.user_id).where(
        SecurityLog.action == "CS_AGENT_SETTINGS_UPDATE", SecurityLog.message.like(f"%{AUTO_FIELD}%"))
        .order_by(SecurityLog.id.desc()).limit(1)).scalar()
    if last in admins:
        return AutoLearn(int(last))
    return AutoLearn(admins[0]) if admins else None


def _cap(cfg: Any) -> int:
    """패널 '한 번에 읽는 사례 수'."""
    value = cfg.get(CASES_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 20


def _known(session: Any) -> str:
    """숫자 허용 글 — 회사 지식(반영 · 확정) + 라홈 상담 승인 지식."""
    cs = load_approved(session, SEND_BRAND)
    return "\n".join([known_text(session), *(item.text for item in cs.items)])


def _propose(session: Any, sent: list[dict[str, Any]], blocks: list[list[str]], used: list[int], *, cfg: Any,
             now: datetime.datetime, client: Any, counts: dict[str, Any], tier: str, images: Sequence[Any] = ()) -> None:
    """두뇌 → 읽음 표 → 관문 → 제안 길 · 바로 반영(모듈 설명 3 · 4)."""
    rows = knowledge_rows(session)
    knowledge, approved = knowledge_lines(rows), [row.text for row in rows if row.text]
    ontology = onto_prompt.knowledge_lines(onto_prompt.knowledge_rows(session))
    pending = pending_lines([(label, text) for status, _key, label, text in seen_proposals(session)
                             if status == CHANGE_OPEN][:MAX_PENDING])
    model, effort = model_for(tier)
    params = build_params(blocks, knowledge, pending, model=model, cfg=cfg, ontology=ontology,
                          differs=differs_lines(open_cards(session)), effort=effort, images=images)
    session.commit()
    called = call_learning(session, params, cfg=cfg, now=now, timeout_s=TIMEOUT_S, client=client)
    if not complete(called.response):  # 출력 상한에 끊김 · 거절 — 읽음으로 적지 않는다(안이 통째로 사라지지 않게)
        counts["halted"] = "incomplete"
        return
    mark_used(session, used)
    raw, onto = raw_proposals(called.response), raw_ontology(called.response)
    counts["proposed"] = len(raw) + len(onto)
    known = _known(session)
    approved += [item.text for item in load_approved(session, SEND_BRAND).items]
    auto = auto_learn(session, cfg)
    session.commit()
    got = file_proposals(session, raw, sent, now=now, known=known, approved=approved, auto=auto, cfg=cfg, client=client)
    more = file_ontology(session, onto, sent, now=now, known=known, auto=auto)
    session.commit()
    for name, key in (("filed", "filed"), ("applied", "applied"), ("cards", "conflict_card"), ("fixed", "differs_fixed"),
                      ("new", "placed_new"), ("added", "placed_added"), ("same", "same"), ("decided", "decided_before"),
                      ("not_rule", "not_rule"), ("held", "held"), ("promoted", "promoted")):  # 놓을 자리(11-22) · 되풀이 문턱(11-23)
        counts[name] = got.pop(key, 0) + more.pop(key, 0)
    counts["blocked"] = {code: got.get(code, 0) + more.get(code, 0) for code in sorted({*got, *more})}


def run_handoff_learning(session: Any, *, now: datetime.datetime, client: Any = None,
                         reader: Any = None) -> dict[str, Any]:
    """넘김 학습 한 번(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다.

    ``reader`` 는 전체 대화를 읽는 채널톡 읽기 도우미(감시 바퀴가 넘긴다 — 없으면 앞뒤 대화 없이 질문 앞 6줄)."""
    if not in_window(now):
        return {"off": "not_window"}
    off, cfg = off_reason(session, HANDOFF_LEARN_FIELD)
    if off is not None:
        session.rollback()
        return {"off": off}
    day = day_id(now)
    if not claim_day(session, day, now):
        return {"off": "already_today"}
    fresh_policy(session)
    pool = collect_cases(session, now, cap=POOL, edits=cfg.get(EDIT_LEARN_FIELD) is True)
    photos = _photo_marks(session, sorted({str(case["chat_id"] or "") for case in pool} - {""}))
    shrink = _doc(session.get(SystemSetting, STORE_KEY, populate_existing=True))["shrink"]
    tier, cases = pick_batch(pool, photos, _cap(cfg))
    cases = cases[:max(1, len(cases) >> shrink)]  # 앞 바퀴 답이 끊겼으면 반씩 줄여 다시
    session.commit()  # 채널톡 읽기 동안 읽기 트랜잭션을 열어 두지 않는다
    pics = batch_photos(session, reader, cfg, cases, photos, brand=SEND_BRAND)  # 이 묶음 상담의 사진 그 자체
    talks = _talks(pics.reader, cfg, cases, pics.marks)
    counts: dict[str, Any] = {"day": day, "tier": tier, "left": len(pool) - len(cases), "cases": len(cases),
                              "talks": len(talks), "mask_dropped": 0, "sent": 0, "proposed": 0, "filed": 0, "applied": 0,
                              "cards": 0, "fixed": 0, "new": 0, "added": 0, "same": 0, "decided": 0, "not_rule": 0,
                              "held": 0, "promoted": 0, "blocked": {}, "halted": None, "photos": 0, "photo_skipped": {}}
    try:
        _run(session, cases, talks, cfg=cfg, now=now, client=client, counts=counts, tier=tier, pics=pics)
    except Exception:  # 뜻밖의 오류 — 그 밤을 닫고 잠금을 푼 뒤 그대로 올린다(학습 몫이 길 이름 · 예외 종류만 적는다)
        session.rollback()
        close_day(session, day)
        release(session)
        raise
    cut = counts["halted"] in CUT_CODES  # 답이 끊김 · 시간 넘김 — 밤을 닫지 않고 반으로 줄여 다시
    if cut and len(cases) == 1:  # 하나로 줄여도 안 되는 사례 — 읽음으로 넘긴다(새 것부터라 밤마다 이 사례에서 멈춘다)
        mark_used(session, [cases[0]["turn_id"]])
        counts["skipped_case"] = 1
    if cut or (shrink and counts["halted"] is None):
        _shrink(session, grow=cut)
    if not cases or (counts["halted"] is not None and not cut):  # 남은 사례가 없다 · 부르기가 실패했다 — 이 밤은 여기까지
        close_day(session, day)
    release(session)
    logger.info("[CS 넘김 학습] day=%s tier=%s left=%d cases=%d talks=%d mask_dropped=%d sent=%d proposed=%d filed=%d "
                "applied=%d cards=%d fixed=%d new=%d added=%d same=%d decided=%d not_rule=%d held=%d promoted=%d "
                "blocked=%s halted=%s photos=%d photo_skipped=%s", day, tier, counts["left"], counts["cases"],
                counts["talks"], counts["mask_dropped"], counts["sent"], counts["proposed"], counts["filed"],
                counts["applied"], counts["cards"], counts["fixed"], counts["new"], counts["added"], counts["same"],
                counts["decided"], counts["not_rule"], counts["held"], counts["promoted"], counts["blocked"],
                counts["halted"], counts["photos"], counts["photo_skipped"])
    return counts


def _run(session: Any, cases: list[dict[str, Any]], talks: dict[int, dict[str, Any]], *, cfg: Any,
         now: datetime.datetime, client: Any, counts: dict[str, Any], tier: str, pics: Optional[BatchPhotos] = None) -> None:
    """사례 줄 → 두뇌 → 넣기(:func:`run_handoff_learning` 의 가운데 — 수는 ``counts`` 에 채운다). 사진은 보낼 사례 줄에 든
    번호만 같이 보낸다(:meth:`.handoff_learning_photos.BatchPhotos.pick`)."""
    sent, blocks, dropped = _blocks(cases, talks)
    counts.update(mask_dropped=len(dropped), sent=len(sent))
    if len({case["chat_id"] for case in sent}) < EVIDENCE_MIN_CHATS:
        mark_used(session, dropped)
        counts["halted"] = "too_few_customers" if sent else None
    else:
        images, counts["photos"], counts["photo_skipped"] = pics.pick(blocks) if pics is not None else ([], 0, {})
        try:
            _propose(session, sent, blocks, [*(case["turn_id"] for case in sent), *dropped], cfg=cfg, now=now,
                     client=client, counts=counts, tier=tier, images=images)
        except MaskLeak:
            session.rollback()
            counts["halted"] = "mask_leak"
        except BrainError as exc:
            session.rollback()
            counts["halted"] = exc.code
