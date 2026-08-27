"""주문 구조화 데이터 변경 비교 — 감사 원장용 필드 단위 diff (ORDER-DIFF-00).

**왜 필요한가**: 2026-08-11 운영 실측에서 ``/security_logs`` 최근 50행 중 ``before``/``after``
를 가진 행이 **0건**이었다. ``ORDER_STRUCTURED_SAVED`` 는 "누가 언제 저장했다"까지만 남기고
"무엇이 어떻게 바뀌었다"가 없어, 금액·일정·품목 규격 분쟁을 감사 원장으로 되짚을 수 없었다.
상용 ERP 의 최소 단위(SAP ``CDPOS`` 의 필드·구값·신값, 21 CFR 11.10(e) 의 old/new value)를
FOMS 구조화 저장 경로에 맞춘 것이 이 모듈이다.

**설계 규칙 3개**

1. **화이트리스트 pull** — 트리 전체를 순회하지 않고 :data:`SCALAR_PATHS` · :data:`ITEM_FIELDS`
   에 적힌 경로만 읽는다. 저장은 hot path 라 비용이 데이터 크기가 아니라 경로 수로 고정돼야
   하고, Dynamics BC 공식 지침도 "All Fields 추적 금지"다(볼륨·성능).
2. **빈값 동치** — ``None`` · ``''`` · 키 부재를 모두 빈값으로 본다. 아니면 저장 버튼만 눌러도
   "변경됨"이 쌓여 원장이 소음으로 덮인다.
3. **라벨은 여기서 굽지 않는다** — 결과에는 ``path`` 와 값만 담고, 사람 라벨은 읽기 시점에
   :mod:`foms.services.audit_message_display` 가 붙인다(라벨을 고치면 과거 기록도 함께 고쳐진다).
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, NamedTuple

from foms.services.orders.structured_item_uid import item_uid_of

__all__ = [
    "ITEM_FIELDS",
    "MAX_CHANGES",
    "NUMERIC_PATH_SUFFIXES",
    "SCALAR_PATHS",
    "AMOUNT_PATH_TEMPLATES",
    "CONFIRMED_STAGES",
    "ITEM_DETAIL_TEMPLATES",
    "STAGE_TEMPLATES",
    "CONSTRUCTION_SCHEDULE_TEMPLATES",
    "SENSITIVE_ITEM_OPS",
    "SENSITIVE_ITEM_TEMPLATE",
    "SITE_EXTRA_PATH",
    "CONTENT_MODIFIED_MARK",
    "DiffResult",
    "diff_structured",
    "get_path",
    "normalize_for_ledger",
    "strip_markup",
]

#: 감사 대상 스칼라 경로(2026-08-11 staging 주문 3,412건 키 분포 조사 기반).
#: 여기 없는 경로는 기록하지 않는다 — 파생/캐시 값(``totals`` 재계산 결과 제외 대상 아님에
#: 주의: totals 는 금액이라 포함한다)과 별도 원장이 있는 값(``shipment.as_log`` = AS 타임라인,
#: ``payment.*_confirmed*`` = ``PAYMENT_CONFIRMED`` action, 도면 = ``drawing_revisions``)은 뺀다.
#: **요약 축**(:data:`SITE_EXTRA_PATH` · 품목 ``spec_rows``)도 여기 없다 — 값이 길어 그대로
#: 실으면 절단되므로 별도 요약 함수가 비교키와 표시값을 따로 만든다.
SCALAR_PATHS: tuple[str, ...] = (
    # --- 일정 ---
    "schedule.measurement.date",
    "schedule.measurement.time",
    "schedule.construction.date",
    "schedule.construction.time",
    "schedule.as_visit.date",
    "schedule.as_visit.time",
    # AUDIT-GAP-01: 고객과 약속한 AS 방문 가능 시간대(평일/주말 · 오전/오후). 폼 저장이
    # as_visit 을 통째로 지우던 선행 결함을 보존 목록으로 고친 뒤 등재했다 — 그 전에
    # 등재했다면 저장 1회마다 허위 '지움' 행이 쌓였다.
    "schedule.as_visit.availability",
    # --- 당사자 ---
    "parties.customer.name",
    "parties.customer.phone",
    # 보조 연락처. 수집이 채우고 폼은 렌더하지 않는다 — 원장에 없으면 사라져도 흔적이 없다
    # (2026-08-20 유실 사고: 누가 언제 지웠는지 남지 않았다).
    "parties.customer.phone2",
    # 발주사(라홈/하우드). 주문한 사람은 아래 buyer 다 — ORDERER-AXIS-01.
    "parties.orderer.name",
    "parties.orderer.phone",
    "parties.buyer.name",
    "parties.buyer.phone",
    "parties.manager.name",
    # --- 현장 ---
    "site.address_full",
    "site.address_detail",
    # --- 단계/플래그/배정 ---
    "workflow.stage",
    "flags.urgent",
    "flags.urgent_reason",
    # 라홈시스템(2공장). 견적서 공급자·입금 계좌를 가르는 값이라 누가 언제 돌렸는지가
    # 남아야 한다 — 2026-08-26 이전에는 토글 이력이 어디에도 없었다.
    "flags.factory2",
    "assignments.owner_team",
    "assignments.drawing_assignee_user_ids",
    # --- 금액 ---
    "totals.items_total",
    "totals.deposit_amount",
    "totals.balance_amount",
    "totals.final_amount",
    "totals.discount_amount",
    "totals.free_input_amount",
    "totals.contract_total",
    "totals.shipping_price",
    # --- 결제(확인 행위는 PAYMENT_CONFIRMED action 이 따로 남긴다) ---
    "payment.deposit",
    "payment.discount",
    "payment.free_input",
    "payment.cash_receipt",
    # 잔금 조건을 적는 자유 칸. 금액이 아니라 약속(``설치 후 현금``)이 적히는 자리라
    # 분쟁에서 자주 인용되는데 2026-08-26 이전에는 누가 언제 고쳤는지가 없었다 (AUDIT-GAP-01).
    "payment.balance_note",
    # --- 출고/시공 ---
    "shipment.sales_delivery",
    "shipment.construction_time",
    "shipment.construction_workers",
    "shipment.trip",
    "shipment.as_billing",
    "shipment.as_pending",
    # AS 접수 본문(HTML). ``shipment.as_log`` 타임라인은 append-only 라 **덮어쓰기**를 잡지
    # 못한다 — 본문이 통째로 바뀐 사실은 이 경로에만 남는다 (AUDIT-GAP-01).
    # 판정은 sanitize 된 HTML 원문으로 하고, 원장에 실을 **표시값**만 태그를 벗긴다
    # (:data:`_MARKUP_TEXT_PATHS` · :func:`_display_for_ledger`).
    "shipment.as_content",
    # --- 비고(문자열 SSOT — dict 아님) ---
    "notes",
)

#: 품목 1건에서 감사할 필드. ``spec_rows`` 는 중첩 배열이라 셀 단위가 아니라 행 수 요약으로 본다.
ITEM_FIELDS: tuple[str, ...] = (
    "product_name",
    "price",
    "spec",
    "spec_width",
    "spec_height",
    "spec_depth",
    "color",
    "handle",
    "option_detail",
    "extra_input",
    "misc",
    "internal",
    "measurement_date",
    "construction_date",
)

#: 숫자로 정규화해 비교할 경로 꼬리(``"1,300"`` 과 ``1300`` 을 같은 값으로 본다).
#: 전 경로에 숫자 정규화를 걸면 ``"0900"`` 같은 앞자리 0 값이 훼손되므로 금액에만 적용한다.
NUMERIC_PATH_SUFFIXES: tuple[str, ...] = (".price", ".amount", ".deposit", ".discount")

#: 한 저장에 담을 변경 상한. 초과분은 버리지 않고 개수(:attr:`DiffResult.truncated`)로 남긴다.
MAX_CHANGES = 40

#: 변경 사유를 물어야 하는 **제품 세부 내역** 경로(ORDER-REASON-00). 값은 경로 템플릿이라
#: ``path_template_of`` 로 정규화한 뒤 대조한다(품목 번호와 무관하게 판정된다).
#:
#: 축을 셋(시공일·금액·제품 세부)으로 좁힌 것은 사용자 결정(2026-08-14)이다. 전 경로에
#: 사유를 물으면 직원이 귀찮아서 아무 값이나 고르고, 그 순간 기록의 가치가 0 이 된다.
#: 여기서 빠지는 것: 실측일·AS 방문일·단계(``workflow.stage``)·연락처·주소·비고.
#:
#: ``internal`` 은 내부 메모라 제품 사양이 아니고, ``price`` 는 금액 축
#: (:data:`AMOUNT_PATH_TEMPLATES`)이 임계와 함께 따로 본다.
ITEM_DETAIL_TEMPLATES: frozenset[str] = frozenset({
    "items.*.product_name",
    "items.*.spec",
    "items.*.spec_rows",
    "items.*.spec_width",
    "items.*.spec_height",
    "items.*.spec_depth",
    "items.*.color",
    "items.*.handle",
    "items.*.option_detail",
    "items.*.extra_input",
    "items.*.misc",
})

#: **``totals.*`` 는 일부러 뺐다** — 전부 서버 파생값이다(``structured_form_projection`` 이 매
#: 저장마다 품목 price·payment 입력에서 재계산한다). 넣으면 저장된 totals 가 낡은 주문에서
#: 전화번호만 고친 저장이 "금액 변경"으로 판정돼 사유를 묻는다(2026-08-13 실측으로 확인).
#: 파생값은 그 값을 만든 **입력 경로**가 대신 대표한다.

#: 단계 이동(취소·보류 포함) — 사용자 결정(2026-08-14)으로 축에 되살렸다. "왜 취소했나"는
#: 분쟁에서 가장 자주 묻는 질문이고, 운영 실측상 단계 변경은 2일간 0건이라 빈도 비용도 없다.
#:
#: **주의**: FOMS 의 "주문 취소"는 구조화 저장이 아니라 **휴지통 이동**(``ORDER_SOFT_DELETED``,
#: ``/delete/<id>``)이다. 여기서 잡는 것은 구조화 저장으로 일어나는 단계 이동뿐이고, 휴지통
#: 이동 사유는 별도 경로가 필요하다.
STAGE_TEMPLATES: frozenset[str] = frozenset({"workflow.stage"})

#: 시공 일정 경로. 다른 일정과 달리 **확정(CONFIRM) 이후**에만 사유를 묻는다 —
#: 접수·실측·도면 단계의 시공일은 아직 "잡는 중"인 값이라 바뀌는 게 정상이다.
#: 운영 실측(2026-08-13): 시공일 변경이 전체 사유 요구의 27% 로 단일 최대 기여였다.
CONSTRUCTION_SCHEDULE_TEMPLATES: frozenset[str] = frozenset({
    "schedule.construction.date",
    "schedule.construction.time",
    "items.*.construction_date",
})

#: 시공일 변경에 사유를 묻기 시작하는 단계(고객 컨펌 이후 = 고객과 약속된 날짜).
CONFIRMED_STAGES: frozenset[str] = frozenset({
    "CONFIRM", "PRODUCTION", "CONSTRUCTION", "CS", "COMPLETED",
})

#: 금액 **입력** 경로. 사유 판정은 여기만 금액 임계(잔돈 변경 제외)를 함께 본다 —
#: 목록 자체는 :data:`ITEM_DETAIL_TEMPLATES` 와 분리해 둔다(금액만 임계를 함께 본다).
AMOUNT_PATH_TEMPLATES: frozenset[str] = frozenset({
    "payment.deposit",
    "payment.discount",
    "payment.free_input",
    "items.*.price",
})

#: 품목 구성 변경(``items.*`` 의 추가·삭제)도 사유 대상이다. 품목 하나가 통째로 들고 나면
#: 개별 필드 변경이 아니라 ``add``/``remove`` 1건으로만 남아 ``items.*.price`` 에 걸리지 않는다.
SENSITIVE_ITEM_TEMPLATE = "items.*"

#: 위 템플릿에서 사유를 요구하는 연산.
SENSITIVE_ITEM_OPS: frozenset[str] = frozenset({"add", "remove"})

#: 현장 특이사항 경로. :data:`SCALAR_PATHS` 에 **일부러 넣지 않았다** — 값 그대로 실으면
#: 원장이 거짓말을 한다(아래 :func:`_site_extra_summary` 참조). ``spec_rows`` 와 같은 요약 축이다.
SITE_EXTRA_PATH = "shipment.site_extra"

#: 현장 특이사항 요약 표시값의 단위(``3건``).
#:
#: 원장 초안은 값 자체를 ``특이사항 3건`` 으로 적자고 했지만, 라벨(``현장 특이사항``)은 읽기
#: 시점에 :func:`~foms.services.audit_message_display.describe_change` 가 앞에 붙인다 —
#: 그대로 두면 화면에 ``현장 특이사항 특이사항 2건 → 특이사항 3건`` 이 뜬다. 그래서 같은
#: 사정을 먼저 겪은 ``spec_rows``(표시값 ``3행``, 라벨 ``규격표``)의 규칙을 따른다.
_SITE_EXTRA_UNIT = "건"

#: 표시값이 같아 보이는 변경 행의 ``after`` 에 붙이는 표식 — **공용 상수**.
#:
#: 원장은 값을 :data:`_VALUE_LIMIT` 에서 자르고 요약 축은 아예 건수만 싣는다. 그래서 실제로
#: 바뀐 행이 화면에 ``3건 → 3건`` · ``A… → A…`` 로 나오고, 읽는 사람은 오타나 버그로 여긴다
#: (무엇이 바뀌었는지는 어디에도 없다). 그 행에 이 표식을 붙여 "표시값은 같지만 저장된 값은
#: 달라졌다"를 말한다.
#:
#: 처음엔 현장 특이사항 전용 이름(``_SITE_EXTRA_CONTENT_MARK``)이었는데 같은 사정이 네 곳에서
#: 났다 — 건수 요약(site_extra·``spec_rows``) · 지방 메모 절단(``regional.py``) · 옵션/AS 본문
#: 절단. 리터럴을 파일마다 두면 한쪽만 고쳐져 감사 화면에 표식이 두 종류로 뜬다.
CONTENT_MODIFIED_MARK = "(내용 수정)"

_EMPTY_TOKENS = frozenset({"", "none", "null", "-"})
_VALUE_LIMIT = 120

#: HTML 태그·연속 공백 제거용. :mod:`foms.services.audit_message_display` 가 **이 함수를
#: 그대로 쓴다**(:func:`strip_markup`) — 태그 정규식이 두 벌이 되면 쓰기(원장 표시값)와
#: 읽기(화면 요약)가 서로 다른 텍스트를 보게 된다.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: 원장 값이 **HTML** 인 경로. 표시값에서 태그를 먼저 벗긴다(:func:`_display_for_ledger`).
_MARKUP_TEXT_PATHS: frozenset[str] = frozenset({"shipment.as_content"})

#: 원장 값이 **JSON 문자열** 인 경로(평면 컬럼). 빈 칸을 걷어낸 안정 직렬화로 다시 적는다.
_JSON_TEXT_PATHS: frozenset[str] = frozenset({"options"})


class DiffResult(NamedTuple):
    """변경 비교 결과.

    Attributes:
        changes: 상한까지 잘라낸 변경 목록(``{'path','before','after','op'}``,
            품목 변경은 ``'item'`` 에 저장 시점 품목명이 붙는다).
        total: 상한과 무관한 실제 변경 건수.
        truncated: 상한 때문에 목록에서 빠진 건수(``total - len(changes)``).
    """

    changes: list[dict[str, Any]]
    total: int
    truncated: int


def _is_numeric_path(path: str) -> bool:
    """경로가 금액류인지(숫자 정규화 대상인지) 판정한다.

    :param path: 점 경로.
    :return: 숫자 정규화를 적용할 경로면 ``True``.
    """
    if path.startswith("totals."):
        return True
    return any(path.endswith(suffix) for suffix in NUMERIC_PATH_SUFFIXES)


def _prune_empty(value: Any) -> Any:
    """빈 잎을 걷어낸 값을 낸다(남는 게 없으면 ``None``).

    ``{"address_note": "", "construction_note": ""}`` 처럼 **키만 있고 내용이 없는** 객체는
    "비고를 입력했다"가 아니라 폼이 빈 칸을 그대로 저장한 흔적이다. 걷어내지 않으면
    저장 버튼만 눌러도 원장에 ``비고 (없음) → {"address_note": "", …}`` 가 쌓인다
    (2026-08-14 운영 실측).

    :param value: 원시 값(중첩 dict/list 허용).
    :return: 내용이 남으면 걷어낸 값, 전부 비었으면 ``None``. ``False``·``0`` 은 값으로 본다
        (빈값 여부는 :func:`_is_unset` 이 경로 성격과 함께 판정한다).
    """
    if isinstance(value, dict):
        pruned_map = {key: pruned for key, item in value.items()
                      if (pruned := _prune_empty(item)) is not None}
        return pruned_map or None
    if isinstance(value, list):
        pruned_list = [pruned for item in value if (pruned := _prune_empty(item)) is not None]
        return pruned_list or None
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip()
        return None if text.lower() in _EMPTY_TOKENS else text
    return value


def _is_unset(normalized: Any, *, numeric: bool) -> bool:
    """정규 값이 "지정하지 않음"과 같은 뜻인지 판정한다.

    폼이 처음 저장될 때 미지정 키가 기본값으로 채워진다(체크 안 한 체크박스 → ``False``,
    빈 금액 칸 → ``0``, 빈 목록 → ``[]``). 이것을 변경으로 적으면 원장이 소음으로 덮여
    **진짜 변경이 묻힌다** — 양쪽이 모두 이 상태일 때만 기록에서 뺀다(값→0 은 실제 변경이라 남긴다).

    :param normalized: :func:`_normalize` 를 거친 값.
    :param numeric: 금액류 경로면 ``True`` — 이때만 ``0`` 을 미지정과 같게 본다
        (``"0900"`` 같은 시각·코드 값을 훼손하지 않기 위해 경로를 가린다).
    :return: 미지정과 같은 뜻이면 ``True``.
    """
    if normalized is None or normalized is False:
        return True
    return bool(numeric and normalized == "0")


def _normalize(value: Any, *, numeric: bool) -> Any:
    """비교용 정규 값으로 옮긴다(빈값 동치 + 금액 숫자 동치).

    :param value: 원시 값.
    :param numeric: 금액류 경로면 ``True`` — ``"1,300"`` 과 ``1300`` 을 같게 본다.
    :return: 비교 가능한 값(빈값은 ``None``).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict)):
        # 목록/객체(도면 배정자 등)는 안정 직렬화로 비교한다 — 키 순서 차이를 변경으로 읽지 않는다.
        # 내용 없는 키는 걷어낸 뒤 비교·저장한다(빈 칸 저장이 변경으로 남지 않는다).
        pruned = _prune_empty(value)
        if pruned is None:
            return None
        try:
            return json.dumps(pruned, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(pruned)
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)

    text = str(value).strip()
    if text.lower() in _EMPTY_TOKENS:
        return None
    if numeric:
        probe = text.replace(",", "")
        try:
            number = float(probe)
        except ValueError:
            return text
        return str(int(number)) if number.is_integer() else str(number)
    return text


