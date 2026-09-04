"""이미 **끝난 집**은 "붙이면 대상"으로 권하지 않는다 (2026-09-04 운영 신고).

운영 실화면: 띠가 `2026053135109771 · → #5130 김민지 · 수령인명 일치` 를 "붙이면 대상이
되는 집" 으로 권했다. 그 집은 5월 주문 · 6월 배송 완료 · **구매확정(PURCHASE_DECIDED)** 인
동명이인 건이었고, 오늘 실측인 #5130 김민지와는 전화도 주소도 다르다.

원인은 동명이인이 아니라 **제외 축 부재**였다. `find_unlinked_matches` 가 후보에서 빼는
축은 취소·반품 확정(`all_money_back_settled`) 하나뿐이라, 클레임 없이 끝난 집(구매확정)은
"취소가 아니다"라는 이유만으로 살아 있는 후보로 남았다. 9월 1일 소급 백필이 옛 주문을
전량 `created_at` 창 안으로 들여놓으면서(운영 실측: 60일 창 미연결 구매확정 556집), 이름이
겹치는 신규 접수 하나만 들어오면 터지는 구조가 됐다.

여기서 못박는 것:

* 집 형제 **전원**이 종결(:data:`claim_watch.TERMINAL_ORDER_STATUSES`)이면 짚지 않는다.
* **모르는 값은 종결이 아니다** — 키 없음·빈 값·처음 보는 코드는 전부 "살아 있다".
  헛짚기는 사람이 한 번 안 붙이면 끝이고, 잘못 빼면 집이 화면에서 통째로 사라진다.
* 뺀 집은 **말한다.** 카운터도 문구도 취소·반품과 **따로** 간다 — 합치면 화면이 구매확정
  집을 두고 "취소·반품 확정"이라고 거짓 라벨을 말한다.
* 뺀 집이 짚던 주문은 `foreign`("네이버 주문이 아닙니다")이 아니라 **`unknown`(모름)** 으로
  되돌아온다. 축은 실제로 맞았고 원본도 있다 — foreign 은 없는 사실이다.
"""

from __future__ import annotations

import pathlib

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.integrations.naver_commerce.bulk_dispatch import (
    build_preview,
    find_unlinked_matches,
)
from models import ExternalOrderLink

from tests.services.integrations.test_naver_bulk_dispatch_select import (  # noqa: F401
    _fresh_db,
)
from tests.services.integrations.test_naver_bulk_dispatch_unlinked import (  # noqa: F401
    MEASUREMENT_PATH,
    TRIAGE_PATH,
    _loose,
    _order_measured_today,
    _set_coverage,
    today,
)
from tests.services.integrations.test_naver_workbench import (  # noqa: F401
    _login,
    _uid,
    workbench_on,
)

SOURCE = pathlib.Path("foms/services/integrations/naver_commerce/bulk_dispatch.py")


def _set_order_status(order_no: str, statuses: list[str], *, flat: bool = False) -> None:
    """그 집 링크들의 ``productOrderStatus`` 를 순서대로 갈아 끼운다.

    Args:
        order_no: 네이버 묶음 주문번호.
        statuses: 링크 수만큼의 상태값. ``""`` 은 **키를 아예 안 넣는다**(옛 수집분 모양).
        flat: 참이면 ``productOrder`` 아래가 아니라 스냅샷 최상위에 넣는다 — 옛 수집분에
            그 모양이 있어 파서가 둘 다 읽어야 한다.
    """
    links = (db_session.query(ExternalOrderLink)
             .filter(ExternalOrderLink.external_order_no == order_no)
             .order_by(ExternalOrderLink.id).all())
    assert len(links) == len(statuses), "픽스처 링크 수와 상태 수가 다르다"
    for link, status in zip(links, statuses):
        snapshot = dict(link.raw_snapshot or {})
        product_order = dict(snapshot.get("productOrder") or {})
        product_order.pop("productOrderStatus", None)
        snapshot.pop("productOrderStatus", None)
        if status:
            if flat:
                snapshot["productOrderStatus"] = status
            else:
                product_order["productOrderStatus"] = status
        snapshot["productOrder"] = product_order
        link.raw_snapshot = snapshot
        flag_modified(link, "raw_snapshot")
    db_session.commit()


# --------------------------------------------------------------------------- #
# 양성 — 빼야 하는 것을 빼는가
# --------------------------------------------------------------------------- #

def test_purchase_decided_household_is_not_recommended(today):
    """구매확정 집은 이름이 같아도 짚지 않는다(운영 신고 재현)."""
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-CLOSED-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED"])

    found = find_unlinked_matches(db_session, on_date=today)

    assert [row for row in found if row["order_no"] == order_no] == []
    assert found.excluded_closed == 1
    assert found.excluded_claims == 0, "취소·반품이 아니다 — 그 카운터가 움직이면 거짓말이다"


def test_closed_exclusion_is_said_out_loud(today):
    """짚을 게 0집인 날에도 **뺐다는 사실**을 실어 보낸다."""
    _set_coverage("2026-01-01")
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-CLOSED-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=2, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED", "PURCHASE_DECIDED"])

    preview = build_preview(db_session, on_date=today)

    assert preview["unlinked"] == 0
    assert preview["unlinked_excluded_closed"] == 1
    assert preview["show"] is True, "뺐다는 말을 하려면 띠가 떠야 한다"


def test_closed_exclusion_has_its_own_sentence(client, workbench_on, today):
    """두 화면이 **취소·반품과 다른 줄**로 말한다."""
    _login(client)
    _set_coverage("2026-01-01")
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-CLOSED-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED"])

    for path in (f"{TRIAGE_PATH}?tab=work", MEASUREMENT_PATH):
        body = client.get(path).get_data(as_text=True)
        assert "이미 끝난 집 1집은 제외했습니다" in body, path
        assert "취소·반품 확정 1집은 제외했습니다" not in body, path
        # 배출구 — 끝난 집을 뒤늦게 붙여야 할 일이 실제로 있다(추가결제·소급 정산).
        assert "워크벤치 붙이기 후보에서 고르세요" in body, path


