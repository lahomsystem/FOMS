import datetime
import uuid
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, func,
    JSON, UniqueConstraint, Index, CheckConstraint, DDL, event, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# Portable UUID: native ``uuid`` on PostgreSQL, ``VARCHAR(36)`` on SQLite/others.
# ``as_uuid=False`` keeps values as canonical str on every dialect so the same
# Python code binds identically under the SQLite test lane and real PostgreSQL.
UUIDColumn = PG_UUID(as_uuid=False).with_variant(String(36), 'sqlite')

# JSON Type Compatibility Layer
JSONColumn = JSON().with_variant(JSONB, 'postgresql')
from db import Base
from foms.services.datetime_kst import format_datetime_kst, now_utc_naive

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
    # REV-00: optimistic-concurrency revision. 초 단위 structured_updated_at 이 구분하지
    # 못하는 동시 저장을 mutation_version 단조 증가로 구분한다. 신규 draft 생성 = 1,
    # 이후 각 Order row/scalar/JSONB/state mutation 이 +1 (helper foms.services.orders.revision).
    mutation_version = Column(Integer, nullable=False, default=1, server_default=text('1'))

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
    # naive DB timestamp = UTC 규약(datetime_kst): created_at 를 UTC-naive 로 통일해
    # 변경감지 윈도(도면 이력 now_utc_naive 와 naive 비교)를 dev/운영 모두 정합시킨다.
    created_at = Column(DateTime, default=now_utc_naive, nullable=False, index=True)

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
    # DRAWING_TRANSFERRED / DRAWING_REVISION / ERP_ORDER_CHANGED / STAGE_CHANGED
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


# ============================================================================
# OPS-APPROVAL-00 — 고위험 ops 승인 인프라 (principal versions + approval requests)
# ============================================================================
#
# SSOT: docs/plans/2026-07-22-foms-full-system-bug-audit-report.md §2.1
#   (line 189 principal versions, line 205 ops_approval_requests, line 207 cross-DB).
#
# 주의: SSOT 프로즈는 principal-version trigger 대상을 ``password_hash|role|team|
# is_active`` 로 기술하지만, 이 코드베이스의 users 테이블 비밀번호 컬럼명은 실제로
# ``password`` (Werkzeug 해시를 저장) 다. trigger 는 실제 컬럼 ``password`` 를 관찰한다.

_PRINCIPAL_VERSION_STATES = ('PENDING', 'APPROVED', 'RESERVED', 'CONSUMED', 'EXPIRED', 'REVOKED')


class SecurityPrincipalVersion(Base):
    """사용자별 보안 principal 버전 (session_version 정본).

    User 는 version 1 로 seed 되고, ``password|role|team|is_active`` 를 바꾸는
    transaction 에서 PostgreSQL trigger 가 정확히 1 증가시킨다. application 은 별도로
    increment 하지 않는다(§2.1 line 189). approval consume 는 승인 시점 version 과
    현재 version 이 같은지를 재확인해 authorization snapshot 무효화를 감지한다.
    """

    __tablename__ = 'security_principal_versions'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    version = Column(Integer, nullable=False, server_default=text('1'))
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class OpsApprovalRequest(Base):
    """고위험 ops 승인 요청 정본 (§2.1 line 205 전 컬럼).

    operator 가 PENDING + 256-bit one-time token 을 만들고(approver 지정 불가),
    active ADMIN 이 화면 재인증으로 APPROVED 로 전이한다. 고위험 CLI 는
    ``--approval-token-file`` 로만 소비하며 same-DB 는 ``FOR UPDATE`` one-time,
    cross-DB 는 5분 RESERVED snapshot 뒤 target unique audit + CONSUMED finalize 다.
    raw token 은 저장하지 않는다 — ``nonce_hash`` = sha256(one-time secret) 만 저장.
    """

    __tablename__ = 'ops_approval_requests'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    operation_type = Column(String(80), nullable=False)
    scope_sha256 = Column(String(64), nullable=False)
    artifact_sha256 = Column(String(64), nullable=True)
    expected_version = Column(Integer, nullable=True)
    expected_generation = Column(Integer, nullable=True)
    nonce_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    state = Column(String(20), nullable=False, server_default='PENDING')
    approved_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    approved_principal_version = Column(Integer, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    reservation_id = Column(UUIDColumn, nullable=True)
    reserved_at = Column(DateTime, nullable=True)
    reservation_expires_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    operator_identity_hash = Column(String(64), nullable=False)
    result_sha256 = Column(String(64), nullable=True)
    row_version = Column(Integer, nullable=False, server_default=text('1'))
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING','APPROVED','RESERVED','CONSUMED','EXPIRED','REVOKED')",
            name='ck_ops_approval_state',
        ),
        Index('ix_ops_approval_state_expires', 'state', 'expires_at'),
    )


