"""채팅 SocketIO 이벤트 핸들러 등록."""
import datetime
from flask import session, request
from flask_socketio import emit, join_room, leave_room
from db import get_db
from models import ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment, User
from apps.api.chat.utils import schedule_chat_thumbnail_generation


def register_chat_socketio_handlers(socketio):
    """채팅 관련 SocketIO 이벤트 핸들러 등록."""
    @socketio.on('connect')
    def handle_connect():
        """클라이언트 연결 이벤트"""
        user_id = session.get('user_id')
        if user_id:
            print(f"[SocketIO] 사용자 {user_id} 연결됨")
            join_room(f'user_{user_id}')
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
        """채팅방 입장"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': '인증이 필요합니다.'})
            return
        room_id = data.get('room_id')
        if room_id:
            join_room(str(room_id))
            print(f"[SocketIO] 사용자 {user_id}가 채팅방 {room_id}에 입장")
            emit('joined_room', {'room_id': room_id, 'user_id': user_id})
            socketio.emit('user_joined', {
                'room_id': room_id,
                'user_id': user_id
            }, room=str(room_id))

    @socketio.on('leave_room')
    def handle_leave_room(data):
        """채팅방 퇴장"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': '인증이 필요합니다.'})
            return
        room_id = data.get('room_id')
        if room_id:
            leave_room(str(room_id))
            print(f"[SocketIO] 사용자 {user_id}가 채팅방 {room_id}에서 퇴장")
            emit('left_room', {'room_id': room_id, 'user_id': user_id})
            socketio.emit('user_left', {
                'room_id': room_id,
                'user_id': user_id
            }, room=str(room_id))

    @socketio.on('send_message')
    def handle_send_message(data):
        """메시지 전송"""
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': '인증이 필요합니다.'})
            return
        try:
            db = get_db()
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
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.user_id == user_id
            ).first()
            if not member:
                emit('error', {'message': '채팅방에 접근할 권한이 없습니다.'})
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
            members = db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room_id).all()
            for m in members:
                if m.user_id != user_id:
                    socketio.emit('new_message', message_data, room=f'user_{m.user_id}')
            room.updated_at = datetime.datetime.now()
            db.commit()
            print(f"[SocketIO] 메시지 전송: 사용자 {user_id} -> 방 {room_id}")
        except Exception as e:
            db.rollback()
            import traceback
            print(f"메시지 전송 오류: {e}")
            print(traceback.format_exc())
            emit('error', {'message': f'메시지 전송 중 오류가 발생했습니다: {str(e)}'})

    @socketio.on('typing')
    def handle_typing(data):
        """타이핑 중 알림"""
        user_id = session.get('user_id')
        if not user_id:
            return
        room_id = data.get('room_id')
        is_typing = data.get('is_typing', False)
        if room_id:
            socketio.emit('user_typing', {
                'room_id': room_id,
                'user_id': user_id,
                'is_typing': is_typing
            }, room=str(room_id), skip_sid=request.sid)

    @socketio.on('mark_read')
    def handle_mark_read(data):
        """메시지 읽음 표시"""
        user_id = session.get('user_id')
        if not user_id:
            return
        try:
            db = get_db()
            room_id = data.get('room_id')
            if room_id:
                member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.room_id == room_id,
                    ChatRoomMember.user_id == user_id
                ).first()
                if member:
                    member.last_read_at = datetime.datetime.now()
                    db.commit()
                    socketio.emit('message_read', {
                        'room_id': room_id,
                        'user_id': user_id
                    }, room=str(room_id))
        except Exception as e:
            db.rollback()
            print(f"읽음 표시 오류: {e}")
