"""도면 전달(transfer) source helper (WIZ-TRANSFER-01) — 순수 계산·``commit=False``.

이 모듈은 도면 전달의 **순수 소스**만 정본화한다:

- ``materialize_pending_snapshot`` : 현재 마법사 pending 상태
  (``structured_data['drawing_wizard']['pending']``)를 전달용 스냅샷 목록으로 materialize.
- ``materialize_transfer_attachments`` : 전달 대상 파일 참조를 **도면 key 경로로 필터**해
  ``drawing_current_files`` 엔트리로 materialize.

**계약(엄격)**: 어떤 helper 도 DB 세션에 ``commit``/``flush`` 하지 않고, 버전(version)
bump·이벤트(event) 기록·SIDEFX outbox enqueue 를 하지 않는다. 트랜잭션 조립(commit·
event·outbox)은 STATE-DRAWING-01 이 담당한다. 따라서 helper 는 db 세션을 인자로 받지
않으며 순수 계산 결과만 반환한다.

**도면 필터**(``project_construction_card_drawing_current_files_leak`` 함정 차단): 전달 대상
첨부는 반드시 해당 주문의 도면 key 경로(``orders/<id>/drawing_wizard/`` ·
``orders/<id>/drawing/`` · ``orders/<id>/drawing_gateway/`` 접두)만 통과시킨다. 실측
(``orders/<id>/measurement/`` 등)·일반 첨부 key 는 유출을 막기 위해 제외한다. 위저드 도면은
DB OrderAttachment 없이 R2-only 로 존재하므로 category(DB) 가 아니라 **key 경로**로 판정한다.

**asset-raw same-origin 규칙**: view/download URL 은 앱 same-origin 경로
(``/api/files/view/<key>`` · ``/api/files/download/<key>``)로만 만든다(운영 R2 presigned
교차출처 redirect 금지 — html2canvas 캡처 오염 방지 규약과 동일).
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

#: 마법사 시트 id 로 받아 줄 모양. 클라이언트가 보낸 값도 섞이므로 저장 전에 거른다.
_SHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: 마법사 산출물(시트 PNG) key 의 경로 조각 — sheet_id 없는 옛 엔트리의 시트 추정에 쓴다.
_WIZARD_EXPORT_SEGMENT = "/drawing_wizard/exports/"


def clean_sheet_id(value: Any) -> str:
    """도면 파일 엔트리의 ``sheet_id`` 를 검증해 돌려준다(모양이 다르면 빈 문자열)."""
    text = str(value or "").strip()
    return text if _SHEET_ID_RE.match(text) else ""


def _wizard_sheet_ids(structured_data: Any) -> list[str]:
    """``drawing_wizard.sheets`` 의 시트 id 목록(순서 유지, 모양이 다른 항목은 건너뜀)."""
    sd = structured_data if isinstance(structured_data, dict) else {}
    dw = sd.get("drawing_wizard")
    sheets = dw.get("sheets") if isinstance(dw, dict) else None
    out: list[str] = []
    for sheet in sheets if isinstance(sheets, list) else []:
        sid = clean_sheet_id(sheet.get("id")) if isinstance(sheet, dict) else ""
        if sid and sid not in out:
            out.append(sid)
    return out


def replace_same_sheet_files(
    old_files: list, new_files: list, structured_data: Any,
) -> tuple[list[dict], list[dict], list[int]]:
    """새 파일 중 마법사 시트가 같은 옛 엔트리를 **그 자리에서** 바꾼다(순수 계산).

    도면팀이 마지막에 저장·전달한 판이 시트(제품)별 1순위다(2026-10-04 사용자 결정, 주문
    5407: 영업 수령 확정 뒤 같은 시트 2판을 APPEND 로 보내 1판·2판이 함께 남았다). 상태와
    상관없이 같다. 다른 시트 도면은 건드리지 않는다 — 주문 전체 교체는 제품이 여럿인 주문에서
    고치지 않은 도면까지 지운다.

    옛 엔트리의 시트는 ``sheet_id`` 로 판정한다. ``sheet_id`` 가 없는 옛 엔트리(2026-10-04
    이전 전달)는 마법사 시트가 정확히 1개이고 key 가 마법사 산출물 경로일 때만 그 시트로 본다.
    같은 시트 옛 엔트리가 여럿이면(예전 APPEND 누적) 첫 자리에 새 판을 넣고 나머지는 뺀다.

    Args:
        old_files: 현재 ``drawing_current_files``.
        new_files: 이번 전달 파일(``materialize_transfer_attachments`` 결과).
        structured_data: 주문 ``structured_data``(마법사 시트 목록을 읽는다).

    Returns:
        ``(base_files, rest_new_files, replaced_numbers)`` — 시트 교체를 마친 목록, 시트로
        자리를 찾지 못한 새 파일(호출측이 기존 mode 규칙으로 처리), 바뀐 옛 엔트리의 1-기준
        번호(오름차순).
    """
    sheets = _wizard_sheet_ids(structured_data)
    sole_sheet = sheets[0] if len(sheets) == 1 else ""

    def _old_sheet(entry: Any) -> str:
        if not isinstance(entry, dict):
            return ""
        sid = clean_sheet_id(entry.get("sheet_id"))
        if sid:
            return sid
        key = str(entry.get("key") or "")
        return sole_sheet if sole_sheet and _WIZARD_EXPORT_SEGMENT in key else ""

    old_sheets = [_old_sheet(f) for f in old_files]
    slot_new: dict[int, dict] = {}
    dropped: set[int] = set()
    rest: list[dict] = []
    for nf in new_files:
        sid = clean_sheet_id((nf or {}).get("sheet_id"))
        positions = [
            i for i, s in enumerate(old_sheets)
            if sid and s == sid and i not in slot_new and i not in dropped
        ]
        if not positions:
            rest.append(nf)
            continue
        slot_new[positions[0]] = nf
        dropped.update(positions[1:])

    base: list[dict] = []
    for i, entry in enumerate(old_files):
        if i in dropped:
            continue
        base.append(slot_new.get(i, entry))
    replaced = sorted(i + 1 for i in (set(slot_new) | dropped))
    return base, rest, replaced


def _normalize_structured_data(order: Any) -> dict:
    """order.structured_data 를 dict 로 정규화한다(읽기 전용·deepcopy 로 원본 격리).

    :param order: ``structured_data`` 속성을 갖는 주문 객체.
    :returns: dict(문자열이면 json 파싱, 실패·None 이면 ``{}``). 원본은 변경하지 않는다.
    """
    raw = getattr(order, "structured_data", None)
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return {}


def materialize_pending_snapshot(order: Any) -> list[dict]:
    """마법사 pending 을 전달용 스냅샷 목록으로 materialize 한다(순수·DB write 0).

    ``structured_data['drawing_wizard']['pending']`` (dict, sheet_id→entry)을 삽입 순서대로
    ``[{sheet_id, key, filename, at, sheet_name}]`` 로 변환한다. key 가 비었거나 항목이 dict
    가 아니면 방어적으로 건너뛴다. 원본 structured_data 는 변경하지 않으며 세션에 아무것도
    commit/flush 하지 않는다.

    :param order: ``structured_data`` 를 갖는 주문 객체.
    :returns: pending 스냅샷 목록(비어 있으면 ``[]``).
    """
    sd = _normalize_structured_data(order)
    dw = sd.get("drawing_wizard") if isinstance(sd, dict) else None
    pending = dw.get("pending") if isinstance(dw, dict) else None
    snapshot: list[dict] = []
    if not isinstance(pending, dict):
        return snapshot
    for sheet_id, entry in pending.items():
        if not isinstance(entry, dict):
            continue
        key = (entry.get("key") or "").strip()
        if not key:
            continue
        snapshot.append({
            "sheet_id": sheet_id,
            "key": key,
            "filename": entry.get("filename") or key.rsplit("/", 1)[-1],
            "at": entry.get("at") or "",
            "sheet_name": entry.get("sheet_name") or sheet_id,
        })
    return snapshot


def _is_drawing_key(order_id: int, key: str) -> bool:
    """key 가 해당 주문의 도면 경로인지 판정한다(실측/일반 첨부 유출 차단).

    도면 경로 = ``orders/<id>/drawing_wizard/`` · ``orders/<id>/drawing/`` ·
    ``orders/<id>/drawing_gateway/`` 접두. traversal(``..``)·절대경로(선행 ``/``)는 거부한다.
    """
    if not key or key.startswith("/") or ".." in key:
        return False
    prefixes = (
        f"orders/{order_id}/drawing_wizard/",
        f"orders/{order_id}/drawing_gateway/",
        f"orders/{order_id}/drawing/",
    )
    return key.startswith(prefixes)


def materialize_transfer_attachments(order_id: int, files: Any) -> list[dict]:
    """전달 대상 파일 참조를 도면 key 로 필터해 ``drawing_current_files`` 엔트리로 materialize.

    입력 각 항목 ``{key, filename?, sheet_id?}`` 중 **도면 key 경로**(``_is_drawing_key``)만
    통과시켜 ``{key, filename, view_url, download_url[, sheet_id]}`` 로 materialize 한다. 실측/일반/타 주문 첨부
    key 는 유출을 막기 위해 제외한다(construction_card drawing_current_files leak 함정).
    URL 은 same-origin(``/api/files/...``)으로만 만든다. DB 조회·commit/flush·version·event·
    outbox 없이 순수 계산만 한다.

    :param order_id: 대상 주문 id(도면 key 경로 격리 검증에 사용).
    :param files: ``[{key, filename?}]`` 후보 목록(dict 아닌 항목은 건너뜀).
    :returns: 도면 전달용 첨부 엔트리 목록(순서 유지, 비어 있으면 ``[]``).
    """
    out: list[dict] = []
    if not isinstance(files, (list, tuple)):
        return out
    for f in files:
        if not isinstance(f, dict):
            continue
        key = (f.get("key") or "").strip()
        if not _is_drawing_key(order_id, key):
            continue
        filename = (f.get("filename") or key.rsplit("/", 1)[-1]).strip()
        entry = {
            "key": key,
            "filename": filename,
            "view_url": f"/api/files/view/{key}",
            "download_url": f"/api/files/download/{key}",
        }
        # 마법사 시트 신원 — 다음 전달에서 같은 시트 옛 판을 찾는 축(replace_same_sheet_files).
        sheet_id = clean_sheet_id(f.get("sheet_id"))
        if sheet_id:
            entry["sheet_id"] = sheet_id
        out.append(entry)
    return out
