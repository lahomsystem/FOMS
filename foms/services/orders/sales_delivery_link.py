"""AS 영업 전달 ↔ 영업 실측 일정 배정 링크 + 기준일 드리프트 판정 순수 서비스.

AS 대시보드 영업/택배 탭의 전달 건을 "영업담당의 실측 방문 일정"에 배정한 사실을
기록하고, 그 실측 주문의 실측일이 나중에 바뀌었는지(드리프트) 판정한다.
전달 수단(영업 직접 전달 / 택배)과 전달 완료 여부도 이 모듈이 SSOT 로 다룬다.

스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md (§2, §3).

**`schedule.as_visit.schedule_link`(`as_schedule_link.py`) 와 별개 축이다.** 그쪽은
"AS 기사 방문일을 남의 시공일에 맞춤"이고, 이쪽은 "전달 건을 남의 실측일에 태움"이다.
규율(순수 함수)만 같고 경로·스키마·상태·액션이 다르므로 코드를 공유하지 않는다.

이 모듈은 **순수 함수만** 담는다 — Flask·DB 세션·`app`·`models` 임포트 금지.
`structured_data` dict 를 인자로 받아 읽거나 그 자리에서 변형(mutate)할 뿐이다.
`copy.deepcopy` / `flag_modified` 는 호출자(API 커맨드 파이프라인)의 책임이다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from foms.services.datetime_kst import now_utc_naive

LINK_PATH: tuple[str, str] = ("shipment", "sales_delivery_link")
METHOD_KEY = "sales_delivery_method"
PARCEL_KEY = "sales_delivery_parcel"

REF_KIND = "measurement"
SOURCE_MODAL = "as_sales_delivery_modal"

METHOD_SALES = "sales"
METHOD_PARCEL = "parcel"
METHODS = (METHOD_SALES, METHOD_PARCEL)

STATUS_ASSIGNED = "assigned"
STATUS_DELIVERED = "delivered"

_DATE_PREFIX_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def _norm_date(value: Any) -> Any:
    """날짜 입력을 'YYYY-MM-DD' 문자열로 정규화한다.

    `date`/`datetime` 객체, 느슨한 구분자 문자열('2026/9/5'), 시각이 붙은 문자열
    ('2026-09-05 14:30')을 모두 앞 10자 형태로 맞춘다. 해석 불가한 문자열은
    원본 그대로 돌려준다(판정부가 "다름"으로 취급하도록).

    Args:
        value: 날짜 입력(str/date/datetime/None 허용).

    Returns:
        'YYYY-MM-DD' 문자열, 빈 값이면 None, 해석 실패 시 원본 값.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return None
    m = _DATE_PREFIX_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    return s


def _shipment(sd: dict, *, create: bool) -> dict | None:
    """LINK_PATH 상위 컨테이너(`shipment`)를 반환한다.

    Args:
        sd: 주문 structured_data.
        create: True 면 `shipment` 가 없거나 dict 가 아닐 때 새로 만들어 꽂는다.
            False 면 없을 때 None 을 반환한다(비파괴 읽기).

    Returns:
        `shipment` dict, 또는 (create=False 이고 없으면) None.
    """
    node = sd.get(LINK_PATH[0])
    if isinstance(node, dict):
        return node
    if not create:
        return None
    node = {}
    sd[LINK_PATH[0]] = node
    return node


def read_link(sd: dict | None) -> dict | None:
    """현재 sales_delivery_link 를 읽는다.

    Args:
        sd: 주문 structured_data(None 허용).

    Returns:
        링크 dict(원본 참조, 복사 아님). 없거나 dict 가 아니면 None.
    """
    container = _shipment(sd or {}, create=False)
    if container is None:
        return None
    link = container.get(LINK_PATH[-1])
    return link if isinstance(link, dict) else None