def test_closed_household_order_returns_as_unknown_not_foreign(today):
    """뺀 집이 짚던 주문은 '모름' 으로 되돌아온다 — '네이버 주문이 아님' 은 거짓이다."""
    _set_coverage("2026-01-01")
    order = _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-CLOSED-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED"])

    preview = build_preview(db_session, on_date=today)

    assert int(order.id) in {row["order_id"] for row in preview["unknown"]}
    assert int(order.id) not in {row["order_id"] for row in preview["foreign"]}


# --------------------------------------------------------------------------- #
# 음성 대조군 — 전부 종결 판정이 발동할 수 있는 집합 안에서 고른다
# --------------------------------------------------------------------------- #

def test_partially_decided_household_is_still_recommended(today):
    """형제 하나라도 살아 있으면 그 집은 남는다(`all` 규칙)."""
    order = _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-MIX-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=3, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED", "PURCHASE_DECIDED", "DELIVERING"])

    found = find_unlinked_matches(db_session, on_date=today)

    mine = [row for row in found if row["order_no"] == order_no]
    assert len(mine) == 1
    assert mine[0]["order_id"] == int(order.id)
    assert found.excluded_closed == 0


def test_household_without_order_status_is_still_recommended(today):
    """상태 키가 아예 없는 옛 수집분은 **모른다** — 종결로 읽지 않는다."""
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-NOSTATUS-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, [""])

    found = find_unlinked_matches(db_session, on_date=today)

    assert [row["order_no"] for row in found].count(order_no) == 1
    assert found.excluded_closed == 0


def test_unknown_order_status_is_not_treated_as_closed(today):
    """처음 보는 코드도 종결이 아니다 — 모르면 살아 있는 쪽으로 기운다."""
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-XYZ-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["NEW_STATUS_XYZ"])

    found = find_unlinked_matches(db_session, on_date=today)

    assert [row["order_no"] for row in found].count(order_no) == 1


def test_delivering_and_payed_households_are_still_recommended(today):
    """띠의 원래 목적(2026-09-01 천화진 건)은 그대로 산다."""
    for status in ("PAYED", "DELIVERING"):
        _order_measured_today(today, customer=f"살아있음{status}", phone=f"010-0000-{_uid()[-4:]}")
    order_alive = _order_measured_today(today, customer="천화진", phone="010-5413-6252")
    order_no = f"N-ALIVE-{_uid()}"
    _loose(order_no, tel="010-5413-6252", count=2)
    _set_order_status(order_no, ["PAYED", "DELIVERING"])

    found = find_unlinked_matches(db_session, on_date=today)

    mine = [row for row in found if row["order_no"] == order_no]
    assert len(mine) == 1
    assert mine[0]["order_id"] == int(order_alive.id)


def test_canceled_household_counts_once_not_twice(today):
    """전부 취소 확정인 집은 **취소 카운터에만** 잡힌다 — 이중 계수 금지."""
    _order_measured_today(today, customer="황인영", phone="010-4321-8779")
    order_no = f"N-CLM-{_uid()}"
    _loose(order_no, tel="010-4321-8779", count=2, claim_status="CANCEL_DONE")
    _set_order_status(order_no, ["CANCELED", "CANCELED"])

    found = find_unlinked_matches(db_session, on_date=today)

    assert found.excluded_claims == 1
    assert found.excluded_closed == 0, "같은 집을 두 줄이 동시에 말하면 화면이 부풀어 오른다"


def test_flat_shaped_snapshot_is_read_too(today):
    """평평한 모양(`snapshot['productOrderStatus']`)도 읽는다 — 옛 행을 놓치지 않는다."""
    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-FLAT-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED"], flat=True)

    found = find_unlinked_matches(db_session, on_date=today)

    assert [row for row in found if row["order_no"] == order_no] == []
    assert found.excluded_closed == 1


# --------------------------------------------------------------------------- #
# 구조 계약 — 축을 지어내지 않고, 조회를 늘리지 않는다
# --------------------------------------------------------------------------- #

def test_closed_axis_reuses_the_terminal_status_ssot():
    """종결 상수를 새로 정의하지 않는다 — `claim_watch` 의 SSOT 를 가져다 쓴다."""
    source = SOURCE.read_text(encoding="utf-8")

    assert "TERMINAL_ORDER_STATUSES" in source
    assert "TERMINAL_ORDER_STATUSES = " not in source, "상수를 두 벌 두면 한쪽만 고쳐진다"
    assert "from foms.services.integrations.naver_commerce.claim_watch import" in source


def test_closed_check_shares_the_claim_query(today):
    """종결 판정이 스냅샷을 **다시 조회하지 않는다**(형제 스냅샷 조회 1회).

    회귀하면 대시보드 렌더에 같은 스냅샷을 두 번 읽는 쿼리가 그대로 붙는다.
    """
    from sqlalchemy import event

    _order_measured_today(today, customer="김민지", phone="010-3754-2973")
    order_no = f"N-Q-{_uid()}"
    _loose(order_no, tel="010-2987-1296", count=1, receiver="김민지")
    _set_order_status(order_no, ["PURCHASE_DECIDED"])

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        if "raw_snapshot" in statement and "external_order_no IN" in statement:
            seen.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        find_unlinked_matches(db_session, on_date=today)
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert len(seen) == 1, f"형제 스냅샷을 {len(seen)}번 읽었다 — 정확히 한 번이어야 한다"
