"""회사 지식 물어보기 — 답하는 길 한 곳(설계서 10.2 '순서 고정' · D88 · D99 · 12절).

순서(바꾸지 않는다):

1. **여는 사람** — 스위치 · 여는 단계 · 내부 계정(:mod:`.chat_access`). 아니면 :class:`ChatError` ``forbidden``(404).
2. **가림** — 상담과 같은 가림(:func:`foms.services.cs_agent.masking.mask`) → 가림 검사 0 이어야 다음. 아니면 기록도 모델도 없이
   ``mask``(400). 이 뒤로는 가린 글만 쓴다(기록 · 모델 · 로그).
3. **사람마다 하루 질문 수** — 넘으면 ``person_cap``(429).
4. **찾기** — 묻는 사람의 보기 범위 안 후보만(:mod:`.chat_retrieve` — 읽기 도구 셋 · '확인 필요'는 사실만 · 의미 찾기가
   켜졌으면 **가린 질문**의 벡터를 더해 섞는다 — :mod:`.embeddings`). 쓸 수 있는 후보가
   없으면 모델을 부르지 않고 '모름 + 누구에게'(돈 0 — '확인 필요' 후보는 이름 · 까닭만 보인다).
5. **두뇌** — 후보 묶음 + 가린 질문 → 구조화 출력 하나(도구 없음 — :mod:`.chat_prompt`). 부르기는 :mod:`.chat_model`(상담 두뇌 길 ·
   챗봇 돈 줄 · 시간 상한). 돈 상한 ``money_cap``(503) · 준비 안 됨 ``not_ready`` · 시간 초과 · 오류 ``unavailable``.
6. **코드 확인** — 근거 키가 모두 쓸 수 있는 후보 안에 있어야 한다(하나라도 밖이면 답을 버림) · 근거 0 · ERP 질문 · 숫자가 근거
   항목 글 · 칸 · 계산기 값에 없음이면 답을 쓰지 않고 **'모름 + 누구에게'**(층 승인자 — D101).
7. **기록 · 쓰인 횟수** — 가린 질문 · 보인 답 · 근거 키 · 모름 · 확신 · 묻는 사람 번호(:mod:`.chat_log`), 답의 근거 키는 쓰인 횟수
   +1(:mod:`.usage` — 판 줄 아님). 커밋은 부르는 쪽(API). 모델을 부를 때 세션이 몇 번 커밋된다(돈 예약 · 바로잡기).

**ERP 주문 읽기**(접목판 ``erp_read`` 스위치가 켜진 사람만 — 설계서 2026-11-14-foms-graft 3.7, :mod:`foms.services.erp_ontology.ask`):
3 과 4 사이에 '번호 찾기(가리기 전 원문) → 읽기 권한 → 주문 · 방문 읽기'가 끼고, 읽은 주문이 있으면 두뇌 사용자 칸에 ERP 주문 칸 ·
근거 고를 값에 주문 키(``erp:order/<번호>``)가 더해진다(지시문은 그대로). 6 은 주문 키를 근거로 단 답만 ``kind = 'erp'`` 로 받고,
답 속 날짜 · 숫자는 주문 줄이나 근거 지식 글에 있어야 한다(아니면 '모름'). 7 은 근거 키에 주문 키까지 남기고 쓰인 곳
(``brain_usage_events`` — 읽은 주문 키 포함) · 실행 기록(``ai_agent_runs``)을 더한다. 답 값에 ``kind`` · ``erp`` 칸이 생긴다.
**스위치가 꺼졌으면 지시문 · 출력 꼴 · 답 · 기록이 지금과 글자까지 같다**(새 표 줄도 없다).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Optional

from foms.services.brain.access import screen_viewer
from foms.services.brain.chat_access import ask_viewer
from foms.services.brain.chat_log import asked_today, log_question
from foms.services.brain.chat_model import build_params, call_model
from foms.services.brain.chat_prompt import (
    ASK_ERP, ERP_CHECK_ANSWER, SYSTEM, ChatOutputError, default_ask, erp_block, output_schema, read_output, task_text,
    unknown_text,
)
from foms.services.brain.chat_retrieve import (
    WHY_LABELS, Retrieval, known_numbers_text, prompt_block, retrieve, weakest_confidence,
)
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.embeddings import query_vector, store_question_vector
from foms.services.brain.gates import numbers_known
from foms.services.brain.usage import READER_CHATBOT, count_reads
from foms.services.brain.usage_events import READER_CHATBOT as EVENT_READER, record_uses
from foms.services.cs_agent.brain_spend import BrainNotReady, BrainUnavailable, SpendCapReached
from foms.services.cs_agent.masking import leak_counts, mask
from foms.services.datetime_kst import now_kst
from foms.services.erp_ontology.ask import (
    TOOL_MASK, TOOL_SEARCH, ErpRead, Trace, answer_kind, dates_known, erp_view, mask_note, question_uses,
    read_question_order, record_run,
)
from foms.services.erp_ontology.read import order_id_of
from foms.services.graft_flags import enabled as graft_enabled

logger = logging.getLogger(__name__)

MAX_QUESTION = 500
#: 주문을 읽은 답이 코드 확인을 못 지난 까닭 — 근거에 주문 키 없음 · 모름 · 빈 답(``erp_check``) · 날짜 · 숫자(``erp_numbers``).
ERP_CHECK_WHYS: frozenset[str] = frozenset({"erp_check", "erp_numbers"})
#: 오류 코드 → HTTP 상태(API 가 정한 말만 보낸다).
STATUS: dict[str, int] = {"forbidden": 404, "shape": 400, "mask": 400, "person_cap": 429, "money_cap": 503,
                          "not_ready": 503, "unavailable": 503}


class ChatError(RuntimeError):
    """답하지 못했다 — ``code``(:data:`STATUS`) · 준비 안 됨이면 ``reason`` 코드. 글(질문 · 답)은 싣지 않는다."""

    def __init__(self, code: str, reason: Optional[str] = None) -> None:
        """코드 · 까닭 코드만."""
        super().__init__(code if reason is None else f"{code}:{reason}")
        self.code, self.reason = code, reason


@dataclass(frozen=True)
class Verified:
    """코드 확인을 지난 답 — 보일 글 · 근거 키 · 확인 필요 키 · 모름 · 물을 곳 · 층 · 확신(모델) · 까닭 코드."""

    answer: str
    evidence: list[str]
    checks: list[str]
    unknown: bool
    ask_team: Optional[str]
    layer: Optional[str]
    certainty: Optional[str]
    why: Optional[str] = None


def _first_layer(retrieval: Retrieval) -> Optional[str]:
    """가장 가까운 후보의 층(누구에게 물을지의 처음 값)."""
    return retrieval.candidates[0].layer if retrieval.candidates else None


def _unknown(retrieval: Retrieval, out: Optional[dict[str, Any]], why: str, checks: list[str]) -> Verified:
    """'모름 + 누구에게'."""
    layer = (out or {}).get("layer") or _first_layer(retrieval)
    erp_side = why == "erp" or why in ERP_CHECK_WHYS
    ask = ASK_ERP if erp_side else ((out or {}).get("ask_team") or default_ask(layer))
    text = ERP_CHECK_ANSWER if why in ERP_CHECK_WHYS else unknown_text(ask)
    return Verified(text, [], checks, True, ask, layer, (out or {}).get("confidence"), why)


def _verify_erp(out: dict[str, Any], retrieval: Retrieval, erp: ErpRead, checks: list[str], *,
                today: datetime.date) -> Verified:
    """주문을 읽은 답 — 근거에 주문 키 · 모름 아님 · 빈 답 아님 · 답 속 날짜 · 숫자가 주문 줄이나 근거 지식 글에 있음."""
    evidence = out["evidence_ids"]
    if out["unknown"] or not out["answer"] or erp.key not in evidence:
        return _unknown(retrieval, out, "erp_check", checks)
    knowledge = [key for key in evidence if key != erp.key]
    known = "\n".join([*erp.lines, known_numbers_text(retrieval, knowledge)])
    if not numbers_known(out["answer"], known) or not dates_known(out["answer"], known, today=today):
        return _unknown(retrieval, out, "erp_numbers", checks)
    return Verified(out["answer"], evidence, checks, False, None, out["layer"], out["confidence"])


def verify(out: dict[str, Any], retrieval: Retrieval, erp: Optional[ErpRead] = None, *,
           today: Optional[datetime.date] = None) -> Verified:
    """모델 출력을 코드로 다시 본다(10.2 의 4) — 밖 근거면 버림 · 근거 0 · ERP · 숫자 출처 · 빈 답이면 '모름'.

    ``erp`` (읽은 주문)가 있으면 주문 키도 근거로 고를 수 있고, ERP 답(``kind = 'erp'`` 이거나 주문 키를 근거로 단 답)은
    :func:`_verify_erp` 가 본다. ``erp`` 가 없으면 지금 판정 그대로다(ERP 답은 '모름').
    """
    usable = {c.key for c in retrieval.usable}
    checks = [k for k in out["check_ids"] if k in {c.key for c in retrieval.checks}]
    evidence = out["evidence_ids"]
    allowed = usable | ({erp.key} if erp is not None else set())
    if any(key not in allowed for key in evidence):
        return _unknown(retrieval, out, "evidence_outside", checks)
    if erp is not None and (out["kind"] == "erp" or erp.key in evidence):
        return _verify_erp(out, retrieval, erp, checks, today=today or now_kst().date())
    if out["kind"] == "erp":
        return _unknown(retrieval, out, "erp", checks)
    if out["unknown"] or not evidence or not out["answer"]:
        return _unknown(retrieval, out, "no_evidence", checks)
    if not numbers_known(out["answer"], known_numbers_text(retrieval, evidence)):
        return _unknown(retrieval, out, "numbers", checks)
    return Verified(out["answer"], evidence, checks, False, None, out["layer"], out["confidence"])


def _clean(question: Any) -> str:
    """묻는 글 꼴 — 글 · 1 ~ :data:`MAX_QUESTION` 자."""
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise ChatError("shape")
    return question.strip()


def _call(session: Any, cfg: Any, masked: str, retrieval: Retrieval, *, now: datetime.datetime,
          client: Any, erp: Optional[ErpRead] = None) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """두뇌 한 번 → (출력, 답한 모델). 오류는 :class:`ChatError`. 읽은 주문이 있으면 ERP 주문 칸 · 주문 키(근거 고를 값)를 더한다."""
    usable = [c.key for c in retrieval.usable] + ([erp.key] if erp is not None else [])
    block = erp_block(erp.key, erp.lines) if erp is not None else None
    params = build_params(
        model=cfg.get("model"), effort=cfg.get("effort"), max_tokens=cfg.get("max_tokens"), system=SYSTEM,
        user=task_text(question=masked, candidates=prompt_block(retrieval), today=now.date(), erp=block),
        schema=output_schema(usable, [c.key for c in retrieval.checks]))
    try:
        answered = call_model(session, params, cfg=cfg, now=now, client=client)
        return read_output(answered.text), answered.model
    except SpendCapReached:
        raise ChatError("money_cap") from None
    except BrainNotReady as exc:
        raise ChatError("not_ready", exc.code) from None
    except BrainUnavailable as exc:
        raise ChatError("unavailable", exc.code) from None
    except ChatOutputError:
        raise ChatError("unavailable", "bad_response") from None


def _view(row_id: int, verified: Verified, retrieval: Retrieval, *, left: int, cards: bool) -> dict[str, Any]:
    """화면 값 — 답 · 근거 칩(이름 · 유형 · 확신 · 마지막 확인) · 확인 중 칩 · 확신 · 물을 곳 · 남은 질문 수."""
    by_key = retrieval.by_key()
    chips = [{"key": k, "name": by_key[k].name, "type": by_key[k].item_type, "confidence": by_key[k].confidence,
              "checked_at": by_key[k].checked_at} for k in verified.evidence if k in by_key]
    checks = [{"key": k, "name": by_key[k].name, "type": by_key[k].item_type, "why": WHY_LABELS.get(by_key[k].why or "")}
              for k in verified.checks if k in by_key]
    return {"id": row_id, "answer": verified.answer, "unknown": verified.unknown, "ask_team": verified.ask_team,
            "evidence": chips, "checks": checks, "confidence": weakest_confidence(retrieval, verified.evidence),
            "certainty": verified.certainty, "left_today": max(0, left), "card_links": cards}


_COMPUTE = object()


def answer_masked(session: Any, viewer: Any, masked: str, *, cfg: Any, now: datetime.datetime,
                  client: Any = None, vector: Any = _COMPUTE, erp: Optional[ErpRead] = None,
                  trace: Optional[Trace] = None) -> tuple[Verified, Retrieval, Optional[str]]:
    """가린 질문 하나 → (확인한 답, 후보, 답한 모델) — 찾기 · 두뇌 · 코드 확인만(기록 · 상한 없음 — 평가 묶음 실행기도 쓴다).
    ``vector`` 를 주면 그 질문 벡터를 쓴다(안 주면 여기서 만든다). ``erp`` = 읽은 주문(ERP 주문 칸 — 지식 후보가 없어도 부른다) ·
    ``trace`` = 걸린 시간 모음(찾기 단계).

    Raises:
        ChatError: money_cap · not_ready · unavailable.
    """
    with (trace or Trace()).step(TOOL_SEARCH) as step:
        if vector is _COMPUTE:
            vector = query_vector(session, masked, cfg=cfg, now=now)  # 의미 찾기(D114) — 가린 글만 · 꺼짐 · 실패면 None
        retrieval = retrieve(session, viewer, masked, today=now.date(), vector=vector)
        step.what, step.detail = f"지식 후보 {len(retrieval.usable)}", f"checks={len(retrieval.checks)}"
    if not retrieval.usable and erp is None:  # 쓸 후보가 없으면 부르지 않는다(돈 0) — '확인 필요' 후보는 사실만 보인다
        checks = [c.key for c in retrieval.checks]
        return _unknown(retrieval, None, "needs_check" if checks else "no_candidates", checks), retrieval, None
    out, model = _call(session, cfg, masked, retrieval, now=now, client=client, erp=erp)
    return verify(out, retrieval, erp, today=now.date()), retrieval, model


def _erp_finish(session: Any, question_id: int, verified: Verified, erp: Optional[ErpRead], trace: Trace,
                now_utc: datetime.datetime) -> None:
    """ERP 읽기 스위치가 켜진 사람의 기록 — 쓰인 곳(질문 번호 · 읽은 주문 키 포함) · 실행 기록 한 줄(커밋은 부르는 쪽)."""
    keys = question_uses(verified.evidence, verified.unknown, erp)
    if keys:
        record_uses(session, keys, EVENT_READER, "question", question_id, now_utc)
    record_run(session, question_id=question_id, trace=trace, outcome=verified.why or "answered", now_utc=now_utc)
    logger.info("[회사 지식 물어보기] ERP 읽기 question=%s order=%s kind=%s", question_id,
                erp.order_id if erp is not None else None, answer_kind(verified.evidence, verified.unknown))


def ask(session: Any, user: Any, question: Any, *, client: Any = None,
        now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """물어보기 한 번(모듈 설명의 순서). 커밋은 부르는 쪽.

    Raises:
        ChatError: forbidden · shape · mask · person_cap · money_cap · not_ready · unavailable.
    """
    cfg = read_chat_settings(session)
    viewer = ask_viewer(user, cfg)
    if viewer is None:
        raise ChatError("forbidden")
    text = _clean(question)
    trace = Trace()
    with trace.step(TOOL_MASK) as step:
        masked = mask(text)
        step.what = mask_note(text, masked)
    if any(leak_counts(masked).values()):
        raise ChatError("mask")  # 가림이 못 지운 개인정보 — 기록하지 않고 모델도 부르지 않는다
    when = now or now_kst()
    now_utc = when.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    used = asked_today(session, viewer.user_id, now_utc)
    if used >= int(cfg.get("per_person_daily")):
        raise ChatError("person_cap")
    erp_on = graft_enabled("erp_read", user)
    erp = read_question_order(session, user, text, masked, trace) if erp_on else None  # 번호는 가리기 전 원문에서
    with trace.step(TOOL_SEARCH):
        vector = query_vector(session, masked, cfg=cfg, now=when)  # 의미 찾기(D114) — 가린 글만 · 꺼짐 · 실패면 None
    verified, retrieval, model = answer_masked(session, viewer, masked, cfg=cfg, now=when, client=client, vector=vector,
                                               erp=erp, trace=trace)
    row = log_question(session, asker_id=viewer.user_id, masked_question=masked, answer=verified.answer,
                       evidence=verified.evidence, unknown=verified.unknown, confidence=verified.certainty,
                       ask_team=verified.ask_team, layer=verified.layer, model=model, now_utc=now_utc)
    store_question_vector(session, row.id, masked, vector, now_utc)  # 근원 chatbot_question — 이미 만든 벡터(돈 0)
    if not verified.unknown:  # 쓰인 횟수(합 표)는 회사 지식 키만 — 주문 키는 쓰인 곳(brain_usage_events)에만
        count_reads(session, [k for k in verified.evidence if order_id_of(k) is None], READER_CHATBOT, now=now_utc)
    logger.info("[회사 지식 물어보기] question=%s unknown=%s why=%s evidence=%d candidates=%d", row.id,
                verified.unknown, verified.why, len(verified.evidence), len(retrieval.candidates))
    if erp_on:
        _erp_finish(session, row.id, verified, erp, trace, now_utc)
    view = _view(row.id, verified, retrieval, left=int(cfg.get("per_person_daily")) - used - 1,
                 cards=screen_viewer(user) is not None)
    if erp_on:  # 설계서 3.7 '답 값에 더하는 칸' — 꺼진 사람의 답 값은 지금 그대로
        view.update(kind=answer_kind(verified.evidence, verified.unknown),
                    erp=erp_view(erp, trace) if erp is not None else None)
    return view
