"""협력사 '도면 작업 중' 목록에 붙일 도면 썸네일.

도면팀이 마법사에서 저장한 전달 대기 PNG와, 그 단계에 이미 전달된 도면 그림만
보여 준다. 시트 JSON·다른 주문 키·그림이 아닌 파일은 넣지 않는다.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from foms.services.orders.drawing_transfer import _is_drawing_key
from models import Order

_STAGE = "도면 작업 중"
_MAX = 4
_IMAGE_EXT = frozenset({"png", "jpg", "jpeg", "webp", "gif"})


def attach_saved_drawing_thumbs(db, rows: list[dict[str, Any]]) -> None:
    """도면 작업 중 행에 ``drawing_thumbs`` · ``drawing_thumbs_more`` 를 채운다.

    그 단계가 아닌 행은 빈 목록이다. 주문 데이터는 그 단계 주문만 읽는다
    (전달 대기와 현재 도면 목록만).

    Args:
        db: SQLAlchemy 세션.
        rows: 목록에 실제로 그릴 행. 각 행을 그 자리에서 고친다.
    """
    ids = [row["id"] for row in rows if row.get("stage_label") == _STAGE]
    loaded = _load_drawing_bits(db, ids)
    for row in rows:
        bits = loaded.get(row["id"])
        thumbs, more = saved_drawing_thumbs(row["id"], bits) if bits else ([], 0)
        row["drawing_thumbs"] = thumbs
        row["drawing_thumbs_more"] = more


def saved_drawing_thumbs(order_id: int, bits: Any) -> tuple[list[dict[str, str]], int]:
    """저장분·전달분 그림 URL. 4장까지 보여주고 나머지는 장수로만 센다.

    Args:
        order_id: 키 경로가 이 주문인지 검사할 id.
        bits: ``{"pending": ..., "files": ...}``. dict 가 아니면 빈 결과.

    Returns:
        (썸네일 ``{url, label}`` 목록, 더 있는 장수).
    """
    data = bits if isinstance(bits, dict) else {}
    found = _collect(order_id, data.get("pending"), data.get("files"))
    return found[:_MAX], max(0, len(found) - _MAX)


def _load_drawing_bits(db, ids: list[int]) -> dict[int, dict[str, Any]]:
    """전달 대기·현재 도면만 읽는다. 시트 JSON 전체는 싣지 않는다."""
    if not ids:
        return {}
    rows = (
        db.query(
            Order.id,
            Order.structured_data["drawing_wizard"]["pending"].label("pending"),
            Order.structured_data["drawing_current_files"].label("files"),
        )
        .filter(Order.id.in_(ids))
        .all()
    )
    return {
        row.id: {"pending": _as_obj(row.pending), "files": _as_obj(row.files)}
        for row in rows
    }


def _as_obj(value: Any) -> Any:
    """JSON 추출이 문자열로 오면 객체로 되돌린다."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _collect(order_id: int, pending: Any, files: Any) -> list[dict[str, str]]:
    """대기 시트를 먼저, 이어서 전달된 도면. 같은 key 는 한 번만."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(pending, dict):
        for entry in pending.values():
            _push(out, seen, order_id, entry)
    if isinstance(files, list):
        for entry in files:
            _push(out, seen, order_id, entry)
    return out


def _push(out: list[dict[str, str]], seen: set[str], order_id: int, entry: Any) -> None:
    """그림이고 이 주문 도면 경로인 항목만 넣는다."""
    if not isinstance(entry, dict):
        return
    key = str(entry.get("key") or "").strip()
    name = str(entry.get("filename") or key.rsplit("/", 1)[-1])
    if not key or key in seen or not _is_drawing_key(order_id, key):
        return
    if not (_is_image(name) or _is_image(key)):
        return
    seen.add(key)
    label = str(entry.get("sheet_name") or name).strip()[:80] or "도면"
    out.append({"url": "/api/files/view/" + quote(key, safe="/"), "label": label})


def _is_image(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in _IMAGE_EXT