def write_link(
    sd: dict,
    *,
    ref_order_id: int,
    ref_date: Any,
    ref_manager: str | None,
    actor_user_id: int | None,
    actor_name: str,
    source: str = SOURCE_MODAL,
    now: datetime | None = None,
) -> dict:
    """전달 건을 실측 주문에 배정한다(재배정도 이 함수 — ack 는 리셋된다).

    Args:
        sd: 주문 structured_data(제자리에서 변형된다).
        ref_order_id: 기준 실측 주문 id.
        ref_date: 배정 시점 실측일 D0(서버가 재조회한 값).
        ref_manager: 배정 시점 실측 담당자 이름 스냅샷(없으면 None).
        actor_user_id: 배정한 사용자 id(없으면 None).
        actor_name: 배정한 사용자 표시 이름.
        source: 배정 출처(기본 `SOURCE_MODAL`).
        now: 기록 시각(UTC naive). None 이면 `now_utc_naive()`.

    Returns:
        생성된 링크 dict(스펙 §2.1 형태, sd 에 저장된 것과 같은 참조).
    """
    container = _shipment(sd, create=True)
    stamp = now or now_utc_naive()
    link = {
        "ref_order_id": ref_order_id,
        "ref_kind": REF_KIND,
        "ref_date": _norm_date(ref_date),
        "ref_manager": ref_manager,
        "assigned_at": stamp.isoformat(),
        "assigned_by_user_id": actor_user_id,
        "assigned_by": actor_name,
        "source": source,
        "ack_ref_date": None,
        "status": STATUS_ASSIGNED,
        "delivered_at": None,
        "delivered_by": None,
    }
    container[LINK_PATH[-1]] = link
    return link


def clear_link(sd: dict) -> bool:
    """배정을 해제한다(링크 키 자체를 제거).

    Args:
        sd: 주문 structured_data.

    Returns:
        실제로 지웠으면 True, 애초에 링크가 없었으면 False(멱등 판정용).
    """
    container = _shipment(sd, create=False)
    if container is None or LINK_PATH[-1] not in container:
        return False
    del container[LINK_PATH[-1]]
    return True


def ack_link(sd: dict, ref_current_date: Any) -> bool:
    """실측일 변경 경고를 "확인" 처리한다 — ack_ref_date 를 현재 실측일로 기록.

    이후 실측일이 또 바뀌면 저장된 값이 더 이상 현재 실측일과 일치하지 않으므로
    `evaluate_drift` 가 자동으로 `acked` 억제를 풀고 `ref_moved` 로 되돌린다.

    Args:
        sd: 주문 structured_data.
        ref_current_date: 확인을 누른 시점의 기준 주문 현재 실측일(Ds).

    Returns:
        링크가 있어 갱신했으면 True, 링크가 없으면 False.
    """
    link = read_link(sd)
    if link is None:
        return False
    link["ack_ref_date"] = _norm_date(ref_current_date)
    return True


def mark_delivered(sd: dict, *, at: datetime | None = None, by: str | None = None) -> bool:
    """전달 완료를 기록한다(status → delivered).

    Args:
        sd: 주문 structured_data.
        at: 전달 시각(UTC naive). None 이면 `now_utc_naive()`.
        by: 전달 처리한 사용자 표시 이름.

    Returns:
        링크가 있어 기록했으면 True, 링크가 없으면 False.
    """
    link = read_link(sd)
    if link is None:
        return False
    stamp = at or now_utc_naive()
    link["status"] = STATUS_DELIVERED
    link["delivered_at"] = stamp.isoformat()
    link["delivered_by"] = by
    return True


def unmark_delivered(sd: dict) -> bool:
    """전달 완료를 되돌린다(status → assigned, 전달 흔적 제거).

    Args:
        sd: 주문 structured_data.

    Returns:
        실제로 되돌렸으면 True. 링크가 없거나 애초에 delivered 가 아니면 False.
    """
    link = read_link(sd)
    if link is None or link.get("status") != STATUS_DELIVERED:
        return False
    link["status"] = STATUS_ASSIGNED
    link["delivered_at"] = None
    link["delivered_by"] = None
    return True


def read_method(sd: dict | None) -> str:
    """전달 수단을 읽는다.

    Args:
        sd: 주문 structured_data(None 허용).

    Returns:
        `"sales"` 또는 `"parcel"`. 미기록·알 수 없는 값이면 기본 `"sales"`.
    """
    container = _shipment(sd or {}, create=False)
    if container is None:
        return METHOD_SALES
    value = container.get(METHOD_KEY)
    return value if value in METHODS else METHOD_SALES


