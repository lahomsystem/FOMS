"""협력사 단가표 JSON API — ADMIN 전용(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.1 · §6).

접두 ``/api/admin/partners/<org_id>/price-lists``:

- ``GET ""`` 판 목록 + 지금 판(ACTIVE) 전체 · ``GET /<id>`` 판 하나(옛 판 보기).
- ``POST /import`` 단가표 HTML(multipart ``file`` 또는 JSON ``html``) → 브랜드마다 판 초안. **저장하지 않는다**
  (화면에 띄우기만 — 저장해야 새 판이 된다).
- ``POST ""`` 새 판 저장 ``{sheet, label, effective_from, base_id}`` → 지금 판은 RETIRED, 새 판 ACTIVE.
  ``base_id`` 가 지금 판이 아니면 409(그 사이 다른 판이 저장됨). 감사 한 줄 ``PARTNER_PRICE_LIST_SAVED``.

미인증 401 · ADMIN 아님 403(JSON). 쓰기는 공용 CSRF · Origin 가드와 쓰기 정책 엔진(``ADMIN_OPS``) 뒤.
응답은 ``{"success", "data", "error"}``. 판정 · 저장은 :mod:`foms.services.partners.price_list`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.partners.price_list import (
    MAX_HTML_BYTES,
    PriceListConflict,
    PriceListError,
    active_price_list,
    import_sheets,
    list_versions,
    save_price_list,
    version_summary,
)
from models import PartnerOrg, PartnerPriceList, SecurityLog, User

logger = logging.getLogger(__name__)

partner_price_list_api_bp = Blueprint("partner_price_list_api", __name__, url_prefix="/api/admin/partners")

_SAVE_FAILED = "저장하지 못했습니다. 잠시 뒤 다시 해 주세요."


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str, errors: Optional[list[str]] = None):
    body = {"success": False, "data": {"errors": errors} if errors else None, "error": error}
    return jsonify(body), status


def _admin() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    """켜진 ADMIN(본사 직원)만 — 아니면 401 · 403."""
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요합니다.")
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role != "ADMIN" or getattr(user, "partner_org_id", None) is not None:
        return None, _fail(403, "관리자만 쓸 수 있습니다.")
    return user, None


def _org(db, org_id: int) -> Optional[PartnerOrg]:
    return db.query(PartnerOrg).filter(PartnerOrg.id == org_id).first()


def _detail(row: PartnerPriceList, names: dict[int, str]) -> dict[str, Any]:
    return {**version_summary(row, names), "sheet": row.sheet, "rules": row.rules or {}}


def _names(db, rows: list[PartnerPriceList]) -> dict[int, str]:
    ids = {r.created_by for r in rows if r.created_by}
    if not ids:
        return {}
    return {u.id: u.name or u.username for u in db.query(User).filter(User.id.in_(ids)).all()}


@partner_price_list_api_bp.route("/<int:org_id>/price-lists", methods=["GET"], endpoint="list_price_lists")
def api_list_price_lists(org_id: int):
    """판 목록 + 지금 판 전체."""
    _actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    org = _org(db, org_id)
    if org is None:
        return _fail(404, "협력사를 찾을 수 없습니다.")
    rows = list_versions(db, org_id)
    names = _names(db, rows)
    active = next((r for r in rows if r.status == "ACTIVE"), None)
    return _ok({"org": {"id": org.id, "name": org.name},
                "versions": [version_summary(r, names) for r in rows],
                "active": _detail(active, names) if active else None})


@partner_price_list_api_bp.route("/<int:org_id>/price-lists/<int:list_id>", methods=["GET"], endpoint="get_price_list")
def api_get_price_list(org_id: int, list_id: int):
    """판 하나(옛 판 보기)."""
    _actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    row = db.query(PartnerPriceList).filter(PartnerPriceList.id == list_id,
                                             PartnerPriceList.partner_org_id == org_id).first()
    if row is None:
        return _fail(404, "단가표 판을 찾을 수 없습니다.")
    return _ok(_detail(row, _names(db, [row])))


@partner_price_list_api_bp.route("/<int:org_id>/price-lists/import", methods=["POST"], endpoint="import_price_list")
def api_import_price_list(org_id: int):
    """단가표 HTML → 브랜드마다 판 초안(저장 안 함). 지금 판이 있으면 같은 이름 줄은 같은 열쇠."""
    _actor, denied = _admin()
    if denied:
        return denied
    db = get_db()
    if _org(db, org_id) is None:
        return _fail(404, "협력사를 찾을 수 없습니다.")
    upload = request.files.get("file")
    if upload is not None:
        raw = upload.read(MAX_HTML_BYTES + 1)
        try:
            html = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return _fail(400, "UTF-8 로 저장한 HTML 파일이 아닙니다.")
    else:
        body = request.get_json(silent=True)
        html = body.get("html") if isinstance(body, dict) else None
    current = active_price_list(db, org_id)
    try:
        data = import_sheets(html, current=current.sheet if current else None)
    except PriceListError as exc:
        return _fail(400, exc.errors[0], exc.errors)
    return _ok(data)


@partner_price_list_api_bp.route("/<int:org_id>/price-lists", methods=["POST"], endpoint="save_price_list")
def api_save_price_list(org_id: int):
    """새 판 저장 — 지금 판은 RETIRED, 새 판 ACTIVE(감사 한 줄)."""
    actor, denied = _admin()
    if denied:
        return denied
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    db = get_db()
    try:
        row = save_price_list(db, org_id, body.get("sheet"), label=body.get("label"),
                              effective_from=body.get("effective_from"), base_id=body.get("base_id"),
                              user_id=actor.id)
        db.add(SecurityLog(
            user_id=actor.id, action="PARTNER_PRICE_LIST_SAVED", target_type="partner_price_list",
            target_id=int(row.id), message=f"협력사 단가표 저장: {row.label} ({row.version}판)",
            detail={"partner_org_id": org_id, "version": row.version, "effective_from": row.effective_from.isoformat()},
        ))
        db.commit()
    except PriceListConflict as exc:
        db.rollback()
        return _fail(409, exc.errors[0])
    except PriceListError as exc:
        db.rollback()
        return _fail(400, exc.errors[0], exc.errors)
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[PRICE_LIST] 단가표 저장 실패 org=%s", org_id)
        return _fail(500, _SAVE_FAILED)
    return _ok(_detail(row, _names(db, [row])), 201)
