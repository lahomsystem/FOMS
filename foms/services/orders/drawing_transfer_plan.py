"""도면 전달의 자리 계산 — 전달 API(``perform_drawing_transfer``)와 미리 보기(R1)가 같은 함수를 쓴다(순수 계산 · 쿼리 0).

설계서 2026-11-25 §2-3 · §3-4 · §3-5(생산 넘어간 주문의 도면 수정 D2). 지금 전달 규칙(방식 기본값 · 같은 시트 자리 교체 · 교체 대상 ·
한 장이면 교체 · 다른 시트면 더하기)은 ``erp_orders_drawing.perform_drawing_transfer`` 에서 **그대로 옮겨 왔다**(글 · 순서 같음).
더한 것은 둘뿐이다:

* **파일 도면 고르기**(사장님 답 Q14): 생산 · 시공 단계에서 직접 올린 파일(시트 신원 없음)은 파일마다 ``replace_of`` = 바꿀 도면 key
  또는 ``"NEW"`` 를 받는다. 고른 도면은 그 자리에서 바뀌고 ``"NEW"`` 는 끝에 더한다. 지금 규칙(방식 · 교체 대상)은 나머지 파일에만.
* **짝**(``pairs`` — 새 key → 옛 key): 같은 시트 자리 교체 · 고른 도면 · 교체 대상(차례대로) · 한 장 교체. '바뀐 도면' 번호
  (:func:`changed_numbers`)와 건드린 열쇠(:func:`touched_idents`)가 이것을 읽는다.
* **파일마다 고르는 전달**(고른 파일이 하나라도 있으면): 전달 모드의 '교체 대상'과 "한 장이면 교체"를 쓰지 않는다 — 자리는 고른
  도면 · 같은 시트 새 판 · 새 시트(끝에 더함)뿐이고, 보내는 창이 말하는 것도 '바뀐 도면' 계산 하나뿐이다(2026-11-25 D2 검토 C).
  두 파일이 같은 도면을 고르거나 이번 시트 새 판이 이미 바꾸는 도면을 고르면 400 ``PICK_TARGET``(검토 D).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from foms.services.orders.drawing_fix import fix_ident
from foms.services.orders.drawing_transfer import clean_sheet_id, replace_same_sheet_files, sends_only_other_sheets

#: 파일 도면을 새 도면으로 더할 때 ``replace_of`` 값(§3-5).
NEW_TARGET = "NEW"
MISSING_TARGET_MESSAGE = '일부 교체 대상 도면을 찾을 수 없습니다. 목록을 새로고침 후 다시 시도해주세요.'
PICK_ONE_MESSAGE = '수정본 재전송 시 교체할 도면 번호를 선택해주세요.'
NEED_FILE_MESSAGE = '수정본 재전송 시 도면 파일 업로드가 필요합니다.'
NO_FILE_MESSAGE = '전달할 도면이 없습니다. 도면 파일을 먼저 업로드해주세요.'
PICK_TARGET = "PICK_TARGET"
PICK_TARGET_MESSAGE = "바꿀 도면을 골라 주세요."


@dataclass
class FilePlan:
    """전달 한 번의 자리 계산 결과 — ``error`` 가 있으면 400 글(쓰기 없음)."""

    updated_files: list[dict[str, Any]]
    mode: str
    is_retransfer: bool
    other_sheet_only: bool
    replace_target_keys: list[str]
    replaced_numbers: list[int] = field(default_factory=list)
    sheet_replaced_numbers: list[int] = field(default_factory=list)
    pairs: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None   # 있으면 거절 code(``PICK_TARGET``) — 없으면 지금 글만(지금 규칙의 400)


def _key(entry: Any) -> str:
    return str((entry or {}).get("key") or "").strip() if isinstance(entry, dict) else ""


def is_manual_file(entry: Any) -> bool:
    """직접 올린 파일(시트 신원 없음)인지."""
    return isinstance(entry, dict) and not clean_sheet_id(entry.get("sheet_id"))


def _split(new_files: list[dict[str, Any]], picks: Optional[dict[str, str]]) -> tuple[list, list]:
    """``picks`` 가 있으면(생산 · 시공 단계) 직접 올린 파일을 떼어 낸다 — (지금 규칙으로 갈 파일, 고른 파일)."""
    if picks is None:
        return list(new_files), []
    return [f for f in new_files if not is_manual_file(f)], [f for f in new_files if is_manual_file(f)]


def _place_targets(plan: FilePlan, base: list, rest: list, target_keys: list[str]) -> None:
    """교체 대상으로 고른 자리에 나머지 파일을 넣는다(지금 규칙 그대로 — 첫 대상 자리에 모두, 짝은 차례대로)."""
    found = []
    for target_key in target_keys:
        for i, f in enumerate(base):
            if _key(f) == target_key:
                found.append((i, target_key))
                break
    if len(found) != len(target_keys):
        plan.error = MISSING_TARGET_MESSAGE
        return
    for (_i, old_key), nf in zip(sorted(found), rest):
        plan.pairs[_key(nf)] = old_key
    found.sort(key=lambda x: x[0], reverse=True)
    for idx, _target_key in found:
        plan.replaced_numbers.append(idx + 1)
        plan.updated_files.pop(idx)
    first_index = min(x[0] for x in found)
    for offset, nf in enumerate(rest):
        plan.updated_files.insert(first_index + offset, nf)


def _place_rest(plan: FilePlan, base: list, rest: list, *, pick_mode: bool) -> None:
    """같은 시트 자리 교체 뒤 남은 파일 — 지금 규칙(교체 대상 · 한 장이면 교체 · 더하기). 파일마다 고르는 전달이면 더하기만."""
    base_keys = {_key(f) for f in base}
    target_keys = [k for k in plan.replace_target_keys if k in base_keys or not plan.sheet_replaced_numbers]
    plan.updated_files = list(base)
    if not rest:
        return
    if pick_mode:
        plan.updated_files = list(base) + list(rest)
    elif target_keys:
        _place_targets(plan, base, rest, target_keys)
    elif plan.is_retransfer and not plan.sheet_replaced_numbers and not plan.other_sheet_only:
        if len(base) > 1:
            plan.error = PICK_ONE_MESSAGE
            return
        for old, nf in zip(base, rest):
            plan.pairs[_key(nf)] = _key(old)
        plan.updated_files = list(rest)
    else:
        plan.updated_files = list(base) + list(rest)


def _pick_refused(plan: FilePlan) -> None:
    plan.error, plan.error_code = PICK_TARGET_MESSAGE, PICK_TARGET


def _apply_picks(plan: FilePlan, picked: list[dict[str, Any]], picks: dict[str, str], old_keys: list[str]) -> None:
    """고른 파일 — 고른 도면 자리에서 바꾸고 '새 도면'은 끝에 더한다(전체 교체면 자리는 그대로 두고 짝만).

    한 도면은 한 번만 바뀐다: 두 파일이 같은 도면을 고르거나, 이번 시트 새 판이 이미 바꾼(짝지은) 도면 · 빠지는 도면을 고르면
    400 ``PICK_TARGET``(화면은 그 도면 단추를 끈다 — 검토 D).
    """
    targets = [picks.get(_key(nf)) for nf in picked if picks.get(_key(nf)) != NEW_TARGET]
    if len(set(targets)) != len(targets) or set(targets) & set(plan.pairs.values()):
        _pick_refused(plan)
        return
    if plan.mode == "REPLACE_ALL":
        for nf in picked:
            if picks.get(_key(nf)) in old_keys:
                plan.pairs[_key(nf)] = picks[_key(nf)]
        return
    added = []
    for nf in picked:
        target = picks.get(_key(nf))
        if target == NEW_TARGET:
            added.append(nf)
            continue
        index = next((i for i, f in enumerate(plan.updated_files) if _key(f) == target), None)
        if index is None:
            _pick_refused(plan)
            return
        plan.updated_files[index] = nf
        plan.pairs[_key(nf)] = target
        plan.replaced_numbers.append(old_keys.index(target) + 1)
    plan.updated_files += added


def plan_transfer_files(old_files: list, new_files: list, sd: Any, *, drawing_status: str, hotfix: bool, mode: str,
                        replace_target_keys: list[str], is_retransfer: bool,
                        picks: Optional[dict[str, str]] = None) -> FilePlan:
    """이번 전달의 새 도면 목록을 계산한다(지금 전달 규칙 그대로 + 파일 도면 고르기).

    Args:
        old_files: 지금 ``drawing_current_files``.
        new_files: 이번 파일(``materialize_transfer_attachments`` · ``order_by_wizard_sheets`` 를 거친 것).
        sd: 주문 ``structured_data``(마법사 시트 목록을 읽는다).
        drawing_status: 지금 도면 상태(``effective_drawing_status``).
        hotfix: 생산 · 시공 단계(바로 반영)인지.
        mode: 부른 쪽 방식(빈 글 · APPEND · REPLACE · REPLACE_ALL).
        replace_target_keys: 교체 대상으로 고른 옛 key(``replace_target_key`` 를 합친 것).
        is_retransfer: 부른 쪽이 수정본이라고 했는지.
        picks: 생산 · 시공 단계의 파일 도면 고르기(새 key → 옛 key 또는 :data:`NEW_TARGET`, 검사를 마친 것). None 이면 지금 규칙만.

    Returns:
        :class:`FilePlan`. ``error`` 가 있으면 부른 쪽이 400 으로 답한다.
    """
    mode = (mode or "").upper()
    # 영업 수령 확정 전(TRANSFERRED)에 방식 없이 다시 보내면 전체 교체(2026-09-30 주문 5331 — APPEND 로 회차가 쌓였다).
    if not mode and not replace_target_keys and not is_retransfer and drawing_status == "TRANSFERRED":
        mode = "REPLACE_ALL"
    is_retransfer = is_retransfer or drawing_status == "RETURNED"
    rest_new, picked = _split(new_files, picks)
    pick_mode = bool(picked)   # 파일마다 고르는 전달 — 교체 대상 · "한 장이면 교체"를 쓰지 않는다(검토 C)
    targets = [] if pick_mode else list(replace_target_keys)
    # 바로 반영인데 방식이 없고 확정 도면이 한 장뿐이면 그 장을 바꾼다(주문 5690) — 단 이번 파일이 모두 다른 마법사 시트로
    # 증명되면 더한다(2026-11-20 M19). 생산 · 시공 단계는 직접 올린 파일이 고른 도면으로 신원이 정해지므로 시트 파일만 본다.
    other = bool(hotfix and mode in ("", "APPEND") and not targets
                 and sends_only_other_sheets(old_files, rest_new if picks is not None else new_files, sd))
    if hotfix and not mode and not targets and not is_retransfer and len(old_files) == 1 and not other and not pick_mode:
        is_retransfer = True
    plan = FilePlan(list(old_files), mode, is_retransfer, other, targets)
    if is_retransfer and not new_files:
        plan.error = NEED_FILE_MESSAGE
    elif not new_files and not old_files:   # 결과 0장 전달 막기(2026-09-08 운영 24건 — 대시보드 길은 빈 files 를 보낸다)
        plan.error = NO_FILE_MESSAGE
    if plan.error or not new_files:
        return plan
    old_keys = [_key(f) for f in old_files]
    if mode == "REPLACE_ALL":
        plan.replaced_numbers = list(range(1, len(old_files) + 1))
        plan.updated_files = list(new_files)
        _pair_same_sheets(plan, old_files, new_files)
    else:
        # 같은 시트 옛 판은 상태 · 방식과 상관없이 그 자리에서 바꾼다(2026-10-04 주문 5407). 남은 파일만 지금 규칙으로.
        base, rest, plan.sheet_replaced_numbers = replace_same_sheet_files(old_files, rest_new, sd)
        plan.replaced_numbers.extend(plan.sheet_replaced_numbers)
        _pair_same_sheets(plan, old_files, rest_new)
        _place_rest(plan, base, rest, pick_mode=pick_mode)
    if picked and not plan.error:
        _apply_picks(plan, picked, picks or {}, old_keys)
    plan.replaced_numbers = sorted(set(plan.replaced_numbers))
    return plan


def _pair_same_sheets(plan: FilePlan, old_files: list, new_files: list) -> None:
    """같은 시트 신원의 옛 판 → 새 판 짝(옛 판이 여럿이면 첫 판)."""
    old_by_sheet: dict[str, str] = {}
    for f in old_files:
        sid = clean_sheet_id((f or {}).get("sheet_id")) if isinstance(f, dict) else ""
        if sid:
            old_by_sheet.setdefault(sid, _key(f))
    for nf in new_files:
        sid = clean_sheet_id((nf or {}).get("sheet_id"))
        if sid and sid in old_by_sheet:
            plan.pairs[_key(nf)] = old_by_sheet[sid]


def changed_numbers(old_files: list, updated_files: list, pairs: dict[str, str]) -> dict[str, list[int]]:
    """바뀐 도면 번호(§3-4 ``changed``) — ``replaced`` = 새 판이 들어온 옛 도면(**옛 번호**), ``added`` = 짝 없는 새 도면(새 번호),
    ``removed`` = 새 목록에 없고 대신 들어온 판도 없는 옛 도면(**옛 번호**).

    고침 · 빠짐은 보내기 전 모두가 아는 번호(경고 글 · 공장 화면과 같은 번호)라 "도면 2 (고침) · 도면 2 (빠짐)" 처럼 겹치지 않는다
    (2026-11-25 D2 검토 E). 보내는 창 줄 · 공장 '바뀐 것' · 알림 글 · 이력 ``changed`` 가 모두 이 값 하나를 쓴다.
    """
    old_no: dict[str, int] = {}
    for no, entry in enumerate(old_files, 1):
        old_no.setdefault(_key(entry), no)
    succeeded = set(pairs.values())
    replaced, added = [], []
    for no, entry in enumerate(updated_files, 1):
        key = _key(entry)
        if key in old_no:
            continue
        prev = pairs.get(key)
        if prev in old_no:
            replaced.append(old_no[prev])
        else:
            added.append(no)
    new_keys = {_key(f) for f in updated_files}
    removed = [no for key, no in old_no.items() if key not in new_keys and key not in succeeded]
    return {"replaced": sorted(set(replaced)), "added": added, "removed": sorted(removed)}


def changed_old_entries(old_files: list, updated_files: list) -> list[tuple[int, dict[str, Any]]]:
    """이번에 바뀌거나 빠지는 옛 도면 ``(옛 번호, 항목)`` — 작업이 닿았는지 볼 대상(§2-3)."""
    new_keys = {_key(f) for f in updated_files}
    return [(no, f) for no, f in enumerate(old_files, 1) if isinstance(f, dict) and _key(f) not in new_keys]


def touched_idents(old_files: list, updated_files: list) -> set[str]:
    """이번 전달이 건드린 열쇠(§3-4) — 바뀌거나 빠진 옛 도면 · 새로 들어온 판의 열쇠(같은 시트 새 판은 옛 판과 같은 열쇠)."""
    old_keys = {_key(f) for f in old_files}
    out = {fix_ident(f) for _no, f in changed_old_entries(old_files, updated_files)}
    out |= {fix_ident(f) for f in updated_files if _key(f) not in old_keys}
    return {ident for ident in out if ident}


def changed_words(changed: Optional[dict[str, list[int]]]) -> str:
    """공장 '바뀐 것' · 알림 글(§10) — "도면 2 바뀜 · 도면 6 새로 추가 · 도면 4 빠짐"(없으면 빈 글)."""
    changed = changed or {}
    parts = []
    for name, tail in (("replaced", "바뀜"), ("added", "새로 추가"), ("removed", "빠짐")):
        numbers = [n for n in changed.get(name) or [] if isinstance(n, int)]
        if numbers:
            parts.append(f"도면 {' · '.join(str(n) for n in numbers)} {tail}")
    return " · ".join(parts)


def changed_detail(changed: Optional[dict[str, list[int]]], note: str) -> str:
    """'바뀐 것' 자세한 글 — "도면 2 바뀜 · 메모: 상판 깊이 600 → 580"(번호가 없으면 "메모: …", 메모도 없으면 빈 글)."""
    words = changed_words(changed)
    memo = f"메모: {note.strip()}" if isinstance(note, str) and note.strip() else ""
    return " · ".join(x for x in (words, memo) if x)


def changed_line(changed: Optional[dict[str, list[int]]]) -> str:
    """보내는 창 글(§10) — "바뀐 도면: 도면 2 (고침) · 도면 6 (새 도면) · 도면 4 (빠짐)"(없으면 빈 글)."""
    changed = changed or {}
    parts = [f"도면 {n} ({word})" for name, word in (("replaced", "고침"), ("added", "새 도면"), ("removed", "빠짐"))
             for n in changed.get(name) or []]
    return f"바뀐 도면: {' · '.join(parts)}" if parts else ""


__all__ = [
    "FilePlan", "NEW_TARGET", "PICK_TARGET", "PICK_TARGET_MESSAGE", "changed_detail", "changed_line", "changed_numbers", "changed_old_entries", "changed_words",
    "is_manual_file", "plan_transfer_files", "touched_idents",
]
