"""
ERP 알림 API: 목록/배지/읽음/보관/확인 처리.

Phase 0B: 읽음/보관/확인의 SSOT 를 사용자별 `notification_user_states` 로 전환.
공유 `Notification` row 는 append-only 콘텐츠로만 취급하고, per-user 상태(read/archive/ack)
는 절대 공유 row 를 오염시키지 않는다. 모든 write 는 same-origin 헤더 guard 를 통과해야 한다.
"""
import datetime as dt_mod
from foms.services.error_logging import log_handled_exception
import json
import time
from urllib.parse import quote

from flask import Blueprint, g, jsonify, request, session
from sqlalchemy import func, or_

from foms.web.auth import login_required
from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_permissions import is_order_related_to_user
from foms.services.notifications.recipients import fan_out_new_notification
from foms.services.request_write_guard import require_same_origin_write
from db import get_db
from models import (
    Notification,
    NotificationDeliveryStatus,
    NotificationEvent,
    NotificationEventType,
    NotificationUserState,
    Order,
    User,
)

notifications_bp = Blueprint(
    "notifications",
    __name__,
    url_prefix="/erp/api",
)

# 알림 write 엔드포인트 공용 same-origin guard 헤더.
NOTIFICATION_WRITE_HEADER = "X-FOMS-Notification-Write"
notification_write_guard = require_same_origin_write(NOTIFICATION_WRITE_HEADER)

# 배지 카운트 캐시: user_id -> (count, expiry_unix_ts). DB 부하 감소용.
_badge_cache = {}
BADGE_CACHE_TTL_SECONDS = 30


def _invalidate_badge_cache(user_id):
    """사용자별 배지 캐시 무효화 (읽음 처리 시 호출)."""
    if user_id is not None:
        _badge_cache.pop(user_id, None)


def invalidate_badge_cache_for_user_ids(user_ids):
    """여러 사용자의 배지 캐시를 한 번에 무효화."""
    if not user_ids:
        return
    for uid in user_ids:
        try:
            _invalidate_badge_cache(int(uid))
        except (TypeError, ValueError):
            continue


def resolve_notification_recipient_user_ids(
    db, target_type=None, target_team=None, target_manager_name=None,
    target_user_ids=None, include_admin=True
):
    """알림 타겟 기준으로 수신 사용자 ID 집합을 계산.

    target_type:
      ALL  -> 전체 활성 사용자
      TEAM -> target_team 기준
      USER -> target_user_ids 직접 지정
      ORDER/None -> 기존 방식 (target_team/target_manager_name)
    """
    ttype = (target_type or "").strip().upper()

    if ttype == "ALL":
        return {int(r[0]) for r in db.query(User.id).filter(User.is_active == True).yield_per(500)}

    if ttype == "USER" and target_user_ids:
        out = set()
        for uid in target_user_ids:
            try:
                out.add(int(uid))
            except (TypeError, ValueError):
                continue
        return out

    team = (target_team or "").strip().upper()
    manager_name = (target_manager_name or "").strip()

    conditions = []
    if team:
        conditions.append(func.upper(User.team) == team)
    if manager_name:
        conditions.append(User.name == manager_name)
    if include_admin:
        conditions.append(User.role == "ADMIN")

    if not conditions:
        return set()

    return {int(r[0]) for r in db.query(User.id).filter(or_(*conditions), User.is_active == True).yield_per(500)}


def _ensure_dict(data):
    """JSONB 필드가 문자열로 오인될 경우를 대비해 딕셔너리로 변환."""
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return {}
    return {}


def _parse_history_time(value):
    """도면 히스토리 문자열 시각을 datetime으로 파싱."""
    if not value:
        return None
    try:
        return dt_mod.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _build_drawing_event_key(idx, event):
    """도면 이벤트 고유 키 생성."""
    action = str((event or {}).get("action") or "")
    at = str((event or {}).get("at") or (event or {}).get("transferred_at") or "")
    by_user_id = str((event or {}).get("by_user_id") or "")
    return f"{idx}:{action}:{at}:{by_user_id}"


