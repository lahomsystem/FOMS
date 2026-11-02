"""FOMS 공지 폰 알림 — 알림 종류 · 잠금화면 글 · 누르면 열 주소(설계서 2026-11-02-foms-notices §7).

공지 한 건을 받는 사람마다 ``Notification``(종류 :data:`FOMS_NOTICE_TYPE`, ``target_user_id`` = 그 사람) 한 줄로 만든다
(:mod:`foms.services.notices.push`). 잠금화면에는 제목 "📢 공지사항" 과 **공지 제목만** 싣는다 — 본문은 싣지 않는다
(사용자 결정 2026-11-02). 누르면 본사 직원은 ``/notices``, 협력사 직원은 ``/partner/notices`` 를 연다(``/erp`` 는 협력사에게
막혀 있다). 이 모듈은 다른 서비스를 import 하지 않는다 — 발송기(:mod:`.push_sender`)와 공지 서비스가 같이 쓴다.
"""
from __future__ import annotations

FOMS_NOTICE_TYPE = "FOMS_NOTICE"
NOTICE_PUSH_TITLE = "📢 공지사항"
#: 잠금화면 본문(공지 제목) 최대 글자 수 — 넘으면 잘라 "…" 를 붙인다.
NOTICE_PUSH_BODY_MAX = 120
STAFF_NOTICE_LINK = "/notices"
PARTNER_NOTICE_LINK = "/partner/notices"


def is_notice_notification_type(ntype: str) -> bool:
    return (ntype or "").strip().upper() == FOMS_NOTICE_TYPE


def notice_push_text(title: str | None) -> tuple[str, str]:
    """푸시 (제목, 본문) — 본문은 공지 제목(공백을 접고 120자에서 자른다). 비면 일반 문구."""
    text = " ".join(str(title or "").split())
    if len(text) > NOTICE_PUSH_BODY_MAX:
        text = text[: NOTICE_PUSH_BODY_MAX - 1] + "…"
    return NOTICE_PUSH_TITLE, text or "새 공지가 있어요"


def notice_deep_link(partner_recipient: bool) -> str:
    """누르면 열 주소 — 협력사 직원은 협력사 공지 목록, 본사 직원은 공지 목록."""
    return PARTNER_NOTICE_LINK if partner_recipient else STAFF_NOTICE_LINK
