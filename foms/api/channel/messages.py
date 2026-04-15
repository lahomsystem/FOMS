"""Chat message, search, and user routes."""

import datetime

from flask import jsonify, request, session
from sqlalchemy import or_

from foms.web.auth import login_required
from foms.api.channel.blueprint import chat_bp
from foms.api.channel.utils import schedule_chat_thumbnail_generation
from db import get_db
from models import ChatAttachment, ChatMessage, ChatRoom, ChatRoomMember, Order, User


@chat_bp.route("/api/chat/search", methods=["GET"])
@login_required
def api_chat_search():
    """전체 채팅 검색 API."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        query = request.args.get("q", "").strip()
        limit = int(request.args.get("limit", 50))
        if not query or len(query) < 2:
            return jsonify({"success": True, "results": [], "count": 0})

        user_rooms = (
            db.query(ChatRoom.id)
            .join(ChatRoomMember, ChatRoom.id == ChatRoomMember.room_id)
            .filter(ChatRoomMember.user_id == user_id)
            .subquery()
        )

        results = []
        messages = (
            db.query(ChatMessage)
            .join(user_rooms, ChatMessage.room_id == user_rooms.c.id)
            .filter(ChatMessage.content.ilike(f"%{query}%"))
            .limit(limit)
            .all()
        )
        for msg in messages:
            room = db.query(ChatRoom).filter(ChatRoom.id == msg.room_id).first()
            results.append(
                {
                    "type": "message",
                    "room_id": msg.room_id,
                    "room_name": room.name if room else None,
                    "message_id": msg.id,
                    "content": msg.content,
                    "user_name": msg.user.name if msg.user else None,
                    "created_at": (
                        lambda timestamp: timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None
                    )(getattr(msg, "created_at", None)),
                }
            )

        rooms = (
            db.query(ChatRoom)
            .join(user_rooms, ChatRoom.id == user_rooms.c.id)
            .filter(or_(ChatRoom.name.ilike(f"%{query}%"), ChatRoom.description.ilike(f"%{query}%")))
            .limit(limit)
            .all()
        )
        for room in rooms:
            if not any(result.get("room_id") == room.id and result.get("type") == "room" for result in results):
                results.append(
                    {
                        "type": "room",
                        "room_id": room.id,
                        "room_name": room.name,
                        "description": room.description,
                        "created_at": (
                            lambda timestamp: timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None
                        )(getattr(room, "created_at", None)),
                    }
                )

        orders = (
            db.query(Order)
            .join(ChatRoom, Order.id == ChatRoom.order_id)
            .join(user_rooms, ChatRoom.id == user_rooms.c.id)
            .filter(
                or_(
                    Order.customer_name.ilike(f"%{query}%"),
                    Order.phone.ilike(f"%{query}%"),
                    Order.address.ilike(f"%{query}%"),
                )
            )
            .limit(limit)
            .all()
        )
        for order in orders:
            room = db.query(ChatRoom).filter(ChatRoom.order_id == order.id).first()
            if room and not any(result.get("room_id") == room.id and result.get("type") == "order" for result in results):
                results.append(
                    {
                        "type": "order",
                        "room_id": room.id,
                        "room_name": room.name,
                        "order_id": order.id,
                        "customer_name": order.customer_name,
                        "phone": order.phone,
                        "address": order.address,
                        "product": order.product,
                    }
                )

        seen = set()
        unique_results = []
        for result in results:
            key = (result["type"], result.get("room_id"), result.get("message_id", 0), result.get("order_id", 0))
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
        return jsonify({"success": True, "results": unique_results[:limit], "count": len(unique_results)})
    except Exception as e:
        import traceback

        print(f"채팅 검색 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/rooms/<int:room_id>/mark-read", methods=["POST"])
@login_required
def api_chat_mark_read(room_id):
    """메시지 읽음 상태 업데이트 API."""
    db = get_db()
    try:
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
            return jsonify({"success": False, "message": "채팅방 멤버가 아닙니다."}), 403
        setattr(member, "last_read_at", datetime.datetime.now())
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        import traceback

        print(f"읽음 상태 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/users", methods=["GET"])
@login_required
def api_chat_users_list():
    """채팅 초대용 사용자 목록 조회 API."""
    try:
        db = get_db()
        current_user_id = session.get("user_id")
        users = (
            db.query(User)
            .filter(User.is_active == True, User.id != current_user_id)
            .order_by(User.name)
            .all()
        )
        users_list = [{"id": user.id, "name": user.name, "username": user.username, "role": user.role} for user in users]
        return jsonify({"success": True, "users": users_list})
    except Exception as e:
        import traceback

        print(f"사용자 목록 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/messages", methods=["POST"])
@login_required
def api_chat_send_message():
    """메시지 전송 API (Socket.IO 폴백용)."""
    db = get_db()
    try:
        user_id = session.get("user_id")
        data = request.get_json()
        room_id = data.get("room_id")
        message_type = data.get("message_type", "text")
        content = data.get("content", "").strip()
        file_info = data.get("file_info")
        if not room_id:
            return jsonify({"success": False, "message": "채팅방 ID는 필수입니다."}), 400
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
        new_message = ChatMessage(
            room_id=room_id,
            user_id=user_id,
            message_type=message_type,
            content=content if message_type == "text" else None,
            file_info=file_info if message_type != "text" else None,
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)

        if file_info and isinstance(file_info, dict):
            attachment = ChatAttachment(
                message_id=new_message.id,
                filename=file_info.get("filename", ""),
                file_type=file_info.get("file_type", "file"),
                file_size=file_info.get("size", 0),
                storage_key=file_info.get("key", ""),
                storage_url=file_info.get("url", ""),
                thumbnail_url=file_info.get("thumbnail_url"),
            )
            db.add(attachment)
            db.commit()
            atype = getattr(attachment, "file_type", None)
            thumb = getattr(attachment, "thumbnail_url", None)
            skey = getattr(attachment, "storage_key", None) or ""
            if atype == "image" and not thumb and skey:
                schedule_chat_thumbnail_generation(skey)

        user = db.query(User).filter(User.id == user_id).first()
        message_data = new_message.to_dict()
        if user:
            message_data["user_name"] = user.name
            message_data["user_username"] = user.username
        attachments = db.query(ChatAttachment).filter(ChatAttachment.message_id == new_message.id).all()
        if attachments:
            message_data["attachments"] = [attachment.to_dict() for attachment in attachments]
        setattr(room, "updated_at", datetime.datetime.now())
        db.commit()
        return jsonify({"success": True, "message": message_data})
    except Exception as e:
        db.rollback()
        import traceback

        print(f"메시지 전송 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500


@chat_bp.route("/api/chat/messages/<int:message_id>", methods=["GET"])
@login_required
def api_chat_get_message(message_id):
    """단일 메시지 조회 API."""
    try:
        db = get_db()
        user_id = session.get("user_id")
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if not message:
            return jsonify({"success": False, "message": "메시지를 찾을 수 없습니다."}), 404
        member = (
            db.query(ChatRoomMember)
            .filter(ChatRoomMember.room_id == message.room_id, ChatRoomMember.user_id == user_id)
            .first()
        )
        if not member:
            return jsonify({"success": False, "message": "권한이 없습니다."}), 403
        message_data = message.to_dict()
        user = db.query(User).filter(User.id == message.user_id).first()
        if user:
            message_data["user_name"] = user.name
        attachments = db.query(ChatAttachment).filter(ChatAttachment.message_id == message.id).all()
        if attachments:
            message_data["attachments"] = [attachment.to_dict() for attachment in attachments]
        return jsonify({"success": True, "message": message_data})
    except Exception as e:
        import traceback

        print(f"메시지 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(e)}), 500
