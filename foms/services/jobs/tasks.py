"""
RQ Worker 태스크 정의.
worker 프로세스에서 실행되며, Flask 앱 컨텍스트 없이 동작.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 프로젝트 루트를 path에 추가 (worker 단독 실행 시)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_repo_root_str = str(_REPO_ROOT)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

def _register_worker_session_wiring() -> None:
    """worker 프로세스에서도 필요한 전역 세션 훅을 등록한다(HB-S1).

    worker 는 ``rq worker default --url $REDIS_URL`` 로 뜨느라 ``app.py`` 를 import
    하지 않는다(Procfile). 즉 :func:`foms.services.app_init.run_auto_init` 가 돌지
    않아 web 프로세스에 걸린 세션 훅이 **하나도 없다**. 썸네일(:func:`create_thumbnail_for_attachment`
    → ``order_attachments``)·지오코딩(:func:`geocode_order_address` → ``orders``)·
    네이버 동기화가 전부 이 프로세스에서 커밋하므로, 테이블 버전 카운터를 여기서
    등록하지 않으면 그 쓰기가 신호를 못 남기고 그 축을 읽는 화면이 낡은 304 를 받는다.

    등록 대상은 **카운터 훅 하나뿐**이다. 날짜 동기화·대시보드 무효화까지 worker 에
    끌어오는 것은 별개 결정이라 여기서 하지 않는다(현행 동작 유지).
    """
    from foms.services.common.table_version_counter import (
        register_table_version_listener,
    )

    register_table_version_listener()


_register_worker_session_wiring()


__all__ = [
    "create_thumbnail_for_attachment",
    "geocode_order_address",
    "push_order_to_channeltalk",
    "process_channeltalk_inbound",
    "send_push_for_notification_task",
    "run_notification_escalation_task",
    "run_naver_order_sync_task",
    "run_naver_backfill_task",
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
    판정·저장 규칙(주소 추출 → address_hash 스킵 → 변환 → success/failed 기록)은
    foms.services.geocode_helpers.apply_geocode_to_order 가 SSOT다. SIDEFX GEOCODE
    handler 도 같은 함수를 부른다(로직 2벌 금지). 이 함수는 세션 소유만 담당한다.
    """
    if not order_id:
        return
    try:
        from db import db_session
        from models import Order
        from foms.services.geocode_helpers import (
            GEOCODE_OUTCOME_SKIPPED,
            apply_geocode_to_order,
        )

        db = db_session()
        try:
            order = db.query(Order).filter(Order.id == int(order_id)).first()
            if not order:
                return

            if apply_geocode_to_order(order) != GEOCODE_OUTCOME_SKIPPED:
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


#: 네이버 경로가 만드는 알림 중 **웹푸시까지** 내보내는 유형.
#: 두 유형 모두 ``push_sender._DEFAULT_P1_TYPES`` 에 등재돼 있다 — 등재는 발송의
#: 필요조건일 뿐이고(미등재면 no-op), 큐에 넣는 사람이 없으면 아무 일도 일어나지 않는다.
#: 그게 이 파일이 메우는 구멍이다.
_NAVER_PUSH_NOTIFICATION_TYPES = ("NAVER_ORDER_CLAIMED", "NAVER_APP_EXPIRY")


def _naver_notification_baseline(db: Any) -> Optional[int]:
    """이번 태스크가 **새로 만든** 알림만 가려내기 위한 기준선을 읽는다.

    작업 **전에** 최대 Notification id 를 찍어 두고, 커밋 후 그보다 큰 id 만 push 대상으로
    본다. 이미 있던 알림(지난 스윕에서 이미 job 이 걸린 것)을 다시 큐에 넣지 않는 장치다.

    Args:
        db: 태스크가 소유한 DB 세션.

    Returns:
        현재 Notification 최대 id(행이 없으면 0). 조회가 실패하면 None — 그때는 호출자가
        push 를 건너뛴다(기준선 없이 훑으면 옛 알림까지 중복 발송된다).
    """
    try:
        from sqlalchemy import func

        from models import Notification

        return int(db.query(func.max(Notification.id)).scalar() or 0)
    except Exception as exc:  # noqa: BLE001 - 부가 배달의 준비 실패가 본체를 죽이지 않게
        logger.error("[RQ] 네이버 push 기준선 조회 실패 — 이번 실행은 push 를 건너뛴다: %s",
                     exc, exc_info=True)
        return None