def _get_path(source: Any, path: str) -> Any:
    """점 경로로 값을 꺼낸다(중간이 dict 가 아니면 ``None``).

    :param source: ``structured_data`` dict.
    :param path: ``schedule.measurement.date`` 형태 경로.
    :return: 값 또는 ``None``.
    """
    node: Any = source
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def get_path(source: Any, path: str) -> Any:
    """점 경로로 값을 꺼낸다(공개 진입점 — 복원 경로가 같은 규칙으로 읽게 한다).

    :param source: ``structured_data`` dict.
    :param path: ``schedule.measurement.date`` 형태 경로.
    :return: 값 또는 ``None``.
    """
    return _get_path(source, path)


def normalize_for_ledger(value: Any, path: str) -> Any:
    """원장에 실릴 정규 값(경로별 축소 + 절단)을 만든다.

    diff 가 저장하는 값과 **같은 규칙**이어야 한다 — 복원 경로가 "지금 값이 원장의
    after 와 같은가"를 물으려면 같은 정규화를 거친 뒤 비교해야 하기 때문이다. 평면 컬럼
    경로(``edit.py``·``regional.py``)도 이 함수를 거치므로 축소 규칙이 한 곳에 모인다.

    **판정에 쓰면 안 된다** — 여기서 나온 값은 이미 잘려 있어, 120자 뒤만 바뀐 저장이
    '무변경'으로 사라진다(그게 곧 무기록이다). 변경 여부는 절단 전 원문으로 판정하고
    (``diff_structured`` 의 스칼라 루프 · ``edit.py._compare_value``), 이 함수의 결과는
    원장 칸에 담을 표현으로만 쓴다.

    :param value: 원시 값(``structured_data`` 에서 읽은 그대로).
    :param path: 그 값의 점 경로(금액·HTML·JSON 규칙 판정에 쓴다).
    :return: 정규화·축소·절단된 값(빈값은 ``None``).
    """
    return _display_for_ledger(path, _normalize(value, numeric=_is_numeric_path(path)))


