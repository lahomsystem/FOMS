"""
RQ Worker 태스크 정의.
worker 프로세스에서 실행되며, Flask 앱 컨텍스트 없이 동작.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 프로젝트 루트를 path에 추가 (worker 단독 실행 시)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_repo_root_str = str(_REPO_ROOT)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

__all__ = [
    "create_thumbnail_for_attachment",
    "geocode_order_address",
    "push_order_to_channeltalk",
    "process_channeltalk_inbound",
    "send_push_for_notification_task",
    "run_notification_escalation_task",
    "run_naver_order_sync_task",
]


def create_thumbnail_for_attachment(attachment_id, storage_key):
    """
    주문 첨부 파일 썸네일 생성 (worker 전용).
    RQ job으로 enqueue되어 별도 worker 프로세스에서 실행됨.
    """
    if not attachment_id or not storage_key:
        return
    try:
        from foms.services.storage import get_storage
        from db import db_session
        from models import OrderAttachment

        storage = get_storage()
        result = storage.generate_thumbnail_from_storage_key(storage_key)
        if not result.get("success"):
            return
        thumbnail_key = result.get("thumbnail_key")
        if not thumbnail_key:
            return

        db = db_session()
        try:
            attachment = db.query(OrderAttachment).filter(OrderAttachment.id == int(attachment_id)).first()
            if attachment and not attachment.thumbnail_key:
                attachment.thumbnail_key = thumbnail_key
                db.commit()
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] create_thumbnail_for_attachment error: {e}", exc_info=True)
        raise


def geocode_order_address(order_id):
    """
    주문 주소 지오코딩 (Phase C).
    RQ job으로 enqueue되어 worker에서 실행.
    FOMSAddressConverter로 좌표 획득 후 Order.lat/lng/geocode_status/geocoded_at/address_hash 갱신.
    """
    import datetime

    if not order_id:
        return
    try:
        from db import db_session
        from models import Order
        from foms.services.common.address_converter import FOMSAddressConverter
        from foms.services.geocode_helpers import extract_address_from_order, compute_address_hash

        db = db_session()
        try:
            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                return

            address = extract_address_from_order(order)
            if not address:
                order.lat = None
                order.lng = None
                order.geocode_status = "failed"
                order.geocoded_at = datetime.datetime.now()
                db.commit()
                return

            new_hash = compute_address_hash(address)
            if order.address_hash == new_hash and order.lat is not None and order.lng is not None:
                return

            converter = FOMSAddressConverter()
            lat, lng, status = converter.convert_address(address)

            order.geocoded_at = datetime.datetime.now()
            order.address_hash = new_hash

            if lat is not None and lng is not None:
                order.lat = float(lat)
                order.lng = float(lng)
                order.geocode_status = "success"
            else:
                order.lat = None
                order.lng = None
                order.geocode_status = "failed"

            db.commit()
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] geocode_order_address error: {e}", exc_info=True)
        raise


def push_order_to_channeltalk(delivery_id: int):
    """
    Legacy RQ job drain only.

    Auto-push outbox was removed; stale Redis jobs must no-op without crashing workers.
    """
    if not delivery_id:
        return
    logger.info("[RQ] push_order_to_channeltalk retired (delivery_id=%s)", delivery_id)
    try:
        from db import db_session
        from foms.services.channel_delivery import mark_delivery_status
        from models import ChannelDeliveryLog

        session = db_session()
        try:
            log = session.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == int(delivery_id)).first()
            if not log or log.status not in ("pending", "queue_enqueue_failed", "queue_unavailable"):
                return
            mark_delivery_status(
                session,
                int(delivery_id),
                "ignored_stale",
                "Automatic ChannelTalk push removed",
            )
            session.commit()
        finally:
            session.close()
            db_session.remove()
    except Exception as exc:
        logger.warning(
            "[RQ] legacy push_order_to_channeltalk drain failed for %s: %s",
            delivery_id,
            exc,
        )


def process_channeltalk_inbound(event_log_id: int):
    """
    채널톡 인바운드 웹훅 파싱 및 도메인 생성 (CT-E-03).
    RQ job으로 enqueue되어 worker에서 실행.
    """
    if not event_log_id:
        return

    try:
        from foms.services.channel_inbound import process_inbound_job

        process_inbound_job(event_log_id)
    except Exception as e:
        logger.error(f"[RQ] process_channeltalk_inbound error for log {event_log_id}: {e}", exc_info=True)
        raise


def send_push_for_notification_task(notification_id):
    """
    알림 Web Push 발송 (Phase 3C).
    RQ job으로 enqueue되어 worker에서 실행. payload 는 notification_id 만 받고,
    구독 비밀은 발송 함수 내부에서 DB 재조회한다.
    """
    if not notification_id:
        return
    try:
        from foms.services.notifications.push_sender import send_push_for_notification

        send_push_for_notification(int(notification_id))
    except Exception as e:
        logger.error(
            f"[RQ] send_push_for_notification_task error id={notification_id}: {e}",
            exc_info=True,
        )
        raise


def run_notification_escalation_task():
    """
    미확인 긴급 알림 에스컬레이션 스윕 (Phase 3C).
    외부 스케줄러/CLI 가 주기 실행(간격 60초 이상 권장). worker context 에서 직접 세션 관리.
    commit 후 finalize_escalation_delivery 로 badge/realtime/push 배달.
    """
    try:
        from db import db_session
        from foms.services.notifications.escalation import (
            escalate_overdue_urgent,
            finalize_escalation_delivery,
        )

        db = db_session()
        try:
            result = escalate_overdue_urgent(db)
            db.commit()
            result["delivery"] = finalize_escalation_delivery(
                db,
                created_notification_ids=result.get("created_notification_ids"),
                recipient_user_ids=result.get("recipient_user_ids"),
            )
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_notification_escalation_task error: {e}", exc_info=True)
        raise


def run_naver_fulfillment_task(link_id: int, action: str, actor_user_id=None):
    """발주확인·발송처리 1건 실행 (NAVER-INGEST-02 T16-G, WORKER 전용).

    web 은 enqueue 만 한다 — 커머스API 에 등록된 호출 IP 가 WORKER 것뿐이라 web 에서 나가면
    차단된다. 되돌릴 수 없는 조작이라 멱등 기록은 서비스(fulfillment)가 책임진다.

    Args:
        link_id: 기준 수집 링크 id(같은 집 전체가 함께 처리된다).
        action: ``confirm``(발주확인) 또는 ``dispatch``(발송처리).
        actor_user_id: 화면에서 누른 사람(기록용).

    Returns:
        서비스 결과 dict.
    """
    try:
        from db import db_session
        from foms.services.integrations.naver_commerce.client import NaverCommerceClient
        from foms.services.integrations.naver_commerce.fulfillment import (
            confirm_place_order,
            dispatch_order,
        )

        from foms.services.integrations.naver_commerce.fulfillment import FulfillmentError

        db = db_session()
        try:
            client = NaverCommerceClient()
            if action == "confirm":
                result = confirm_place_order(db, client, link_id=int(link_id),
                                             actor_user_id=actor_user_id)
            elif action == "dispatch":
                result = dispatch_order(db, client, link_id=int(link_id),
                                        actor_user_id=actor_user_id)
            else:
                raise ValueError(f"알 수 없는 작업입니다: {action}")
            db.commit()
            return result
        except FulfillmentError:
            # 서비스가 실패 사유를 **일부러** 상태에 적고 올린다(fulfillment.py 의 except 절).
            # 여기서 통째로 rollback 하면 그 기록까지 지워져, 실패가 DB 어디에도 안 남고
            # 로그·RQ 에만 남는다 — 화면이 "성공 n · 실패 m · 사유" 를 못 보여주는 원인이었다.
            # 이 경로는 네이버 호출이 실패한 것이라 성공 표식은 아직 하나도 쓰이지 않았다.
            db.commit()
            raise
        except Exception:
            # 그 밖의 예외(프로그래밍 오류·DB 오류)는 무엇이 쓰였는지 알 수 없어 되돌린다.
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_fulfillment_task error: {e}", exc_info=True)
        raise


def run_naver_order_sync_task(dry_run: bool = False):
    """네이버 스마트스토어 주문 수집 1회 실행 (NAVER-INGEST-01, WORKER 전용).

    화면의 "지금 수집" 버튼이 이 job 을 enqueue 한다. **web 프로세스에서 직접 호출하면
    안 된다** — 커머스API센터에 등록된 호출 IP 는 WORKER 것뿐이라 web 에서 나가면 차단된다.
    """
    try:
        from db import db_session
        from foms.services.integrations.naver_commerce.ingest import run_sweep

        db = db_session()
        try:
            return run_sweep(db, dry_run=bool(dry_run))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_order_sync_task error: {e}", exc_info=True)
        raise
