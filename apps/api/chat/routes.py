"""채팅 API 라우트 (Quest 3~10)."""
import os
import datetime
from flask import Blueprint, request, jsonify, redirect, send_file, render_template, session
from sqlalchemy import or_, and_, func

from db import get_db
from models import Order, User, ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment
from apps.auth import login_required, log_access
from services.storage import get_storage
from apps.api.files import build_file_view_url
from apps.api.chat.utils import allowed_chat_file, get_chat_file_max_size, schedule_chat_thumbnail_generation
from constants import CHAT_ALLOWED_EXTENSIONS
from wdcalculator_db import get_wdcalculator_db
from wdcalculator_models import Estimate, EstimateOrderMatch

chat_bp = Blueprint('chat', __name__, url_prefix='')


# ============================================
# 채팅 파일 API (Quest 3, 4)
# ============================================

@chat_bp.route('/api/chat/upload', methods=['POST'])
@login_required
def api_chat_upload():
    """채팅 파일 업로드 API (Quest 3)"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '파일이 선택되지 않았습니다.'}), 400
        file = request.files['file']
        room_id = request.form.get('room_id')
        if file.filename == '':
            return jsonify({'success': False, 'message': '파일명이 없습니다.'}), 400
        if not allowed_chat_file(file.filename):
            allowed_exts = ', '.join(sorted(CHAT_ALLOWED_EXTENSIONS))
            return jsonify({
                'success': False,
                'message': f'허용되지 않은 파일 형식입니다. 지원 형식: {allowed_exts}'
            }), 400
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        max_size = get_chat_file_max_size(file.filename)
        if file_size > max_size:
            size_mb = max_size / (1024 * 1024)
            return jsonify({
                'success': False,
                'message': f'파일 크기가 너무 큽니다. 최대 {size_mb:.0f}MB까지 업로드 가능합니다.'
            }), 400
        storage = get_storage()
        temp_id = f"temp_{int(datetime.datetime.now().timestamp() * 1000)}"
        if room_id:
            temp_id = f"room_{room_id}_{temp_id}"
        result = storage.upload_chat_file(file, file.filename, temp_id, generate_thumbnail=False)
        if not result.get('success'):
            return jsonify({
                'success': False,
                'message': f'파일 업로드 실패: {result.get("error", "알 수 없는 오류")}'
            }), 500
        storage_key = result.get('key')
        file_url = build_file_view_url(storage_key)
        thumbnail_key = result.get('thumbnail_key')
        thumbnail_url = build_file_view_url(thumbnail_key) if thumbnail_key else None
        file_info = {
            'filename': file.filename,
            'url': file_url,
            'storage_url': file_url,
            'thumbnail_url': thumbnail_url,
            'file_type': result.get('file_type'),
            'size': file_size,
            'key': storage_key,
            'download_url': f"/api/chat/download/{storage_key}"
        }
        log_access(
            f"채팅 파일 업로드: {file.filename} ({result.get('file_type')}, {file_size / 1024 / 1024:.2f}MB)",
            session.get('user_id')
        )
        return jsonify({
            'success': True,
            'message': '파일이 성공적으로 업로드되었습니다.',
            'file_info': file_info
        })
    except Exception as e:
        import traceback
        print(f"채팅 파일 업로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'파일 업로드 중 오류가 발생했습니다: {str(e)}'
        }), 500


@chat_bp.route('/api/chat/download/<path:storage_key>', methods=['GET'])
@login_required
def api_chat_download(storage_key):
    """채팅 파일 다운로드 API (Quest 4)"""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '잘못된 파일 경로입니다.'}), 400
        storage = get_storage()
        if storage.storage_type in ['r2', 's3']:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if url:
                log_access(f"채팅 파일 다운로드 요청: {storage_key}", session.get('user_id'))
                return redirect(url)
            else:
                return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
        else:
            file_path = os.path.join(storage.upload_folder, storage_key)
            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            log_access(f"채팅 파일 다운로드: {storage_key}", session.get('user_id'))
            return send_file(file_path, as_attachment=True)
    except Exception as e:
        import traceback
        print(f"파일 다운로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/preview/<path:storage_key>', methods=['GET'])
@login_required
def api_chat_preview(storage_key):
    """채팅 파일 미리보기 API (Quest 4)"""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '잘못된 파일 경로입니다.'}), 400
        storage = get_storage()
        filename = storage_key.rsplit('/', 1)[-1] if '/' in storage_key else storage_key
        file_type = storage._get_file_type(filename)
        if file_type == 'image':
            if storage.storage_type in ['r2', 's3']:
                url = storage.get_download_url(storage_key, expires_in=3600)
                if url:
                    return redirect(url)
                else:
                    return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            else:
                file_path = os.path.join(storage.upload_folder, storage_key)
                if os.path.exists(file_path):
                    return send_file(file_path)
                else:
                    return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
        elif file_type == 'video':
            if storage.storage_type in ['r2', 's3']:
                url = storage.get_download_url(storage_key, expires_in=3600)
                if url:
                    return jsonify({'success': True, 'type': 'video', 'url': url})
                else:
                    return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            else:
                file_path = os.path.join(storage.upload_folder, storage_key)
                if os.path.exists(file_path):
                    return send_file(file_path)
                else:
                    return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
        else:
            return jsonify({
                'success': False,
                'message': '미리보기를 지원하지 않는 파일 형식입니다.',
                'type': 'file'
            }), 400
    except Exception as e:
        import traceback
        print(f"파일 미리보기 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# 채팅방 관리 API (Quest 6)
# ============================================

@chat_bp.route('/api/chat/rooms', methods=['GET'])
@login_required
def api_chat_rooms_list():
    """채팅방 목록 조회 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        memberships = db.query(ChatRoomMember, ChatRoom).join(
            ChatRoom, ChatRoom.id == ChatRoomMember.room_id
        ).filter(ChatRoomMember.user_id == user_id).order_by(
            func.coalesce(ChatRoom.updated_at, ChatRoom.created_at).desc()
        ).all()
        if not memberships:
            return jsonify({'success': True, 'rooms': [], 'count': 0})
        rooms = [room for _, room in memberships]
        room_ids = [room.id for room in rooms]
        member_by_room = {member.room_id: member for member, _ in memberships}
        latest_ts_subq = db.query(
            ChatMessage.room_id.label('room_id'),
            func.max(ChatMessage.created_at).label('max_created_at')
        ).filter(ChatMessage.room_id.in_(room_ids)).group_by(ChatMessage.room_id).subquery()
        latest_rows = db.query(ChatMessage).join(
            latest_ts_subq,
            and_(
                ChatMessage.room_id == latest_ts_subq.c.room_id,
                ChatMessage.created_at == latest_ts_subq.c.max_created_at
            )
        ).all()
        last_message_by_room = {}
        for msg in latest_rows:
            prev = last_message_by_room.get(msg.room_id)
            if prev is None or (msg.created_at, msg.id) > (prev.created_at, prev.id):
                last_message_by_room[msg.room_id] = msg
        unread_rows = db.query(
            ChatMessage.room_id.label('room_id'),
            func.count(ChatMessage.id).label('unread_count')
        ).join(
            ChatRoomMember,
            and_(
                ChatRoomMember.room_id == ChatMessage.room_id,
                ChatRoomMember.user_id == user_id
            )
        ).filter(ChatMessage.room_id.in_(room_ids)).filter(
            or_(
                ChatRoomMember.last_read_at.is_(None),
                ChatMessage.created_at > ChatRoomMember.last_read_at
            )
        ).group_by(ChatMessage.room_id).all()
        unread_count_by_room = {room_id: int(count or 0) for room_id, count in unread_rows}
        rooms_list = []
        for room in rooms:
            room_data = room.to_dict()
            room_data['last_message'] = (
                last_message_by_room[room.id].to_dict()
                if room.id in last_message_by_room else None
            )
            room_data['unread_count'] = unread_count_by_room.get(room.id, 0) if member_by_room.get(room.id) else 0
            rooms_list.append(room_data)
        return jsonify({'success': True, 'rooms': rooms_list, 'count': len(rooms_list)})
    except Exception as e:
        import traceback
        print(f"채팅방 목록 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms', methods=['POST'])
@login_required
def api_chat_rooms_create():
    """채팅방 생성 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'message': '채팅방 이름은 필수입니다.'}), 400
        new_room = ChatRoom(
            name=name,
            description=data.get('description', '').strip(),
            order_id=data.get('order_id'),
            created_by=user_id
        )
        db.add(new_room)
        db.commit()
        db.refresh(new_room)
        member = ChatRoomMember(room_id=new_room.id, user_id=user_id)
        db.add(member)
        member_ids = data.get('member_ids', [])
        if member_ids:
            for member_id in member_ids:
                if member_id != user_id:
                    db.add(ChatRoomMember(room_id=new_room.id, user_id=member_id))
        db.commit()
        log_access(f"채팅방 생성: {name} (ID: {new_room.id})", user_id)
        return jsonify({
            'success': True,
            'message': '채팅방이 생성되었습니다.',
            'room': new_room.to_dict()
        }), 201
    except Exception as e:
        db.rollback()
        import traceback
        print(f"채팅방 생성 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms/<int:room_id>', methods=['GET'])
@login_required
def api_chat_rooms_detail(room_id):
    """채팅방 상세 조회 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '채팅방에 접근할 권한이 없습니다.'}), 403
        members = db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room_id).all()
        messages = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id
        ).order_by(ChatMessage.created_at.desc()).limit(50).all()
        messages_with_read_status = []
        for msg in messages:
            msg_dict = msg.to_dict()
            attachments = db.query(ChatAttachment).filter(ChatAttachment.message_id == msg.id).all()
            if attachments:
                msg_dict['attachments'] = [a.to_dict() for a in attachments]
            if msg.user_id == user_id:
                read_count = 0
                total_other_members = 0
                for m in members:
                    if m.user_id != user_id:
                        total_other_members += 1
                        if m.last_read_at and m.last_read_at >= msg.created_at:
                            read_count += 1
                if total_other_members == 0:
                    msg_dict['read_status'] = 'no_other_members'
                elif read_count == 0:
                    msg_dict['read_status'] = 'unread'
                elif read_count == total_other_members:
                    msg_dict['read_status'] = 'all_read'
                else:
                    msg_dict['read_status'] = 'some_read'
                msg_dict['read_count'] = read_count
                msg_dict['total_other_members'] = total_other_members
            else:
                msg_dict['read_status'] = None
                msg_dict['read_count'] = 0
                msg_dict['total_other_members'] = 0
            messages_with_read_status.append(msg_dict)
        room_data = room.to_dict()
        room_data['members'] = [{
            **m.to_dict(),
            'user_name': m.user.name if m.user else None,
            'user_username': m.user.username if m.user else None
        } for m in members]
        room_data['messages'] = list(reversed(messages_with_read_status))
        if room.order_id:
            try:
                order = db.query(Order).filter(Order.id == room.order_id).first()
                if order:
                    order_data = order.to_dict()
                    try:
                        wd_db = get_wdcalculator_db()
                        estimates = wd_db.query(EstimateOrderMatch).filter(
                            EstimateOrderMatch.order_id == room.order_id
                        ).all()
                        estimate_list = []
                        for match in estimates:
                            est = wd_db.query(Estimate).filter(Estimate.id == match.estimate_id).first()
                            if est:
                                estimate_list.append(est.to_dict())
                        order_data['estimates'] = estimate_list
                    except Exception as e:
                        print(f"견적 정보 조회 오류 (무시): {e}")
                        order_data['estimates'] = []
                    room_data['order'] = order_data
                else:
                    room_data['order'] = None
            except Exception as e:
                print(f"주문 정보 조회 오류 (무시): {e}")
                room_data['order'] = None
        else:
            room_data['order'] = None
        return jsonify({'success': True, 'room': room_data})
    except Exception as e:
        import traceback
        print(f"채팅방 상세 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms/<int:room_id>', methods=['PUT'])
@login_required
def api_chat_rooms_update(room_id):
    """채팅방 수정 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        data = request.get_json()
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        if room.created_by != user_id:
            return jsonify({'success': False, 'message': '채팅방을 수정할 권한이 없습니다.'}), 403
        if 'name' in data:
            room.name = data['name'].strip()
        if 'description' in data:
            room.description = data.get('description', '').strip()
        if 'order_id' in data:
            room.order_id = data.get('order_id')
        room.updated_at = datetime.datetime.now()
        db.commit()
        log_access(f"채팅방 수정: {room.name} (ID: {room_id})", user_id)
        return jsonify({
            'success': True,
            'message': '채팅방이 수정되었습니다.',
            'room': room.to_dict()
        })
    except Exception as e:
        db.rollback()
        import traceback
        print(f"채팅방 수정 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms/<int:room_id>', methods=['DELETE'])
@login_required
def api_chat_rooms_delete(room_id):
    """채팅방 삭제 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        if room.created_by != user_id:
            return jsonify({'success': False, 'message': '채팅방을 삭제할 권한이 없습니다.'}), 403
        room_name = room.name
        db.delete(room)
        db.commit()
        log_access(f"채팅방 삭제: {room_name} (ID: {room_id})", user_id)
        return jsonify({'success': True, 'message': '채팅방이 삭제되었습니다.'})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"채팅방 삭제 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms/<int:room_id>/members', methods=['POST'])
@login_required
def api_chat_rooms_add_member(room_id):
    """채팅방 멤버 추가 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        data = request.get_json()
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '채팅방에 접근할 권한이 없습니다.'}), 403
        new_member_id = data.get('user_id')
        if not new_member_id:
            return jsonify({'success': False, 'message': '사용자 ID는 필수입니다.'}), 400
        user = db.query(User).filter(User.id == new_member_id).first()
        if not user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 404
        existing = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == new_member_id
        ).first()
        if existing:
            return jsonify({'success': False, 'message': '이미 채팅방 멤버입니다.'}), 400
        new_member = ChatRoomMember(room_id=room_id, user_id=new_member_id)
        db.add(new_member)
        db.commit()
        log_access(f"채팅방 멤버 추가: 방 {room_id}, 사용자 {new_member_id}", user_id)
        return jsonify({
            'success': True,
            'message': '멤버가 추가되었습니다.',
            'member': new_member.to_dict()
        }), 201
    except Exception as e:
        db.rollback()
        import traceback
        print(f"멤버 추가 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/rooms/<int:room_id>/members/<int:member_user_id>', methods=['DELETE'])
@login_required
def api_chat_rooms_remove_member(room_id, member_user_id):
    """채팅방 멤버 제거 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        if room.created_by != user_id and member_user_id != user_id:
            return jsonify({'success': False, 'message': '멤버를 제거할 권한이 없습니다.'}), 403
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == member_user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '멤버를 찾을 수 없습니다.'}), 404
        db.delete(member)
        db.commit()
        log_access(f"채팅방 멤버 제거: 방 {room_id}, 사용자 {member_user_id}", user_id)
        return jsonify({'success': True, 'message': '멤버가 제거되었습니다.'})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"멤버 제거 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# 주문 연동 API (Quest 8)
