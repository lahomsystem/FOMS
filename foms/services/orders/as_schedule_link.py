"""AS 일정 매칭 링크 + 기준일 드리프트 판정 순수 서비스.

AS 방문일을 잡을 때 참고한 "기준 주문"(대개 시공일)을 링크로 기록하고,
그 기준 주문의 시공일이 나중에 바뀌었는지(드리프트) 판정한다.

스펙: docs/specs/2026-07-30-as-schedule-link-drift-design.md (§3 스키마, §4 판정표).

이 모듈은 **순수 함수만** 담는다 — Flask·DB 세션·`app` 임포트 금지, `structured_data`
dict 를 인자로 받아 읽거나 그 자리에서 변형(mutate)할 뿐이다. `copy.deepcopy` /
`flag_modified` 는 호출자(API 커맨드 파이프라인)의 책임이며 여기서는 하지 않는다.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

LINK_PATH: tuple[str, str, str] = ("schedule", "as_visit", "schedule_link")
SOURCE_NEARBY = "as_nearby_modal"
SOURCE_SHIPMENT = "shipment_asrec"

_DATE_PREFIX_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def _norm_date(value: Any) -> Any:
    """느슨한 구분자의 날짜 문자열을 'YYYY-MM-DD' 로 정규화. 실패 시 원본 그대로.

    프로젝트 정본 정규화 유틸은 `foms/services/order_date_sync._normalize_date_str`
    이지만, 그 모듈은 `db.py`(Flask `g`, SQLAlchemy 엔진 초기화)를 임포트 체인에
    끌고 온다 — 이 모듈의 "Flask/DB 세션 무의존" 요구와 충돌해 재사용하지 않는다.
    알고리즘만 그대로 옮겨온 로컬 사본이므로, 정본이 바뀌면 이 함수도 맞춰 갱신한다.
    """
    if not value or not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return s
    m = _DATE_PREFIX_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _link_container(sd: dict, *, create: bool) -> dict | None:
    """LINK_PATH 상위 컨테이너(`schedule.as_visit`)를 반환.

    Args:
        sd: 주문 structured_data.
        create: True 면 중간 dict(`schedule`, `as_visit`)가 없거나 dict 가 아닐 때
            새로 만들어 sd 에 꽂아 넣는다. False 면 없을 때 None 을 반환(비파괴 읽기).

    Returns:
        `schedule.as_visit` dict, 또는 (create=False 이고 경로가 없으면) None.
    """
    node = sd
    for key in LINK_PATH[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            if not create:
                return None
            nxt = {}
            node[key] = nxt
        node = nxt
    return node


def read_link(sd: dict) -> dict | None:
    """현재 schedule_link 를 읽는다. 없거나 형식이 dict 가 아니면 None.

    Args:
        sd: 주문 structured_data.

    Returns:
        링크 dict(원본 참조, 복사 아님) 또는 None.
    """
    container = _link_container(sd, create=False)
    if container is None:
        return None
    link = container.get(LINK_PATH[-1])
    return link if isinstance(link, dict) else None


def write_link(
    sd: dict,
    *,
    ref_order_id: int,
    ref_date: str,
    source: str,
    user_id: int | None,
    user_name: str,
    now: datetime,
) -> dict:
    """신규 링크를 생성/덮어쓴다(기존 ack 상태는 초기화). sd 를 제자리에서 변형.

    Args:
        sd: 주문 structured_data.
        ref_order_id: 기준 주문 id.
        ref_date: 매칭 시점 기준 주문 시공일(D0).
        source: `SOURCE_NEARBY` | `SOURCE_SHIPMENT`.
        user_id: 매칭한 사용자 id(없으면 None).
        user_name: 매칭한 사용자 표시 이름.
        now: 호출자가 넘기는 UTC naive datetime(`now_utc_naive()`). 여기서
            `datetime.now()` 를 호출하지 않는다.

    Returns:
        생성된 링크 dict(스펙 §3.1 형태, sd 에 저장된 것과 동일 참조).
    """
    container = _link_container(sd, create=True)
    link = {
        "ref_order_id": ref_order_id,
        "ref_kind": "construction",
        "ref_date": _norm_date(ref_date),
        "linked_at": now.isoformat(),
        "linked_by_user_id": user_id,
        "linked_by": user_name,
        "source": source,
        "ack_ref_date": None,
    }
    container[LINK_PATH[-1]] = link
    return link


def clear_link(sd: dict) -> bool:
    """링크를 삭제한다(키 자체를 제거). 링크가 없었으면 False.

    Args:
        sd: 주문 structured_data.

    Returns:
        실제로 삭제했으면 True, 애초에 링크가 없었으면 False.
    """
    container = _link_container(sd, create=False)
    if container is None or LINK_PATH[-1] not in container:
        return False
    del container[LINK_PATH[-1]]
    return True


def ack_link(sd: dict, ref_date_now: str) -> bool:
    """드리프트 경고를 "무시"한다 — `ack_ref_date` 를 현재 기준일로 기록.

    이후 기준일이 다시 바뀌면(= 새 현재 기준일이 이 값과 달라지면) 저장된
    `ack_ref_date` 는 더 이상 일치하지 않으므로 `evaluate_drift` 가 자동으로
    `acked` 억제를 해제하고 `ref_moved`/`both_moved` 로 되돌린다.

    Args:
        sd: 주문 structured_data.
        ref_date_now: 무시를 누른 시점의 기준 주문 현재 시공일(Ds).

    Returns:
        링크가 있어 갱신했으면 True, 링크가 없으면 False.
    """
    link = read_link(sd)
    if link is None:
        return False
    link["ack_ref_date"] = _norm_date(ref_date_now)
    return True


def relink(sd: dict, ref_date_now: str) -> bool:
    """"재적용" — 링크의 `ref_date` 를 기준 주문의 현재 시공일로 갱신하고 ack 해제.

    Args:
        sd: 주문 structured_data.
        ref_date_now: 재적용 시점의 기준 주문 현재 시공일(새 D0).

    Returns:
        링크가 있어 갱신했으면 True, 링크가 없으면 False.
    """
    link = read_link(sd)
    if link is None:
        return False
    link["ref_date"] = _norm_date(ref_date_now)
    link["ack_ref_date"] = None
    return True


def evaluate_drift(
    link: dict | None,
    *,
    ref_current_date: str | None,
    as_visit_date: str | None,
    ref_missing: bool,
) -> dict[str, Any]:
    """스펙 §4 판정표를 구현한다. link 는 호출자가 `read_link` 로 미리 읽어 전달.

    상태값 우선순위(표에 명시되지 않은 동시-충족 케이스에 대한 이 구현의 결정):
    `ref_gone > none > ok > resolved > acked > ref_moved > both_moved` — `ref_gone` 은
    Ds 자체를 못 믿는 상태라 최우선, `resolved`(사용자가 이미 방문일을 새 기준일에
    맞춤)는 자동 치유 가능한 긍정 신호라 `acked`(단순 경고 숨김)보다 먼저 본다.
    `acked` 는 `ack_ref_date` 가 **현재** Ds 와 일치할 때만 유효 — 이후 Ds 가 다시
    바뀌면 자동으로 `ref_moved`/`both_moved` 로 복귀한다.

    Args:
        link: `read_link(sd)` 결과(없으면 None → 상태 `none`).
        ref_current_date: 기준 주문의 현재 시공일(Ds).
        as_visit_date: 이 AS 건의 현재 방문일(Da, `sd.schedule.as_visit.date`).
        ref_missing: 기준 주문이 삭제됐거나 조회 불가면 True.

    Returns:
        `{"state", "ref_order_id", "ref_date", "ref_current_date", "as_visit_date"}`.
        state ∈ `none|ok|ref_moved|both_moved|resolved|acked|ref_gone`. 날짜 필드는
        전부 정규화된 값(가능한 경우)이다.
    """
    ds = _norm_date(ref_current_date)
    da = _norm_date(as_visit_date)
    if link is None:
        return {"state": "none", "ref_order_id": None, "ref_date": None,
                "ref_current_date": ds, "as_visit_date": da}

    d0 = _norm_date(link.get("ref_date"))
    ack = _norm_date(link.get("ack_ref_date"))
    state = _drift_state(ref_missing=ref_missing, d0=d0, ds=ds, da=da, ack=ack)
    return {
        "state": state,
        "ref_order_id": link.get("ref_order_id"),
        "ref_date": d0,
        "ref_current_date": ds,
        "as_visit_date": da,
    }


def _drift_state(
    *, ref_missing: bool, d0: str | None, ds: str | None, da: str | None, ack: str | None
) -> str:
    """`evaluate_drift` 의 상태 결정 규칙만 분리(≤50줄 유지용, 순서=우선순위)."""
    if ref_missing:
        return "ref_gone"
    if ds == d0:
        return "ok"
    if da is not None and da == ds:
        return "resolved"
    if ack is not None and ack == ds:
        return "acked"
    if da is not None and da == d0:
        return "ref_moved"
    return "both_moved"
