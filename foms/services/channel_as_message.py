"""AS 채널톡 PUSH 본문 조립 (서버 SSOT).

AS PUSH 본문은 두 화면에서 발사된다 — ERP 주문수정 탭과 AS 대시보드 첨부 모달.
AS 대시보드에는 주문 폼 DOM 이 없으므로 본문을 클라이언트가 만들 수 없고, 화면마다
다른 조립기를 두면 같은 주문이 화면에 따라 다른 문구로 나가는 드리프트가 난다.
그래서 조립은 저장된 주문(Order + structured_data) 기준으로 서버가 단독 수행한다.

포맷(요청 사양 그대로)::

    고객명 : 홍길동
    발주사 : 숨고
    시공일 : 8월 14일
    주  소 : 경남 창원시 ...
    연락처 : 010-0000-0000

    시공자 - 문정현

    내용 : (AS 모달에서 접수한 최신 내용)

    [1차 기록]
    - 8/13 방안: 후드 자재 발주 후 방문

시공자 줄과 현재 회차 기록 블록은 **값이 있을 때만** 나타난다(없으면 앞뒤 빈 줄까지
통째로 생략 — 구주문 출력이 바뀌지 않는다).
"""

from __future__ import annotations

import re
from typing import Any

from foms.services.as_content_safety import as_content_html_to_text
from foms.services.orders.as_log import current_as_round, decorate_entry

__all__ = ["build_as_push_text", "format_schedule_date_korean"]

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DEFAULT_ORDERER = "라홈"
_NO_CONSTRUCTION_DATE = "상담"
# 현재 회차 기록 블록 상한. as_log 는 항목당 10,000자 append-only 라 상한이 없으면
# 오래된 AS 한 건이 채널톡 메시지 하나를 통째로 삼킨다.
_ROUND_RECORD_LIMIT = 10
_ROUND_RECORD_CHARS = 1000
_ROUND_RECORD_LINE_MAX = 200
# 회차 기록 블록에서 제외하는 유형. reception 은 위 `내용 :` 줄이 이미 담고(중복),
# system·verdict 는 상태 카드·판정 표면 소관이라 발주처에 보낼 정보가 아니다.
_ROUND_EXCLUDED_TYPES = frozenset({"reception", "system", "verdict"})