# ============================================

@chat_bp.route('/api/chat/orders/<int:order_id>', methods=['GET'])
@login_required
def api_chat_order_detail(order_id):
    """채팅방에서 사용할 주문 상세 정보 조회 API"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        order_data = order.to_dict()
        try:
            wd_db = get_wdcalculator_db()
            estimates = wd_db.query(EstimateOrderMatch).filter(
                EstimateOrderMatch.order_id == order_id
            ).all()
            estimate_list = []
            for match in estimates:
                est = wd_db.query(Estimate).filter(Estimate.id == match.estimate_id).first()
                if est:
                    estimate_list.append(est.to_dict())
            order_data['estimates'] = estimate_list
        except Exception as e:
            print(f"견적 정보 조회 오류 (무시): {e}")
            order_data['estimates'] = []
        return jsonify({'success': True, 'order': order_data})
    except Exception as e:
        import traceback
        print(f"주문 정보 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/search-orders', methods=['GET'])
@login_required
def api_chat_search_orders():
    """채팅방에서 주문 검색 API"""
    try:
        db = get_db()
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 20))
        if not query:
            return jsonify({'success': True, 'orders': [], 'count': 0})
        conds = [Order.customer_name.ilike(f'%{query}%')]
        if query.isdigit():
            conds.append(Order.id == int(query))
        orders = db.query(Order).filter(or_(*conds)).filter(
            Order.deleted_at.is_(None)
        ).order_by(Order.created_at.desc()).limit(limit).all()
        orders_list = [{
            'id': o.id, 'customer_name': o.customer_name, 'phone': o.phone,
            'address': o.address, 'product': o.product, 'status': o.status,
            'received_date': o.received_date,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S') if o.created_at else None
        } for o in orders]
        return jsonify({'success': True, 'orders': orders_list, 'count': len(orders_list)})
    except Exception as e:
        import traceback
        print(f"주문 검색 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# 전체 채팅 검색 API (Quest 1)
# ============================================

@chat_bp.route('/api/chat/search', methods=['GET'])
@login_required
def api_chat_search():
    """전체 채팅 검색 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 50))
        if not query or len(query) < 2:
            return jsonify({'success': True, 'results': [], 'count': 0})
        user_rooms = db.query(ChatRoom.id).join(
            ChatRoomMember, ChatRoom.id == ChatRoomMember.room_id
        ).filter(ChatRoomMember.user_id == user_id).subquery()
        results = []
        messages = db.query(ChatMessage).join(
            user_rooms, ChatMessage.room_id == user_rooms.c.id
        ).filter(ChatMessage.content.ilike(f'%{query}%')).limit(limit).all()
        for msg in messages:
            room = db.query(ChatRoom).filter(ChatRoom.id == msg.room_id).first()
            results.append({
                'type': 'message', 'room_id': msg.room_id, 'room_name': room.name if room else None,
                'message_id': msg.id, 'content': msg.content,
                'user_name': msg.user.name if msg.user else None,
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S') if msg.created_at else None
            })
        rooms = db.query(ChatRoom).join(user_rooms, ChatRoom.id == user_rooms.c.id).filter(
            or_(
                ChatRoom.name.ilike(f'%{query}%'),
                ChatRoom.description.ilike(f'%{query}%')
            )
        ).limit(limit).all()
        for room in rooms:
            if not any(r.get('room_id') == room.id and r.get('type') == 'room' for r in results):
                results.append({
                    'type': 'room', 'room_id': room.id, 'room_name': room.name,
                    'description': room.description,
                    'created_at': room.created_at.strftime('%Y-%m-%d %H:%M:%S') if room.created_at else None
                })
        orders = db.query(Order).join(ChatRoom, Order.id == ChatRoom.order_id).join(
            user_rooms, ChatRoom.id == user_rooms.c.id
        ).filter(
            or_(
                Order.customer_name.ilike(f'%{query}%'),
                Order.phone.ilike(f'%{query}%'),
                Order.address.ilike(f'%{query}%')
            )
        ).limit(limit).all()
        for order in orders:
            room = db.query(ChatRoom).filter(ChatRoom.order_id == order.id).first()
            if room and not any(r.get('room_id') == room.id and r.get('type') == 'order' for r in results):
                results.append({
                    'type': 'order', 'room_id': room.id, 'room_name': room.name,
                    'order_id': order.id, 'customer_name': order.customer_name,
                    'phone': order.phone, 'address': order.address, 'product': order.product
                })
        seen = set()
        unique_results = []
        for r in results:
            key = (r['type'], r.get('room_id'), r.get('message_id', 0), r.get('order_id', 0))
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        return jsonify({
            'success': True,
            'results': unique_results[:limit],
            'count': len(unique_results)
        })
    except Exception as e:
        import traceback
        print(f"채팅 검색 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# 메시지 읽음 / 사용자 목록 / 메시지 REST API
# ============================================

@chat_bp.route('/api/chat/rooms/<int:room_id>/mark-read', methods=['POST'])
@login_required
def api_chat_mark_read(room_id):
    """메시지 읽음 상태 업데이트 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '채팅방 멤버가 아닙니다.'}), 403
        member.last_read_at = datetime.datetime.now()
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"읽음 상태 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/users', methods=['GET'])
@login_required
def api_chat_users_list():
    """채팅 초대용 사용자 목록 조회 API"""
    try:
        db = get_db()
        current_user_id = session.get('user_id')
        users = db.query(User).filter(
            User.is_active == True,
            User.id != current_user_id
        ).order_by(User.name).all()
        users_list = [{'id': u.id, 'name': u.name, 'username': u.username, 'role': u.role} for u in users]
        return jsonify({'success': True, 'users': users_list})
    except Exception as e:
        import traceback
        print(f"사용자 목록 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/messages', methods=['POST'])
@login_required
def api_chat_send_message():
    """메시지 전송 API (Socket.IO 폴백용)"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        data = request.get_json()
        room_id = data.get('room_id')
        message_type = data.get('message_type', 'text')
        content = data.get('content', '').strip()
        file_info = data.get('file_info')
        if not room_id:
            return jsonify({'success': False, 'message': '채팅방 ID는 필수입니다.'}), 400
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return jsonify({'success': False, 'message': '채팅방을 찾을 수 없습니다.'}), 404
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '채팅방에 접근할 권한이 없습니다.'}), 403
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
        room.updated_at = datetime.datetime.now()
        db.commit()
        return jsonify({'success': True, 'message': message_data})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"메시지 전송 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@chat_bp.route('/api/chat/messages/<int:message_id>', methods=['GET'])
@login_required
def api_chat_get_message(message_id):
    """단일 메시지 조회 API"""
    try:
        db = get_db()
        user_id = session.get('user_id')
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if not message:
            return jsonify({'success': False, 'message': '메시지를 찾을 수 없습니다.'}), 404
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == message.room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if not member:
            return jsonify({'success': False, 'message': '권한이 없습니다.'}), 403
        message_data = message.to_dict()
        user = db.query(User).filter(User.id == message.user_id).first()
        if user:
            message_data['user_name'] = user.name
        attachments = db.query(ChatAttachment).filter(ChatAttachment.message_id == message.id).all()
        if attachments:
            message_data['attachments'] = [a.to_dict() for a in attachments]
        return jsonify({'success': True, 'message': message_data})
    except Exception as e:
        import traceback
        print(f"메시지 조회 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# 채팅 페이지 (Quest 10)
# ============================================

@chat_bp.route('/chat')
@login_required
def chat():
    """채팅 페이지 (Quest 10)"""
    from flask import current_app
    socketio_available = current_app.config.get('SOCKETIO_AVAILABLE', False) and current_app.config.get('_SOCKETIO_INSTANCE') is not None
    return render_template('chat.html', socketio_available=socketio_available)