def _resolve_notification_deep_link(notification, order_structured_data):
    """알림 -> 도면 작업실 상세 딥링크 정보(event_id/target_no/tab) 계산."""
    n_type = str(getattr(notification, "notification_type", "") or "").upper()
    oid = getattr(notification, "order_id", None)

    if n_type not in ("DRAWING_TRANSFERRED", "DRAWING_REVISION", "ERP_ORDER_CHANGED") or not oid:
        return {
            "deep_tab": None,
            "deep_event_id": None,
            "deep_target_no": None,
            "deep_link_url": None,
        }

    if n_type == "ERP_ORDER_CHANGED":
        target_action = "ERP_ORDER_CHANGED"
        target_tab = "timeline"
    elif n_type == "DRAWING_TRANSFERRED":
        target_action = "TRANSFER"
        target_tab = "timeline"
    else:
        target_action = "REQUEST_REVISION"
        target_tab = "requests"
    history = list(((order_structured_data or {}).get("drawing_transfer_history", []) or []))
    if not history:
        return {
            "deep_tab": target_tab,
            "deep_event_id": None,
            "deep_target_no": None,
            "deep_link_url": f"/erp/drawing-workbench/{oid}?tab={target_tab}",
        }

    created_at = getattr(notification, "created_at", None)
    matched = None
    matched_idx = -1
    best_score = None

    for idx, h in enumerate(history):
        if not isinstance(h, dict):
            continue
        if str(h.get("action") or "") != target_action:
            continue
        h_dt = _parse_history_time(h.get("at") or h.get("transferred_at"))
        if created_at and h_dt:
            score = abs((created_at - h_dt).total_seconds())
        else:
            score = float("inf")
        if best_score is None or score < best_score:
            best_score = score
            matched = h
            matched_idx = idx

    if matched is None:
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if isinstance(h, dict) and str(h.get("action") or "") == target_action:
                matched = h
                matched_idx = idx
                break

    deep_event_id = _build_drawing_event_key(matched_idx, matched) if matched is not None and matched_idx >= 0 else None
    deep_target_no = None
    if isinstance(matched, dict):
        try:
            deep_target_no = int(matched.get("target_drawing_number") or matched.get("replace_target_number") or 0) or None
        except (TypeError, ValueError):
            deep_target_no = None

    query_parts = [f"tab={target_tab}"]
    if deep_event_id:
        query_parts.append(f"event_id={quote(str(deep_event_id), safe='')}")
    if deep_target_no:
        query_parts.append(f"target_no={deep_target_no}")
    deep_link_url = f"/erp/drawing-workbench/{oid}?{'&'.join(query_parts)}"
    return {
        "deep_tab": target_tab,
        "deep_event_id": deep_event_id,
        "deep_target_no": deep_target_no,
        "deep_link_url": deep_link_url,
    }


def _record_event(
    db, notification_id, event_type, *,
    user_state_id=None, actor_user_id=None, recipient_user_id=None, metadata=None,
):
    """append-only `notification_events` 감사 로그 1건 추가(flush 는 호출자 책임)."""
    db.add(NotificationEvent(
        notification_id=notification_id,
        user_state_id=user_state_id,
        actor_user_id=actor_user_id,
        recipient_user_id=recipient_user_id,
        event_type=event_type,
        metadata_json=metadata,
    ))


def _owner_state(db, notification_id, user_id):
    """(notification_id, user_id) owner state row 조회. 없으면 None."""
    return (
        db.query(NotificationUserState)
        .filter(
            NotificationUserState.notification_id == notification_id,
            NotificationUserState.user_id == user_id,
        )
        .first()
    )


def _user_can_access_order_urgent(user, order):
    """긴급 호출(멘션/대상조회) 접근 권한: 주문 관련자이거나 ADMIN/MANAGER."""
    role = str(getattr(user, "role", "") or "").upper()
    if role in ("ADMIN", "MANAGER"):
        return True
    return is_order_related_to_user(order, user)


def _urgent_target_payload(u):
    """긴급 호출 대상 사용자 표시용 dict."""
    return {"id": u.id, "name": u.name, "team": u.team, "role": u.role}


