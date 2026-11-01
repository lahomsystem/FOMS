"""협력사 공지 확인 JSON API(사용자 2026-11-02) — ``POST /api/partner/notices/<id>/ack``.

공지 창은 "확인"으로만 닫힌다. 자기 공지만 확인할 수 있다(남의 공지 · 없는 공지 404). 공지 · 확인 판정은
:mod:`foms.services.partners.notices`.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from db import get_db
from foms.services.auth.partner_scope import partner_required
from foms.services.partners.notices import ack_partner_notice, pending_partner_notices

partner_notice_bp = Blueprint("partner_notice", __name__, url_prefix="/api/partner")


@partner_notice_bp.route("/notices/<int:notice_id>/ack", methods=["POST"])
@partner_required
def ack_notice(notice_id: int):
    """공지 확인 — 남은 공지 목록을 돌려준다(창이 다음 공지를 띄운다)."""
    db = get_db()
    if not ack_partner_notice(db, g.current_user, notice_id):
        db.rollback()
        return jsonify({"success": False, "data": None, "error": "공지를 찾을 수 없습니다."}), 404
    db.commit()
    return jsonify({"success": True, "data": {"pending": pending_partner_notices(db, g.current_user)}, "error": None})