def strip_markup(text: str) -> str:
    """HTML 태그를 지우고 공백을 접어 한 줄 텍스트로 만든다.

    쓰기(원장 표시값)와 읽기(:func:`~foms.services.audit_message_display.format_value`)가
    **같은 함수**를 써야 한다 — 태그 정규식이 두 벌이 되면 원장에 담긴 텍스트와 화면에 뜨는
    텍스트가 서로 다른 규칙으로 잘린다.

    :param text: HTML 이 섞여 있을 수 있는 문자열.
    :return: 태그 없는 한 줄 문자열.
    """
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _compact_json_text(text: str) -> str | None:
    """JSON 문자열을 **빈 칸을 걷어낸** 안정 직렬화로 다시 적는다.

    평면 ``options`` 컬럼은 값이 JSON 문자열이라 ``_normalize`` 의 dict 가지를 타지 못하고
    원문 그대로 실린다. 그런데 ``direct`` 옵션의 **빈 스켈레톤만 162자**라(2026-08-26 실측)
    :data:`_VALUE_LIMIT` 를 이미 넘는다 — ``misc``·``quote``·``option_detail`` 처럼 뒤쪽에
    직렬화되는 칸은 무엇을 고쳐도 원장에 ``A… → A…`` 로 남았다. 빈 칸을 걷어내면 같은 값이
    53자로 줄어 **바뀐 칸이 그대로 보인다**.

    라벨을 굽지 않는다(모듈 docstring 규칙 3) — 여기서 만드는 것은 여전히 JSON 데이터이고,
    사람 표기는 읽기 시점에 ``audit_message_display._format_structured_text`` 가 붙인다.

    :param text: 값 문자열.
    :return: 다시 적은 JSON. 내용이 하나도 없으면 ``None``, JSON 이 아니면 원문 그대로.
    """
    if not (text.startswith("{") or text.startswith("[")):
        return text
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return text
    compact = _normalize(parsed, numeric=False)
    if compact is None:
        return None
    return compact if isinstance(compact, str) else text


