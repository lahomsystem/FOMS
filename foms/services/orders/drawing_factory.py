"""도면 장의 공장(1공장 · 2공장) — 자료 읽기 · 일이 시작된 장 · 걸린 것 글 · 옮김 계획 · 상차 줄(설계서 2026-11-23 §4-13 · §6-3 · §4-15).

자료는 주문 JSON 의 **서버 소유** 칸 ``structured_data.drawing_factory`` 하나다(안 ⓒ)::

    {"sheets": {"<마법사 시트 id>": 2}, "files": {"<직접 올린 파일 저장 key>": 2}, "at": "<UTC iso>", "by_name": "오가람"}

* 공장 지정 API(``foms/api/drawing/erp_orders_sheet_factory.py``)만 쓴다. 폼 저장(``structured_form_projection.SERVER_LOCKED_KEYS``) ·
  주문 만들기(``order_create._prepare_structured``) · 마법사 저장 · 전달 · 확정 어느 길도 이 칸을 못 바꾼다.
* 값은 2 만 줄로 둔다(1공장으로 되돌리면 줄을 지운다). 칸이 없거나 비면 모든 장이 1공장 = 지금과 같다.
* 시트 신원(``sheet_id``)은 판이 바뀌어도 같아서 다시 보내기 · 한 장 바꾸기 · 확정 · 전달 취소에서 저절로 살아남는다. 직접 올린 파일은
  저장 key 로 — 같은 파일을 새로 올리면 새 key 라 1공장으로 돌아간다(§16). 마법사 시트 복제는 새 신원이라 1공장. AS 도면은 공장을 두지
  않는다(``as_drawing`` 은 지금 확정 도면 목록 밖).
* 이 모듈은 순수 함수다(쿼리 0). 표시 줄(``production_part_marks``)은 부르는 쪽이 읽어 넘긴다. ``flags.factory2``(라홈시스템 계약)와
  상관없다(C7).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.orders.stage_override import STAGE_FORWARD_RANK
from foms.services.production.factory_constants import DEFAULT_FACTORY, FACTORIES, FACTORY_2, factory_label
from foms.services.production.part_constants import PRODUCTION_PART_KEYS, PRODUCTION_PART_LABELS
from foms.services.production.part_mark_rules import subject_particle, toward_particle

#: 주문 JSON 칸 이름(서버 소유).
DRAWING_FACTORY_KEY = "drawing_factory"
#: 이벤트 · 감사 행위 코드.
SHEET_FACTORY_EVENT = "DRAWING_SHEET_FACTORY_CHANGED"
SHEET_FACTORY_REFUSED = "DRAWING_SHEET_FACTORY_REFUSED"

FORBIDDEN_MESSAGE = "공장은 도면팀이나 관리자만 지정할 수 있어요."
ORDER_DONE_MESSAGE = "이미 제작 완료한 주문이에요."
NOT_CURRENT_MESSAGE = "지금 도면에 없는 장이에요. 화면을 다시 열어 주세요."

_PRODUCTION_RANK = STAGE_FORWARD_RANK["PRODUCTION"]
_KST = datetime.timezone(datetime.timedelta(hours=9))
_FINISHED = ("DONE", "BASIC")


class SheetFactoryRefusal(Exception):
    """공장 지정을 거절하는 까닭(상태 · 코드 · 글 · 자료) — API 가 응답으로 바꾼다. 하나라도 막히면 아무것도 안 바꾼다."""

    def __init__(self, status: int, code: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


@dataclass(frozen=True)
class FactoryChange:
    """장 하나의 공장 바꿈 — ``kind`` = sheet(시트 신원) · file(직접 올린 파일 key)."""

    kind: str
    ident: str
    before: int
    after: int
    keys: tuple[str, ...] = field(default=())  # 그 장의 지금 확정 도면 key(안 보낸 시트는 빈 것)


# --------------------------------------------------------------------------- #
# 읽기
# --------------------------------------------------------------------------- #
def _table(sd: Any) -> tuple[dict[str, int], dict[str, int]]:
    """``(시트 → 공장, 파일 key → 공장)`` — 1 · 2 가 아닌 값 · 모양이 다른 열쇠는 버린다."""
    raw = sd.get(DRAWING_FACTORY_KEY) if isinstance(sd, dict) else None
    raw = raw if isinstance(raw, dict) else {}

    def _clean(part: Any, key_ok: Callable[[str], bool]) -> dict[str, int]:
        rows = part if isinstance(part, dict) else {}
        return {str(k): v for k, v in rows.items() if v in FACTORIES and not isinstance(v, bool) and key_ok(str(k))}

    return _clean(raw.get("sheets"), lambda k: bool(clean_sheet_id(k))), _clean(raw.get("files"), lambda k: bool(k.strip()))


def _factory_of(entry: dict[str, Any], sheets: dict[str, int], files: dict[str, int]) -> int:
    sid = clean_sheet_id(entry.get("sheet_id"))
    if sid and sid in sheets:
        return sheets[sid]
    key = str(entry.get("key") or "").strip()
    return files.get(key, DEFAULT_FACTORY) if key else DEFAULT_FACTORY


def sheet_factory(sd: Any, entry: dict[str, Any]) -> int:
    """장 하나의 공장 — ``sheet_id`` 가 표에 있으면 그 값 → key 가 표에 있으면 그 값 → 1(§4-13). 쿼리 0.

    Args:
        sd: 주문 ``structured_data``.
        entry: 확정 도면 항목(``resolve_final_drawing_files`` 한 줄) 또는 ``{sheet_id}`` · ``{key}`` 꼴.

    Returns:
        1 · 2.
    """
    sheets, files = _table(sd)
    return _factory_of(entry, sheets, files)


def current_factories(sd: Any) -> list[tuple[dict[str, Any], int]]:
    """지금 확정 도면 장마다 ``(항목, 공장)`` — 도면 번호 순."""
    sheets, files = _table(sd)
    return [(entry, _factory_of(entry, sheets, files)) for entry in resolve_final_drawing_files(sd)]


def present_factories(sd: Any) -> tuple[int, ...]:
    """있는 공장(§4-1) — 지금 장들의 공장 모음(정의 순서). 1공장만이면 한 공장 주문(오늘과 같은 길)."""
    found = {factory for _entry, factory in current_factories(sd)}
    return tuple(f for f in FACTORIES if f in found)


def has_second_factory(sd: Any) -> bool:
    """지금 장 중 2공장 장이 하나라도 있는지 — 없으면 모든 2공장 그림이 꺼진다(지금 화면 그대로, §3)."""
    sheets, files = _table(sd)
    if not sheets and not files:
        return False
    return FACTORY_2 in present_factories(sd)


def wizard_sheet_ids(sd: Any) -> list[str]:
    """마법사 시트 id(아직 안 보낸 시트 포함) — 순서 유지, 모양이 다른 것은 건너뛴다."""
    wizard = sd.get("drawing_wizard") if isinstance(sd, dict) else None
    out: list[str] = []
    for sheet in (wizard.get("sheets") if isinstance(wizard, dict) else None) or []:
        sid = clean_sheet_id(sheet.get("id")) if isinstance(sheet, dict) else ""
        if sid and sid not in out:
            out.append(sid)
    return out


def factory_by_sheet(sd: Any) -> dict[str, int]:
    """마법사 · 지금 장의 시트 신원 중 2공장인 것 ``{sheet_id: 2}``(1공장은 열쇠가 없다) — 마법사 탭 딱지 · 공장 지정 API 응답."""
    sheets, _files = _table(sd)
    known = set(wizard_sheet_ids(sd)) | {clean_sheet_id(e.get("sheet_id")) for e in resolve_final_drawing_files(sd)}
    return {sid: f for sid, f in sorted(sheets.items()) if sid in known and f == FACTORY_2}


def factory_by_key(sd: Any) -> dict[str, int]:
    """지금 확정 도면 key 중 2공장인 것 ``{key: 2}``(시트 · 직접 올린 파일 모두) — 작업실 타일 · 생산 쪽."""
    return {entry["key"]: f for entry, f in current_factories(sd) if f == FACTORY_2}


# --------------------------------------------------------------------------- #
# 일이 시작된 장 · 공장 완료 · 걸린 것 글
# --------------------------------------------------------------------------- #
def _part_order(row: Any) -> int:
    part = getattr(row, "part", None)
    return PRODUCTION_PART_KEYS.index(part) if part in PRODUCTION_PART_KEYS else len(PRODUCTION_PART_KEYS)


def sheet_work(key: str, marks: Iterable[Any]) -> Optional[dict[str, Any]]:
    """장(지금 key)에 걸린 일 — 일이 시작된 장(§4-1 C3′)이면 무엇이 걸렸는지, 아니면 None.

    Args:
        key: 확정 도면 key.
        marks: 그 주문 표시 줄들(``ProductionPartMark`` 꼴 — ``drawing_key`` · ``part`` · ``state`` · 이름 칸).

    Returns:
        완료(재단 기본 포함)한 파트가 있으면 ``{kind: 'done', part, name}``(공정 순 첫 파트, 이름 = 완료한 사람), 담당만 있으면
        ``{kind: 'held', part, name}``(이름 = 담당). NONE 줄만 있거나 줄이 없으면 None(일이 시작 안 된 장 — 옮길 수 있다).
    """
    rows = sorted((m for m in marks if getattr(m, "drawing_key", None) == key and getattr(m, "state", "NONE") != "NONE"),
                  key=_part_order)
    done = [m for m in rows if m.state in _FINISHED]
    if done:
        row = done[0]
        return {"kind": "done", "part": row.part, "name": row.done_by_name or row.picked_by_name or ""}
    if rows:
        row = rows[0]
        return {"kind": "held", "part": row.part, "name": row.picked_by_name or ""}
    return None


def _final_particle(word: str, with_final: str, without_final: str) -> str:
    """받침이 있으면 ``with_final``, 없으면 ``without_final``(한글이 아니면 받침 있음으로 본다)."""
    last = word[-1:] or " "
    if "가" <= last <= "힣":
        return word + (with_final if (ord(last) - ord("가")) % 28 else without_final)
    return word + with_final


def work_block_message(work: dict[str, Any], *, from_factory: int, to_factory: int) -> str:
    """일이 시작된 장을 옮기려 할 때의 글(409 ``SHEET_HAS_WORK``, §4-13 — 완료 · 담당을 갈라).

    Args:
        work: :func:`sheet_work` 결과.
        from_factory: 지금 공장.
        to_factory: 옮기려던 공장.

    Returns:
        해요체 한 문장 둘("2공장으로 옮길 수 없어요 — …").
    """
    head = f"{toward_particle(factory_label(to_factory))} 옮길 수 없어요 — "
    part = PRODUCTION_PART_LABELS.get(work["part"], work["part"])
    name = str(work.get("name") or "").strip()
    if work["kind"] == "done":
        who = subject_particle(name) if name else "다른 사람이"
        return (f"{head}{factory_label(from_factory)}에서 {who} {_final_particle(part, '을', '를')} 이미 완료한 장이에요. "
                "이미 완료한 장은 옮기지 않아요.")
    who = subject_particle(name) if name else "다른 사람이"
    ask = f"{name}에게" if name else "담당에게"
    return f"{head}{factory_label(from_factory)} {who} {part} 담당이에요. {ask} 맡기 취소를 부탁한 뒤 다시 해 주세요."


def factory_done_entry(sd: Any, factory: int) -> Optional[dict[str, Any]]:
    """공장 완료 표지가 **살아 있는지**(§4-14) — 항목이 있고 지금 그 공장 장 key 모음 ⊆ 저장한 ``keys`` 면 그 항목, 아니면 None.

    새 판(새 key)이 그 공장에 오면 저절로 풀리고, 그 공장 장이 하나도 없으면(있는 공장이 아님) 버린다. 표지는 3단계 ⑥(공장별
    제작 완료)이 ``structured_data.production.factory_done`` 에 쓴다 — 이 묶음은 읽기만 한다.
    """
    production = sd.get("production") if isinstance(sd, dict) else None
    marks = production.get("factory_done") if isinstance(production, dict) else None
    entry = marks.get(str(factory)) if isinstance(marks, dict) else None
    if not isinstance(entry, dict):
        return None
    current = {e["key"] for e, f in current_factories(sd) if f == factory}
    saved = {str(k) for k in entry.get("keys") or [] if isinstance(k, str)}
    return entry if current and current <= saved else None


def _kst_md_hm(raw: Any) -> str:
    """UTC iso → KST "11/24 16:10"(읽을 수 없으면 빈 글)."""
    try:
        at = datetime.datetime.fromisoformat(str(raw))
    except ValueError:
        return ""
    at = (at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)).astimezone(_KST)
    return f"{at.month}/{at.day} {at:%H:%M}"


def factory_done_message(factory: int, entry: dict[str, Any]) -> str:
    """완료한 공장으로 들고 나는 옮김의 글(409 ``FACTORY_DONE``) — "2공장은 강검수가 11/24 16:10에 제작 완료했어요. …"."""
    label = factory_label(factory)
    name = str(entry.get("by_name") or "").strip()
    when = _kst_md_hm(entry.get("at"))
    who = f"{subject_particle(name)} " if name else ""
    at = f"{when}에 " if when else ""
    return f"{_final_particle(label, '은', '는')} {who}{at}제작 완료했어요. 옮기려면 {label} 완료부터 취소해 주세요."


# --------------------------------------------------------------------------- #
# 옮김 계획 · 쓰기
# --------------------------------------------------------------------------- #
def _resolve_item(sd: dict[str, Any], item: dict[str, Any], current: list[dict[str, Any]],
                  known_sheets: set[str]) -> tuple[str, str, tuple[str, ...]]:
    """요청 한 줄 → ``(kind, 열쇠, 그 장의 지금 key 들)``. 시트 신원이 있는 파일을 key 로 보내도 시트로 친다."""
    raw_sid = str(item.get("sheet_id") or "").strip()
    sid = clean_sheet_id(raw_sid)
    if raw_sid:  # 보낸 시트 신원이 모양이 다르거나 어디에도 없으면 그 값 그대로 알려 준다(key 로 넘어가지 않는다)
        if not sid or sid not in known_sheets:
            raise SheetFactoryRefusal(409, "DRAWING_NOT_CURRENT", NOT_CURRENT_MESSAGE, {"sheet_id": raw_sid[:64]})
        return "sheet", sid, tuple(e["key"] for e in current if clean_sheet_id(e.get("sheet_id")) == sid)
    key = str(item.get("key") or "").strip()
    entry = next((e for e in current if e["key"] == key), None) if key else None
    if entry is None:
        raise SheetFactoryRefusal(409, "DRAWING_NOT_CURRENT", NOT_CURRENT_MESSAGE, {"key": key or None})
    entry_sid = clean_sheet_id(entry.get("sheet_id"))
    if entry_sid:
        return "sheet", entry_sid, tuple(e["key"] for e in current if clean_sheet_id(e.get("sheet_id")) == entry_sid)
    return "file", key, (key,)


def plan_factory_changes(sd: dict[str, Any], items: list[dict[str, Any]], *, stage: Optional[str],
                         load_marks: Callable[[], list[Any]]) -> list[FactoryChange]:
    """요청(장 하나 또는 여럿) → 바꿀 것. 하나라도 막히면 :class:`SheetFactoryRefusal`(아무것도 안 바꿈). 같은 값이면 빠진다.

    판정(§4-13 표): 바꿀 것이 있는데 시공 대기 이후면 409 ``ORDER_DONE``. 생산 단계(또는 단계를 모름)면 지금 장이 걸린 옮김만
    표시 줄을 읽어(``load_marks`` — 쿼리 1, 그 밖엔 0) 들고 나는 공장 완료 표지(``FACTORY_DONE``) → 일이 시작된 장(``SHEET_HAS_WORK``,
    완료 · 담당 갈라 ``blocked``). 생산 전 단계 · 안 보낸 시트는 그냥 된다.

    Args:
        sd: 주문 ``structured_data``(잠근 행의 값).
        items: ``[{sheet_id? , key?, factory: 1|2}]``(API 가 모양을 본 것).
        stage: 주문 큰 단계(``read_main_stage``).
        load_marks: 그 주문 표시 줄을 읽는 함수(필요할 때만 부른다).

    Returns:
        :class:`FactoryChange` 목록(요청 순서, 같은 장은 마지막 값).
    """
    current = resolve_final_drawing_files(sd)
    known_sheets = set(wizard_sheet_ids(sd)) | {clean_sheet_id(e.get("sheet_id")) for e in current} - {""}
    sheets, files = _table(sd)
    wanted: dict[tuple[str, str], tuple[int, tuple[str, ...]]] = {}
    for item in items:
        kind, ident, keys = _resolve_item(sd, item, current, known_sheets)
        wanted[(kind, ident)] = (int(item["factory"]), keys)
    changes = []
    for (kind, ident), (after, keys) in wanted.items():
        before = (sheets if kind == "sheet" else files).get(ident, DEFAULT_FACTORY)
        if before != after:
            changes.append(FactoryChange(kind, ident, before, after, keys))
    if not changes:
        return []
    rank = STAGE_FORWARD_RANK.get(str(stage or ""))
    if rank is not None and rank > _PRODUCTION_RANK:
        raise SheetFactoryRefusal(409, "ORDER_DONE", ORDER_DONE_MESSAGE)
    moving = [c for c in changes if c.keys]
    if moving and (rank is None or rank == _PRODUCTION_RANK):
        _check_production_moves(sd, moving, load_marks())
    return changes


def _check_production_moves(sd: dict[str, Any], moving: list[FactoryChange], marks: list[Any]) -> None:
    """생산 단계 옮김 — 공장 완료 표지 먼저, 그다음 일이 시작된 장(하나라도 막히면 모두 안 바꿈)."""
    for change in moving:
        for factory in (change.before, change.after):
            done = factory_done_entry(sd, factory)
            if done is not None:
                raise SheetFactoryRefusal(409, "FACTORY_DONE", factory_done_message(factory, done), {"factory": factory})
    blocked = []
    for change in moving:
        for key in change.keys:
            work = sheet_work(key, marks)
            if work is not None:
                blocked.append({"sheet_id": change.ident if change.kind == "sheet" else None, "key": key, **work,
                                "message": work_block_message(work, from_factory=change.before, to_factory=change.after)})
    if blocked:
        raise SheetFactoryRefusal(409, "SHEET_HAS_WORK", blocked[0]["message"], {"blocked": blocked})


def apply_factory_changes(sd: dict[str, Any], changes: list[FactoryChange], *, by_name: str, at_iso: str) -> None:
    """바꿀 것을 ``sd``(부르는 쪽의 deepcopy)에 쓴다 — 2 만 줄로, 1 은 줄 지움, 지금 장 · 시트 어디에도 없는 열쇠는 지움.

    Args:
        sd: 고칠 ``structured_data`` 사본(제자리에서 바꾼다 — 부르는 쪽이 재대입 · ``flag_modified``).
        changes: :func:`plan_factory_changes` 결과(비어 있지 않음).
        by_name: 바꾼 사람 이름 스냅샷.
        at_iso: 바꾼 때(UTC iso).
    """
    sheets, files = _table(sd)
    for change in changes:
        table = sheets if change.kind == "sheet" else files
        if change.after == FACTORY_2:
            table[change.ident] = FACTORY_2
        else:
            table.pop(change.ident, None)
    current = resolve_final_drawing_files(sd)
    known_sheets = set(wizard_sheet_ids(sd)) | {clean_sheet_id(e.get("sheet_id")) for e in current}
    current_keys = {e["key"] for e in current}
    sd[DRAWING_FACTORY_KEY] = {
        "sheets": {k: v for k, v in sorted(sheets.items()) if v == FACTORY_2 and k in known_sheets},
        "files": {k: v for k, v in sorted(files.items()) if v == FACTORY_2 and k in current_keys},
        "at": at_iso,
        "by_name": by_name,
    }


def change_rows(sd: dict[str, Any], changes: list[FactoryChange]) -> list[dict[str, Any]]:
    """이벤트 payload · 응답 · 감사 글에 실을 줄 — 장 이름(마법사 시트 이름 · 파일 이름) · 도면 번호(n/m, 안 보낸 시트는 None)."""
    current = resolve_final_drawing_files(sd)
    wizard = sd.get("drawing_wizard") if isinstance(sd.get("drawing_wizard"), dict) else {}
    names = {clean_sheet_id(s.get("id")): str(s.get("name") or "") for s in wizard.get("sheets") or [] if isinstance(s, dict)}
    rows = []
    for change in changes:
        index = next((i for i, e in enumerate(current, 1) if e["key"] in change.keys), None)
        entry = current[index - 1] if index else {}
        rows.append({"sheet_id": change.ident if change.kind == "sheet" else None,
                     "key": change.ident if change.kind == "file" else (change.keys[0] if change.keys else None),
                     "name": names.get(change.ident) or entry.get("filename") or "",
                     "index": index, "total": len(current), "from": change.before, "to": change.after})
    return rows


def change_note(rows: list[dict[str, Any]]) -> str:
    """감사 글 꼬리 — "도면 2/3 1공장 → 2공장" · 안 보낸 시트는 "시트 '안방' 1공장 → 2공장"."""
    parts = []
    for row in rows:
        where = f"도면 {row['index']}/{row['total']}" if row["index"] else f"시트 '{row['name'] or row['sheet_id']}'"
        parts.append(f"{where} {factory_label(row['from'])} → {factory_label(row['to'])}")
    return ", ".join(parts)


# --------------------------------------------------------------------------- #
# 상차 줄(§4-15, 3단계 ⑦ 화면이 쓴다)
# --------------------------------------------------------------------------- #
def load_split(sd: Any) -> Optional[dict[str, Any]]:
    """출고 · 시공 화면의 상차 줄 — 2공장 장이 하나도 없으면 None(지금 화면과 같음). 쿼리 0(이미 든 주문 JSON).

    Returns:
        ``{text: "상차 1공장 3장 · 2공장 2장", factories: [{factory, sheets, done}]}``. 생산 단계에서 아직 안 끝난 공장(공장 완료
        표지가 살아 있지 않음)에는 "(제작 중)" — 예 "상차 1공장 3장 · 2공장 2장(제작 중)". 시공 대기 이후는 모두 완료로 본다.
    """
    if not has_second_factory(sd):
        return None
    counts = {f: 0 for f in FACTORIES}
    for _entry, factory in current_factories(sd):
        counts[factory] += 1
    workflow = sd.get("workflow") if isinstance(sd.get("workflow"), dict) else {}
    rank = STAGE_FORWARD_RANK.get(str(workflow.get("stage") or ""))
    in_production = rank == _PRODUCTION_RANK
    factories = []
    for factory in FACTORIES:
        if counts[factory]:
            done = (rank is not None and rank > _PRODUCTION_RANK) or (in_production and factory_done_entry(sd, factory) is not None)
            factories.append({"factory": factory, "sheets": counts[factory], "done": done})
    text = " · ".join(f"{factory_label(f['factory'])} {f['sheets']}장" + ("(제작 중)" if in_production and not f["done"] else "")
                      for f in factories)
    return {"text": f"상차 {text}", "factories": factories}
