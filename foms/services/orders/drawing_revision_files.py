"""도면 수정요청 참고 파일 검증 — 저장·표시가 같은 한 함수로 답한다(원장 M5, 2b).

수정요청 API 는 예전에 클라이언트가 보낸 ``files`` 를 그대로 저장했다. key·filename·
view_url·download_url 모두 검증이 없어 남의 주문 key 나 ``javascript:`` URL 이 이력에
들어갔다. 이 모듈이 판정의 정본이다:

* :func:`is_revision_reference_key` — 이 주문 ``drawing_gateway/`` 정본 경로 key 인가.
  수정요청 저장(``request-revision``)·창구 업로드 완료(``drawing-gateway/complete``)·
  화면 표시(PC 작업실·모바일 도면 방)가 모두 이 함수를 부른다.
* :func:`normalize_revision_files` — 저장할 항목을 서버가 다시 만든다(URL 은 key 로만).
* :func:`revision_reference_display_rows` — 옛 이력 표시용(열 수 있는 행 + 개수만 셀 수).
"""
from __future__ import annotations

import posixpath
from collections.abc import Mapping
from typing import Any

from foms.services.files.upload_authz import validate_upload_key

__all__ = [
    "MAX_REVISION_FILES",
    "is_revision_reference_key",
    "normalize_revision_files",
    "revision_reference_display_rows",
]

#: 한 수정요청에 실을 수 있는 참고 파일 수 상한(화면 업로드 상한과 맞출 값은 확인 필요 — SPEC §10.5).
MAX_REVISION_FILES = 20

_IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".heif",
)
_VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".m4v", ".avi")


def is_revision_reference_key(order_id: Any, key: Any) -> bool:
    """key 가 이 주문 도면 창구(``orders/<id>/drawing_gateway/``) 정본 경로인지.

    앞뒤 공백이 없고, 접두가 정확히 맞고, :func:`validate_upload_key` (정규화·안전 문자·
    주문 일치·폴더 화이트리스트)를 통과해야 한다. 부분 문자열 검사로 결론짓지 않는다.

    Args:
        order_id: 대상 주문 id. 비어 있으면 늘 False.
        key: 검사할 storage key.

    Returns:
        정본 경로면 True.
    """
    if not order_id or not isinstance(key, str) or not key or key != key.strip():
        return False
    if not key.startswith(f"orders/{order_id}/drawing_gateway/"):
        return False
    return bool(validate_upload_key(key, order_id)[0])


def _file_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(_IMAGE_EXTENSIONS):
        return "image"
    if lower.endswith(_VIDEO_EXTENSIONS):
        return "video"
    return "file"


def _view_url(key: str) -> str:
    # api 레이어(foms.api.files.build_file_view_url)를 부르지 않고 같은 모양을 직접 만든다 —
    # services → api import 금지(레이어 의존 래칫). drawing_confirm_cleanup 과 같은 규칙.
    return f"/api/files/view/{key}"


def _download_url(key: str) -> str:
    return f"/api/files/download/{key}"


def normalize_revision_files(order_id: Any, files: Any) -> tuple[list[dict], list[str]]:
    """수정요청 ``files`` 를 저장 모양으로 다시 만든다. 하나라도 이상하면 이유를 돌려준다.

    통과 항목은 ``{key, filename, file_type, view_url, download_url}`` 로 서버가 만든다 —
    보낸 URL·file_type 은 버린다. filename 은 앞뒤 공백을 빼고 255자로 자르며 없으면 key 끝.

    Args:
        order_id: 대상 주문 id.
        files: 요청 본문의 ``files`` 값(호출자가 list 인지 먼저 본다).

    Returns:
        ``(정규화된 항목 목록, 거절 이유 목록)``. 거절이 하나라도 있으면 호출자는 400 을 낸다.
    """
    rows: list[dict] = []
    rejects: list[str] = []
    if not isinstance(files, list):
        return rows, ["files 가 목록이 아닙니다."]
    if len(files) > MAX_REVISION_FILES:
        rejects.append(f"참고 파일은 {MAX_REVISION_FILES}개까지입니다.")
    for idx, file_obj in enumerate(files):
        key = file_obj.get("key") if isinstance(file_obj, Mapping) else None
        if not is_revision_reference_key(order_id, key):
            rejects.append(f"{idx + 1}번째 파일 경로가 이 주문 도면 창구 경로가 아닙니다.")
            continue
        raw_name = file_obj.get("filename")
        filename = (raw_name.strip() if isinstance(raw_name, str) else "")[:255]
        filename = filename or posixpath.basename(key)
        rows.append({
            "key": key,
            "filename": filename,
            "file_type": _file_type(filename or key),
            "view_url": _view_url(key),
            "download_url": _download_url(key),
        })
    return rows, rejects


def revision_reference_display_rows(order_id: Any, files: Any) -> tuple[list[dict[str, Any]], int]:
    """이력의 수정요청 참고 파일을 화면 행으로 만든다(저장된 URL 은 쓰지 않는다).

    옛 이력에는 검증 없이 저장된 key·URL 이 남아 있다. :func:`is_revision_reference_key` 를
    통과한 key 만 서버가 만든 URL 로 링크하고, 나머지는 개수만 센다.

    Args:
        order_id: 화면의 주문 id. ``None`` 이면 어떤 파일도 링크하지 않는다.
        files: REQUEST_REVISION 이력의 ``files`` 값.

    Returns:
        ``(열 수 있는 행 목록, 열 수 없어 개수만 세는 파일 수)``.
        행은 ``{key, filename, view_url, download_url, is_image}``.
    """
    if not isinstance(files, list):
        return [], 0
    rows: list[dict[str, Any]] = []
    hidden = 0
    for file_obj in files:
        key = file_obj.get("key") if isinstance(file_obj, Mapping) else None
        if not is_revision_reference_key(order_id, key):
            hidden += 1
            continue
        filename = str(file_obj.get("filename") or "").strip() or key.rsplit("/", 1)[-1]
        rows.append({
            "key": key,
            "filename": filename,
            "view_url": _view_url(key),
            "download_url": _download_url(key),
            "is_image": key.lower().endswith(_IMAGE_EXTENSIONS),
        })
    return rows, hidden