def _display_for_ledger(path: str, value: Any) -> Any:
    """원장 칸에 담을 **표시값**을 만든다(경로별 군살 제거 → 절단).

    :data:`_VALUE_LIMIT` 는 컬럼 상한이라 늘릴 수 없다. 그러면 그 예산을 무엇에 쓰느냐가
    문제인데, 두 경로는 예산을 **내용이 아닌 껍데기**에 쓰고 있었다:

    * ``shipment.as_content`` = sanitize 된 HTML. 2026-08-26 실측에서 여는 태그
      (``<div class="as-body"><p style="…">``)만 56자를 먹어 실텍스트가 64자밖에 남지 않았고,
      본문 중간중간의 태그가 남은 예산도 갉아먹는다. 태그를 먼저 벗기면 같은 120자에
      본문이 훨씬 많이 들어간다.
    * ``options`` = JSON 문자열. :func:`_compact_json_text` 참조.

    **판정은 건드리지 않는다.** 변경 여부는 호출부가 절단 전 원문으로 이미 판정했고
    (``diff_structured`` 스칼라 루프 · ``edit.py._compare_value``), 이 함수는 그 결과를
    사람이 읽을 칸에 옮기기만 한다 — 태그만 바뀐 저장도 변경으로 기록되고, 표시값이 같아지면
    :func:`~foms.services.audit_message_display.describe_change` 가
    :data:`CONTENT_MODIFIED_MARK` 로 구분한다.

    :param path: 원장 경로.
    :param value: :func:`_normalize` 를 거친 값.
    :return: 절단된 표시값.
    """
    if isinstance(value, str):
        if path in _MARKUP_TEXT_PATHS:
            # 태그뿐인 본문(``<br>`` 만 남은 값)을 빈값으로 둔갑시키지 않는다 — 벗겨서 남는 게
            # 없으면 원문을 그대로 싣고, 값이 없다는 판정은 호출부(_op_of)가 원문으로 한다.
            value = strip_markup(value) or value
        elif path in _JSON_TEXT_PATHS:
            value = _compact_json_text(value)
    return _clip(value)


