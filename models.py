import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from db import Base

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    received_date = Column(String, nullable=False)
    received_time = Column(String)
    customer_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    address = Column(Text, nullable=False)
    product = Column(String, nullable=False)
    options = Column(Text)
    notes = Column(Text)
    status = Column(String, default='RECEIVED')
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
    
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False, default='사용자')
    role = Column(String, nullable=False, default='VIEWER')
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