"""협력사 파일 올리기 도우미 — ``foms/api/partner/__init__.py`` 500줄 래칫 때문에 나눴다(라우트는 그대로 거기)."""
from __future__ import annotations

from foms.api.files.common import parse_attachment_item_index
from models import Order


def item_index_for_upload(order: Order, raw: str | None, category: str) -> tuple[int | None, str | None]:
    """품목 실측 사진의 품목 번호(우리 직원 업로드와 같은 ``item_index``). 없으면 공통 사진.

    Returns:
        ``(item_index, None)`` 또는 ``(None, 오류 문구)``.
    """
    ok, item_index, _err = parse_attachment_item_index(raw)
    if not ok:
        return None, "품목 번호가 올바르지 않습니다."
    if item_index is None:
        return None, None
    if category != "measurement":
        return None, "품목에는 실측 사진만 붙일 수 있습니다."
    items = (order.structured_data or {}).get("items")
    if not isinstance(items, list) or item_index >= len(items):
        return None, "없는 품목입니다. 화면을 새로고침한 뒤 다시 올려 주세요."
    return item_index, None