def _clip(value: Any) -> Any:
    """저장할 값 표현을 만든다(긴 문자열은 절단 표시와 함께 자른다).

    :param value: 정규화된 값.
    :return: 원 값 또는 ``…`` 를 붙인 절단 문자열.
    """
    if isinstance(value, str) and len(value) > _VALUE_LIMIT:
        return f"{value[:_VALUE_LIMIT]}…"
    return value


def _op_of(before: Any, after: Any) -> str:
    """변경 종류를 판정한다.

    :param before: 이전 정규 값.
    :param after: 이후 정규 값.
    :return: ``'add'``(빈값→값) · ``'clear'``(값→빈값) · ``'set'``(값→값).
    """
    if before is None:
        return "add"
    if after is None:
        return "clear"
    return "set"


def _change(
    path: str,
    before: Any,
    after: Any,
    *,
    item: str | None = None,
    op: str | None = None,
    uid: str | None = None,
) -> dict[str, Any]:
    """변경 1건 dict 를 만든다.

    :param path: 점 경로.
    :param before: 이전 정규 값.
    :param after: 이후 정규 값.
    :param item: 품목 경로면 저장 시점 품목명(읽는 사람이 인덱스만으로 헤매지 않게).
    :param op: 변경 종류 강제 지정. 품목 자체의 추가/삭제(``add``/``remove``)는 값 유무로
        추론한 ``add``/``clear`` 와 뜻이 다르므로 호출부가 명시한다.
    :param uid: 품목 안정 식별자(ORDER-ITEM-UID). 인덱스는 저장마다 바뀔 수 있어도 이 값은
        같은 품목을 계속 가리킨다 — 원장이 품목 축으로 이력을 모을 수 있는 유일한 열쇠다.
    :return: ``security_logs.detail['changes']`` 에 들어갈 dict.
    """
    entry: dict[str, Any] = {
        "path": path,
        # 값은 경로별 표시 규칙을 거친다(HTML 태그 제거·JSON 압축 → 절단). ``op`` 는 **절단 전**
        # 값으로 판정한다 — 잘린 값으로 판정하면 120자 뒤만 바뀐 저장이 통째로 사라진다.
        "before": _display_for_ledger(path, before),
        "after": _display_for_ledger(path, after),
        "op": op or _op_of(before, after),
    }
    if item:
        entry["item"] = _clip(item)
    if uid:
        entry["uid"] = uid
    return entry


