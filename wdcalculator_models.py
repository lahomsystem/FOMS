import datetime
import json
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, TypeDecorator
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import BYTEA
from wdcalculator_db import WDCalculatorBase

class UTF8Text(TypeDecorator):
    """UTF-8 인코딩을 보장하는 Text 타입"""
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        """데이터베이스에 저장할 때 처리 - 인코딩 문제 완전 차단"""
        if value is None:
            return None
            
        # 이미 문자열인 경우
        if isinstance(value, str):
            # 안전하게 UTF-8로 변환 (검증 없이 바로 변환)
            # errors='replace'를 사용하여 손상된 문자를 ?로 대체
            try:
                # 먼저 UTF-8로 인코딩 시도 (이미 UTF-8이면 문제없음)
                # 하지만 검증 단계를 건너뛰고 바로 안전하게 처리
                return value.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            except Exception:
                # 인코딩 실패 시 최후의 수단
                try:
                    # latin1로 인코딩하여 바이트로 변환 후 다른 인코딩으로 디코딩 시도
                    if all(ord(c) < 256 for c in value):
                        try:
                            # CP949로 디코딩 시도
                            decoded = value.encode('latin1').decode('cp949', errors='replace')
                            return decoded.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                        except:
                            pass
                    # 실패 시 강제 변환
                    return value.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
                except:
                    # 최종 실패 시 원본 반환 (SQLAlchemy가 처리하도록)
                    return str(value)
            
        # bytes인 경우 디코딩 시도
        if isinstance(value, bytes):
            # 1. UTF-8 시도
            try:
                decoded = value.decode('utf-8')
                # 디코딩 성공 시 UTF-8로 재인코딩하여 검증
                decoded.encode('utf-8').decode('utf-8')
                return decoded
            except UnicodeDecodeError:
                pass
                
            # 2. CP949 (Windows 한글) 시도
            try:
                decoded = value.decode('cp949')
                # UTF-8로 재인코딩하여 정규화
                return decoded.encode('utf-8', errors='replace').decode('utf-8')
            except UnicodeDecodeError:
                pass
                
            # 3. EUC-KR 시도
            try:
                decoded = value.decode('euc-kr')
                return decoded.encode('utf-8', errors='replace').decode('utf-8')
            except UnicodeDecodeError:
                pass
                
            # 4. 실패 시 강제 변환 (errors='ignore'로 손실 최소화)
            return value.decode('utf-8', errors='ignore')
            
        # 기타 타입은 문자열로 변환
        try:
            str_value = str(value)
            # 변환된 문자열도 UTF-8 검증
            str_value.encode('utf-8').decode('utf-8')
            return str_value
        except:
            # 변환 실패 시 안전하게 처리
            return str(value).encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    
    def process_result_value(self, value, dialect):
        """데이터베이스에서 읽을 때 처리"""
        if value is None:
            return None
        
        # 이미 문자열인 경우
        if isinstance(value, str):
            return value
        
        # bytes인 경우 안전하게 디코딩
        if isinstance(value, bytes):
            # UTF-8 -> CP949 -> EUC-KR -> Latin1 순서로 시도
            for encoding in ['utf-8', 'cp949', 'euc-kr', 'latin1']:
                try:
                    return value.decode(encoding)
                except UnicodeDecodeError:
                    continue
            
            # 모든 인코딩 실패 시
            return value.decode('utf-8', errors='replace')
        
        return str(value)

class Estimate(WDCalculatorBase):
    """견적 저장 테이블"""
    __tablename__ = 'estimates'
    
    id = Column(Integer, primary_key=True)
    customer_name = Column(String, nullable=False, index=True)  # 고객명 (검색용 인덱스)
    estimate_data = Column(UTF8Text, nullable=False)  # 견적 데이터 (JSON 문자열, UTF-8 보장)
    created_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=False)
    
    # 관계: 주문 매칭
    order_matches = relationship("EstimateOrderMatch", back_populates="estimate", cascade="all, delete-orphan")
    
    def to_dict(self):
        """견적 데이터를 딕셔너리로 변환"""
        estimate_data = None
        if self.estimate_data:
            try:
                # UTF8Text 타입이 이미 문자열로 변환해주므로 직접 파싱
                if isinstance(self.estimate_data, str):
                    estimate_data = json.loads(self.estimate_data)
                elif isinstance(self.estimate_data, bytes):
                    # 혹시 bytes로 온 경우 여러 인코딩 시도
                    for encoding in ['utf-8', 'cp949', 'euc-kr', 'latin1']:
                        try:
                            decoded = self.estimate_data.decode(encoding)
                            estimate_data = json.loads(decoded)
                            break
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                    if estimate_data is None:
                        # 모든 인코딩 실패 시 errors='replace'로 처리
                        decoded = self.estimate_data.decode('utf-8', errors='replace')
                        estimate_data = json.loads(decoded)
                else:
                    estimate_data = json.loads(str(self.estimate_data))
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as e:
                # 파싱 실패 시 빈 딕셔너리 반환
                import traceback
                print(f"Warning: Failed to parse estimate_data for estimate {self.id}: {str(e)}")
                print(traceback.format_exc())
                estimate_data = {}
        
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'estimate_data': estimate_data,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

class EstimateOrderMatch(WDCalculatorBase):
    """견적-주문 매칭 테이블 (FOMS 주문과의 연결)"""
    __tablename__ = 'estimate_order_matches'
    
    id = Column(Integer, primary_key=True)
    estimate_id = Column(Integer, ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(Integer, nullable=False, index=True)  # FOMS 주문 ID (외래키는 사용하지 않음 - 독립성 유지)
    matched_at = Column(DateTime, default=datetime.datetime.now, nullable=False)
    
    # 관계
    estimate = relationship("Estimate", back_populates="order_matches")
    
    def to_dict(self):
        """매칭 데이터를 딕셔너리로 변환"""
        return {
            'id': self.id,
            'estimate_id': self.estimate_id,
            'order_id': self.order_id,
            'matched_at': self.matched_at.strftime('%Y-%m-%d %H:%M:%S') if self.matched_at else None
        }