@notifications_bp.route("/notifications", methods=["GET"])
@login_required
def api_notifications_list():
    """현재 사용자의 알림 목록 조회(user_states 기준). unread_only, limit 지원."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        user = getattr(g, "current_user", None)

        if not user:
            return jsonify({"success": False, "message": "사용자 정보를 찾을 수 없습니다."}), 404

        unread_only = request.args.get("unread_only", "false").lower() == "true"
        limit = int(request.args.get("limit", 20))

        query = (
            db.query(Notification, NotificationUserState)
            .join(
                NotificationUserState,
                NotificationUserState.notification_id == Notification.id,
            )
            .filter(
                NotificationUserState.user_id == user_id,
                NotificationUserState.archived_at.is_(None),
            )
        )
        if unread_only:
            query = query.filter(NotificationUserState.read_at.is_(None))

        query = query.order_by(Notification.created_at.desc()).limit(limit)
        rows = query.all()

        unread_count = (
            db.query(func.count(NotificationUserState.id))
            .filter(
                NotificationUserState.user_id == user_id,
                NotificationUserState.archived_at.is_(None),
                NotificationUserState.read_at.is_(None),
            )
            .scalar()
            or 0
        )

        order_ids = list({int(n.order_id) for (n, _s) in rows if n.order_id is not None})
        order_map = {}
        if order_ids:
            order_rows = db.query(Order.id, Order.structured_data).filter(Order.id.in_(order_ids)).all()  # perf-ok: order_ids from paginated notifications
            for oid, sd in order_rows:
                order_map[int(oid)] = _ensure_dict(sd)

        notif_payloads = []
        for n, state in rows:
            row = n.to_dict()
            # per-user 상태로 덮어쓰기: 공유 row 의 is_read/read_at 은 사용하지 않는다.
            row["is_read"] = state.read_at is not None
            row["read_at"] = format_datetime_kst(state.read_at)
            row["archived_at"] = format_datetime_kst(state.archived_at)
            row["ack_at"] = format_datetime_kst(state.ack_at)
            sd = order_map.get(n.order_id, {}) if n.order_id else {}
            deep = _resolve_notification_deep_link(n, sd)
            row.update(deep)
            notif_payloads.append(row)

        return jsonify({
            "success": True,
            "notifications": notif_payloads,
            "unread_count": int(unread_count),
        })
    except Exception as e:
        log_handled_exception()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/badge", methods=["GET"])
@login_required
def api_notifications_badge():
    """알림 배지 카운트(미읽음 user_states 수). 사용자별 30초 캐시로 DB 부하 완화."""
    try:
        user_id = session.get("user_id")
        if user_id is None:
            return jsonify({"success": True, "count": 0})

        now_ts = time.time()
        cached = _badge_cache.get(user_id)
        if cached is not None and cached[1] > now_ts:
            return jsonify({"success": True, "count": cached[0]})

        db = get_db()
        count = (
            db.query(func.count(NotificationUserState.id))
            .filter(
                NotificationUserState.user_id == user_id,
                NotificationUserState.archived_at.is_(None),
                NotificationUserState.read_at.is_(None),
            )
            .scalar()
            or 0
        )
        count = int(count)
        _badge_cache[user_id] = (count, now_ts + BADGE_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "count": count})
    except Exception:
        return jsonify({"success": True, "count": 0})


@notifications_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
@notification_write_guard
def api_notification_mark_read(notification_id):
    """알림 읽음 처리(owner state 기준). 없으면 404, 이미 읽음이면 no-op."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")

        state = _owner_state(db, notification_id, user_id)
        if not state:
            return jsonify({"success": False, "message": "알림을 찾을 수 없습니다."}), 404

        if state.read_at is None:
            now = dt_mod.datetime.now()
            state.read_at = now
            _record_event(
                db, notification_id, NotificationEventType.READ,
                user_state_id=state.id, actor_user_id=user_id, recipient_user_id=user_id,
            )
            # 호환 dual-write: USER 전용 소유 알림만 legacy 필드 갱신. 공유 row 는 금지.
            notification = db.query(Notification).filter(Notification.id == notification_id).first()
            if (
                notification is not None
                and notification.target_type == "USER"
                and notification.target_user_id == user_id
            ):
                notification.is_read = True
                notification.read_at = now
                notification.read_by_user_id = user_id

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({"success": True, "message": "알림을 읽음 처리했습니다."})
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/read-all", methods=["POST"])
@login_required
@notification_write_guard
def api_notifications_mark_all_read():
    """현재 사용자의 미읽음·미보관 user_states 전체 읽음 처리."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")

        base_filter = (
            NotificationUserState.user_id == user_id,
            NotificationUserState.read_at.is_(None),
            NotificationUserState.archived_at.is_(None),
        )
        rep_nid = (
            db.query(NotificationUserState.notification_id)
            .filter(*base_filter)
            .order_by(NotificationUserState.notification_id.desc())
            .first()
        )
        now = dt_mod.datetime.now()
        updated = (
            db.query(NotificationUserState)
            .filter(*base_filter)
            .update({NotificationUserState.read_at: now}, synchronize_session=False)
        )
        if updated and rep_nid is not None:
            _record_event(
                db, int(rep_nid[0]), NotificationEventType.READ,
                actor_user_id=user_id, recipient_user_id=user_id,
                metadata={"bulk": True, "count": int(updated)},
            )

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({"success": True, "message": f"{updated}개 알림을 읽음 처리했습니다.", "count": updated})
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/<int:notification_id>/archive", methods=["POST"])
@login_required
@notification_write_guard
def api_notification_archive(notification_id):
    """알림 보관 처리(owner state 기준). 목록에서 제거된다."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")

        state = _owner_state(db, notification_id, user_id)
        if not state:
            return jsonify({"success": False, "message": "알림을 찾을 수 없습니다."}), 404

        if state.archived_at is None:
            state.archived_at = dt_mod.datetime.now()
            _record_event(
                db, notification_id, NotificationEventType.ARCHIVE,
                user_state_id=state.id, actor_user_id=user_id, recipient_user_id=user_id,
            )

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({"success": True, "message": "알림을 보관했습니다."})
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/archive-all", methods=["POST"])
@login_required
@notification_write_guard
def api_notifications_archive_all():
    """현재 사용자의 미보관 user_states 전체 보관 처리."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")

        base_filter = (
            NotificationUserState.user_id == user_id,
            NotificationUserState.archived_at.is_(None),
        )
        rep_nid = (
            db.query(NotificationUserState.notification_id)
            .filter(*base_filter)
            .order_by(NotificationUserState.notification_id.desc())
            .first()
        )
        now = dt_mod.datetime.now()
        updated = (
            db.query(NotificationUserState)
            .filter(*base_filter)
            .update({NotificationUserState.archived_at: now}, synchronize_session=False)
        )
        if updated and rep_nid is not None:
            _record_event(
                db, int(rep_nid[0]), NotificationEventType.ARCHIVE,
                actor_user_id=user_id, recipient_user_id=user_id,
                metadata={"bulk": True, "count": int(updated)},
            )

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({"success": True, "message": f"{updated}개 알림을 보관했습니다.", "count": updated})
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/<int:notification_id>/ack", methods=["POST"])
@login_required
@notification_write_guard
def api_notification_ack(notification_id):
    """긴급(P0) 알림 확인(ack) 처리(owner state 기준). read 와 독립, idempotent."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")

        state = _owner_state(db, notification_id, user_id)
        if not state:
            return jsonify({"success": False, "message": "알림을 찾을 수 없습니다."}), 404

        if state.ack_at is None:
            state.ack_at = dt_mod.datetime.now()
            state.last_delivery_status = NotificationDeliveryStatus.ACK
            _record_event(
                db, notification_id, NotificationEventType.ACK,
                user_state_id=state.id, actor_user_id=user_id, recipient_user_id=user_id,
            )

        db.commit()
        _invalidate_badge_cache(user_id)
        return jsonify({"success": True, "message": "긴급 알림을 확인했습니다."})
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/delete-all", methods=["POST"])
@login_required
@notification_write_guard
def api_notifications_delete_all():
    """관리자 전용 - 공유 Notification row 하드 삭제(운영 정리용)."""
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")
        user = getattr(g, "current_user", None)

        if not user or str(getattr(user, "role", "") or "").upper() != "ADMIN":
            return jsonify({"success": False, "message": "권한이 없습니다."}), 403

        deleted = db.query(Notification).delete(synchronize_session="fetch")
        db.commit()
        _badge_cache.clear()
        return jsonify({"success": True, "message": f"{deleted}개 알림을 삭제했습니다.", "count": deleted})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/users/list", methods=["GET"])
