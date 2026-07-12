"""QR 코드 생성(B4) handler for the canonical orders blueprint.

`GET /api/orders/<id>/qr.svg` — 주문 모바일 상세 절대 URL을 segno(pure-python)로
QR 인코딩해 SVG(image/svg+xml)로 반환한다. 라벨 인쇄·현장 스캔 진입에 쓰인다.
로그인 필요, 캐시는 private 1시간(주문별 URL은 불변이라 재검증 부하 절감).
"""

from __future__ import annotations

import io
import logging

import segno
from flask import Response, url_for

from db import get_db
from models import Order

logger = logging.getLogger(__name__)

_CACHE_CONTROL = "private, max-age=3600"


def build_order_mobile_url(order_id: int) -> str:
    """주문 모바일 상세 절대 URL(_external)을 반환한다."""
    return url_for(
        "erp_dashboard.erp_order_mobile_detail", order_id=order_id, _external=True
    )


def render_order_qr_svg(order_id: int) -> Response:
    """주문 모바일 상세 URL을 QR 인코딩한 SVG 응답. 주문이 없으면 404.

    반환: image/svg+xml Response(Cache-Control private 1h) 또는 404 text/plain.
    """
    db = get_db()
    exists = db.query(Order.id).filter(Order.id == order_id).first()
    if not exists:
        return Response("order not found", status=404, mimetype="text/plain")

    qr = segno.make(build_order_mobile_url(order_id), error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=6, border=2, dark="#111111")

    resp = Response(buffer.getvalue(), mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = _CACHE_CONTROL
    return resp


__all__ = ["build_order_mobile_url", "render_order_qr_svg"]
