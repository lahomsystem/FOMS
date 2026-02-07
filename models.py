import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

# JSON Type Compatibility Layer
JSONColumn = JSON().with_variant(JSONB, 'postgresql')
from db import Base

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    received_date = Column(String, nullable=False)
    received_time = Column(String)
    customer_name = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=False, index=True)
    address = Column(Text, nullable=False)
    product = Column(String, nullable=False)
    options = Column(Text)
    notes = Column(Text)
    status = Column(String, default='RECEIVED', index=True)
    original_status = Column(String)
    deleted_at = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    # New fields for request 2
    measurement_date = Column(String) # 실측일
    measurement_time = Column(String) # 실측시간
    completion_date = Column(String)  # 설치완료일
    manager_name = Column(String)     # 담당자
    payment_amount = Column(Integer, nullable=True, default=0) # 결제 금액
    
    # Additional date fields for each status
    scheduled_date = Column(String)  # 설치 예정일
    as_received_date = Column(String)  # AS 접수일
    as_completed_date = Column(String)  # AS 완료일
    
    # Regional order management fields (지방 주문 관리)
    is_regional = Column(Boolean, default=False)  # 지방 주문 여부
    is_self_measurement = Column(Boolean, default=False)  # 자가실측 여부
    # Cabinet (수납장) management flag and status
    is_cabinet = Column(Boolean, default=False)  # 수납장 주문 여부
    cabinet_status = Column(String, default=None, nullable=True)  # 수납장 상태: RECEIVED/IN_PRODUCTION/SHIPPED
    regional_sales_order_upload = Column(Boolean, default=False)  # 영업발주 업로드  
    regional_blueprint_sent = Column(Boolean, default=False)  # 도면발송
    regional_order_upload = Column(Boolean, default=False)  # 발주 업로드
    regional_cargo_sent = Column(Boolean, default=False)  # 화물 발송
    regional_construction_info_sent = Column(Boolean, default=False)  # 시공정보 발송
    measurement_completed = Column(Boolean, default=False) # 실측완료
    construction_type = Column(String(50), nullable=True) # 시공 구분
    regional_memo = Column(Text, nullable=True) # 지방 주문 메모
    
    # 상차 예정일 추가
    shipping_scheduled_date = Column(String)
    
    # 배송비 추가 (수납장 대시보드용)
    shipping_fee = Column(Integer, nullable=True, default=0)
    
    # 도면 이미지 URL
    blueprint_image_url = Column(Text, nullable=True)

    # ============================================
    # ERP Beta (Palantir-style structured data)
    # ============================================
    # ERP Beta로 생성된 주문인지 여부 (ERP 대시보드 노출/운영 분리용)
    is_erp_beta = Column(Boolean, nullable=False, default=False, server_default='false')
    raw_order_text = Column(Text, nullable=True)  # 원문 텍스트(붙여넣기) 보관
    structured_data = Column(JSONColumn, nullable=True)  # 구조화 데이터(JSON / JSONB)
    structured_schema_version = Column(Integer, nullable=False, default=1)
    structured_confidence = Column(String(20), nullable=True)  # high/medium/low
    structured_updated_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class OrderAttachment(Base):
    """주문(ERP Beta 등) 첨부파일: 사진/동영상 메타데이터만 저장 (파일 바이너리는 스토리지에 저장)"""
    __tablename__ = 'order_attachments'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)

    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # image / video
    file_size = Column(Integer, nullable=False, default=0)

    storage_key = Column(String(500), nullable=False)  # static/uploads 기준 key 또는 R2 key
    thumbnail_key = Column(String(500), nullable=True)  # 이미지 썸네일 key (선택)

    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)

    order = relationship('Order', foreign_keys=[order_id])

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'storage_key': self.storage_key,
            'thumbnail_key': self.thumbnail_key,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class OrderEvent(Base):
    """ERP 이벤트 스트림(단계 변경/일정 변경/긴급 발주/컨펌 등)"""
    __tablename__ = 'order_events'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # e.g. STAGE_CHANGED, URGENT_SET
    payload = Column(JSONB, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False, index=True)

    order = relationship('Order', foreign_keys=[order_id])
    created_by = relationship('User', foreign_keys=[created_by_user_id])


class OrderTask(Base):
    """팔로업/이슈 추적(Task)"""
    __tablename__ = 'order_tasks'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default='OPEN')  # OPEN/IN_PROGRESS/DONE/CANCELLED
    owner_team = Column(String(50), nullable=True)  # CS/SALES/MEASURE/DRAWING/PRODUCTION/CONSTRUCTION
    owner_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    due_date = Column(String, nullable=True)  # YYYY-MM-DD
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.now, nullable=False)

    order = relationship('Order', foreign_keys=[order_id])
    owner_user = relationship('User', foreign_keys=[owner_user_id])


class SystemBuildStep(Base):
    """빌드/마이그레이션 단계 진행상태 저장 (끊김 시 이어서 실행용)"""
    __tablename__ = 'system_build_steps'

    step_key = Column(String(100), primary_key=True)  # 예: ERP_BETA_STEP_1_SCHEMA
    status = Column(String(30), nullable=False, default='PENDING')  # PENDING/RUNNING/COMPLETED/FAILED
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    message = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False, default='사용자')
    role = Column(String, nullable=False, default='VIEWER')
    team = Column(String(50), nullable=True)  # cs/drawing/production/construction
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    last_login = Column(DateTime)
    
    access_logs = relationship("AccessLog", back_populates="user")
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'name': self.name,
            'role': self.role,
            'team': self.team,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else None
        }