def _items_of(source: Any) -> list[dict[str, Any]]:
    """``structured_data['items']`` 를 dict 목록으로 정규화한다.

    :param source: ``structured_data``.
    :return: 품목 dict 목록(형식이 아니면 빈 목록).
    """
    if not isinstance(source, dict):
        return []
    items = source.get("items")
    if not isinstance(items, list):
        return []
    return [item if isinstance(item, dict) else {} for item in items]


def _item_name(item: dict[str, Any]) -> str | None:
    """품목 표시명(``product_name``)을 꺼낸다.

    :param item: 품목 dict.
    :return: 이름 문자열 또는 ``None``.
    """
    name = _normalize(item.get("product_name"), numeric=False)
    return name if isinstance(name, str) else None


def _spec_rows_summary(item: dict[str, Any]) -> tuple[Any, str | None]:
    """규격표(``spec_rows``)를 비교키와 표시값으로 요약한다.

    셀 단위 diff 는 v1 범위 밖이다 — 행 수와 안정 직렬화만 보고 "몇 행에서 몇 행" 으로 남긴다.

    :param item: 품목 dict.
    :return: ``(비교키, 표시값)``. 규격표가 없으면 ``(None, None)``.
    """
    rows = item.get("spec_rows")
    if not isinstance(rows, list) or not rows:
        return None, None
    try:
        key = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        key = repr(rows)
    return key, f"{len(rows)}행"


