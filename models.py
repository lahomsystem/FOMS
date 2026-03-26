import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, func, JSON
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
    # 지도 지오코딩 (Phase C: 선계산 저장)
    # ============================================
    lat = Column(Float, nullable=True)  # 위도
    lng = Column(Float, nullable=True)  # 경도
    geocode_status = Column(String(50), nullable=True)  # pending / success / failed
    geocoded_at = Column(DateTime, nullable=True)  # 지오코딩 완료 시각
    address_hash = Column(String(64), nullable=True)  # 주소 변경 감지용 (SHA256 앞 16자 등)

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
    
    # ERP Beta 실측·시공 일정 정규화 컬럼 (D-day SQL 필터용)
    erp_measurement_date = Column(String(10), nullable=True, index=True)   # YYYY-MM-DD
    erp_construction_date = Column(String(10), nullable=True, index=True)  # YYYY-MM-DD

    # Phase D 플랫 컬럼 (DB 레벨 쿼리/페이지네이션 최적화)
    erp_stage_code = Column(String(30), nullable=True, index=True)         # workflow.stage (ex: "RECEIVED", "MEASURE")
    erp_urgent = Column(Boolean, nullable=False, default=False, server_default='false', index=True)  # flags.urgent
    erp_drawing_updated_at = Column(DateTime, nullable=True)               # workflow.stage_updated_at (DRAWING/CONFIRM용)
    erp_owner_team_code = Column(String(20), nullable=True, index=True)    # assignments.owner_team

    # ============================================
    # ChannelTalk 연동 (Phase 0)
    # ============================================
    channel_source_seq = Column(Integer, nullable=False, default=0, server_default='0')

    
    # Phase 4: 정규화된 날짜 테이블 (1:N)
    schedule_dates = relationship('OrderScheduleDate', backref='order', cascade='all, delete-orphan')

    from sqlalchemy import Index, and_
    __table_args__ = (
        Index('ix_orders_regional_active', 'id', postgresql_where=(and_(status != 'DELETED', deleted_at.is_(None), is_regional == True))),
        Index('ix_orders_self_measurement_active', 'id', postgresql_where=(and_(status != 'DELETED', deleted_at.is_(None), is_self_measurement == True))),
        Index('ix_orders_erp_beta_active', 'id', postgresql_where=(and_(status != 'DELETED', deleted_at.is_(None), is_erp_beta == True))),
    )

    @classmethod
    def active_filter(cls):
        """Phase C-0: active 주문 필터 (soft-delete 제외). status != DELETED AND deleted_at IS NULL."""
        from sqlalchemy import and_
        return and_(cls.status != 'DELETED', cls.deleted_at.is_(None))

    @classmethod
    def dashboard_active_filter(cls, days=60):
        """
        Phase H: 운영 대시보드 전용 필터.
        기본 active_filter를 포함하며, 완료('COMPLETED', 'AS_COMPLETED')된 지 
        지정된 기간(기본 60일)이 지난 과거 데이터는 제외한다.
        """
        from sqlalchemy import and_, or_, not_
        import datetime
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        completed_stages = ['COMPLETED', 'AS_COMPLETED', '"COMPLETED"', '"AS_COMPLETED"', '완료', 'AS완료', '"완료"', '"AS완료"']
        
        return and_(
            cls.active_filter(),
            or_(
                cls.erp_stage_code.is_(None),
                ~cls.erp_stage_code.in_(completed_stages),
                or_(
                    and_(cls.structured_updated_at.isnot(None), cls.structured_updated_at >= cutoff_date),
                    and_(cls.structured_updated_at.is_(None), cls.created_at >= cutoff_date)
                )
            )
        )

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class OrderScheduleDate(Base):
    """Phase 4 날짜 검색 구조 정상화를 위한 조인/검색 전용 테이블"""
    __tablename__ = 'order_schedule_dates'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(50), nullable=False, index=True)      # e.g., 'measurement', 'construction', 'shipping'
    date = Column(String(20), nullable=False, index=True)      # e.g., '2026-03-09'
    source = Column(String(50), nullable=False)                # e.g., 'legacy_column', 'beta_schedule', 'beta_item'
    item_index = Column(Integer, nullable=True)                # e.g., 0, 1 ... (for items array)

    from sqlalchemy import Index
    __table_args__ = (
        Index('idx_order_schedule_dates_composite', 'kind', 'date', 'order_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'kind': self.kind,
            'date': self.date,
            'source': self.source,
            'item_index': self.item_index
        }


class OrderAttachment(Base):
    """주문(ERP Beta 등) 첨부파일: 사진/동영상 메타데이터만 저장 (파일 바이너리는 스토리지에 저장)"""
    __tablename__ = 'order_attachments'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)

    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # image / video
    category = Column(String(50), nullable=False, default='measurement')  # measurement / drawing / construction / as
    item_index = Column(Integer, nullable=True, default=None, index=True)  # 제품 항목 인덱스 (None=공통)
    file_size = Column(Integer, nullable=False, default=0)

    storage_key = Column(String(500), nullable=False)  # static/uploads 기준 key 또는 R2 key
    thumbnail_key = Column(String(500), nullable=True)  # 이미지 썸네일 key (선택)

    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)  # 업로더 (AS 재업로드 시 본인 것만 삭제)

    order = relationship('Order', foreign_keys=[order_id])

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'category': self.category or 'measurement',
            'item_index': self.item_index,
            'file_size': self.file_size,
            'storage_key': self.storage_key,
            'thumbnail_key': self.thumbnail_key,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'user_id': self.user_id,
        }


