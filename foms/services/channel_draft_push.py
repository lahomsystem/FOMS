"""마법사 초안(Order 행 없음)의 실측방 채널톡 PUSH 전송 계층 (WIZ-SEND-01 T3).

PC 경로(``foms/api/channel/channel_integration.py::api_channel_push_manual``)는 저장된
``Order`` + ``OrderAttachment`` 를 전제로 한다. 마법사 4단계에서는 아직 주문 행이 없고
첨부도 ``payload.items[].attachments[].tmp_key`` 로 스토리지에만 올라가 있으므로, 같은
규약(설정 확인 → 그룹 결정 → 서명 URL → 최대 20장 → 실측방 전송)을 초안 자료로 수행하는
얇은 계층을 따로 둔다.

PC 와 다른 점은 **주문 상세 링크가 붙지 않는 것 하나뿐**이다(설계 D5 — 가리킬 주문이
없다). ``dispatch_order_event`` 는 ``channel_policy.build_message_template`` /
``build_message_blocks`` 를 거치는데 둘 다 링크 문단을 무조건 덧붙이므로, 초안 경로는
``channel_policy`` 를 고치는 대신 ``send_group_message`` 를 직접 호출한다(주문 경로의
링크는 그대로 유지된다).
"""

from __future__ import annotations

import logging
from typing import Any

from foms.services.channel_client import (
    build_channel_bot_name,
    is_configured,
    send_group_message,
)
from foms.services.channel_measure_message import build_measure_push_text
from foms.services.channel_policy import (
    MAX_MANUAL_ATTACHMENTS,
    ChannelGroupRetiredError,
    get_routing_group_id,
    # 줄바꿈 규약(빈 줄 = nbsp 블록)의 SSOT. 채널톡은 블록 value 를 HTML 로 읽어 raw
    # 개행을 접으므로 "한 줄 = 한 블록"이 아니면 본문이 뭉개진다. 여기서 다시 구현하면
    # 주문 경로와 초안 경로의 줄바꿈이 조용히 갈린다 — kakao API 가 _ineligible_reason 을
    # 그대로 쓰는 것과 같은 이유로 비공개 헬퍼를 재사용한다.
    _manual_push_body_lines,
    _paragraph_blocks,
)
from foms.services.storage import get_storage

logger = logging.getLogger(__name__)

__all__ = ["collect_draft_measure_files", "push_measure_room_for_draft"]

#: 실측방 라우팅 키(PC ``_PUSH_KIND_CONFIG['measure_room']`` 과 같은 값).
PUSH_KIND_MEASURE_ROOM = "measure_room"

#: 채널톡 dto.files 의 MIME. PC 경로 ``channel_integration._MIME_MAP`` 과 같은 표를 쓴다
#: (스토리지의 ``_get_content_type`` 은 문서 확장자까지 다루고 기본값이
#: ``application/octet-stream`` 이라 이미지/동영상 전용인 이 경로에는 맞지 않는다).
_MIME_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp",
    "mp4": "video/mp4", "mov": "video/quicktime", "avi": "video/avi",
    "mkv": "video/x-matroska", "webm": "video/webm",
}

#: 서명 URL 유효기간(초). PC 수동 푸쉬와 같은 값.
_SIGNED_URL_TTL_SECONDS = 3600


def _infer_mime(filename: str, file_type: str) -> str:
    """첨부 MIME 추론(PC ``channel_integration._infer_mime`` 미러).

    Args:
        filename: 확장자를 포함한 파일명.
        file_type: ``image`` 또는 ``video``.

    Returns:
        MIME 문자열. 확장자를 모르면 종류 기본값.
    """
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _MIME_MAP:
            return _MIME_MAP[ext]
    return "video/mp4" if file_type == "video" else "image/jpeg"


