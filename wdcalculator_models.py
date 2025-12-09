from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from wdcalculator_db import WDCalculatorBase
import json

class Estimate(WDCalculatorBase):
    __tablename__ = 'estimates'

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(100), nullable=False, index=True)
    # JSONB 타입 사용 (PostgreSQL 전용)
    # 딕셔너리/리스트를 그대로 저장하고 조회할 수 있음 (자동 직렬화/역직렬화)
    estimate_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        """객체를 딕셔너리로 변환"""
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'estimate_data': self.estimate_data,  # JSONB는 자동으로 dict로 변환됨
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

class EstimateHistory(WDCalculatorBase):
    """견적 수정 이력 테이블"""
    __tablename__ = 'estimate_histories'
    
    id = Column(Integer, primary_key=True)
    estimate_id = Column(Integer, ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False, index=True)
    estimate_data = Column(JSONB, nullable=False) # 변경 전 데이터
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
