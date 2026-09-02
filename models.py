import datetime
import uuid
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, Date, DateTime, Float,
    Numeric, ForeignKey, func, JSON, UniqueConstraint, Index, CheckConstraint,
    DDL, event, text,
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
    erp_phone_digits = Column(String(64), nullable=True, index=True)       # customer phone digits-only (P1-02 search, 다전화 주문 22~23자)
    # AS-AXIS-01: AS 축(as_lifecycle) 의 SQL 조회용 플랫 투영. NULL = AS 이력 없음.
    # 값 도메인은 state_axes.AS_VALUES 와 같다(RECEIVED/IN_PROGRESS/COMPLETED).
    # status 컬럼은 overlay projection 이라 외부 write 로 덮이면 AS 목록이 증발했다(2026-08-14 사고).
    as_axis_status = Column(String(16), nullable=True)                     # as_lifecycle 현재 cycle 상태

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
        # AS 행만 담는 부분 인덱스(AS 이력 없는 대다수 행은 NULL 이라 인덱스에 안 들어간다).
        Index('ix_orders_as_axis_status', 'as_axis_status', postgresql_where=(as_axis_status.isnot(None))),
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
    item_index = Column(Integer, nullable=True)                # e.g., 0, 1 ... (for items array, legacy provenance)
    # ITEM-ID-00: 아이템-스코프 일정의 결합 SSOT = 안정 UUID(order_item_identities.id).
    # date-sync(order_date_sync)가 rebuild 시 registry 에서 이 UUID 를 다시 채운다(위치
    # 인덱스가 아니라 UUID 로 결합). expand 단계라 nullable.
    item_id = Column(
        UUIDColumn, ForeignKey('order_item_identities.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )

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
    item_index = Column(Integer, nullable=True, default=None, index=True)  # 제품 항목 인덱스 (None=공통, legacy provenance)
    # ITEM-ID-00: 아이템 결합 SSOT = 안정 UUID(order_item_identities.id). item_index 는
    # legacy positional provenance 로만 남고, 결합/authz 판정은 이 UUID 를 쓴다. expand
    # 단계라 nullable 이며, ambiguous 0건 backfill 완료 전에는 NOT NULL enforcement 를 걸지 않는다.
    item_id = Column(
        UUIDColumn, ForeignKey('order_item_identities.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    # AS-FRESH-01: AS 첨부 ↔ 타임라인 기록(structured_data.shipment.as_log 항목 id) 결합.
    # JSONB 안의 항목을 가리키므로 FK 가 아니라 약한 참조다 — 존재 검증은 등록 라우트 소관.
    # 이 축이 "이 기록의 사진" 렌더와 PUSH 회차 필터의 근거이며, 기존 첨부는 NULL 로 남는다
    # (소급 배정 금지 — 추정 배정은 오귀속을 만든다).
    as_log_id = Column(String(64), nullable=True)
    # AS-SORT-01: 같은 기록(as_log_id) 안에서의 표시·전송 순서. 작을수록 앞.
    # NULL = 레거시(소급 배정 금지) → 읽기는 id ASC 폴백. 병렬 업로드가 id 순서를
    # 뒤섞으므로 순서는 이 컬럼이 정본이다.
    sort_order = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=False, default=0)

    storage_key = Column(String(500), nullable=False)  # static/uploads 기준 key 또는 R2 key
    thumbnail_key = Column(String(500), nullable=True)  # 이미지 썸네일 key (선택)

    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)  # 업로더 (AS 재업로드 시 본인 것만 삭제)

    # ATTACH-LIFE-01(T4): hard delete → tombstone(soft delete). 삭제는 이 두 컬럼만 채우고
    # row/R2 object 는 남긴다 — R2 blob 은 STORAGE_DELETE outbox 가 유예 후 지운다.
    # 84 파일 사용처는 수동 필터 대신 전역 do_orm_execute 필터
    # (:mod:`foms.services.attachment_visibility`)가 ``deleted_at IS NULL`` 을 기본 적용한다.
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_user_id = Column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    order = relationship('Order', foreign_keys=[order_id])

    __table_args__ = (
        # ATTACH-LIFE-01: canonical 파일 라우트(/api/files/view|download/orders/...)가 요청
        # key 로 tombstone 여부를 1쿼리 판정한다(매 파일 요청 = hot path). 조회는
        # ``storage_key = :k OR thumbnail_key = :k`` 라 두 인덱스가 모두 있어야
        # BitmapOr 로 풀리고 Seq Scan 을 피한다.
        Index('ix_order_attachments_storage_key', 'storage_key'),
        Index('ix_order_attachments_thumbnail_key', 'thumbnail_key'),
        # AS 회차 차트가 "이 주문 첨부를 기록별로" 1쿼리 배치 조회한다(N+1 금지) —
        # order_id 선행 복합이어야 그 조회가 인덱스로 풀린다.
        Index('ix_order_attachments_as_log_id', 'order_id', 'as_log_id'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'filename': self.filename,
            'file_type': self.file_type,
            'category': self.category or 'measurement',
            'item_index': self.item_index,
            'as_log_id': self.as_log_id,
            'sort_order': self.sort_order,
            'file_size': self.file_size,
            'storage_key': self.storage_key,
            'thumbnail_key': self.thumbnail_key,
            'created_at': format_datetime_kst(self.created_at),
            'user_id': self.user_id,
            'deleted_at': format_datetime_kst(self.deleted_at) if self.deleted_at else None,
        }


class OrderItemIdentity(Base):
    """주문 아이템의 DB-global UUID identity registry (ITEM-ID-00, §5.2).

    주문 아이템은 오늘 ``structured_data['items']`` 배열의 **위치 인덱스**(``item_index``)
    로만 식별된다 — 아이템 추가/삭제/재정렬에 인덱스가 밀리면 첨부(:class:`OrderAttachment`)
    ·일정(:class:`OrderScheduleDate`) 결합이 조용히 깨진다. 이 registry 는 아이템마다
    **안정 UUID identity row** 를 발급해, 첨부/일정이 위치 인덱스가 아니라 이 UUID
    (``item_id``)를 가리키게 한다.

    계약(§5.2 ITEM-ID-00):

    * **DB-global unique**: ``id`` 는 UUID PK 로 전 DB 유일하다.
    * **order binding**: 모든 identity 는 한 주문(``order_id`` FK)에 묶인다.
    * **immutable / no-reuse**: 발급된 UUID 는 다른 아이템에 재발급되지 않는다. 아이템이
      사라지면 hard delete 하지 않고 tombstone(``is_active=False`` + ``retired_at``)으로
      은퇴시키며, 은퇴한 UUID 는 재활성화하지 않는다(같은 슬롯은 **새 UUID** 로 재발급).
    * ``item_index`` 는 발급 시점 아이템 슬롯 좌표(provenance·backfill 멱등 키)일 뿐
      **런타임 authorization/link 근거로 쓰지 않는다** — 첨부/일정 결합은 오직 UUID 다.

    ``uq_order_item_identity_active`` (partial unique)로 한 주문의 한 슬롯에 활성 identity
    는 최대 1개다 — 중복 발급을 막고 backfill 을 멱등하게 만든다. tombstone 뒤 같은 슬롯은
    새 UUID 로 다시 발급할 수 있다. DDL 은 migration(``item_id_00``)과 SSOT 를 공유한다
    (create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'order_item_identities'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    # 발급 시점 아이템 슬롯 좌표(provenance/backfill 멱등 키). 런타임 auth/link 근거 아님.
    item_index = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    retired_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # 한 주문의 한 아이템 슬롯에 활성 identity 는 최대 1개(중복 발급 방지·backfill 멱등).
        # tombstone(is_active=False) 뒤 같은 슬롯은 새 UUID 로 재발급 가능.
        Index(
            'uq_order_item_identity_active', 'order_id', 'item_index',
            unique=True, postgresql_where=text('is_active'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'item_index': self.item_index,
            'is_active': self.is_active,
            'created_at': format_datetime_kst(self.created_at),
            'retired_at': format_datetime_kst(self.retired_at) if self.retired_at else None,
        }


class ProductionRun(Base):
    """생산 실행(production run)의 DB-global UUID run registry (PRODUCTION-BACKFILL-00, §5.2).

    생산 공정은 오늘 주문마다 **단일 flat** ``structured_data['production']``(단일 steps
    리스트·단일 defects 리스트·rework count)로만 기록돼, 재제작(rework)마다 새 실행이 열려도
    이전 실행의 step/defect scope 경계가 남지 않는다. 이 registry 는 실행마다 **안정 UUID
    run row** 를 발급해, step/defect scope 를 실행 단위로 귀속한다
    (:func:`~foms.services.orders.state_axes.read_current_production_run` 의 canonical
    target — ``production.runs[]`` + ``current_run_id`` — 과 shape 정합).

    계약(§5.2 PRODUCTION-BACKFILL-00):

    * **DB-global unique**: ``id`` 는 UUID PK(= ``run_id``)로 전 DB 유일하다.
    * **order binding**: 모든 run 은 한 주문(``order_id`` FK)에 묶인다.
    * **status**: ``IN_PROGRESS`` | ``COMPLETED`` | ``SUPERSEDED`` (§2.2 read-model target).
    * **flat 보존**: run 의 ``steps``/``defects`` 는 flat ``structured_data['production']``
      의 **복제 스냅샷**이다 — backfill 은 flat 을 삭제하지 않고 복제만 한다(전이 활성화는
      하류 STATE-PROD-01 소관).

    ``uq_production_run_current`` (partial unique)로 한 주문에 current run 은 최대 1개다 —
    ``current_run_id`` 포인터의 DB 표현이자 중복 발급 방지·backfill 멱등 키다. 종결된
    run(``is_current=False``, COMPLETED/SUPERSEDED)은 이력으로 남는다. DDL 은
    migration(``production_backfill_00``)과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'production_runs'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    status = Column(String(20), nullable=False)  # IN_PROGRESS|COMPLETED|SUPERSEDED
    # legacy 생산 시작 시각(provenance) — flat workflow.history 의 PRODUCTION 진입 시각.
    started_at = Column(DateTime, nullable=True)
    # 실행 단위 step/defect scope 스냅샷(flat production.steps/defects 의 복제 — flat 보존).
    steps = Column(JSONColumn, nullable=True)
    defects = Column(JSONColumn, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True, server_default='true')
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 한 주문의 current run 은 최대 1개(current_run_id 포인터 DB 표현·backfill 멱등).
        # 종결된 run(is_current=False)은 여러 개 이력으로 남을 수 있다.
        Index(
            'uq_production_run_current', 'order_id',
            unique=True, postgresql_where=text('is_current'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'status': self.status,
            'started_at': format_datetime_kst(self.started_at) if self.started_at else None,
            'steps': self.steps,
            'defects': self.defects,
            'is_current': self.is_current,
            'created_at': format_datetime_kst(self.created_at),
        }


class OrderASCycle(Base):
    """AS(A/S) 실행 cycle 의 DB-global UUID registry (AS-BACKFILL-00, §5.2).

    AS 는 오늘 주문마다 flat ``structured_data['as_info']`` 리스트(접수/방문일정/완료가 한
    entry 에 뭉쳐 있고, 재접수마다 entry 가 append 됨)와 flat ``order.status``/
    ``workflow.history`` 의 AS 전이로만 기록된다 — 실행별 cycle 경계·current cycle 포인터가
    없다. 이 registry 는 AS 발생마다 **안정 UUID cycle row** 를 발급해, transition(시작)·
    schedule(방문일)·completion(완료)·classification(사유/설명)을 cycle 단위로 귀속하고,
    :data:`~foms.services.orders.state_axes.AS_VALUES`(``RECEIVED|IN_PROGRESS|COMPLETED``)
    read-model 과 shape 를 정합시킨다(주문당 current cycle 0/1).

    계약(§5.2 AS-BACKFILL-00):

    * **DB-global unique**: ``id`` 는 UUID PK(= ``cycle_id``)로 전 DB 유일하다.
    * **order binding**: 모든 cycle 은 한 주문(``order_id`` FK)에 묶인다.
    * **status**: ``RECEIVED`` | ``IN_PROGRESS`` | ``COMPLETED`` (§2.2 AS axis read-model).
    * **flat 보존**: cycle 컬럼은 flat ``as_info`` entry 의 **복제 스냅샷**이다 — backfill 은
      flat 을 삭제/재작성하지 않고 복제만 한다. legacy stage rewrite·전이(create/complete)
      활성화는 하류 STATE-AS-01 소관이므로 이 registry 는 runtime 의미 변경이 0 이다.
    * ``legacy_as_id`` 는 발급 시점 ``as_info`` entry id(provenance·backfill 멱등 키)일 뿐
      런타임 근거로 쓰지 않는다.

    ``uq_order_as_cycle_current`` (partial unique)로 한 주문에 current cycle 은 최대 1개다 —
    ``current_cycle_id`` 포인터의 DB 표현이자 "current cycle 0/1" 불변식의 강제다. 종결된
    cycle(``is_current=False``, COMPLETED)은 이력으로 여러 개 남는다.
    ``uq_order_as_cycle_legacy`` (partial unique)는 한 주문의 한 ``legacy_as_id`` 에 cycle 을
    최대 1개로 강제해 backfill 을 멱등하게 만든다. DDL 은 migration(``as_backfill_00``)과 SSOT
    를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'order_as_cycles'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    status = Column(String(20), nullable=False)  # RECEIVED|IN_PROGRESS|COMPLETED
    # 발급 시점 as_info entry id(provenance·backfill 멱등 키). 런타임 근거 아님.
    legacy_as_id = Column(Integer, nullable=True)
    # transition(시작): flat as_info entry 의 started_at/started_by 스냅샷.
    started_at = Column(DateTime, nullable=True)
    started_by = Column(String(120), nullable=True)
    # classification: AS 사유/설명 스냅샷.
    reason = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    # schedule: AS 방문일/시각 스냅샷(legacy 문자열 원문 보존 — 파싱 유실 방지).
    visit_date = Column(String(32), nullable=True)
    visit_time = Column(String(32), nullable=True)
    # completion: 완료 시각/담당/메모 스냅샷.
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(String(120), nullable=True)
    completion_note = Column(Text, nullable=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default='false')
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 한 주문의 current(열린) cycle 은 최대 1개("current cycle 0/1" 불변식의 DB 표현).
        # 종결된 cycle(is_current=False)은 여러 개 이력으로 남을 수 있다.
        Index(
            'uq_order_as_cycle_current', 'order_id',
            unique=True, postgresql_where=text('is_current'),
        ),
        # 한 주문의 한 legacy as_info entry 에 cycle 은 최대 1개(중복 발급 방지·backfill 멱등).
        # legacy_as_id IS NULL(비-legacy)은 이 제약 밖(향후 STATE-AS-01 발급분).
        Index(
            'uq_order_as_cycle_legacy', 'order_id', 'legacy_as_id',
            unique=True, postgresql_where=text('legacy_as_id IS NOT NULL'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'status': self.status,
            'legacy_as_id': self.legacy_as_id,
            'started_at': format_datetime_kst(self.started_at) if self.started_at else None,
            'started_by': self.started_by,
            'reason': self.reason,
            'description': self.description,
            'visit_date': self.visit_date,
            'visit_time': self.visit_time,
            'completed_at': format_datetime_kst(self.completed_at) if self.completed_at else None,
            'completed_by': self.completed_by,
            'completion_note': self.completion_note,
            'is_current': self.is_current,
            'created_at': format_datetime_kst(self.created_at),
        }


class DrawingRevision(Base):
    """도면 개정(drawing revision)의 DB-global UUID registry (DRAWING-REVISION-BACKFILL-00, §5.2).

    도면 이력은 오늘 주문마다 flat ``structured_data['drawing_transfer_history']``
    (TRANSFER/REQUEST_REVISION/CONFIRM_RECEIPT 가 한 리스트에 뒤섞여 append 됨)·
    ``drawing_status``·``drawing_current_files``·``blueprint.customer_confirmed`` 로만
    기록돼, 개정별 안정 identity 도 current/receipt/customer-confirm 포인터도 남지 않는다.
    이 registry 는 TRANSFER(도면 전달)마다 **안정 UUID revision row** 를 발급해, 전달·수령
    확인(receipt)·고객 확인(customer-confirm) 스냅샷을 개정 단위로 귀속하고,
    :func:`~foms.services.orders.state_axes.read_drawing_revision_registry` 의 canonical
    포인터(``current_revision_id`` / ``receipt_revision_id`` /
    ``customer_confirmed_revision_id``)와 shape 를 정합시킨다(주문당 각 포인터 0/1).

    계약(§5.2 DRAWING-REVISION-BACKFILL-00):

    * **DB-global unique**: ``id`` 는 UUID PK(= ``revision_id``)로 전 DB 유일하다.
    * **order binding**: 모든 revision 은 한 주문(``order_id`` FK)에 묶인다.
    * **status**: ``TRANSFERRED`` | ``RETURNED`` | ``CONFIRMED`` | ``SUPERSEDED``.
    * **flat 보존**: revision 컬럼은 flat ``drawing_transfer_history`` entry·``blueprint``
      의 **복제 스냅샷**이다 — backfill 은 flat/attachment 를 삭제/재작성하지 않고 복제만
      한다. 전이(개정 발급/전달) 활성화는 하류 STATE-DRAWING-01 소관이라 runtime 의미
      변경이 0 이다.
    * ``legacy_seq`` 는 발급 근거 ``drawing_transfer_history`` 인덱스(provenance·backfill
      멱등 키)일 뿐 런타임 근거로 쓰지 않는다.

    ``uq_drawing_revision_current`` / ``_receipt`` / ``_customer`` (partial unique)로 한 주문의
    current / receipt / customer-confirmed revision 은 각각 최대 1개다 — 세 canonical 포인터의
    DB 표현이다. 종결된(``is_current=False``) 개정은 SUPERSEDED 이력으로 남는다.
    ``uq_drawing_revision_legacy`` (partial unique)는 한 주문의 한 legacy transfer entry 에
    revision 을 최대 1개로 강제해 backfill 을 멱등하게 만든다. DDL 은
    migration(``drawing_revision_00``)과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'drawing_revisions'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    status = Column(String(20), nullable=False)  # TRANSFERRED|RETURNED|CONFIRMED|SUPERSEDED
    # 개정 순번(주문 내 TRANSFER 발생 순 1-based) — provenance·정렬.
    revision_no = Column(Integer, nullable=False)
    # 전달(발급) 스냅샷: flat TRANSFER entry 의 transferred_at/by_user_name/note/files.
    transferred_at = Column(DateTime, nullable=True)
    transferred_by = Column(String(120), nullable=True)
    note = Column(Text, nullable=True)
    files = Column(JSONColumn, nullable=True)
    # receipt(도면 수령 확인) 스냅샷: flat CONFIRM_RECEIPT entry 의 at/by_user_name.
    receipt_confirmed_at = Column(DateTime, nullable=True)
    receipt_confirmed_by = Column(String(120), nullable=True)
    # customer-confirm 스냅샷: flat blueprint.confirmed_at/confirmed_by.
    customer_confirmed_at = Column(DateTime, nullable=True)
    customer_confirmed_by = Column(String(120), nullable=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default='false')
    is_receipt = Column(Boolean, nullable=False, default=False, server_default='false')
    is_customer_confirmed = Column(Boolean, nullable=False, default=False, server_default='false')
    # 발급 근거 drawing_transfer_history 인덱스(provenance·backfill 멱등 키). 런타임 근거 아님.
    legacy_seq = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 한 주문의 current revision 은 최대 1개(current_revision_id 포인터 DB 표현).
        Index(
            'uq_drawing_revision_current', 'order_id',
            unique=True, postgresql_where=text('is_current'),
        ),
        # 한 주문의 receipt revision(수령 확인분)은 최대 1개(receipt_revision_id 포인터).
        Index(
            'uq_drawing_revision_receipt', 'order_id',
            unique=True, postgresql_where=text('is_receipt'),
        ),
        # 한 주문의 customer-confirmed revision 은 최대 1개(customer_confirmed_revision_id 포인터).
        Index(
            'uq_drawing_revision_customer', 'order_id',
            unique=True, postgresql_where=text('is_customer_confirmed'),
        ),
        # 한 주문의 한 legacy transfer entry 에 revision 은 최대 1개(중복 발급 방지·backfill 멱등).
        Index(
            'uq_drawing_revision_legacy', 'order_id', 'legacy_seq',
            unique=True, postgresql_where=text('legacy_seq IS NOT NULL'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'status': self.status,
            'revision_no': self.revision_no,
            'transferred_at': format_datetime_kst(self.transferred_at) if self.transferred_at else None,
            'transferred_by': self.transferred_by,
            'note': self.note,
            'files': self.files,
            'receipt_confirmed_at': format_datetime_kst(self.receipt_confirmed_at) if self.receipt_confirmed_at else None,
            'receipt_confirmed_by': self.receipt_confirmed_by,
            'customer_confirmed_at': format_datetime_kst(self.customer_confirmed_at) if self.customer_confirmed_at else None,
            'customer_confirmed_by': self.customer_confirmed_by,
            'is_current': self.is_current,
            'is_receipt': self.is_receipt,
            'is_customer_confirmed': self.is_customer_confirmed,
            'legacy_seq': self.legacy_seq,
            'created_at': format_datetime_kst(self.created_at),
        }


class DrawingRevisionRequest(Base):
    """도면 수정요청(revision request)의 DB-global UUID registry (DRAWING-REVISION-BACKFILL-00, §5.2).

    수정요청은 오늘 주문마다 flat ``drawing_transfer_history`` 의 ``REQUEST_REVISION`` entry·
    ``drawing_status == 'RETURNED'`` 로만 기록돼, 요청별 안정 identity 도 "열린 요청" 포인터도
    남지 않는다. 이 registry 는 REQUEST_REVISION 마다 **안정 UUID request row** 를 발급해
    요청 스냅샷(대상 도면 key·참고 파일·메모)을 요청 단위로 귀속하고,
    :func:`~foms.services.orders.state_axes.read_drawing_revision_registry` 의
    ``current_revision_request_id`` 포인터와 shape 를 정합시킨다.

    계약(§5.2 DRAWING-REVISION-BACKFILL-00):

    * **DB-global unique**: ``id`` 는 UUID PK(= ``request_id``)로 전 DB 유일하다.
    * **order binding**: 모든 request 는 한 주문(``order_id`` FK)에 묶인다.
    * ``revision_id`` 는 요청 대상 revision(발급 시점 current revision) 의 **soft link**
      (FK 아님 — 형제 :class:`DrawingRevision` 과 느슨 결합). None 은 대상 미상.
    * **status**: ``OPEN`` | ``RESOLVED``. flat REQUEST_REVISION → open, 후속 TRANSFER 로
      해소된 과거 요청 → resolved 이력.
    * **flat 보존**: request 컬럼은 flat entry 의 **복제 스냅샷**이다 — backfill 은
      flat/attachment 를 삭제하지 않는다.

    ``uq_drawing_request_open`` (partial unique)로 한 주문의 열린 요청은 최대 1개다 —
    "duplicate open request 0" 불변식의 DB 강제이자 ``current_revision_request_id`` 포인터의
    표현이다. ``uq_drawing_request_legacy`` (partial unique)는 backfill 멱등을 보장한다.
    DDL 은 migration(``drawing_revision_00``)과 SSOT 를 공유한다.
    """

    __tablename__ = 'drawing_revision_requests'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    # 요청 대상 revision(발급 시점 current revision) 의 soft link — FK 아님(느슨 결합).
    revision_id = Column(UUIDColumn, nullable=True)
    status = Column(String(20), nullable=False)  # OPEN|RESOLVED
    # 요청 스냅샷: flat REQUEST_REVISION entry 의 at/by_user_name/note/files/대상 도면 key.
    requested_at = Column(DateTime, nullable=True)
    requested_by = Column(String(120), nullable=True)
    note = Column(Text, nullable=True)
    files = Column(JSONColumn, nullable=True)
    target_drawing_keys = Column(JSONColumn, nullable=True)
    is_open = Column(Boolean, nullable=False, default=False, server_default='false')
    # 발급 근거 drawing_transfer_history 인덱스(provenance·backfill 멱등 키).
    legacy_seq = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 한 주문의 열린(open) 수정요청은 최대 1개("duplicate open request 0" DB 강제).
        Index(
            'uq_drawing_request_open', 'order_id',
            unique=True, postgresql_where=text('is_open'),
        ),
        # 한 주문의 한 legacy request entry 에 request 는 최대 1개(중복 발급 방지·backfill 멱등).
        Index(
            'uq_drawing_request_legacy', 'order_id', 'legacy_seq',
            unique=True, postgresql_where=text('legacy_seq IS NOT NULL'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'revision_id': self.revision_id,
            'status': self.status,
            'requested_at': format_datetime_kst(self.requested_at) if self.requested_at else None,
            'requested_by': self.requested_by,
            'note': self.note,
            'files': self.files,
            'target_drawing_keys': self.target_drawing_keys,
            'is_open': self.is_open,
            'legacy_seq': self.legacy_seq,
            'created_at': format_datetime_kst(self.created_at),
        }


class OrderConstructionAttempt(Base):
    """시공(construction) 실행 attempt 의 DB-global UUID registry (CONSTRUCTION-BACKFILL-00, §5.2).

    시공은 오늘 주문마다 flat ``workflow.history`` 의 ``시공 시작`` 진입·
    ``structured_data['construction_fail_history']`` (시공 불가 재작업 리스트)·
    ``construction.evidence`` (before/after/서명)·``schedule.construction`` (시공 예정일)·
    그리고 시공 완료 시 ``order.status``/``workflow.stage`` 의 ``COMPLETED`` 전이로만
    기록된다 — attempt 별 경계도 current attempt 포인터도 남지 않는다. 이 registry 는 시공
    attempt 마다 **안정 UUID attempt row** 를 발급해 schedule(예정일)·transition(시작)·
    completion(완료)·classification(시공 불가 사유) 스냅샷을 attempt 단위로 귀속하고,
    :data:`~foms.services.orders.state_axes.CONSTRUCTION_VALUES`
    (``IN_PROGRESS|READY|COMPLETED|REWORKED``) read-model 과 shape 를 정합시킨다(주문당
    current attempt 0/1).

    계약(§5.2 CONSTRUCTION-BACKFILL-00):

    * **DB-global unique**: ``id`` 는 UUID PK(= ``attempt_id``)로 전 DB 유일하다.
    * **order binding**: 모든 attempt 는 한 주문(``order_id`` FK)에 묶인다.
    * **status**: ``IN_PROGRESS`` | ``READY`` | ``COMPLETED`` | ``REWORKED``.
    * **flat 보존**: attempt 컬럼은 flat 시공 데이터의 **복제 스냅샷**이다 — backfill 은
      flat 을 삭제/재작성하지 않고 복제만 한다. 시공 완료(직접 COMPLETED)의 자동 추론은
      금지되고(불명확 → 수동 CSV), 전이(시작/완료) 활성화는 하류 STATE-CONST-CS 소관이므로
      이 registry 는 runtime 의미 변경이 0 이다.
    * ``legacy_seq`` 는 발급 근거 시공 시작 ordinal(provenance·backfill 멱등 키)일 뿐
      런타임 근거로 쓰지 않는다.

    ``uq_construction_attempt_current`` (partial unique)로 한 주문에 current attempt 는 최대
    1개다 — ``current_attempt_id`` 포인터의 DB 표현이자 "current attempt 0/1" 불변식의
    강제다. 종결된 attempt(``is_current=False``, COMPLETED/REWORKED)은 이력으로 여러 개
    남는다. ``uq_construction_attempt_legacy`` (partial unique)는 한 주문의 한
    ``legacy_seq`` 에 attempt 를 최대 1개로 강제해 backfill 을 멱등하게 만든다. DDL 은
    migration(``construction_backfill_00``)과 SSOT 를 공유한다(create_all 테스트 lane 동일
    스키마).
    """

    __tablename__ = 'order_construction_attempts'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    status = Column(String(20), nullable=False)  # IN_PROGRESS|READY|COMPLETED|REWORKED
    # 발급 시점 시공 시작 ordinal(provenance·backfill 멱등 키). 런타임 근거 아님.
    legacy_seq = Column(Integer, nullable=True)
    # schedule 스냅샷 — 시공 예정일(schedule.construction.date, legacy 문자열 원문 보존).
    scheduled_date = Column(String(32), nullable=True)
    # transition(시작) 스냅샷 — workflow.history "시공 시작" entry.
    started_at = Column(DateTime, nullable=True)
    started_by = Column(String(120), nullable=True)
    # completion 스냅샷 — 완료 시각/담당/메모(하류 STATE-CONST-CS 발급분).
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(String(120), nullable=True)
    completion_note = Column(Text, nullable=True)
    # classification 스냅샷 — REWORKED attempt 의 시공 불가 사유/상세.
    fail_reason = Column(String(40), nullable=True)
    fail_detail = Column(Text, nullable=True)
    # evidence 스냅샷 — construction.evidence(before/after/signature) 참조.
    evidence = Column(JSONColumn, nullable=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default='false')
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 한 주문의 current(열린) attempt 는 최대 1개("current attempt 0/1" 불변식의 DB 표현).
        # 종결된 attempt(is_current=false)은 여러 개 이력으로 남을 수 있다.
        Index(
            'uq_construction_attempt_current', 'order_id',
            unique=True, postgresql_where=text('is_current'),
        ),
        # 한 주문의 한 legacy 시공 시작 ordinal 에 attempt 는 최대 1개(중복 발급 방지·backfill 멱등).
        # legacy_seq IS NULL(비-legacy)은 이 제약 밖(향후 STATE-CONST-CS 발급분).
        Index(
            'uq_construction_attempt_legacy', 'order_id', 'legacy_seq',
            unique=True, postgresql_where=text('legacy_seq IS NOT NULL'),
        ),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'status': self.status,
            'legacy_seq': self.legacy_seq,
            'scheduled_date': self.scheduled_date,
            'started_at': format_datetime_kst(self.started_at) if self.started_at else None,
            'started_by': self.started_by,
            'completed_at': format_datetime_kst(self.completed_at) if self.completed_at else None,
            'completed_by': self.completed_by,
            'completion_note': self.completion_note,
            'fail_reason': self.fail_reason,
            'fail_detail': self.fail_detail,
            'evidence': self.evidence,
            'is_current': self.is_current,
            'created_at': format_datetime_kst(self.created_at),
        }


class OrderEvent(Base):
    """ERP 이벤트 스트림(단계 변경/일정 변경/긴급 발주/컨펌 등).

    AUDIT-LOG T9: **감사 원장은 감사 대상과 생명주기를 공유하지 않는다.** ``order_id`` 는
    과거 ``orders.id`` 를 ``ON DELETE CASCADE`` 로 참조해서, 주문 hard purge 가 그 주문의
    이벤트 이력까지 통째로 지웠다(스펙 §4 T9·§8 결정 ④). 마이그레이션 ``auditlife_00`` 이
    FK 를 떼어냈고 여기도 동기화한다 — ``order_id`` 는 NOT NULL + 인덱스 그대로이며,
    ``orders`` 와의 조인은 아래 ``order`` relationship 의 명시 ``primaryjoin`` 이 담당한다.
    같은 이유로 raw DDL 재생성 경로(``scripts/ops/erp_build_step_runner.py``)에도 FK 가 없다.
    """
    __tablename__ = 'order_events'

    id = Column(Integer, primary_key=True)
    # FK 없음(auditlife_00) — 참조 제약이 아니라 인덱스만 있는 감사 원장 컬럼.
    order_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # e.g. STAGE_CHANGED, URGENT_SET
    payload = Column(JSONColumn, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    # naive DB timestamp = UTC 규약(datetime_kst): created_at 를 UTC-naive 로 통일해
    # 변경감지 윈도(도면 이력 now_utc_naive 와 naive 비교)를 dev/운영 모두 정합시킨다.
    created_at = Column(DateTime, default=now_utc_naive, nullable=False, index=True)

    # FK 가 없으므로 SQLAlchemy 가 조인 조건을 추론할 수 없다 — ``foreign()`` 로 참조 측을
    # 명시한다(lazy 로드 유지, backref 없음: ``Order.events`` 는 존재한 적이 없다).
    order = relationship('Order', primaryjoin='foreign(OrderEvent.order_id) == Order.id')
    created_by = relationship('User', foreign_keys=[created_by_user_id])


class OrderShareToken(Base):
    """고객 공유 열람 토큰(로그인 없는 링크) — 스펙 2026-08-11 §3.1.

    토큰 원문은 저장하지 않는다 — sha256 해시(``token_hash``)만 UNIQUE 로 보관하며
    256bit 원문(``secrets.token_urlsafe(32)``)이 실질 방어선이다. ``snapshot`` 은
    kind='estimate' 전용 동결 렌더 데이터(D6 — 발송 시점 스냅샷 고정), drawing 은
    NULL(라이브 수집). server_default 는 의도적으로 없다 — 모든 insert 가 ORM 경로라
    클라이언트 default 만 두어 migration_chain 지문(모델↔마이그레이션)을 정합시킨다.
    """
    __tablename__ = 'order_share_tokens'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'),
                      nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # 'drawing' | 'estimate'
    token_hash = Column(String(64), nullable=False, unique=True)  # sha256 hex
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    expires_at = Column(DateTime, nullable=False)  # 발급 +FOMS_SHARE_TOKEN_DAYS(기본 30)d
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_utc_naive, nullable=False)
    view_count = Column(Integer, nullable=False, default=0)
    last_viewed_at = Column(DateTime, nullable=True)
    snapshot = Column(JSONColumn, nullable=True)  # estimate 전용 동결 렌더(64KB 캡)

    order = relationship('Order')
    created_by = relationship('User', foreign_keys=[created_by_user_id])


class OrderShareSnapshot(Base):
    """고객이 **실제로 본** 계약서 내용 원장 (SHARE-HIST-00).

    공유 계약서를 라이브 반영으로 바꾸면서(``foms.api.share._live_estimate_snapshot``)
    같은 링크가 늘 최신 주문 값을 보여준다. 그 대가로 "고객이 그날 본 금액" 이 어디에도
    남지 않는데, 계약서에는 법적 효력 문구가 들어가므로 분쟁 시 제시할 근거가 필요하다.

    ``order_field_changes`` 로는 대신할 수 없다. 그쪽은 **주문 값의 변경 이력**이고, 계약서
    표면에는 회사정보·계좌(발주사 판정에 따른 1벌)와 스냅샷 화이트리스트 버전, 발급 시점
    고정 계약번호가 함께 들어간다 — 재생(replay)하면 당시 화면과 달라진다. 그래서 **열람
    시점에 렌더된 dict 그대로** 남긴다.

    * **FK 없음** — ``OrderFieldChange``·``OrderChangeReason``·``OrderEvent`` 와 같은 이유
      (AUDIT-LOG T9 / ``auditlife_00``): 증거 원장이 감사 대상과 생명주기를 공유하면 주문
      hard purge 가 증거까지 지운다.
    * **UNIQUE 를 두지 않는다** — ``(share_token_id, content_hash)`` 를 unique 로 묶으면
      금액이 A→B→A 로 되돌아갔을 때 세 번째 상태가 첫 행에 흡수돼 시간축이 무너진다.
      중복 판정은 **그 토큰의 최신 행과만** 한다(``order_share_history.record_snapshot_view``).
    * ``source`` — 라이브 재구성본(``live``)인지 발급 시점 폴백본(``stored``)인지. 폴백으로
      뜬 화면도 고객이 본 화면이므로 똑같이 남기되 구별은 해 둔다.

    ``__table_args__`` 의 인덱스 이름·컬럼 순서는 마이그레이션 ``sharehist_00`` 과 **완전히**
    같아야 한다(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합 — PG 왕복 테스트가 강제).
    """

    __tablename__ = 'order_share_snapshots'
    __table_args__ = (
        # "이 링크가 고객에게 보여 온 내용들" — 이력 목록의 1순위 질의이자 중복 판정용
        # 최신 행 조회 경로. 선행 컬럼이 share_token_id 여야 한다.
        Index('ix_order_share_snapshots_token_id', 'share_token_id', 'id'),
        # "이 주문이 고객에게 보여진 이력 전부" — 링크를 여러 번 재발급한 주문용.
        Index('ix_order_share_snapshots_order_time', 'order_id', 'first_viewed_at'),
    )

    # 원장 계열 공통(OrderFieldChange 와 같은 variant — SQLite 자동증가 보존).
    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    # FK 없음(위 docstring) — 인덱스만 있는 증거 원장 컬럼.
    share_token_id = Column(Integer, nullable=False)
    order_id = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False)  # 'estimate' | 'bundle'
    content_hash = Column(String(64), nullable=False)  # canonical JSON 의 sha256 hex
    # 렌더된 dict 그대로. 크기는 build_estimate_snapshot 의 64KB 캡이 이미 강제한다.
    snapshot = Column(JSONColumn, nullable=False)
    source = Column(String(16), nullable=False)  # 'live' | 'stored'
    # naive DB timestamp = UTC 규약(datetime_kst).
    first_viewed_at = Column(DateTime, default=now_utc_naive, nullable=False)
    last_viewed_at = Column(DateTime, default=now_utc_naive, nullable=False)
    # 같은 내용을 다시 열어 본 횟수(내용이 바뀌면 새 행이라 행마다 독립).
    view_count = Column(Integer, nullable=False, default=1)


class OrderFieldChange(Base):
    """주문 필드 변경 원장 — 저장 1회가 바꾼 값들을 **질의 가능한 행**으로 편다 (ORDER-DIFF-01).

    ORDER-DIFF-00 이 같은 내용을 ``security_logs.detail['changes']`` JSONB 로 남겼지만,
    감사의 핵심 질문("최근 한 달에 실측일이 바뀐 주문 전부", "출고가를 내린 사람")이
    JSONB 배열 해체를 요구해 인덱스를 타지 못했다. SAP 이 ``CDHDR``(헤더)/``CDPOS``(항목)로
    나눈 것과 같은 분리이며, 여기가 항목 쪽이다. 헤더는 여전히 ``security_logs`` 행이다.

    * ``change_set_id`` — 저장 1회 묶음(UUID4). 헤더의 ``detail['change_set']`` 과 같은 값이라
      **FK 없이** 헤더↔항목이 이어진다.
    * ``path_template`` — 품목 인덱스를 지운 질의 키(``items.*.price``). 품목 번호와 무관하게
      "단가가 바뀐 것 전부"를 인덱스로 물을 수 있다(``path`` 는 원본 경로 그대로 보존).
    * **FK 없음** — ``OrderEvent`` 와 같은 이유다(AUDIT-LOG T9 / ``auditlife_00``): 감사 원장이
      감사 대상과 생명주기를 공유하면 주문 hard purge 가 이력까지 지운다.

    ``__table_args__`` 의 인덱스 이름·컬럼 순서는 마이그레이션 ``orderdiff_01`` 과 **완전히**
    같아야 한다(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합 — PG 왕복 테스트가 강제).
    """

    __tablename__ = 'order_field_changes'
    __table_args__ = (
        # "이 필드가 바뀐 것 전부" — 감사의 1순위 질문. 선행 컬럼이 path_template 이어야 한다.
        Index('ix_order_field_changes_template_time', 'path_template', 'created_at'),
        # "이 주문의 변경 역사" — 주문별 이력 조회.
        Index('ix_order_field_changes_order_time', 'order_id', 'created_at'),
        # 헤더(security_logs) ↔ 항목 연결.
        Index('ix_order_field_changes_change_set', 'change_set_id'),
    )

    # 저장 1건이 필드 N개를 낳는 원장이라 32bit 상한을 남겨두지 않는다.
    # SQLite 는 ``BIGINT PRIMARY KEY`` 를 rowid 별칭으로 보지 않아 자동증가가 죽는다
    # (테스트 레인이 NOT NULL 로 터진다) — 그 레인에서만 INTEGER 로 낮춘다.
    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    change_set_id = Column(String(36), nullable=False)
    # FK 없음(위 docstring) — 인덱스만 있는 감사 원장 컬럼.
    order_id = Column(Integer, nullable=False)
    path = Column(String(120), nullable=False)
    path_template = Column(String(120), nullable=False)
    item_index = Column(Integer, nullable=True)
    # 품목 안정 식별자(ORDER-ITEM-UID). 인덱스는 저장마다 밀릴 수 있어도 이 값은 같은 품목을
    # 계속 가리킨다 — "이 품목이 어떻게 바뀌어 왔나"를 물을 수 있는 열쇠다. 그 질의를 하는
    # 화면이 아직 없어 인덱스는 붙이지 않는다(필요해질 때 붙인다).
    item_uid = Column(String(36), nullable=True)
    item_name = Column(String(120), nullable=True)
    op = Column(String(8), nullable=False)
    before_value = Column(Text, nullable=True)
    after_value = Column(Text, nullable=True)
    actor_user_id = Column(Integer, nullable=True)
    # naive DB timestamp = UTC 규약(datetime_kst).
    created_at = Column(DateTime, default=now_utc_naive, nullable=False)


class OrderChangeReason(Base):
    """주문 변경 사유 — 저장 1회가 **왜** 일어났는지 (ORDER-REASON-00).

    ``OrderFieldChange`` 가 "무엇이 어떻게" 를 답한다면 여기는 "왜" 다. 금액·일정 분쟁에서
    "고객이 요청한 변경"과 "우리 입력 실수"는 책임 소재가 정반대인데, 값만 남은 원장에서는
    구별되지 않는다.

    * ``change_set_id`` — 저장 1회 묶음이자 **unique** 키. 사유는 저장 1회에 하나뿐이고,
      감사 원장이므로 나중에 덮어쓰지 않는다(중복 첨부는 API 가 409 로 막는다).
    * ``reason_code`` — 자유 문자열이 아니라 목록 코드다(``change_reason.REASON_CODES``).
      "입력 오류 정정이 이번 달 몇 건" 같은 질문이 인덱스를 타야 하기 때문이다.
      라벨은 굽지 않는다 — 읽는 시점에 붙인다.
    * **FK 없음** — ``OrderFieldChange``·``OrderEvent`` 와 같은 이유(감사 원장이 감사 대상과
      생명주기를 공유하면 주문 hard purge 가 이력까지 지운다).

    사유를 ``order_field_changes`` 의 컬럼으로 두지 않는 이유: 같은 문자열이 변경 필드 수만큼
    복제되고 집계가 ``DISTINCT`` 를 타야 한다.

    ``__table_args__`` 의 인덱스 이름·컬럼 순서는 마이그레이션 ``orderreason_00`` 과 **완전히**
    같아야 한다(create_all 부트스트랩 레인과 alembic 레인의 스키마 정합).
    """

    __tablename__ = 'order_change_reasons'
    __table_args__ = (
        # 저장 1회 = 사유 1행(중복 첨부 차단은 DB 에서도 강제한다).
        Index('ux_order_change_reasons_change_set', 'change_set_id', unique=True),
        # "입력 오류 정정 월 몇 건" — 사유 기준 집계.
        Index('ix_order_change_reasons_code_time', 'reason_code', 'created_at'),
        # 주문별 이력 탭 조인.
        Index('ix_order_change_reasons_order_time', 'order_id', 'created_at'),
    )

    # 원장 계열 공통(OrderFieldChange 와 같은 variant — SQLite 자동증가 보존).
    id = Column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    change_set_id = Column(String(36), nullable=False)
    # FK 없음(위 docstring).
    order_id = Column(Integer, nullable=False)
    reason_code = Column(String(32), nullable=False)
    reason_note = Column(String(200), nullable=True)
    # 사유를 적은 사람 — 저장한 사람과 다를 수 있다(관리자 대리 입력).
    actor_user_id = Column(Integer, nullable=True)
    # naive DB timestamp = UTC 규약(datetime_kst).
    created_at = Column(DateTime, default=now_utc_naive, nullable=False)


class OrderTask(Base):
    """팔로업/이슈 추적(Task).

    TASK-BACKFILL-00 (§5.2) expand: flat task 행에 **DB-global 안정 UUID identity**
    (``task_uuid``)·**optimistic mutation version**(``version``)·**provenance**
    (``provenance``, backfill 은 ``'LEGACY'``) 3개 컬럼을 additive(nullable)로 더한다.
    backfill 은 audit 이 SAFE 로 분류한 task 에만 seed 하고(자동 매핑 0), orphan/status/
    date/team/user/auto_key 이상이 있는 ambiguous task 는 NULL 로 남겨 quarantine 한다.
    기존 컬럼은 무변경(expand 단계) — NOT NULL·auto_key collision unique enforcement 와
    version_id_col 배선은 하류 TASK-01 소관이라 이 단계의 runtime 의미 변경은 0 이다.
    """
    __tablename__ = 'order_tasks'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default='OPEN')  # OPEN/IN_PROGRESS/DONE/CANCELLED
    owner_team = Column(String(50), nullable=True)  # CS/SALES/MEASURE/DRAWING/PRODUCTION/CONSTRUCTION
    owner_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    due_date = Column(String, nullable=True)  # YYYY-MM-DD
    meta = Column(JSONColumn, nullable=True)
    # TASK-BACKFILL-00 expand(nullable): backfill 이 SAFE task 에만 채운다. ambiguous 는 NULL.
    task_uuid = Column(UUIDColumn, nullable=True)          # DB-global 안정 identity(전 DB 유일)
    version = Column(Integer, nullable=True)               # optimistic mutation version(SAFE=1 seed)
    provenance = Column(String(20), nullable=True)         # 'LEGACY'(backfill 표식) — creator 추정 금지
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.now, nullable=False)

    __table_args__ = (
        # 발급된 task_uuid 는 전 DB 유일(partial — 아직 미발급/ambiguous NULL 행은 제외).
        # auto_key collision unique(active) 는 ambiguous 0 확인 후 하류 enforcement 마이그레이션.
        Index(
            'uq_order_task_uuid', 'task_uuid',
            unique=True, postgresql_where=text('task_uuid IS NOT NULL'),
        ),
    )

    order = relationship('Order', foreign_keys=[order_id])
    owner_user = relationship('User', foreign_keys=[owner_user_id])


class SystemSetting(Base):
    """시스템 전역 설정값 저장용 (JSONB 지원).

    ``version`` 은 SHIPMENT-REFERENCE-01 이 도입한 optimistic-lock revision 이다. 설정
    collection 을 갱신하는 command(예: ``UPDATE_SHIPMENT_REFERENCE_LISTS``)는 이 row 를
    ``FOR UPDATE`` 로 잠그고 client 의 If-Match 가 현재 ``version`` 과 일치할 때만 쓴 뒤
    ``version`` 을 1 증가시킨다(초 단위 ``updated_at`` 이 구분 못 하는 동시 저장 lost
    update 를 차단). 기존 setting row 는 server_default 로 ``1`` 을 갖는다.
    """
    __tablename__ = 'system_settings'

    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(JSONColumn, nullable=True)
    description = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=False)


class SystemSettingReceipt(Base):
    """SystemSetting collection mutation 의 idempotency + audit receipt (SHIPMENT-REFERENCE-01).

    Order 단위가 아니라 setting collection 단위의 revision 이므로 REV-00
    :class:`OrderMutationReceipt`(order FK·per-order version) 대신 별도 정본을 둔다. 한
    command 커밋마다 한 행이 두 역할을 겸한다:

    * **idempotency**: ``(actor_user_id, policy_id, idempotency_key)`` unique. 같은 key
      replay 는 저장된 ``response_status``/``response_body`` 를 그대로 돌려주고 business
      write 는 재수행하지 않는다. ``expires_at`` (커밋+24시간) 이후 같은 key 는
      ``IDEMPOTENCY_KEY_EXPIRED`` 다. 비-멱등 요청은 ``idempotency_key`` NULL(PostgreSQL
      은 NULL 을 distinct 로 취급하므로 dedupe 하지 않음).
    * **receipt**: opaque ``read_receipt_id`` 로 갱신 결과 version 을 확인시킨다.

    ``resulting_version`` 은 커밋 후 setting 의 새 ``SystemSetting.version`` 이다.
    """

    __tablename__ = 'system_setting_receipts'

    id = Column(Integer, primary_key=True)
    read_receipt_id = Column(UUIDColumn, nullable=False, unique=True,
                             default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    setting_key = Column(String(100), nullable=False)
    policy_id = Column(String(80), nullable=False)
    idempotency_key = Column(String(64), nullable=True)
    request_hash = Column(String(64), nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSONColumn, nullable=False)
    resulting_version = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # 커밋 + 24시간 (replay window)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            'actor_user_id', 'policy_id', 'idempotency_key',
            name='uq_system_setting_receipt_idem',
        ),
        Index('ix_ssr_setting_key', 'setting_key'),
        Index('ix_ssr_expires_id', 'expires_at', 'id'),  # 향후 retention purge keyset
    )


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
    # ACCOUNT-SELF-01: 셀프 가입 승인 상태. ACTIVE=정상, PENDING=가입 신청 후 관리자
    # 승인 대기(로그인 차단). 거절은 상태 보존 없이 row 삭제(재신청 허용). 기존 행은
    # 마이그레이션 server_default('ACTIVE') 로 backfill.
    approval_status = Column(
        String(20), nullable=False, server_default='ACTIVE', default='ACTIVE',
    )
    # PASSWORD-POLICY-01: 비밀번호 강도 정책 버전(SSOT). 0=LEGACY(강도 미검증),
    # 1=STRONG. hash rehash 로 추정하지 않고 설정 시점에 이 컬럼으로 명시 기록한다.
    # 기존 행은 마이그레이션 server_default('0')=LEGACY 로 backfill 된다.
    password_policy_version = Column(
        Integer, nullable=False, server_default='0', default=0,
    )
    # SHARE-SMS(D2): 공유 링크 문자 개인 명의 발신번호(Solapi 사전 등록 전제).
    # NULL이면 회사 대표번호(SOLAPI_SENDER_PHONE) 폴백. server_default 없음 —
    # migration_chain 지문 정합(senderphone_00 과 컬럼 단위 동일).
    sender_phone = Column(String(20), nullable=True)
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
            'approval_status': self.approval_status,
            'created_at': format_datetime_kst(self.created_at),
            'last_login': format_datetime_kst(self.last_login)
        }

