"""백업 상황판 + 심박 수신 (RESTORE-GUI-01 F7).

화면(`/admin/backup-status`)은 ADMIN 전용 읽기 전용이고, 수신(`/api/ops/backup-heartbeat`)은
쿠키 세션이 없는 기계 요청이라 HMAC 서명으로 인증한다(ChannelTalk 웹훅과 같은 방식).

앱은 백업 보관소에 대한 권한을 갖지 않는다 — 이유는
:mod:`foms.services.backup_status` 모듈 docstring 참고.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from db import get_db
from foms.services.backup_status import (
    SIGNATURE_HEADER,
    STALE_AFTER_HOURS,
    evaluate_backup_status,
    load_heartbeat,
    record_heartbeat,
    verify_heartbeat_signature,
)
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required
from models import SecurityLog

ops_ingest_bp = Blueprint("ops_ingest", __name__, url_prefix="/api/ops")


@admin_bp.route("/admin/backup-status")
@login_required
@role_required(["ADMIN"])
def backup_status():
    """오프사이트 백업 상황판(읽기 전용).

    :return: ``admin/backup_status.html`` 렌더 결과.
    """
    status = evaluate_backup_status(load_heartbeat(get_db()))
    return render_template(
        "admin/backup_status.html",
        status=status,
        stale_after_hours=STALE_AFTER_HOURS,
    )


@ops_ingest_bp.route("/backup-heartbeat", methods=["POST"])
def backup_heartbeat():
    """백업 성공 심박을 받는다(기계 요청 — 쿠키 세션 없음, HMAC 서명이 인증).

    비밀이 설정되지 않았으면 어떤 요청도 통과하지 못한다(fail-closed). 검증 실패는 401 이며
    실패 사유를 나누어 알리지 않는다(존재/형식 탐색 방지).

    :return: JSON ``{'success': True, 'data': {...}}`` / 실패 시 401·400.
    """
    raw = request.get_data() or b""
    if not verify_heartbeat_signature(raw, request.headers.get(SIGNATURE_HEADER, "")):
        return jsonify({"success": False, "error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "invalid payload"}), 400

    db = get_db()
    stored = record_heartbeat(db, payload)
    # 심박도 감사 대상이다 — "백업이 성공했다"는 주장이 언제 들어왔는지 남아야, 나중에
    # 상황판이 초록이었던 근거를 되짚을 수 있다(행위자는 사람이 아니라 백업 파이프라인).
    db.add(SecurityLog(
        user_id=None,
        action="OPS_BACKUP_HEARTBEAT",
        target_type="OPS",
        message=f"오프사이트 백업 성공 심박 수신: {stored.get('key') or '-'}",
        detail={
            "finished_at": stored.get("finished_at"),
            "size_bytes": stored.get("size_bytes"),
            "toc_entries": stored.get("toc_entries"),
        },
    ))
    db.commit()
    return jsonify({"success": True, "data": stored})