def _site_extra_summary(source: Any) -> tuple[Any, str | None]:
    """현장 특이사항(``shipment.site_extra``)을 **비교키와 표시값으로 나눠** 요약한다.

    저장 형식은 ``{text, color}`` **최대 20개 · text 500자** 리스트다(``shipment/writer.py``
    의 exact schema). 이 값을 :data:`SCALAR_PATHS` 에 그냥 넣으면 직렬화 JSON 이
    :func:`_clip` 의 120자 상한에서 잘리고, 앞 120자가 같으면 **``before`` 와 ``after`` 가
    똑같아 보이는 행**이 남는다 — 원장이 "바뀌었다"면서 무엇이 바뀌었는지는커녕 바뀐 것처럼
    보이지도 않게 된다. ``spec_rows``(:func:`_spec_rows_summary`) 가 먼저 쓴 해법을 따른다.

    **비교키는 내용 전체, 표시값은 건수**로 나눈 이유:

    * 건수로 비교하면 "3건 중 한 줄의 문구만 고친" 변경을 통째로 놓친다. 특이사항은 건수보다
      **문구**가 분쟁 대상이라(``엘리베이터 없음`` 한 줄이 사라지면 시공이 멈춘다) 놓치면 안 된다.
    * 그렇다고 내용을 표시값으로 실을 수는 없다 — 500자 × 20개는 어차피 절단된다. 원장은
      "몇 건에서 몇 건으로, 내용이 바뀌었다"까지만 말하고 본문은 주문 화면이 갖는다.

    비교는 **순서에 민감**하다(화면 표시 순서가 곧 사용자가 정한 우선순위다). 빈 text 항목은
    양쪽 모두에서 걷어내므로 빈 칸 추가·삭제는 변경으로 남지 않는다.

    :param source: ``structured_data``.
    :return: ``(비교키, 표시값)`` — 표시값은 ``3건`` (라벨은 읽기 시점에 붙는다,
        :data:`_SITE_EXTRA_UNIT` 참조). 내용 있는 항목이 하나도 없으면 ``(None, None)``.
    """
    entries = _get_path(source, SITE_EXTRA_PATH)
    if not isinstance(entries, list):
        return None, None

    normalized: list[dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
            color = str(entry.get("color") or "").strip()
        else:  # 폼 왕복 호환: 순수 문자열 항목도 저장돼 있다(shipment_reference.py:206).
            text = str(entry or "").strip()
            color = ""
        if text:
            normalized.append({"text": text, "color": color})

    if not normalized:
        return None, None
    key = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return key, f"{len(normalized)}{_SITE_EXTRA_UNIT}"


def _diff_site_extra(old_sd: Any, new_sd: Any) -> Iterable[dict[str, Any]]:
    """현장 특이사항 변경 1건을 낸다(변화가 없으면 아무것도 내지 않는다).

    :param old_sd: 이전 ``structured_data``.
    :param new_sd: 이후 ``structured_data``.
    :yield: 변경 dict(최대 1건).
    """
    old_key, old_display = _site_extra_summary(old_sd)
    new_key, new_display = _site_extra_summary(new_sd)
    if old_key == new_key:
        return
    if new_display is not None and new_display == old_display:
        new_display = f"{new_display}{CONTENT_MODIFIED_MARK}"
    yield _change(SITE_EXTRA_PATH, old_display, new_display)


def _diff_item_pair(
    index: int,
    old_item: dict[str, Any],
    new_item: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    """짝지어진 품목 1쌍의 필드 변경을 낸다.

    :param index: 표시·경로에 쓸 **새 문서 기준** 위치(사람이 보는 "N번 품목").
    :param old_item: 이전 품목 dict.
    :param new_item: 이후 품목 dict.
    :yield: 변경 dict.
    """
    name = _item_name(new_item) or _item_name(old_item)
    for field in ITEM_FIELDS:
        path = f"items.{index}.{field}"
        numeric = _is_numeric_path(path)
        before = _normalize(old_item.get(field), numeric=numeric)
        after = _normalize(new_item.get(field), numeric=numeric)
        if before == after:
            continue
        if _is_unset(before, numeric=numeric) and _is_unset(after, numeric=numeric):
            continue  # 미지정 ↔ 기본값(0·False·빈 목록)은 변경이 아니다.
        yield _change(path, before, after, item=name, uid=item_uid_of(new_item))
    old_key, old_display = _spec_rows_summary(old_item)
    new_key, new_display = _spec_rows_summary(new_item)
    if old_key != new_key:
        yield _change(f"items.{index}.spec_rows", old_display, new_display,
                      item=name, uid=item_uid_of(new_item))


def _diff_items_by_uid(
    old_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> Iterable[dict[str, Any]]:
    """uid 로 짝지어 품목 변경을 낸다 (ORDER-ITEM-UID).

    위치가 아니라 identity 로 맞추므로 중간 삽입·순서 변경이 "여러 품목 변경"으로 번지지 않는다.
    **순서만 바뀐 품목은 기록하지 않는다** — 값이 그대로면 변경이 아니다(사용자 결정 2026-08-11).

    :param old_items: 이전 품목 목록(전부 uid 보유).
    :param new_items: 이후 품목 목록(전부 uid 보유).
    :yield: 변경 dict.
    """
    old_by_uid = {item_uid_of(item): item for item in old_items}
    new_uids = {item_uid_of(item) for item in new_items}

    for index, new_item in enumerate(new_items):
        uid = item_uid_of(new_item)
        old_item = old_by_uid.get(uid)
        if old_item is None:
            yield _change(f"items.{index}", None, _item_name(new_item) or "(이름 없음)",
                          op="add", uid=uid)
            continue
        yield from _diff_item_pair(index, old_item, new_item)

    for index, old_item in enumerate(old_items):
        uid = item_uid_of(old_item)
        if uid not in new_uids:
            yield _change(f"items.{index}", _item_name(old_item) or "(이름 없음)", None,
                          op="remove", uid=uid)


def _diff_items(old_sd: Any, new_sd: Any) -> Iterable[dict[str, Any]]:
    """품목 배열 변경을 훑는다(uid 우선, 없으면 위치 인덱스).

    양쪽 품목이 모두 uid 를 갖고 있으면 identity 로 짝짓는다(ORDER-ITEM-UID). 하나라도 없으면
    — uid 도입 이전에 저장된 문서다 — 예전처럼 위치로 짝짓는다. 이 폴백에서는 중간 삽입이
    "여러 품목이 동시에 바뀐 것"으로 읽히며(NetSuite 서브리스트 사각지대와 같은 계열),
    읽는 사람이 판별할 수 있도록 각 변경에 저장 시점 품목명(``item``)을 함께 남긴다.

    :param old_sd: 이전 ``structured_data``.
    :param new_sd: 이후 ``structured_data``.
    :yield: 변경 dict.
    """
    old_items = _items_of(old_sd)
    new_items = _items_of(new_sd)

    if _all_have_uid(old_items) and _all_have_uid(new_items):
        yield from _diff_items_by_uid(old_items, new_items)
        return

    common = min(len(old_items), len(new_items))
    for index in range(common):
        yield from _diff_item_pair(index, old_items[index], new_items[index])

    for index in range(common, len(new_items)):
        yield _change(f"items.{index}", None, _item_name(new_items[index]) or "(이름 없음)", op="add")
    for index in range(common, len(old_items)):
        yield _change(f"items.{index}", _item_name(old_items[index]) or "(이름 없음)", None, op="remove")


def _all_have_uid(items: list[dict[str, Any]]) -> bool:
    """목록의 모든 품목이 uid 를 갖고 있는지(빈 목록은 참).

    :param items: 품목 목록.
    :return: 전부 uid 를 가지면 ``True``.
    """
    return all(item_uid_of(item) for item in items)


def diff_structured(
    old_sd: Any,
    new_sd: Any,
    *,
    max_changes: int = MAX_CHANGES,
) -> DiffResult:
    """저장 전후 ``structured_data`` 에서 감사 대상 변경만 뽑는다.

    화이트리스트 경로만 읽으므로 비용은 ``O(경로 수 + 품목 수 × 필드 수)`` 이고, 문서 크기와
    무관하다. 반환 목록은 항상 결정적 순서다(스칼라 = :data:`SCALAR_PATHS` 순서, 그 뒤 품목).

    :param old_sd: 저장 전 ``structured_data``(dict 아니면 빈 문서로 본다).
    :param new_sd: 저장 후 ``structured_data``.
    :param max_changes: 목록 상한. 초과분은 개수로만 남는다(무성 절단 금지).
    :return: :class:`DiffResult`.
    """
    old_doc = old_sd if isinstance(old_sd, dict) else {}
    new_doc = new_sd if isinstance(new_sd, dict) else {}

    collected: list[dict[str, Any]] = []
    for path in SCALAR_PATHS:
        numeric = _is_numeric_path(path)
        before = _normalize(_get_path(old_doc, path), numeric=numeric)
        after = _normalize(_get_path(new_doc, path), numeric=numeric)
        if before == after:
            continue
        if _is_unset(before, numeric=numeric) and _is_unset(after, numeric=numeric):
            continue  # 미지정 ↔ 기본값(0·False·빈 목록)은 변경이 아니다.
        collected.append(_change(path, before, after))

    collected.extend(_diff_site_extra(old_doc, new_doc))
    collected.extend(_diff_items(old_doc, new_doc))

    total = len(collected)
    if max_changes >= 0 and total > max_changes:
        return DiffResult(collected[:max_changes], total, total - max_changes)
    return DiffResult(collected, total, 0)
