"""
ERP 주문 구조화 데이터 API (structured GET/PUT, parse-text, erp/draft).
"""

import json
import datetime
from flask import Blueprint, request, jsonify, session
from sqlalchemy import text

from db import get_db
from models import Order, OrderEvent
from constants import STATUS
from apps.auth import login_required, role_required
from services.erp_policy import (
    STAGE_LABELS,
    check_quest_approvals_complete,
    create_quest_from_template,
)
from erp_automation import apply_auto_tasks
from erp_order_text_parser import parse_order_text


erp_orders_structured_bp = Blueprint('erp_orders_structured', __name__, url_prefix='/api')


def _ensure_system_build_steps_table(db):
    """B안: 진행상태는 DB 테이블에만 기록. 테이블이 없으면 생성."""
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS system_build_steps (
        step_key VARCHAR(100) PRIMARY KEY,
        status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        message TEXT NULL,
        meta JSONB NULL
    );
    """))
    db.commit()


def _record_build_step(db, step_key, status, message=None, meta=None):
    """빌드 체크포인트 기록. 실패해도 API 자체는 죽지 않게 함."""
    try:
        _ensure_system_build_steps_table(db)
        meta_json = json.dumps(meta, ensure_ascii=False) if isinstance(meta, (dict, list)) else None
        now = datetime.datetime.now()
        db.execute(
            text("""
            INSERT INTO system_build_steps (step_key, status, started_at, completed_at, message, meta)
            VALUES (:k, :s, :started, :completed, :m, CAST(:meta AS JSONB))
            ON CONFLICT (step_key)
            DO UPDATE SET
                status = EXCLUDED.status,
                started_at = COALESCE(system_build_steps.started_at, EXCLUDED.started_at),
                completed_at = CASE WHEN EXCLUDED.status IN ('COMPLETED','FAILED') THEN EXCLUDED.completed_at ELSE system_build_steps.completed_at END,
                message = EXCLUDED.message,
                meta = COALESCE(EXCLUDED.meta, system_build_steps.meta);
            """),
            {
                "k": step_key,
                "s": status,
                "started": now if status == "RUNNING" else None,
                "completed": now if status in ["COMPLETED", "FAILED"] else None,
                "m": message,
                "meta": meta_json,
            }
        )
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[ERP_BETA] build-step log warning: {e}")


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured', methods=['GET'])
@login_required
def api_get_order_structured(order_id):
    """구조화 데이터 조회(전사 공용)."""
    db = get_db()
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        return jsonify({
            'success': True,
            'order_id': order.id,
            'raw_order_text': order.raw_order_text,
            'structured_data': order.structured_data,
            'structured_schema_version': order.structured_schema_version,
            'structured_confidence': order.structured_confidence,
            'structured_updated_at': order.structured_updated_at.strftime('%Y-%m-%d %H:%M:%S') if order.structured_updated_at else None,
            'received_date': order.received_date or '',
            'received_time': order.received_time or ''
        })
    except Exception as e:
        import traceback
        print(f"[ERP_BETA] structured GET 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/<int:order_id>/structured', methods=['PUT'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_put_order_structured(order_id):
    """구조화 데이터 저장(전사 공용)."""
    db = get_db()
    step_key = f"ERP_BETA_API_SAVE_{order_id}"
    _record_build_step(db, step_key, "RUNNING", message="Saving structured data")
    try:
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            _record_build_step(db, step_key, "FAILED", message="Order not found")
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        payload = request.get_json(silent=True) or {}
        structured_data = payload.get('structured_data')
        raw_order_text = payload.get('raw_order_text')
        schema_version = payload.get('structured_schema_version', 1)
        confidence = payload.get('structured_confidence')
        received_date = payload.get('received_date')
        received_time = payload.get('received_time')
        now = datetime.datetime.now()
        draft_cleared = False

        if structured_data is not None and not isinstance(structured_data, dict):
            _record_build_step(db, step_key, "FAILED", message="structured_data must be an object")
            return jsonify({'success': False, 'message': 'structured_data는 JSON 객체여야 합니다.'}), 400

        old_sd = order.structured_data or {}

        if raw_order_text is not None:
            order.raw_order_text = raw_order_text
        if received_date is not None and isinstance(received_date, str) and received_date.strip():
            order.received_date = received_date.strip()
        if received_time is not None and isinstance(received_time, str):
            order.received_time = received_time.strip() or None
        if structured_data is not None:
            if not structured_data.get('workflow'):
                structured_data['workflow'] = {}
            if not structured_data.get('flags'):
                structured_data['flags'] = {}
            if not structured_data.get('assignments'):
                structured_data['assignments'] = {}

            # workflow.stage 변경 감지 + 이벤트
            try:
                new_stage = (structured_data.get('workflow') or {}).get('stage')
                old_stage = (old_sd.get('workflow') or {}).get('stage')
                if new_stage and new_stage != old_stage:
                    # [GDM] Order.status 동기화 (기존 필터링 호환)
                    # ERP Beta 단계가 기존 상태 코드와 호환되면 Order.status 업데이트
                    if new_stage in STATUS:
                        order.status = new_stage
                    elif new_stage == 'AS':
                        # AS 단계는 상세 매핑 필요할 수 있으나, 일단 STATUS에 'AS'가 있으므로 사용
                        # 필요시 'AS_RECEIVED' 등으로 매핑 가능
                        order.status = 'AS'

                    is_quest_complete, missing_teams = check_quest_approvals_complete(old_sd, old_stage)
                    if not is_quest_complete and missing_teams:
                        stage_label = STAGE_LABELS.get(old_stage, old_stage) if old_stage else '알 수 없음'
                        TEAM_LABELS = {
                            'CS': '라홈팀', 'SALES': '영업팀', 'MEASURE': '실측팀',
                            'DRAWING': '도면팀', 'PRODUCTION': '생산팀', 'CONSTRUCTION': '시공팀',
                        }
                        missing_team_labels = [TEAM_LABELS.get(t, t) for t in missing_teams]
                        print(f"경고: [{stage_label}] 단계의 Quest 승인 미완료 팀: {', '.join(missing_team_labels)}")

                    (structured_data.get('workflow') or {})['stage_updated_at'] = datetime.datetime.now().isoformat()
                    db.add(OrderEvent(
                        order_id=order.id,
                        event_type='STAGE_CHANGED',
                        payload={'from': old_stage, 'to': new_stage, 'manual': True},
                        created_by_user_id=session.get('user_id')
                    ))

                    quests = structured_data.get('quests') or []
                    has_new_stage_quest = any(
                        isinstance(q, dict) and q.get('stage') == new_stage for q in quests
                    )
                    if not has_new_stage_quest:
                        new_quest = create_quest_from_template(new_stage, session.get('username') or '', structured_data)
                        if new_quest:
                            if not structured_data.get('quests'):
                                structured_data['quests'] = []
                            structured_data['quests'].append(new_quest)
            except Exception as _e:
                import traceback
                print(f"단계 전환 검증 오류: {_e}")
                print(traceback.format_exc())

            # 긴급 변경 이벤트
            try:
                new_urgent = bool((structured_data.get('flags') or {}).get('urgent'))
                old_urgent = bool((old_sd.get('flags') or {}).get('urgent'))
                if new_urgent != old_urgent:
                    db.add(OrderEvent(
                        order_id=order.id,
                        event_type='URGENT_CHANGED',
                        payload={'from': old_urgent, 'to': new_urgent, 'reason': (structured_data.get('flags') or {}).get('urgent_reason')},
                        created_by_user_id=session.get('user_id')
                    ))
            except Exception:
                pass

            # 일정 변경 이벤트
            try:
                new_meas = ((structured_data.get('schedule') or {}).get('measurement') or {}).get('date')
                old_meas = ((old_sd.get('schedule') or {}).get('measurement') or {}).get('date')
                if new_meas != old_meas:
                    db.add(OrderEvent(
                        order_id=order.id,
                        event_type='MEASUREMENT_DATE_CHANGED',
                        payload={'from': old_meas, 'to': new_meas},
                        created_by_user_id=session.get('user_id')
                    ))
            except Exception:
                pass
            try:
                new_cons = ((structured_data.get('schedule') or {}).get('construction') or {}).get('date')
                old_cons = ((old_sd.get('schedule') or {}).get('construction') or {}).get('date')
                if new_cons != old_cons:
                    db.add(OrderEvent(
                        order_id=order.id,
                        event_type='CONSTRUCTION_DATE_CHANGED',
                        payload={'from': old_cons, 'to': new_cons},
                        created_by_user_id=session.get('user_id')
                    ))
            except Exception:
                pass

            # 오너팀 변경 이벤트
            try:
                new_team = (structured_data.get('assignments') or {}).get('owner_team')
                old_team = (old_sd.get('assignments') or {}).get('owner_team')
                if new_team != old_team:
                    db.add(OrderEvent(
                        order_id=order.id,
                        event_type='OWNER_TEAM_CHANGED',
                        payload={'from': old_team, 'to': new_team},
                        created_by_user_id=session.get('user_id')
                    ))
            except Exception:
                pass

            try:
                apply_auto_tasks(db, order.id, structured_data)
            except Exception as _e:
                print(f"[ERP_BETA] auto-task apply warning: {_e}")

            try:
                meta = structured_data.get('meta') or {}
                if meta.get('draft') is True:
                    meta['draft'] = False
                    meta['finalized_at'] = now.isoformat()
                    structured_data['meta'] = meta
                    draft_cleared = True
            except Exception:
                pass

            order.structured_data = structured_data
        order.structured_schema_version = int(schema_version) if schema_version else 1
        order.structured_confidence = confidence or (structured_data.get('confidence') if structured_data else None)
        order.structured_updated_at = now

        try:
            existing_id = session.get('erp_draft_order_id')
            if existing_id and int(existing_id) == order.id:
                session.pop('erp_draft_order_id', None)
                draft_cleared = True
        except Exception:
            pass

        db.commit()
        _record_build_step(db, step_key, "COMPLETED", message="Saved structured data")
        return jsonify({'success': True, 'draft_cleared': draft_cleared})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_BETA] structured PUT 오류: {e}")
        print(traceback.format_exc())
        _record_build_step(db, step_key, "FAILED", message=str(e))
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/parse-text', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_parse_order_text():
    """텍스트 붙여넣기 → 구조화 파싱(미리보기용). 저장은 하지 않음."""
    db = get_db()
    _record_build_step(db, "ERP_BETA_API_PARSE_TEXT", "RUNNING", message="Parsing order text")
    try:
        payload = request.get_json(silent=True) or {}
        raw_text = (payload.get('raw_text') or '').strip()
        if not raw_text:
            _record_build_step(db, "ERP_BETA_API_PARSE_TEXT", "FAILED", message="raw_text is empty")
            return jsonify({'success': False, 'message': 'raw_text가 필요합니다.'}), 400

        structured = parse_order_text(raw_text)
        _record_build_step(db, "ERP_BETA_API_PARSE_TEXT", "COMPLETED", message="Parsed order text")
        return jsonify({'success': True, 'structured_data': structured})
    except Exception as e:
        import traceback
        print(f"[ERP_BETA] parse-text 오류: {e}")
        print(traceback.format_exc())
        _record_build_step(db, "ERP_BETA_API_PARSE_TEXT", "FAILED", message=str(e))
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_orders_structured_bp.route('/orders/erp/draft', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_create_draft():
    """ERP '새 주문' 화면용 draft 주문 생성. order_id를 먼저 확보."""
    db = get_db()
    try:
        existing_id = session.get('erp_draft_order_id')
        if existing_id:
            order = db.query(Order).filter(Order.id == int(existing_id), Order.status != 'DELETED').first()
            if order:
                return jsonify({'success': True, 'order_id': order.id, 'reused': True})

        now = datetime.datetime.now()
        today = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M')
        structured = {
            'workflow': {'stage': 'RECEIVED', 'stage_updated_at': now.isoformat()},
            'flags': {'urgent': False},
            'assignments': {},
            'schedule': {},
            'meta': {'draft': True, 'created_via': 'ADD_ORDER'},
        }

        order = Order(
            received_date=today,
            received_time=time_str,
            customer_name='ERP Beta',
            phone='000-0000-0000',
            address='-',
            product='ERP Beta',
            options=None,
            notes=None,
            status='RECEIVED',
            is_erp_beta=True,
            raw_order_text='',
            structured_data=structured,
            structured_schema_version=1,
            structured_confidence=None,
            structured_updated_at=now,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        session['erp_draft_order_id'] = order.id
        return jsonify({'success': True, 'order_id': order.id, 'reused': False})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        import traceback
        print(f"[ERP_BETA] draft create error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