def format_schedule_date_korean(value: Any) -> str:
    """ISO 날짜를 변환 텍스트와 같은 한글 표기로 바꾼다.

    콤마로 이어진 다중 일정도 각 항목을 개별 변환한다(예: ``2026-08-14,2026-08-15``
    → ``8월 14일, 8월 15일``). ISO 형태가 아니면 원문을 그대로 돌려준다 —
    사용자가 직접 적은 자유 문구(예: ``미정``)를 지우지 않기 위해서다.

    Args:
        value: ``YYYY-MM-DD`` 또는 콤마로 이어진 날짜 문자열.

    Returns:
        ``8월 14일`` 형태의 표시 문자열(빈 입력이면 빈 문자열).
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts: list[str] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        match = _ISO_DATE_RE.match(token)
        parts.append(f"{int(match.group(2))}월 {int(match.group(3))}일" if match else token)
    return ", ".join(parts) if parts else raw


def _append_line(text: str, label: str, value: Any) -> str:
    """``label : value`` 한 줄을 덧붙인다(값이 비면 줄 자체를 생략).

    여러 줄 값은 첫 줄만 라벨을 달고 나머지는 이어 붙인다 — ERP 변환 텍스트
    (``erpAppendConversionTextLine``)와 같은 규칙이라 두 경로의 표기가 어긋나지 않는다.

    Args:
        text: 지금까지 조립된 본문.
        label: 줄 라벨(예: ``고객명``).
        value: 표시 값.

    Returns:
        줄이 덧붙은 본문.
    """
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return text
    lines = normalized.split("\n")
    out = f"{text}{label} : {lines[0].strip()}\n"
    for line in lines[1:]:
        stripped = line.strip()
        if stripped:
            out += f"{stripped}\n"
    return out


def _dict_at(container: Any, *keys: str) -> dict:
    """중첩 dict 를 안전하게 따라간다(중간이 dict 가 아니면 빈 dict)."""
    node = container if isinstance(container, dict) else {}
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return {}
    return node


def _construction_worker_label(sd: dict) -> str:
    """``sd['shipment']['construction_workers']`` → ``문정현`` / ``문정현, 김철수``.

    저장 형태가 리스트로 정규화돼 있지만(:func:`_normalize_construction_workers`),
    구주문·부분 저장에서 문자열이나 dict 항목이 남아 있을 수 있어 관대하게 읽는다.

    Args:
        sd: 주문 structured_data.

    Returns:
        쉼표로 이은 시공자 표시명(없으면 빈 문자열).
    """
    raw = (sd.get("shipment") or {}).get("construction_workers")
    if isinstance(raw, str):
        items: list[Any] = raw.replace("\n", ",").split(",")
    elif isinstance(raw, list):
        items = raw
    else:
        return ""
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            raw_name = item.get("name") or item.get("text") or item.get("value") or ""
        else:
            raw_name = item
        name = str(raw_name or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def _record_line(entry: dict) -> str:
    """as_log 항목 1건 → ``- 8/13 방안: 본문`` 한 줄(개행 접음, 길이 절단).

    본문은 저장 시점 sanitize 를 통과한 HTML 이라 평문화해서 넣는다 — 채널톡은
    plain text 라 태그가 그대로 보이면 읽을 수 없다.

    Args:
        entry: ``decorate_entry`` 를 거친 as_log 항목.

    Returns:
        한 줄 문자열.
    """
    body = as_content_html_to_text(entry.get("text"), already_sanitized=True)
    body = " ".join(body.split())
    if len(body) > _ROUND_RECORD_LINE_MAX:
        body = body[:_ROUND_RECORD_LINE_MAX].rstrip() + "…"
    ts_abs = str(entry.get("ts_abs") or "")
    stamp = ""
    match = _ISO_DATE_RE.match(ts_abs[:10])
    if match:
        stamp = f"{int(match.group(2))}/{int(match.group(3))} "
    label = entry.get("type_label") or "메모"
    return f"- {stamp}{label}: {body}" if body else f"- {stamp}{label}"


def _current_round_block(sd: dict) -> str:
    """현재 회차 기록 블록(``[N차 기록]`` + 항목 줄들). 기록이 없으면 빈 문자열.

    접수 이후 타임라인에 쌓인 방안·통화·자재·메모가 PUSH 에 실리지 않아 "화면은 최신,
    메시지는 접수 시점"으로 갈리던 문제의 수정이다. **현재 회차만** 담는다 — 지난 회차는
    이미 종결된 건이라 발주처가 다시 볼 이유가 없다.

    Args:
        sd: 주문 structured_data.

    Returns:
        블록 문자열(맨 끝 개행 없음) 또는 빈 문자열.
    """
    entries = (sd.get("shipment") or {}).get("as_log")
    if not isinstance(entries, list) or not entries:
        return ""
    round_no = current_as_round(sd)
    picked: list[tuple[str, int, dict]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if entry.get("deleted") is True or entry.get("legacy") is True:
            continue
        if entry.get("type") in _ROUND_EXCLUDED_TYPES:
            continue
        raw_round = entry.get("round")
        entry_round = raw_round if isinstance(raw_round, int) and raw_round >= 1 else 1
        if entry_round != round_no:
            continue
        picked.append((str(entry.get("ts") or ""), idx, entry))
    if not picked:
        return ""
    # ts 동률은 삽입 순서로 tie-break(as_log 전역 규칙과 동일).
    picked.sort(key=lambda item: (item[0], item[1]))

    # 최신 우선으로 채우고 마지막에 되돌린다 — 앞에서부터 채우면 글자 상한에 걸릴 때
    # 잘려 나가는 쪽이 **최신 기록**이 된다(첨부 절단과 같은 함정).
    lines: list[str] = []
    used = 0
    for _ts, _idx, entry in reversed(picked[-_ROUND_RECORD_LIMIT:]):
        line = _record_line(decorate_entry(entry))
        if lines and used + len(line) + 1 > _ROUND_RECORD_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    lines.reverse()

    omitted = len(picked) - len(lines)
    head = f"[{round_no}차 기록]"
    if omitted > 0:
        return "\n".join([head, f"- 외 {omitted}건", *lines])
    return "\n".join([head, *lines])


def build_as_push_text(order: Any) -> str:
    """저장된 주문으로 AS PUSH 본문을 조립한다.

    값은 ``structured_data`` 를 우선하고, 비어 있으면 평면 컬럼(Order.customer_name 등)
    으로 폴백한다 — 구버전/부분 저장 주문에서도 식별 정보가 비지 않게 하기 위해서다.
    본문의 핵심인 AS 접수 내용은 ``structured_data.shipment.as_content`` 하나만 본다
    (append-only ``as_log`` 는 이력 화면 소관이며, PUSH 는 최신 접수 내용만 보낸다).

    Args:
        order: 대상 ``Order`` (structured_data 포함).

    Returns:
        전송 본문. **AS 접수 내용이 없으면 빈 문자열** — 호출자는 이를 전송 거부
        신호로 쓴다(내용 없는 AS 알림은 받는 쪽에 무의미하므로).
    """
    sd = order.structured_data if isinstance(getattr(order, "structured_data", None), dict) else {}

    as_content = str(_dict_at(sd, "shipment").get("as_content") or "").strip()
    if not as_content:
        return ""

    parties = _dict_at(sd, "parties")
    customer = parties.get("customer") if isinstance(parties.get("customer"), dict) else {}
    orderer = parties.get("orderer") if isinstance(parties.get("orderer"), dict) else {}
    site = _dict_at(sd, "site")
    construction = _dict_at(sd, "schedule", "construction")

    customer_name = str(customer.get("name") or "").strip() or (getattr(order, "customer_name", "") or "")
    orderer_name = str(orderer.get("name") or "").strip() or _DEFAULT_ORDERER
    phone = str(customer.get("phone") or "").strip() or (getattr(order, "phone", "") or "")
    address = (
        str(site.get("address_full") or site.get("address_main") or "").strip()
        or (getattr(order, "address", "") or "")
    )
    construction_date = (
        str(construction.get("date") or "").strip()
        or str(getattr(order, "erp_construction_date", "") or "").strip()
    )
    construction_label = format_schedule_date_korean(construction_date) or _NO_CONSTRUCTION_DATE

    text = ""
    text = _append_line(text, "고객명", customer_name)
    text = _append_line(text, "발주사", orderer_name)
    text = _append_line(text, "시공일", construction_label)
    text = _append_line(text, "주  소", address)
    text = _append_line(text, "연락처", phone)
    # 시공자는 고객정보와 AS 내용 사이의 독립 블록이다(사용자 확정 서식) — `라벨 : 값`
    # 5줄과 구분되도록 하이픈 표기이며, 앞뒤 빈 줄이 채널톡에서 문단 경계로 살아난다.
    worker_label = _construction_worker_label(sd)
    if worker_label:
        if text:
            text += "\n"
        text += f"시공자 - {worker_label}\n"
    if text:
        text += "\n"
    text = _append_line(text, "내용", as_content)
    round_block = _current_round_block(sd)
    if round_block:
        text = f"{text.rstrip()}\n\n{round_block}\n"
    return text.strip()
