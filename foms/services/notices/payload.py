"""관리자 공지 입력 검증 — 설계서 2026-11-02-foms-notices §3 · §4 페이로드.

페이로드: ``title`` · ``body`` · ``audience: {staff_all, staff_teams[], partner_all, partner_org_ids[]}`` ·
``display_mode`` (``POPUP`` | ``LIST``) · ``pinned`` · ``starts_at`` · ``ends_at`` (``YYYY-MM-DDTHH:MM`` 한국 시간 또는 빈 값) ·
``images`` (``[{key, thumb_key, name, width, height, size}]`` — 보이는 순서, 최대 5장, 설계서 §8. 칸이 없으면 고치기에서 그대로 둔다).
틀리면 :class:`NoticeInputError`(화면에 그대로 보여 줄 쉬운 한글 한 줄). 시간은 UTC naive 로 바꿔 돌려준다.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from foms.services.datetime_kst import format_datetime_kst, to_utc_naive
from foms.services.notices.audience import NOTICE_TEAM_CODES
from foms.services.notices.images import KEY_RE, MAX_IMAGES, clean_name, thumb_key_for
from foms.services.orders.order_mutation_policy import normalize_team
from models import PartnerOrg

__all__ = [
    "DISPLAY_MODES", "NoticeInputError", "TITLE_MAX", "BODY_MAX", "clean_images", "format_input_kst", "parse_notice_payload",
]

DISPLAY_MODES: tuple[str, ...] = ("POPUP", "LIST")
TITLE_MAX = 200
BODY_MAX = 20000
_INPUT_FMT = "%Y-%m-%dT%H:%M"


class NoticeInputError(ValueError):
    """공지 입력이 틀렸다 — ``str(err)`` 가 화면 문구."""


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return bool(value)


def _kst_input(value: Any, label: str) -> Optional[datetime.datetime]:
    """``YYYY-MM-DDTHH:MM``(한국 시간) → UTC naive. 빈 값은 None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        datetime.datetime.fromisoformat(text)
    except ValueError:
        raise NoticeInputError(f"{label} 시간 모양이 맞지 않습니다.") from None
    result = to_utc_naive(text, assume_utc_if_naive=False)
    if result is None:
        raise NoticeInputError(f"{label} 시간 모양이 맞지 않습니다.")
    return result


def format_input_kst(value: Optional[datetime.datetime]) -> str:
    """UTC naive → 입력 칸 모양(``YYYY-MM-DDTHH:MM`` 한국 시간). 비면 빈 글."""
    if value is None:
        return ""
    return format_datetime_kst(value, _INPUT_FMT) or ""