class OrderEvent(Base):
    """ERP 이벤트 스트림(단계 변경/일정 변경/긴급 발주/컨펌 등)"""
    __tablename__ = 'order_events'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # e.g. STAGE_CHANGED, URGENT_SET
    payload = Column(JSONColumn, nullable=True)
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
    meta = Column(JSONColumn, nullable=True)
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
    meta = Column(JSONColumn, nullable=True)

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
    file_info = Column(JSONColumn, nullable=True)  # 파일 정보 (JSON 형태)
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
    """알림 시스템 - 담당 팀/영업사원/특정 사용자에게 알림 전달

    target_type에 따른 대상 결정:
    - ORDER: 주문 관련 (기존 방식 — target_team/target_manager_name)
    - ALL: 전체 사용자 (사용자별 레코드 복제)
    - TEAM: 특정 팀 대상
    - USER: 특정 사용자 직접 지정 (target_user_id)
    """
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=True, index=True)
    
    # 알림 유형
    notification_type = Column(String(50), nullable=False, index=True)
    # DRAWING_TRANSFERRED / DRAWING_REVISION / STAGE_CHANGED
    # QUEST_ASSIGNED / AS_REQUIRED
    # ANNOUNCEMENT / URGENT_ANNOUNCEMENT / URGENT_MENTION
    
    # 대상 유형: ORDER(주문관련), ALL(전체), TEAM(팀), USER(특정인)
    target_type = Column(String(20), nullable=False, default='ORDER', server_default='ORDER', index=True)
    
    # 알림 대상 (팀 또는 영업사원명 — 기존 호환)
    target_team = Column(String(50), nullable=True, index=True)
    target_manager_name = Column(String(100), nullable=True, index=True)
    # 특정 사용자 직접 지정
    target_user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    
    # 긴급 여부
    is_urgent = Column(Boolean, default=False, nullable=False, server_default='false', index=True)
    
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
    target_user = relationship('User', foreign_keys=[target_user_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'notification_type': self.notification_type,
            'target_type': self.target_type,
            'target_team': self.target_team,
            'target_manager_name': self.target_manager_name,
            'target_user_id': self.target_user_id,
            'is_urgent': bool(self.is_urgent),
            'title': self.title,
            'message': self.message,
            'created_by_name': self.created_by_name,
            'is_read': self.is_read,
            'read_at': self.read_at.strftime('%Y-%m-%d %H:%M:%S') if self.read_at else None,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

# ============================================
# ChannelTalk 연동 모델 (Phase 0)
# ============================================

class ChannelDeliveryLog(Base):
    """FOMS -> ChannelTalk 전송 상태 영속화 (Outbox 겸용)"""
    __tablename__ = 'channel_delivery_logs'
    
    id = Column(Integer, primary_key=True)
    event_key = Column(String(200), nullable=False)
    source_type = Column(String(50), nullable=False)
    source_id = Column(Integer, nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(200), nullable=False)
    status = Column(String(50), nullable=False, default='pending')
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    message_id = Column(String(200), nullable=True)
    masked_request_payload = Column(JSONColumn, nullable=True)
    masked_response_payload = Column(JSONColumn, nullable=True)
    rendered_text_snapshot = Column(Text, nullable=True)
    file_snapshot = Column(JSONColumn, nullable=True)
    target_group_snapshot = Column(String(200), nullable=True)
    template_key = Column(String(100), nullable=True)
    template_version = Column(Integer, nullable=True)
    source_version = Column(Integer, nullable=True)
    parent_delivery_id = Column(Integer, ForeignKey('channel_delivery_logs.id'), nullable=True)
    correlation_id = Column(String(100), nullable=True)
    actor_type = Column(String(30), nullable=True)
    actor_id = Column(Integer, nullable=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    wave = Column(String(20), nullable=True)
    request_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    
    order = relationship('Order', foreign_keys=[order_id])
    
    from sqlalchemy import Index, UniqueConstraint
    __table_args__ = (
        UniqueConstraint('event_key', 'target_type', 'target_id', name='uq_channel_delivery_event_target'),
        Index('ix_channel_delivery_source_status', 'source_type', 'source_id', 'status'),
        Index('ix_channel_delivery_retry', 'status', 'next_retry_at', postgresql_where=(status.in_(['pending', 'api_failed', 'token_issue_failed', 'token_rate_limited']))),
        Index('ix_channel_delivery_order_created', 'order_id', 'created_at'),
        Index('ix_channel_delivery_created_at', 'created_at'),
    )


class ChannelManagerLink(Base):
    """ChannelTalk manager와 FOMS user 매핑"""
    __tablename__ = 'channel_manager_links'
    
    id = Column(Integer, primary_key=True)
    channel_manager_id = Column(String(200), nullable=False)
    channel_manager_email = Column(String(200), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    linked_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    last_verified_at = Column(DateTime, nullable=True)
    deactivated_at = Column(DateTime, nullable=True)
    deactivated_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    user = relationship('User', foreign_keys=[user_id])
    
    from sqlalchemy import Index
    __table_args__ = (
        Index('ix_channel_manager_link_active_id', 'channel_manager_id', postgresql_where=(is_active == True), unique=True),
        Index('ix_channel_manager_link_user_active', 'user_id', 'is_active'),
    )


class ChannelInboundEventLog(Base):
    """ChannelTalk webhook 원본과 파싱 결과 추적"""
    __tablename__ = 'channel_inbound_event_logs'
    
    id = Column(Integer, primary_key=True)
    provider_event_id = Column(String(200), nullable=True, index=True)
    dedupe_key = Column(String(200), nullable=False, unique=True)
    creation_key = Column(String(200), nullable=True, unique=True)
    payload_hash = Column(String(64), nullable=False, index=True)
    raw_payload = Column(JSONColumn, nullable=True)
    chat_type = Column(String(50), nullable=True)
    source_chat_id = Column(String(200), nullable=True, index=True)
    status = Column(String(50), nullable=False, default='received')
    parsed_result = Column(JSONColumn, nullable=True)
    error_reason = Column(Text, nullable=True)
    correlation_id = Column(String(100), nullable=True)
    wave = Column(String(20), nullable=True)
    source_manager_id = Column(String(200), nullable=True)
    created_order_id = Column(Integer, ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    created_task_id = Column(Integer, ForeignKey('order_tasks.id', ondelete='SET NULL'), nullable=True)
    created_order_ref = Column(String(100), nullable=True)
    created_task_ref = Column(String(100), nullable=True)
    received_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    
    created_order = relationship('Order', foreign_keys=[created_order_id])
    created_task = relationship('OrderTask', foreign_keys=[created_task_id])
    
    from sqlalchemy import Index
    __table_args__ = (
        Index('ix_channel_inbound_status_time', 'status', 'received_at'),
    )