def set_method(
    sd: dict,
    method: str,
    *,
    parcel: dict | None = None,
    actor_name: str | None = None,
    now: datetime | None = None,
) -> None:
    """전달 수단을 바꾼다. `parcel` 로 바꾸면 실측 배정 링크도 함께 해제된다.

    택배로 보내는 순간 영업 동선에 태울 이유가 사라지므로, 링크를 남겨두면
    실측 대시보드에 유령 배정이 뜬다 — 그래서 여기서 같이 지운다.

    Args:
        sd: 주문 structured_data(제자리에서 변형된다).
        method: `"sales"` | `"parcel"`.
        parcel: method="parcel" 일 때 택배 정보 `{carrier, tracking_no}`.
        actor_name: 택배 발송 처리자 이름(`sent_by` 로 기록).
        now: 기록 시각(UTC naive). None 이면 `now_utc_naive()`.

    Returns:
        None.

    Raises:
        ValueError: `method` 가 `"sales"`/`"parcel"` 이 아닐 때.
    """
    if method not in METHODS:
        raise ValueError(f"unknown sales delivery method: {method!r}")
    container = _shipment(sd, create=True)
    container[METHOD_KEY] = method
    if method == METHOD_SALES:
        container.pop(PARCEL_KEY, None)
        return
    clear_link(sd)
    stamp = now or now_utc_naive()
    info = dict(parcel or {})
    container[PARCEL_KEY] = {
        "carrier": info.get("carrier"),
        "tracking_no": info.get("tracking_no"),
        "sent_at": stamp.isoformat(),
        "sent_by": actor_name,
    }


def evaluate_drift(sd: dict | None, ref_current_date: Any) -> dict[str, Any]:
    """기준 실측일이 배정 이후 움직였는지 판정한다(스펙 §2.2).

    상태 우선순위(= 아래 구현 순서): `none > ref_gone > (ok|resolved) > acked > ref_moved`.
    `resolved` 는 "한 번 어긋났다가(=ack 흔적이 D0 아닌 날짜로 남아 있다) 실측일이
    원래 D0 로 되돌아온" 경우만이다 — 어긋난 적이 없으면 그냥 `ok` 다.
    `acked` 는 `ack_ref_date` 가 **현재** 실측일과 일치할 때만 유효하다.

    Args:
        sd: 주문 structured_data(None 허용).
        ref_current_date: 기준 실측 주문의 현재 실측일(Ds). 주문이 사라졌거나
            실측일이 지워졌으면 None.

    Returns:
        `{"state", "ref_order_id", "ref_date", "ref_current_date", "ref_manager"}`.
        state ∈ `none|ok|ref_moved|acked|resolved|ref_gone`. 날짜는 정규화된 값.
    """
    ds = _norm_date(ref_current_date)
    link = read_link(sd)
    if link is None:
        return {"state": "none", "ref_order_id": None, "ref_date": None,
                "ref_current_date": ds, "ref_manager": None}
    d0 = _norm_date(link.get("ref_date"))
    ack = _norm_date(link.get("ack_ref_date"))
    return {
        "state": _drift_state(d0=d0, ds=ds, ack=ack),
        "ref_order_id": link.get("ref_order_id"),
        "ref_date": d0,
        "ref_current_date": ds,
        "ref_manager": link.get("ref_manager"),
    }


def _drift_state(*, d0: Any, ds: Any, ack: Any) -> str:
    """`evaluate_drift` 의 상태 결정 규칙만 분리(순서 = 우선순위).

    Args:
        d0: 배정 시점 실측일(정규화됨).
        ds: 현재 실측일(정규화됨, 없으면 None).
        ack: 확인 처리된 실측일(정규화됨, 없으면 None).

    Returns:
        `ok|resolved|acked|ref_moved|ref_gone` 중 하나.
    """
    if ds is None:
        return "ref_gone"
    if ds == d0:
        return "resolved" if ack is not None and ack != d0 else "ok"
    if ack is not None and ack == ds:
        return "acked"
    return "ref_moved"


def derive_display_state(sd: dict | None) -> str:
    """AS 영업/택배 탭 셀에 찍을 표시 상태를 유도한다(읽기 SSOT, 스펙 §2.2).

    Args:
        sd: 주문 structured_data(None 허용).

    Returns:
        `"unassigned"` | `"assigned"` | `"delivered"` | `"parcel"`.
        (`"일정 변경"` 배지는 별도 축이라 `evaluate_drift` 로 얹는다.)
    """
    if read_method(sd) == METHOD_PARCEL:
        return "parcel"
    link = read_link(sd)
    if link is None:
        return "unassigned"
    return "delivered" if link.get("status") == STATUS_DELIVERED else "assigned"