def _draft_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """draft_v1 봉투 또는 그 ``data`` 객체에서 품목 목록을 꺼낸다.

    호출부가 ``OrderDraft.payload``(봉투)를 넘기든 이미 벗긴 ``data`` 를 넘기든 같은
    결과를 내야 한다 — 초안 sd 변환기(``_draft_payload_to_structured``)는 ``data`` 를
    받고, 라우트가 들고 있는 행 값은 봉투이기 때문이다.

    Args:
        payload: draft_v1 봉투(``{schema_version, step, data}``) 또는 그 ``data``.

    Returns:
        dict 인 품목만 남긴 목록. 모양이 다르면 빈 목록.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def collect_draft_measure_files(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    """초안 첨부(``tmp_key``)를 채널톡 전송용 서명 URL 목록으로 만든다.

    승격 경로(``order_draft_attachments.promote_draft_attachments``)와 **같은 판정**을
    쓴다: ``tmp_key``·``filename`` 이 모두 있고, 스토리지에 실제 객체가 있으며
    (``storage.object_exists``), 확장자가 이미지/동영상인 것만 보낸다. 그 함수는 이
    작업의 수정 금지 범위라 판정을 추출하지 않고 여기서 최소로 재현한다 — 두 경로가
    갈리면 "PUSH 로는 갔는데 등록 후 첨부에는 없는" 파일이 생긴다.

    Args:
        payload: draft_v1 봉투 또는 그 ``data`` 객체.

    Returns:
        ``[{'filename', 'url', 'type'}]`` — 품목 순서 그대로, 최대
        :data:`~foms.services.channel_policy.MAX_MANUAL_ATTACHMENTS` 개.
    """
    storage = get_storage()
    files: list[dict[str, str]] = []
    for item in _draft_items(payload):
        attachments = item.get("attachments")
        if not isinstance(attachments, list):
            continue
        for raw in attachments:
            if not isinstance(raw, dict):
                continue
            tmp_key = str(raw.get("tmp_key") or "").strip()
            filename = str(raw.get("filename") or "").strip()
            if not tmp_key or not filename:
                continue
            if not storage.object_exists(tmp_key):
                continue
            file_type = storage.get_file_type(filename)
            if file_type not in ("image", "video"):
                continue
            url = storage.get_download_url(tmp_key, expires_in=_SIGNED_URL_TTL_SECONDS)
            if not url:
                logger.warning("초안 첨부 서명 URL 발급 실패 (tmp_key=%s)", tmp_key)
                continue
            files.append({"filename": filename, "url": url, "type": file_type})
            if len(files) >= MAX_MANUAL_ATTACHMENTS:
                return files
    return files


def _resolve_group_id() -> tuple[str | None, str | None]:
    """실측방 그룹 id 를 결정한다(PC 수동 푸쉬와 같은 라우팅·같은 실패 분기).

    Returns:
        ``(group_id, error)`` — 성공이면 error 가 None.
        ``group_retired`` 는 삭제된 방(PC 는 410), ``group_missing`` 은 환경변수 미설정.
    """
    try:
        group_id = get_routing_group_id("manual", {"push_kind": PUSH_KIND_MEASURE_ROOM})
    except ChannelGroupRetiredError as exc:
        logger.info("초안 실측 PUSH 차단: retired group (group_id=%s)", exc.group_id)
        return None, "group_retired"
    if not group_id:
        return None, "group_missing"
    return str(group_id), None


def _draft_dto_files(files: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """서명 URL 목록을 채널톡 ``dto.files`` 모양으로 바꾼다(상한 20장).

    Args:
        files: :func:`collect_draft_measure_files` 결과.

    Returns:
        ``[{'fileName', 'url', 'mime'}]``.
    """
    dto: list[dict[str, str]] = []
    for entry in files or []:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        filename = str(entry.get("filename") or "file")
        dto.append({
            "fileName": filename,
            "url": str(entry["url"]),
            "mime": _infer_mime(filename, str(entry.get("type") or "image")),
        })
    return dto[:MAX_MANUAL_ATTACHMENTS]


def push_measure_room_for_draft(
    *,
    sd: dict,
    files: list[dict[str, str]],
    user_id: int | None,
    user_name: str | None = None,
    change_note: str | None = None,
) -> dict[str, Any]:
    """실측방 그룹으로 초안 본문 + 첨부를 전송한다.

    Args:
        sd: 초안 payload 를 변환한 structured_data(본문 조립 SSOT).
        files: :func:`collect_draft_measure_files` 결과.
        user_id: 발송자 user id(로그·추적용).
        user_name: 발송자 표시명 — 채널톡 botName(``FOMS{이름}``)에 쓴다. PC 경로가
            ``pushed_by_name`` 으로 넘기는 값과 같다.
        change_note: 재전송 변경 메모. 있으면 PC 와 같이 ``[수정]`` 머리말로 붙는다.

    Returns:
        ``{'sent', 'error', 'files_count', 'message_id', 'group_id'}``. 실패는 예외 대신
        오류 코드로 분류한다(``not_configured``·``group_retired``·``group_missing``·
        ``send_failed``·``not_sent``).
    """
    if not is_configured():
        return {"sent": False, "error": "not_configured", "files_count": 0,
                "message_id": None, "group_id": None}

    group_id, group_error = _resolve_group_id()
    if group_error is not None:
        return {"sent": False, "error": group_error, "files_count": 0,
                "message_id": None, "group_id": None}

    text = build_measure_push_text(sd)
    lines = _manual_push_body_lines(text, (change_note or "").strip() or None)
    dto_files = _draft_dto_files(files)

    try:
        result = send_group_message(
            group_id=group_id,
            plain_text="\n".join(lines),
            blocks=_paragraph_blocks(lines),
            files=dto_files,
            bot_name=build_channel_bot_name(user_name),
            raise_on_error=True,
        )
    except Exception as exc:  # 벤더 예외는 삼키지 않고 코드로 분류해 호출자에게 넘긴다
        logger.error(
            "초안 실측 PUSH 실패 (user_id=%s, group_id=%s): %s", user_id, group_id, exc,
            exc_info=True,
        )
        return {"sent": False, "error": "send_failed", "files_count": 0,
                "message_id": None, "group_id": group_id}

    if not (isinstance(result, dict) and result.get("success")):
        # 채널톡이 예외 없이 "안 보냈다"를 돌려주는 경로(CH-LATENT-01). 성공으로 읽으면
        # 보낸 적 없는 발송 이력이 남는다.
        logger.error("초안 실측 PUSH 미전송 (group_id=%s, result=%s)", group_id, result)
        return {"sent": False, "error": "not_sent", "files_count": 0,
                "message_id": None, "group_id": group_id}

    logger.info(
        "초안 실측 PUSH 성공 (user_id=%s, group_id=%s, files=%s, message_id=%s)",
        user_id, group_id, len(dto_files), result.get("message_id"),
    )
    return {
        "sent": True,
        "error": None,
        "files_count": len(dto_files),
        "message_id": result.get("message_id"),
        "group_id": group_id,
    }
