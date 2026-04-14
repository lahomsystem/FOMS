"""
시공 완료 대시보드용 API.
계획서: docs/plans/2026-03-02-construction-completion-dashboard-plan.md
- GET /api/orders/completion: 완료·AS 건 목록 + 시공 사진(category=construction) + 시공자 코멘트.
- POST /api/orders/<id>/settlement/issue: 비용 청구/차감 이벤트 기록 (structured_data.settlement).
"""
import copy
import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderAttachment, OrderEvent, SecurityLog, User
from apps.auth import login_required, get_user_by_id
from apps.api.files import build_file_view_url, build_file_download_url
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import ORDER_SETTLEMENT_ALERT_TARGET_STATUSES

# 완료 대시보드 대상: 시공 완료·AS 접수 등 (정책 상수는 `foms.services.erp_policy` SSOT)
TARGET_STATUSES = ORDER_SETTLEMENT_ALERT_TARGET_STATUSES
CONSTRUCTION_CATEGORY = 'construction'

# 비용 청구 귀속 대상 (계획서 3.1)
SETTLEMENT_DEPARTMENTS = ('SALES', 'DRAWING', 'PRODUCTION', 'CONSTRUCTION', 'CUSTOMER')

erp_orders_completion_bp = Blueprint(
    'erp_orders_completion',
    __name__,
    url_prefix='/api/orders',
)


def _att_view_url(storage_key):
    if not storage_key:
        return ''
    return build_file_view_url(storage_key)


def _att_download_url(storage_key):
    if not storage_key:
        return ''
    return build_file_download_url(storage_key)