class AccessLog(Base):
    __tablename__ = 'access_logs'
    # ACCESS-LOG-00: 마이그레이션(access_log_00·accesslog_detail_00)과 이름까지 동일해야
    # 한다 — create_all 부트스트랩 레인과 alembic 레인의 스키마 정합(체인 왕복 테스트가 강제).
    #
    # ACCESS-LOG-DETAIL-00: 주문 축 인덱스는 표현식 인덱스라 **PostgreSQL 전용**이다.
    # ``detail['order_id'].as_integer()`` 가 PG 에서 내는 SQL 이
    # ``CAST((detail ->> 'order_id') AS INTEGER)`` 이므로 인덱스 표현식도 같은 모양이어야
    # 계획기가 매칭한다(다르면 인덱스가 있어도 Seq Scan — PG 레인이 EXPLAIN 으로 고정).
    # SQLite 는 같은 비교를 ``JSON_EXTRACT`` 로 내므로 이 인덱스가 의미 없다 → ddl_if 로 제외.
    __table_args__ = (
        Index('ix_access_logs_user_id_timestamp', 'user_id', 'timestamp'),
        Index('ix_access_logs_timestamp', 'timestamp'),
        Index(
            'ix_access_logs_detail_order_id',
            text("((detail ->> 'order_id')::integer)"),
        ).ddl_if(dialect='postgresql'),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String, nullable=False)
    ip_address = Column(String)
    user_agent = Column(String)
    additional_data = Column(Text)
    # 구조화 payload(JSONB on PostgreSQL). ``additional_data`` 의 JSON **문자열** 원문은
    # 그대로 두고 질의 가능한 사본을 따로 든다 — 감사 원장은 원문을 지우지 않는다.
    detail = Column(JSONColumn, nullable=True)
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
            'detail': self.detail,
            'timestamp': format_datetime_kst(self.timestamp)
        }