class OpsApprovalTargetAudit(Base):
    """cross-DB(TARGET_RESERVED) consume 의 target-DB 측 idempotency/audit row.

    ``(approval_id, reservation_id, operation_scope_sha256)`` unique 로 target
    mutation 이 정확히 1회만 적용되게 만들고, crash retry 시 result hash 대조로
    primary 를 finalize 만 한다(§2.1 line 207). 실제 배포에서는 target(예: WDC) DB 에
    산다 — 테스트에서는 동일 물리 DB 의 별 테이블이 두 논리 DB 를 모델링한다.
    """

    __tablename__ = 'ops_approval_target_audits'

    id = Column(Integer, primary_key=True)
    approval_id = Column(UUIDColumn, nullable=False)
    reservation_id = Column(UUIDColumn, nullable=False)
    operation_scope_sha256 = Column(String(64), nullable=False)
    operation_id = Column(String(80), nullable=False)
    result_sha256 = Column(String(64), nullable=True)
    committed_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            'approval_id', 'reservation_id', 'operation_scope_sha256',
            name='uq_ops_approval_target_audit',
        ),
    )


class OrderMutationReceipt(Base):
    """Order mutation 의 idempotency + read-after-write receipt 정본 (REV-00, §2.4).

    한 mutation 커밋마다 receipt 한 행이 두 역할을 겸한다:

    * **idempotency**: ``(actor_user_id, policy_id, idempotency_key)`` unique. 같은
      key replay 는 저장된 ``response_status``/``response_body`` 를 그대로 돌려주고
      business write/event 는 재수행하지 않는다. ``expires_at`` (커밋+24시간) 이후 같은
      key 는 ``409 IDEMPOTENCY_KEY_EXPIRED`` 다. key 는 UUID 문자열 최대 64자, 비-멱등
      mutation 은 NULL (PostgreSQL 은 NULL 을 서로 distinct 로 취급하므로 dedupe 하지
      않음).
    * **read-after-write**: opaque 128-bit ``read_receipt_id`` UNIQUE 를 발급한다.
      initiator client 가 다음 read 에 ``X-FOMS-Mutation-Receipt`` 로 되보내
      ``read_expires_at`` (커밋+2분) 안에서 자기 write 를 확실히 본다.

    REV-00 은 expiry 의 *의미* 와 ``(expires_at, id)`` purge 인덱스만 소유한다. 실제
    retention purge CLI/schedule 은 REV-CLEANUP-01 이 소유한다(여기서 만들지 않음).
    """

    __tablename__ = 'order_mutation_receipts'

    id = Column(Integer, primary_key=True)  # (expires_at, id) keyset purge 용 surrogate
    read_receipt_id = Column(UUIDColumn, nullable=False, unique=True,
                             default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    policy_id = Column(String(80), nullable=False)
    idempotency_key = Column(String(64), nullable=True)
    scope_hash = Column(String(64), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSONColumn, nullable=False)
    resulting_versions = Column(JSONColumn, nullable=False)  # {order_id: mutation_version}
    read_expires_at = Column(DateTime, nullable=False)       # 커밋 + 2분
    expires_at = Column(DateTime, nullable=False)            # 커밋 + 24시간 (replay window)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            'actor_user_id', 'policy_id', 'idempotency_key',
            name='uq_order_mutation_receipt_idem',
        ),
        Index('ix_omr_actor_read_expires', 'actor_user_id', 'read_expires_at'),
        Index('ix_omr_expires_id', 'expires_at', 'id'),  # REV-CLEANUP-01 purge keyset
    )


class OrderMutationReadResource(Base):
    """Receipt 가 건드린 Order 를 정규화한 child (REV-00, §2.4 line 405).

    단건/batch/copy/import 한 mutation 이 만드는 최대 1000개 resource 를 receipt 당
    한 행씩 담는다. ``read_receipt_id`` 는 부모의 UNIQUE opaque UUID 를 참조하고 PK 는
    ``(read_receipt_id, order_id)`` 다. ``changed_cache_families_json`` 은 호출자(하류
    mutation packet)가 계산한 무효화 family 목록을 그대로 저장한다(REV-00 은 계산하지
    않고 보관만 한다).
    """

    __tablename__ = 'order_mutation_read_resources'

    read_receipt_id = Column(
        UUIDColumn,
        ForeignKey('order_mutation_receipts.read_receipt_id', ondelete='CASCADE'),
        primary_key=True,
    )
    order_id = Column(Integer, ForeignKey('orders.id'), primary_key=True)
    resulting_version = Column(Integer, nullable=False)
    changed_cache_families_json = Column(JSONColumn, nullable=False)

    __table_args__ = (
        Index('ix_omrr_order_receipt', 'order_id', 'read_receipt_id'),
    )


