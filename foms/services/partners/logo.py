"""PARTNER-03: 협력사 로고 — 관리자가 협력사마다 올리고, 협력사 주문의 도면에 들어간다.

협력사 주문 도면에는 라홈 · 하우드 로고를 쓰지 않는다. 로고가 있으면 협력사 로고(``'partner'``),
없으면 로고 칸을 비운다(``'none'``). 도면 PNG 는 브라우저 html2canvas 로 만들어지므로 로고는
반드시 같은 출처(앱 경유)로 내려야 한다 — R2 서명 URL 은 다른 출처라 캔버스에서 빠진다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §13
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import object_session

from foms.services.auth.partner_scope import is_partner_order
from models import PartnerOrg

LOGO_MIMETYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024

# 도면 마법사 defaults.logo 값(기존 'lahom'/'haud' 옆에 둘을 더한다).
LOGO_PARTNER = "partner"
LOGO_NONE = "none"


class PartnerLogoError(ValueError):
    """관리 화면에 그대로 보여 줄 수 있는 로고 입력 오류."""


def save_partner_logo(storage: Any, org: PartnerOrg, file: Any) -> str:
    """로고 파일을 검사해 올리고 ``org.logo_storage_key`` 를 바꾼다(호출자가 commit)."""
    filename = (getattr(file, "filename", None) or "").strip()
    ext = os.path.splitext(filename)[1].lower()
    if ext not in LOGO_MIMETYPES:
        raise PartnerLogoError("로고는 png · jpg · webp 이미지만 올릴 수 있습니다.")
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size <= 0 or size > MAX_LOGO_BYTES:
        raise PartnerLogoError("로고 파일은 2MB 이하여야 합니다.")
    result = storage.upload_file(file, filename, f"partners/{org.id}/logo")
    if not result.get("success") or not result.get("key"):
        raise PartnerLogoError("로고를 올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.")
    org.logo_storage_key = result["key"]
    return org.logo_storage_key


def read_partner_logo(storage: Any, org: PartnerOrg | None) -> tuple[bytes, str] | None:
    """로고 바이트와 MIME — 없으면 None. key 는 DB 값만 쓴다(요청 값을 받지 않는다)."""
    key = getattr(org, "logo_storage_key", None) if org is not None else None
    if not key:
        return None
    data = storage.read_file_bytes(key)
    if data is None:
        return None
    return data, LOGO_MIMETYPES.get(os.path.splitext(key)[1].lower(), "application/octet-stream")


def partner_org_of(db, order: Any) -> PartnerOrg | None:
    org_id = getattr(order, "partner_org_id", None)
    if org_id is None:
        return None
    return db.query(PartnerOrg).filter(PartnerOrg.id == org_id).first()


def partner_logo_mode(order: Any) -> str | None:
    """협력사 주문이면 ``'partner'``(로고 있음) / ``'none'``, 아니면 None(기존 라홈·하우드 규칙).

    협력사 주문일 때만 그 주문의 세션으로 협력사 행 하나를 읽는다(우리 주문은 쿼리 0).
    """
    if not is_partner_order(order):
        return None
    db = object_session(order)
    org = partner_org_of(db, order) if db is not None else None
    return LOGO_PARTNER if getattr(org, "logo_storage_key", None) else LOGO_NONE
