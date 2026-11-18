"""문장으로 고치기 — 누가 쓰나 · 묶음 줄 읽기 · 감사 줄 · 묶음 화면 값 · 목록(설계서 2026-11-18 4절 · 11절 · D247).

- **누가 쓰나**(:func:`can_use`): 접목판 스위치 ``brain_change_request``(``brain_ui`` 가 켜져 있어야 — :mod:`foms.services.graft_flags`)가
  켜진 사람 가운데 회사 지식 화면을 여는 사람(:func:`.access.screen_viewer`) — 관리자 또는 층 승인자(:func:`.access.approver_layers`
  가 층을 하나 이상 주는 팀장). 그 밖은 없는 것과 같은 404.
- **묶음을 보는 사람**: 넣은 사람 · 관리자. 이대로 고치기 · 되물음 답 · 버리기는 넣은 사람만, 되돌리기는 넣은 사람 · 관리자.
  볼 수 없는 묶음은 없는 묶음과 같은 답(:class:`ChangeRequestError` ``forbidden``).
- 감사 줄(``SecurityLog``)은 번호 · 수 · 코드만 싣는다(글 없음 — 이웃 :func:`.decide.record_proposal` 버릇).
- **멈춘 분석 치우기**(:func:`close_stuck`): 분석을 시작한 지 :data:`STUCK_AFTER` 가 지나도 ``analyzing`` 인 묶음은
  :func:`view` · :func:`list_page` 가 읽을 때 ``failed``(``error_code`` ``stuck``)로 닫는다(분석 시작 시각은 묶음 ``analyzing_at``).
- 화면 값(:func:`view_of`)은 11절 약속 꼴 — 줄(``kind`` · ``label`` · ``before`` · ``after`` · ``why`` · ``check`` · ``state`` ·
  ``caution``) · 못 고친 것 · 코드가 필요한 것 · 같이 볼 것 · 물음 · 할 수 있는 일(``can_apply`` · ``can_revert``).
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChangeRequest
from foms.services.brain.access import approver_layers, screen_viewer
from foms.services.brain.change_request_check import (
    KIND_SETTING, STATE_APPLIED, STATE_BLOCKED, STATE_FAILED, STATE_PENDING, STATE_PREVIEW, STATE_REVERT_BLOCKED,
    STATE_REVERTED,
)
from foms.services.brain.display import LAYER_LABELS
from foms.services.brain.scope import Viewer
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import enabled as graft_enabled
from models import SecurityLog

FLAG = "brain_change_request"
SCOPE_EVERY = "all"
ANALYZING, READY, ASKED, APPLIED, PARTIAL = "analyzing", "ready", "asked", "applied", "partial"
REVERTED, DISCARDED, FAILED = "reverted", "discarded", "failed"
STATUS_LABELS: dict[str, str] = {
    ANALYZING: "분석 중", READY: "미리 보기", ASKED: "되물음", APPLIED: "반영됨", PARTIAL: "일부 반영",
    REVERTED: "되돌림", DISCARDED: "버림", FAILED: "분석 못 함",
}
KIND_LABELS: dict[str, str] = {"update": "고침", "create": "새로 만듦", "retire": "은퇴", "link_add": "연결 더하기",
                               "link_remove": "연결 빼기", "setting": "AI 직원 설정"}
STATE_LABELS: dict[str, str] = {
    STATE_PREVIEW: "고칠 것", STATE_BLOCKED: "못 고침", "skipped": "뺌", STATE_APPLIED: "고침", STATE_PENDING: "승인 대기",
    STATE_FAILED: "실패", STATE_REVERTED: "되돌림", STATE_REVERT_BLOCKED: "되돌리지 못함", "withdrawn": "거둠",
    "rejected": "거절됨",
}
#: 실패 코드 머리 → 화면 말(분석 실패 — 묶음 ``error_code``).
ERROR_TEXTS: dict[str, str] = {
    "money_cap": "오늘 문장으로 고치기 돈 상한에 닿았어요 — 내일 다시 넣어 주세요.",
    "not_ready": "분석 준비가 안 됐어요(돈 상한 · 열쇠 설정) — 관리자에게 알려 주세요.",
    "unavailable": "지금 분석 답을 받지 못했어요 — 잠시 뒤 다시 넣어 주세요.",
    "bad_response": "AI 답이 정한 꼴이 아니라서 아무것도 고치지 않았어요 — 다시 넣어 주세요.",
    "stuck": "분석이 끝나지 않아 멈췄어요 — 다시 넣어 주세요.",
    "error": "분석 중 오류가 나서 멈췄어요 — 다시 넣어 주세요.",
    "off": "문장으로 고치기가 꺼져 있어요 — 관리자에게 알려 주세요.",
    "forbidden": "분석 중 쓸 수 있는 사람이 아니게 됐어요 — 관리자에게 알려 주세요.",
}
#: 분석 시작 시각 칸(묶음 JSON — 되물음 답으로 다시 분석할 때 새로 적는다).
ANALYZING_AT = "analyzing_at"
#: 이만큼 지나도 ``analyzing`` 이면 멈춘 것으로 닫는다.
STUCK_AFTER = datetime.timedelta(minutes=10)
PAGE_SIZE = 20
#: 오류 코드 → HTTP 상태(API 가 정한 말만 보낸다).
STATUS: dict[str, int] = {"forbidden": 404, "shape": 400, "mask": 400, "off": 503, "state": 409, "empty": 409}
NOT_DONE_STATES = frozenset({STATE_BLOCKED, STATE_FAILED, STATE_REVERT_BLOCKED})


class ChangeRequestError(RuntimeError):
    """묶음 일을 하지 못했다 — ``code``(:data:`STATUS`). 글(문장 · 답)은 싣지 않는다."""

    def __init__(self, code: str) -> None:
        """코드만."""
        super().__init__(code)
        self.code = code


def can_use(user: Any) -> Optional[Viewer]:
    """문장으로 고치기를 쓸 수 있으면 그 사람의 Viewer — 스위치 켬 · 관리자 또는 층 승인자. 아니면 ``None``."""
    if user is None or not graft_enabled(FLAG, user):
        return None
    viewer = screen_viewer(user)
    if viewer is None or not (viewer.is_admin or approver_layers(viewer)):
        return None
    return viewer


def require_user(user: Any) -> Viewer:
    """:func:`can_use` 이거나 ``forbidden``."""
    viewer = can_use(user)
    if viewer is None:
        raise ChangeRequestError("forbidden")
    return viewer


def layer_scope_of(viewer: Viewer) -> str:
    """넣은 사람이 고칠 수 있는 층(관리자 ``all``, 층 승인자는 그 층 — 팀 하나 = 층 하나)."""
    layers = approver_layers(viewer)
    return SCOPE_EVERY if layers is None else layers[0]


def scope_tuple(row: BrainChangeRequest) -> Optional[tuple[str, ...]]:
    """묶음 줄의 층 칸 → 검사용 층 묶음(``None`` = 모든 층)."""
    return None if row.layer_scope == SCOPE_EVERY else (row.layer_scope,)


def load(session: Any, viewer: Viewer, request_id: Any, *, lock: bool = False, owner_only: bool = False
         ) -> BrainChangeRequest:
    """묶음 줄 — 없음 · 볼 수 없음(넣은 사람 · 관리자 밖) · 넣은 사람만 하는 일인데 남은 모두 ``forbidden``(같은 404)."""
    try:
        number = int(request_id)
    except (TypeError, ValueError):
        raise ChangeRequestError("forbidden") from None
    row = session.get(BrainChangeRequest, number, with_for_update=lock, populate_existing=True)
    mine = row is not None and row.created_by == viewer.user_id
    if row is None or not (mine or (viewer.is_admin and not owner_only)):
        raise ChangeRequestError("forbidden")
    return row


def audit(session: Any, actor_id: int, row: BrainChangeRequest, verb: str, detail: dict[str, Any],
          now: datetime.datetime) -> None:
    """감사 한 줄 — 묶음 번호 · 수 · 코드만(글 없음)."""
    session.add(SecurityLog(user_id=actor_id, action=f"BRAIN_REQUEST_{verb}", target_type="brain_change_request",
                            target_id=row.id, timestamp=now,
                            message=f"BRAIN_REQUEST_{verb} request={row.id} "
                                    + " ".join(f"{k}={v}" for k, v in detail.items()),
                            detail={"request": row.id, **detail}))


def settings_of(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """묶음 ``settings[]`` — 설정 줄마다 갈래 · 칸 · 전 → 후 · 반영 · 되돌림(11절 '전 → 후 값과 반영 여부')."""
    return [{"no": line["no"], "area": line["plan"].get("area"), "name": line["key"],
             "before": (line.get("before") or {}).get("level"), "after": (line.get("after") or {}).get("level"),
             "applied": line["state"] in (STATE_APPLIED, STATE_REVERTED, STATE_REVERT_BLOCKED),
             "reverted": line["state"] == STATE_REVERTED} for line in lines if line["kind"] == KIND_SETTING]


def save_bundle(row: BrainChangeRequest, bundle: dict[str, Any]) -> None:
    """묶음 칸을 다시 넣는다(깊은 사본 → 설정 목록 맞춤 → 다시 넣기 → flag_modified)."""
    value = copy.deepcopy(bundle)
    value["settings"] = settings_of(value.get("lines", []))
    row.bundle = value
    flag_modified(row, "bundle")


def counts_of(lines: list[dict[str, Any]]) -> dict[str, int]:
    """줄 상태마다 수."""
    out = {"lines": len(lines)}
    for line in lines:
        out[line["state"]] = out.get(line["state"], 0) + 1
    return out


def _line_view(line: dict[str, Any]) -> dict[str, Any]:
    """화면 줄(안쪽 계획 칸은 싣지 않는다)."""
    return {"no": line["no"], "kind": line["kind"], "kind_label": KIND_LABELS.get(line["kind"], line["kind"]),
            "key": line["key"], "label": line["label"], "layer": line["layer"],
            "layer_label": LAYER_LABELS.get(line["layer"] or "", ""), "before": line["before"], "after": line["after"],
            "fields": line["fields"], "why": line["why"], "check": line["check"], "state": line["state"],
            "state_label": STATE_LABELS.get(line["state"], line["state"]), "caution": bool(line["caution"]),
            "change_id": line.get("change_id")}


def _error_text(code: Optional[str]) -> Optional[str]:
    """실패 코드 → 화면 말(머리만 본다 — ``not_ready:no_api_key`` 는 ``not_ready``)."""
    return ERROR_TEXTS.get((code or "").split(":")[0]) if code else None


def view_of(row: BrainChangeRequest, viewer: Viewer) -> dict[str, Any]:
    """묶음 화면 값(11절) — 문장 · 상태 · 줄 · 못 고친 것 · 코드가 필요한 것 · 같이 볼 것 · 물음 · 할 수 있는 일."""
    bundle = row.bundle or {}
    lines = bundle.get("lines") or []
    mine = row.created_by == viewer.user_id
    counts = counts_of(lines)
    has_questions = bool(bundle.get("questions"))
    data = {
        "id": row.id, "text": row.masked_text, "status": row.status, "status_label": STATUS_LABELS.get(row.status, ""),
        "error_code": row.error_code, "error_text": _error_text(row.error_code), "summary": bundle.get("summary") or "",
        "layer_scope": row.layer_scope, "mine": mine,
        "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
        "decided_at": row.decided_at.isoformat(timespec="seconds") if row.decided_at else None,
        "lines": [_line_view(line) for line in lines],
        "not_done": [{"no": line["no"], "label": line["label"], "text": (line["check"] or {}).get("text")}
                     for line in lines if line["state"] in NOT_DONE_STATES],
        "needs_code": list(bundle.get("needs_code") or []), "also_look": list(bundle.get("also_look") or []),
        "questions": list(bundle.get("questions") or []), "answers": list(bundle.get("answers") or []),
        "settings": list(bundle.get("settings") or []), "counts": counts,
        "can_apply": mine and row.status == READY and counts.get(STATE_PREVIEW, 0) > 0,
        "can_answer": mine and row.status in (READY, ASKED) and has_questions,
        "can_discard": mine and row.status in (READY, ASKED, FAILED),
        "can_revert": (mine or viewer.is_admin) and row.status in (APPLIED, PARTIAL)
                      and (counts.get(STATE_APPLIED, 0) + counts.get(STATE_PENDING, 0)) > 0,
    }
    if viewer.is_admin:
        data["cost_usd"] = str(row.cost_usd) if row.cost_usd is not None else None
        data["latency_ms"] = row.latency_ms
    return data


def _since(row: BrainChangeRequest) -> Optional[datetime.datetime]:
    """분석 시작 시각(묶음 ``analyzing_at`` — 없거나 틀리면 만든 때)."""
    raw = (row.bundle or {}).get(ANALYZING_AT)
    try:
        return datetime.datetime.fromisoformat(raw) if isinstance(raw, str) else row.created_at
    except ValueError:
        return row.created_at


def close_stuck(session: Any, *, now: Optional[datetime.datetime] = None) -> int:
    """분석 시작 뒤 :data:`STUCK_AFTER` 가 지나도 ``analyzing`` 인 묶음을 ``failed``(``stuck``)로 닫는다. 닫은 수(flush 만)."""
    now = now or now_utc_naive()
    rows = session.execute(select(BrainChangeRequest).where(BrainChangeRequest.status == ANALYZING)
                           .with_for_update()).scalars().all()
    closed = 0
    for row in rows:
        since = _since(row)
        if since is not None and now - since > STUCK_AFTER:
            row.status, row.error_code = FAILED, "stuck"
            closed += 1
    if closed:
        session.flush()
    return closed


def view(session: Any, user: Any, request_id: Any, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """묶음 화면 값(넣은 사람 · 관리자만 — 그 밖 ``forbidden``). 멈춘 분석은 먼저 닫는다(커밋은 부르는 쪽)."""
    viewer = require_user(user)
    close_stuck(session, now=now)
    return view_of(load(session, viewer, request_id), viewer)


def list_page(session: Any, user: Any, page: Any = 1, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """목록(새 것부터) — 관리자는 모두, 그 밖은 내가 넣은 것만. ``{"items", "page", "pages", "total"}``. 멈춘 분석은 먼저 닫는다."""
    viewer = require_user(user)
    close_stuck(session, now=now)
    try:
        number = max(1, int(page or 1))
    except (TypeError, ValueError):
        number = 1
    where = [] if viewer.is_admin else [BrainChangeRequest.created_by == viewer.user_id]
    total = int(session.execute(select(func.count()).select_from(BrainChangeRequest).where(*where)).scalar_one())
    rows = session.execute(select(BrainChangeRequest).where(*where).order_by(BrainChangeRequest.id.desc())
                           .offset((number - 1) * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
    items = []
    for row in rows:
        lines = (row.bundle or {}).get("lines") or []
        counts = counts_of(lines)
        items.append({"id": row.id, "status": row.status, "status_label": STATUS_LABELS.get(row.status, ""),
                      "summary": (row.bundle or {}).get("summary") or "", "text": row.masked_text[:80],
                      "created_at": row.created_at.isoformat(timespec="seconds") if row.created_at else None,
                      "lines": counts["lines"], "applied": counts.get(STATE_APPLIED, 0),
                      "pending": counts.get(STATE_PENDING, 0), "mine": row.created_by == viewer.user_id})
    return {"items": items, "page": number, "pages": max(1, -(-total // PAGE_SIZE)), "total": total}