class SecurityLog(Base):
    """감사 원장 — 사람용 요약(``message``) + SQL 질의용 구조화 컬럼(AUDIT-LOG T8).

    T8 이전에는 자유 텍스트 ``message`` 1컬럼뿐이라 "누가 무엇을 바꿨나"를 ILIKE 로만
    물을 수 있었다(스펙 §1-2). 구조화 컬럼 4개를 additive 로 붙여 SQL 질의가 가능해진다.
    ``message`` 의 의미는 그대로 유지한다(사람이 읽는 요약) — 기존 행 백필은 하지 않으므로
    구조화 컬럼은 T8 이후 기록에만 채워지고 그 이전 행은 전부 NULL 이다(스펙 §6).

    * ``action`` — 행위 종류 태그(``USER_UPDATE``·``LOGIN_FAIL``·``ACCESS_DENIED`` 등).
    * ``target_type``/``target_id`` — 행위 대상(``user`` / ``password_reset_request`` …).
    * ``detail`` — 구조화 부가정보(from→to 변경 내역 등). **비밀번호·PII 원문 금지.**
    """

    __tablename__ = 'security_logs'
    # SEC-LOG-STRUCT-00: 마이그레이션(``seclog_struct_00``·``seclog_time_00``)과 인덱스
    # 이름·컬럼 구성이 완전히 같아야 한다 — create_all 부트스트랩 레인과 alembic 레인의
    # 스키마 정합(tests/postgres 체인 왕복 테스트가 강제). 기존 trgm 인덱스(phase_f)는 무접촉.
    #
    # SEC-LOG-TIME-00: ``ix_security_logs_timestamp_id`` 는 감사 화면의 **기본 조회**
    # (``ORDER BY timestamp DESC, id DESC`` + count)용이다. ``ix_security_logs_target`` 은
    # 선행 컬럼이 ``target_type`` 이라 이 정렬에 쓸 수 없고, trgm 은 ``message`` 전용이다.
    # ``id`` 를 붙인 복합이라 tie-break 까지 인덱스 하나로 풀리고, DESC 는 PostgreSQL 이
    # backward index scan 으로 처리하므로 별도 DESC 인덱스가 필요 없다.
    __table_args__ = (
        Index('ix_security_logs_target', 'target_type', 'target_id', 'timestamp'),
        Index('ix_security_logs_timestamp_id', 'timestamp', 'id'),
    )

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    message = Column(String, nullable=False)
    action = Column(String(64), nullable=True)
    target_type = Column(String(32), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(JSONColumn, nullable=True)


class PasswordResetRequest(Base):
    """ACCOUNT-SELF-01: 비밀번호 재설정 요청 큐(관리자 처리형, 인증 채널 없음).

    로그인 화면에서 접수된 재설정 요청을 기록한다. 계정 열거 방지를 위해 username 이
    실존하지 않아도 row 를 만들며(``user_id`` NULL), 요청자에게는 항상 동일한 성공
    메시지를 보여준다. 관리자가 기존 재설정 기능(edit_user)으로 처리한 뒤 상태를
    DONE/DISMISSED 로 마감한다. DDL 은 migration(``account_self_00``)과 SSOT 를
    공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'password_reset_requests'

    id = Column(Integer, primary_key=True)
    # 요청 폼에 입력된 원문(오타 감사용). 매칭 실패여도 보존한다.
    username_submitted = Column(String(64), nullable=False)
    # 접수 시점 username 매칭 결과(없으면 NULL). 사용자 삭제 시 요청은 감사로 보존.
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    status = Column(String(20), nullable=False, server_default='PENDING', default='PENDING')
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    handled_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    request_ip = Column(String(64), nullable=True)

    user = relationship('User', foreign_keys=[user_id])
    handled_by = relationship('User', foreign_keys=[handled_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','DONE','DISMISSED')",
            name='ck_password_reset_requests_status'),
        # 관리자 대기 큐 조회 hot path(PENDING 을 최신순).
        Index('ix_password_reset_requests_status_created', 'status', 'created_at'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'username_submitted': self.username_submitted,
            'user_id': self.user_id,
            'status': self.status,
            'created_at': format_datetime_kst(self.created_at),
            'handled_by_user_id': self.handled_by_user_id,
            'handled_at': format_datetime_kst(self.handled_at),
        }


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
    - ROLE: 특정 역할 전원 (target_role, 예: 'ADMIN')
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
    # 역할 대상(NOTIF-ROLE-01): target_type='ROLE' 일 때 이 역할의 활성 사용자 전원에게
    # state 를 만든다. 사건 1건 = Notification 1건 + 수신자별 state N개.
    target_role = Column(String(20), nullable=True, index=True)
    
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
    
    # 타임스탬프 (naive=UTC 규약 — format_datetime_kst 가 +9 표시 변환)
    created_at = Column(DateTime, default=now_utc_naive, nullable=False, index=True)
    
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
    TARGET_ROLE = 'target_role'
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

    created_at = Column(DateTime, default=now_utc_naive, nullable=False)
    updated_at = Column(
        DateTime,
        default=now_utc_naive,
        onupdate=now_utc_naive,
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
    created_at = Column(DateTime, default=now_utc_naive, nullable=False)

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
    created_at = Column(DateTime, default=now_utc_naive, nullable=False)
    updated_at = Column(
        DateTime,
        default=now_utc_naive,
        onupdate=now_utc_naive,
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
    # WIZ-SEND-01 D3: 초안 단계 발송 이력({kind: entry}). **서버만 쓴다** —
    # payload 는 매 autosave 마다 클라이언트가 통째로 덮으므로 발송 흔적을 거기 두면
    # 다음 자동저장 한 번에 사라진다. 이 컬럼은 클라이언트 PUT payload 가 닿지 못하는
    # 자리이고, 주문 등록 시 새 주문 structured_data 의 정본 키로 승계된다.
    send_history = Column(JSONColumn, nullable=True)

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

    # --- CHANNEL-INBOUND-ORDER-01: order-creation receipt lifecycle ---------- #
    # 주문 생성 파이프라인의 정본 lifecycle(레거시 ``status`` 와 직교). dedicated worker 가
    # 이 상태만 보고 create_order 로 전이한다. accepted 를 조용히 clear/DEAD 하지 않는다.
    #   NONE            — 아직 생성 대상 아님(parse 전/dry-run).
    #   ACCEPTED        — 생성 대기(worker claim 대상).
    #   PAUSED_ACCEPTED — 전역 create flag cutoff 로 일시 중지(유실 0, 재개 가능).
    #   RECOVERY_REQUIRED — worker 시도 소진(max attempts) → 운영자 recovery 필요.
    #   CREATED         — 주문 1건 생성 완료(exact conservation).
    #   IGNORED         — recovery 판정으로 무시(승인 필요).
    #   RETENTION_EXPIRED — retention deadline 경과(visible incident, 조용한 삭제 아님).
    receipt_state = Column(String(30), nullable=False, server_default='NONE')
    #: 미생성 receipt 데이터를 보관/purge 해야 하는 기한(승인 없는 무기한 보관 금지).
    retention_deadline = Column(DateTime, nullable=True)
    #: 마지막으로 발송한 retention 경고 단계('7d'/'24h'/'6h') — 중복 알림 방지.
    retention_alert_stage = Column(String(10), nullable=True)
    #: 법적 보존(legal hold) — True 면 ignore/purge 로 조용히 없앨 수 없다.
    legal_hold = Column(Boolean, nullable=False, server_default=text('false'))
    #: worker 주문 생성 시도 횟수(max 도달 시 RECOVERY_REQUIRED, 무한 재시도 0).
    create_attempts = Column(Integer, nullable=False, server_default=text('0'))
    #: 이 receipt 의 sealed_secret 를 봉인한 channel key generation(rewrap old-reference 근거).
    key_generation = Column(Integer, nullable=True)
    #: channel key 로 봉인한 per-receipt secret 의 AES-256-GCM envelope(평문 0, rewrap 대상).
    sealed_secret = Column(Text, nullable=True)
    # worker claim lease(SKIP LOCKED · 크래시 시 만료 회수).
    lease_owner_hash = Column(String(64), nullable=True)
    lease_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)

    created_order = relationship('Order', foreign_keys=[created_order_id])
    created_task = relationship('OrderTask', foreign_keys=[created_task_id])

    from sqlalchemy import Index
    __table_args__ = (
        Index('ix_channel_inbound_status_time', 'status', 'received_at'),
        # worker 가 생성 대상(available lease)을 SKIP LOCKED 로 claim 할 때의 hot path.
        Index('ix_channel_inbound_receipt_state', 'receipt_state', 'lease_expires_at'),
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


# 배정 domain / source enum SSOT — service·migration·backfill 이 공유한다.
ORDER_ASSIGNMENT_DOMAINS = ('SALES', 'DRAWING', 'CONSTRUCTION')
ORDER_ASSIGNMENT_SOURCES = ('SELF_CLAIM', 'TEAM_REPLACE', 'INITIAL_OWNER', 'BACKFILL')


class OrderAssignment(Base):
    """주문 배정 authorization 정본 (ASSIGNMENT-00, §2.1 line 172).

    drawing/construction/sales 권한 판정은 **오직 이 user-ID row** 로만 한다. JSONB
    이름 배열(``structured_data.assignments`` 등)은 server-owned 표시 projection 일 뿐
    authorization 근거가 아니다.

    * ``domain`` = ``SALES|DRAWING|CONSTRUCTION`` (check 제약).
    * ``source`` = ``SELF_CLAIM|TEAM_REPLACE|INITIAL_OWNER|BACKFILL`` (check 제약);
      release 규칙과 legacy backfill 승격 여부를 구분한다.
    * ``active`` = 현재 유효 배정. release 는 hard delete 하지 않고 ``active=false`` +
      ``released_at/released_by_user_id/release_reason`` 로 **이력을 보존**한다.

    PostgreSQL partial unique 두 개가 정합성을 DB 레벨에서 강제한다:

    * ``uq_order_assignment_active`` = ``(order_id,domain,user_id) WHERE active`` —
      같은 사람을 같은 domain 에 중복 active 배정 금지(released 뒤 재배정은 허용).
    * ``uq_order_assignment_sales_owner`` = ``(order_id) WHERE active AND domain='SALES'``
      — SALES 는 주문당 active owner 1명 강제.

    DDL 은 migration(assignment_00) 과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'order_assignments'

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False,
    )
    domain = Column(String(20), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    source = Column(String(20), nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default='true')
    assigned_at = Column(DateTime, nullable=False, default=now_utc_naive)
    assigned_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    released_at = Column(DateTime, nullable=True)
    released_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    release_reason = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "domain IN ('SALES','DRAWING','CONSTRUCTION')",
            name='ck_order_assignment_domain',
        ),
        CheckConstraint(
            "source IN ('SELF_CLAIM','TEAM_REPLACE','INITIAL_OWNER','BACKFILL')",
            name='ck_order_assignment_source',
        ),
        # active (order,domain,user) 중복 금지 — released 뒤 재배정은 partial 이라 허용.
        Index(
            'uq_order_assignment_active', 'order_id', 'domain', 'user_id',
            unique=True, postgresql_where=text('active'),
        ),
        # SALES active owner 는 주문당 1명.
        Index(
            'uq_order_assignment_sales_owner', 'order_id',
            unique=True, postgresql_where=text("active AND domain = 'SALES'"),
        ),
        # authorization 조회(주문·domain 별 active 배정) 인덱스.
        Index(
            'ix_order_assignment_active_lookup', 'order_id', 'domain',
            postgresql_where=text('active'),
        ),
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
# WDC-LINK-FENCE-00: WDC link cutover runtime state (SEPARATE topology, §8.2 line 734)
# --------------------------------------------------------------------------- #
class WDCLinkRuntimeState(Base):
    """SEPARATE_DATABASE topology 의 WDC link fence singleton (§8.2 line 734).

    WDC DB 에 사는 정본으로 legacy ``EstimateOrderMatch`` → canonical
    ``estimate_order_links_v2`` cutover 를 게이트한다(mode ``LEGACY → FROZEN → CANONICAL``).
    SAME_DATABASE topology 는 한 transaction / no-freeze 이므로 이 행을 쓰지 않는다 — 그래서
    singleton row 는 create_all / migration 이 **auto-seed 하지 않고** SEPARATE 프로비저닝
    (하류)이 seed 한다. fence 전이 로직은 ``foms/services/security/cutover/wdc_link_fence.py``
    다(이 packet 은 fence 정의만 — freeze / canonical / abort CLI 는 WDC-LINK-01 하류 몫).
    """

    __tablename__ = 'wdc_link_runtime_state'

    id = Column(Integer, primary_key=True)  # singleton — 항상 1 (ck_wdc_link_state_singleton).
    mode = Column(String(20), nullable=False, server_default='LEGACY')
    generation = Column(Integer, nullable=False, server_default=text('0'))
    row_version = Column(Integer, nullable=False, server_default=text('1'))
    prepared_consumer_generation = Column(Integer, nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    freeze_source_fingerprint = Column(String(64), nullable=True)
    freeze_rollout_artifact_sha256 = Column(String(64), nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    # CLI 가 소비된 approval row 에서 복사하는 optional actor(fence 정의 helper 는 미설정).
    updated_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "mode IN ('LEGACY','FROZEN','CANONICAL')",
            name='ck_wdc_link_state_mode',
        ),
        CheckConstraint('id = 1', name='ck_wdc_link_state_singleton'),
    )


# --------------------------------------------------------------------------- #
# WDC-LINK-BACKFILL-00: canonical estimate<->order link (§5.2 line 1040)
# --------------------------------------------------------------------------- #
class EstimateOrderLinkV2(Base):
    """canonical estimate↔order link 정본 (WDC-LINK-BACKFILL-00, §5.2 line 1040).

    legacy ``EstimateOrderMatch``(V1, ``wdcalculator_models``) → 이 canonical row 로
    topology-aware backfill 되는 대상이다. legacy runtime 은 이 테이블을 읽지 않으며(shadow),
    marker/CANONICAL 뒤에야 WDC-LINK-01 canonical reader/writer 가 소비한다. **V1 테이블은
    병행(무변경)** 이고 V1 cleanup 은 별도 packet(WDC-LINK-CLEANUP-01) 몫이라 이 모델은 V1 을
    참조/삭제하지 않는다.

    * **unique pair**: ``(estimate_id, order_id)`` 는 유일하다(``uq_estimate_order_link_v2_pair``).
      backfill 은 V1 의 중복 pair 를 이 canonical row **하나**로 정규화한다(source-target
      equivalence — target pair == source pair).
    * **topology 표현**: :data:`source_topology` 가 이 row 를 만든 위상(``SAME_DATABASE`` |
      ``SEPARATE_DATABASE``)을 기록해 phase conflation(SAME/SEPARATE 혼동)을 감사 가능하게 한다.
    * **phase run ID / V2_BACKFILL checkpoint**: :data:`backfill_run_id` 가 이 row 를 발급한
      resume run(:class:`MaintenanceBackfillRun`, ``V2_BACKFILL_*`` phase)에 연결해 checkpoint
      원장과 provenance 를 맺는다.

    ``estimate_id``/``order_id`` 는 cross-DB(SEPARATE 위상)라 물리 FK 를 걸지 않는다(V1 의
    ``order_id`` 와 동일한 논리 참조 규약).
    """

    __tablename__ = 'estimate_order_links_v2'

    id = Column(Integer, primary_key=True)
    estimate_id = Column(Integer, nullable=False, index=True)  # WDC estimates.id (논리 참조·물리 FK 아님).
    order_id = Column(Integer, nullable=False, index=True)      # FOMS orders.id (논리 참조·물리 FK 아님).
    # 이 row 를 만든 위상(phase conflation 감사용).
    source_topology = Column(String(20), nullable=False)
    # provenance: 발급 근거 V1 estimate_order_matches.id(중복 pair 는 최소 id — 결정적 equivalence).
    source_match_id = Column(Integer, nullable=True)
    # 발급 resume run id(V2_BACKFILL_* phase). checkpoint 원장·phase run ID 연결.
    backfill_run_id = Column(String(64), nullable=True)
    linked_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('estimate_id', 'order_id', name='uq_estimate_order_link_v2_pair'),
        CheckConstraint(
            "source_topology IN ('SAME_DATABASE','SEPARATE_DATABASE')",
            name='ck_estimate_order_link_v2_topology',
        ),
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


# --------------------------------------------------------------------------- #
# SIDEFX-00: typed-domain side-effect outbox (SSOT §2.2.1 line 385 / §2.3 line 391)
# --------------------------------------------------------------------------- #
# domain side-effect(notification·cache·geocode·storage-delete·provider call)를
# business tx 와 원자적으로 기록하는 typed outbox. 실 producer(도메인 write)·consumer
# (worker delivery/expiry/retention)는 하류(SIDEFX-WORKER-01·CHANNEL·URGENT 등) 몫이다 —
# SIDEFX-00 은 스키마+repository+계약 테스트만 소유한다.
#
# source_domain 은 정확히 자기 FK 컬럼 하나만 non-null 이어야 한다(one-of matrix,
# ck_dseo_source_one_of). 부모 테이블이 존재하는 4 도메인이 실 FK 로 orphan 을 거부하고
# (order_events·notification_events·chat_attachments·**upload_drafts** — 마지막은
# UPLOAD-INTENT-01 이 additive 로 부착), 나머지 3 도메인(address_learning·wizard_pending·
# upload_ticket)은 소유 packet 이 자기 business table 과 FK 를 additive migration 으로
# 등록한다(ORDER-IMPORT-01 이 8번째 ORDER_IMPORT_ARTIFACT 를 그렇게 추가하는 선례와 동일).
# SIDEFX-00 은 그 business table 들을 선행 생성하지 않는다.
DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN = {
    'ORDER_EVENT': 'order_event_id',
    'NOTIFICATION_EVENT': 'notification_event_id',
    'ADDRESS_LEARNING': 'address_learning_request_id',
    'WIZARD_PENDING': 'wizard_pending_id',
    'UPLOAD_TICKET': 'upload_ticket_id',
    'UPLOAD_DRAFT': 'upload_draft_id',
    'CHAT_ATTACHMENT': 'chat_attachment_id',
    # ORDER-IMPORT-01: 8번째 도메인. order_import_artifacts 부모가 생겨 실 FK 로 orphan 거부
    # (one-of matrix 유지). SIDEFX-00 이 남겨둔 선례대로 소유 packet 이 additive 로 추가한다.
    'ORDER_IMPORT_ARTIFACT': 'order_import_artifact_id',
}
DOMAIN_SIDE_EFFECT_STATUSES = ('PENDING', 'PROCESSING', 'DONE', 'DEAD')


def _domain_side_effect_one_of_sql() -> str:
    """source_domain 별 exact one-of FK 매트릭스를 SQL boolean 식으로 생성한다.

    각 도메인 절은 (source_domain=D AND 자기 FK IS NOT NULL AND 나머지 FK 전부 IS NULL)
    이고 전체는 OR 이다 → 정확히 하나의 FK 만 non-null 이며 그것이 domain 과 일치할 때만
    참. mismatch(다른 FK)·다중 non-null·전부 NULL 은 모두 거짓 → CHECK 위반. migration
    과 ORM 이 이 문자열을 공유해 drift 를 막는다.
    """
    cols = list(DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN.values())
    clauses = []
    for domain, own in DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN.items():
        parts = ["source_domain = '%s'" % domain, "%s IS NOT NULL" % own]
        parts += ["%s IS NULL" % c for c in cols if c != own]
        clauses.append("(" + " AND ".join(parts) + ")")
    return " OR ".join(clauses)


DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL = _domain_side_effect_one_of_sql()


