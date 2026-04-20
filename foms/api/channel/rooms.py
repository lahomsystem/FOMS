"""Chat room and order lookup routes."""

import datetime

from flask import jsonify, request, session
from sqlalchemy import and_, func, or_

from foms.web.auth import log_access, login_required
from foms.api.channel.blueprint import chat_bp
from db import get_db
from models import ChatAttachment, ChatMessage, ChatRoom, ChatRoomMember, Order, User
from wdcalculator_db import get_wdcalculator_db
from wdcalculator_models import Estimate, EstimateOrderMatch


def _load_estimates_for_order(order_id: int) -> list[dict]:
    """Return WDCalculator estimates linked to an order."""
    wd_db = get_wdcalculator_db()
    matches = wd_db.query(EstimateOrderMatch).filter(EstimateOrderMatch.order_id == order_id).all()
    estimate_list: list[dict] = []
    for match in matches:
        est = wd_db.query(Estimate).filter(Estimate.id == match.estimate_id).first()
        if est:
            estimate_list.append(est.to_dict())
    return estimate_list


@chat_bp.route("/api/chat/rooms", methods=["GET"])
@login_required
def api_chat_rooms_list():
    """채팅방 목록 조회 API."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        memberships = (
            db.query(ChatRoomMember, ChatRoom)
            .join(ChatRoom, ChatRoom.id == ChatRoomMember.room_id)
            .filter(ChatRoomMember.user_id == user_id)
            .order_by(func.coalesce(ChatRoom.updated_at, ChatRoom.created_at).desc())
            .all()
        )
        if not memberships:
            return jsonify({"success": True, "rooms": [], "count": 0})

        rooms = [room for _, room in memberships]
        room_ids = [room.id for room in rooms]
        member_by_room = {member.room_id: member for member, _ in memberships}

        latest_ts_subq = (
            db.query(
                ChatMessage.room_id.label("room_id"),
                func.max(ChatMessage.created_at).label("max_created_at"),
            )
            .filter(ChatMessage.room_id.in_(room_ids))
            .group_by(ChatMessage.room_id)
            .subquery()
        )
        latest_rows = (
            db.query(ChatMessage)
            .join(
                latest_ts_subq,
                and_(
                    ChatMessage.room_id == latest_ts_subq.c.room_id,
                    ChatMessage.created_at == latest_ts_subq.c.max_created_at,
                ),
            )
            .all()
        )
        last_message_by_room = {}
        for msg in latest_rows:
            prev = last_message_by_room.get(msg.room_id)
            if prev is None or (msg.created_at, msg.id) > (prev.created_at, prev.id):
                last_message_by_room[msg.room_id] = msg

        unread_rows = (
            db.query(
                ChatMessage.room_id.label("room_id"),
                func.count(ChatMessage.id).label("unread_count"),
            )
            .join(
                ChatRoomMember,
                and_(
                    ChatRoomMember.room_id == ChatMessage.room_id,
                    ChatRoomMember.user_id == user_id,
                ),
            )
            .filter(ChatMessage.room_id.in_(room_ids))
            .filter(
                or_(
                    ChatRoomMember.last_read_at.is_(None),
                    ChatMessage.created_at > ChatRoomMember.last_read_at,
                )
            )
            .group_by(ChatMessage.room_id)
            .all()
        )
        unread_count_by_room = {room_id: int(count or 0) for room_id, count in unread_rows}

        rooms_list = []
        for room in rooms:
            room_data = room.to_dict()
            room_data["last_message"] = last_message_by_room[room.id].to_dict() if room.id in last_message_by_room else None
            room_data["unread_count"] = unread_count_by_room.get(room.id, 0) if member_by_room.get(room.id) else 0
            rooms_list.append(room_data)
        return jsonify({"success": True, "rooms": rooms_list, "count": len(rooms_list)})
    except Exception as e:
        import traceback

        print(f"채팅방 목록 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms", methods=["POST"])
@login_required
def api_chat_rooms_create():
    """채팅방 생성 API."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        data = request.get_json()
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"success": False, "message": "채팅방 이름은 필수입니다."}), 400
        new_room = ChatRoom(
            name=name,
            description=data.get("description", "").strip(),
            order_id=data.get("order_id"),
            created_by=user_id,
        )
        db.add(new_room)
        db.commit()
        db.refresh(new_room)

        db.add(ChatRoomMember(room_id=new_room.id, user_id=user_id))
        member_ids = data.get("member_ids", [])
        if member_ids:
            for member_id in member_ids:
                if member_id != user_id:
                    db.add(ChatRoomMember(room_id=new_room.id, user_id=member_id))
        db.commit()
        log_access(f"채팅방 생성: {name} (ID: {new_room.id})", user_id)
        return jsonify({"success": True, "message": "채팅방이 생성되었습니다.", "room": new_room.to_dict()}), 201
    except Exception as e:
        db.rollback()
        import traceback

        print(f"채팅방 생성 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>", methods=["GET"])
