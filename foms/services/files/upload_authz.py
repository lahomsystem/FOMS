"""UPLOAD-01: order-upload 권한 + 서버 object key 경로 SSOT.

direct(presigned)·multipart 두 업로드 경로가 **공유**하는 방어 3종을 한곳에 고정한다.
route 별로 흩어진 임시 substring 검사(``".." in folder`` / ``f"orders/{id}/" not in key``)를
대체한다.

1. **VIEWER 403 + 용도(purpose)별 role/team** — AUTH-01(:mod:`order_mutation_policy`)
   ``evaluate_policy`` 재사용. 신규 policy_id 없이 category → 기존 정책 후보로 매핑한다.
2. **arbitrary folder 0** — R2 object key 는 항상 ``orders/{order_id}/{whitelist}[/...]`` 형태만
   허용한다. 사용자 입력 folder/key 는 :func:`posixpath.normpath` 로 **완전 정규화**한 뒤
   정규형과 원본이 다르면(=traversal·비정규 경로) 거부하고, 첫 segment 는 화이트리스트로만
   통과시킨다. **substring/prefix match 로 안전 결론짓지 않는다.**
3. **대상 order 일치** — complete 시 key 의 order segment 는 route 의 ``order_id`` 와 정확히
   일치해야 한다(``foo/orders/5/...`` 같은 substring 우회 차단).

경계(UPLOAD-01): 업로드 비즈니스(썸네일·R2 저장) 로직은 건드리지 않는다. 이 모듈은
권한 판정과 key 경로 검증만 제공한다. 신규 policy_id/route 는 만들지 않는다(필요 시 report).
"""
from __future__ import annotations

import posixpath
import re
from typing import Any, Optional

from foms.services.orders.order_mutation_policy import user_can

__all__ = [
    "ALLOWED_UPLOAD_SUBFOLDERS",
    "category_upload_allowed",
    "parse_upload_folder",
    "validate_upload_key",
]

#: ``orders/{order_id}/`` 바로 뒤에 올 수 있는 첫 subfolder segment 화이트리스트.
#: 프론트 실사용 folder(attachments/measurement/drawing/drawing_gateway/blueprint/
#: construction/as) 를 근거로 확정한다. 그 외 값은 arbitrary folder 로 거부한다.
ALLOWED_UPLOAD_SUBFOLDERS = frozenset({
    "attachments",
    "measurement",
    "drawing",
    "drawing_gateway",
    "blueprint",
    "construction",
    "as",
})

#: 깊은 segment(예: drawing_gateway/**revisions**, 서버 생성 파일명)에 허용되는 문자.
#: ``..`` 는 normpath 단계에서 이미 걸러지지만, 제어문자·구분자 유입을 2차로 막는다.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")

#: 용도(category) → 통과 정책 후보(**하나라도** 통과하면 허용). AUTH-01 기존 policy_id 만
#: 재사용한다(신규 policy_id 0). VIEWER hard-deny·ADMIN/MANAGER override 는 각 정책이 처리한다.
#:   - drawing(도면): DRAWING team ∪ CS/SALES(gateway 는 ERP_EDIT 로 CS/SALES 가 실사용).
#:   - construction/as(시공·AS): CS/SALES/CONSTRUCTION.
#:   - measurement/general(실측·일반): 전 STAFF(현행 유지, 비파괴).
_CATEGORY_POLICIES: dict[str, tuple[str, ...]] = {
    "drawing": ("DRAWING_TEAM", "ERP_EDIT"),
    "construction": ("CONSTRUCTION_EDIT",),
    "as": ("CONSTRUCTION_EDIT",),
    "measurement": ("STAFF_MUTATION",),
}
_DEFAULT_CATEGORY_POLICIES: tuple[str, ...] = ("STAFF_MUTATION",)


def category_upload_allowed(user: Any, category: Optional[str]) -> bool:
    """사용자가 해당 용도(category)로 order 업로드를 할 수 있는지(VIEWER 403 포함).

    AUTH-01 ``evaluate_policy`` 를 category 별 정책 후보에 적용한다. ``None``(미인증)·VIEWER 는
    어떤 category 에서도 통과하지 못한다(정책이 처리). 후보 중 하나라도 통과하면 허용.

    Args:
        user: 현재 사용자(``role``/``team`` 를 읽음). ``None`` 이면 거부.
        category: 정규화된 첨부 category(measurement/drawing/construction/as 등).

    Returns:
        업로드 허용이면 True.
    """
    policies = _CATEGORY_POLICIES.get((category or "").strip().lower(), _DEFAULT_CATEGORY_POLICIES)
    return any(user_can(policy_id, user) for policy_id in policies)