@erp_orders_completion_bp.route('/completion', methods=['GET'])
@login_required
def api_orders_completion():
    """완료·AS 건 목록 + 시공 사진 썸네일·URL + 시공자 코멘트(as_content, construction_fail_history 등)."""
    try:
        db = get_db()
        orders = (
            db.query(Order)
            .filter(
                Order.active_filter(),
                Order.is_erp_beta.is_(True),
                Order.status.in_(TARGET_STATUSES),
            )
            .order_by(Order.id.desc())
            .limit(200)
            .all()
        )

        order_ids = [o.id for o in orders]
        if not order_ids:
            return jsonify({'success': True, 'orders': []})

        # N+1 방지: order_id별 construction 첨부 한 번에 조회
        atts = (
            db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id.in_(order_ids),
                OrderAttachment.category == CONSTRUCTION_CATEGORY,
            )
            .order_by(OrderAttachment.order_id, OrderAttachment.created_at.asc())
            .all()
        )
        atts_by_order = {}
        for a in atts:
            atts_by_order.setdefault(a.order_id, []).append(a)

        result = []
        for o in orders:
            sd = _ensure_dict(o.structured_data)
            schedule = sd.get('schedule') or {}
            construction_date = (schedule.get('construction') or {}).get('date')
            parties = sd.get('parties') or {}
            customer_name = (parties.get('customer') or {}).get('name') or getattr(o, 'customer_name', None) or '-'
            manager_name = (parties.get('manager') or {}).get('name') or getattr(o, 'manager_name', None) or '-'
            items = sd.get('items') or []
            product_summary = ', '.join(
                str((it.get('product_name') or '').strip() or '')
                for it in items if isinstance(it, dict) and (it.get('product_name') or '').strip()
            )[:80] or '-'

            # 시공자 코멘트: AS 접수 사유, 시공 불가 이력, 완료 메모 등
            shipment = sd.get('shipment') or {}
            as_content = shipment.get('as_content') or ''
            fail_history = sd.get('construction_fail_history') or []
            completion_note = (sd.get('workflow') or {}).get('completion_note') or ''

            construction_photos = []
            for a in atts_by_order.get(o.id, []):
                construction_photos.append({
                    'id': a.id,
                    'filename': a.filename,
                    'file_type': a.file_type or 'image',
                    'storage_key': a.storage_key,
                    'view_url': _att_view_url(a.storage_key),
                    'download_url': _att_download_url(a.storage_key),
                    'created_at': a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else None,
                })

            result.append({
                'id': o.id,
                'status': o.status,
                'is_self_measurement': getattr(o, 'is_self_measurement', False),
                'construction_date': construction_date,
                'customer_name': customer_name,
                'manager_name': manager_name,
                'product_summary': product_summary,
                'as_content': as_content,
                'construction_fail_history': fail_history,
                'completion_note': completion_note,
                'construction_photos': construction_photos,
            })

        return jsonify({'success': True, 'orders': result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_completion_bp.route('/<int:order_id>/settlement/issue', methods=['POST'])
@login_required
def api_settlement_issue(order_id):
    """비용 청구/차감 이벤트 기록. structured_data.settlement에 deductions 추가, status=ISSUE_RAISED."""
    db = None
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        if order.status not in TARGET_STATUSES:
            return jsonify({'success': False, 'message': '완료·AS 건에만 비용 청구를 등록할 수 있습니다.'}), 400

        data = request.get_json() or {}
        department = (data.get('department') or '').strip().upper()
        amount = data.get('amount')
        reason = (data.get('reason') or '').strip()
        charge_to_user_id = data.get('charge_to_user_id')

        if department not in SETTLEMENT_DEPARTMENTS:
            return jsonify({'success': False, 'message': '귀속 대상이 올바르지 않습니다. (SALES, DRAWING, PRODUCTION, CONSTRUCTION, CUSTOMER)'}), 400
        if amount is None:
            return jsonify({'success': False, 'message': '청구 금액을 입력해주세요.'}), 400
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '청구 금액을 숫자로 입력해주세요.'}), 400
        if amount > 0:
            amount = -amount
        if not reason:
            return jsonify({'success': False, 'message': '사유를 입력해주세요.'}), 400

        charge_to_name = None
        if charge_to_user_id is not None and charge_to_user_id != '':
            if department == 'CUSTOMER':
                charge_to_user_id = None
            else:
                try:
                    uid = int(charge_to_user_id)
                except (TypeError, ValueError):
                    return jsonify({'success': False, 'message': '귀속 인원이 올바르지 않습니다.'}), 400
                charge_user = db.query(User).filter(User.id == uid, User.is_active == True).first()
                if not charge_user:
                    return jsonify({'success': False, 'message': '해당 귀속 인원을 찾을 수 없거나 비활성입니다.'}), 400
                if (charge_user.team or '').strip().upper() != department:
                    return jsonify({'success': False, 'message': '선택한 인원이 해당 부서 소속이 아닙니다.'}), 400
                charge_to_user_id = uid
                charge_to_name = str(charge_user.name) if charge_user.name is not None else None

        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        created_by = user.name if user else 'Unknown'
        now_iso = datetime.datetime.now().isoformat()
        ded_id = f"DED-{order_id}-{int(datetime.datetime.now().timestamp() * 1000)}"

        sd = _ensure_dict(order.structured_data)
        settlement = sd.get('settlement')
        if not isinstance(settlement, dict):
            settlement = {'status': 'PENDING', 'base_cost': None, 'deductions': [], 'final_cost': None}
        deductions = settlement.get('deductions')
        if not isinstance(deductions, list):
            deductions = []
        ded_item = {
            'id': ded_id,
            'department': department,
            'amount': amount,
            'reason': reason,
            'created_at': now_iso,
            'created_by': created_by,
        }
        if charge_to_user_id is not None:
            ded_item['charge_to_user_id'] = charge_to_user_id
        if charge_to_name:
            ded_item['charge_to_name'] = charge_to_name
        deductions.append(ded_item)
        settlement['deductions'] = deductions
        settlement['status'] = 'ISSUE_RAISED'
        base = settlement.get('base_cost')
        if base is not None and isinstance(base, (int, float)):
            settlement['final_cost'] = base + sum(d.get('amount', 0) for d in deductions)
        sd['settlement'] = settlement
        order.structured_data = copy.deepcopy(sd)  # type: ignore[assignment]
        flag_modified(order, 'structured_data')

        event_payload = {
            'deduction_id': ded_id,
            'department': department,
            'amount': amount,
            'reason': reason,
            'created_by': created_by,
        }
        if charge_to_user_id is not None:
            event_payload['charge_to_user_id'] = charge_to_user_id
        if charge_to_name:
            event_payload['charge_to_name'] = charge_to_name
        db.add(OrderEvent(
            order_id=order_id,
            event_type='SETTLEMENT_ISSUE_RAISED',
            payload=event_payload,
            created_by_user_id=user_id,
        ))
        log_msg = f"주문 #{order_id} 비용 청구: {department}"
        if charge_to_name:
            log_msg += f" {charge_to_name}({charge_to_user_id})"
        log_msg += f" {amount}원 — {reason[:50]}"
        db.add(SecurityLog(user_id=user_id, message=log_msg))
        db.commit()

        return jsonify({
            'success': True,
            'message': '비용 청구가 등록되었습니다.',
            'deduction_id': ded_id,
            'settlement': settlement,
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
