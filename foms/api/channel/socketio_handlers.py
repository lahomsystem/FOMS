"""채팅 SocketIO 이벤트 핸들러 등록.

방 들어가기 · 입력 중 · 보내기 · 읽음은 :mod:`foms.services.chat_room_access` 한 곳에서 판정한다 — 개인 알림 방
``user_<id>`` 는 본인만(연결 때 서버가 넣는다), 채팅방은 회원만, 켜진 프리랜서는 채팅 이벤트를 모두 못 쓴다
(설계서 FCOMM-01 §6.4 · §6.3 겹 5, D19). 시험: tests/security/test_socket_room_membership.py
"""
import datetime
from foms.services.error_logging import log_handled_exception
from flask import session, request
from flask_socketio import emit, join_room, leave_room
from db import get_db
from models import ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment, User
from foms.api.channel.utils import schedule_chat_thumbnail_generation
from foms.services.auth.partner_scope import is_partner_user
from foms.services.chat_room_access import (
    DENY_LOGIN,
    chat_member_fanout_ids,
    chat_room_denial,
    user_room,
)


def _session_user(user_id):
    """세션 user_id 의 사용자 행(없으면 None)."""
    return get_db().query(User).filter(User.id == user_id).first()


def _room_value(data):
    """이벤트 본문의 방 값(본문이 dict 가 아니면 None)."""
    return data.get('room_id') if isinstance(data, dict) else None


def _chat_access(user_id, room_value):
    """채팅 이벤트 판정 → ``(room_id, None)`` 허용 / ``(None, 이유)`` 거부."""
    return chat_room_denial(get_db(), _session_user(user_id), room_value)