def _category_for_folder(folder: str) -> str:
    """정규화된 ``orders/{id}/{sub}`` folder → 첨부 category(runtime import 로 layering 유지)."""
    from foms.api.files.common import resolve_attachment_category

    return resolve_attachment_category(folder, None)


def parse_upload_folder(
    folder: Any,
) -> tuple[bool, Optional[int], Optional[str], Optional[str], Optional[str]]:
    """사용자 입력 folder 를 검증·정규화한다(presigned 세션 발급 경로).

    ``orders/{order_id}/{whitelisted}[/{safe_segment}...]`` 형태만 통과한다. 완전 정규화 후
    정규형이 원본과 다르면(traversal·중복 슬래시·비정규) 거부한다.

    Args:
        folder: 클라이언트가 준 folder 문자열.

    Returns:
        ``(ok, order_id, normalized_folder, category, error)``. 실패 시 ``ok=False`` 와
        한글 error 메시지, 나머지는 ``None``.
    """
    if not isinstance(folder, str) or not folder.strip():
        return False, None, None, None, "folder가 필요합니다."
    raw = folder.strip()
    if raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return False, None, None, None, "유효하지 않은 folder 경로입니다."

    # 완전 정규화: '..'·'.'·중복 슬래시가 있으면 정규형이 원본과 달라져 거부된다(substring 검사 아님).
    norm = posixpath.normpath(raw)
    if norm != raw or norm.startswith("..") or norm.startswith("/"):
        return False, None, None, None, "유효하지 않은 folder 경로입니다."

    parts = norm.split("/")
    if len(parts) < 3 or parts[0] != "orders" or not parts[1].isdigit():
        return False, None, None, None, "유효하지 않은 folder 경로입니다."
    if parts[2] not in ALLOWED_UPLOAD_SUBFOLDERS:
        return False, None, None, None, "허용되지 않은 업로드 폴더입니다."
    if not all(_SAFE_SEGMENT.match(seg) for seg in parts[2:]):
        return False, None, None, None, "유효하지 않은 folder 경로입니다."

    order_id = int(parts[1])
    return True, order_id, norm, _category_for_folder(norm), None


def validate_upload_key(key: Any, order_id: int) -> tuple[bool, Optional[str], Optional[str]]:
    """direct 업로드 complete 시 사용자 key 가 대상 order 정본 경로인지 검증한다.

    ``orders/{order_id}/{whitelisted}/{safe_segment}...`` 형태만 통과한다. key 의 order segment
    는 route 의 ``order_id`` 와 **정확히 일치**해야 한다(``foo/orders/5/...`` substring 우회 차단).

    Args:
        key: 클라이언트가 등록 요청한 object key.
        order_id: route 의 대상 order_id.

    Returns:
        ``(ok, category, error)``. 실패 시 ``ok=False`` 와 한글 error, ``category=None``.
    """
    if not isinstance(key, str) or not key.strip():
        return False, None, "key가 필요합니다."
    raw = key.strip()
    if raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return False, None, "유효하지 않은 key 경로입니다."

    norm = posixpath.normpath(raw)
    if norm != raw or norm.startswith("..") or norm.startswith("/"):
        return False, None, "유효하지 않은 key 경로입니다."

    parts = norm.split("/")
    # orders/{id}/{sub}/{file...} → 최소 4 segment. parts[0] 은 리터럴 'orders' 여야 한다.
    if len(parts) < 4 or parts[0] != "orders":
        return False, None, "유효하지 않은 key 경로입니다."
    if parts[1] != str(order_id):
        return False, None, "대상 order와 일치하지 않는 key입니다."
    if parts[2] not in ALLOWED_UPLOAD_SUBFOLDERS:
        return False, None, "허용되지 않은 업로드 폴더입니다."
    if not all(_SAFE_SEGMENT.match(seg) for seg in parts[2:]):
        return False, None, "유효하지 않은 key 경로입니다."

    folder = posixpath.dirname(norm)
    return True, _category_for_folder(folder), None