def _enqueue_naver_push_after_commit(db: Any, baseline: Optional[int]) -> dict:
    """커밋된 네이버 알림에 웹푸시 job 을 건다 — **커밋 이후에만** 부른다.

    알림을 만드는 쪽(``claim_watch._notify`` · ``app_expiry.check_and_notify``)은 커밋을
    소유하지 않는다. 거기서 enqueue 하면 아직 커밋되지 않은 id 로 job 이 나가고, 워커가
    먼저 깨면 알림을 못 찾아 빈손으로 끝난다. 그래서 커밋을 소유한 이 파일이 건다.

    실패는 **삼키되 반드시 남긴다**: push 는 부가 배달이라 여기서 예외를 올리면 이미
    커밋된 클레임 동기화가 태스크 실패로 뒤집힌 것처럼 보이고, 재시도가 같은 구간을
    또 훑는다. 대신 조용히 넘어가지 않는다(묵시적 무시 금지 — 로그가 유일한 흔적이다).

    Args:
        db: 커밋이 끝난 태스크 세션. enqueue 헬퍼에 **그대로 넘긴다** — 워커에는 요청
            컨텍스트가 없어 헬퍼 기본값(``get_db()``)이 통하지 않는다.
        baseline: :func:`_naver_notification_baseline` 이 준 기준선. None 이면 아무것도
            걸지 않는다.

    Returns:
        ``{"candidates", "enqueued", "skipped", "failed"}`` 집계.
        ``skipped`` 는 헬퍼가 정상 판정으로 안 건 경우(push 기능 off·큐 미가용),
        ``failed`` 는 enqueue 가 예외로 터진 경우다.
    """
    summary = {"candidates": 0, "enqueued": 0, "skipped": 0, "failed": 0}
    if baseline is None:
        return summary

    try:
        from foms.services.notifications.push_sender import enqueue_push_for_notification
        from models import Notification

        rows = (
            db.query(Notification.id)
            .filter(
                Notification.id > int(baseline),
                Notification.notification_type.in_(_NAVER_PUSH_NOTIFICATION_TYPES),
            )
            .order_by(Notification.id)
            .all()
        )
    except Exception as exc:  # noqa: BLE001 - 대상 조회 실패가 수집을 되돌리지 않게
        logger.error("[RQ] 네이버 push 대상 조회 실패(동기화는 유지): %s", exc, exc_info=True)
        return summary

    for row in rows:
        notification_id = int(row[0])
        summary["candidates"] += 1
        try:
            result = enqueue_push_for_notification(notification_id, db=db) or {}
        except Exception as exc:  # noqa: BLE001 - 배달 실패가 본체를 죽이지 않게
            summary["failed"] += 1
            logger.error("[RQ] 네이버 알림 push enqueue 실패 id=%s(동기화는 유지): %s",
                         notification_id, exc, exc_info=True)
            continue
        if result.get("enqueued"):
            summary["enqueued"] += 1
        else:
            # 예외는 아니지만 push 는 안 나갔다 — 이유를 남겨야 "왜 안 왔지"를 셀 수 있다.
            summary["skipped"] += 1
            logger.warning("[RQ] 네이버 알림 push 미발송 id=%s reason=%s",
                           notification_id, result.get("reason"))
    if summary["candidates"]:
        logger.info("[RQ] 네이버 알림 push enqueue %s", summary)
    return summary


#: 끝난 뒤 그 집을 **다시 읽어야 하는** 조작. 전부 네이버 쪽 사실을 바꾼다.
#: (사용자 결정 2026-08-31 — "네 가지 모두" · ``return-reject`` 는 T8-S3 에서 같은 규율로 추가
#: · ``cancel-approve``·``return-approve`` 는 T9 에서 추가. 승인은 네이버 쪽 상태를
#: ``CANCEL_DONE``/``RETURN_DONE`` 으로 **끝내는** 조작이라 다시 읽지 않으면 화면이
#: 승인 전 사실을 계속 말한다.)
REFRESH_AFTER_ACTIONS = ("confirm", "dispatch", "cancel", "return", "return-reject",
                         "cancel-approve", "return-approve")


