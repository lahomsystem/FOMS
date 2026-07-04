import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, func, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

# JSON Type Compatibility Layer
JSONColumn = JSON().with_variant(JSONB, 'postgresql')
from db import Base
from foms.services.datetime_kst import format_datetime_kst

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
    # ERP Order (Palantir-style structured data)
    # ============================================
    # ERP Order로 생성된 주문인지 여부 (canonical schema/runtime name).
    is_erp_order = Column(Boolean, nullable=False, default=False, server_default='false', index=True)
    raw_order_text = Column(Text, nullable=True)  # 원문 텍스트(붙여넣기) 보관
    structured_data = Column(JSONColumn, nullable=True)  # 구조화 데이터(JSON / JSONB)
    structured_schema_version = Column(Integer, nullable=False, default=1)
    structured_confidence = Column(String(20), nullable=True)  # high/medium/low
    structured_updated_at = Column(DateTime, nullable=True)
    
    # ERP Order 실측·시공 일정 정규화 컬럼 (D-day SQL 필터용)
    erp_measurement_date = Column(String(10), nullable=True, index=True)   # YYYY-MM-DD
    erp_construction_date = Column(String(10), nullable=True, index=True)  # YYYY-MM-DD

    # Phase D 플랫 컬럼 (DB 레벨 쿼리/페이지네이션 최적화)
    erp_stage_code = Column(String(30), nullable=True, index=True)         # workflow.stage (ex: "RECEIVED", "MEASURE")
    erp_urgent = Column(Boolean, nullable=False, default=False, server_default='false', index=True)  # flags.urgent
    erp_drawing_updated_at = Column(DateTime, nullable=True)               # workflow.stage_updated_at (DRAWING/CONFIRM용)
    erp_stage_updated_at = Column(DateTime, nullable=True, index=True)     # workflow.stage_updated_at (stage transition truth)
    erp_owner_team_code = Column(String(20), nullable=True, index=True)    # assignments.owner_team
    erp_phone_digits = Column(String(20), nullable=True, index=True)       # customer phone digits-only (P1-02 search)

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
        Index('ix_orders_erp_order_active', 'id', postgresql_where=(and_(status != 'DELETED', deleted_at.is_(None), is_erp_order == True))),
    )

    @classmethod
    def not_deleted_filter(cls):
        """Soft-delete 제외 필터. Draft 조회/승격처럼 숨김 주문도 다뤄야 할 때 사용한다."""
        from sqlalchemy import and_
        return and_(cls.status != 'DELETED', cls.deleted_at.is_(None))

    @classmethod
    def erp_draft_filter(cls):
        """ERP Order draft row 필터."""
        from sqlalchemy import and_, or_
        return and_(
            cls.not_deleted_filter(),
            cls.is_erp_order.is_(True),
            or_(
                cls.status == 'DRAFT',
                cls.structured_data[("meta", "draft")].as_boolean().is_(True),
            ),
        )

    @classmethod
    def active_filter(cls):
        """Phase C-0: 운영 화면용 active 주문 필터. soft-delete와 ERP draft row는 제외한다."""
        from sqlalchemy import and_, not_, or_
        return and_(
            cls.not_deleted_filter(),
            not_(and_(
                cls.is_erp_order.is_(True),
                or_(
                    cls.status == 'DRAFT',
                    cls.structured_data[("meta", "draft")].as_boolean().is_(True),
                ),
            )),
        )

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
                    cls.erp_stage_updated_at >= cutoff_date,
                    and_(
                        cls.erp_stage_updated_at.is_(None),
                        cls.structured_updated_at.isnot(None),
                        cls.structured_updated_at >= cutoff_date,
                    ),
                    and_(
                        cls.erp_stage_updated_at.is_(None),
                        cls.structured_updated_at.is_(None),
                        cls.created_at >= cutoff_date,
                    )
                )
            )
        )

    def to_dict(self):
        payload = {}
        for c in self.__table__.columns:
            value = getattr(self, c.name)
            if isinstance(value, datetime.datetime):
                payload[c.name] = format_datetime_kst(value)
            else:
                payload[c.name] = value
        return payload


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
    """주문(ERP Order 등) 첨부파일: 사진/동영상 메타데이터만 저장 (파일 바이너리는 스토리지에 저장)"""
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
            'created_at': format_datetime_kst(self.created_at),
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