@login_required
def api_chat_rooms_detail(room_id):
    """채팅방 상세 조회 API."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({"success": False, "message": "채팅방을 찾을 수 없습니다."}), 404

        member = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
            .first()
        )
        if not member:
            return jsonify({"success": False, "message": "채팅방에 접근할 권한이 없습니다."}), 403

        members = db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room_id).all()
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.room_id == room_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(50)
            .all()
        )

        messages_with_read_status = []
        for msg in messages:
            msg_dict = msg.to_dict()
            attachments = db.query(ChatAttachment).filter(ChatAttachment.message_id == msg.id).all()
            if attachments:
                msg_dict["attachments"] = [a.to_dict() for a in attachments]
            if msg.user_id == user_id:
                read_count = 0
                total_other_members = 0
                for room_member in members:
                    if room_member.user_id != user_id:
                        total_other_members += 1
                        last_read = getattr(room_member, "last_read_at", None)
                        msg_created = getattr(msg, "created_at", None)
                        if last_read is not None and msg_created is not None and last_read >= msg_created:
                            read_count += 1
                if total_other_members == 0:
                    msg_dict["read_status"] = "no_other_members"
                elif read_count == 0:
                    msg_dict["read_status"] = "unread"
                elif read_count == total_other_members:
                    msg_dict["read_status"] = "all_read"
                else:
                    msg_dict["read_status"] = "some_read"
                msg_dict["read_count"] = read_count
                msg_dict["total_other_members"] = total_other_members
            else:
                msg_dict["read_status"] = None
                msg_dict["read_count"] = 0
                msg_dict["total_other_members"] = 0
            messages_with_read_status.append(msg_dict)

        room_data = room.to_dict()
        room_data["members"] = [
            {
                **member_item.to_dict(),
                "user_name": member_item.user.name if member_item.user else None,
                "user_username": member_item.user.username if member_item.user else None,
            }
            for member_item in members
        ]
        room_data["messages"] = list(reversed(messages_with_read_status))

        if getattr(room, "order_id", None):
            try:
                order = db.query(Order).filter(Order.id == room.order_id).first()
                if order:
                    order_data = order.to_dict()
                    try:
                        order_data["estimates"] = _load_estimates_for_order(room.order_id)
                    except Exception as e:
                        print(f"견적 정보 조회 오류 (무시): {e}")
                        order_data["estimates"] = []
                    room_data["order"] = order_data
                else:
                    room_data["order"] = None
            except Exception as e:
                print(f"주문 정보 조회 오류 (무시): {e}")
                room_data["order"] = None
        else:
            room_data["order"] = None
        return jsonify({"success": True, "room": room_data})
    except Exception as e:
        import traceback

        print(f"채팅방 상세 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>", methods=["PUT"])
@login_required
def api_chat_rooms_update(room_id):
    """채팅방 수정 API."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        data = request.get_json()
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({"success": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if room.created_by != user_id:
            return jsonify({"success": False, "message": "채팅방을 수정할 권한이 없습니다."}), 403
        if "name" in data:
            room.name = data["name"].strip()
        if "description" in data:
            room.description = data.get("description", "").strip()
        if "order_id" in data:
            room.order_id = data.get("order_id")
        setattr(room, "updated_at", datetime.datetime.now())
        db.commit()
        log_access(f"채팅방 수정: {room.name} (ID: {room_id})", user_id)
        return jsonify({"success": True, "message": "채팅방이 수정되었습니다.", "room": room.to_dict()})
    except Exception as e:
        db.rollback()
        import traceback

        print(f"채팅방 수정 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>", methods=["DELETE"])
@login_required
def api_chat_rooms_delete(room_id):
    """채팅방 삭제 API."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({"success": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if room.created_by != user_id:
            return jsonify({"success": False, "message": "채팅방을 삭제할 권한이 없습니다."}), 403
        room_name = room.name
        db.delete(room)
        db.commit()
        log_access(f"채팅방 삭제: {room_name} (ID: {room_id})", user_id)
        return jsonify({"success": True, "message": "채팅방이 삭제되었습니다."})
    except Exception as e:
        db.rollback()
        import traceback

        print(f"채팅방 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>/members", methods=["POST"])
@login_required
def api_chat_rooms_add_member(room_id):
    """채팅방 멤버 추가 API."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        data = request.get_json()
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({"success": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        member = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
            .first()
        )
        if not member:
            return jsonify({"success": False, "message": "채팅방에 접근할 권한이 없습니다."}), 403
        new_member_id = data.get("user_id")
        if not new_member_id:
            return jsonify({"success": False, "message": "사용자 ID는 필수입니다."}), 400
        user = db.query(User).filter(User.id == new_member_id).first()
        if not user:
            return jsonify({"success": False, "message": "사용자를 찾을 수 없습니다."}), 404
        existing = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == new_member_id)
            .first()
        )
        if existing:
            return jsonify({"success": False, "message": "이미 채팅방 멤버입니다."}), 400
        new_member = ChatRoomMember(room_id=room_id, user_id=new_member_id)
        db.add(new_member)
        db.commit()
        log_access(f"채팅방 멤버 추가: 방 {room_id}, 사용자 {new_member_id}", user_id)
        return jsonify({"success": True, "message": "멤버가 추가되었습니다.", "member": new_member.to_dict()}), 201
    except Exception as e:
        db.rollback()
        import traceback

        print(f"멤버 추가 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>/members/<int:member_user_id>", methods=["DELETE"])
@login_required
def api_chat_rooms_remove_member(room_id, member_user_id):
    """채팅방 멤버 제거 API."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({"success": False, "message": "채팅방을 찾을 수 없습니다."}), 404
        if room.created_by != user_id and member_user_id != user_id:
            return jsonify({"success": False, "message": "멤버를 제거할 권한이 없습니다."}), 403
        member = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == member_user_id)
            .first()
        )
        if not member:
            return jsonify({"success": False, "message": "멤버를 찾을 수 없습니다."}), 404
        db.delete(member)
        db.commit()
        log_access(f"채팅방 멤버 제거: 방 {room_id}, 사용자 {member_user_id}", user_id)
        return jsonify({"success": True, "message": "멤버가 제거되었습니다."})
    except Exception as e:
        db.rollback()
        import traceback

        print(f"멤버 제거 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/orders/<int:order_id>", methods=["GET"])
@login_required
def api_chat_order_detail(order_id):
    """채팅방에서 사용할 주문 상세 정보 조회 API."""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
        order_data = order.to_dict()
        try:
            order_data["estimates"] = _load_estimates_for_order(order_id)
        except Exception as e:
            print(f"견적 정보 조회 오류 (무시): {e}")
            order_data["estimates"] = []
        return jsonify({"success": True, "order": order_data})
    except Exception as e:
        import traceback

        print(f"주문 정보 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/search-orders", methods=["GET"])
@login_required
def api_chat_search_orders():
    """채팅방에서 주문 검색 API."""
    try:
        db = get_db()
        query = request.args.get("q", "").strip()
        limit = int(request.args.get("limit", 20))
        if not query:
            return jsonify({"success": True, "orders": [], "count": 0})
        conds: list = [Order.customer_name.ilike(f"%{query}%")]
        if query.isdigit():
            conds.append(Order.id == int(query))
        orders = (
            db.query(Order)
            .filter(or_(*conds))
            .filter(Order.active_filter())
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )
        orders_list = [
            {
                "id": order.id,
                "customer_name": order.customer_name,
                "phone": order.phone,
                "address": order.address,
                "product": order.product,
                "status": order.status,
                "received_date": order.received_date,
                "created_at": (
                    lambda timestamp: timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None
                )(getattr(order, "created_at", None)),
            }
            for order in orders
        ]
        return jsonify({"success": True, "orders": orders_list, "count": len(orders_list)})
    except Exception as e:
        import traceback

        print(f"주문 검색 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500
