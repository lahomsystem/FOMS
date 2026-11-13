"""주문 공정 칸(``structured_data.production.steps``) 정의와 칸 하나 바꾸기 — 한 곳 규칙.

지금 공정 API(``POST /api/orders/<id>/production/steps``)와 파트 카드 동기화(설계서 §15.5 — 표시 API ·
도면 쓰기 셋)가 **같은 함수**로 칸을 바꾼다(복사 금지). 모두 순수 계산이다 — DB · commit · 이벤트 없이 호출자가
deepcopy 한 ``structured_data`` dict 만 제자리에서 고친다(재대입 · ``flag_modified`` 는 호출자 몫).

칸 모양: ``{key, label, done, at, by_name}`` — ``at`` = 켠 때(UTC iso), ``by_name`` = 켠 사람 이름. 끄면 둘 다 None.
"""

from __future__ import annotations

from typing import Any, Optional

#: 생산 공정 기본 4단계(cut/edge/assemble/inspect). 최초 쓰기 때 서버가 만든다.
#: 도장(paint)은 우리 공장에 없어 2026-11-09 뺐다(사용자 결정 D15). 옛 주문의 저장 목록에 남은 paint 는
#: 읽을 때 :func:`normalize_production_steps` 가 걸러 낸다 — 저장 데이터·run 스냅샷은 손대지 않는다(감사 비교 보존).
PRODUCTION_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("cut", "재단"),
    ("edge", "엣지"),
    ("assemble", "조립"),
    ("inspect", "검수"),
)
PRODUCTION_STEP_KEYS = frozenset(k for k, _ in PRODUCTION_STEP_DEFS)
PRODUCTION_STEP_LABELS: dict[str, str] = dict(PRODUCTION_STEP_DEFS)


def _blank_step(key: str) -> dict[str, Any]:
    return {"key": key, "label": PRODUCTION_STEP_LABELS[key], "done": False, "at": None, "by_name": None}


def normalize_production_steps(raw: Any) -> list[dict[str, Any]]:
    """저장된 공정 목록 → 화면·API 가 보는 목록. 정의에 없는 key(옛 도장)는 빼고, 빠진 단계는 미완으로 채운다.

    저장 목록은 바꾸지 않는다(새 리스트). 정의 순서(재단·엣지·조립·검수)로 돌려준다.
    """
    by_key: dict[str, dict[str, Any]] = {}
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("key") in PRODUCTION_STEP_KEYS:
            by_key.setdefault(str(item["key"]), item)
    return [by_key.get(key) or _blank_step(key) for key, _ in PRODUCTION_STEP_DEFS]


def ensure_production_steps(sd: dict[str, Any]) -> list[dict[str, Any]]:
    """sd['production']['steps'] 를 보장한다(없으면 기본 4단계 미체크로 생성) 후 반환.

    :param sd: 수정 대상 structured_data (deepcopy 된 사본이어야 한다).
    :return: 공정 스텝 리스트(sd 내부 참조와 동일 객체).
    """
    production = sd.get("production")
    if not isinstance(production, dict):
        production = {}
        sd["production"] = production
    steps = production.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [_blank_step(key) for key, _ in PRODUCTION_STEP_DEFS]
        production["steps"] = steps
    return steps


def step_done_map(sd: Any) -> dict[str, bool]:
    """지금 공정 칸 켜짐 여부(정의 4칸, 저장 안 된 칸 = 꺼짐). sd 는 읽기만 한다."""
    production = sd.get("production") if isinstance(sd, dict) else None
    raw = production.get("steps") if isinstance(production, dict) else None
    return {str(s["key"]): bool(s.get("done")) for s in normalize_production_steps(raw)}


def set_production_step(sd: dict[str, Any], key: str, done: bool, *, by_name: Optional[str],
                        at_iso: str) -> list[dict[str, Any]]:
    """공정 칸 하나를 켜거나 끈다(제자리) — 지금 공정 API 와 파트 카드 동기화가 같이 쓴다.

    Args:
        sd: 수정 대상 structured_data(deepcopy 된 사본).
        key: 공정 key(:data:`PRODUCTION_STEP_KEYS` 안 — 호출자가 검증).
        done: 켬 여부.
        by_name: 켤 때 남길 이름(끌 때는 무시하고 None).
        at_iso: 켤 때 남길 때(UTC iso, 끌 때는 무시하고 None).

    Returns:
        공정 목록(sd 안 참조와 같은 객체).
    """
    steps = ensure_production_steps(sd)
    target = next((s for s in steps if isinstance(s, dict) and s.get("key") == key), None)
    if target is None:  # 옛 목록에 그 단계가 없으면 미완으로 더한다(정의에 있는 key 만 여기 온다)
        target = _blank_step(key)
        steps.append(target)
    target["done"] = bool(done)
    target["at"] = at_iso if done else None
    target["by_name"] = by_name if done else None
    return steps