class SystemSetting(Base):
    """시스템 전역 설정값 저장용 (JSONB 지원)"""
    __tablename__ = 'system_settings'
    
    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(JSONColumn, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=False)


class SystemBuildStep(Base):
    """빌드/마이그레이션 단계 진행상태 저장 (끊김 시 이어서 실행용)"""
    __tablename__ = 'system_build_steps'

    step_key = Column(String(100), primary_key=True)  # 예: ERP_ORDER_STEP_1_SCHEMA
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
            'created_at': format_datetime_kst(self.created_at),
            'last_login': format_datetime_kst(self.last_login)
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
            'timestamp': format_datetime_kst(self.timestamp)
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
            'created_at': format_datetime_kst(self.created_at),
            'updated_at': format_datetime_kst(self.updated_at)
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
            'joined_at': format_datetime_kst(self.joined_at),
            'last_read_at': format_datetime_kst(self.last_read_at)
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
            'created_at': format_datetime_kst(self.created_at)
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
            'created_at': format_datetime_kst(self.created_at)
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
            'read_at': format_datetime_kst(self.read_at),
            'created_at': format_datetime_kst(self.created_at)
        }


class NotificationEventType:
    """`notification_events.event_type` 표준 상수 (append-only audit).

    새 이벤트 유형 추가 시 여기에 상수를 정의하고 코드에서 문자열 리터럴 대신 사용한다.
    """

    CREATED = 'created'
    STATE_BACKFILLED = 'state_backfilled'
    REALTIME_ATTEMPTED = 'realtime_attempted'
    PUSH_ATTEMPTED = 'push_attempted'
    PUSH_FAILED = 'push_failed'
    PUSH_QUEUE_UNAVAILABLE = 'push_queue_unavailable'
    OPENED = 'opened'
    CLOSED = 'closed'
    READ = 'read'
    ARCHIVE = 'archive'
    ACK = 'ack'
    ESCALATED = 'escalated'
    OPERATOR_ESCALATED = 'operator_escalated'
    RESOLVED = 'resolved'
    LEGACY_READ_AMBIGUOUS = 'legacy_read_ambiguous'


class NotificationDeliveryStatus:
    """`notification_user_states.last_delivery_status` 표준 상수."""

    PENDING = 'pending'
    REALTIME_ATTEMPTED = 'realtime_attempted'
    PUSH_ATTEMPTED = 'push_attempted'
    PUSH_FAILED = 'push_failed'
    QUEUE_UNAVAILABLE = 'queue_unavailable'
    OPENED = 'opened'
    ACK = 'ack'
    RESOLVED = 'resolved'


class NotificationRecipientSource:
    """`notification_user_states.recipient_source` 표준 상수.

    공유 Notification row가 사용자에게 도달한 경로를 기록한다.
    """

    TARGET_USER = 'target_user'
    TARGET_TEAM = 'target_team'
    TARGET_MANAGER_NAME = 'target_manager_name'
    TARGET_ALL = 'target_all'
    LEGACY_BACKFILL = 'legacy_backfill'


class NotificationUserState(Base):
    """공유 Notification 1건을 수신자별 상태로 감싸는 per-user row.

    하나의 Notification이 여러 사용자에게 도달할 때 각 사용자의 읽음/보관/확인/해결
    상태를 독립적으로 추적한다. (notification_id, user_id)는 유일하다.
    """

    __tablename__ = 'notification_user_states'

    id = Column(Integer, primary_key=True)
    notification_id = Column(
        Integer, ForeignKey('notifications.id', ondelete='CASCADE'), nullable=False
    )
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    # 수신 경로: NotificationRecipientSource 상수 중 하나
    recipient_source = Column(String(30), nullable=False)

    # per-user 상태 타임스탬프 (전부 nullable)
    read_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    ack_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    escalated_at = Column(DateTime, nullable=True)
    last_opened_at = Column(DateTime, nullable=True)

    # 마지막 전달 상태: NotificationDeliveryStatus 상수 중 하나
    last_delivery_status = Column(
        String(30), nullable=False, default='pending', server_default='pending'
    )

    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
        nullable=False,
    )

    notification = relationship('Notification', foreign_keys=[notification_id])
    user = relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint(
            'notification_id', 'user_id', name='uq_notification_user_states_notif_user'
        ),
        Index(
            'ix_notification_user_states_user_inbox',
            'user_id',
            'archived_at',
            'read_at',
            'notification_id',
        ),
    )