# --- PostgreSQL trigger: principal version seed(+1 on tracked change) ---------
#
# ``create_all`` (SQLite test lane 포함) 와 Alembic 양쪽에서 같은 DDL 을 쓰도록
# security_principal_versions 테이블의 after_create 이벤트에 붙인다. SQLite 에서는
# ``execute_if(dialect='postgresql')`` 로 skip 되어 회귀를 만들지 않는다.

OPS_PRINCIPAL_VERSION_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION foms_principal_version_seed() RETURNS trigger AS $$
BEGIN
    INSERT INTO security_principal_versions (user_id, version, updated_at)
    VALUES (NEW.id, 1, now())
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION foms_principal_version_bump() RETURNS trigger AS $$
BEGIN
    IF (NEW.password IS DISTINCT FROM OLD.password)
       OR (NEW.role IS DISTINCT FROM OLD.role)
       OR (NEW.team IS DISTINCT FROM OLD.team)
       OR (NEW.is_active IS DISTINCT FROM OLD.is_active) THEN
        UPDATE security_principal_versions
           SET version = version + 1, updated_at = now()
         WHERE user_id = NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_principal_version_seed ON users;
CREATE TRIGGER trg_principal_version_seed
    AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION foms_principal_version_seed();

DROP TRIGGER IF EXISTS trg_principal_version_bump ON users;
CREATE TRIGGER trg_principal_version_bump
    AFTER UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION foms_principal_version_bump();
"""

OPS_PRINCIPAL_VERSION_TRIGGER_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_principal_version_bump ON users;
DROP TRIGGER IF EXISTS trg_principal_version_seed ON users;
DROP FUNCTION IF EXISTS foms_principal_version_bump();
DROP FUNCTION IF EXISTS foms_principal_version_seed();
"""

event.listen(
    SecurityPrincipalVersion.__table__,
    'after_create',
    DDL(OPS_PRINCIPAL_VERSION_TRIGGER_SQL).execute_if(dialect='postgresql'),
)
event.listen(
    SecurityPrincipalVersion.__table__,
    'before_drop',
    DDL(OPS_PRINCIPAL_VERSION_TRIGGER_DROP_SQL).execute_if(dialect='postgresql'),
)


# --------------------------------------------------------------------------- #
# CUTOVER-MODE-01: feature cutover fences / markers (§8.2 line 1518)
# --------------------------------------------------------------------------- #
# 15 family SSOT 는 foms/services/cutover/families.py 다. 여기서 import 하면 순환이
# 생기지 않는다(그 모듈은 models 를 참조하지 않음).
from foms.services.security.cutover.families import (  # noqa: E402
    FEATURE_CUTOVER_FAMILIES,
)


class FeatureCutoverFence(Base):
    """family별 무중단 cutover fence (§8.2 line 1518).

    15 family 모두 ``mode=OPEN`` 으로 additive pre-seed 된다. 각 affected business
    mutation 은 tx 시작 직후 이 행을 ``FOR KEY SHARE`` 로 잠가(동시 business 간 공유,
    mark 의 ``FOR UPDATE`` 와 충돌) drain 계약을 만든다. mark/begin/abort CLI 만 mode 를
    전이한다: COMPATIBLE 은 ``OPEN→CUTOVER``, DRAIN 은 ``OPEN→DRAINING→CUTOVER``.
    실제 fence 적용(business mutation 게이트)은 각 family packet 몫이다.
    """

    __tablename__ = 'feature_cutover_fences'

    family = Column(String(40), primary_key=True)
    mode = Column(String(20), nullable=False, server_default='OPEN')
    generation = Column(Integer, nullable=False, server_default=text('0'))
    row_version = Column(Integer, nullable=False, server_default=text('1'))
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "mode IN ('OPEN','DRAINING','CUTOVER')",
            name='ck_feature_cutover_fence_mode',
        ),
    )


