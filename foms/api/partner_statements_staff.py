"""협력사 거래명세서 — 우리 CS JSON API(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.5 · §6).

접두 ``/api/partner-statements``:

- ``GET /pending`` 발행 대기(도면 · 옵션 확정, 발행 명세서 없음) · ``GET /issued`` 최근 발행 · 취소.
- ``POST /orders/<order_id>/draft`` 주문 초안 열기(없으면 확정 옵션으로 만든다) · ``GET /<id>`` 명세서 하나.
- ``POST /<id>/save`` CS 가 넣은 값 ``{version, edits}`` · ``/recalc`` 다시 계산 · ``/issue`` 발행 ``{version, date?}`` ·
  ``/revise`` 수정본 ``{reason}`` · ``/void`` 취소 ``{reason}`` · ``/discard`` 초안 지우기 ``{version}``.
- ``POST /issue-complete`` 금액이 다 찬 대기 주문만 한꺼번에 발행.
- ``POST /<id>/questions/<question_id>/answer`` 협력사 금액 문의에 답 ``{text}``(협력사 화면에 보인다).

ADMIN, 또는 CS 권한 팀의 STAFF · MANAGER 만(:func:`foms.services.partners.statements.can_manage_statements` — 쓰기 정책
``PARTNER_STATEMENT`` 게이트와 같은 함수). 협력사 계정은 문지기 허용 목록에 없어 막힌다. 발행 · 수정본 · 취소 · 초안 저장은
감사 한 줄씩. 응답은 ``{"success", "data", "error"}``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.files.routes import build_file_view_url
from foms.services.orders.drawing_confirm_partial import file_item_uids
from foms.services.orders.upload_ticket import _file_type as attachment_file_type  # 확장자→image/video/file (첨부 정본)
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.statement_partner import answer, questions
from foms.services.partners.statement_view import issued_rows, pending_rows, statement_json
from foms.services.partners.statements import (
    StatementError,
    can_manage_statements,
    discard_draft,
    issue,
    open_draft,
    recalc_draft,
    save_draft,
    start_revision,
    void,
)
from models import Order, PartnerStatement, SecurityLog

logger = logging.getLogger(__name__)

partner_statements_staff_api_bp = Blueprint("partner_statements_staff_api", __name__,
                                            url_prefix="/api/partner-statements")

_FAILED = "처리하지 못했습니다. 잠시 뒤 다시 해 주세요."


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _fail(status: int, error: str):
    return jsonify({"success": False, "data": None, "error": error}), status


def _staff() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "is_active", None) is False:
        return None, _fail(401, "로그인이 필요합니다.")
    if not can_manage_statements(user):
        return None, _fail(403, "CS 팀과 관리자만 쓸 수 있습니다.")
    return user, None


def _body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _order(db, order_id: int) -> Optional[Order]:
    return db.query(Order).filter(Order.id == order_id, Order.active_filter(), Order.partner_org_id.isnot(None)).first()


def _log(db, actor: Any, action: str, stmt: PartnerStatement, message: str, **detail: Any) -> None:
    db.add(SecurityLog(user_id=actor.id, action=action, target_type="partner_statement", target_id=int(stmt.id),
                       message=message, detail={"order_id": stmt.order_id, "partner_org_id": stmt.partner_org_id,
                                                "doc_no": stmt.doc_no, "total": int(stmt.total or 0), **detail}))


def _full(db, stmt: PartnerStatement) -> dict[str, Any]:
    order = db.get(Order, stmt.order_id)
    sd = order.structured_data if order is not None and isinstance(order.structured_data, dict) else {}
    # 도면마다 묶인 품목 uid(마법사 제품 시트 · 명시 연결) — 화면이 고른 도면의 묶음만 보인다. 모르면 빈 목록 = 전체.
    drawings = [{**drawing_card(i, f), "no": i, "uids": file_item_uids(sd, f)}
                for i, f in enumerate(final_drawings_for_partner(order) if order else [], start=1) if f.get("key")]
    return {**statement_json(db, stmt), "drawings": drawings, "questions": questions(db, stmt)}


def drawing_card(no: int, f: dict) -> dict[str, Any]:
    """최종 도면 한 장 — 그림이면 썸네일로 보인다(협력사 주문 도면 탭과 같은 판정 · 같은 보기 주소)."""
    name = f.get("filename") or f.get("name") or str(f.get("key") or "").rsplit("/", 1)[-1] or f"{no}번 도면"
    return {"name": f"{no}번 · {name}", "url": build_file_view_url(f["key"]), "is_image": attachment_file_type(name) == "image"}


def _run(work):
    """쓰기 한 번 — 거부 이유는 그대로, DB 오류는 되돌리고 한 줄 기록."""
    db = get_db()
    try:
        result = work(db)
        db.commit()
    except StatementError as exc:
        db.rollback()
        return _fail(exc.status, str(exc))
    except SQLAlchemyError:
        db.rollback()
        logger.exception("[PARTNER_STATEMENT] 쓰기 실패")
        return _fail(500, _FAILED)
    return _ok(result)


@partner_statements_staff_api_bp.route("/pending", methods=["GET"], endpoint="pending")
def api_pending():
    """발행 대기 목록."""
    _actor, denied = _staff()
    if denied:
        return denied
    return _ok({"rows": pending_rows(get_db())})


@partner_statements_staff_api_bp.route("/issued", methods=["GET"], endpoint="issued")
def api_issued():
    """최근 발행 · 취소 명세서."""
    _actor, denied = _staff()
    if denied:
        return denied
    return _ok({"rows": issued_rows(get_db())})


@partner_statements_staff_api_bp.route("/<int:statement_id>", methods=["GET"], endpoint="detail")
def api_detail(statement_id: int):
    """명세서 하나(묶음 · 줄 · 합계 · 최종 도면 이름)."""
    _actor, denied = _staff()
    if denied:
        return denied
    db = get_db()
    stmt = db.get(PartnerStatement, statement_id)
    if stmt is None:
        return _fail(404, "명세서를 찾을 수 없습니다.")
    return _ok(_full(db, stmt))


@partner_statements_staff_api_bp.route("/orders/<int:order_id>/draft", methods=["POST"], endpoint="open_draft")
def api_open_draft(order_id: int):
    """주문 초안 열기 — 없으면 확정 옵션 × 단가표로 만든다."""
    actor, denied = _staff()
    if denied:
        return denied

    def work(db):
        order = _order(db, order_id)
        if order is None:
            raise StatementError("협력사 주문을 찾을 수 없습니다.", 404)
        stmt = open_draft(db, order, actor.id)
        _log(db, actor, "PARTNER_STATEMENT_DRAFT_OPENED", stmt, f"협력사 명세서 초안 열기: 주문 {order_id}")
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/save", methods=["POST"], endpoint="save")
def api_save(statement_id: int):
    """CS 가 넣은 값(커스텀 금액 · 고친 단가 + 이유) 저장."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = save_draft(db, statement_id, body.get("edits"), body.get("version"))
        _log(db, actor, "PARTNER_STATEMENT_DRAFT_SAVED", stmt, f"협력사 명세서 초안 저장: 주문 {stmt.order_id}",
             edits=len(body.get("edits") or []))
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/recalc", methods=["POST"], endpoint="recalc")
def api_recalc(statement_id: int):
    """다시 계산(넣은 값은 같은 줄에 다시 붙는다)."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        head = db.get(PartnerStatement, statement_id)
        order = _order(db, head.order_id) if head is not None else None
        if order is None:
            raise StatementError("명세서를 찾을 수 없습니다.", 404)
        stmt = recalc_draft(db, order, statement_id, body.get("version"))
        _log(db, actor, "PARTNER_STATEMENT_DRAFT_SAVED", stmt, f"협력사 명세서 다시 계산: 주문 {stmt.order_id}")
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/issue", methods=["POST"], endpoint="issue")
def api_issue(statement_id: int):
    """발행 — 번호 · 일자 · 잔액을 정하고 잠근다. 협력사 화면에 보인다."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = issue(db, statement_id, actor.id, base_version=body.get("version"), statement_date=body.get("date"))
        _log(db, actor, "PARTNER_STATEMENT_ISSUED", stmt, f"협력사 명세서 발행: {stmt.doc_no}",
             revision_of=stmt.revision_of)
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/revise", methods=["POST"], endpoint="revise")
def api_revise(statement_id: int):
    """수정본 초안 만들기(이유 필수). 발행 전까지 협력사는 옛 명세서를 본다."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = start_revision(db, statement_id, actor.id, body.get("reason"))
        _log(db, actor, "PARTNER_STATEMENT_REVISED", stmt, f"협력사 명세서 수정본 만들기: 옛 명세서 {statement_id}",
             revision_of=statement_id, reason=stmt.reason)
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/void", methods=["POST"], endpoint="void")
def api_void(statement_id: int):
    """발행 취소(이유 필수)."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = void(db, statement_id, actor.id, body.get("reason"))
        _log(db, actor, "PARTNER_STATEMENT_VOIDED", stmt, f"협력사 명세서 취소: {stmt.doc_no}", reason=stmt.reason)
        return _full(db, stmt)
    return _run(work)