class AccessLog(Base):
    __tablename__ = 'access_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String, nullable=False)
    ip_address = Column(String)
    user_agent = Column(String)
    additional_data = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    
    user = relationship("User", back_populates="access_logs")
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'additional_data': self.additional_data,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None
        }

class SecurityLog(Base):
    __tablename__ = 'security_logs'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    message = Column(String, nullable=False) 


# ============================================
# 채팅 시스템 모델 (Quest 1)
# ============================================

class ChatRoom(Base):
    """채팅방"""
    __tablename__ = 'chat_rooms'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)  # 채팅방 이름
    description = Column(Text, nullable=True)  # 설명
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True)  # 주문 연결 (선택)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)  # 생성자
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=True)
    
    # 관계
    messages = relationship('ChatMessage', backref='room', lazy='dynamic', cascade='all, delete-orphan')
    members = relationship('ChatRoomMember', backref='room', lazy='dynamic', cascade='all, delete-orphan')
    creator = relationship('User', foreign_keys=[created_by])
    order = relationship('Order', foreign_keys=[order_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'order_id': self.order_id,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }


class ChatRoomMember(Base):
    """채팅방 멤버"""
    __tablename__ = 'chat_room_members'
    
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    joined_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    last_read_at = Column(DateTime, nullable=True)  # 마지막 읽은 시간
    
    # 관계
    user = relationship('User', foreign_keys=[user_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'joined_at': self.joined_at.strftime('%Y-%m-%d %H:%M:%S') if self.joined_at else None,
            'last_read_at': self.last_read_at.strftime('%Y-%m-%d %H:%M:%S') if self.last_read_at else None
        }


class ChatMessage(Base):
    """채팅 메시지"""
    __tablename__ = 'chat_messages'
    
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_type = Column(String(20), default='text', nullable=False)  # text, image, video, file
    content = Column(Text, nullable=True)  # 텍스트 메시지 내용
    file_info = Column(JSONB, nullable=True)  # 파일 정보 (JSON 형태)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False, index=True)
    
    # 관계
    user = relationship('User', foreign_keys=[user_id])
    attachments = relationship('ChatAttachment', backref='message', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'message_type': self.message_type,
            'content': self.content,
            'file_info': self.file_info,  # JSONB는 자동으로 dict로 변환됨
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class ChatAttachment(Base):
    """채팅 첨부파일"""
    __tablename__ = 'chat_attachments'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('chat_messages.id', ondelete='CASCADE'), nullable=False, index=True)
    filename = Column(String(255), nullable=False)  # 원본 파일명
    file_type = Column(String(50), nullable=False)  # image, video, file
    file_size = Column(Integer, nullable=False)  # 바이트 단위
    storage_key = Column(String(500), nullable=False)  # 클라우드 스토리지 키
    storage_url = Column(String(1000), nullable=False)  # 다운로드 URL
    thumbnail_url = Column(String(1000), nullable=True)  # 썸네일 URL (이미지/동영상)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'storage_key': self.storage_key,
            'storage_url': self.storage_url,
            'url': self.storage_url,  # 호환성을 위해 추가
            'thumbnail_url': self.thumbnail_url,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        } 


class Notification(Base):
    """알림 시스템 - 담당 팀/영업사원에게 알림 전달
    
    담당(manager_name) 값에 따라 알림 대상 결정:
    - '라홈' → 라홈팀(CS)
    - '하우드' → 하우드팀(HAUDD)
    - 그 외 → 해당 영업사원(SALES)
    """
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # 알림 유형
    notification_type = Column(String(50), nullable=False, index=True)
    # DRAWING_TRANSFERRED: 도면 전달됨
    # STAGE_CHANGED: 단계 변경됨
    # QUEST_ASSIGNED: 퀘스트 할당됨
    # AS_REQUIRED: AS 필요
    
    # 알림 대상 (팀 또는 영업사원명)
    target_team = Column(String(50), nullable=True, index=True)  # CS, HAUDD, SALES, etc.
    target_manager_name = Column(String(100), nullable=True, index=True)  # 특정 영업사원명
    
    # 알림 내용
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=True)
    
    # 생성자
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_by_name = Column(String(100), nullable=True)
    
    # 상태
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
    read_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # 타임스탬프
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False, index=True)
    
    # 관계
    order = relationship('Order', foreign_keys=[order_id])
    created_by = relationship('User', foreign_keys=[created_by_user_id])
    read_by = relationship('User', foreign_keys=[read_by_user_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'notification_type': self.notification_type,
            'target_team': self.target_team,
            'target_manager_name': self.target_manager_name,
            'title': self.title,
            'message': self.message,
            'created_by_name': self.created_by_name,
            'is_read': self.is_read,
            'read_at': self.read_at.strftime('%Y-%m-%d %H:%M:%S') if self.read_at else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }