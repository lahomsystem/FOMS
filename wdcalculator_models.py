from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from wdcalculator_db import WDCalculatorBase
from foms.services.datetime_kst import format_datetime_kst
import json

SETTINGS_JSON_TYPE = JSON().with_variant(JSONB(), 'postgresql')


class WDCalculatorProductSettings(WDCalculatorBase):
    __tablename__ = 'wdcalculator_product_settings'

    id = Column(Integer, primary_key=True)
    products = Column(SETTINGS_JSON_TYPE, nullable=False, default=list)
    additional_options = Column(SETTINGS_JSON_TYPE, nullable=False, default=list)
    notes_categories = Column(SETTINGS_JSON_TYPE, nullable=False, default=list)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)


class Estimate(WDCalculatorBase):
    __tablename__ = 'estimates'

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(100), nullable=False, index=True)
    # PostgreSQL에서는 JSONB, SQLite 등 로컬 QA 환경에서는 JSON으로 동작시킨다.
    estimate_data = Column(SETTINGS_JSON_TYPE, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        """객체를 딕셔너리로 변환"""
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'estimate_data': self.estimate_data,  # JSONB는 자동으로 dict로 변환됨
            'created_at': format_datetime_kst(self.created_at),
            'updated_at': format_datetime_kst(self.updated_at),
        }

class EstimateHistory(WDCalculatorBase):
    """견적 수정 이력 테이블"""
    __tablename__ = 'estimate_histories'
    
    id = Column(Integer, primary_key=True)
    estimate_id = Column(Integer, ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False, index=True)
    estimate_data = Column(SETTINGS_JSON_TYPE, nullable=False)  # 변경 전 데이터
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    # 관계 설정
    estimate = relationship('Estimate', backref=backref('histories', cascade='all, delete-orphan'))

class EstimateOrderMatch(WDCalculatorBase):
    __tablename__ = 'estimate_order_matches'

    id = Column(Integer, primary_key=True)
    estimate_id = Column(Integer, ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(Integer, nullable=False, index=True)  # FOMS DB의 orders.id 참조 (물리적 FK 아님)
    matched_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    # 관계 설정
    estimate = relationship('Estimate', backref=backref('matches', cascade='all, delete-orphan'))
