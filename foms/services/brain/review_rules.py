"""제안함 · 결정의 순수 규칙(DB 를 읽지 않는다) — 제안함 화면(:mod:`.inbox`)과 결정 동작(:mod:`.decide`)이 같은 판정을 쓴다.

- **등급 B 핵심 값**(7.5 '등급 B 는 핵심 값 하나를 직접 확인'): 바뀐 칸 가운데 :data:`.constants.KEY_FIELD_ORDER` 앞의 칸
  하나와 그 새 값 글(지우기는 지우는 항목의 이름). 화면은 그 글을 보이고, 결정 동작은 받은 글이 서버가 다시 만든 글과 같아야
  넣는다 — 화면이 낡은 값을 보고 누르지 않게.
- **휴대폰 결정**(사장님 D103 — 13절 14): '아직 맞음'과 **칸 하나 고침의 넣기**만. 나머지는 'PC 에서 볼게요'.
- **AI 제안 주 상한 · 저절로 닫힘**(D103 — 13절 13): 주는 한국 월요일 0시에 시작, 만든 뒤 :data:`AI_EXPIRE_DAYS` 일.
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Mapping, Optional

from foms.services.brain.constants import AI_EXPIRE_DAYS, KEY_FIELD_ORDER, OP_DELETE, OP_UPDATE
from foms.services.brain.schemas import PAYLOAD, payload_props
from foms.services.brain.store import kst_day

AGENT_PREFIX = "agent:"
_KST = datetime.timedelta(hours=9)


def is_agent(proposed_by: Optional[str]) -> bool:
    """에이전트(AI)가 만든 제안인가."""
    return bool(proposed_by) and str(proposed_by).startswith(AGENT_PREFIX)


def value_text(value: Any) -> str:
    """칸 값 → 견주기 · 보이기 글(없음은 빈 글, 목록은 ' · ', 객체는 키 정렬 JSON)."""
    if value is None:
        return ""
    if isinstance(value, list):
        return " · ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def key_field(op: str, fields: Optional[Mapping[str, Any]]) -> Optional[str]:
    """등급 B 확인 칸 — 바뀐 칸 가운데 정한 차례 앞의 것(지우기는 이름). 칸이 없으면 ``None``."""
    names = set(fields or {})
    if op == OP_DELETE:
        return "name" if "name" in names else next(iter(sorted(names)), None)
    return next((name for name in KEY_FIELD_ORDER if name in names), next(iter(sorted(names)), None))


def confirm_value(op: str, fields: Optional[Mapping[str, Any]],
                  item_type: Optional[str] = None) -> tuple[Optional[str], str]:
    """(확인 칸, 확인 글) — 지우기는 지우는 값(전), 그 밖은 새 값(후). 실음 칸이면 속성 틀의 바뀐 첫 칸
    (``payload.<칸>`` — 7.7 속성 틀)."""
    name = key_field(op, fields)
    if name is None:
        return None, ""
    entry = (fields or {}).get(name) or {}
    if name == "payload" and op != OP_DELETE and payload_props(item_type):
        before = entry.get("before") if isinstance(entry.get("before"), dict) else {}
        after = entry.get("after") if isinstance(entry.get("after"), dict) else {}
        for prop in payload_props(item_type):
            sub = prop.path[len(PAYLOAD):]
            if before.get(sub) != after.get(sub):
                return prop.path, value_text(after.get(sub))
    return name, value_text(entry.get("before") if op == OP_DELETE else entry.get("after"))


def phone_ok(op: str, fields: Optional[Mapping[str, Any]]) -> bool:
    """휴대폰에서 넣을 수 있나 — 칸 하나 고침만(D103)."""
    return op == OP_UPDATE and len(fields or {}) == 1


def week_start(now: datetime.datetime) -> datetime.datetime:
    """이번 주(한국 월요일 0시)의 UTC naive 시각."""
    day = kst_day(now)
    monday = day - datetime.timedelta(days=day.weekday())
    return datetime.datetime.combine(monday, datetime.time()) - _KST


def ai_cutoff(now: datetime.datetime) -> datetime.datetime:
    """이보다 앞에 만든 AI 제안은 기간이 끝났다(저절로 닫힘)."""
    return now - datetime.timedelta(days=AI_EXPIRE_DAYS)


def clamp_ms(value: Any) -> Optional[int]:
    """화면이 잰 결정 시간(밀리초) — 정수 0 ~ 하루만, 그 밖은 ``None``(측정 없음)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = int(value)
    return number if 0 <= number <= 86_400_000 else None
