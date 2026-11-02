"""FOMS 공지사항 관리자 화면(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5) — ADMIN · MANAGER.

화면 네 개(목록 · 쓰기 · 고치기 · 확인 현황)는 뼈대만 서버가 그리고, 값은 작은 스크립트
(``static/js/admin/notices-*.js``)가 JSON API(``/api/admin/notices``, 설계서 §4 — :mod:`foms.api.notices`)
에서 읽고 보낸다. 고치기 화면만 지금 값을 서버가 ``data-notice`` 로 실어 준다(목록 API 에 본문 · 받는 쪽이 없다).

긴급 알림(빨간 전체 화면)은 ``/admin/notifications`` 그대로 따로 둔다.
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, render_template

from db import get_db
from foms.services.datetime_kst import format_datetime_kst
from foms.services.notices.audience import audience_label
from foms.services.notices.images import MAX_IMAGES, admin_items
from foms.web.auth import login_required, role_required
from models import Notice

notices_admin_bp = Blueprint("notices_admin", __name__)

#: 기존 ``/admin/notifications`` 와 같은 권한.
ADMIN_ROLES = ["ADMIN", "MANAGER"]

#: JSON API 접두(설계서 §4 블루프린트 ``notices_admin_api``).
API_BASE = "/api/admin/notices"

#: 화면 주소 접두(스크립트가 ``/<id>/edit`` · ``/<id>/status`` 를 붙인다).
PAGE_BASE = "/admin/notices"

#: ``<input type="datetime-local">`` 값 모양(한국 시각).
_INPUT_DT_FORMAT = "%Y-%m-%dT%H:%M"


def _kst_input_value(value: Any) -> str:
    """UTC naive 시각을 datetime-local 칸 값(한국 시각 ``YYYY-MM-DDTHH:MM``)으로. 없으면 빈 글."""
    return format_datetime_kst(value, _INPUT_DT_FORMAT) or ""


def _load_live_notice(notice_id: int) -> Any:
    """지우지 않은 공지 한 줄. 없거나 지운 것이면 404."""
    notice = get_db().get(Notice, notice_id)
    if notice is None or getattr(notice, "deleted_at", None) is not None:
        abort(404)
    return notice


def _int_list(values: Any) -> list[int]:
    """JSONB 목록을 정수 목록으로(틀린 값은 버린다)."""
    out: list[int] = []
    for value in values or []:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


def notice_form_state(notice: Any) -> dict[str, Any]:
    """고치기 화면에 미리 채울 값(설계서 §4 페이로드 모양 그대로).

    :param notice: ``Notice`` 한 줄.
    :return: ``{id, title, body, audience:{...}, display_mode, pinned, starts_at, ends_at, images:[...]}`` — 사진은
        저장 항목 + 관리자 미리보기 주소(설계서 §8).
    """
    return {
        "id": notice.id,
        "title": notice.title or "",
        "body": notice.body or "",
        "audience": {
            "staff_all": bool(notice.audience_staff_all),
            "staff_teams": [str(code) for code in (notice.audience_staff_teams or [])],
            "partner_all": bool(notice.audience_partner_all),
            "partner_org_ids": _int_list(notice.audience_partner_org_ids),
        },
        "display_mode": notice.display_mode or "POPUP",
        "pinned": bool(notice.pinned),
        "starts_at": _kst_input_value(notice.starts_at),
        "ends_at": _kst_input_value(notice.ends_at),
        "images": admin_items(notice.images),
    }


@notices_admin_bp.route("/admin/notices")
@login_required
@role_required(ADMIN_ROLES)
def notices_list():
    """공지 목록(값은 스크립트가 ``GET /api/admin/notices`` 로 읽는다)."""
    return render_template("admin/notices/list.html", api_base=API_BASE, page_base=PAGE_BASE)


@notices_admin_bp.route("/admin/notices/new")
@login_required
@role_required(ADMIN_ROLES)
def notice_new():
    """공지 쓰기."""
    return render_template("admin/notices/form.html", api_base=API_BASE, page_base=PAGE_BASE,
                           mode="new", notice_state=None, max_images=MAX_IMAGES)


@notices_admin_bp.route("/admin/notices/<int:notice_id>/edit")
@login_required
@role_required(ADMIN_ROLES)
def notice_edit(notice_id: int):
    """공지 고치기(지금 값을 ``data-notice`` 로 싣는다)."""
    notice = _load_live_notice(notice_id)
    state = notice_form_state(notice)
    get_db().rollback()  # 읽기만 — 트랜잭션을 닫는다
    return render_template("admin/notices/form.html", api_base=API_BASE, page_base=PAGE_BASE,
                           mode="edit", notice_state=state, max_images=MAX_IMAGES)


@notices_admin_bp.route("/admin/notices/<int:notice_id>/status")
@login_required
@role_required(ADMIN_ROLES)
def notice_status(notice_id: int):
    """확인 현황(사람 목록은 스크립트가 ``GET /api/admin/notices/<id>/status`` 로 읽는다)."""
    notice = _load_live_notice(notice_id)
    title = notice.title or ""
    label = audience_label(notice)
    get_db().rollback()
    return render_template("admin/notices/status.html", api_base=API_BASE, page_base=PAGE_BASE,
                           notice_id=notice_id, notice_title=title, audience_label=label)
