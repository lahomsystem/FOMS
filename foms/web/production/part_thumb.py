"""생산 파트 도면 카드 작은 그림 길 — 설계서 §15.6 '작은 그림 길'(P15-5).

``GET /erp/production/parts/thumb/<order_id>?key=`` — 확정 도면 한 장의 긴 변 720px JPEG(품질 85).

* 왜 새 길인가: 지금 그림 길(``/api/files/view/<key>``)은 ``no-store`` 302 라 카드를 다시 그릴 때마다 앱 요청 + R2 원본 전체
  내려받기가 다시 난다(§15.2 ④). key 는 올릴 때마다 새 이름이라 내용이 안 바뀌므로 작은 그림은 오래 캐시해도 된다.
* 문지기: 생산 첫 화면을 볼 수 있는 사람(:func:`can_view_production_home`) + 그 주문 읽기 범위(:func:`user_can_read_order`) +
  key 가 그 주문 **지금** 확정 도면 안(교체된 옛 key · 남의 주문 key 는 404) + 그림 확장자만(그 밖 404 → 카드는 파일 표).
* 만들기: 처음 요청 때 원본을 읽어 **흰 바탕에 얹고**(투명 칸이 검정이 되는 함정 — ``storage.py`` 의 RGB 바로 바꾸기를 쓰지
  않는 까닭) 긴 변 720px 로 줄여 원본 옆 ``pthumb720_<이름>.jpg`` 로 R2 에 한 번 저장한다. 그 뒤로는 저장본 바이트.
  로컬 저장소는 비공개 저장을 받지 않으므로(``put_private_bytes``) 매번 만든다(개발용).
* 응답 ``Cache-Control: private, max-age=2592000, immutable`` — 같은 기기는 장마다 처음 한 번만 서버에 온다.

``dashboard.py`` 와 같은 Blueprint(``erp_production_page``)에 라우트만 더한다 — ``foms/web/production/__init__.py`` 가 import.
"""

from __future__ import annotations

import io
import posixpath
from typing import Any, Optional

from flask import Response, abort, g, request

from db import get_db
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_board import is_part_thumb_image
from foms.services.storage import get_storage
from foms.web.auth import login_required
from foms.web.production.dashboard import erp_production_page_bp
from models import Order

#: 작은 그림 긴 변(px) · JPEG 품질 · 저장 이름 접두.
PART_THUMB_LONG_EDGE = 720
PART_THUMB_QUALITY = 85
PART_THUMB_PREFIX = "pthumb720_"
#: key 가 올릴 때마다 새 이름이라 내용이 안 바뀐다 — 30일 · 다시 묻지 않음.
PART_THUMB_CACHE_CONTROL = "private, max-age=2592000, immutable"


def part_thumb_key(key: str) -> str:
    """원본 key → 작은 그림 저장 key(원본 옆 ``pthumb720_<원본 이름>.jpg``).

    원본 이름을 통째로 넣는다(확장자까지) — 같은 폴더의 ``a.png`` 와 ``a.jpg`` 가 한 작은 그림을 나눠 쓰지 않게.
    """
    folder, name = posixpath.split(key)
    thumb = f"{PART_THUMB_PREFIX}{name}.jpg"
    return posixpath.join(folder, thumb) if folder else thumb


def render_part_thumb(raw: bytes) -> bytes:
    """원본 그림 바이트 → 흰 바탕 · 긴 변 720px · 품질 85 JPEG 바이트.

    Args:
        raw: 원본 그림 바이트(PNG 투명 칸 · 팔레트 · EXIF 회전 포함).

    Returns:
        JPEG 바이트.

    Raises:
        OSError: 그림으로 읽을 수 없을 때(PIL ``UnidentifiedImageError`` 포함).
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as source:
        if source.format == "JPEG":
            source.draft("RGB", (PART_THUMB_LONG_EDGE * 2, PART_THUMB_LONG_EDGE * 2))  # 큰 사진은 줄여 읽는다
        image = ImageOps.exif_transpose(source).convert("RGBA")
    image.thumbnail((PART_THUMB_LONG_EDGE, PART_THUMB_LONG_EDGE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", image.size, (255, 255, 255))
    canvas.paste(image, mask=image.getchannel("A"))  # 투명 칸 = 흰색(검정이 되지 않게)
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=PART_THUMB_QUALITY, optimize=True)
    return out.getvalue()


def _current_entry(order: Order, key: str) -> Optional[dict[str, Any]]:
    """그 주문 지금 확정 도면 안의 항목(없으면 None — 교체된 옛 key · 남의 주문 key)."""
    for entry in resolve_final_drawing_files(order.structured_data or {}):
        if entry.get("key") == key:
            return entry
    return None


def _thumb_bytes(key: str) -> Optional[bytes]:
    """저장된 작은 그림을 쓰고, 없으면 원본에서 만들어 한 번 저장한다. 원본이 없거나 그림이 아니면 None."""
    storage = get_storage()
    thumb_key = part_thumb_key(key)
    if storage.object_exists(thumb_key):
        cached = storage.read_file_bytes(thumb_key)
        if cached:
            return cached
    raw = storage.read_file_bytes(key)
    if not raw:
        return None
    try:
        data = render_part_thumb(raw)
    except (OSError, ValueError):
        return None
    storage.put_private_bytes(thumb_key, data, "image/jpeg")  # 로컬 저장소 · 저장 실패면 다음에 다시 만든다
    return data


@erp_production_page_bp.route('/production/parts/thumb/<int:order_id>')
@login_required
def erp_production_part_thumb(order_id: int):
    """도면 카드 작은 그림(긴 변 720px JPEG). 볼 수 없는 사람 403, 지금 확정 도면이 아니거나 그림이 아니면 404."""
    user = getattr(g, 'current_user', None)
    if not can_view_production_home(user):
        abort(403)
    order = (
        get_db().query(Order)
        .filter(Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True))
        .first()
    )
    if order is None:
        abort(404)
    if not user_can_read_order(user, order):
        abort(403)
    key = (request.args.get('key') or '').strip()
    entry = _current_entry(order, key) if key else None
    if entry is None or not is_part_thumb_image(entry):
        abort(404)
    data = _thumb_bytes(key)
    if data is None:
        abort(404)
    response = Response(data, mimetype='image/jpeg')
    response.headers['Cache-Control'] = PART_THUMB_CACHE_CONTROL
    return response
