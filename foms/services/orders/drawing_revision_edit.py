"""도면팀 확인 전 영업의 '요청 고치기'(사용자 결정 Q5-③) — 판정·본문 검사·항목 고치기.

라우트 ``POST /api/orders/<id>/request-revision/edit``(``foms/api/drawing/erp_orders_revision.py``)는
잠금·쓰기·알림만 하고, 무엇을 고칠 수 있는지와 어떻게 고치는지는 이 모듈이 정한다. 작업실
화면값(``customer_send.bar`` 의 ``edit_revision`` · ``customer_send.edit_revision`` 미리 채움)도
같은 판정 함수를 쓴다 — 화면과 서버가 다른 답을 내지 않게.

고칠 수 있는 요청: ``drawing_status == RETURNED`` 이고 이력의 **마지막** ``REQUEST_REVISION`` 이
도면팀 반영 체크(``review_check.checked``) 전. 요청 식별값(``at``·``by_user_id`` — 반영 체크
토글이 보내는 두 값)은 바꾸지 않는다. 고치기 전 내용은 항목 안 ``edits`` 목록에 남긴다.

본문 규칙: 보내지 않은 칸(키 없음·null·빈 문자열)은 그대로다. 출처(``source``)와 받은 경로
(``received_via``)는 따로 본다 — 경로만 오면 출처는 두고(고객 요청일 때만 경로를 바꾼다), 출처만
오면 경로는 둔다(영업 의견으로 바꿀 때만 지운다). 메모는 공백만이면 400, 바뀐 칸이 하나도 없으면
400 ``NOTHING_TO_EDIT``(쓰기·버전·알림 없음).
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, NamedTuple

from foms.services.orders.drawing_revision_files import (
    MAX_REVISION_FILES,
    normalize_revision_files,
    revision_reference_display_rows,
)
from foms.services.orders.drawing_revision_source import (
    INVALID_REVISION_SOURCE,
    RECEIVED_VIA_LABELS,
    REVISION_SOURCES,
    SOURCE_CUSTOMER,
    SOURCE_SALES,
)

#: 고치기 전 내용으로 ``edits`` 에 남기는 필드(출처 필드는 있을 때만).
_EDITABLE_FIELDS = (
    "note", "files", "files_count", "target_drawing_keys", "target_drawing_numbers",
    "target_drawing_key", "target_drawing_number",
)
_SOURCE_FIELDS = ("source", "received_via")


class EditError(NamedTuple):
    code: str
    message: str
    status: int


class RevisionEditRequest(NamedTuple):
    """검사를 통과한 본문. ``None`` 인 칸은 '보내지 않음 = 그대로'.

    ``source_fields`` 는 **보낸 칸만** 담는다(``source``·``received_via`` 따로). 키가 없거나
    null·빈 문자열이면 그 칸은 그대로다 — 수정요청 라우트의 '키 없음 = 지금과 같음'과 같은 뜻.
    """
    note: str | None
    files: list[dict] | None
    source_fields: dict[str, str] | None
    target_keys: list[str] | None


#: 바뀐 것이 하나도 없는 고치기(빈 본문·같은 값) — 쓰기·버전·알림 없이 400.
NOTHING_TO_EDIT = "NOTHING_TO_EDIT"


def editable_revision_request(sd: Any) -> tuple[int | None, dict | None]:
    """고칠 수 있는 마지막 수정요청의 (이력 위치, 항목). 없으면 ``(None, None)``."""
    if not isinstance(sd, Mapping) or str(sd.get("drawing_status") or "").upper() != "RETURNED":
        return None, None
    history = sd.get("drawing_transfer_history")
    if not isinstance(history, list):
        return None, None
    for idx in range(len(history) - 1, -1, -1):
        entry = history[idx]
        if isinstance(entry, dict) and entry.get("action") == "REQUEST_REVISION":
            review = entry.get("review_check") if isinstance(entry.get("review_check"), Mapping) else {}
            return (None, None) if bool(review.get("checked")) else (idx, entry)
    return None, None


def is_requester(user: Any, entry: Any) -> bool:
    """이 사용자가 그 수정요청을 낸 사람인가."""
    if user is None or not isinstance(entry, Mapping):
        return False
    try:
        return int(entry.get("by_user_id")) == int(getattr(user, "id", None))
    except (TypeError, ValueError):
        return False


def can_edit_revision_request(user: Any, entry: Any, *, is_admin: bool, sales_side: bool) -> bool:
    """요청자 본인·배정 영업(영업 쪽)·관리자만."""
    if entry is None or user is None:
        return False
    return bool(is_admin or sales_side or is_requester(user, entry))


def parse_revision_edit_body(order_id: int, data: Any) -> tuple[RevisionEditRequest | None, EditError | None]:
    """본문 검사(행 잠금·쓰기 전). files 는 2b 계약, 출처는 수정요청과 같은 엄격 규칙."""
    body = data if isinstance(data, Mapping) else {}
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        return None, EditError("INVALID_REVISION_NOTE", "요청 내용이 올바르지 않습니다.", 400)
    if isinstance(note, str) and not note.strip():
        # 수정요청 창의 '메모 필수'와 같다 — 요청 내용을 빈칸으로 만들 수 없다.
        return None, EditError("INVALID_REVISION_NOTE", "요청 내용을 적어 주세요.", 400)
    files = None
    raw_files = body.get("files")
    if raw_files is not None:
        files, rejects = normalize_revision_files(order_id, raw_files)
        if rejects:
            too_many = isinstance(raw_files, list) and len(raw_files) > MAX_REVISION_FILES
            return None, EditError(
                "INVALID_REVISION_FILE",
                (f"참고 파일은 {MAX_REVISION_FILES}개까지 올릴 수 있습니다." if too_many
                 else "참고 파일 경로가 올바르지 않습니다. 파일을 다시 올려 주세요."),
                400,
            )
    source_fields, source_err = _parse_source_fields(body)
    if source_err:
        return None, source_err
    raw_targets = body.get("target_file_keys")
    if raw_targets is None:
        raw_targets = body.get("target_drawing_keys")
    target_keys = None
    if raw_targets is not None:
        if not isinstance(raw_targets, list) or not all(isinstance(k, str) and k.strip() for k in raw_targets):
            return None, EditError("INVALID_REVISION_TARGET", "수정 대상 도면이 올바르지 않습니다.", 400)
        target_keys = list(dict.fromkeys(k.strip() for k in raw_targets))
    return RevisionEditRequest(note=note, files=files, source_fields=source_fields,
                               target_keys=target_keys), None


def _parse_source_fields(body: Mapping[str, Any]) -> tuple[dict[str, str] | None, EditError | None]:
    """출처·받은 경로를 **따로** 읽는다(보낸 칸만). 목록 밖 값은 수정요청과 같은 엄격 400."""
    fields: dict[str, str] = {}
    for key, allowed in (("source", REVISION_SOURCES), ("received_via", tuple(RECEIVED_VIA_LABELS))):
        value = body.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if not isinstance(value, str) or value.strip() not in allowed:
            return None, EditError(INVALID_REVISION_SOURCE, "요청 출처 값이 올바르지 않습니다.", 400)
        fields[key] = value.strip()
    return (fields or None), None


def _apply_source_fields(target: dict, fields: Mapping[str, str]) -> None:
    """보낸 칸만 반영한다. 받은 경로는 고객 요청에만 뜻이 있다(영업 의견·옛 항목이면 버린다)."""
    source = fields.get("source") or target.get("source")
    if source == SOURCE_SALES:
        target["source"] = SOURCE_SALES
        target.pop("received_via", None)
    elif source == SOURCE_CUSTOMER:
        target["source"] = SOURCE_CUSTOMER
        if fields.get("received_via"):
            target["received_via"] = fields["received_via"]


def _file_keys(files: Any) -> list[str]:
    return [str((f or {}).get("key") or "") for f in (files or []) if isinstance(f, Mapping)]


def _changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """고친 칸이 하나라도 실제로 바뀌었나(참고 파일은 key 목록으로 비교)."""
    if _file_keys(before.get("files")) != _file_keys(after.get("files")):
        return True
    if list(before.get("target_drawing_keys") or []) != list(after.get("target_drawing_keys") or []):
        return True
    return any(before.get(k) != after.get(k) for k in ("note", *_SOURCE_FIELDS))


def _resolve_targets(current_files: list, keys: list[str]) -> tuple[list[str], list[int]] | EditError:
    by_key = {}
    for idx, f in enumerate(current_files):
        key = ((f or {}).get("key") or "").strip() if isinstance(f, Mapping) else ""
        if key and key not in by_key:
            by_key[key] = idx + 1
    if not keys and len(current_files) > 1:
        return EditError("INVALID_REVISION_TARGET", "수정 요청할 도면 번호를 선택해주세요.", 400)
    if not keys and len(by_key) == 1:
        keys = list(by_key)  # 도면이 1장이면 수정요청 라우트처럼 그 도면이 대상이다
    numbers = []
    for key in keys:
        if key not in by_key:
            return EditError("INVALID_REVISION_TARGET", f"선택한 수정 대상 도면을 찾을 수 없습니다: {key}", 400)
        numbers.append(by_key[key])
    return keys, numbers


def apply_revision_edit(
    sd: dict, req: RevisionEditRequest, *, user: Any, is_admin: bool, sales_side: bool, now_str: str,
) -> tuple[dict | None, EditError | None]:
    """잠근 뒤 deepcopy 한 ``sd`` 의 마지막 수정요청을 고친다(제자리). 고친 항목을 돌려준다.

    호출자는 ``lock_order_row`` 로 잠근 주문의 ``structured_data`` 사본을 넘기고, 성공이면
    ``execute_single_order_write`` 콜백 안에서 재대입·``flag_modified`` 한다.
    """
    if str(sd.get("drawing_status") or "").upper() != "RETURNED":
        return None, EditError("REVISION_NOT_EDITABLE", "도면팀이 수정 중인 요청만 고칠 수 있습니다.", 409)
    history = list(sd.get("drawing_transfer_history") or [])
    last_idx = next((i for i in range(len(history) - 1, -1, -1)
                     if isinstance(history[i], dict) and history[i].get("action") == "REQUEST_REVISION"), None)
    if last_idx is None:
        return None, EditError("REVISION_NOT_EDITABLE", "고칠 수정 요청을 찾을 수 없습니다.", 409)
    idx, entry = editable_revision_request({**sd, "drawing_transfer_history": history})
    if entry is None:
        return None, EditError("REVISION_ALREADY_CHECKED",
                               "도면팀이 이미 반영을 확인한 요청이라 고칠 수 없어요. 수정요청을 취소하고 다시 요청하세요.",
                               409)
    if not can_edit_revision_request(user, entry, is_admin=is_admin, sales_side=sales_side):
        return None, EditError("FORBIDDEN", "요청을 고칠 권한이 없습니다. (요청자·주문 담당자·관리자만 가능)", 403)

    target = copy.deepcopy(entry)
    if req.target_keys is not None:
        resolved = _resolve_targets(list(sd.get("drawing_current_files") or []), req.target_keys)
        if isinstance(resolved, EditError):
            return None, resolved
        keys, numbers = resolved
        target["target_drawing_keys"] = keys or None
        target["target_drawing_numbers"] = numbers or None
        target["target_drawing_key"] = keys[0] if len(keys) == 1 else None
        target["target_drawing_number"] = numbers[0] if len(numbers) == 1 else None

    snapshot = {k: copy.deepcopy(entry.get(k)) for k in _EDITABLE_FIELDS}
    snapshot.update({k: entry[k] for k in _SOURCE_FIELDS if k in entry})
    snapshot.update(replaced_at=now_str, replaced_by_user_id=getattr(user, "id", None),
                    replaced_by=getattr(user, "name", "") or "")

    if req.note is not None:
        target["note"] = req.note
    if req.files is not None:
        target["files"] = req.files
        target["files_count"] = len(req.files)
    if req.source_fields:
        _apply_source_fields(target, req.source_fields)
    if not _changed(entry, target):
        return None, EditError(NOTHING_TO_EDIT, "바뀐 내용이 없어요.", 400)
    target["edits"] = [*list(entry.get("edits") or []), snapshot]
    target["edited_at"] = now_str
    target["edited_by_user_id"] = getattr(user, "id", None)
    target["edited_by"] = getattr(user, "name", "") or ""
    history[idx] = target
    sd["drawing_transfer_history"] = history
    return target, None


def edit_revision_prefill(order_id: int, entry: Any) -> dict[str, Any]:
    """보내기·요청 고치기 창 미리 채움(``customer_send.edit_revision``). 없으면 ``{}``."""
    if not isinstance(entry, Mapping):
        return {}
    files, hidden = revision_reference_display_rows(order_id, entry.get("files"))
    return {
        "request_at": str(entry.get("at") or entry.get("transferred_at") or "").strip(),
        "by_user_id": entry.get("by_user_id") or "",
        "note": str(entry.get("note") or ""),
        "source": str(entry.get("source") or ""),
        "received_via": str(entry.get("received_via") or ""),
        "target_drawing_keys": list(entry.get("target_drawing_keys") or []),
        "files": [{"key": f["key"], "filename": f["filename"], "view_url": f["view_url"],
                   "is_image": f["is_image"]} for f in files],
        "files_hidden_count": hidden,
        "edited": bool(entry.get("edited_at")),
    }


__all__ = [
    "NOTHING_TO_EDIT",
    "EditError",
    "RevisionEditRequest",
    "apply_revision_edit",
    "can_edit_revision_request",
    "edit_revision_prefill",
    "editable_revision_request",
    "is_requester",
    "parse_revision_edit_body",
]
