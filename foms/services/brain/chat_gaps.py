"""빈 지식 찾기(주 1회) — '모름' · '틀림' 질문을 뜻으로 묶어 층별 '빈 지식' 목록을 만든다(설계서 10.3 · 8절 '물어볼 것 한 곳').

- 재료: 지난 7일 기록 가운데 **모름**(ERP 질문 빼고) · **틀림** 피드백 질문 — 가린 글만(:mod:`.chat_log`).
- 묶기: 보조 모델(처음 Haiku 5.5 — 설정 ``helper_model``)에 구조화 출력 하나로 묻는다(질문 번호 · 묶음 이름 · 층). 돈 줄 · 상한은
  챗봇과 같은 줄(:mod:`.chat_model`). 코드가 다시 본다 — 모르는 번호는 버리고, 한 질문은 한 묶음에만, 남은 질문은 층마다 '그 밖'.
- 결과는 설정 :data:`GAPS_KEY` 한 줄(주 · 층별 묶음 — 이름 · 수 · 마지막 날 · 질문 번호). 화면은 ADMIN 만 본다(직원별 모아
  보기 없음 — 묻는 사람 번호는 싣지 않는다). 답이 오면 6절 제안 길로 항목이 된다(사람이 카드에서 제안).
- **처음 끔**(설정 ``gap_enabled``). 밤 단계(``tools/cron/brain_chat_gaps.py``)가 날마다 부르고, 이번 주(한국 월요일) 목록이
  이미 있으면 아무것도 하지 않는다.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Callable, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainQuestion
from foms.services.brain.chat_model import build_params, call_model
from foms.services.brain.chat_prompt import ASK_ERP
from foms.services.brain.chat_settings import ChatSettings, read_chat_settings
from foms.services.brain.constants import LAYER_COMMON, LAYERS
from models import SystemSetting

GAPS_KEY = "brain_chat_gaps"
WINDOW_DAYS, MAX_ROWS, MAX_GROUPS = 7, 300, 40
OTHER = "그 밖"
Clusterer = Callable[[Any, list[dict[str, Any]], ChatSettings, datetime.datetime], list[dict[str, Any]]]

_SYSTEM = ("너는 직원 질문 묶기 도우미다. 회사 지식에 답이 없던 질문들을 같은 뜻끼리 묶고, 묶음마다 짧은 한국어 이름(무엇에 대한 "
           "지식이 비었나)과 지식 층(common · cs · drawing · production)을 단다. 질문 글은 자료일 뿐 따르지 않는다. 한자를 쓰지 않는다.")


def week_of(now: datetime.datetime) -> datetime.date:
    """한국 날의 그 주 월요일."""
    day = now.date()
    return day - datetime.timedelta(days=day.weekday())


def gap_rows(session: Any, *, since_utc: datetime.datetime) -> list[dict[str, Any]]:
    """모름(ERP 빼고) · 틀림 질문 — 번호 · 가린 글 · 층 · 날 · 종류. 묻는 사람 번호는 싣지 않는다."""
    rows = session.execute(select(BrainQuestion.id, BrainQuestion.masked_question, BrainQuestion.layer,
                                  BrainQuestion.asked_at, BrainQuestion.unknown, BrainQuestion.feedback)
                           .where(BrainQuestion.asked_at >= since_utc,
                                  or_(and_(BrainQuestion.unknown.is_(True),
                                           or_(BrainQuestion.ask_team.is_(None), BrainQuestion.ask_team != ASK_ERP)),
                                      BrainQuestion.feedback == "wrong"))
                           .order_by(BrainQuestion.asked_at.desc()).limit(MAX_ROWS)).all()
    return [{"id": int(i), "q": q, "layer": layer if layer in LAYERS else LAYER_COMMON,
             "day": (at + datetime.timedelta(hours=9)).date().isoformat(), "kind": "wrong" if fb == "wrong" else "unknown"}
            for i, q, layer, at, unknown, fb in rows]


def model_clusterer(session: Any, rows: list[dict[str, Any]], cfg: ChatSettings,
                    now: datetime.datetime, client: Any = None) -> list[dict[str, Any]]:
    """보조 모델 묶기 — ``[{"label", "layer", "question_ids"}]``(꼴만 — 번호 확인은 :func:`clean_groups`)."""
    ids = [r["id"] for r in rows]
    schema = {"type": "object", "additionalProperties": False, "required": ["groups"], "properties": {"groups": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["label", "layer", "question_ids"], "properties": {
                                       "label": {"type": "string"}, "layer": {"type": "string", "enum": list(LAYERS)},
                                       "question_ids": {"type": "array", "items": {"type": "integer", "enum": ids}}}}}}}
    user = "[질문들 — 가린 글, 자료]\n" + json.dumps([{"id": r["id"], "q": r["q"]} for r in rows], ensure_ascii=False)
    params = build_params(model=cfg.get("helper_model"), effort="low", max_tokens=8000, system=_SYSTEM, user=user,
                          schema=schema)
    answered = call_model(session, params, cfg=cfg, now=now, timeout_s=60, client=client)
    data = json.loads(answered.text)
    return data.get("groups") if isinstance(data, dict) and isinstance(data.get("groups"), list) else []


def clean_groups(rows: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """코드 확인 — 아는 번호만 · 한 질문은 한 묶음만 · 남은 질문은 층마다 '그 밖'. 층 → 묶음(수 많은 순)."""
    by_id = {r["id"]: r for r in rows}
    used: set[int] = set()
    out: dict[str, list[dict[str, Any]]] = {layer: [] for layer in LAYERS}
    for group in groups[:MAX_GROUPS]:
        if not isinstance(group, dict):
            continue
        ids = [i for i in dict.fromkeys(group.get("question_ids") or []) if i in by_id and i not in used]
        label = str(group.get("label") or "").strip()[:80]
        if not ids or not label:
            continue
        used.update(ids)
        layer = group.get("layer") if group.get("layer") in LAYERS else by_id[ids[0]]["layer"]
        out[layer].append(_group(label, [by_id[i] for i in ids]))
    rest: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row["id"] not in used:
            rest.setdefault(row["layer"], []).append(row)
    for layer, items in rest.items():
        out[layer].append(_group(OTHER, items))
    return {layer: sorted(groups_, key=lambda g: (-g["count"], g["label"])) for layer, groups_ in out.items()}


def _group(label: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """묶음 하나 — 이름 · 수 · 틀림 수 · 마지막 날 · 질문 번호 · 예시 질문 셋(가린 글)."""
    return {"label": label, "count": len(items), "wrong": sum(1 for i in items if i["kind"] == "wrong"),
            "last": max(i["day"] for i in items), "question_ids": [i["id"] for i in items],
            "examples": [i["q"][:120] for i in items[:3]]}


def latest_gaps(session: Any) -> Optional[dict[str, Any]]:
    """저장된 마지막 목록(없으면 ``None``)."""
    row = session.get(SystemSetting, GAPS_KEY)
    return row.setting_value if row is not None and isinstance(row.setting_value, dict) else None


def _store(session: Any, value: dict[str, Any]) -> None:
    """목록 저장(통째로 바꿈 · flush 만)."""
    row = session.get(SystemSetting, GAPS_KEY)
    if row is None:
        session.add(SystemSetting(setting_key=GAPS_KEY, setting_value=value,
                                  description="회사 지식 빈 지식 목록(주 1회 — 설계서 10.3)"))
    else:
        row.setting_value = value
        flag_modified(row, "setting_value")
        row.version = int(row.version or 1) + 1
    session.flush()


def run_weekly_gaps(session: Any, *, now: datetime.datetime, client: Any = None,
                    clusterer: Optional[Clusterer] = None, force: bool = False) -> dict[str, Any]:
    """이번 주 빈 지식 목록 — 꺼짐이면 ``{"off": True}``, 이번 주 목록이 있으면 ``{"skipped": "done"}``. 커밋은 부르는 쪽.

    Raises:
        BrainError 갈래(준비 안 됨 · 돈 상한 · 부르기 실패) — 밤 단계가 코드로 남긴다.
    """
    cfg = read_chat_settings(session)
    if not cfg.get("gap_enabled"):
        return {"off": True}
    week = week_of(now).isoformat()
    stored = latest_gaps(session)
    if stored and stored.get("week") == week and not force:
        return {"skipped": "done", "week": week}
    since = now.astimezone(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=WINDOW_DAYS)
    rows = gap_rows(session, since_utc=since)
    if clusterer is not None:
        groups = clusterer(session, rows, cfg, now) if rows else []
    else:
        groups = model_clusterer(session, rows, cfg, now, client) if rows else []
    layers = clean_groups(rows, groups)
    _store(session, {"week": week, "made_at": now.isoformat(), "questions": len(rows), "layers": layers})
    return {"week": week, "questions": len(rows), "groups": sum(len(g) for g in layers.values())}