class FeatureCutoverMarker(Base):
    """family별 irreversible cutover marker (§8.2 line 1518).

    mark CLI 가 **최초 1회만** insert 한다. update/delete/downgrade 는 PostgreSQL
    trigger 가 DB 레벨에서 거부한다(사후 취소·되돌리기 불가). ``approved_by_admin_user_id``
    는 CLI 입력이 아니라 소비된 approval row 에서 복사한다. runtime consumer 는 이 marker
    를 live request 에서 읽어 post-cutover legacy writer 를 막는다(marker DB 장애는
    fail-open 금지 — 시작 전 503).
    """

    __tablename__ = 'feature_cutover_markers'

    family = Column(String(40), primary_key=True)
    cutover_at = Column(DateTime, nullable=False, server_default=func.now())
    cutover_sha = Column(String(64), nullable=False)
    cutover_generation = Column(Integer, nullable=False)
    minimum_compatibility_generation = Column(Integer, nullable=False)
    readiness_artifact_sha256 = Column(String(64), nullable=False)
    ops_approval_id = Column(UUIDColumn, nullable=False)
    approved_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    row_version = Column(Integer, nullable=False, server_default=text('1'))
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# fence 15 family additive pre-seed — family 만 INSERT 하고 나머지는 server_default 로
# 채운다(sqlite/PostgreSQL 양쪽 유효). create_all(테스트/부트스트랩) 경로용이며 Alembic
# 은 migration 에서 동일 seed 를 별도 수행한다(principal trigger 와 같은 이중 SSOT 패턴).
_FENCE_SEED_VALUES = ",".join(f"('{f}')" for f in FEATURE_CUTOVER_FAMILIES)
FEATURE_CUTOVER_FENCE_SEED_SQL = (
    f"INSERT INTO feature_cutover_fences (family) VALUES {_FENCE_SEED_VALUES}"
)

# marker irreversibility — BEFORE UPDATE OR DELETE 를 RAISE 로 차단(PostgreSQL 전용).
# INSERT 는 허용(최초 mark). SQLite 테스트 lane 은 execute_if 로 skip 되며, 그 lane 은
# marker 갱신을 시도하지 않으므로 회귀가 없다(irreversibility 는 PG 계약 테스트가 검증).
FEATURE_CUTOVER_MARKER_IMMUTABLE_SQL = """
CREATE OR REPLACE FUNCTION foms_feature_cutover_marker_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'feature_cutover_markers is irreversible (UPDATE/DELETE not permitted)'
        USING ERRCODE = 'restrict_violation';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feature_cutover_marker_immutable ON feature_cutover_markers;
CREATE TRIGGER trg_feature_cutover_marker_immutable
    BEFORE UPDATE OR DELETE ON feature_cutover_markers
    FOR EACH ROW EXECUTE FUNCTION foms_feature_cutover_marker_immutable();
"""