@partner_statements_staff_api_bp.route("/<int:statement_id>/discard", methods=["POST"], endpoint="discard")
def api_discard(statement_id: int):
    """초안 지우기(발행 전만)."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = db.get(PartnerStatement, statement_id)
        if stmt is not None and stmt.status == "DRAFT":
            _log(db, actor, "PARTNER_STATEMENT_DRAFT_DISCARDED", stmt, f"협력사 명세서 초안 지우기: 주문 {stmt.order_id}")
        return {"order_id": discard_draft(db, statement_id, body.get("version"))}
    return _run(work)


@partner_statements_staff_api_bp.route("/issue-complete", methods=["POST"], endpoint="issue_complete")
def api_issue_complete():
    """금액이 다 찬 발행 대기 주문만 한꺼번에 발행(주문마다 따로 커밋 — 하나가 막혀도 나머지는 나간다)."""
    actor, denied = _staff()
    if denied:
        return denied
    db = get_db()
    issued, skipped = [], []
    for row in [r for r in pending_rows(db) if r["complete"] and r["date"]]:
        try:
            order = _order(db, row["order_id"])
            stmt = open_draft(db, order, actor.id)
            stmt = issue(db, stmt.id, actor.id)
            _log(db, actor, "PARTNER_STATEMENT_ISSUED", stmt, f"협력사 명세서 발행(한꺼번에): {stmt.doc_no}", bulk=True)
            db.commit()
            issued.append(stmt.doc_no)
        except StatementError as exc:
            db.rollback()
            skipped.append({"order_id": row["order_id"], "error": str(exc)})
        except SQLAlchemyError:
            db.rollback()
            logger.exception("[PARTNER_STATEMENT] 한꺼번에 발행 실패 order=%s", row["order_id"])
            skipped.append({"order_id": row["order_id"], "error": _FAILED})
    return _ok({"issued": issued, "skipped": skipped})


@partner_statements_staff_api_bp.route("/<int:statement_id>/questions/<int:question_id>/answer", methods=["POST"],
                                       endpoint="answer")
def api_answer(statement_id: int, question_id: int):
    """협력사 금액 문의에 답(고쳐 쓸 수 있다 — 마지막 답이 보인다)."""
    actor, denied = _staff()
    if denied:
        return denied
    body = _body()

    def work(db):
        stmt = db.get(PartnerStatement, statement_id)
        question = answer(db, question_id, actor.id, body.get("text"))
        if stmt is None or question.statement_id != stmt.id:
            raise StatementError("문의를 찾을 수 없습니다.", 404)
        _log(db, actor, "PARTNER_STATEMENT_ANSWERED", stmt, f"협력사 명세서 문의 답: {stmt.doc_no}", question_id=question_id)
        return _full(db, stmt)
    return _run(work)
