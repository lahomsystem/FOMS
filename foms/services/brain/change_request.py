"""문장으로 고치기 — 묶음 일 한 곳(설계서 2026-11-18-brain-sentence-change 2절 흐름 · 11절 약속 · D246 ~ D249).

순서(바꾸지 않는다):

1. **누가** — :func:`can_use`(스위치 · 관리자 또는 층 승인자). 아니면 ``forbidden``(404).
2. **가림** — 물어보기와 같은 가림(:func:`foms.services.cs_agent.masking.mask` →
   :func:`~foms.services.cs_agent.masking.require_masked`).
   새면 묶음 줄도 AI 도 없이 ``mask``(400). **원문은 저장하지 않는다** — 이 뒤로는 가린 글만(묶음 · AI · 로그).
3. **묶음 줄 만들기**(:func:`open_request`) — 상태 ``analyzing`` · 넣은 사람 · 고칠 수 있는 층 · 가린 문장. 감사 한 줄.
4. **분석 돌리기**(:func:`analyze`) — 재료 모으기 · AI 한 번(:mod:`.change_request_model` — 따로 돈 줄 · 하루 상한) · 답 읽기 ·
   줄마다 검사(:mod:`.change_request_check`) → ``ready``(되물음만 있으면 ``asked``) · 실패면 ``failed`` + ``error_code``.
   AI 답이 틀 밖이면 반영 0 · ``failed``. 지금은 요청 안에서 바로 돈다 — 줄 일(WORKER)로 옮길 때는 4 만 옮기면 된다.
5. **되물음 답**(:func:`answer`) — 가린 답을 묶음에 더하고(감사 한 줄) 같은 묶음을 다시 분석.
6. **이대로 고치기 · 되돌리기**는 :mod:`.change_request_apply`(:func:`apply` · :func:`revert`), **버리기**(:func:`discard`).

커밋: :func:`start` · :func:`answer` 는 AI 를 부르기 전 묶음 줄을 커밋한다(돈 예약 · 바로잡기가 세션을 커밋한다). 나머지는
부르는 쪽(API)이 커밋한다. 시각: :func:`start` · :func:`answer` · :func:`analyze` 의 ``now`` 는 한국 시각(돈 줄 날 — 물어보기와 같다),
:func:`discard` · :func:`apply` · :func:`revert` 의 ``now`` 는 UTC naive(반영 동작과 같다).
"""

from __future__ import annotations

import datetime
import logging
import time
from decimal import Decimal
from typing import Any, Optional

from foms.persistence.brain.models import BrainChangeRequest
from foms.services.brain.change_request_apply import apply, revert
from foms.services.brain.change_request_check import check_bundle
from foms.services.brain.change_request_model import (
    ChangeOutputError, build, call, daily_cap, gather, read_bundle,
)
from foms.services.brain.change_request_store import (
    ANALYZING, ASKED, DISCARDED, FAILED, READY, ChangeRequestError, audit, can_use, layer_scope_of, list_page, load,
    require_user, save_bundle, scope_tuple, view_of,
)
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.embeddings import query_vector
from foms.services.brain.proposals import known_text
from foms.services.cs_agent.brain_spend import BrainNotReady, BrainUnavailable, SpendCapReached
from foms.services.cs_agent.masking import MaskLeak, mask, require_masked
from foms.services.datetime_kst import now_kst, now_utc_naive

__all__ = ["ChangeRequestError", "analyze", "answer", "apply", "can_use", "discard", "list_page", "open_request",
           "revert", "start", "view"]

logger = logging.getLogger(__name__)

#: 넣는 글 상한(원문 글자) · 가린 문장 칸 상한 · 되물음 답 수.
MAX_TEXT, MAX_MASKED, MAX_ANSWERS = 800, 1000, 3