class NotificationEvent(Base):
    """알림 상태 변화의 append-only 감사 로그.

    상태 전이(생성/전달 시도/열람/읽음/보관/확인/해결/에스컬레이션 등)를 불변 기록으로
    남긴다. 절대 UPDATE/DELETE 하지 않는다(파티션/정리는 별도 정책).
    """

    __tablename__ = 'notification_events'

    id = Column(Integer, primary_key=True)
    notification_id = Column(
        Integer, ForeignKey('notifications.id', ondelete='CASCADE'), nullable=False
    )
    user_state_id = Column(
        Integer, ForeignKey('notification_user_states.id'), nullable=True
    )
    actor_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    recipient_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    # NotificationEventType 상수 중 하나
    event_type = Column(String(40), nullable=False)
    channel = Column(String(20), nullable=True)
    endpoint_hash = Column(String(64), nullable=True)
    request_id = Column(String(64), nullable=True)
    metadata_json = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        Index('ix_notification_events_notif_created', 'notification_id', 'created_at'),
        Index(
            'ix_notification_events_recipient_type_created',
            'recipient_user_id',
            'event_type',
            'created_at',
        ),
        Index('ix_notification_events_actor_created', 'actor_user_id', 'created_at'),
        Index('ix_notification_events_endpoint_created', 'endpoint_hash', 'created_at'),
    )


class NotificationPushSubscription(Base):
    """사용자별 Web Push 구독 엔드포인트 (Phase 0A 기반, 발송은 Phase 0B+)."""

    __tablename__ = 'notification_push_subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=True)
    auth = Column(Text, nullable=True)
    platform = Column(String(30), nullable=True)
    browser = Column(String(50), nullable=True)
    device_label = Column(String(100), nullable=True)
    permission_state = Column(String(20), nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
        nullable=False,
    )

    user = relationship('User', foreign_keys=[user_id])


# ============================================
# ChannelTalk 연동 모델 (Phase 0)
# ============================================

# ============================================
# 견적서/계약서 모델
# ============================================

class OrderEstimate(Base):
    """견적서(계약서) — 주문별 N건 발급 가능.

    견적번호 형식: YYYYMMDD_N  (해당 날짜의 순번)
    items JSON 예시:
        [{"product_name": "무몰딩 여닫이", "spec": "3090X700X2408",
          "color": "포그그레이", "quantity": 1, "unit_price": 550000,
          "amount": 550000}]
    """
    __tablename__ = 'order_estimates'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)

    estimate_number = Column(String(50), nullable=False, unique=True)

    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    site_address = Column(Text, nullable=True)

    estimate_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    construction_date = Column(String(10), nullable=True)

    manager_name = Column(String(100), nullable=True)
    manager_phone = Column(String(50), nullable=True)

    items = Column(JSONColumn, nullable=False, default=list)

    total_amount = Column(Integer, nullable=False, default=0)
    deposit_amount = Column(Integer, nullable=True, default=0)
    balance_amount = Column(Integer, nullable=True, default=0)

    payment_info = Column(JSONColumn, nullable=True)

    status = Column(String(20), nullable=False, default='DRAFT')
    notes = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.now, nullable=False)

    order = relationship('Order', foreign_keys=[order_id])
    created_by = relationship('User', foreign_keys=[created_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'estimate_number': self.estimate_number,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'site_address': self.site_address,
            'estimate_date': self.estimate_date,
            'construction_date': self.construction_date,
            'manager_name': self.manager_name,
            'manager_phone': self.manager_phone,
            'items': self.items or [],
            'total_amount': self.total_amount,
            'deposit_amount': self.deposit_amount,
            'balance_amount': self.balance_amount,
            'payment_info': self.payment_info,
            'status': self.status,
            'notes': self.notes,
            'created_by_user_id': self.created_by_user_id,
            'created_at': format_datetime_kst(self.created_at),
            'updated_at': format_datetime_kst(self.updated_at),
        }


class OrderDraft(Base):
    """모바일 wizard 자동저장 draft (TTL 7일, P0-00B)."""

    __tablename__ = 'order_drafts'

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    order_id = Column(
        Integer,
        ForeignKey('orders.id', ondelete='CASCADE'),
        nullable=True,
        index=True,
    )
    draft_key = Column(String(64), nullable=False)
    step = Column(Integer, nullable=False, default=1)
    payload = Column(JSONColumn, nullable=False, default=dict)
    schema_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'draft_key', name='uq_order_drafts_user_key'),
    )


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