def _enqueue_refresh_after(action: str, link_id: int, actor_user_id=None) -> bool:
    """조작이 끝난 집을 **자동으로 다시 읽게** 큐에 넣는다.

    왜: ``dispatch_order`` 같은 조작은 ``triage_state`` 만 쓰고 ``raw_snapshot`` 은 손대지
    않는다. 그래서 발송처리를 하고 이력으로 가면 화면의 네이버 축이 **발송 전 사실**을
    계속 말한다. 지금까지는 사람이 `다시 읽기` 를 손으로 눌러야 최신화됐다.

    **실패해도 원래 작업을 깨지 않는다** — 조작은 이미 네이버에 나갔고 커밋됐다. 다시 읽기는
    편의이지 정합성 조건이 아니다. 다만 조용히 삼키지 않고 **로그로 남긴다**(fail-open 규율).

    Args:
        action: 방금 끝난 조작(:data:`REFRESH_AFTER_ACTIONS` 안의 값일 때만 넣는다).
        link_id: 기준 수집 링크 id(그 집 전체가 함께 다시 읽힌다).
        actor_user_id: 누가 눌렀는지(기록용).

    Returns:
        큐에 넣었으면 True.
    """
    if str(action or "").strip().lower() not in REFRESH_AFTER_ACTIONS:
        return False
    try:
        from foms.services.jobs.queue import enqueue_naver_refresh

        queued = bool(enqueue_naver_refresh(int(link_id), actor_user_id=actor_user_id))
    except Exception as exc:  # noqa: BLE001 - 다시 읽기 실패가 조작 결과를 덮으면 안 된다
        logger.warning("[RQ] 조작 뒤 자동 다시읽기 enqueue 실패 link=%s action=%s: %s",
                       link_id, action, exc)
        return False
    if not queued:
        logger.warning("[RQ] 조작 뒤 자동 다시읽기 enqueue 안 됨(큐 없음) link=%s action=%s",
                       link_id, action)
    return queued


