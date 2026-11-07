"""프리랜서 설정 JSON API(설계서 FCOMM-01 §2.3 · §4.1 · §9 · J5).

- ``GET  /api/admin/sales-freelancers`` — 설정 version · 프리랜서 목록(계정 이름 · 지금 요율 · 이력) · 추가할 수 있는 계정.
  회계팀 · 관리자(:func:`~foms.services.settlement_channel_access.is_accounting_or_admin`).
- ``POST /api/admin/sales-freelancers`` ``{user_id, match_name, start_month, tax_type, active, rate?, version}`` — 추가 · 고치기.
  같은 트랜잭션에서 그 사람의 주문 ↔ 프리랜서 연결을 다시 맞춘다(:func:`~foms.services.sales_commission.links.resync_freelancer_links`).
  켜진 프리랜서로 저장하면 같은 트랜잭션에서 채팅방 회원을 풀고 옛 알림을 숨긴다(겹 5 —
  :func:`~foms.services.auth.freelancer_designation.apply_designation_side_effects`), 커밋 뒤 열린 실시간 연결을 끊는다.
- ``POST /api/admin/sales-freelancers/<user_id>/rates`` ``{effective_month, lahom_bp, haud_bp, personal_bp, version}``
  — 요율 한 줄 더하기.

쓰기는 ADMIN 만(정책 manifest ``ADMIN_OPS`` + 핸들러가 한 번 더 본다), 공용 CSRF · Origin 가드 뒤. version 이 다르면 409.
감사는 ``SecurityLog`` 한 줄(요율 숫자 대신 바뀐 칸 이름 · 적용 달). 응답은 ``{"success", "data", "error"}``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.notifications import invalidate_badge_cache_for_user_ids
from foms.services.auth.freelancer_designation import apply_designation_side_effects, disconnect_realtime
from foms.services.datetime_kst import get_today_kst
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.sales_commission.links import resync_freelancer_links
from foms.services.sales_commission.settings import (
    FREELANCER_ROLES,
    TAX_TYPES,
    FreelancerSettingsError,
    add_rate,
    load_settings,
    save_freelancer,
)
from foms.services.settlement_channel_access import is_accounting_or_admin
from models import SecurityLog, User

logger = logging.getLogger(__name__)

sales_freelancers_admin_api_bp = Blueprint("sales_freelancers_admin_api", __name__)

_PREFIX = "/api/admin/sales-freelancers"
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str):
    return jsonify({"success": False, "data": None, "error": error}), status


def _user() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요해요.")
    return user, None


def _reader():
    user, denied = _user()
    if denied:
        return None, denied
    if not is_accounting_or_admin(user) or getattr(user, "partner_org_id", None) is not None:
        return None, _fail(403, "회계팀과 관리자만 볼 수 있어요.")
    return user, None


def _admin():
    user, denied = _user()
    if denied:
        return None, denied
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role != "ADMIN" or getattr(user, "partner_org_id", None) is not None:
        return None, _fail(403, "관리자만 고칠 수 있어요.")
    return user, None


def _body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _state(db) -> dict[str, Any]:
    version, configs = load_settings(db)
    month = get_today_kst().strftime("%Y-%m")
    users = {u.id: u for u in db.query(User).filter(User.id.in_(list(configs))).all()} if configs else {}
    freelancers = []
    for uid, config in sorted(configs.items(), key=lambda kv: kv[1].match_name):
        user = users.get(uid)
        current = config.rate_for(month)
        freelancers.append({
            **config.as_dict(),
            "name": user.name if user is not None else "",
            "username": user.username if user is not None else "",
            "user_active": bool(user.is_active) if user is not None else False,
            "current_rate": current.as_dict() if current is not None else None,
        })
    staff = db.query(User).filter(User.is_active.is_(True), User.role.in_(tuple(FREELANCER_ROLES)),
                                  User.partner_org_id.is_(None)).order_by(User.name).all()
    candidates = [{"user_id": u.id, "name": u.name, "username": u.username}
                  for u in staff if normalize_team(u.team) == "SALES" and u.id not in configs]
    return {"version": version, "month": month, "tax_types": list(TAX_TYPES),
            "freelancers": freelancers, "candidates": candidates}


@sales_freelancers_admin_api_bp.route(_PREFIX, methods=["GET"], endpoint="list_freelancers")
def api_list_freelancers():
    """설정 한 덩어리(읽기만)."""
    _actor, denied = _reader()
    if denied:
        return denied
    db = get_db()
    data = _state(db)
    db.rollback()
    return _ok(data)


@sales_freelancers_admin_api_bp.route(_PREFIX, methods=["POST"], endpoint="save_freelancer")
def api_save_freelancer():
    """프리랜서 추가 · 고치기 — 감사 한 줄(바뀐 칸 이름만)."""
    actor, denied = _admin()
    if denied:
        return denied
    body = _body()
    actor_id = int(actor.id)
    db = get_db()
    try:
        version, config, changed = save_freelancer(db, body.get("user_id"), body, base_version=body.get("version"),
                                                   actor_user_id=actor_id)
        # 3단계 보기 범위: 맞출 이름 · 켜고 끔이 바뀌면 그 사람의 주문 연결을 같은 트랜잭션에서 다시 맞춘다(알림 없음).
        links = resync_freelancer_links(db, config.user_id)
        # 겹 5: 켜진 프리랜서면 채팅방 회원 해제 · 옛 알림 숨김(연결을 다시 맞춘 뒤 — 남길 알림 판정이 새 연결을 본다).
        side = (apply_designation_side_effects(db, config.user_id, actor_id) if config.active
                else {"chat_memberships_removed": 0, "notifications_hidden": 0})
        db.add(SecurityLog(
            user_id=actor_id, action="SALES_FREELANCER_SAVED", target_type="user", target_id=config.user_id,
            message=f"프리랜서 설정 저장: {config.match_name}",
            detail={"user_id": config.user_id, "version": version, "changed": changed,
                    "links_added": links["added"], "links_removed": links["removed"], **side},
        ))
        db.commit()
    except FreelancerSettingsError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[SALES_FREELANCER] 설정 저장 실패 user=%s", body.get("user_id"))
        return _fail(500, _SAVE_FAILED)
    if config.active:
        invalidate_badge_cache_for_user_ids([config.user_id])  # 숨긴 알림이 종 숫자에 남지 않게
        disconnect_realtime(config.user_id)  # 이미 들어가 있던 채팅방 방송을 끊는다(다시 연결하면 개인 방만)
    data = _state(db)
    db.rollback()
    return _ok(data)


@sales_freelancers_admin_api_bp.route(f"{_PREFIX}/<int:user_id>/rates", methods=["POST"], endpoint="add_rate")
def api_add_rate(user_id: int):
    """요율 한 줄 더하기 — 감사 한 줄(적용 달만, 요율 숫자는 설정 이력에 남는다)."""
    actor, denied = _admin()
    if denied:
        return denied
    body = _body()
    actor_id = int(actor.id)
    db = get_db()
    try:
        version, config, rate = add_rate(db, user_id, body, base_version=body.get("version"), actor_user_id=actor_id)
        db.add(SecurityLog(
            user_id=actor_id, action="SALES_FREELANCER_RATE_ADDED", target_type="user", target_id=config.user_id,
            message=f"프리랜서 요율 추가: {config.match_name} {rate.effective_month}부터",
            detail={"user_id": config.user_id, "version": version, "effective_month": rate.effective_month},
        ))
        db.commit()
    except FreelancerSettingsError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[SALES_FREELANCER] 요율 저장 실패 user=%s", user_id)
        return _fail(500, _SAVE_FAILED)
    data = _state(db)
    db.rollback()
    return _ok(data)