def register_chat_socketio_handlers(socketio):
    """채팅 관련 SocketIO 이벤트 핸들러 등록."""
    @socketio.on('connect')
    def handle_connect():
        """클라이언트 연결 이벤트"""
        user_id = session.get('user_id')
        user = _session_user(user_id) if user_id else None
        if user_id and (user is None or not user.is_active):
            # INACTIVE-SESSION-01: 없거나 비활성(퇴사 처리)된 계정은 연결을 받지 않는다.
            # Socket.IO 는 before_request(_set_current_user)를 거치지 않으므로 여기서 따로 막는다.
            return False
        if user_id and is_partner_user(user):
            # PARTNER-01: 협력사 계정은 실시간 연결(사내 채팅·알림)을 쓰지 않는다. Socket.IO 는
            # Flask before_request 문지기를 거치지 않으므로 여기서 따로 막는다.
            return False
        if user_id:
            print(f"[SocketIO] 사용자 {user_id} 연결됨")
            join_room(user_room(user_id))
            print(f"[SocketIO] 사용자 {user_id}가 자신의 전용 room에 입장: user_{user_id}")
            emit('connected', {'user_id': user_id, 'message': '연결되었습니다.'})
        else:
            print("[SocketIO] 인증되지 않은 연결 시도")
            return False  # 연결 거부

    @socketio.on('disconnect')
    def handle_disconnect():
        """클라이언트 연결 해제 이벤트"""
        user_id = session.get('user_id')
        if user_id:
            print(f"[SocketIO] 사용자 {user_id} 연결 해제됨")

    @socketio.on('join_room')
    def handle_join_room(data):
        """방 입장 — 내 개인 알림 방, 또는 내가 회원인 채팅방만."""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': DENY_LOGIN})
            return
        room_value = _room_value(data)
        if not room_value:
            return
        if str(room_value) == user_room(user_id):
            join_room(user_room(user_id))  # 연결 때 이미 들어가 있다 — 다시 들어가도 같다
            emit('joined_room', {'room_id': room_value, 'user_id': user_id})
            return
        room_id, reason = _chat_access(user_id, room_value)
        if reason:
            emit('error', {'message': reason})
            return
        join_room(str(room_id))
        print(f"[SocketIO] 사용자 {user_id}가 채팅방 {room_id}에 입장")
        emit('joined_room', {'room_id': room_value, 'user_id': user_id})
        socketio.emit('user_joined', {
            'room_id': room_value,
            'user_id': user_id
        }, room=str(room_id))

    @socketio.on('leave_room')
    def handle_leave_room(data):
        """채팅방 퇴장 — 나가기는 늘 된다. 방 사람들에게 알리는 것은 회원일 때만."""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': DENY_LOGIN})
            return
        room_value = _room_value(data)
        if not room_value or str(room_value) == user_room(user_id):
            return  # 개인 알림 방은 나가지 않는다(나가면 실시간 알림이 끊긴다)
        leave_room(str(room_value))
        print(f"[SocketIO] 사용자 {user_id}가 채팅방 {room_value}에서 퇴장")
        emit('left_room', {'room_id': room_value, 'user_id': user_id})
        room_id, reason = _chat_access(user_id, room_value)
        if reason is None:
            socketio.emit('user_left', {
                'room_id': room_value,
                'user_id': user_id
            }, room=str(room_id))

    @socketio.on('send_message')
    def handle_send_message(data):
        """메시지 전송"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': DENY_LOGIN})
            return
        db = get_db()
        try:
            data = data if isinstance(data, dict) else {}
            room_id = data.get('room_id')
            message_type = data.get('message_type', 'text')
            content = data.get('content', '').strip()
            file_info = data.get('file_info')
            if not room_id:
                emit('error', {'message': '채팅방 ID는 필수입니다.'})
                return
            room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
            if not room:
                emit('error', {'message': '채팅방을 찾을 수 없습니다.'})
                return
            room_id, reason = _chat_access(user_id, room_id)
            if reason:
                emit('error', {'message': reason})
                return
            new_message = ChatMessage(
                room_id=room_id,
                user_id=user_id,
                message_type=message_type,
                content=content if message_type == 'text' else None,
                file_info=file_info if message_type != 'text' else None
            )
            db.add(new_message)
            db.commit()
            db.refresh(new_message)
            if file_info and isinstance(file_info, dict):
                attachment = ChatAttachment(
                    message_id=new_message.id,
                    filename=file_info.get('filename', ''),
                    file_type=file_info.get('file_type', 'file'),
                    file_size=file_info.get('size', 0),
                    storage_key=file_info.get('key', ''),
                    storage_url=file_info.get('url', ''),
                    thumbnail_url=file_info.get('thumbnail_url')
                )
                db.add(attachment)
                db.commit()
                if attachment.file_type == 'image' and not attachment.thumbnail_url and attachment.storage_key:
                    schedule_chat_thumbnail_generation(attachment.storage_key)
            user = db.query(User).filter(User.id == user_id).first()
            message_data = new_message.to_dict()
            if user:
                message_data['user_name'] = user.name
                message_data['user_username'] = user.username
            attachments = db.query(ChatAttachment).filter(
                ChatAttachment.message_id == new_message.id
            ).all()
            if attachments:
                message_data['attachments'] = [a.to_dict() for a in attachments]
            socketio.emit('new_message', message_data, room=str(room_id))
            members = db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room_id).all()  # perf-ok: single-room member list
            for member_id in chat_member_fanout_ids(db, room_id, user_id, members):
                socketio.emit('new_message', message_data, room=user_room(member_id))
            room.updated_at = datetime.datetime.now()
            db.commit()
            print(f"[SocketIO] 메시지 전송: 사용자 {user_id} -> 방 {room_id}")
        except Exception as e:
            db.rollback()
            log_handled_exception()
            emit('error', {'message': f'메시지 전송 중 오류가 발생했습니다: {str(e)}'})

    @socketio.on('typing')
    def handle_typing(data):
        """타이핑 중 알림 — 회원인 채팅방에만."""
        user_id = session.get('user_id')
        if not user_id:
            return
        room_value = _room_value(data)
        if not room_value:
            return
        room_id, reason = _chat_access(user_id, room_value)
        if reason:
            emit('error', {'message': reason})
            return
        socketio.emit('user_typing', {
            'room_id': room_value,
            'user_id': user_id,
            'is_typing': data.get('is_typing', False)
        }, room=str(room_id), skip_sid=request.sid)

    @socketio.on('mark_read')
    def handle_mark_read(data):
        """메시지 읽음 표시"""
        user_id = session.get('user_id')
        if not user_id:
            return
        db = get_db()
        try:
            room_value = _room_value(data)
            if room_value:
                room_id, reason = _chat_access(user_id, room_value)
                if reason:
                    emit('error', {'message': reason})
                    return
                member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.room_id == room_id,
                    ChatRoomMember.user_id == user_id
                ).first()
                if member:
                    member.last_read_at = datetime.datetime.now()
                    db.commit()
                    socketio.emit('message_read', {
                        'room_id': room_value,
                        'user_id': user_id
                    }, room=str(room_id))
        except Exception as e:
            db.rollback()