def run_naver_fulfillment_task(link_id: int, action: str, actor_user_id=None,
                               reason=None, detail=None, approve=False):
    """발주확인·발송처리·취소·반품접수 1건 실행 (NAVER-INGEST-02 T16-G, WORKER 전용).

    web 은 enqueue 만 한다 — 커머스API 에 등록된 호출 IP 가 WORKER 것뿐이라 web 에서 나가면
    차단된다. 되돌릴 수 없는 조작이라 멱등 기록은 서비스(fulfillment)가 책임진다.

    Args:
        link_id: 기준 수집 링크 id(같은 집 전체가 함께 처리된다).
        action: ``confirm``(발주확인) · ``dispatch``(발송처리) · ``cancel``(판매자 직접취소) ·
            ``return``(판매자 반품 접수, T8-S1) · ``return-reject``(반품 거부, T8-S3) ·
            ``cancel-approve``(구매자 취소요청 승인, T9-G1) ·
            ``return-approve``(반품 승인 독립 경로, T9-G2).
        actor_user_id: 화면에서 누른 사람(기록용).
        reason: 사유 코드(``cancel``·``return``) 또는 **거부 사유 문장**(``return-reject`` —
            코드가 아니라 구매자에게 그대로 가는 문장이다).
        detail: 상세 사유(``cancel``·``return`` 일 때만, 선택).

    Returns:
        서비스 결과 dict.
    """
    try:
        from db import db_session
        from foms.services.integrations.naver_commerce.client import NaverCommerceClient
        from foms.services.integrations.naver_commerce import fulfillment as naver_fulfillment

        from foms.services.integrations.naver_commerce.fulfillment import FulfillmentError

        db = db_session()
        try:
            client = NaverCommerceClient()
            if action == "confirm":
                result = naver_fulfillment.confirm_place_order(
                    db, client, link_id=int(link_id), actor_user_id=actor_user_id)
            elif action == "dispatch":
                result = naver_fulfillment.dispatch_order(
                    db, client, link_id=int(link_id), actor_user_id=actor_user_id)
            elif action == "cancel":
                result = naver_fulfillment.cancel_order(
                    db, client, link_id=int(link_id), reason=str(reason or ""),
                    detail=detail, actor_user_id=actor_user_id)
            elif action == "return":
                # 반품 접수도 되돌릴 수 없다 — 취소와 같은 자리를 쓰는 이유는 아래
                # ``except FulfillmentError`` 의 커밋 규율이다(실패 사유를 DB 에 남긴다).
                result = naver_fulfillment.request_return(
                    db, client, link_id=int(link_id), reason=str(reason or ""),
                    detail=detail, actor_user_id=actor_user_id,
                    approve=bool(approve))
            elif action == "return-reject":
                # 반품 **거부**(T8-S3). 접수·승인과 같은 자리를 쓰는 이유는 아래
                # ``except FulfillmentError`` 의 커밋 규율이다 — 실패 사유가 DB 에 남는다.
                result = naver_fulfillment.reject_return(
                    db, client, link_id=int(link_id), reason=str(reason or ""),
                    actor_user_id=actor_user_id)
            elif action == "cancel-approve":
                # 구매자 취소요청 **승인**(T9-G1). 환불이 확정되고 되돌리는 API 가 없다.
                # 사유를 보내지 않는다 — 네이버 규격이 path 파라미터만 받는다.
                result = naver_fulfillment.approve_cancel(
                    db, client, link_id=int(link_id), actor_user_id=actor_user_id)
            elif action == "return-approve":
                # 반품 **승인**(T9-G2, 접수와 분리된 독립 경로). 접수 경로의
                # ``action="return"`` + ``approve=True`` 와 **일부러 갈라 둔다** —
                # 감사 원장에서 두 갈래를 구분해 읽어야 한다.
                result = naver_fulfillment.approve_return(
                    db, client, link_id=int(link_id), actor_user_id=actor_user_id)
            else:
                raise ValueError(f"알 수 없는 작업입니다: {action}")
            db.commit()
            _enqueue_refresh_after(action, link_id, actor_user_id)
            return result
        except FulfillmentError:
            # 서비스가 실패 사유를 **일부러** 상태에 적고 올린다(fulfillment.py 의 except 절).
            # 여기서 통째로 rollback 하면 그 기록까지 지워져, 실패가 DB 어디에도 안 남고
            # 로그·RQ 에만 남는다 — 화면이 "성공 n · 실패 m · 사유" 를 못 보여주는 원인이었다.
            # 부분 실패(HTTP 200 + failProductOrderInfos)도 이 경로로 온다 — 그때는 성공한
            # 상품주문의 표식도 함께 커밋해야 재시도가 실패한 건만 다시 보낸다.
            db.commit()
            # 부분 성공분은 **네이버에서 이미 바뀌었다**. 여기서 다시 읽지 않으면 그 건들의
            # 스냅샷이 옛 사실로 남아, 실패 띠를 보고 온 사람이 옛 상태를 보게 된다.
            _enqueue_refresh_after(action, link_id, actor_user_id)
            raise
        except Exception as exc:
            # 그 밖의 예외(프로그래밍 오류·DB 오류)는 무엇이 쓰였는지 알 수 없어 되돌린다.
            db.rollback()
            # 되돌린 뒤 **사유만** 따로 남긴다. web 은 이미 "요청했습니다"로 답했고, 화면의
            # 실패 띠가 유일한 통지 경로다(취소는 재시도 버튼도 없다). 기록 자체가 실패하면
            # 원래 예외를 가리지 않도록 조용히 넘어간다.
            try:
                naver_fulfillment.record_task_failure(
                    db, link_id=int(link_id), action=str(action),
                    reason=f"작업이 실패했습니다: {exc}")
                db.commit()
            except Exception as record_exc:  # noqa: BLE001 - 통지 실패가 원인을 덮지 않게
                db.rollback()
                logger.warning("[RQ] 실패 사유 기록 실패 link=%s: %s", link_id, record_exc)
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_fulfillment_task error: {e}", exc_info=True)
        raise