def _teams(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise NoticeInputError("받는 팀 목록이 맞지 않습니다.")
    out: list[str] = []
    for item in raw:
        code = normalize_team(str(item) if item is not None else "")
        if code not in NOTICE_TEAM_CODES:
            raise NoticeInputError("없는 팀이 들어 있습니다.")
        if code not in out:
            out.append(code)
    return out


def _org_ids(db, raw: Any) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise NoticeInputError("받는 협력사 목록이 맞지 않습니다.")
    out: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            raise NoticeInputError("받는 협력사 목록이 맞지 않습니다.")
        try:
            value = int(item)
        except (TypeError, ValueError):
            raise NoticeInputError("받는 협력사 목록이 맞지 않습니다.") from None
        if value not in out:
            out.append(value)
    if out:
        found = {int(row[0]) for row in db.query(PartnerOrg.id).filter(PartnerOrg.id.in_(out)).all()}
        if set(out) - found:
            raise NoticeInputError("없는 협력사가 들어 있습니다.")
    return out


def _count(value: Any) -> int:
    """폭 · 높이 · 크기 숫자(틀리면 0 — 보여 주기용이라 막지 않는다)."""
    if isinstance(value, bool):
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def clean_images(raw: Any) -> list[dict[str, Any]]:
    """사진 목록 검증 — 업로드 API 가 만든 key(``notices/images/...``)만, 최대 5장, 같은 사진 두 번 금지.

    썸네일 key 는 보낸 값을 믿지 않고 본 key 에서 다시 만든다(남의 파일 key 끼워 넣기 금지).
    """
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise NoticeInputError("사진 목록이 맞지 않습니다.")
    if len(raw) > MAX_IMAGES:
        raise NoticeInputError(f"사진은 {MAX_IMAGES}장까지 올릴 수 있어요.")
    out: list[dict[str, Any]] = []
    for item in raw:
        key = str(item.get("key") or "") if isinstance(item, dict) else ""
        if not KEY_RE.fullmatch(key):
            raise NoticeInputError("올리지 않은 사진이 들어 있습니다. 사진을 다시 올려 주세요.")
        thumb = thumb_key_for(key)
        if item.get("thumb_key") not in (None, "", thumb):
            raise NoticeInputError("올리지 않은 사진이 들어 있습니다. 사진을 다시 올려 주세요.")
        if any(o["key"] == key for o in out):
            raise NoticeInputError("같은 사진이 두 번 들어 있습니다.")
        out.append({"key": key, "thumb_key": thumb, "name": clean_name(item.get("name")),
                    "width": _count(item.get("width")), "height": _count(item.get("height")),
                    "size": _count(item.get("size"))})
    return out


def parse_notice_payload(db, payload: Any) -> dict[str, Any]:
    """페이로드를 검증해 ``Notice`` 칸 값 dict 로 바꾼다.

    Raises:
        NoticeInputError: 제목 없음 · 너무 김 · 받는 쪽 없음 · 보이는 방식 틀림 · 끝이 시작보다 앞섬 등.
    """
    if not isinstance(payload, dict):
        raise NoticeInputError("보낸 내용이 맞지 않습니다.")
    title = str(payload.get("title") or "").strip()
    if not title:
        raise NoticeInputError("제목을 적어 주세요.")
    if len(title) > TITLE_MAX:
        raise NoticeInputError(f"제목은 {TITLE_MAX}자까지 쓸 수 있습니다.")
    body = str(payload.get("body") or "").strip()
    if len(body) > BODY_MAX:
        raise NoticeInputError(f"내용은 {BODY_MAX}자까지 쓸 수 있습니다.")

    audience = payload.get("audience")
    if audience is None:
        audience = {}
    if not isinstance(audience, dict):
        raise NoticeInputError("받는 사람 고르기가 맞지 않습니다.")
    staff_all = _flag(audience.get("staff_all"))
    partner_all = _flag(audience.get("partner_all"))
    staff_teams = [] if staff_all else _teams(audience.get("staff_teams"))
    partner_org_ids = [] if partner_all else _org_ids(db, audience.get("partner_org_ids"))
    if not (staff_all or staff_teams or partner_all or partner_org_ids):
        raise NoticeInputError("받는 사람을 하나 이상 골라 주세요.")

    display_mode = str(payload.get("display_mode") or "").strip().upper()
    if display_mode not in DISPLAY_MODES:
        raise NoticeInputError("보이는 방식을 골라 주세요(확인 창 · 목록만).")

    starts_at = _kst_input(payload.get("starts_at"), "게시 시작")
    ends_at = _kst_input(payload.get("ends_at"), "게시 끝")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise NoticeInputError("게시 끝은 시작보다 뒤여야 합니다.")

    values = {
        "title": title,
        "body": body,
        "audience_staff_all": staff_all,
        "audience_staff_teams": staff_teams,
        "audience_partner_all": partner_all,
        "audience_partner_org_ids": partner_org_ids,
        "display_mode": display_mode,
        "pinned": _flag(payload.get("pinned")),
        "starts_at": starts_at,
        "ends_at": ends_at,
    }
    if "images" in payload:
        values["images"] = clean_images(payload.get("images"))
    return values
