"""챗봇 '틀림' 신고 — 근거 항목에 '엇갈림 후보'로 붙고, 서로 다른 사람 둘 이상이면 승인자에게 제안이 간다(설계서 10.3 · 3.1 규칙 4).

- :func:`add_reports` — 틀림 피드백 하나 → 그 답의 근거 항목마다 신고 한 줄(가린 고칠 말). 같은 질문 · 같은 항목은 한 줄.
- :func:`open_reports` — 항목마다 **지금 판에 대한** 신고(지금 판 기록 뒤에 온 것 · 거절된 신고 제안에 묶인 것은 뺌). 항목을 고치면
  (새 판) 앞 신고는 저절로 닫힌다.
- :func:`reported_keys` — 서로 다른 사람 둘 이상이 신고한 항목 = **'확인 필요'**(챗봇은 그 값을 답에 쓰지 않는다 — 3.1 규칙 4).
- :func:`build_conflict_proposal` — 이름 있는 에이전트 액션 ``report_conflict`` 의 몸(:func:`foms.services.brain.action_runner.perform_agent`
  가 부른다): 그 항목의 열린 신고에서 사람 · 고칠 말을 **다시 읽어** 엇갈림 항목 만들기 제안(에이전트 ``brain_chat`` — 근거 =
  ``person:<번호>`` 서로 다른 사람들, 관문 셋을 돈다)을 넣고 신고 줄에 제안 번호를 적는다. 정본은 바꾸지 않는다(승인자가 넣는다).
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Iterable, Optional

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange, BrainWrongReport
from foms.services.brain.constants import CHANGE_APPLIED, CHANGE_OPEN, CHANGE_REJECTED, OP_CREATE
from foms.services.brain.errors import BrainTargetError
from foms.services.brain.store import current_object

MIN_PEOPLE = 2
CHAT_AGENT = "brain_chat"
MAX_NOTE = 300


_MARKER = re.compile(r"\[[^\[\]\n]{1,100}\]")


def _plain(note: Optional[str]) -> str:
    """가린 고칠 말의 가림 표시(``[전화]`` · ``[링크:…]`` 같은 대괄호 말)를 '(가림)'으로 — 항목 글 관문(가림 표시 0)을 넘게."""
    return _MARKER.sub("(가림)", (note or "").strip())


def add_reports(session: Any, *, question_id: int, reporter_id: Optional[int], keys: Iterable[str], note: Optional[str],
                now: datetime.datetime) -> list[str]:
    """신고 줄을 넣는다(같은 질문 · 항목이 있으면 고칠 말만 바꾼다). 넣거나 바꾼 키."""
    out = []
    for key in dict.fromkeys(k for k in keys if isinstance(k, str) and k):
        row = session.execute(select(BrainWrongReport).where(BrainWrongReport.question_id == int(question_id),
                                                              BrainWrongReport.item_key == key)).scalar_one_or_none()
        if row is None:
            session.add(BrainWrongReport(item_key=key, question_id=int(question_id), reporter_id=reporter_id,
                                         note=(note or None), created_at=now))
        elif row.change_id is None:
            row.note = note or None
        out.append(key)
    session.flush()
    return out


def drop_reports(session: Any, *, question_id: int) -> int:
    """아직 올라가지 않은 그 질문의 신고를 지운다(피드백을 '틀림'에서 바꿨을 때). 지운 수."""
    rows = session.execute(select(BrainWrongReport).where(BrainWrongReport.question_id == int(question_id),
                                                          BrainWrongReport.change_id.is_(None))).scalars().all()
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def open_reports(session: Any, keys: Iterable[str]) -> dict[str, list[BrainWrongReport]]:
    """항목 → 지금 판에 대한 신고(지금 판 기록 뒤 · 거절된 신고 제안 빼고). 지금 판이 없는 키는 빈 목록."""
    wanted = sorted({k for k in keys if isinstance(k, str)})
    if not wanted:
        return {}
    rows = session.execute(select(BrainWrongReport, BrainChange.status)
                           .outerjoin(BrainChange, BrainChange.id == BrainWrongReport.change_id)
                           .where(BrainWrongReport.item_key.in_(wanted))
                           .order_by(BrainWrongReport.created_at, BrainWrongReport.id)).all()
    since = {key: getattr(current_object(session, key), "recorded_at", None) for key in {r.item_key for r, _s in rows}}
    out: dict[str, list[BrainWrongReport]] = {key: [] for key in wanted}
    for report, status in rows:
        start = since.get(report.item_key)
        if start is None or report.created_at < start or status == CHANGE_REJECTED:
            continue
        out[report.item_key].append(report)
    return out


def reported_keys(session: Any, keys: Iterable[str]) -> set[str]:
    """서로 다른 사람 둘 이상이 지금 판을 '틀림'으로 신고한 항목('확인 필요')."""
    return {key for key, rows in open_reports(session, keys).items()
            if len({r.reporter_id for r in rows if r.reporter_id is not None}) >= MIN_PEOPLE}


def raisable(session: Any, key: str) -> list[BrainWrongReport]:
    """올릴 신고 — 서로 다른 사람 둘 이상 · 그 신고로 이미 연(열림 · 넣음) 엇갈림 제안이 없음. 아니면 빈 목록."""
    rows = open_reports(session, [key]).get(key, [])
    if len({r.reporter_id for r in rows if r.reporter_id is not None}) < MIN_PEOPLE:
        return []
    raised = sorted({r.change_id for r in rows if r.change_id is not None})
    if raised and session.execute(select(BrainChange.id).where(
            BrainChange.id.in_(raised), BrainChange.status.in_((CHANGE_OPEN, CHANGE_APPLIED)))).first():
        return []
    return rows


def build_conflict_proposal(session: Any, *, key: str, proposer: Any, now: datetime.datetime,
                            propose_create: Any) -> BrainChange:
    """엇갈림 항목 만들기 제안 하나(관문은 :func:`propose_create` 가 돈다) · 신고 줄에 제안 번호를 적는다.

    Raises:
        BrainTargetError: 올릴 신고가 없음(사람 하나뿐 · 이미 열린 신고 제안 · 항목 없음).
    """
    target = current_object(session, key)
    rows = raisable(session, key) if target is not None else []
    if not rows:
        raise BrainTargetError("올릴 틀림 신고가 없다")
    people = sorted({int(r.reporter_id) for r in rows if r.reporter_id is not None})
    notes = list(dict.fromkeys(_plain(r.note)[:MAX_NOTE] for r in rows if (r.note or "").strip()))
    lines = ["챗봇 답의 근거로 쓰인 이 항목이 틀렸다는 신고가 서로 다른 직원 둘 이상에게서 왔어요."]
    lines += ["고칠 말:", *(f"- {n}" for n in notes)] if notes else ["고칠 말은 없어요."]
    first = rows[0].id
    values = {"name": f"틀림 신고 — {target.name}"[:200], "text": "\n".join(lines)[:2000], "status": "active",
              "visibility": target.visibility, "evidence_kind": "person", "evidence_ref": f"brain_questions:{first}",
              "payload": {"target": key, "target_version": target.version,
                          "questions": sorted({int(r.question_id) for r in rows})}}
    change = propose_create(session, key=f"conflict/chat-{first}", brand=target.brand, layer=target.layer,
                            item_type="conflict", values=values, proposer=proposer, now=now,
                            reason="챗봇 '틀림' 신고 — 서로 다른 사람 둘 이상(설계서 10.3)",
                            evidence=[f"person:{p}" for p in people], action="report_conflict")
    for row in rows:
        row.change_id = change.id
    session.flush()
    return change


def is_conflict_create(change: BrainChange) -> bool:
    """챗봇 신고로 만든 엇갈림 제안인가."""
    return change.op == OP_CREATE and change.item_type == "conflict" and change.action == "report_conflict"
