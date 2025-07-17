#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app import app
from db import get_db
from models import Order
from datetime import date, datetime, timedelta
import datetime as dt

def debug_shipping_completed():
    with app.app_context():
        db = get_db()
        
        # 기본 쿼리
        base_query = db.query(Order).filter(
            Order.is_regional == True,
            Order.status != 'DELETED'
        )
        
        # 모든 지방 주문 가져오기
        all_regional_orders = base_query.order_by(Order.id.desc()).all()
        
        # 오늘 날짜
        today = date.today()
        print(f"오늘 날짜: {today}")
        
        # 완료된 주문 분류
        completed_orders = [
            order for order in all_regional_orders
            if order.status == 'COMPLETED'
        ]
        print(f"완료된 주문 수: {len(completed_orders)}")

        # 보류 상태 주문 분류
        hold_orders = [
            order for order in all_regional_orders
            if order.status == 'ON_HOLD'
        ]
        print(f"보류 상태 주문 수: {len(hold_orders)}")

        # 상차 예정 알림
        shipping_alerts = []
        for order in all_regional_orders:
            if (getattr(order, 'measurement_completed', False) and 
                order.shipping_scheduled_date and 
                order.shipping_scheduled_date.strip() and
                order.status not in ['COMPLETED', 'ON_HOLD']):
                try:
                    shipping_date = dt.datetime.strptime(order.shipping_scheduled_date, '%Y-%m-%d').date()
                    if shipping_date >= today:
                        shipping_alerts.append(order)
                except (ValueError, TypeError):
                    pass
        print(f"상차 예정 알림 수: {len(shipping_alerts)}")

        # 상차완료: 상차일이 지났지만 완료 처리되지 않은 주문들
        shipping_completed_orders = []
        for order in all_regional_orders:
            if (order.shipping_scheduled_date and 
                order.shipping_scheduled_date.strip() and
                order.status not in ['COMPLETED', 'ON_HOLD']):
                try:
                    shipping_date = dt.datetime.strptime(order.shipping_scheduled_date, '%Y-%m-%d').date()
                    if shipping_date < today:
                        shipping_completed_orders.append(order)
                        print(f"상차완료 주문: ID {order.id}, 고객명: {order.customer_name}, 상차일: {order.shipping_scheduled_date}, 상태: {order.status}")
                except (ValueError, TypeError) as e:
                    print(f"날짜 파싱 오류 - ID {order.id}: {e}")

        print(f"상차완료 주문 수: {len(shipping_completed_orders)}")
        
        # 진행 중인 주문 계산
        shipping_alert_order_ids = {order.id for order in shipping_alerts}
        shipping_completed_order_ids = {order.id for order in shipping_completed_orders}
        pending_orders = [
            order for order in all_regional_orders
            if (order.status not in ['COMPLETED', 'ON_HOLD'] and 
                order.id not in shipping_alert_order_ids and
                order.id not in shipping_completed_order_ids and
                (not getattr(order, 'measurement_completed', False) or 
                 not order.shipping_scheduled_date or 
                 not order.shipping_scheduled_date.strip()))
        ]
        print(f"진행 중인 주문 수: {len(pending_orders)}")
        
        print("\n=== 전체 요약 ===")
        print(f"완료된 주문: {len(completed_orders)}건")
        print(f"보류 상태: {len(hold_orders)}건")
        print(f"상차 예정: {len(shipping_alerts)}건")
        print(f"상차완료: {len(shipping_completed_orders)}건")
        print(f"진행 중: {len(pending_orders)}건")
        print(f"전체 지방 주문: {len(all_regional_orders)}건")

if __name__ == "__main__":
    debug_shipping_completed() 