def _utc(now: Optional[datetime.datetime]) -> tuple[datetime.datetime, datetime.datetime]:
    """(한국 시각, UTC naive) — 돈 줄은 한국 날, 표 칸은 UTC naive."""
    when = now or now_kst()
    return when, when.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _masked(text: Any) -> str:
    """넣은 글 → 가린 글(꼴 · 가림 검사). 원문은 여기서 버린다."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ChangeRequestError("shape")
    masked = mask(text.strip())
    try:
        require_masked(masked)
    except MaskLeak:
        raise ChangeRequestError("mask") from None  # 가림이 못 지운 개인정보 — 묶음 줄 · AI 모두 없음
    if len(masked) > MAX_MASKED:
        raise ChangeRequestError("shape")
    return masked


def _ready_cfg(session: Any) -> Any:
    """물어보기 설정 — 문장으로 고치기 하루 상한이 비었으면 ``off``(묶음 줄을 만들지 않는다)."""
    cfg = read_chat_settings(session)
    if daily_cap(cfg) is None:
        raise ChangeRequestError("off")
    return cfg


def open_request(session: Any, user: Any, text: Any, *, now: Optional[datetime.datetime] = None) -> BrainChangeRequest:
    """묶음 줄 만들기(``analyzing``) — 누가 · 가림 · 상한 확인 뒤. flush 만(커밋은 부르는 쪽)."""
    viewer = require_user(user)
    masked = _masked(text)
    _ready_cfg(session)
    _when, now_utc = _utc(now)
    row = BrainChangeRequest(created_by=viewer.user_id, layer_scope=layer_scope_of(viewer), masked_text=masked,
                             bundle={"answers": []}, status=ANALYZING, created_at=now_utc)
    session.add(row)
    session.flush()
    audit(session, viewer.user_id, row, "START", {"chars": len(masked), "scope": row.layer_scope}, now_utc)
    session.flush()
    return row


def _search_text(row: BrainChangeRequest) -> str:
    """재료 찾기 글 — 가린 문장 + 가린 답(500자 — 찾기 상한)."""
    answers = [a.get("answer", "") for a in (row.bundle or {}).get("answers") or []]
    return " ".join([row.masked_text, *answers])[:500]


def _fail(row: BrainChangeRequest, code: str, bundle: dict[str, Any]) -> None:
    """분석 실패 — 줄 없이 ``failed`` + 코드(반영 0)."""
    row.status, row.error_code = FAILED, code[:48]
    save_bundle(row, {**bundle, "lines": [], "also_look": [], "needs_code": [], "questions": []})


def analyze(session: Any, row: BrainChangeRequest, user: Any, *, client: Any = None,
            now: Optional[datetime.datetime] = None) -> BrainChangeRequest:
    """분석 돌리기 — 재료 → AI 한 번 → 답 읽기 → 줄마다 검사 → ``ready`` · ``asked`` · ``failed``. 세션을 몇 번 커밋한다."""
    viewer = require_user(user)
    when, now_utc = _utc(now)
    today = when.date()
    started = time.monotonic()
    cfg = _ready_cfg(session)
    base = {"answers": list((row.bundle or {}).get("answers") or [])}
    search = _search_text(row)
    vector = query_vector(session, search, cfg=cfg, now=when)  # 의미 찾기(D114) — 가린 글만 · 꺼짐 · 실패면 None
    material = gather(session, viewer, search, today=today, vector=vector)
    params = build(cfg, masked=row.masked_text, answers=base["answers"], material=material, today=today)
    request_id = row.id
    cost, model = Decimal(0), None
    try:
        answered = call(session, params, cfg=cfg, now=when, client=client)
        cost, model = answered.cost, answered.model
        bundle = read_bundle(answered.text)
    except SpendCapReached:
        code = "money_cap"
    except BrainNotReady as exc:
        code = f"not_ready:{exc.code}"
    except BrainUnavailable as exc:
        code = f"unavailable:{exc.code}"
    except ChangeOutputError:
        code = "bad_response"
    else:
        code = None
    row = session.get(BrainChangeRequest, request_id, populate_existing=True)
    row.cost_usd = Decimal(str(row.cost_usd or 0)) + cost
    if code is not None:
        _fail(row, code, base)
    else:
        checked = check_bundle(session, bundle, material, viewer=viewer, scope=scope_tuple(row), request_id=row.id,
                               known=known_text(session), now=now_utc, today=today)
        ready = any(line["state"] == "preview" for line in checked["lines"])
        row.status = ASKED if bundle["questions"] and not ready else READY
        row.error_code = None
        save_bundle(row, {**base, "summary": bundle["summary"], "lines": checked["lines"],
                          "also_look": checked["also_look"], "needs_code": bundle["needs_code"],
                          "questions": bundle["questions"], "model": model, "raw": bundle})
    row.latency_ms = int(row.latency_ms or 0) + int((time.monotonic() - started) * 1000)
    session.flush()
    logger.info("[문장으로 고치기] request=%s status=%s code=%s lines=%d", row.id, row.status, row.error_code,
                len((row.bundle or {}).get("lines") or []))
    return row


def start(session: Any, user: Any, text: Any, *, client: Any = None,
          now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """분석 시작 — 묶음 줄 만들기(커밋) → 분석 돌리기 → 묶음 화면 값. 커밋은 부르는 쪽(분석 결과)."""
    row = open_request(session, user, text, now=now)
    session.commit()
    row = analyze(session, row, user, client=client, now=now)
    return view_of(row, require_user(user))


def answer(session: Any, user: Any, request_id: Any, text: Any, *, client: Any = None,
           now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """되물음에 답 — 가린 답을 더하고 같은 묶음을 다시 분석(넣은 사람만 · 미리 보기 · 되물음 상태 · 물음이 있을 때)."""
    viewer = require_user(user)
    row = load(session, viewer, request_id, lock=True, owner_only=True)
    bundle = row.bundle or {}
    answers = list(bundle.get("answers") or [])
    if row.status not in (READY, ASKED) or not bundle.get("questions") or len(answers) >= MAX_ANSWERS:
        raise ChangeRequestError("state")
    masked = _masked(text)
    _ready_cfg(session)
    answers.append({"question": " / ".join(bundle["questions"])[:500], "answer": masked})
    row.status = ANALYZING
    save_bundle(row, {**bundle, "answers": answers})
    _when, now_utc = _utc(now)
    audit(session, viewer.user_id, row, "ANSWER", {"answers": len(answers), "chars": len(masked)}, now_utc)
    session.commit()
    row = analyze(session, row, user, client=client, now=now)
    return view_of(row, viewer)


def discard(session: Any, user: Any, request_id: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """버리기 — 넣은 사람만 · 반영 전(미리 보기 · 되물음 · 분석 못 함)만. 제안 줄은 만든 적이 없다. 커밋은 부르는 쪽.

    ``now`` 는 UTC naive(이대로 고치기 · 되돌리기와 같다 — 시작 · 되물음 답의 ``now`` 는 돈 줄 날을 정하는 한국 시각)."""
    viewer = require_user(user)
    row = load(session, viewer, request_id, lock=True, owner_only=True)
    if row.status not in (READY, ASKED, FAILED):
        raise ChangeRequestError("state")
    now_utc = now or now_utc_naive()
    row.status, row.decided_at = DISCARDED, now_utc
    audit(session, viewer.user_id, row, "DISCARD", {"lines": len((row.bundle or {}).get("lines") or [])}, now_utc)
    session.flush()
    return view_of(row, viewer)


def view(session: Any, user: Any, request_id: Any) -> dict[str, Any]:
    """묶음 화면 값(넣은 사람 · 관리자만 — 그 밖 ``forbidden``)."""
    viewer = require_user(user)
    return view_of(load(session, viewer, request_id), viewer)