class DomainSideEffectOutbox(Base):
    """typed-domain side-effect outbox 행(SIDEFX-00).

    business transaction 안에서 INSERT 되어 side effect 를 durable 하게 예약한다. 하류
    worker 가 ``FOR UPDATE SKIP LOCKED`` + lease(획득/만료 reclaim)로 소비하고 최대 재시도
    후 DEAD 로 보낸다(worker 는 SIDEFX-WORKER-01 몫). 여기서는 스키마만 정의한다.
    """

    __tablename__ = 'domain_side_effect_outbox'

    id = Column(Integer, primary_key=True)
    source_domain = Column(String(40), nullable=False)

    # per-domain source FK — 정확히 하나만 non-null(ck_dseo_source_one_of).
    order_event_id = Column(
        Integer, ForeignKey('order_events.id', ondelete='CASCADE'), nullable=True)
    notification_event_id = Column(
        Integer, ForeignKey('notification_events.id', ondelete='CASCADE'), nullable=True)
    # 아래 도메인은 부모 테이블 미존재 → 소유 packet 이 FK 를 additive 로 추가(현재는
    # plain integer, one-of CHECK 로 domain 일치만 강제; orphan 거부는 FK 추가 후).
    address_learning_request_id = Column(Integer, nullable=True)
    # WIZ-01-COMPLETION: drawing_wizard_pending 부모가 생겨 실 FK 로 orphan 거부(one-of matrix 유지).
    wizard_pending_id = Column(
        Integer, ForeignKey('drawing_wizard_pending.id', ondelete='CASCADE'), nullable=True)
    # UPLOAD-02: upload_tickets 부모가 생겨 실 FK 로 orphan 거부(one-of matrix 유지).
    upload_ticket_id = Column(
        Integer, ForeignKey('upload_tickets.id', ondelete='CASCADE'), nullable=True)
    # UPLOAD-INTENT-01: upload_drafts 부모가 생겨 실 FK 로 orphan 거부(one-of matrix 유지).
    upload_draft_id = Column(
        Integer, ForeignKey('upload_drafts.id', ondelete='CASCADE'), nullable=True)
    chat_attachment_id = Column(
        Integer, ForeignKey('chat_attachments.id', ondelete='CASCADE'), nullable=True)
    # ORDER-IMPORT-01: order_import_artifacts 부모가 생겨 실 FK 로 orphan 거부(8번째 도메인).
    order_import_artifact_id = Column(
        Integer, ForeignKey('order_import_artifacts.id', ondelete='CASCADE'), nullable=True)

    effect_type = Column(String(40), nullable=False)
    payload = Column(JSONColumn, nullable=False)
    schema_version = Column(Integer, nullable=False, server_default=text('1'))
    source_generation = Column(BigInteger, nullable=True)
    # provider 로 보낼 idempotency key(consumer 측). dedupe_key 는 producer 측 중복 행 차단.
    provider_idempotency_key = Column(String(200), nullable=True)
    dedupe_key = Column(String(200), nullable=True)

    status = Column(String(20), nullable=False, server_default='PENDING')
    attempts = Column(Integer, nullable=False, server_default=text('0'))
    last_error = Column(Text, nullable=True)

    lease_owner_hash = Column(String(64), nullable=True)
    lease_token = Column(UUIDColumn, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)

    available_at = Column(DateTime, nullable=False, default=now_utc_naive,
                          server_default=func.now())
    created_at = Column(DateTime, nullable=False, default=now_utc_naive,
                        server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    dead_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source_domain IN ("
            + ", ".join("'%s'" % d for d in DOMAIN_SIDE_EFFECT_FK_BY_DOMAIN)
            + ")",
            name='ck_dseo_source_domain',
        ),
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','DONE','DEAD')",
            name='ck_dseo_status',
        ),
        # exact source-domain/FK one-of matrix (mismatch/다중/전무 거부).
        CheckConstraint(DOMAIN_SIDE_EFFECT_ONE_OF_CHECK_SQL, name='ck_dseo_source_one_of'),
        # dedupe: 같은 effect 의 중복 outbox 행 차단(SSOT unique(effect_type,dedupe_key)).
        # dedupe_key NULL 행은 collapse 하지 않도록 partial.
        Index('uq_dseo_effect_dedupe', 'effect_type', 'dedupe_key',
              unique=True, postgresql_where=text('dedupe_key IS NOT NULL')),
        # queue pickup: PENDING 을 available_at 순으로.
        Index('ix_dseo_queue', 'status', 'available_at'),
        # lease reclaim: 만료 lease(PROCESSING) 회수.
        Index('ix_dseo_lease_expiry', 'lease_expires_at',
              postgresql_where=text("status = 'PROCESSING'")),
        # retention: DONE completed_at>30d / DEAD dead_at>180d 조회.
        Index('ix_dseo_done_retention', 'completed_at',
              postgresql_where=text("status = 'DONE'")),
        Index('ix_dseo_dead_retention', 'dead_at',
              postgresql_where=text("status = 'DEAD'")),
    )


class SideEffectWorkerHeartbeat(Base):
    """side-effect worker readiness 정본(SIDEFX-00 은 테이블만).

    worker(SIDEFX-WORKER-01)가 loop 종류별로 upsert 한다. readiness gate 는 heartbeat
    신선도(<30s)와 lag(delivery<60s·expiry scan<360s·retention<90000s)를 이 행에서 읽는다.
    """

    __tablename__ = 'side_effect_worker_heartbeats'

    worker_kind = Column(String(40), primary_key=True)  # DELIVERY|EXPIRY_SCAN|RETENTION
    last_heartbeat_at = Column(DateTime, nullable=False, default=now_utc_naive,
                               server_default=func.now())
    oldest_lag_seconds = Column(Integer, nullable=True)
    metadata_json = Column(JSONColumn, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive,
                        server_default=func.now())


class AddressLearningRequest(Base):
    """주소 교정 학습 요청 child 행 (DATA-MEASUREMENT-01).

    운영자가 지오코딩이 틀린 주소를 바로잡으면(original→corrected + 좌표) 그 교정을
    **감사 가능한 durable child 행**으로 기록한다. 무제한 all-STAFF in-memory 학습(구
    ``FOMSAddressConverter.add_learning_data``)을 대체하는 정본으로, 세 가지를 강제한다.

    * **audit**: ``requested_by_user_id``·``created_at`` 로 누가/언제 교정했는지 보존한다.
    * **rate**: 요청 handler 가 사용자별 최근 창(window) row 수를 세어 폭주를 거부한다
      (:mod:`foms.services.address_learning_requests`).
    * **outbox 연동**: 이 행 id 를 ``domain_side_effect_outbox.address_learning_request_id``
      (source_domain=``ADDRESS_LEARNING``)로 참조해 실제 학습 적용을 worker 로 비동기화한다.
      그 컬럼은 아직 실 FK 가 아니므로(SIDEFX-00 note) 여기서 부모 테이블만 만든다.
    """

    __tablename__ = 'address_learning_requests'

    id = Column(Integer, primary_key=True)
    original_address = Column(Text, nullable=False)   # 사용자가 입력한(틀린) 원 주소
    corrected_address = Column(Text, nullable=False)  # 정답 주소
    lat = Column(Float, nullable=True)                # 교정 좌표(선택)
    lng = Column(Float, nullable=True)
    requested_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # audit
    created_at = Column(DateTime, nullable=False, default=now_utc_naive,
                        server_default=func.now())

    __table_args__ = (
        # rate-limit 조회(사용자별 최근 창 count)와 audit 스캔 hot path.
        Index('ix_alr_requester_created', 'requested_by_user_id', 'created_at'),
    )


# --------------------------------------------------------------------------- #
# UPLOAD-INTENT-01: pre-file upload DRAFT (drawing revision / AS cycle intent)
# --------------------------------------------------------------------------- #
#: DRAFT 종류 — drawing revision 전달용 / AS cycle 접수용 업로드 의도.
UPLOAD_DRAFT_KINDS = ('drawing_revision', 'as_cycle')
#: DRAFT state machine. DRAFT 는 활성, 나머지는 terminal. EXPIRED 는 lazy 판정 결과이며
#: scheduler 가 기록하지 않는다(만료는 조회 시 effective_state 로 계산).
UPLOAD_DRAFT_STATES = ('DRAFT', 'FINALIZED', 'CANCELLED', 'EXPIRED')
#: DRAFT 유효기간(시간). 만료는 lazy 판정(자동 정리 scheduler 없음).
UPLOAD_DRAFT_TTL_HOURS = 24


class UploadDraft(Base):
    """파일 업로드 **전에** 발급하는 업로드 intent DRAFT (UPLOAD-INTENT-01, §5.2 line 1082).

    drawing revision / AS cycle 파일을 R2 에 올리기 전부터 안정 ``id`` 를 발급해 업로드
    의도를 durable 하게 예약한다. 실제 drawing revision / AS cycle row 발급과 상태 전이는
    하류(STATE-DRAWING-01·STATE-AS-01) 몫이며, 이 packet 은 DRAFT 수명주기만 소유한다.

    계약(§5.2 UPLOAD-INTENT-01):

    * **pre-file id**: 파일 도착 전에 ``id`` 를 발급한다(create).
    * **idempotent create**: 같은 ``(order_id, kind, idempotency_key)`` 재요청은 기존
      DRAFT 를 돌려주고 새 행을 만들지 않는다(``uq_upload_draft_idem`` partial unique).
    * **24h expiry (lazy)**: ``expires_at = created_at + 24h``. 만료는 조회 시
      :func:`~foms.services.orders.upload_intent.effective_state` 로 판정하고 scheduler 가
      상태를 기록하지 않는다.
    * **queue 비노출**: 별도 테이블이라 order 대시보드/큐(orders 기반)에 노출되지 않는다.
    * **cancel = terminal**: CANCELLED 로 마크(멱등). Order 는 불변.
    * **finalize only bumps Order**: final command(finalize)만 Order ``mutation_version``
      을 1회 올린다(REV-00). create/cancel 는 Order version 불변.

    ``upload_draft_id`` FK 로 :class:`DomainSideEffectOutbox` 가 이 행을 참조하며(source_domain=
    ``UPLOAD_DRAFT``), orphan 은 DB 가 거부한다. DDL 은 migration(``upload_intent_00``)과 SSOT
    를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'upload_drafts'

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String(32), nullable=False)  # drawing_revision | as_cycle
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # audit
    state = Column(String(20), nullable=False, server_default='DRAFT')
    # FILE-01 direct_upload 로 이 DRAFT 아래 올라온 server-derived object key 목록.
    object_keys = Column(JSONColumn, nullable=True)
    # 같은 intent 재요청 dedupe 키(client 발급). NULL 이면 매 create 가 새 DRAFT.
    idempotency_key = Column(String(80), nullable=True)
    row_version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    # created_at + 24h. 만료는 lazy 판정(scheduler 없음).
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('drawing_revision','as_cycle')", name='ck_upload_draft_kind'),
        CheckConstraint(
            "state IN ('DRAFT','FINALIZED','CANCELLED','EXPIRED')",
            name='ck_upload_draft_state'),
        # idempotent create: 같은 (order,kind,key) 는 최대 1행(중복 생성 0). key NULL 제외.
        Index('uq_upload_draft_idem', 'order_id', 'kind', 'idempotency_key',
              unique=True, postgresql_where=text('idempotency_key IS NOT NULL')),
    )


#: per-file upload ticket state machine (UPLOAD-02, §5.2 line 1083). ISSUED 는 활성,
#: 나머지는 terminal. EXPIRED 는 bounded cleanup provider 가 만료 ISSUED 를 claim 하며
#: 기록한다(UPLOAD-INTENT DRAFT 의 lazy EXPIRED 와 달리 ticket 은 provider 가 실기록).
UPLOAD_TICKET_STATES = ('ISSUED', 'COMPLETED', 'EXPIRED', 'CANCELLED')
#: ticket 유효기간(초). 900s(=15분) 안에 complete 하지 않으면 cleanup provider 가 EXPIRED.
UPLOAD_TICKET_TTL_SECONDS = 900


class UploadTicket(Base):
    """per-file 업로드 ticket (UPLOAD-02, §5.2 line 1083).

    한 파일의 direct-upload 수명을 durable 하게 예약하는 per-file 티켓이다. issue 는
    server-derived object key(FILE-01)·900s expiry 와 함께 ISSUED 행을 발급하고, complete
    는 파일 확정 시 auth/resource/item-active 를 **재검사**하며 tamper(key 불일치)·expiry·
    type·size 를 검증한 뒤 :class:`OrderAttachment` 로 소비한다(REV-00 Order version 1회
    bump). 만료·item 은퇴로 orphan 이 된 티켓은 :mod:`foms.services.upload_cleanup` bounded
    scan provider 가 EXPIRED 로 claim 하고 ``STORAGE_DELETE`` outbox 를 만든다.

    계약(§5.2 UPLOAD-02):

    * **per-file / server-derived key**: ``object_key`` 는 서버가 유도하며(클라이언트 입력
      아님) ``uq_upload_ticket_object_key`` 로 유일하다 — complete 시 exact-match tamper 검사.
    * **900s expiry**: ``expires_at = created_at + 900s``. complete 는 만료 티켓을 거부하고
      cleanup provider 가 만료 ISSUED 를 EXPIRED 로 claim 한다.
    * **item active 재검사**: ``item_id`` 가 있으면 issue/complete 가 identity 활성을
      재확인한다. complete 는 티켓·identity 를 ``FOR UPDATE`` 로 잠가 동시 retire 와
      직렬화한다(item-retire race).
    * **retry idempotent**: 이미 COMPLETED 인 티켓 재확정은 no-op(중복 첨부·version bump 0).

    ``upload_ticket_id`` FK 로 :class:`DomainSideEffectOutbox` 가 이 행을 참조하며(source_domain=
    ``UPLOAD_TICKET``), orphan 은 DB 가 거부한다. DDL 은 migration(``upload_02_00``)과 SSOT 를
    공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'upload_tickets'

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    # 첨부 category(measurement/drawing/construction/as) — auth 정책·확장자 정책의 축.
    category = Column(String(50), nullable=False, default='measurement')
    # 아이템 결합 SSOT = 안정 UUID(order_item_identities.id). None 이면 order 공통 첨부.
    item_id = Column(
        UUIDColumn, ForeignKey('order_item_identities.id', ondelete='SET NULL'), nullable=True)
    # 발급 시점 아이템 슬롯 좌표(provenance). 런타임 결합은 item_id, 이건 기록/재조회용.
    item_index = Column(Integer, nullable=True)
    # server-derived R2 object key(클라이언트 입력 아님). complete 의 exact-match tamper 기준.
    object_key = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # image / video / file
    file_size = Column(Integer, nullable=False, default=0)  # issue 시점 선언 크기(<=max)
    state = Column(String(20), nullable=False, server_default='ISSUED')
    issued_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    row_version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    # created_at + 900s. complete 만료 거부·provider 만료 claim 의 기준.
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('ISSUED','COMPLETED','EXPIRED','CANCELLED')",
            name='ck_upload_ticket_state'),
        # server-derived key 는 티켓당 유일 → complete tamper 검사·중복 발급 차단.
        Index('uq_upload_ticket_object_key', 'object_key', unique=True),
        # bounded cleanup provider 의 만료 claim hot path(만료 ISSUED 를 state,expires_at 순).
        Index('ix_upload_ticket_expiry', 'state', 'expires_at'),
        # item-retire cleanup: 은퇴 identity 의 ISSUED 티켓 claim.
        Index('ix_upload_ticket_item', 'item_id'),
    )


# --------------------------------------------------------------------------- #
# WIZ-01-COMPLETION: drawing wizard transfer-pending child (§ SSOT line 530)
# --------------------------------------------------------------------------- #
#: drawing wizard 전달 대기(sheet PNG export) pending 의 state machine(master plan line 530).
#: READY = export 직후 전달 대기, CLAIMED = 전달이 소비(lock)한 상태, DELETE_PENDING =
#: WIZ-DELETE-01 이 삭제 요청(STORAGE_DELETE outbox enqueue 후), DELETED = worker 가 object
#: 삭제 확인, QUARANTINED = invalid pending 을 삭제하지 않고 보존(§2.6). DELETED 는 terminal.
DRAWING_WIZARD_PENDING_STATES = (
    'READY', 'CLAIMED', 'DELETE_PENDING', 'DELETED', 'QUARANTINED')
#: pending orphan 정리 지평(초). 이 기간 안에 전달/삭제되지 않은 export pending 은 bounded
#: cleanup provider 의 만료 claim 대상이다(active 작업 강제 만료가 아니라 orphan 청소용).
DRAWING_WIZARD_PENDING_TTL_SECONDS = 7 * 24 * 3600


class DrawingWizardPending(Base):
    """drawing wizard 전달 대기 pending child row (WIZ-01-COMPLETION, § SSOT line 530).

    도면 마법사가 export 한 sheet PNG(``orders/<id>/drawing_wizard/exports/`` 접두)를 전달
    대기 상태로 durable 하게 기록하는 정본 child row 다. 기존에는 ``structured_data
    ['drawing_wizard']['pending']`` JSON 에만 있었으나, WIZ-DELETE-01 의 "child row
    DELETE_PENDING + STORAGE_DELETE outbox·worker child-only·Order JSON 0" 불변식이 실
    child 테이블을 요구하므로 이 정본을 도입한다.

    계약(§2.6 / line 530):

    * **server-derived key**: ``object_key`` 는 서버가 유도한 exports prefix 이며
      ``uq_drawing_wizard_pending_object_key`` 로 유일하다 — STORAGE_DELETE 의 대상 기준.
    * **state machine**: READY→CLAIMED(전달)·READY/CLAIMED→DELETE_PENDING(삭제 요청)→
      DELETED(worker 확인), invalid 는 QUARANTINED 로 보존(삭제 금지). 전이는
      :mod:`foms.services.orders.drawing_wizard_pending` 서비스가 강제하고 ``row_version``
      을 optimistic lock 으로 bump 한다.
    * **collection ETag**: 서비스가 order 별 pending 집합의 (id, row_version, state) 로 ETag
      를 유도해 전달/삭제의 collection precondition 으로 쓴다.

    ``wizard_pending_id`` FK 로 :class:`DomainSideEffectOutbox` 가 이 행을 참조하며
    (source_domain=``WIZARD_PENDING``), orphan 은 DB 가 거부한다. DDL 은 migration
    (``wiz_pending_00``)과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'drawing_wizard_pending'

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    # export/전달 대기 pending 을 소유한 도면 담당자(audit; 사용자 삭제 시 SET NULL 로 보존).
    owner_user_id = Column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    # server-derived R2 object key(클라이언트 입력 아님). STORAGE_DELETE 의 exact 대상 기준.
    object_key = Column(String(500), nullable=False)
    state = Column(String(20), nullable=False, server_default='READY')
    row_version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    # created_at + TTL. bounded cleanup provider 의 만료 claim 기준(active 강제 만료 아님).
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('READY','CLAIMED','DELETE_PENDING','DELETED','QUARANTINED')",
            name='ck_drawing_wizard_pending_state'),
        # server-derived key 는 pending 당 유일 → 중복 export 차단·STORAGE_DELETE tamper 기준.
        Index('uq_drawing_wizard_pending_object_key', 'object_key', unique=True),
        # bounded cleanup provider 의 만료 claim hot path(만료 활성 pending 을 state,expires_at 순).
        Index('ix_drawing_wizard_pending_expiry', 'state', 'expires_at'),
    )


# --------------------------------------------------------------------------- #
# ORDER-IMPORT-01: admin Excel import receipt/artifact (§ SSOT line ~1065)
# --------------------------------------------------------------------------- #
#: import artifact state machine. COMPLETED = 주문 batch 생성 성공, FAILED = 전 행 검증
#: 실패(에러 리포트 보관), EXPIRED = 24h 만료를 SIDEFX worker 300s expiry scan provider 가
#: claim 하며 기록(별도 cleanup scheduler 없음). COMPLETED/FAILED 는 24h 만료 대상.
ORDER_IMPORT_ARTIFACT_STATES = ('COMPLETED', 'FAILED', 'EXPIRED')
#: import artifact 보존기간(시간). created_at + 24h 이후 scan provider 가 STORAGE_DELETE.
ORDER_IMPORT_ARTIFACT_TTL_HOURS = 24


class OrderImportArtifact(Base):
    """admin Excel import 의 durable receipt/artifact (ORDER-IMPORT-01).

    한 번의 admin Excel import 를 durable 하게 기록하는 정본 receipt 다. 원본 파일과(검증
    실패 시) 에러 리포트를 **server-derived object key**(클라이언트 경로 아님·public/local
    temp path 아님)로 private 하게 24h 보관하고, ``file_hash`` 로 같은 파일 재import 를
    멱등 처리한다(중복 주문 0). 생성된 Order id 목록을 ``resource_order_ids`` 에 담아
    resources[] 로 돌려준다.

    계약(§ORDER-IMPORT-01):

    * **file-hash receipt**: ``file_hash`` (원본 sha256)로 같은 파일 재import 를 멱등
      처리한다. 만료 전(state<>EXPIRED) 같은 hash 는 ``uq_order_import_artifact_hash``
      partial unique 로 최대 1행이며, 서비스가 기존 receipt 를 그대로 돌려준다(재생성 0).
    * **private source/error artifact 24h**: ``source_object_key``·``error_object_key`` 는
      서버가 유도한 private key(``order_imports/...``)이며 ``expires_at = created_at + 24h``.
    * **all-or-none**: 검증 통과 행만 :func:`~foms.services.orders.order_create.create_order`
      경유 batch 생성하고 한 tx 로 commit 한다(raw Order constructor·row commit 금지).

    ``order_import_artifact_id`` FK 로 :class:`DomainSideEffectOutbox` 가 이 행을 참조하며
    (source_domain=``ORDER_IMPORT_ARTIFACT``), orphan 은 DB 가 거부한다. DDL 은 migration
    (``order_import_00``)과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'order_import_artifacts'

    id = Column(Integer, primary_key=True)
    # import 를 실행한 admin/manager(audit; 사용자 삭제 시 SET NULL 로 artifact 보존).
    uploaded_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    # 원본 파일 sha256 hex — 재import 멱등(receipt)의 정본 키.
    file_hash = Column(String(64), nullable=False)
    # 원본 표시용 파일명(receipt display; 경로 아님).
    filename = Column(String(255), nullable=True)
    row_count = Column(Integer, nullable=False, server_default=text('0'))
    state = Column(String(20), nullable=False, server_default='COMPLETED')
    # server-derived private object key(클라이언트 경로 아님·static/tmp 아님). 만료 정리 대상.
    source_object_key = Column(String(500), nullable=True)
    # 검증 실패 시 에러 리포트 key(FAILED 만 채움). error download 가 이 key 를 스트림.
    error_object_key = Column(String(500), nullable=True)
    # 생성된 Order id 목록(resources[]). all-or-none 성공 시에만 채움.
    resource_order_ids = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    # created_at + 24h. scan provider 만료 claim 의 기준.
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('COMPLETED','FAILED','EXPIRED')",
            name='ck_order_import_artifact_state'),
        # file-hash receipt: 만료 전 같은 hash 는 최대 1행(재import 멱등의 DB backstop).
        Index('uq_order_import_artifact_hash', 'file_hash', unique=True,
              postgresql_where=text("state <> 'EXPIRED'")),
        # bounded cleanup provider 의 만료 claim hot path(COMPLETED/FAILED 를 state,expires_at 순).
        Index('ix_order_import_artifact_expiry', 'state', 'expires_at'),
    )