@login_required
def api_users_list_for_mention():
    """동료 호출 대상 선택용 사용자 목록(ADMIN/MANAGER 전용)."""
    try:
        user = getattr(g, "current_user", None)
        if not user or str(getattr(user, "role", "") or "").upper() not in ("ADMIN", "MANAGER"):
            return jsonify({"success": False, "message": "권한이 없습니다."}), 403
        db = get_db()
        users = (
            db.query(User.id, User.name, User.team, User.role)
            .filter(User.is_active == True)
            .order_by(User.name)
            .limit(500)
            .all()
        )
        return jsonify({
            "success": True,
            "users": [
                {"id": u.id, "name": u.name, "team": u.team, "role": u.role}
                for u in users
            ],
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/orders/<int:order_id>/urgent-targets", methods=["GET"])
@login_required
def api_order_urgent_targets(order_id):
    """주문 문맥형 긴급 호출 후보 목록.

    호출자는 주문 관련자이거나 ADMIN/MANAGER 여야 한다(아니면 403 — sender 게이트).
    후보는 활성 사용자 전원(자기 자신·inactive 제외)이며, 팀 드롭다운 UI 가 등록 인원을
    팀별로 묶어 노출한다. 정렬은 팀 표시순(auth TEAMS SSOT)→이름순이고, 각 항목에
    team_label(팀 라벨, 팀 미등록/미상=기타)을 포함한다.
    """
    try:
        db = get_db()
        user_id = session.get("user_id")
        user = getattr(g, "current_user", None)
        if not user:
            return jsonify({"success": False, "message": "사용자 정보를 찾을 수 없습니다."}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        if not _user_can_access_order_urgent(user, order):
            return jsonify({"success": False, "message": "권한이 없습니다."}), 403

        # 팀 표시순·라벨은 auth 사용자관리와 동일한 TEAMS SSOT 를 따른다.
        # (지연 import 로 auth↔notifications 순환 의존 회피)
        from foms.web.auth import TEAMS

        # 활성 사용자 1회 조회(N+1 없음), 자기 자신만 제외하고 등록 인원 전체를 후보로 연다.
        # 운영 규모상 상한 500 으로 bound(users/list 와 동일 상한).
        active_users = db.query(User).filter(User.is_active == True).limit(500).all()  # perf-ok: bounded active-user candidate scan
        targets = [
            {**_urgent_target_payload(u), "team_label": TEAMS.get(u.team) or "기타"}
            for u in active_users
            if u.id != user_id
        ]
        # 팀 미등록/미상(=기타)은 TEAMS 뒤로, 같은 팀은 이름순. JS 는 이 순서대로 그룹핑한다.
        team_index = {code: idx for idx, code in enumerate(TEAMS)}
        targets.sort(key=lambda t: (
            team_index.get(t["team"], len(team_index)),
            str(t["name"] or ""),
        ))

        return jsonify({"success": True, "targets": targets})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/notifications/send", methods=["POST"])
@login_required
@notification_write_guard
def api_notifications_send():
    """관리자/매니저 전용 - 공지/알림 발송.

    target_type:
      ALL  -> 전체 사용자에게 레코드 복제
      TEAM -> 특정 팀 대상 사용자에게 레코드 복제
      USER -> target_user_ids 목록에 레코드 복제
    """
    db = None
    try:
        db = get_db()
        user_id = session.get("user_id")
        user = getattr(g, "current_user", None)
        if not user or user.role not in ("ADMIN", "MANAGER"):
            return jsonify({"success": False, "message": "권한이 없습니다."}), 403

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        message = (data.get("message") or "").strip()
        is_urgent = bool(data.get("is_urgent"))
        target_type = (data.get("target_type") or "ALL").strip().upper()
        target_team_val = (data.get("target_team") or "").strip().upper() or None
        target_user_ids_raw = data.get("target_user_ids") or []
        order_id_val = data.get("order_id")

        if not title:
            return jsonify({"success": False, "message": "제목을 입력해주세요."}), 400
        if target_type not in ("ALL", "TEAM", "USER"):
            return jsonify({"success": False, "message": "대상 유형이 올바르지 않습니다."}), 400
        if target_type == "TEAM" and not target_team_val:
            return jsonify({"success": False, "message": "팀을 선택해주세요."}), 400
        if target_type == "USER" and not target_user_ids_raw:
            return jsonify({"success": False, "message": "사용자를 선택해주세요."}), 400

        ntype = "URGENT_ANNOUNCEMENT" if is_urgent else "ANNOUNCEMENT"

        recipient_ids = resolve_notification_recipient_user_ids(
            db,
            target_type=target_type,
            target_team=target_team_val,
            target_user_ids=target_user_ids_raw,
            include_admin=True,
        )
        if not recipient_ids:
            return jsonify({"success": False, "message": "수신 대상자가 없습니다."}), 400

        # 전체/팀/개인 발송 시 수신자별 레코드 생성. 각 레코드는 해당 수신자 전용이므로
        # target_type 을 'USER' 로 저장해, 브리핑 보드 등에서 target_user_id 로 1건만 조회되게 함.
        stored_target_type = "USER" if target_type in ("ALL", "TEAM", "USER") else target_type
        created_notif_ids = []
        for uid in recipient_ids:
            notif = Notification(
                order_id=int(order_id_val) if order_id_val else None,
                notification_type=ntype,
                target_type=stored_target_type,
                target_team=target_team_val,
                target_user_id=uid,
                is_urgent=is_urgent,
                title=title,
                message=message or None,
                created_by_user_id=user_id,
                created_by_name=str(user.name or ""),
                is_read=False,
            )
            db.add(notif)
            db.flush()
            # 같은 트랜잭션에서 수신자 state + 'created' 이벤트 생성(고아 알림 방지).
            fan_out_new_notification(db, notif, actor_user_id=user_id)
            created_notif_ids.append(notif.id)

        db.commit()

        # 커밋 후 Web Push enqueue(worker 가 커밋된 row 를 재조회하도록 commit 이후 실행).
        from foms.services.notifications.push_sender import enqueue_push_for_notification
        for nid in created_notif_ids:
            enqueue_push_for_notification(nid, db=db)

        invalidate_badge_cache_for_user_ids(recipient_ids)

        from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
        payload = {
            "title": title,
            "message": message,
            "urgent": is_urgent,
            "notification_type": ntype,
            "order_id": int(order_id_val) if order_id_val else None,
            "created_by_name": str(user.name or ""),
        }
        realtime_sent = emit_erp_notification_to_users(list(recipient_ids), payload)

        msg = f"{len(recipient_ids)}명에게 알림을 발송했습니다."
        if realtime_sent < len(recipient_ids) and len(recipient_ids) > 0:
            msg += f" (실시간 전송: {realtime_sent}명 - 일부는 새로고침 시 확인)"

        return jsonify({
            "success": True,
            "message": msg,
            "sent_count": len(recipient_ids),
            "realtime_sent": realtime_sent,
        })
    except Exception as e:
        log_handled_exception()
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "message": str(e)}), 500


@notifications_bp.route("/orders/<int:order_id>/urgent-mention", methods=["POST"])
@login_required
@notification_write_guard
def api_order_urgent_mention(order_id):
    """주문 상세에서 특정 동료를 긴급 호출(멘션).

    Body: { target_user_id: int, message: str (선택, 최대 500자) }
    호출자는 주문 관련자이거나 ADMIN/MANAGER 여야 한다(sender 게이트). 대상은 활성
    사용자면 누구나 가능 — 대상 목록(urgent-targets)이 등록 인원 전체를 여는 것과 계약 일치.
    """
    db = None
    try:
        db = get_db()
        sender_id = session.get("user_id")
        sender = db.query(User).filter(User.id == sender_id).first()
        if not sender:
            return jsonify({"success": False, "message": "사용자 정보를 찾을 수 없습니다."}), 404

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        if not _user_can_access_order_urgent(sender, order):
            return jsonify({"success": False, "message": "이 주문의 긴급 호출 권한이 없습니다."}), 403

        data = request.get_json(silent=True) or {}
        target_uid_raw = data.get("target_user_id")
        if not target_uid_raw:
            return jsonify({"success": False, "message": "호출 대상을 선택해주세요."}), 400

        try:
            target_uid = int(target_uid_raw)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "올바르지 않은 사용자입니다."}), 400

        if target_uid == sender_id:
            return jsonify({"success": False, "message": "자기 자신은 호출할 수 없습니다."}), 400

        target_user = db.query(User).filter(User.id == target_uid).first()
        if not target_user or not target_user.is_active:
            return jsonify({"success": False, "message": "대상 사용자를 찾을 수 없습니다."}), 404

        # 대상 게이트 없음: 등록 인원 전체를 호출 대상으로 열어둔다(urgent-targets 계약과 일치).
        # sender 게이트(위)와 자기 자신·비활성 차단만 유지한다.
        msg = (data.get("message") or "").strip()
        if len(msg) > 500:
            return jsonify({"success": False, "message": "메시지는 500자 이내여야 합니다."}), 400
        customer = order.customer_name or f"#{order_id}"
        title = f"[긴급 멘션] {sender.name}님이 #{order_id} {customer} 주문에서 호출했습니다"

        notif = Notification(
            order_id=order_id,
            notification_type="URGENT_MENTION",
            target_type="USER",
            target_user_id=target_uid,
            is_urgent=True,
            title=title,
            message=msg or None,
            created_by_user_id=sender_id,
            created_by_name=str(sender.name or ""),
            is_read=False,
        )
        db.add(notif)
        db.flush()
        fan_out_new_notification(db, notif, actor_user_id=sender_id)
        db.commit()

        invalidate_badge_cache_for_user_ids([target_uid])

        from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users
        payload = {
            "title": title,
            "message": msg or "",
            "urgent": True,
            "notification_type": "URGENT_MENTION",
            "order_id": order_id,
            "created_by_name": str(sender.name or ""),
        }
        emit_erp_notification_to_users([target_uid], payload)
        _record_event(
            db, notif.id, NotificationEventType.REALTIME_ATTEMPTED,
            actor_user_id=sender_id, recipient_user_id=target_uid,
        )
        db.commit()

        # 커밋 후 Web Push enqueue. queue 미가용이면 os_push 미보장을 응답으로 노출.
        from foms.services.notifications.push_sender import enqueue_push_for_notification
        push_result = enqueue_push_for_notification(notif.id, db=db)
        os_push = "queued" if push_result.get("enqueued") else (
            "not_guaranteed"
            if push_result.get("reason") == "queue_unavailable"
            else push_result.get("reason")
        )

        return jsonify({
            "success": True,
            "message": f"{target_user.name}님에게 긴급 멘션을 보냈습니다.",
            "os_push": os_push,
            "push_reason": push_result.get("reason"),
        })
    except Exception as e:
        log_handled_exception()
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = [
    "notifications_bp",
    "invalidate_badge_cache_for_user_ids",
    "resolve_notification_recipient_user_ids",
    "api_notifications_list",
    "api_notifications_badge",
    "api_notification_mark_read",
    "api_notifications_mark_all_read",
    "api_notification_archive",
    "api_notifications_archive_all",
    "api_notification_ack",
    "api_notifications_delete_all",
    "api_users_list_for_mention",
    "api_order_urgent_targets",
    "api_notifications_send",
    "api_order_urgent_mention",
]
