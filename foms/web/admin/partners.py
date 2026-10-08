"""PARTNER-02: 협력사 관리 화면(ADMIN 전용) — 협력사 · 협력사 계정 만들기/끄기.

협력사 계정은 여기서만 만든다. 일반 사용자 관리(``/admin/users``)의 역할 목록에는 PARTNER 가 없다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §5.3
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from db import get_db
from foms.services.partners.orgs import (
    PartnerAdminError,
    create_partner_org,
    create_partner_user,
    get_partner_user,
    list_partner_orgs_with_users,
    reset_partner_user_password,
    sales_owner_choices,
    update_partner_owner,
)
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required
from models import PartnerOrg


def _back():
    return redirect(url_for("admin.partners"))


def _org_or_none(db, org_id: int) -> PartnerOrg | None:
    return db.query(PartnerOrg).filter(PartnerOrg.id == org_id).first()


def _audit(db, message: str, action: str, target_type: str, target_id: int, **detail) -> None:
    log_access(message, session.get("user_id"), auto_commit=False, action=action,
               target_type=target_type, target_id=int(target_id), detail=detail or None, db=db)


@admin_bp.route("/admin/partners")
@login_required
@role_required(["ADMIN"])
def partners():
    db = get_db()
    return render_template(
        "admin/partners.html",
        rows=list_partner_orgs_with_users(db),
        owner_choices=sales_owner_choices(db),
    )


@admin_bp.route("/admin/partners", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_create():
    db = get_db()
    try:
        org = create_partner_org(
            db,
            name=request.form.get("name"),
            owner_user_id=request.form.get("owner_user_id"),
            biz_reg_no=request.form.get("biz_reg_no"),
            contact_name=request.form.get("contact_name"),
            contact_phone=request.form.get("contact_phone"),
        )
        _audit(db, f"협력사 추가: {org.name}", "PARTNER_ORG_CREATED", "partner_org", org.id)
        db.commit()
        flash(f"협력사 '{org.name}'를 만들었습니다.", "success")
    except PartnerAdminError as exc:
        db.rollback()
        flash(str(exc), "error")
    return _back()


@admin_bp.route("/admin/partners/<int:org_id>/owner", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_set_owner(org_id: int):
    db = get_db()
    org = _org_or_none(db, org_id)
    if org is None:
        flash("협력사를 찾을 수 없습니다.", "error")
        return _back()
    try:
        update_partner_owner(db, org, request.form.get("owner_user_id"))
        _audit(db, f"협력사 담당 변경: {org.name}", "PARTNER_ORG_OWNER_CHANGED", "partner_org", org.id,
               owner_user_id=org.owner_user_id)
        db.commit()
        flash("우리 쪽 담당 직원을 바꿨습니다.", "success")
    except PartnerAdminError as exc:
        db.rollback()
        flash(str(exc), "error")
    return _back()


@admin_bp.route("/admin/partners/<int:org_id>/toggle", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_toggle(org_id: int):
    db = get_db()
    org = _org_or_none(db, org_id)
    if org is None:
        flash("협력사를 찾을 수 없습니다.", "error")
        return _back()
    org.is_active = not org.is_active
    _audit(db, f"협력사 {'켬' if org.is_active else '끔'}: {org.name}", "PARTNER_ORG_TOGGLED",
           "partner_org", org.id, is_active=org.is_active)
    db.commit()
    flash(f"'{org.name}'을(를) {'켰' if org.is_active else '껐'}습니다.", "success")
    return _back()


@admin_bp.route("/admin/partners/<int:org_id>/users", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_add_user(org_id: int):
    db = get_db()
    org = _org_or_none(db, org_id)
    if org is None:
        flash("협력사를 찾을 수 없습니다.", "error")
        return _back()
    try:
        user = create_partner_user(
            db, org,
            username=request.form.get("username"),
            name=request.form.get("name"),
            password=request.form.get("password"),
        )
        _audit(db, f"협력사 계정 추가: {user.username} ({org.name})", "PARTNER_USER_CREATED", "user", user.id,
               partner_org_id=org.id)
        db.commit()
        flash(f"계정 '{user.username}'을(를) 만들었습니다.", "success")
    except PartnerAdminError as exc:
        db.rollback()
        flash(str(exc), "error")
    return _back()


@admin_bp.route("/admin/partners/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_toggle_user(user_id: int):
    db = get_db()
    user = get_partner_user(db, user_id)
    if user is None:
        flash("협력사 계정을 찾을 수 없습니다.", "error")
        return _back()
    user.is_active = not user.is_active
    _audit(db, f"협력사 계정 {'켬' if user.is_active else '끔'}: {user.username}", "PARTNER_USER_TOGGLED",
           "user", user.id, is_active=user.is_active)
    db.commit()
    flash(f"계정 '{user.username}'을(를) {'켰' if user.is_active else '껐'}습니다.", "success")
    return _back()


@admin_bp.route("/admin/partners/users/<int:user_id>/password", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def partners_reset_password(user_id: int):
    db = get_db()
    user = get_partner_user(db, user_id)
    if user is None:
        flash("협력사 계정을 찾을 수 없습니다.", "error")
        return _back()
    try:
        reset_partner_user_password(user, request.form.get("password"))
        _audit(db, f"협력사 계정 비밀번호 초기화: {user.username}", "PARTNER_USER_PASSWORD_RESET", "user", user.id)
        db.commit()
        flash(f"'{user.username}' 비밀번호를 바꿨습니다.", "success")
    except PartnerAdminError as exc:
        db.rollback()
        flash(str(exc), "error")
    return _back()