# --------------------------------------------------------------------------- #
# SESSION-SIGNING-STATE-00: signing-key state machine + WAM entry nonces
# (§2.1 line 225-227). Additive expand only — the existing runtime reads NEITHER
# table nor the new env, so cookie/token semantics are unchanged. The runtime
# provider/serializer switch and activation transitions are SESSION-SIGNING-
# SECRET-01; this packet ships the schema, the singleton EMPTY seed, and the pure
# key-format/inspect/prepare tooling only.
# --------------------------------------------------------------------------- #
SIGNING_STATE_MODES = (
    'EMPTY', 'READY', 'ACTIVE', 'CURRENT_ONLY', 'ROTATION_READY', 'ROTATING',
)
SIGNING_MAINTENANCE_MODES = ('OFF', 'AUTH_ONLY')
SIGNING_LEGACY_CUTOVER_MODES = ('BRIDGE', 'FORCE_REAUTH')


class SecuritySigningState(Base):
    """signing-key state machine 정본(singleton id=1, §2.1 line 227).

    multi-replica 가 요청마다 이 한 행을 읽어 어떤 key 로 sign/verify 할지 판정하는
    정본이다(process cache 금지). SESSION-SIGNING-STATE-00 은 ``mode=EMPTY`` 로 seed 만
    하고 어떤 runtime 도 아직 이 행을 읽지 않는다. prepare CLI 는 deadline-null 전이만
    수행하고(EMPTY→READY 등), active=pending·deadline 기록·READY→ACTIVE 같은 activation
    은 SESSION-SIGNING-SECRET-01 몫이다. key ID 컬럼은 fingerprint 만 담으며 raw/subkey 는
    절대 저장하지 않는다.
    """

    __tablename__ = 'security_signing_state'

    id = Column(Integer, primary_key=True)  # singleton — 항상 1 (ck_signing_state_singleton).
    mode = Column(String(20), nullable=False, server_default='EMPTY')
    maintenance_mode = Column(String(20), nullable=False, server_default='OFF')
    maintenance_started_at = Column(DateTime, nullable=True)
    generation = Column(Integer, nullable=False, server_default=text('0'))
    session_epoch = Column(Integer, nullable=False, server_default=text('0'))
    wam_not_before = Column(DateTime, nullable=True)
    # key-ID fingerprints only (never raw/subkey material).
    active_key_id = Column(String(64), nullable=True)
    previous_key_id = Column(String(64), nullable=True)
    pending_key_id = Column(String(64), nullable=True)
    previous_not_after = Column(DateTime, nullable=True)
    legacy_cutover_mode = Column(String(20), nullable=True)  # BRIDGE|FORCE_REAUTH (null until prepared)
    legacy_flask_not_after = Column(DateTime, nullable=True)
    legacy_wam_not_after = Column(DateTime, nullable=True)
    grace_seconds = Column(Integer, nullable=False, server_default=text('0'))
    row_version = Column(Integer, nullable=False, server_default=text('1'))
    # prepare-time evidence (deadline-null prepare records these; activation reads them).
    prepared_consumer_sha = Column(String(64), nullable=True)
    prepared_key_artifact_sha256 = Column(String(64), nullable=True)
    prepared_rollout_artifact_sha256 = Column(String(64), nullable=True)
    rescue_deployment_sha = Column(String(64), nullable=True)
    prepared_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    updated_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        # 단일 행 강제 — id 는 1 만 허용(singleton 정본).
        CheckConstraint('id = 1', name='ck_signing_state_singleton'),
        CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','CURRENT_ONLY','ROTATION_READY','ROTATING')",
            name='ck_signing_state_mode',
        ),
        CheckConstraint(
            "maintenance_mode IN ('OFF','AUTH_ONLY')",
            name='ck_signing_state_maintenance_mode',
        ),
        CheckConstraint(
            "legacy_cutover_mode IS NULL OR legacy_cutover_mode IN ('BRIDGE','FORCE_REAUTH')",
            name='ck_signing_state_legacy_cutover_mode',
        ),
    )


class WamEntryNonce(Base):
    """WAM entry-token one-time nonce 정본(§2.1 line 227/239).

    ACTIVE runtime 에서 신규 entry issue 는 nonce 행을 insert 하고 exchange 는
    ``UPDATE ... WHERE consumed_at IS NULL AND expires_at > clock_timestamp() RETURNING``
    한 건만 성공시켜 replay 를 막는다(그 issue/exchange 는 SESSION-SIGNING-SECRET-01 몫).
    SESSION-SIGNING-STATE-00 은 테이블만 만든다 — nonce_hash 는 raw nonce 의 해시이며 raw
    는 저장하지 않는다.
    """

    __tablename__ = 'wam_entry_nonces'

    nonce_hash = Column(String(64), primary_key=True)
    subject_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    # ponytail: exchange 는 nonce_hash(PK) 로 조회하므로 추가 인덱스 불필요. 만료 sweep
    #           (expires_at 스캔)은 retention worker(SECRET-01/downstream)가 필요 시 인덱스 추가.


# singleton EMPTY seed — id 만 INSERT 하고 mode/maintenance_mode/generation 등은
# server_default(EMPTY/OFF/0)로 채운다. create_all(테스트/부트스트랩) 경로용이며 Alembic
# 은 migration 에서 동일 seed 를 별도 수행한다(fence/principal trigger 와 같은 이중 SSOT).
SECURITY_SIGNING_STATE_SEED_SQL = (
    "INSERT INTO security_signing_state (id) VALUES (1)"
)

event.listen(
    SecuritySigningState.__table__,
    'after_create',
    DDL(SECURITY_SIGNING_STATE_SEED_SQL),
)


class AuthRateKeyState(Base):
    """auth anti-abuse rate-limit key 상태기계 정본(singleton id=1, AUTH-ACCOUNT-01).

    ``SecuritySigningState`` 와 동형인 prepare/activate 상태기계로, 로그인/telemetry
    등 anti-abuse rate limiter 가 bucket 을 서명할 때 쓰는 **rate key** 의 bootstrap 과
    rotation 을 OPS-APPROVAL 게이트 하에서 관리한다. signing state 가 key ID fingerprint
    만 담고 raw 를 env 에 두는 것과 달리, 이 rate key 는 **AES-256-GCM 으로 암호화된
    envelope(``*_key_ciphertext``)** 로 DB 에 at-rest 저장한다(plaintext 키 저장 금지).
    각 replica 는 env master key 로 복호화해 runtime 에서 읽는다.

    상태 전이:

    * ``EMPTY → READY`` (BOOTSTRAP_PREPARE): 최초 pending key 준비(암호화 envelope +
      fingerprint 기록). ``version`` 증가·``generation`` 을 1 로.
    * ``READY → ACTIVE`` (BOOTSTRAP_ACTIVATE): pending 을 active 로 승격(첫 키 활성).
    * ``ACTIVE → ROTATION_READY`` (ROTATION_PREPARE): 새 pending key(다음 generation).
    * ``ROTATION_READY → ROTATING`` (ROTATION_ACTIVATE): previous=구 active, active=새 키,
      ``previous_not_after`` grace 동안 **dual accept**(구·신 키 모두 유효).
    * ``ROTATING → ACTIVE`` (ROTATION_FINALIZE): grace 경과 후 previous(구 키) 폐기.

    ``version`` 은 매 전이마다 증가하며 OPS-APPROVAL scope 의 ``expected_version`` +
    낙관적 concurrency guard 를 겸한다. ``generation`` 은 key 세대(각 prepare 에서 증가)로
    scope 의 ``expected_generation`` 이다. key_id 컬럼은 material 의 sha256 fingerprint 만
    담으며 raw 는 절대 저장하지 않는다.
    """

    __tablename__ = 'auth_rate_key_state'

    id = Column(Integer, primary_key=True)  # singleton — 항상 1 (ck_auth_rate_key_singleton).
    mode = Column(String(20), nullable=False, server_default='EMPTY')
    version = Column(Integer, nullable=False, server_default=text('1'))
    generation = Column(Integer, nullable=False, server_default=text('0'))
    # key-material fingerprints (sha256 hex) only — never raw key bytes.
    active_key_id = Column(String(64), nullable=True)
    previous_key_id = Column(String(64), nullable=True)
    pending_key_id = Column(String(64), nullable=True)
    # AES-256-GCM encrypted envelopes (JSON text) — never plaintext key material.
    active_key_ciphertext = Column(Text, nullable=True)
    previous_key_ciphertext = Column(Text, nullable=True)
    pending_key_ciphertext = Column(Text, nullable=True)
    previous_not_after = Column(DateTime, nullable=True)  # dual-accept grace deadline (ROTATING).
    # prepare-time evidence (deadline-null prepare records these; activation reads them).
    prepared_key_artifact_sha256 = Column(String(64), nullable=True)
    prepared_rollout_artifact_sha256 = Column(String(64), nullable=True)
    prepared_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    updated_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        # 단일 행 강제 — id 는 1 만 허용(singleton 정본).
        CheckConstraint('id = 1', name='ck_auth_rate_key_singleton'),
        CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','ROTATION_READY','ROTATING')",
            name='ck_auth_rate_key_mode',
        ),
    )


# singleton EMPTY seed — id 만 INSERT 하고 mode/version/generation 은 server_default
# (EMPTY/1/0)로 채운다. create_all(테스트/부트스트랩) 경로용이며 Alembic 은 migration
# 에서 동일 seed 를 별도 수행한다(SecuritySigningState 와 같은 이중 SSOT 패턴).
AUTH_RATE_KEY_STATE_SEED_SQL = (
    "INSERT INTO auth_rate_key_state (id) VALUES (1)"
)

event.listen(
    AuthRateKeyState.__table__,
    'after_create',
    DDL(AUTH_RATE_KEY_STATE_SEED_SQL),
)


# ============================================================================
# CHANNEL-INBOUND-ORDER-01 — 채널 수신 주문 recovery key state + 전역 create flag
#   + dedicated worker heartbeat (§2.1 line 218, §channel line 1066)
# ============================================================================
class ChannelInboundKeyState(Base):
    """채널 수신 파이프라인 encryption key 상태기계 정본(singleton id=1).

    :class:`AuthRateKeyState` 와 **동형** prepare/activate 상태기계다. 채널 수신
    데이터(receipt 봉인 secret 등)를 암호화하는 channel key 의 bootstrap 과 rotation 을
    OPS-APPROVAL 게이트 하에 관리한다. key material 은 AES-256-GCM envelope
    (``*_key_ciphertext``)로 at-rest 저장하며 **plaintext 키를 절대 저장하지 않는다**.
    각 replica 는 env master key(``FOMS_CHANNEL_INBOUND_MASTER_KEY_B64URL``)로 복호화한다.

    상태 전이(AUTH-ACCOUNT-01 미러):

    * ``EMPTY → READY`` (KEY_ROTATION_PREPARE 최초): 첫 pending key stage, generation→1.
    * ``READY → ACTIVE`` (KEY_ROTATION_ACTIVATE 최초): pending→active(첫 키 활성).
    * ``ACTIVE → ROTATION_READY`` (KEY_ROTATION_PREPARE): 새 pending key, generation++.
    * ``ROTATION_READY → ROTATING`` (KEY_ROTATION_ACTIVATE): previous=구 active, active=새 키,
      ``previous_not_after`` grace 동안 dual accept.
    * ``ROTATING → ACTIVE`` (KEY_ROTATION_FINALIZE): grace 경과 **및 old-reference 0** 이어야
      previous(구 키) 폐기(참조가 남은 키 삭제 금지 — rewrap 선행 강제).
    """

    __tablename__ = 'channel_inbound_key_state'

    id = Column(Integer, primary_key=True)  # singleton — 항상 1.
    mode = Column(String(20), nullable=False, server_default='EMPTY')
    version = Column(Integer, nullable=False, server_default=text('1'))
    generation = Column(Integer, nullable=False, server_default=text('0'))
    # key-material fingerprints (sha256 hex) only — never raw key bytes.
    active_key_id = Column(String(64), nullable=True)
    previous_key_id = Column(String(64), nullable=True)
    pending_key_id = Column(String(64), nullable=True)
    # AES-256-GCM encrypted envelopes (JSON text) — never plaintext key material.
    active_key_ciphertext = Column(Text, nullable=True)
    previous_key_ciphertext = Column(Text, nullable=True)
    pending_key_ciphertext = Column(Text, nullable=True)
    previous_not_after = Column(DateTime, nullable=True)  # dual-accept grace deadline.
    prepared_key_artifact_sha256 = Column(String(64), nullable=True)
    prepared_rollout_artifact_sha256 = Column(String(64), nullable=True)
    prepared_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    updated_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        CheckConstraint('id = 1', name='ck_channel_inbound_key_singleton'),
        CheckConstraint(
            "mode IN ('EMPTY','READY','ACTIVE','ROTATION_READY','ROTATING')",
            name='ck_channel_inbound_key_mode',
        ),
    )


CHANNEL_INBOUND_KEY_STATE_SEED_SQL = (
    "INSERT INTO channel_inbound_key_state (id) VALUES (1)"
)

event.listen(
    ChannelInboundKeyState.__table__,
    'after_create',
    DDL(CHANNEL_INBOUND_KEY_STATE_SEED_SQL),
)


class ChannelCreateFlag(Base):
    """전역 채널 주문 생성 on/off 플래그 정본(singleton id=1).

    ``CHANNEL_CREATE_ENABLE`` / ``CHANNEL_CREATE_DISABLE`` OPS operation 이 이 한 행의
    ``state`` 를 뒤집는다. **기본은 DISABLED**(명시 승인 전 자동 생성 0). worker 는 매
    배치마다 이 행을 읽어 DISABLED 면 새 주문을 만들지 않는다(**global flag 우회 worker 0**).
    disable(cutoff) 시 ACCEPTED receipt 는 조용히 버려지지 않고 PAUSED_ACCEPTED 로 보존되며
    (job PAUSED), 재enable 시 되살아난다(유실 0).
    """

    __tablename__ = 'channel_create_flag'

    id = Column(Integer, primary_key=True)  # singleton — 항상 1.
    state = Column(String(20), nullable=False, server_default='DISABLED')
    version = Column(Integer, nullable=False, server_default=text('1'))
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    updated_by_admin_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        CheckConstraint('id = 1', name='ck_channel_create_flag_singleton'),
        CheckConstraint("state IN ('ENABLED','DISABLED')", name='ck_channel_create_flag_state'),
    )


CHANNEL_CREATE_FLAG_SEED_SQL = (
    "INSERT INTO channel_create_flag (id) VALUES (1)"
)

event.listen(
    ChannelCreateFlag.__table__,
    'after_create',
    DDL(CHANNEL_CREATE_FLAG_SEED_SQL),
)


class ChannelInboundWorkerHeartbeat(Base):
    """dedicated 채널 수신 worker heartbeat/lag 정본(SIDEFX-WORKER-01 미러).

    PK ``worker_kind`` upsert(ON CONFLICT DO UPDATE). readiness gate 는 heartbeat 신선도와
    oldest pending lag·RECOVERY_REQUIRED count 로 fail-closed 판정한다.
    """

    __tablename__ = 'channel_inbound_worker_heartbeats'

    worker_kind = Column(String(40), primary_key=True)
    last_heartbeat_at = Column(DateTime, nullable=False)
    oldest_lag_seconds = Column(Integer, nullable=True)
    metadata_json = Column(JSONColumn, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())


# --------------------------------------------------------------------------- #
# CREW-00: 설치 작업자 마스터 + 주문 배정 registry (§5.2 CREW-00)
# --------------------------------------------------------------------------- #
INSTALLATION_ASSIGNMENT_STATUSES = ('ACTIVE', 'RELEASED')


