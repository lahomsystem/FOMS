"""생산 넘어간 주문의 도면 수정 — 도면 열쇠 · 막힘 판정(도면별) · 글 꼴(설계서 2026-11-25 §3-2 · §3-3 · §3-6 · §10). 순수 함수(쿼리 0).

자료는 주문 JSON 의 **서버 소유** 칸 ``structured_data.drawing_fix`` 하나다(안 ⓐ — 마이그레이션 없음, 칸이 없으면 "고치는 중 없음")::

    {"fixing": {"sheet:<시트 id>": {"no", "by_user_id", "by_name", "at"}, "file:<저장 key>": {...}},
     "requests": [{"id", "from": "factory", "targets": ["sheet:…"], "numbers", "note", "photos", "factory", "state": "open|done|rejected", …}],
     "log": [{"act", "idents", "numbers", "by_name", "at"}]}

* **열쇠**(:func:`fix_ident`) = ``sheet:<sheet_id>``(마법사 시트 — 판이 바뀌어도 같다) 또는 ``file:<저장 key>``(직접 올린 파일). 공장 꼴 패킹 줄
  열쇠(``packing_factory``)와 같은 꼴이다. 막힘 · 풀림 · 패킹을 보는 모든 자리가 이 함수 하나만 쓴다.
* **막힘**(:func:`blocked`) — 통째 = :func:`~foms.services.orders.confirm_drawing_gate.drawing_revision_in_progress`(TRANSFERRED · 대상을 못 고른
  RETURNED, 지금 그대로) · 도면별 = (대상을 고른 영업 요청의 ``target_idents``) ∪ ``fixing`` 열쇠 ∪ 열린 공장 요청 ``targets``. 도면별은 단계가
  생산 · 시공일 때만 본다(고객컨펌 단계 영업 요청은 지금처럼 통째 — §3-3 4).
* 쓰기(풀림 · 시작 · 취소 · 요청 · 반려)는 이 모듈에 없다 — D2 ~ D4 가 따로 이름을 붙여 더한다(§8-5). 폼 저장 · 초안 · 주문 만들기는 이 칸을 못
  바꾼다(``structured_form_projection.SERVER_LOCKED_KEYS`` · ``drawing_factory.strip_client_factory_state``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import (
    drawing_revision_in_progress,
    per_drawing_stage,
    revision_request_target_keys,
    targeted_revision_request,
)
from foms.services.orders.drawing_factory import DRAWING_FACTORY_KEY, DRAWING_FIX_KEY, current_factories, sheet_factory
from foms.services.orders.drawing_transfer import clean_sheet_id

SHEET_PREFIX = "sheet:"
FILE_PREFIX = "file:"
#: 도면별 막힘의 까닭(``Block.why`` 값) — 영업 요청 · 도면팀 [수정 시작] · 공장 요청.
WHY_SALES = "sales"
WHY_FIXING = "fixing"
WHY_FACTORY = "factory"
REQUEST_OPEN = "open"

#: 숫자를 읽을 때 끝소리에 받침이 있는 끝자리(일 · 삼 · 육 · 칠 · 팔 · 영 → 은, 이 · 사 · 오 · 구 → 는) — §2-3 조사.
_FINAL_DIGITS = frozenset("136780")


@dataclass(frozen=True)
class Block:
    """한 주문의 막힘 — ``whole`` = 주문 통째, ``idents`` = 도면별로 막힌 열쇠, ``why`` = 열쇠마다 까닭(:data:`WHY_SALES` …)."""

    whole: bool
    idents: frozenset[str] = frozenset()
    why: dict[str, tuple[str, ...]] = field(default_factory=dict, compare=False, hash=False)


# --------------------------------------------------------------------------- #
# 열쇠
# --------------------------------------------------------------------------- #
def fix_ident(entry: Any) -> str:
    """도면 항목(확정 도면 한 줄 · ``{sheet_id}`` · ``{key}``)의 열쇠 — ``sheet:<id>`` 우선, 없으면 ``file:<key>``, 둘 다 없으면 빈 글."""
    if not isinstance(entry, dict):
        return ""
    sid = clean_sheet_id(entry.get("sheet_id"))
    if sid:
        return f"{SHEET_PREFIX}{sid}"
    key = str(entry.get("key") or "").strip()
    return f"{FILE_PREFIX}{key}" if key else ""


def idents_for_keys(sd: Any, keys: Iterable[str]) -> list[str]:
    """지금 확정 도면 저장 key → 열쇠(``keys`` 순서, 지금 도면에 없는 key 는 버림) — 영업 요청 줄의 ``target_idents``."""
    by_key = {entry["key"]: fix_ident(entry) for entry in resolve_final_drawing_files(sd)}
    return list(dict.fromkeys(by_key[k] for k in keys if by_key.get(k)))


def _clean_idents(raw: Iterable[Any]) -> list[str]:
    return [x.strip() for x in raw if isinstance(x, str) and x.strip()]


def _fix_table(sd: Any) -> dict[str, Any]:
    raw = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    return raw if isinstance(raw, dict) else {}


# --------------------------------------------------------------------------- #
# 막힘
# --------------------------------------------------------------------------- #
def sales_request_idents(sd: Any) -> frozenset[str]:
    """대상을 고른 영업 요청(생산 · 시공 단계 RETURNED)이 막는 열쇠 — 새 줄은 ``target_idents``, 옛 줄은 ``target_drawing_keys`` 를 지금
    도면으로 푼다(§3-2). 통째 요청 · 요청 없음은 빈 것(통째는 :func:`blocked` 의 ``whole``)."""
    request = targeted_revision_request(sd)
    if request is None:
        return frozenset()
    stored = _clean_idents(request.get("target_idents") or []) if isinstance(request.get("target_idents"), list) else []
    return frozenset(stored or idents_for_keys(sd, revision_request_target_keys(request)))


def fixing_idents(sd: Any) -> frozenset[str]:
    """도면팀 [수정 시작] 열쇠(``drawing_fix.fixing``)."""
    fixing = _fix_table(sd).get("fixing")
    return frozenset(_clean_idents(fixing)) if isinstance(fixing, dict) else frozenset()


def open_request_idents(sd: Any) -> frozenset[str]:
    """열린 공장 요청의 대상 열쇠(사장님 답 "요청하면 바로 막기")."""
    requests = _fix_table(sd).get("requests")
    out: list[str] = []
    for request in requests if isinstance(requests, list) else []:
        if isinstance(request, dict) and request.get("state") == REQUEST_OPEN and isinstance(request.get("targets"), list):
            out += request_left(request)
    return frozenset(out)


def blocked(sd: Any) -> Block:
    """주문 하나의 막힘(§3-3) — 통째(지금 규칙) + 도면별(생산 · 시공 단계에서만: 영업 요청 대상 ∪ 고치는 중 ∪ 열린 공장 요청).

    Args:
        sd: 주문 ``structured_data``(읽기만).

    Returns:
        :class:`Block`. 생산 · 시공 단계가 아니면 ``idents`` 는 늘 비어 있다.
    """
    whole = drawing_revision_in_progress(sd)
    if not per_drawing_stage(sd):
        return Block(whole)
    why: dict[str, list[str]] = {}
    for reason, idents in ((WHY_SALES, sales_request_idents(sd)), (WHY_FIXING, fixing_idents(sd)),
                           (WHY_FACTORY, open_request_idents(sd))):
        for ident in sorted(idents):
            why.setdefault(ident, []).append(reason)
    return Block(whole, frozenset(why), {ident: tuple(reasons) for ident, reasons in why.items()})


def entry_blocked(block: Block, entry: Any) -> bool:
    """도면 한 장이 막혔는지 — 통째거나 그 장 열쇠가 도면별로 막힘."""
    return block.whole or (fix_ident(entry) in block.idents)


def drawing_blocked(sd: Any, entry: Any, *, block: Optional[Block] = None) -> bool:
    """도면 한 장이 막혔는지(:func:`blocked` 를 한 번 계산해 둔 값이 있으면 ``block`` 으로 넘긴다)."""
    return entry_blocked(block if block is not None else blocked(sd), entry)


def blocked_entries(sd: Any, *, block: Optional[Block] = None, factory: Optional[int] = None) -> list[dict[str, Any]]:
    """지금 확정 도면 중 막힌 장(통째면 모두) — ``[{no, key, ident, factory}]`` 도면 번호 순. ``factory`` 를 주면 그 공장 장만."""
    block = block if block is not None else blocked(sd)
    out = []
    for no, (entry, owner) in enumerate(current_factories(sd), 1):
        if (factory is None or owner == factory) and entry_blocked(block, entry):
            out.append({"no": no, "key": entry["key"], "ident": fix_ident(entry), "factory": owner})
    return out


def per_drawing_numbers(sd: Any, *, block: Optional[Block] = None, factory: Optional[int] = None) -> list[int]:
    """도면별로 막힌 장 번호(통째면 빈 목록 — 통째 글은 지금 글 그대로)."""
    block = block if block is not None else blocked(sd)
    if block.whole or not block.idents:
        return []
    return [row["no"] for row in blocked_entries(sd, block=block, factory=factory)]


def factory_has_blocked(sd: Any, factory: int, *, block: Optional[Block] = None) -> bool:
    """그 공장에 막힌 도면이 있는지([N공장 완료] 막힘 — 통째면 늘 참)."""
    block = block if block is not None else blocked(sd)
    return block.whole or bool(blocked_entries(sd, block=block, factory=factory))


def complete_blocked(sd: Any, *, block: Optional[Block] = None) -> bool:
    """[제작 완료]가 막히는지 — 통째 또는 막힌 도면이 하나라도(사장님 답 Q7 "그 도면이 끝날 때까지 막힘")."""
    block = block if block is not None else blocked(sd)
    return block.whole or bool(blocked_entries(sd, block=block))


def factory_complete_blocked(sd: Any, factory: int, *, final: bool, block: Optional[Block] = None) -> bool:
    """[N공장 완료]가 막히는지 — 그 공장에 막힌 도면 · 마지막 공장(= 주문 제작 완료)이면 [제작 완료]와 같은 판정."""
    block = block if block is not None else blocked(sd)
    return complete_blocked(sd, block=block) if final else factory_has_blocked(sd, factory, block=block)


# --------------------------------------------------------------------------- #
# 통째 작업에서 막힌 도면 빼기(§3-6 ①)
# --------------------------------------------------------------------------- #
def expand_plan(sd: Any) -> Optional[dict[str, Any]]:
    """통째 작업을 도면별 표시로 풀어 적을지 — 통째가 아니고 지금 도면 중 막힌 장이 1장 이상일 때만(풀이 §11-6).

    범위는 막히지 않은 지금 도면 **전부**다(공장을 가리지 않는다) — 공정 칸은 주문 하나에 값 하나라 막힌 도면이 없으면 반장 한 번에
    두 공장 장이 모두 완료되는 지금 규칙(설계서 2026-11-23 C8)과 같은 범위여야 한다(2026-11-25 D1 검토 판결 A).

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        ``{total, numbers, skip_keys, keys}`` — ``numbers`` = 막힌 장 번호, ``skip_keys`` = 막힌 장 key, ``keys`` = 풀어 적을 장 key
        (막히지 않은 지금 도면 전부 — 비면 처리할 장이 없다). 풀어 적을 일이 아니면 None(지금처럼 칸만 켬).
    """
    block = blocked(sd)
    if block.whole or not block.idents:
        return None
    rows = resolve_final_drawing_files(sd)
    skipped = [(no, entry) for no, entry in enumerate(rows, 1) if entry_blocked(block, entry)]
    if not skipped:
        return None
    keys = list(dict.fromkeys(entry["key"] for entry in rows if not entry_blocked(block, entry)))
    return {"total": len(rows), "numbers": [no for no, _e in skipped], "skip_keys": [e["key"] for _no, e in skipped],
            "keys": keys}


def expand_confirm(sd: Any) -> Optional[dict[str, Any]]:
    """통째 작업 확인 창 본문 재료(§2-4 · §10) — ``{done, numbers, tail}`` 또는 None(지금 글 그대로).

    화면(``foms-production-sheet-parts.js``)이 "이 주문의 도면 {sheets}장 중 {done}장이 {파트} 완료로 처리돼요. " + ``tail`` 로 잇는다.
    ``sheets``(N) 와 ``done``(M)은 같은 모집단 — 주문 전체 지금 도면 · 그중 처리될 장.
    """
    plan = expand_plan(sd)
    if plan is None:
        return None
    return {"done": len(plan["keys"]), "numbers": plan["numbers"], "tail": skip_tail(plan["numbers"])}


def confirm_extras(sd: Any) -> dict[str, Any]:
    """공정 API · 작업 시트 · '내 공정' [끝] · PC 창 확인 창 자료에 더할 값 — 막힌 도면이 있으면 ``{"fix": …}``, 없으면 ``{}``(그대로)."""
    fix = expand_confirm(sd)
    return {"fix": fix} if fix else {}


def expanded_words(numbers: list[int]) -> dict[str, str]:
    """풀어 쓴 뒤 화면이 잇는 글 재료 — ``tail`` = "도면 2는 고치는 중이라 뺐어요.", ``hold`` = "도면 2 고치는 중"([끝] 자리)."""
    return {"tail": f"도면 {numbers_text(numbers)}{number_topic(numbers[-1])} 수정 중이라 뺐어요.", "hold": fixing_label(numbers)}


def blocked_left_numbers(sd: Any, left_keys: Iterable[str], *, block: Optional[Block] = None) -> list[int]:
    """그 파트에 남은 장(``left_keys``)이 **도면별로 막힌 장뿐**이면 그 장 번호, 아니면 빈 목록(남은 장 없음 · 처리할 장 있음 · 통째).

    공정 줄이 [끝] 대신 "도면 2 고치는 중"을 보일지(2026-11-25 D1 검토 판결 D) — 누르면 처리할 장이 없어 거절되는 길을 없앤다.
    """
    block = block if block is not None else blocked(sd)
    left = set(left_keys)
    if block.whole or not block.idents or not left:
        return []
    rows = [(no, entry) for no, entry in enumerate(resolve_final_drawing_files(sd), 1) if entry["key"] in left]
    if not rows or not all(fix_ident(entry) in block.idents for _no, entry in rows):
        return []
    return [no for no, _entry in rows]


# --------------------------------------------------------------------------- #
# 글 꼴(새 글 둘 — §10)
# --------------------------------------------------------------------------- #
def numbers_text(numbers: Iterable[int]) -> str:
    """도면 번호 줄 — "2" · "2 · 3"."""
    return " · ".join(str(n) for n in numbers)


def number_topic(n: int) -> str:
    """숫자 뒤 토씨(은/는) — 끝자리 소리로(1 · 3 · 6 · 7 · 8 · 0 → 은, 2 · 4 · 5 · 9 → 는)."""
    return "은" if str(abs(int(n)))[-1] in _FINAL_DIGITS else "는"


def fixing_label(numbers: Iterable[int]) -> str:
    """도면별 막힘 글 "도면 2 고치는 중" · "도면 2 · 3 고치는 중"(배지 · 공정 줄 · 작업 시트, §10 '공장 막힘(번호)')."""
    return f"도면 {numbers_text(numbers)} 수정 중"


def skip_tail(numbers: list[int]) -> str:
    """확인 창 본문 뒤 문장 — "도면 2는 고치는 중이라 빼요." · "도면 2 · 3은 고치는 중이라 빼요."."""
    return f"도면 {numbers_text(numbers)}{number_topic(numbers[-1])} 수정 중이라 빼요."


def expand_confirm_body(sheets: int, done: int, part_label: str, numbers: list[int]) -> str:
    """통째 작업 확인 창 본문 전부(시험 · 서버 쪽 글 — 화면 JS 와 같은 글)."""
    return f"이 주문의 도면 {sheets}장 중 {done}장이 {part_label} 완료로 처리돼요. {skip_tail(numbers)}"


def expand_done_text(total: int, done: int, part_label: str, numbers: list[int]) -> str:
    """풀어 쓴 [끝] 뒤 알림 글 전부(시험 · 서버 쪽 글 — 화면 JS ``FomsSheetParts.doneText`` 와 같은 글)."""
    return f"도면 {total}장 중 {done}장을 {part_label} 완료로 처리했어요. {expanded_words(numbers)['tail']}"


# --------------------------------------------------------------------------- #
# 수정본 보내기의 풀림 · 이어받기(D2 — §3-4 · §3-5, 전달 쓰기가 같은 JSON 사본에서 부른다)
# --------------------------------------------------------------------------- #
#: ``drawing_fix.log`` · ``file_successor`` 에 남기는 줄 수(넘으면 앞을 버림 — 전체 기록은 ``OrderEvent``).
FIX_LOG_CAP = 50
LOG_DONE = "done"


def file_successor(sd: Any) -> dict[str, str]:
    """파일 도면 이어받기 표(``drawing_fix.file_successor`` — 새 key → 옛 key, §3-5). 없으면 빈 사전."""
    raw = _fix_table(sd).get("file_successor")
    return {str(k): str(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(raw, dict) else {}


def _writable_fix(sd: dict[str, Any]) -> dict[str, Any]:
    table = sd.get(DRAWING_FIX_KEY)
    if not isinstance(table, dict):
        table = {}
        sd[DRAWING_FIX_KEY] = table
    return table


def release_fixing_on_transfer(sd: dict[str, Any], idents: Iterable[str], *, by_name: str, at: str) -> list[int]:
    """수정본 전달이 건드린 열쇠의 [수정 시작] 표시를 지운다(제자리 — §3-4). 안 건드린 도면은 그대로 막힘.

    공장 요청은 :func:`close_requests_on_transfer` 가 따로 닫는다. 지운 것이 있으면 ``log`` 에 ``done`` 한 줄(최근
    :data:`FIX_LOG_CAP` 줄).

    Args:
        sd: 고칠 ``structured_data`` 사본(부르는 쪽이 재대입 · ``flag_modified``).
        idents: 건드린 열쇠(:func:`fix_ident` 꼴).
        by_name: 보낸 사람 이름. at: 보낸 때(UTC iso).

    Returns:
        풀린 도면 번호(고치는 중 표시의 ``no``, 없으면 빈 목록).
    """
    fixing = _fix_table(sd).get("fixing")
    wanted = set(_clean_idents(idents))
    hit = sorted(ident for ident in fixing if ident in wanted) if isinstance(fixing, dict) else []
    if not hit:
        return []
    table = _writable_fix(sd)
    numbers = [table["fixing"].pop(ident).get("no") for ident in hit]
    numbers = [n for n in numbers if isinstance(n, int)]
    log = [row for row in table.get("log") or [] if isinstance(row, dict)]
    log.append({"act": LOG_DONE, "idents": hit, "numbers": numbers, "by_name": by_name, "at": at})
    table["log"] = log[-FIX_LOG_CAP:]
    return numbers


def request_checked(request: Any) -> bool:
    """공장 요청이 [반영 완료] 표시됐는지(``checked`` — 설계서 §3-2 · N5, ``checked_by_name`` · ``checked_at`` 와 같이 적힌다).

    [반영 완료]는 상태(``state``)를 바꾸지 않는다 — 수정본이 갈 때까지 그 도면은 막힌 채다(사장님 "요청하면 바로 막기").
    """
    return isinstance(request, dict) and request.get("checked") is True


def unhandled_requests(sd: Any) -> list[dict[str, Any]]:
    """[반영 완료]도 [요청 반려]도 안 된 공장 요청(열림 + 체크 안 됨) — 하나라도 있으면 수정본을 못 보낸다(§4-2 ``FACTORY_REQUEST_OPEN``)."""
    requests = _fix_table(sd).get("requests")
    return [r for r in requests or [] if isinstance(r, dict) and r.get("state") == REQUEST_OPEN and not request_checked(r)]


def request_left(request: Any) -> list[str]:
    """공장 요청이 아직 막는 열쇠 = ``targets`` − ``resolved``(수정본이 간 열쇠, 2026-11-25 D2 지휘 N — "고치는 도면만 막기 ·
    수정본을 보내면 풀림"). 요청이 열린 동안만 뜻이 있다(닫힌 요청은 부르는 쪽이 거른다)."""
    if not isinstance(request, dict) or not isinstance(request.get("targets"), list):
        return []
    resolved = set(_clean_idents(request.get("resolved") or [])) if isinstance(request.get("resolved"), list) else set()
    return [ident for ident in _clean_idents(request["targets"]) if ident not in resolved]


def _target_numbers(request: dict[str, Any], idents: Iterable[str]) -> list[int]:
    """요청 ``numbers`` 가 ``targets`` 와 짝이면 그 열쇠들의 번호(짝이 아니면 빈 목록 — 기록용)."""
    targets, numbers = _clean_idents(request.get("targets") or []), request.get("numbers") or []
    if len(targets) != len(numbers):
        return []
    wanted = set(idents)
    return [n for t, n in zip(targets, numbers) if t in wanted and isinstance(n, int)]


def close_requests_on_transfer(sd: dict[str, Any], idents: Iterable[str], *, by_name: str, at: str) -> list[str]:
    """수정본 전달이 건드린 열쇠를 열린 공장 요청의 ``resolved`` 에 적고, 대상이 모두 풀린 요청만 ``done``(+ ``done_at``)으로
    닫는다(제자리 — 설계서 §3-4 "안 건드린 도면은 그대로 막힘", 지휘 N).

    일부만 풀린 요청은 ``open`` · ``checked`` 그대로 — 남은 도면은 막힌 채이고, 도면팀이 남은 도면을 마저 보내거나 [요청 반려]로
    닫는다. 풀린 것이 있으면 ``log`` 에 ``done`` 한 줄(이번에 풀린 열쇠 · 번호 · 손댄 요청 · 닫은 요청).

    Args:
        sd: 고칠 사본. idents: 건드린 열쇠. by_name: 보낸 사람 이름. at: 보낸 때(UTC iso).

    Returns:
        이번에 닫은(``done``) 요청 id(없으면 빈 목록).
    """
    wanted = set(_clean_idents(idents))
    requests = _fix_table(sd).get("requests")
    touched, closed, freed, numbers = [], [], set(), set()
    for request in requests or []:
        if not (isinstance(request, dict) and request.get("state") == REQUEST_OPEN):
            continue
        hit = [ident for ident in request_left(request) if ident in wanted]
        if not hit:
            continue
        resolved = _clean_idents(request.get("resolved") or []) if isinstance(request.get("resolved"), list) else []
        request["resolved"] = list(dict.fromkeys(resolved + hit))
        touched.append(str(request.get("id") or ""))
        freed.update(hit)
        numbers.update(_target_numbers(request, hit))
        if not request_left(request):
            request.update(state="done", done_at=at)
            closed.append(str(request.get("id") or ""))
    if not touched:
        return []
    table = _writable_fix(sd)
    log = [row for row in table.get("log") or [] if isinstance(row, dict)]
    log.append({"act": LOG_DONE, "idents": sorted(freed), "numbers": sorted(numbers), "requests": touched,
                "closed": closed, "by_name": by_name, "at": at})
    table["log"] = log[-FIX_LOG_CAP:]
    return closed


def inherit_file_successors(sd: dict[str, Any], pairs: dict[str, str], old_files: Iterable[Any]) -> None:
    """파일로 올린 도면이 고른 도면을 이어받는다(제자리 — §3-5): ``file_successor[새 key] = 옛 key`` · 옛 도면 공장.

    공장은 옛 도면(그 항목의 시트 신원 · key — :func:`~foms.services.orders.drawing_factory.sheet_factory`)이 2공장일 때만 새
    key 를 2공장 줄로 적는다(1공장이면 줄 없음 — 지금 규칙). 막힘 풀림은 :func:`release_fixing_on_transfer`(건드린 열쇠)가 한다.

    Args:
        sd: 고칠 사본. pairs: 파일 도면 짝(새 key → 고른 옛 key, '새 도면'은 빼고).
        old_files: 전달 전 확정 도면 목록(옛 항목의 시트 신원으로 공장을 읽는다).
    """
    if not pairs:
        return
    olds = {str(e.get("key") or ""): e for e in old_files if isinstance(e, dict)}
    from_factory = {new: sheet_factory(sd, olds.get(old) or {"key": old}) for new, old in pairs.items()}
    table = _writable_fix(sd)
    successors = {**file_successor(sd), **pairs}
    table["file_successor"] = dict(list(successors.items())[-FIX_LOG_CAP:])
    seconds = {new: factory for new, factory in from_factory.items() if factory != 1}
    if seconds:
        raw = sd.get(DRAWING_FACTORY_KEY) if isinstance(sd.get(DRAWING_FACTORY_KEY), dict) else {}
        files = dict(raw.get("files") or {}) if isinstance(raw.get("files"), dict) else {}
        files.update(seconds)
        sd[DRAWING_FACTORY_KEY] = {**raw, "sheets": raw.get("sheets") or {}, "files": files}


__all__ = [
    "Block", "DRAWING_FIX_KEY", "FILE_PREFIX", "REQUEST_OPEN", "SHEET_PREFIX", "WHY_FACTORY", "WHY_FIXING", "WHY_SALES",
    "close_requests_on_transfer", "file_successor", "inherit_file_successors", "release_fixing_on_transfer", "request_checked",
    "request_left", "unhandled_requests",
    "blocked", "blocked_entries", "blocked_left_numbers", "complete_blocked", "confirm_extras", "drawing_blocked", "entry_blocked",
    "expand_confirm", "expand_confirm_body", "expand_done_text", "expand_plan", "expanded_words", "factory_complete_blocked", "factory_has_blocked", "fix_ident", "fixing_idents", "fixing_label", "idents_for_keys",
    "number_topic", "numbers_text", "open_request_idents", "per_drawing_numbers", "sales_request_idents", "skip_tail",
]
