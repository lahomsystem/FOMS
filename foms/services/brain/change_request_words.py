"""문장으로 고치기 — 화면 값의 사람 말(설계서 2026-11-18-brain-sentence-change 12절 '화면에 남은 흠').

사장님 · 팀장이 보는 글(줄 이름 · 같이 볼 것 · 못 고친 것 · 코드가 필요한 것 · 물음 · 줄 까닭 · 한 줄 요약)에 지식 주소
(``common/…``) · 코드 이름(``ops.assign_draftsman``) · 영어 상태 코드가 그대로 나오지 않게 한다. 주소는 화면 값의 다른 칸
(``key`` · ``after.to`` 등)에는 남는다.

- **없거나 볼 수 없는 지식**은 한 이름(:data:`UNKNOWN_LABEL`)이다 — 둘을 가르면 넣은 사람이 볼 수 없는 키가 있는지를 알게 된다
  (검사 :mod:`.change_request_check` 의 '있는지도 알리지 않는다' — 까닭 글 ``unknown_key`` 도 한 말이다).
- 바깥 자리 끝(``calc:`` · ``setting:`` · ``erp:stage/`` · 사본 자리)은 그 자리 이름(:func:`external_label` — ERP 단계는 단계 이름).
- AI 가 쓴 글 속 주소는 **이번 묶음의 재료 항목 이름**(+ 새 항목 ``new:<n>`` 은 그 이름, 설정 칸 이름은 그 이름표)으로 바꾼다
  (:func:`tidy`). 재료에 없는 주소는 그대로 둔다(짐작해 이름을 달지 않는다).
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional

from foms.services.brain.constants import EXT_ERP_STAGE, external_type
from foms.services.brain.display import LINK_DISPLAY, STATUS_LABELS, type_label
from foms.services.orders.erp_policy_constants import STAGE_LABELS

UNKNOWN_LABEL = "없거나 볼 수 없는 지식"
UNKNOWN_SETTING = "없는 설정 칸"
CS_SETTING = "상담 AI 관리 칸"
UNNAMED_NEW = "이름 없는 새 지식"
UNKNOWN_LINK = "모르는 연결"
#: 글 속 주소 꼴(키 꼴 :data:`.constants.KEY_RE` 와 같은 글자 — 앞뒤가 같은 글자가 아닌 곳에서만, 끝은 글자 · 숫자).
_TOKEN = re.compile(r"(?<![A-Za-z0-9_./:-])[a-z0-9][a-z0-9_.:/-]{0,118}[a-z0-9](?![A-Za-z0-9_/-])")
_ERP_STAGE = "erp:stage/"


def external_label(key: str) -> Optional[str]:
    """바깥 자리 키 → 화면 이름(바깥 자리가 아니면 ``None``)."""
    kind = external_type(key)
    if kind is None:
        return None
    if kind == EXT_ERP_STAGE:
        stage = STAGE_LABELS.get(key[len(_ERP_STAGE):].upper())
        return f"{type_label(kind)} · {stage}" if stage else type_label(kind)
    return type_label(kind)


def link_kind_label(kind: str) -> str:
    """연결 종류 → 화면 이름(모르는 종류는 :data:`UNKNOWN_LINK`)."""
    shown = LINK_DISPLAY.get(kind)
    return shown[0] if shown else UNKNOWN_LINK


def status_label(status: Any) -> Any:
    """항목 상태 값 → 화면 말(모르는 값은 그대로)."""
    return STATUS_LABELS.get(status, status) if isinstance(status, str) else status


def names_of(items: Mapping[str, Mapping[str, Any]], settings: Mapping[str, Mapping[str, Any]],
             creates: list[Mapping[str, Any]]) -> dict[str, str]:
    """주소 → 이름 — 재료 항목 · 설정 칸 · 같은 묶음의 새 항목(``new:<n>``, 이름이 있을 때만)."""
    out = {key: str(row.get("name") or "") for key, row in items.items() if row.get("name")}
    out.update({name: str(row.get("label") or "") for name, row in settings.items() if row.get("label")})
    for number, row in enumerate(creates, 1):
        name = ((row.get("values") or {}).get("name") or "").strip()
        if name:
            out[f"new:{number}"] = name
    return out


def tidy(text: Any, names: Mapping[str, str]) -> Any:
    """글 속 주소 · 코드 이름을 이름으로(아는 것만 — 재료에 없으면 그대로, 바깥 자리는 그 자리 이름). 글이 아니면 그대로."""
    if not isinstance(text, str) or not text:
        return text

    def swap(match: re.Match[str]) -> str:
        token = match.group(0)
        return names.get(token) or external_label(token) or token

    return _TOKEN.sub(swap, text)


def tidy_note(note: str, names: Mapping[str, str]) -> str:
    """'같이 볼 것' 한 줄(``키 — 까닭``) — 앞 키는 찾기에 쓰니 두고, 까닭만 다듬는다(가름표가 없으면 온 줄)."""
    head, sep, why = note.partition(" — ")
    return f"{head}{sep}{tidy(why, names)}" if sep else note


def tidy_bundle(bundle: Mapping[str, Any], names: Mapping[str, str]) -> dict[str, Any]:
    """AI 묶음의 사람 글(요약 · 줄 까닭 · 코드가 필요한 것 · 물음 · 같이 볼 것의 까닭)을 다듬은 사본(키 · 값 칸은 그대로)."""
    out = dict(bundle)
    out["summary"] = tidy(bundle.get("summary", ""), names)
    for name in ("updates", "creates", "retires", "links", "settings"):
        out[name] = [{**row, "why": tidy(row.get("why", ""), names)} for row in bundle.get(name) or []]
    for name in ("needs_code", "questions"):
        out[name] = [tidy(t, names) for t in bundle.get(name) or []]
    out["also_look"] = [tidy_note(t, names) for t in bundle.get("also_look") or []]
    return out