class InstallationWorker(Base):
    """외부 설치 작업자 마스터 (CREW-00, §5.2).

    출고/시공 화면에서 free-name 문자열로 흩어져 있던 설치 작업자를 **정본 마스터
    행**으로 옮긴다. 배정(:class:`OrderInstallationAssignment`)은 항상 이 마스터 id 를
    가리키며, free-name 을 직접 배정하지 않는다(free-name master write 금지 — CREW-00
    경계). crew row 는 순수 운영 마스터이며 **어떤 authorization 판정에도 쓰지 않는다**.

    lifecycle:

    * ``external_worker_id`` = 외부(업체 발급 등) 작업자 식별자. **활성 상태에서만**
      유일하다(``uq_installation_worker_active_external_id`` partial unique) — 비활성화
      후 같은 external ID 로 재등록(신규 행)할 수 있다.
    * ``is_active`` = 활성 여부. 활성 배정(``OrderInstallationAssignment.status='ACTIVE'``)
      이 남아 있는 worker 는 비활성화할 수 없다(in-use → 409, service 레벨 강제).
    * ``user_id`` = linked 내부 계정(선택). 지정하면 실존·활성 User 임을 write 시점에
      검증한다(존재/활성 아니면 거부). authorization 근거가 아니라 표시·연계용이다.

    DDL 은 migration(``crew_00``) 과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'installation_workers'

    id = Column(Integer, primary_key=True)
    external_worker_id = Column(String(64), nullable=False)
    display_name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default='true')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive, server_default=func.now())
    deactivated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # 활성 external_worker_id 는 유일 — 비활성화 뒤 같은 ID 재등록은 partial 이라 허용.
        Index(
            'uq_installation_worker_active_external_id', 'external_worker_id',
            unique=True, postgresql_where=text('is_active'),
        ),
        # picker display projection(활성 worker 정렬 목록) 조회.
        Index('ix_installation_worker_active', 'is_active', 'display_name'),
    )


class OrderInstallationAssignment(Base):
    """주문 ↔ 설치 작업자 배정 history (CREW-00, §5.2).

    한 주문에 활성 설치 작업자를 **0..20명** 배정한다. release 는 hard delete 하지 않고
    ``status='RELEASED'`` + ``released_at/released_by_user_id/release_reason`` 로 **이력을
    보존**한다(released 뒤 같은 worker 재배정 허용). 상한(20) enforcement 와 동시성 직렬화
    (주문 행 ``FOR UPDATE``)는 registry service 몫이며, 아래 partial unique 는 같은 worker
    중복 active 배정을 DB 레벨에서 막는 backstop 이다.

    * ``uq_order_installation_active`` = ``(order_id,worker_id) WHERE status='ACTIVE'`` —
      같은 주문에 같은 worker 를 중복 active 배정 금지(released 뒤 재배정은 허용).

    이 배정 row 는 **authorization 에 쓰지 않는다**(CREW-00 경계). DDL 은 migration
    (``crew_00``) 과 SSOT 를 공유한다(create_all 테스트 lane 동일 스키마).
    """

    __tablename__ = 'order_installation_assignments'

    id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=False,
    )
    worker_id = Column(
        Integer, ForeignKey('installation_workers.id'), nullable=False,
    )
    status = Column(String(20), nullable=False, default='ACTIVE', server_default='ACTIVE')
    assigned_at = Column(DateTime, nullable=False, default=now_utc_naive)
    assigned_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    released_at = Column(DateTime, nullable=True)
    released_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    release_reason = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','RELEASED')",
            name='ck_order_installation_status',
        ),
        # 같은 worker 를 같은 주문에 중복 active 배정 금지(released 뒤 재배정은 허용).
        Index(
            'uq_order_installation_active', 'order_id', 'worker_id',
            unique=True, postgresql_where=text("status = 'ACTIVE'"),
        ),
        # 주문별 active 배정 조회(0..20 카운트·picker) 인덱스.
        Index(
            'ix_order_installation_active_lookup', 'order_id',
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )


# ============================================================================
# CHANNEL-WEBHOOK-AUTH-01 — Webhook acceptance 정본(receipt/conflict/intent/job)
# ============================================================================
#
# SSOT: docs/plans/2026-07-22-foms-full-system-bug-audit-report.md §5.2
#   (CHANNEL-WEBHOOK-AUTH-01 — receipt/conflict/intent/job migration, versioned
#    AES-GCM envelope, stable hash/JCS, log redaction).
#
# ChannelTalk Webhook 수신은 provider token 검증 뒤 **acceptance transaction** 으로만
# 2xx 를 낸다: JCS canonical hash → 30d dedup window → versioned AES-256-GCM envelope →
# receipt/intent/job 를 **한 트랜잭션**에 커밋(transactional outbox). durable job row 가
# 커밋된 뒤에만 2xx 이므로 부분 수용이 없다(DB/job insert 실패 → 롤백 → non-2xx). 실제
# Order mutation 은 downstream worker 소관이라 이 테이블들은 Order 를 건드리지 않는다.
# raw payload 는 평문 저장/로깅하지 않고 envelope(암호문)로만 남긴다.


class ChannelWebhookReceipt(Base):
    """Webhook acceptance ledger — accepted_at + JCS hash + 암호화 envelope.

    30d dedup window 의 기준 row. ``content_hash`` 는 payload 의 JCS canonical sha256
    이고, ``envelope`` 은 raw payload 를 AES-256-GCM 으로 암호화한 versioned 봉투(평문
    미저장)다. 30일이 지나면 같은 hash 라도 새 acceptance 로 취급하므로 hash 를 전역
    unique 로 두지 않고 (content_hash, accepted_at) 인덱스로 window 조회한다.
    """

    __tablename__ = 'channel_webhook_receipts'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String(40), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=False)
    dedup_expires_at = Column(DateTime, nullable=False)
    # versioned AES-256-GCM envelope(version/alg/nonce/aad_sha256/ciphertext) — 평문 0.
    envelope = Column(JSONColumn, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_channel_webhook_receipt_hash_time', 'content_hash', 'accepted_at'),
    )


class ChannelWebhookConflict(Base):
    """중복 재전송(soak) 관측 기록 — masked only(hash/receipt 참조만, payload 0).

    30d window 안에서 같은 ``content_hash`` 가 다시 오면 새 receipt 를 만들지 않고 이
    row 만 append 한다(실 Order/downstream 재실행 없음).
    """

    __tablename__ = 'channel_webhook_conflicts'

    id = Column(Integer, primary_key=True)
    receipt_id = Column(
        UUIDColumn, ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    content_hash = Column(String(64), nullable=False, index=True)
    source = Column(String(40), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ChannelWebhookIntent(Base):
    """수용된 webhook 의 intent marker(receipt 당 1개). 상세 파싱/실행은 downstream."""

    __tablename__ = 'channel_webhook_intents'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_id = Column(
        UUIDColumn, ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
        nullable=False, unique=True,
    )
    intent_type = Column(String(80), nullable=False)
    created_at = Column(DateTime, nullable=False)


class ChannelWebhookJob(Base):
    """durable ID-job(transactional outbox) — receipt 와 같은 tx 에서 생성.

    이 row 가 커밋된 뒤에만 webhook 이 2xx 를 낸다. downstream RQ dispatch 는 best-effort
    이며 실패해도 row 는 ``pending`` 으로 남아 재구동 가능하다(2xx 취소 아님). ``legacy_log_id``
    는 기존 ``channel_inbound_event_logs`` 파이프라인과의 연결 고리다.
    """

    __tablename__ = 'channel_webhook_jobs'

    id = Column(UUIDColumn, primary_key=True, default=lambda: str(uuid.uuid4()))
    receipt_id = Column(
        UUIDColumn, ForeignKey('channel_webhook_receipts.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    status = Column(String(20), nullable=False, server_default='pending')
    legacy_log_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','enqueued','failed')",
            name='ck_channel_webhook_job_status',
        ),
    )


# --------------------------------------------------------------------------- #
# NAVER-INGEST-01: 외부 채널(스마트스토어 등) 주문 수집 링크
# --------------------------------------------------------------------------- #
EXTERNAL_ORDER_CHANNELS = ('NAVER',)
EXTERNAL_ORDER_SYNC_STATUSES = ('LINKED', 'PENDING_REVIEW', 'FAILED')


class ExternalOrderLink(Base):
    """외부 판매채널 주문 ↔ FOMS 주문의 링크 + 원본 스냅샷 (NAVER-INGEST-01 §3.4).

    수집 파이프라인의 **멱등 정본**이다. ``UNIQUE (channel, external_id)`` 가 같은
    ``productOrderId`` 를 두 번 주문으로 만드는 것을 DB 레벨에서 막는다 — 앱 선체크만으로는
    다중 replica 동시 스윕 레이스를 못 막는다(체크와 INSERT 사이에 창이 있다).

    ``Order`` 에 컬럼을 붙이지 않는 이유(설계 결정):

    * 채널이 늘 때마다 ``orders`` 에 컬럼이 늘어난다.
    * 네이버 원본 응답을 보존할 자리가 없다 — 매핑을 나중에 고쳐 **재처리**하려면 원본이 필요하다.
    * 주문 soft delete 수명과 수집 이력 수명이 다르다(주문이 지워져도 "이미 수집함"은 남아야
      재수집으로 되살아나지 않는다). 그래서 ``order_id`` 는 FK 지만 ``ON DELETE SET NULL``.

    ``order_id`` 가 nullable 인 것은 **매핑 실패 보류 상태**(``PENDING_REVIEW``) 때문이다.
    필수 필드가 없거나 형식이 깨진 응답은 쓰레기 주문을 만드는 대신 주문 없이 이 행만 남기고,
    사람이 관리 화면에서 확인 후 수동 연결하거나 폐기한다.

    ``raw_snapshot`` 은 개인정보(실번호·주소)를 그대로 담으므로 **관리자 전용**으로만 노출한다.
    """

    __tablename__ = 'external_order_links'

    id = Column(Integer, primary_key=True)
    # 판매채널 코드. v1 은 'NAVER' 뿐이지만 컬럼으로 둬 채널 확장을 막지 않는다.
    channel = Column(String(20), nullable=False, server_default='NAVER')
    # 채널의 상품주문 단위 고유 id(네이버 productOrderId) — 멱등 키.
    external_id = Column(String(64), nullable=False)
    # 매핑 성공 시 생성된 FOMS 주문. 주문이 hard delete 돼도 수집 이력은 남긴다(SET NULL).
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    # 묶음 주문번호(네이버 orderId). 한 주문에 상품주문이 여럿일 수 있어 참조용으로만 둔다.
    external_order_no = Column(String(64), nullable=True)
    # 채널 원본 응답 그대로(매핑 재처리·감사용). 관리자 전용 노출.
    raw_snapshot = Column(JSONColumn, nullable=True)
    sync_status = Column(String(20), nullable=False, server_default='LINKED')
    # PENDING_REVIEW/FAILED 의 사유(사람이 읽는 문장).
    failure_reason = Column(Text, nullable=True)
    # --- 트리아지(사람 처리) 축 — NAVER-INGEST-01 §8.3 ---
    # ``sync_status`` 에 값을 더하지 않는 이유: 그건 **수집 결과**(LINKED/PENDING_REVIEW/
    # FAILED) 축이고 이건 **사람이 확인했는가** 축이다. 섞으면 "수집은 성공했지만 사람이
    # 아직 안 본" 상태를 표현할 수 없다.
    # NULL = 확인 대기(트리아지 큐에 뜬다). 값이 있으면 큐에서 빠진다.
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by_user_id = Column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    # --- 관계 축 — NAVER-INGEST-02 T16-B ---
    # 이 수집분이 **새 주문**인지, 기존 주문의 **추가결제(차액)** 인지, 취소 뒤 **재결제**인지.
    # sync_status(수집 결과)·reviewed_at(사람 확인)과 또 다른 축이다. ADDON/REPAY 는 주문을
    # 새로 만들지 않고 order_id 에 기존 주문을 넣는다(스펙 §3.1).
    relation = Column(String(10), nullable=False, server_default='NEW')
    # 네이버 발주(발주확인) 상태 — 원본 placeOrderStatus 의 사본. raw_snapshot(JSONB) 안에도
    # 있지만 그걸로 필터하면 인덱스 없는 JSONB 스캔이 된다. 목록 필터 전용 사본이다.
    # 정본은 여전히 raw_snapshot 이며, 재수집·클레임 갱신 때 함께 덮어쓴다.
    place_order_status = Column(String(20), nullable=True)
    # 묶음('집') 키 — mapping.group_key_text(raw_snapshot) 의 사본.
    # (주문번호, 수취인 전화, 주소)를 이은 값이다. 주소는 raw_snapshot 안에서 파이썬으로
    # 조립해야 나오므로 SQL 이 못 센다 — 그래서 컬럼으로 복사해 둔다. 이 컬럼이 없던 시절
    # 이력 표는 주문번호만으로 묶었고, 분할배송(같은 주문번호·다른 주소)에서 확인 큐와
    # 집 수가 영구히 어긋났다(45집 vs 43집).
    # nullable 인 이유: 이 컬럼이 생기기 전 행이 있다. 읽는 쪽이 external_order_no 로
    # 폴백하므로 backfill 전에도 예전과 같은 동작으로 떨어질 뿐 화면은 죽지 않는다.
    group_key = Column(String(200), nullable=True)
    # 매칭 축 사본 — ``order_candidates._snapshot_keys`` 결과의 사본이다(NAVER-INGEST-BACKFILL).
    # ``group_key`` 와 같은 이유로 컬럼이다: 축이 raw_snapshot(JSONB) 안에 있어 SQL 이 못
    # 좁히면, "오늘 실측인데 안 붙은 집" 매칭이 **최신 300행만 훑는 캡**에 갇힌다. 과거
    # 소급 수집(백필)으로 미연결이 1,500행대가 되면 그 캡이 즉시 걸려 띠가 조용히 잘린다.
    # 정본은 여전히 raw_snapshot 이고, 값이 없으면 읽는 쪽이 옛 스캔 경로로 폴백한다.
    recipient_name = Column(String(80), nullable=True)
    recipient_phone_digits = Column(String(20), nullable=True)
    orderer_phone_digits = Column(String(20), nullable=True)
    # 도크(주문 편집 옆 네이버 원본 패널) 반영 상태 — T14-B.
    # {checked, checked_by, checked_at, assigned_main, assigned_by, assigned_at}.
    # reviewed_at 과 다른 축: 저건 큐 이탈(첫 확인 시각 불변), 이건 토글 가능한 표시용.
    triage_state = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc_naive,
                        server_default=func.now())
    updated_at = Column(DateTime, nullable=False, default=now_utc_naive,
                        onupdate=now_utc_naive, server_default=func.now())

    __table_args__ = (
        # 중복 수집 차단의 본체. 앱 체크가 아니라 이 제약이 정본이다.
        UniqueConstraint('channel', 'external_id', name='uq_external_order_link_channel_ext'),
        # COLLECTED = 수집만 됨(주문 미생성, 사람이 "주문 만들기"를 누르면 LINKED 로 간다).
        CheckConstraint(
            "sync_status IN ('COLLECTED','LINKED','PENDING_REVIEW','FAILED')",
            name='ck_external_order_link_status'),
        # 관계 축 닫힌집합. 오타 값이 들어가면 화면 분기가 조용히 새 주문 경로로 떨어진다.
        CheckConstraint(
            "relation IN ('NEW','ADDON','REPAY')",
            name='ck_external_order_link_relation'),
        # 관리 화면: 보류/실패 목록을 최신순으로 훑는 경로.
        Index('ix_external_order_link_status_created', 'sync_status', 'created_at'),
        # 트리아지 큐 hot path: 확인 대기 건만 최신순으로 훑는다(확인 완료분은 인덱스에서 빠진다).
        Index('ix_external_order_link_pending_review', 'channel', 'created_at',
              postgresql_where=text('reviewed_at IS NULL')),
        # 주문 상세에서 "이 주문이 어느 채널 수집분인가" 역조회.
        Index('ix_external_order_link_order', 'order_id'),
        # 안 붙은 수집분 매칭 경로(전화·이름). **미연결 행만** 담는 부분 인덱스다 —
        # 붙고 나면 매칭 대상이 아니므로 인덱스가 이력 전체로 커지지 않는다.
        Index('ix_external_order_link_match_recipient_phone', 'channel',
              'recipient_phone_digits', postgresql_where=text('order_id IS NULL')),
        Index('ix_external_order_link_match_orderer_phone', 'channel',
              'orderer_phone_digits', postgresql_where=text('order_id IS NULL')),
        Index('ix_external_order_link_match_name', 'channel', 'recipient_name',
              postgresql_where=text('order_id IS NULL')),
        # '발주확인 전' 목록 필터 경로(채널 + 발주상태 + 최신순).
        Index('ix_external_order_link_place', 'channel', 'place_order_status', 'created_at'),
        # 이력 표의 묶음 단위 집계·페이징 경로(집 수 COUNT DISTINCT, 페이지 키 조회).
        Index('ix_external_order_link_group', 'channel', 'group_key'),
    )


@event.listens_for(Order, 'before_insert')
def _fill_as_axis_status_on_insert(mapper, connection, target) -> None:
    """새 주문 row 의 AS 축 투영(``as_axis_status``)을 채운다 (AS-AXIS-01).

    AS 대시보드 술어가 이 컬럼을 보므로 **생성 시점부터 stale 이면 안 된다**. 갱신은
    ``sync_erp_flat_columns`` 가 담당하지만, 주문을 만드는 경로는 그 함수를 안 지나는 것도
    있다(엑셀 임포트·테스트 픽스처 등). 명시로 값을 준 경우는 존중한다(백필·복구 도구).

    갱신(before_update)에는 붙이지 않는다 — status 를 덮는 외부 write 가 투영까지 지우면
    2026-08-14 사고가 그대로 재현된다. 투영은 AS 쓰기 경로에서만 바뀐다.
    """
    if getattr(target, 'as_axis_status', None) is not None:
        return
    from foms.services.orders.state_axes import derive_as_axis_status

    target.as_axis_status = derive_as_axis_status(target)


# --------------------------------------------------------------------------- #
# 채널(네이버) 정산 — SETTLE-CHANNEL-01 §3
#
# 네이버 커머스API ``/v1/pay-settle/*`` 응답을 **원본 그대로** 담는 5개 적재 테이블과
# 동기화 실행 이력 1개다. 설계 원칙 셋:
#
# 1. **금액을 재계산하지 않는다.** 네이버가 준 값을 ``Numeric(16, 2)`` 로 그대로 저장한다.
#    취소·환급 행은 음수로 오며 그 부호도 손대지 않는다. 우리가 다시 더하면 네이버 정산서와
#    한 원이라도 어긋나는 순간 회계팀이 두 숫자 중 무엇을 믿어야 할지 알 수 없게 된다.
# 2. **날짜는 ``Date``**(네이버가 주는 KST 달력일 그대로). ``DateTime`` 으로 승격하면 시각이
#    없는 값에 00:00 이 붙고, naive=UTC 저장 규약과 섞여 하루씩 밀린다.
# 3. **적재 단위는 "파티션 통째 교체"**(``channel`` + 축 날짜). 네이버 정산은 소급해서 바뀌므로
#    upsert 로 행을 누적하면 사라진 행이 영원히 남는다. 그래서 이 테이블들에는 멱등 UNIQUE 키가
#    없다 — 멱등성은 "그 날짜 파티션을 지우고 다시 넣는다"가 담보한다.
#
# ``raw_snapshot`` 은 응답 element 원본이다(NOT NULL). 컬럼은 SQL 이 좁혀야 하는 축만 복제한
# 사본이며 정본은 언제나 이 JSONB 다 — ``ExternalOrderLink`` 와 같은 규율이다.
# ``sync_run_id`` 는 ``naver_settle_sync_runs.id`` 를 가리키는 **소프트 참조**(FK 없음):
# 실행 이력은 보존기간이 짧아 먼저 지워질 수 있는데, 그때 정산 행이 함께 지워지거나 이력 삭제가
# 막히면 안 된다.
# --------------------------------------------------------------------------- #
NAVER_SETTLE_CHANNEL_DEFAULT = 'NAVER'
# 매칭 축: MATCHED = FOMS 주문에 붙음, UNMATCHED = 상품주문인데 못 붙음(예외 목록 대상),
# NA = 매칭 대상이 아님(배송비·기타비용 행).
NAVER_SETTLE_MATCH_STATUSES = ('MATCHED', 'UNMATCHED', 'NA')
NAVER_SETTLE_RUN_STATUSES = ('RUNNING', 'OK', 'FAILED', 'ABORTED_QUOTA')
NAVER_SETTLE_RUN_TRIGGERS = ('SCHEDULE', 'MANUAL', 'BACKFILL')


class NaverSettleDaily(Base):
    """일자별 정산 내역 — ``GET /v1/pay-settle/settle/daily`` 의 element 1행.

    파티션 축은 ``settle_expect_date``(정산 예정일)다. 대시보드의 기본 기준일이 예정일이고,
    네이버가 소급 수정하는 단위도 예정일이기 때문이다. 완료일(``settle_complete_date``)은
    돈이 실제로 들어온 날이라 **매출 인식 축과 다르다** — 화면이 둘을 섞지 않도록 둘 다 컬럼으로
    둔다.

    ``settle_method_type`` 이 ``CHARGE_AMT`` 인 행은 계좌로 들어오지 않고 충전금으로 상계된다.
    통장 대사에서 이 행을 빼지 않으면 "입금이 비었다"는 오판이 난다.
    """

    __tablename__ = 'naver_settle_daily'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    # --- 축 ---
    settle_basis_start_date = Column(Date, nullable=True)
    settle_basis_end_date = Column(Date, nullable=True)
    # 파티션 축. NOT NULL 인 유일한 날짜다(이 값이 없으면 어느 파티션인지 정할 수 없다).
    settle_expect_date = Column(Date, nullable=False)
    settle_complete_date = Column(Date, nullable=True)
    # --- 금액(네이버 원본, 부호 포함 그대로) ---
    settle_amount = Column(Numeric(16, 2), nullable=True)
    pay_settle_amount = Column(Numeric(16, 2), nullable=True)
    commission_settle_amount = Column(Numeric(16, 2), nullable=True)
    benefit_settle_amount = Column(Numeric(16, 2), nullable=True)
    deduction_restore_settle_amount = Column(Numeric(16, 2), nullable=True)
    pay_holdback_amount = Column(Numeric(16, 2), nullable=True)
    minus_charge_amount = Column(Numeric(16, 2), nullable=True)
    difference_settle_amount = Column(Numeric(16, 2), nullable=True)
    return_care_settle_amount = Column(Numeric(16, 2), nullable=True)
    normal_settle_amount = Column(Numeric(16, 2), nullable=True)
    quick_settle_amount = Column(Numeric(16, 2), nullable=True)
    preferential_commission_amount = Column(Numeric(16, 2), nullable=True)
    settlement_limit_amount = Column(Numeric(16, 2), nullable=True)
    # --- 입금 채널 ---
    settle_method_type = Column(String(20), nullable=True)
    bank_type = Column(String(40), nullable=True)
    depositor_name = Column(String(100), nullable=True)
    # 계좌번호는 화면에 그대로 내보내지 않는다(뒤 4자리만). 마스킹은 조회 커널 책임.
    account_no = Column(String(60), nullable=True)
    merchant_id = Column(String(40), nullable=True)
    merchant_name = Column(String(100), nullable=True)
    # --- 공통 ---
    raw_snapshot = Column(JSONColumn, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=now_utc_naive)
    sync_run_id = Column(Integer, nullable=True)

    __table_args__ = (
        # 대시보드 기본 경로: 채널 + 정산 예정일 구간 스캔.
        Index('ix_nsd_channel_expect', 'channel', 'settle_expect_date'),
    )


class NaverSettleCase(Base):
    """건별 정산 내역 — ``GET /v1/pay-settle/settle/case`` 의 element 1행.

    파티션 축이 ``settle_expect_date`` 가 아니라 **``search_date``(조회한 날짜)** 인 이유:
    이 API 는 "어느 날짜로 조회했는가"(``period_type`` + 그 날짜)로 결과 집합이 정해진다.
    응답 안의 예정일로 다시 파티션을 나누면 한 번의 조회 결과가 여러 파티션에 흩어져,
    "이 조회를 통째로 다시 넣는다"는 멱등 규칙이 깨진다. ``period_type`` 을 함께 저장하는 것도
    같은 이유다 — 기준이 바뀌면 같은 날짜라도 다른 집합이다.

    ``foms_order_id`` / ``link_id`` 는 **FK 가 없는 소프트 참조**다. 주문이 지워져도 네이버가
    정산한 사실은 남아야 하고, 정산 적재가 주문 삭제를 막아서도 안 된다.
    ``match_status`` 는 ``product_order_type == 'PROD_ORDER'`` 인 행에만 MATCHED/UNMATCHED 를
    쓰고, 배송비·기타비용 행은 'NA' 다 — 붙을 주문이 없는 행을 미매칭으로 세면 매칭률이
    영원히 100% 에 못 닿는다.
    """

    __tablename__ = 'naver_settle_case'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    # --- 축 (조회 파라미터의 사본 — 파티션 정의 그 자체) ---
    search_date = Column(Date, nullable=False)
    period_type = Column(String(48), nullable=False)
    # --- 네이버 원본 날짜 ---
    settle_basis_date = Column(Date, nullable=True)
    settle_expect_date = Column(Date, nullable=True)
    settle_complete_date = Column(Date, nullable=True)
    pay_date = Column(Date, nullable=True)
    # --- 식별자 ---
    order_id = Column(String(40), nullable=True)
    product_order_id = Column(String(40), nullable=True)
    product_order_type = Column(String(40), nullable=True)
    settle_type = Column(String(40), nullable=True)
    product_id = Column(String(40), nullable=True)
    product_name = Column(String(300), nullable=True)
    purchaser_name = Column(String(100), nullable=True)
    # --- 금액(원본 그대로) ---
    pay_settle_amount = Column(Numeric(16, 2), nullable=True)
    total_pay_commission_amount = Column(Numeric(16, 2), nullable=True)
    free_installment_commission_amount = Column(Numeric(16, 2), nullable=True)
    selling_interlock_commission_amount = Column(Numeric(16, 2), nullable=True)
    benefit_settle_amount = Column(Numeric(16, 2), nullable=True)
    settle_expect_amount = Column(Numeric(16, 2), nullable=True)
    merchant_id = Column(String(40), nullable=True)
    merchant_name = Column(String(100), nullable=True)
    contract_no = Column(String(60), nullable=True)
    # --- FOMS 매칭(소프트 참조, FK 없음) ---
    foms_order_id = Column(Integer, nullable=True)
    link_id = Column(Integer, nullable=True)
    match_status = Column(String(20), nullable=False, server_default='NA')
    # --- 공통 ---
    raw_snapshot = Column(JSONColumn, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=now_utc_naive)
    sync_run_id = Column(Integer, nullable=True)

    __table_args__ = (
        # 원장 표의 기본 경로: 채널 + 조회일 구간.
        Index('ix_nsc_channel_search', 'channel', 'search_date'),
        # 주문 상세/워크벤치에서 "이 상품주문의 정산 행" 역조회.
        Index('ix_nsc_product_order', 'product_order_id'),
        # 예외 목록(미매칭)의 hot path. **미매칭 행만** 담는 부분 인덱스라 매칭이 끝난
        # 대다수 행은 인덱스에서 빠진다 — 이력이 쌓여도 예외 조회가 함께 느려지지 않는다.
        # SQLite 테스트 레인은 ``postgresql_where`` 를 무시하고 일반 인덱스로 만든다.
        Index('ix_nsc_unmatched', 'channel', 'search_date',
              postgresql_where=text("match_status = 'UNMATCHED'")),
    )


class NaverSettleCommission(Base):
    """건별 수수료 상세 — ``GET /v1/pay-settle/settle/commission-details`` 의 element 1행.

    ``naver_settle_case`` 와 파티션 규칙이 같다(``search_date`` + ``period_type``). 별도 테이블인
    이유는 **행의 단위가 다르기 때문**이다: 건별 정산은 상품주문 1행이지만 수수료 상세는
    (상품주문 x 수수료 타입) 1행이라, 한 상품주문이 판매수수료·연동수수료로 여러 행이 된다.
    한 테이블에 섞으면 상품주문 수를 세는 모든 쿼리가 조용히 부풀어 오른다.

    주문번호 필드 이름이 ``order_no`` 인 것은 오타가 아니라 네이버 원본이 그렇다
    (건별 정산은 ``orderId``, 수수료 상세는 ``orderNo``).
    """

    __tablename__ = 'naver_settle_commission'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    # --- 축 ---
    search_date = Column(Date, nullable=False)
    period_type = Column(String(48), nullable=False)
    # --- 식별자 ---
    order_no = Column(String(40), nullable=True)
    product_order_id = Column(String(40), nullable=True)
    product_order_type = Column(String(40), nullable=True)
    product_id = Column(String(40), nullable=True)
    product_name = Column(String(300), nullable=True)
    merchant_id = Column(String(40), nullable=True)
    merchant_name = Column(String(100), nullable=True)
    purchaser_name = Column(String(100), nullable=True)
    settle_type = Column(String(40), nullable=True)
    # --- 날짜 ---
    settle_basis_date = Column(Date, nullable=True)
    settle_expect_date = Column(Date, nullable=True)
    settle_complete_date = Column(Date, nullable=True)
    tax_return_date = Column(Date, nullable=True)
    # --- 수수료 ---
    commission_basis_amount = Column(Numeric(16, 2), nullable=True)
    commission_type = Column(String(40), nullable=True)
    pay_means_type = Column(String(40), nullable=True)
    commission_amount = Column(Numeric(16, 2), nullable=True)
    # 매출 연동 수수료의 최대 과금 금액(상한). 상한 소진율 미터의 분모다.
    maximum_selling_interlock_commission_amount = Column(Numeric(16, 2), nullable=True)
    # --- 공통 ---
    raw_snapshot = Column(JSONColumn, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=now_utc_naive)
    sync_run_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_nscm_channel_search', 'channel', 'search_date'),
        Index('ix_nscm_product_order', 'product_order_id'),
    )


class NaverVatDaily(Base):
    """일자별 부가세 신고 내역 — ``GET /v1/pay-settle/vat/daily`` 의 element 1행.

    파티션 축은 ``settle_basis_date``(정산 기준일)다. 부가세는 정산 예정일이 아니라 **매출이
    일어난 기준일**로 신고하므로, 정산 테이블과 축을 맞추면 신고 금액이 달 경계에서 어긋난다.

    ``is_final`` 은 "익월 10일 이후 확정본으로 다시 받아 덮었다"는 표식이다. 그 전에 받은 값은
    잠정치라 화면이 확정처럼 보여주면 안 된다 — 회계팀이 신고에 그대로 쓴다.
    """

    __tablename__ = 'naver_vat_daily'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    settle_basis_date = Column(Date, nullable=False)
    # --- 금액 8종(네이버 원본 순서 그대로) ---
    total_sales_amount = Column(Numeric(16, 2), nullable=True)
    taxation_sales_amount = Column(Numeric(16, 2), nullable=True)
    tax_exemption_sales_amount = Column(Numeric(16, 2), nullable=True)
    credit_card_amount = Column(Numeric(16, 2), nullable=True)
    # 네이버 원본 필드명은 ``cashInComeDeductionAmount`` — 대소문자만 우리 규약으로 폈다.
    cash_income_deduction_amount = Column(Numeric(16, 2), nullable=True)
    # 원본 ``cashOutGoingEvidenceAmount``.
    cash_outgoing_evidence_amount = Column(Numeric(16, 2), nullable=True)
    cash_exclusion_issuance_amount = Column(Numeric(16, 2), nullable=True)
    other_amount = Column(Numeric(16, 2), nullable=True)
    merchant_id = Column(String(40), nullable=True)
    merchant_name = Column(String(100), nullable=True)
    # 익월 10일 이후 확정 재적재분이면 True. 기본은 잠정.
    is_final = Column(Boolean, nullable=False, default=False, server_default='false')
    # --- 공통 ---
    raw_snapshot = Column(JSONColumn, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=now_utc_naive)
    sync_run_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_nvd_channel_basis', 'channel', 'settle_basis_date'),
    )


class NaverVatCase(Base):
    """건별 부가세 신고 내역 — ``GET /v1/pay-settle/vat/case`` 의 element 1행.

    금액 8종은 ``naver_vat_daily`` 와 같은 이름·같은 의미다(일자 합계의 구성 요소). 이름을 맞춰
    두면 일자표와 건별표를 같은 코드로 렌더할 수 있고, 합이 안 맞을 때 어느 건이 원인인지
    바로 짚을 수 있다.

    ``detail_type``(결제대금 정산/혜택 정산/공제·환급)과 ``status``(원주문 매출/주문 취소/…)는
    **다른 축**이다. 취소 행은 status 로 갈리며 금액이 음수로 온다 — 그 부호를 뒤집지 않는다.
    """

    __tablename__ = 'naver_vat_case'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    settle_basis_date = Column(Date, nullable=False)
    order_id = Column(String(40), nullable=True)
    product_order_id = Column(String(40), nullable=True)
    product_order_type = Column(String(40), nullable=True)
    detail_type = Column(String(50), nullable=True)
    status = Column(String(40), nullable=True)
    product_name = Column(String(300), nullable=True)
    # --- 금액 8종(vat_daily 와 동일 이름) ---
    total_sales_amount = Column(Numeric(16, 2), nullable=True)
    taxation_sales_amount = Column(Numeric(16, 2), nullable=True)
    tax_exemption_sales_amount = Column(Numeric(16, 2), nullable=True)
    credit_card_amount = Column(Numeric(16, 2), nullable=True)
    cash_income_deduction_amount = Column(Numeric(16, 2), nullable=True)
    cash_outgoing_evidence_amount = Column(Numeric(16, 2), nullable=True)
    cash_exclusion_issuance_amount = Column(Numeric(16, 2), nullable=True)
    other_amount = Column(Numeric(16, 2), nullable=True)
    merchant_id = Column(String(40), nullable=True)
    merchant_name = Column(String(100), nullable=True)
    # --- 공통 ---
    raw_snapshot = Column(JSONColumn, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=now_utc_naive)
    sync_run_id = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_nvc_channel_basis', 'channel', 'settle_basis_date'),
        Index('ix_nvc_product_order', 'product_order_id'),
    )


class NaverSettleSyncRun(Base):
    """정산 동기화 1회 실행 이력 (SETTLE-CHANNEL-01 §4).

    ``SystemSetting`` 워터마크(마지막 성공 구간)와 **역할이 다르다**: 워터마크는 "지금 어디까지
    믿을 수 있는가" 한 줄이고, 이 표는 "무엇을 언제 몇 번 불렀고 무엇이 소급해서 바뀌었는가"의
    이력이다. 화면 상단의 동기화 배너(마지막 실행·성공·stale 여부)와 예외 목록의 RETRO(소급
    변경) 항목이 이 표를 읽는다.

    ``status`` 에 ``ABORTED_QUOTA`` 가 따로 있는 이유: 네이버 호출 쿼터에 걸려 중간에 멈춘 것은
    실패가 아니라 **정상적인 중단**이고, 이때는 워터마크를 전진시키면 안 된다. FAILED 와 섞으면
    "고쳐야 할 오류"와 "내일 이어서 하면 되는 중단"을 구분할 수 없다.

    ``actor_user_id`` 는 FK 가 없는 소프트 참조다(사용자가 지워져도 실행 이력은 남는다).
    ``dry_run`` 실행은 DB 에 아무것도 쓰지 않으므로 현재 규약상 이 표에도 행을 남기지 않는다 —
    컬럼을 둔 것은 나중에 "모의 실행도 기록하자"로 규약이 바뀔 자리를 비워두기 위함이다.
    """

    __tablename__ = 'naver_settle_sync_runs'

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False, server_default='NAVER')
    started_at = Column(DateTime, nullable=False, default=now_utc_naive)
    finished_at = Column(DateTime, nullable=True)
    # RUNNING / OK / FAILED / ABORTED_QUOTA
    status = Column(String(20), nullable=False)
    # SCHEDULE / MANUAL / BACKFILL
    trigger = Column(String(20), nullable=False)
    actor_user_id = Column(Integer, nullable=True)
    # 요청 구간 {from, to, backfill_from, ...} — 무엇을 달라고 했는지 그대로.
    scope = Column(JSONColumn, nullable=False)
    # 엔드포인트별 호출수·행수와 retro_changes 목록. 실행 중에는 비어 있을 수 있다.
    stats = Column(JSONColumn, nullable=True)
    error = Column(Text, nullable=True)
    dry_run = Column(Boolean, nullable=False, default=False, server_default='false')

    __table_args__ = (
        # 배너·이력 화면: 최근 실행부터 훑는다.
        Index('ix_nssr_started', 'started_at'),
    )