FEATURE_CUTOVER_MARKER_IMMUTABLE_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_feature_cutover_marker_immutable ON feature_cutover_markers;
DROP FUNCTION IF EXISTS foms_feature_cutover_marker_immutable();
"""

event.listen(
    FeatureCutoverFence.__table__,
    'after_create',
    DDL(FEATURE_CUTOVER_FENCE_SEED_SQL),
)
event.listen(
    FeatureCutoverMarker.__table__,
    'after_create',
    DDL(FEATURE_CUTOVER_MARKER_IMMUTABLE_SQL).execute_if(dialect='postgresql'),
)
event.listen(
    FeatureCutoverMarker.__table__,
    'before_drop',
    DDL(FEATURE_CUTOVER_MARKER_IMMUTABLE_DROP_SQL).execute_if(dialect='postgresql'),
)


# --------------------------------------------------------------------------- #
# BACKFILL-ARTIFACT-00: encrypted backfill run state machine (§7.3 line 1255-1259)
# --------------------------------------------------------------------------- #
# 모든 remediation audit/backfill 도구가 공유하는 resume run 정본. 실제 domain business
# write 는 각 consumer packet 몫이며, 이 스키마는 run/lease/checkpoint/append-only approval
# 메커니즘만 소유한다. 라이브러리 API 는 foms/services/security/backfill/ 다.
class MaintenanceBackfillRun(Base):
    """backfill resume run 정본 (§7.3 line 1257).

    ``run_id = SHA256(LP(packet_id,phase,manifest_sha256,mapping_sha256))`` 로 결정적이며
    동일 artifact/mapping 에 대한 재개를 한 행으로 모은다. lease token 은 raw 저장 0
    (``lease_token_hash`` = sha256(raw))이고 60초 lease/10초 heartbeat 다. state 는
    PENDING→RUNNING→(PAUSED_APPROVAL|STOPPED_DRIFT)→VERIFYING→DONE 로 전이한다.
    """

    __tablename__ = 'maintenance_backfill_runs'

    run_id = Column(String(64), primary_key=True)
    packet_id = Column(String(80), nullable=False)
    phase = Column(String(80), nullable=False)
    db_instance_id = Column(String(120), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    mapping_sha256 = Column(String(64), nullable=False)
    current_approval_seq = Column(Integer, nullable=False, server_default=text('0'))
    state = Column(String(20), nullable=False, server_default='PENDING')
    lease_owner_hash = Column(String(64), nullable=True)
    lease_token_hash = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    total_rows = Column(Integer, nullable=False, server_default=text('0'))
    completed_rows = Column(Integer, nullable=False, server_default=text('0'))
    last_error_code = Column(String(40), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, server_default=text('1'))

    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING','RUNNING','PAUSED_APPROVAL','STOPPED_DRIFT','VERIFYING','DONE')",
            name='ck_maintenance_backfill_run_state',
        ),
    )


class MaintenanceBackfillCheckpoint(Base):
    """backfill batch 진행 원장 (§7.3 line 1257).

    각 batch 의 business write + completed_rows + heartbeat 와 **같은 tx** 로 append 되어
    resume 시 completed=expected-after / pending=expected-before 정합을 재구성한다. local
    checkpoint 는 authority 0 (drift/tamper 판정은 fingerprint + run 정본).
    """

    __tablename__ = 'maintenance_backfill_checkpoints'

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), ForeignKey('maintenance_backfill_runs.run_id'), nullable=False)
    batch_seq = Column(Integer, nullable=False)
    completed_rows = Column(Integer, nullable=False)
    checkpoint_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('run_id', 'batch_seq', name='uq_maintenance_backfill_checkpoint_seq'),
    )


class MaintenanceBackfillApproval(Base):
    """backfill approval seq append-only 원장 (§7.3 line 1259).

    최초 BACKFILL_APPLY 가 seq1 을, 이후 BACKFILL_REAUTHORIZE 가 seq2.. 를 append 한다.
    기존 row 의 UPDATE/DELETE 는 PostgreSQL trigger 가 DB 레벨에서 거부한다(append-only).
    ``composite_sha256`` 은 승인 시점 source composite 이며 run row_version CAS 와 함께
    stale approval 재사용을 막는다.
    """

    __tablename__ = 'maintenance_backfill_approvals'

    id = Column(Integer, primary_key=True)
    run_id = Column(String(64), ForeignKey('maintenance_backfill_runs.run_id'), nullable=False)
    seq = Column(Integer, nullable=False)
    approval_id = Column(UUIDColumn, nullable=False)
    kind = Column(String(20), nullable=False)
    admin_principal_version = Column(Integer, nullable=False)
    composite_sha256 = Column(String(64), nullable=False)
    reason_code = Column(String(40), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('run_id', 'seq', name='uq_maintenance_backfill_approval_seq'),
        CheckConstraint(
            "kind IN ('APPLY','REAUTHORIZE')",
            name='ck_maintenance_backfill_approval_kind',
        ),
    )


# approval append-only — BEFORE UPDATE OR DELETE 를 RAISE 로 차단(PostgreSQL 전용, marker
# irreversibility 와 동일 패턴). INSERT 만 허용. SQLite 테스트 lane 은 execute_if 로 skip
# 되며 그 lane 은 approval row 갱신을 시도하지 않는다(append-only 는 PG 계약 테스트가 검증).
MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION foms_maintenance_backfill_approval_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'maintenance_backfill_approvals is append-only (UPDATE/DELETE not permitted)'
        USING ERRCODE = 'restrict_violation';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_maintenance_backfill_approval_append_only ON maintenance_backfill_approvals;
CREATE TRIGGER trg_maintenance_backfill_approval_append_only
    BEFORE UPDATE OR DELETE ON maintenance_backfill_approvals
    FOR EACH ROW EXECUTE FUNCTION foms_maintenance_backfill_approval_append_only();
"""

MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_maintenance_backfill_approval_append_only ON maintenance_backfill_approvals;
DROP FUNCTION IF EXISTS foms_maintenance_backfill_approval_append_only();
"""

event.listen(
    MaintenanceBackfillApproval.__table__,
    'after_create',
    DDL(MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_SQL).execute_if(dialect='postgresql'),
)
event.listen(
    MaintenanceBackfillApproval.__table__,
    'before_drop',
    DDL(MAINTENANCE_BACKFILL_APPROVAL_APPEND_ONLY_DROP_SQL).execute_if(dialect='postgresql'),
)
