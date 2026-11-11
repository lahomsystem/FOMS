"""[수정하기] '왜 고쳤나요(자세히)' · 사진 — 저장 · 지우기 · 보기 권한(설계서 17.6.1 (a) · (b) · 사장님 결정 D94).

화면(:mod:`foms.web.cs_agent_send`)과 JSON API(:mod:`foms.api.cs_agent_edit_detail`)가 이 모듈만 부른다. **[보내기]를 막지 않는다**
— 보내기가 먼저 끝나 차례의 끝난 꼴이 '고침'(``edited``)이 된 뒤에만 저장할 곳이 생긴다(그대로 · 버림 · 직접 답 줄은 409).
실패해도 보낸 글은 그대로다.

- **권한(D94)**: 적기 · 올리기 · 지우기 = 그 차례를 보낸 직원(보낸 때부터 :data:`WINDOW` 24시간) · ADMIN(언제나). 사진 원본 보기 =
  ADMIN · 올린 직원(올린 때부터 24시간). 링크 한 번용 표(30분)가 아니라 로그인 세션 + '보낸 직원 = 나'로 본다. 상담 직원 ·
  ADMIN 인지는 API · 화면이 :func:`.send_auth.can_use_send_screen` 으로 먼저 본다.
- **스위치**: 관리 패널 '자세한 이유 칸' · '사진 올리기'(처음 끔) · 비상 정지(모두 멈춤). 사진은 저장소가 R2 · S3 일 때만 — 로컬
  저장소는 누구나 여는 정적 경로라 늘 끔.
- **자세한 이유**: 1~:data:`MAX_DETAIL` 자(줄 바꿈 포함). 받은 글에 개인정보 꼴(전화 · 주소 · 이름꼴 …)이 있으면 **저장하지 않고**
  400(``detail_private``), 없으면 한 번 더 가려 가림 검사 0 일 때만 저장한다. 다시 보내면 덮어쓴다(빈 글은 지움).
- **사진**: :mod:`.edit_photos` 가 다시 본다(꼴 · 크기 · 다시 그리기). 살아 있는 사진 :data:`~.edit_photos.MAX_PHOTOS` 장까지 ·
  같은 사진(sha256) 두 번 거절. 저장소에 먼저 올리고 줄을 넣는다(줄을 못 넣으면 올린 것을 지운다). 응답에는 URL · key 가 없다.
- **감사 원장**: ``CS_AGENT_EDIT_DETAIL`` · ``CS_AGENT_PHOTO_ADD`` · ``CS_AGENT_PHOTO_DELETE`` — 차례 id · 코드 · 숫자만(글 · key 없음).
  로그도 차례 id · seq · 코드 · 바이트 수만 싣는다.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from foms.persistence.main.models import CsAgentTurn, CsAgentTurnPhoto
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.edit_detail_settings import DETAIL_FIELD, PHOTOS_FIELD, switch_value
from foms.services.cs_agent.edit_photos import MAX_PHOTOS, PhotoError, photo_key, redraw
from foms.services.cs_agent.masking import MaskLeak, leak_counts
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import read_switch
from foms.services.cs_agent.turns_fields import masked_or_none
from foms.services.storage import get_storage
from models import SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_DETAIL", "MESSAGES", "SEQ_MAX", "WINDOW", "DetailResult", "Switches", "add_photo", "delete_photo", "detail_text",
    "photo_for_view", "photo_rows", "save_detail", "switches",
]

MAX_DETAIL = 1000
SEQ_MAX = 10  # 차례 번호 상한(직원이 지운 줄도 번호를 차지한다 — 살아 있는 사진 상한은 MAX_PHOTOS)
WINDOW = datetime.timedelta(hours=24)
OUTCOME_EDITED = "edited"
CLOUD_TYPES = ("r2", "s3")
MESSAGES: dict[str, str] = {
    "saved": "자세한 이유를 저장했어요.",
    "cleared": "자세한 이유를 지웠어요.",
    "photo_saved": "사진을 저장했어요.",
    "photo_deleted": "사진을 지웠어요(저장소에서도 지움).",
    "detail_off": "지금은 자세한 이유 칸이 꺼져 있어요.",
    "photo_off": "지금은 사진 올리기가 꺼져 있어요.",
    "not_edited": "고쳐 보낸 초안에만 이유 · 사진을 남길 수 있어요(먼저 보내 주세요).",
    "not_yours": "이 초안을 보낸 직원 · 관리자만 남길 수 있어요.",
    "too_late": "보낸 지 24시간이 지나 더 남길 수 없어요.",
    "not_found": "초안이나 사진을 찾지 못했어요.",
    "bad_request": "입력을 확인해 주세요.",
    "detail_private": "손님 정보(이름 · 전화 · 주소)가 들어 있어 저장하지 않았어요 — 지우고 다시 저장해 주세요.",
    "photo_empty": "빈 파일이에요.",
    "photo_size": "사진이 너무 커요(한 장 5MB · 픽셀 4천만까지).",
    "photo_format": "JPEG · PNG · WebP 사진만 받아요(HEIC · GIF · PDF · 동영상은 안 돼요).",
    "photo_full": f"사진은 {MAX_PHOTOS}장까지예요.",
    "photo_same": "같은 사진을 이미 올렸어요.",
    "store_failed": "사진을 저장소에 올리지 못했어요 — 다시 눌러 주세요(보낸 글은 그대로예요).",
    "delete_failed": "저장소에서 지우지 못했어요 — 잠시 뒤 다시 눌러 주세요.",
    "busy": "같은 때 다른 사진이 올라갔어요 — 다시 눌러 주세요.",
}


@dataclass(frozen=True)
class DetailResult:
    """결과 — 코드 · HTTP 상태 · 숫자와 코드뿐인 ``data``(글 · key · URL 없음)."""

    code: str
    status: int
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """성공 꼴인가."""
        return self.status < 300

    @property
    def message(self) -> str:
        """화면 글."""
        return MESSAGES.get(self.code, MESSAGES["bad_request"])


@dataclass(frozen=True)
class Switches:
    """화면 · API 스위치 — 자세한 이유 칸 · 사진 올리기(비상 정지 · 로컬 저장소면 끔)."""

    detail: bool
    photos: bool


def _fail(code: str, status: int, **data: Any) -> DetailResult:
    return DetailResult(code, status, data)


def _is_admin(user: Any) -> bool:
    return (getattr(user, "role", None) or "").strip().upper() == "ADMIN"


def switches(session: Any, storage: Any = None, *, with_photos: bool = True) -> Switches:
    """지금 스위치(DB 에서 새로) — 비상 정지면 둘 다 끔, 사진은 자세한 이유 칸이 켜졌고 저장소가 클라우드일 때만.
    ``with_photos`` 가 거짓이면 저장소를 보지 않는다(사진은 끔으로 둔다 — 자세한 이유만 볼 때)."""
    if not read_switch(session):
        return Switches(False, False)
    cfg = read_settings(session, log=False)
    detail = switch_value(cfg, DETAIL_FIELD)
    if not (with_photos and detail and switch_value(cfg, PHOTOS_FIELD)):
        return Switches(detail, False)
    cloud = getattr(storage if storage is not None else get_storage(), "storage_type", "") in CLOUD_TYPES
    return Switches(detail, cloud)


def _audit(session: Any, action: str, turn_id: int, user_id: int, result: DetailResult) -> DetailResult:
    """감사 원장 한 줄(누가 · 어느 차례 · 결과 코드 · 숫자 — 글 · key 없음). 못 남겨도 결과는 그대로다."""
    detail = {"code": result.code, "status": result.status,
              **{k: v for k, v in result.data.items() if k in ("seq", "bytes", "chars")}}
    try:
        session.add(SecurityLog(user_id=int(user_id), action=action, target_type="cs_agent_turn", target_id=int(turn_id),
                                message=f"{action} turn={int(turn_id)} code={result.code}", detail=detail))
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 고친 까닭] 감사 원장을 못 남겼다 action=%s turn=%s", action, turn_id)
    return result


def _writer_gate(session: Any, turn_id: int, user: Any, now: datetime.datetime) -> Union[Any, DetailResult]:
    """쓰기 앞 확인 — 차례 · 끝난 꼴 '고침' · 보낸 직원(24시간) · ADMIN. 통과면 줄, 아니면 결과."""
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    if row is None:
        return _fail("not_found", 404)
    if row.outcome != OUTCOME_EDITED:
        return _fail("not_edited", 409)
    if _is_admin(user):
        return row
    if row.sent_by_user_id is None or int(row.sent_by_user_id) != int(user.id):
        return _fail("not_yours", 403)
    sent = row.sent_at or row.send_started_at or row.updated_at
    if sent is None or naive_utc(now) - sent > WINDOW:
        return _fail("too_late", 403)
    return row


def photo_rows(session: Any, turn_id: int) -> list[dict[str, Any]]:
    """살아 있는 사진 줄 — 차례 번호 · 확인 칸 · 크기 · 설명 상태만(key · URL 없음)."""
    stmt = (select(CsAgentTurnPhoto).where(CsAgentTurnPhoto.turn_id == int(turn_id),
                                           CsAgentTurnPhoto.purged_at.is_(None))
            .order_by(CsAgentTurnPhoto.seq))
    return [{"seq": p.seq, "no_personal": bool(p.no_personal), "bytes": int(p.bytes), "width": int(p.width),
             "height": int(p.height), "desc_state": p.desc_state} for p in session.scalars(stmt)]


# ── 자세한 이유 ──────────────────────────────────────────────────────────
def detail_text(detail: Any) -> Union[Optional[str], DetailResult]:
    """받은 글 → 가린 글(빈 글은 ``None`` — 지움) 또는 실패 결과. 개인정보 꼴이 있으면 저장하지 않는다. 채널톡 작은 창
    [수정하기]의 '왜 고쳤나요' 칸(:mod:`.send_flow` — 보내기와 함께 받는다)도 같은 규칙이다."""
    if not isinstance(detail, str) or len(detail) > MAX_DETAIL:
        return _fail("bad_request", 400, field="detail")
    if not detail.strip():
        return None
    if any(leak_counts(detail).values()):
        return _fail("detail_private", 400, field="detail_private")
    try:
        return masked_or_none(detail.strip())
    except MaskLeak:
        return _fail("detail_private", 400, field="detail_private")


def save_detail(session: Any, *, turn_id: int, user: Any, detail: Any, now: datetime.datetime) -> DetailResult:
    """자세한 이유 저장(덮어씀) + 감사 원장. 커밋한다."""
    result = _save_detail(session, turn_id=turn_id, user=user, detail=detail, now=now)
    return _audit(session, "CS_AGENT_EDIT_DETAIL", turn_id, user.id, result)


def _save_detail(session: Any, *, turn_id: int, user: Any, detail: Any, now: datetime.datetime) -> DetailResult:
    if not switches(session, with_photos=False).detail:
        session.rollback()
        return _fail("detail_off", 409)
    row = _writer_gate(session, turn_id, user, now)
    if isinstance(row, DetailResult):
        session.rollback()
        return row
    masked = detail_text(detail)
    if isinstance(masked, DetailResult):
        session.rollback()
        return masked
    turns = CsAgentTurn.__table__
    at = naive_utc(now)
    done = session.execute(update(turns).where(turns.c.id == row.id, turns.c.outcome == OUTCOME_EDITED).values(
        edit_detail_masked=masked, edit_detail_by=int(user.id) if masked else None, edit_detail_at=at if masked else None,
        updated_at=at)).rowcount == 1
    session.commit()
    logger.info("[CS 고친 까닭] 자세한 이유 turn=%s chars=%d done=%s", row.id, len(masked or ""), done)
    if not done:
        return _fail("not_edited", 409)
    return _fail("saved" if masked else "cleared", 200, chars=len(masked or ""))


# ── 사진 ─────────────────────────────────────────────────────────────────
def _next_seq(session: Any, turn_id: int, sha256: str) -> Union[int, DetailResult]:
    """새 차례 번호 — 살아 있는 사진 상한 · 같은 사진 · 번호 상한을 본다."""
    rows = session.execute(select(CsAgentTurnPhoto.seq, CsAgentTurnPhoto.sha256, CsAgentTurnPhoto.purged_at)
                           .where(CsAgentTurnPhoto.turn_id == int(turn_id))).all()
    alive = [r for r in rows if r.purged_at is None]
    if any(r.sha256 == sha256 for r in alive):
        return _fail("photo_same", 409)
    top = max((r.seq for r in rows), default=0)
    if len(alive) >= MAX_PHOTOS or top >= SEQ_MAX:
        return _fail("photo_full", 409)
    return top + 1


def add_photo(session: Any, *, turn_id: int, user: Any, data: bytes, no_personal: bool, now: datetime.datetime,
              storage: Any = None) -> DetailResult:
    """사진 한 장 저장(다시 그림 → 저장소 → 줄) + 감사 원장. 커밋한다."""
    store = storage if storage is not None else get_storage()
    result = _add_photo(session, turn_id=turn_id, user=user, data=data, no_personal=no_personal, now=now, store=store)
    return _audit(session, "CS_AGENT_PHOTO_ADD", turn_id, user.id, result)


def _add_photo(session: Any, *, turn_id: int, user: Any, data: bytes, no_personal: bool, now: datetime.datetime,
               store: Any) -> DetailResult:
    if not switches(session, store).photos:
        session.rollback()
        return _fail("photo_off", 409)
    row = _writer_gate(session, turn_id, user, now)
    if isinstance(row, DetailResult):
        session.rollback()
        return row
    try:
        photo = redraw(data)
    except PhotoError as exc:
        session.rollback()
        return _fail(exc.code, 400, field="photo")
    seq = _next_seq(session, row.id, photo.sha256)
    if isinstance(seq, DetailResult):
        session.rollback()
        return seq
    session.commit()  # 저장소를 부르는 동안 읽기 트랜잭션을 열어 두지 않는다
    key = f"{photo_key(row.id)}.{photo.ext}"
    if not store.put_private_bytes(key, photo.data, photo.content_type):
        logger.warning("[CS 고친 까닭] 사진을 저장소에 못 올렸다 turn=%s seq=%s", row.id, seq)
        return _fail("store_failed", 502)
    return _insert_photo(session, row.id, seq, key, photo, user=user, no_personal=no_personal, now=now, store=store)


def _insert_photo(session: Any, turn_id: int, seq: int, key: str, photo: Any, *, user: Any, no_personal: bool,
                  now: datetime.datetime, store: Any) -> DetailResult:
    """사진 줄 넣기 — 못 넣으면(같은 때 같은 번호) 올린 파일을 지운다."""
    session.add(CsAgentTurnPhoto(turn_id=turn_id, seq=seq, storage_key=key, content_type=photo.content_type,
                                 bytes=len(photo.data), width=photo.width, height=photo.height, sha256=photo.sha256,
                                 no_personal=bool(no_personal), desc_state="pending" if no_personal else "skipped",
                                 uploaded_by=int(user.id), created_at=naive_utc(now)))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        store.delete_file(key)
        logger.warning("[CS 고친 까닭] 같은 번호가 먼저 들어가 올린 사진을 지웠다 turn=%s seq=%s", turn_id, seq)
        return _fail("busy", 409)
    logger.info("[CS 고친 까닭] 사진 turn=%s seq=%s bytes=%d", turn_id, seq, len(photo.data))
    return _fail("photo_saved", 200, seq=seq, bytes=len(photo.data), photos=photo_rows(session, turn_id))


def delete_photo(session: Any, *, turn_id: int, seq: int, user: Any, now: datetime.datetime,
                 storage: Any = None) -> DetailResult:
    """사진 지우기 — 저장소에서 바로 지우고(유예 없음) 줄은 ``purged_at``. 감사 원장. 커밋한다."""
    store = storage if storage is not None else get_storage()
    result = _delete_photo(session, turn_id=turn_id, seq=seq, user=user, now=now, store=store)
    return _audit(session, "CS_AGENT_PHOTO_DELETE", turn_id, user.id, result)


def _delete_photo(session: Any, *, turn_id: int, seq: int, user: Any, now: datetime.datetime,
                  store: Any) -> DetailResult:
    row = _writer_gate(session, turn_id, user, now)
    if isinstance(row, DetailResult):
        session.rollback()
        return row
    photo = session.scalar(select(CsAgentTurnPhoto).where(CsAgentTurnPhoto.turn_id == row.id,
                                                          CsAgentTurnPhoto.seq == int(seq),
                                                          CsAgentTurnPhoto.purged_at.is_(None)))
    if photo is None:
        session.rollback()
        return _fail("not_found", 404)
    key = photo.storage_key
    session.commit()
    if key and store.delete_file(key) is False:
        logger.warning("[CS 고친 까닭] 저장소에서 사진을 못 지웠다 turn=%s seq=%s", row.id, seq)
        return _fail("delete_failed", 502)
    photos = CsAgentTurnPhoto.__table__
    session.execute(update(photos).where(photos.c.id == photo.id).values(storage_key=None, purged_at=naive_utc(now)))
    session.commit()
    logger.info("[CS 고친 까닭] 사진 지움 turn=%s seq=%s", row.id, seq)
    return _fail("photo_deleted", 200, seq=int(seq), photos=photo_rows(session, row.id))


def photo_for_view(session: Any, *, turn_id: int, seq: int, user: Any, now: datetime.datetime,
                   storage: Any = None) -> Union[tuple[bytes, str], DetailResult]:
    """원본 보기 — ADMIN · 올린 직원(24시간)만. ``(바이트, Content-Type)`` 또는 결과(403 · 404). DB 는 읽기만 한다."""
    photo = session.scalar(select(CsAgentTurnPhoto).where(CsAgentTurnPhoto.turn_id == int(turn_id),
                                                          CsAgentTurnPhoto.seq == int(seq)))
    session.rollback()
    if photo is None or photo.purged_at is not None or not photo.storage_key:
        return _fail("not_found", 404)
    if not _is_admin(user):
        if int(photo.uploaded_by) != int(user.id):
            return _fail("not_yours", 403)
        if naive_utc(now) - photo.created_at > WINDOW:
            return _fail("too_late", 403)
    data = (storage if storage is not None else get_storage()).read_file_bytes(photo.storage_key)
    if not data:
        return _fail("not_found", 404)
    return data, photo.content_type