def run_naver_refresh_task(link_id: int, actor_user_id: Optional[int] = None) -> dict:
    """집 1건을 네이버에서 다시 읽는다 (T4, WORKER 전용) — **읽기 전용**.

    web 은 enqueue 만 한다(커머스API 호출 IP 가 WORKER 것뿐이다). 여기서 나가는 네이버
    호출은 상세 조회 하나뿐이라 **되돌릴 수 없는 조작이 없다** — 실패하면 통째로 되돌려도
    안전하다(발송처리 태스크가 실패분을 커밋해 두는 것과 다른 이유가 여기 있다).

    Args:
        link_id: 기준 수집 링크 id(같은 집 전체를 다시 읽는다).
        actor_user_id: 화면에서 누른 사람(기록용 — 지금은 로그에만 남는다).

    Returns:
        :func:`claim_watch.refresh_household` 집계 dict에 ``push``(웹푸시 enqueue 집계)를
        더한 dict.
    """
    try:
        from db import db_session
        from foms.services.integrations.naver_commerce.claim_watch import refresh_household
        from foms.services.integrations.naver_commerce.client import NaverCommerceClient

        db = db_session()
        try:
            baseline = _naver_notification_baseline(db)
            result = refresh_household(db, client=NaverCommerceClient(), link_id=int(link_id))
            db.commit()
            # 웹푸시는 **커밋 뒤**다 — 알림 row 가 확정된 다음이라야 워커가 찾을 수 있다.
            result["push"] = _enqueue_naver_push_after_commit(db, baseline)
            logger.info("[RQ] 네이버 다시 읽기 완료 link=%s actor=%s %s",
                        link_id, actor_user_id, result)
            return result
        except Exception:
            # 불가역 호출이 없으므로 부분 상태를 남기지 않는다 — 다음 시도가 깨끗하다.
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_refresh_task error: {e}", exc_info=True)
        raise


def run_naver_backfill_task(start_iso: str, end_iso: str, dry_run: bool = False) -> dict:
    """네이버 과거 주문 소급 수집(백필) 1회 실행 (NAVER-INGEST-BACKFILL, WORKER 전용).

    워크벤치의 "과거 주문 소급 수집" 이 이 job 을 enqueue 한다. **web 프로세스에서 직접
    호출하면 안 된다** — 등록된 호출 IP 는 WORKER 것뿐이다.

    정상 스윕(:func:`run_naver_order_sync_task`)과 달리 **웹푸시를 걸지 않는다**. 백필은
    알림 자체를 만들지 않으므로(과거 클레임 알림 억제 — 사용자 결정 2026-09-01) 보낼
    알림이 없다.

    Args:
        start_iso: 구간 시작(ISO-8601, KST).
        end_iso: 구간 끝(ISO-8601, KST).
        dry_run: True 면 조회까지만 하고 아무것도 만들지 않는다.

    Returns:
        :func:`backfill.run_backfill` 집계 dict.
    """
    try:
        from datetime import datetime

        from db import db_session
        from foms.services.integrations.naver_commerce.backfill import run_backfill

        start = datetime.fromisoformat(str(start_iso))
        end = datetime.fromisoformat(str(end_iso))
        db = db_session()
        try:
            # run_backfill 이 창마다 커밋한다(중간에 죽어도 받은 원본은 남는다).
            return run_backfill(db, start=start, end=end, dry_run=bool(dry_run))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_backfill_task error: {e}", exc_info=True)
        raise


def run_naver_order_sync_task(dry_run: bool = False) -> dict:
    """네이버 스마트스토어 주문 수집 1회 실행 (NAVER-INGEST-01, WORKER 전용).

    화면의 "지금 수집" 버튼이 이 job 을 enqueue 한다. **web 프로세스에서 직접 호출하면
    안 된다** — 커머스API센터에 등록된 호출 IP 는 WORKER 것뿐이라 web 에서 나가면 차단된다.

    5분 스윕이 만드는 알림은 두 종류다 — 수집 이후 취소·반품(``NAVER_ORDER_CLAIMED``)과
    앱 인증 만료 임박(``NAVER_APP_EXPIRY``). 둘 다 만드는 쪽은 커밋을 소유하지 않으므로
    **커밋한 이 자리**에서 웹푸시 job 을 건다.

    Args:
        dry_run: True 면 조회까지만 하고 아무것도 만들지 않는다(알림도 push 도 없다).

    Returns:
        :func:`ingest.run_sweep` 집계 dict에 ``push``(웹푸시 enqueue 집계)를 더한 dict.
    """
    try:
        from db import db_session
        from foms.services.integrations.naver_commerce.ingest import run_sweep

        db = db_session()
        try:
            baseline = _naver_notification_baseline(db)
            # run_sweep 이 자기 안에서 커밋한다(러너·워커가 tx 를 소유하지 않는 단발 실행).
            # 그래서 이 줄이 끝난 시점이 곧 "알림이 확정된 시점"이다.
            payload = run_sweep(db, dry_run=bool(dry_run))
            payload["push"] = _enqueue_naver_push_after_commit(db, baseline)
            return payload
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            db_session.remove()
    except Exception as e:
        logger.error(f"[RQ] run_naver_order_sync_task error: {e}", exc_info=True)
        raise
