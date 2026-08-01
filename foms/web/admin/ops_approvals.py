"""고위험 ops 승인 UI (OPS-APPROVAL-00, §2.1 line 205).

active ADMIN 이 공용 WRITE-GUARD(CSRF+Origin before_request) 뒤에서 자기 session +
current password 재인증으로 PENDING approval 을 APPROVED 로 전이한다. operator 는
approver 를 지정할 수 없고, approver identity 와 principal version 은 오직 session/DB
에서만 취한다. 화면에는 operation/state/expiry 와 **masked** hash 만 노출한다(값/secret/
PII0).
"""
from __future__ import annotations

from flask import abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash

from db import get_db
from models import OpsApprovalRequest
from foms.services.datetime_kst import now_utc_naive
from foms.services.security.ops_approval import approve_request, ApprovalConsumeError
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required


def _mask(value: str | None) -> str:
    """hash/식별자를 앞 8자만 남기고 마스킹(값 노출 방지)."""
    if not value:
        return "-"
    return f"{value[:8]}…" if len(value) > 8 else value


def _masked_detail(row: OpsApprovalRequest) -> dict:
    """UI 에 노출할 masked detail(값/secret/PII 없음)."""
    return {
        "approval_id": row.id,
        "operation_type": row.operation_type,
        "state": row.state,
        "scope_sha256_masked": _mask(row.scope_sha256),
        "artifact_sha256_masked": _mask(row.artifact_sha256),
        "expected_version": row.expected_version,
        "expected_generation": row.expected_generation,
        "expires_at": row.expires_at,
        "approved_at": row.approved_at,
    }


@admin_bp.route("/admin/ops/approvals/<approval_id>", methods=["GET", "POST"])
@login_required
@role_required(["ADMIN"])
def ops_approval_review(approval_id: str):
    """고위험 ops 승인 상세 + 재인증 승인.

    GET: masked detail + 재인증 폼. POST: current password 재인증 후 PENDING→APPROVED.
    WRITE-GUARD 공용 가드가 CSRF/Origin 을 이미 검증한다(핸들러 실행 전 차단).
    """
    db = get_db()
    row = (
        db.query(OpsApprovalRequest)
        .filter(OpsApprovalRequest.id == approval_id)
        .one_or_none()
    )
    if row is None:
        # 존재하지 않는/불투명 id → 404 (열거 방지).
        abort(404)

    if request.method == "GET":
        return render_template("admin/ops_approval_review.html", detail=_masked_detail(row))

    # --- POST: 재인증 승인 ---
    user = g.current_user  # login_required + role_required(ADMIN) 통과
    current_password = request.form.get("current_password") or ""
    if not check_password_hash(user.password, current_password):
        log_access(f"ops 승인 재인증 실패 (approval={approval_id})", user.id)
        flash("현재 비밀번호가 일치하지 않습니다.", "error")
        return render_template("admin/ops_approval_review.html", detail=_masked_detail(row)), 403

    now = now_utc_naive()
    try:
        # PENDING→APPROVED 전이는 ops_approval.approve_request 가 SSOT(잠금+재확인+
        # principal version snapshot). approver identity 는 세션 user.id 로만 전달.
        approve_request(db, approval_id=approval_id, approver_user_id=user.id, now=now)
        db.commit()
    except ApprovalConsumeError as exc:
        db.rollback()
        flash(f"승인할 수 없습니다: {exc}", "error")
        refreshed = (
            db.query(OpsApprovalRequest)
            .filter(OpsApprovalRequest.id == approval_id)
            .one_or_none()
        )
        detail = _masked_detail(refreshed) if refreshed is not None else _masked_detail(row)
        return render_template("admin/ops_approval_review.html", detail=detail), 409
    # 예기치 못한 예외는 그대로 전파한다 — teardown_appcontext(close_db) 가 scoped
    # 세션을 rollback 한다(광범위 except 로 삼키지 않음).

    log_access(f"ops 승인 완료 (approval={approval_id}, op={row.operation_type})", user.id)
    flash("승인되었습니다.", "success")
    return redirect(url_for("admin.ops_approval_review", approval_id=approval_id))
