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
    "SENSITIVE_ITEM_OPS",
    "SENSITIVE_ITEM_TEMPLATE",
    "SENSITIVE_PATH_TEMPLATES",
    "DiffResult",
    "diff_structured",
]

#: 감사 대상 스칼라 경로(2026-08-11 staging 주문 3,412건 키 분포 조사 기반).
#: 여기 없는 경로는 기록하지 않는다 — 파생/캐시 값(``totals`` 재계산 결과 제외 대상 아님에
#: 주의: totals 는 금액이라 포함한다)과 별도 원장이 있는 값(``shipment.as_log`` = AS 타임라인,
#: ``payment.*_confirmed*`` = ``PAYMENT_CONFIRMED`` action, 도면 = ``drawing_revisions``)은 뺀다.
SCALAR_PATHS: tuple[str, ...] = (
    # --- 일정 ---
    "schedule.measurement.date",
    "schedule.measurement.time",
    "schedule.construction.date",
    "schedule.construction.time",
    "schedule.as_visit.date",
    "schedule.as_visit.time",
    # --- 당사자 ---
    "parties.customer.name",
    "parties.customer.phone",
    "parties.orderer.name",
    "parties.orderer.phone",
    "parties.manager.name",
    # --- 현장 ---
    "site.address_full",
    "site.address_detail",
    # --- 단계/플래그/배정 ---
    "workflow.stage",
    "flags.urgent",
    "flags.urgent_reason",
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
    # --- 출고/시공 ---
    "shipment.sales_delivery",
    "shipment.construction_time",
    "shipment.construction_workers",
    "shipment.trip",
    "shipment.as_billing",
    "shipment.as_pending",
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

#: 변경 사유를 물어야 하는 경로(ORDER-REASON-00). 값은 **경로 템플릿**이라
#: ``path_template_of`` 로 정규화한 뒤 대조한다(품목 번호와 무관하게 판정된다).
#:
#: 고르는 기준은 "분쟁이 실제로 나는 축" 하나다 — 금액·일정·단계. 전 경로에 사유를 물으면
#: 직원이 귀찮아서 아무 값이나 고르고, 그 순간 기록의 가치가 0 이 된다(사용자 결정 2026-08-13).
#:
#: **``totals.*`` 는 일부러 뺐다** — 전부 서버 파생값이다(``structured_form_projection`` 이 매
#: 저장마다 품목 price·payment 입력에서 재계산한다). 넣으면 저장된 totals 가 낡은 주문에서
#: 전화번호만 고친 저장이 "금액 변경"으로 판정돼 사유를 묻는다(2026-08-13 실측으로 확인).
#: 파생값은 그 값을 만든 **입력 경로**가 대신 대표한다.
SENSITIVE_PATH_TEMPLATES: frozenset[str] = frozenset({
    # --- 일정 ---
    "schedule.measurement.date",
    "schedule.measurement.time",
    "schedule.construction.date",
    "schedule.construction.time",
    "schedule.as_visit.date",
    "schedule.as_visit.time",
    "items.*.measurement_date",
    "items.*.construction_date",
    # --- 단계/취소 ---
    "workflow.stage",
})

#: 금액 **입력** 경로. 사유 판정은 여기만 금액 임계(잔돈 변경 제외)를 함께 본다 —
#: 목록 자체는 :data:`SENSITIVE_PATH_TEMPLATES` 와 분리해 둔다(판정 규칙이 다르다).
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

_EMPTY_TOKENS = frozenset({"", "none", "null", "-"})
_VALUE_LIMIT = 120


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
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(value)
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
        "before": _clip(before),
        "after": _clip(after),
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
        if before != after:
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
        if before != after:
            collected.append(_change(path, before, after))

    collected.extend(_diff_items(old_doc, new_doc))

    total = len(collected)
    if max_changes >= 0 and total > max_changes:
        return DiffResult(collected[:max_changes], total, total - max_changes)
    return DiffResult(collected, total, 0)
