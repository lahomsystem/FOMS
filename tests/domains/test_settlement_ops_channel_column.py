"""NAVER-SETTLE v1.1 T13 — 실무 탭 "네이버 정산" 컬럼의 **백엔드** 계약.

이 파일이 red 로 잡아야 하는 것:

1. **N+1** — 주문 수만큼 정산 표를 다시 묻는 구현. 실무 탭은 모집단 전량(운영 1,978건)을
   도는 hot path 라, 행마다 한 번씩만 물어도 화면이 그 자리에서 죽는다. 컬럼이 붙어도
   쿼리는 **정확히 1회만** 늘어야 한다.
2. **판정 뒤집힘** — 한 주문에 정산 행이 여럿 붙는다(상품주문 단위 + 취소·환급 행).
   "완료 행이 하나라도 있으면 완료"라는 우선순위가 깨지면 이미 돈이 들어온 건이
   대기로 보인다 — 실무자가 없는 미수를 쫓는다.
3. **날짜 뒤집힘** — 완료는 **가장 최근** 완료일, 대기는 **가장 이른** 예정일이다. 서로
   바뀌면 분할 정산 건에서 늘 틀린 날짜가 뜬다.
4. **부호 소실** — 취소·환급 행은 음수로 들어온다. 절댓값으로 더하면 환불된 건이 정산된
   것처럼 보인다(v1 워터폴 부호 사고와 같은 실패형).
5. **권한 누출** — 행 API 게이트(정산 대시보드)는 CS·영업까지 열려 있다. 채널 정산은
   회계 전용이라 **서버가 키 자체를 만들지 않아야** 한다. 값을 None 으로 실어 보내고
   화면에서 감추면 개발자 도구로 그대로 보인다.
6. **어휘 누출** — 백엔드는 상태 **코드**와 날짜만 낸다. 한글 라벨을 서버가 정하면 실무 탭
   금칙어("예정"·"수수료")가 API 응답을 타고 화면에 들어온다.

--------------------------------------------------------------------------
W2-B(프론트) 가 이 파일에 **덧붙일** 계약 — 아직 없다
--------------------------------------------------------------------------
아래는 `static/js/settlement/operations.js` 와
`templates/cs/partials/settlement_operations_body.html` 를 소유한 W2-B 의 몫이다.
백엔드 담당(W1-C)은 그 두 파일을 열지 않았으므로 여기서도 쓰지 않았다:

* ``operations.js`` 소스 계약 — 12번째 칸 렌더가 ``ctx.showChannelCol`` 게이트 뒤에 있고,
  그 값이 **행 데이터가 아니라** 서버 렌더 표식(``data-settlement-ops-channel-col``)에서
  온다(``<th>`` 수와 ``<td>`` 수가 같은 신호를 따라야 두 벌이 안 갈린다).
* ``csvHeaders(ctx)`` 와 ``csvRow(ctx, row)`` 의 칸 수가 같은 조건에서 같다.
* 개명 계약 — ``templates/`` + ``static/js/settlement/`` 전역에 "정산상태" 문자열 0건.
* 금칙어 — 컬럼 문구·CSV 헤더에 "예정"·"수수료" 0건(기존 목업 스캔이 자동으로 잡는다).
* 배지 3클래스(``.s-ch-ops-nv-done``/``-wait``/``-none``)가 ``settlement-channel.css``
  에서 온다(W2-A 선행 커밋).

테스트 데이터 규율은 `test_settlement_rows_api` 와 같다 — 실제 Order·링크·정산 행을 만든다.
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

from sqlalchemy import event

from db import db_session, engine
from foms.services.settlement_rows import (
    NAVER_SETTLE_PENDING,
    NAVER_SETTLE_SETTLED,
    NAVER_SETTLE_UNMATCHED,
    _load_rows,
    _naver_settle_map,
    list_settlement_rows,
)
from models import ExternalOrderLink, NaverSettleCase

# --- 권한 매트릭스·시드 SSOT 재사용(복제 금지) ---------------------------------
from tests.domains.test_auth_finance import _login, _make_user  # noqa: E402
from tests.domains.test_settlement_aggregation import _money, _seed_order  # noqa: E402

ROWS_URL = "/api/settlement/rows"

#: 채널 정산 게이트를 통과하는 actor / 행 API 는 열리지만 채널 정산은 못 보는 actor.
_CHANNEL_ALLOWED_ACTOR = ("ADMIN", None)
_CHANNEL_DENIED_ACTOR = ("STAFF", "CS")

#: 백엔드가 낼 수 있는 상태 코드 전량. 한글이 섞이면 화면 어휘 제약이 서버로 새어 나온 것이다.
_STATUS_CODES = {NAVER_SETTLE_SETTLED, NAVER_SETTLE_PENDING, NAVER_SETTLE_UNMATCHED}

_TODAY = datetime.date(2026, 9, 1)
_seq = 0


# ==========================================================================
# 시드 헬퍼
# ==========================================================================
def _seed_naver_order(**kwargs):
    """네이버 채널 링크가 붙은 모집단 주문 1건.

    `_channel_map` 이 채널을 `ExternalOrderLink` 에서 읽으므로 링크가 없으면 채널이
    "일반" 이 되고 컬럼 판정 자체가 성립하지 않는다.

    Args:
        **kwargs: `_seed_order` 에 그대로 넘긴다.

    Returns:
        생성된 Order.
    """
    global _seq
    _seq += 1
    kwargs.setdefault("completion", "2026-08-10")
    kwargs.setdefault("sd", _money(items_total=1_000_000, deposit=0))
    order = _seed_order(**kwargs)
    db_session.add(
        ExternalOrderLink(
            channel="NAVER",
            external_id=f"2026090100{_seq:04d}",
            order_id=order.id,
            external_order_no=f"20260901{_seq:04d}",
            sync_status="LINKED",
            relation="NEW",
        )
    )
    db_session.commit()
    return order


def _seed_case(order_id: int, *, expect=None, complete=None,
               amount: int | None = 1_000_000, **kwargs) -> NaverSettleCase:
    """주문에 붙은 건별 정산 1행.

    Args:
        order_id: `foms_order_id` 소프트 참조 값.
        expect: 정산 예정일(date 또는 None).
        complete: 정산 완료일(date 또는 None).
        amount: `settle_expect_amount`(부호 그대로 저장한다). None 이면 NULL.
        **kwargs: 나머지 컬럼 덮어쓰기.

    Returns:
        생성된 NaverSettleCase(아직 commit 전).
    """
    global _seq
    _seq += 1
    values = {
        "channel": "NAVER",
        "search_date": expect or complete or _TODAY,
        "period_type": "SETTLE_CASEBYCASE_SETTLE_SCHEDULE_DATE",
        "settle_expect_date": expect,
        "settle_complete_date": complete,
        "product_order_id": f"20260901{_seq:05d}",
        "product_order_type": "PROD_ORDER",
        "settle_type": "NORMAL_SETTLE_ORIGINAL",
        "settle_expect_amount": None if amount is None else Decimal(amount),
        "foms_order_id": order_id,
        "match_status": "MATCHED",
        "raw_snapshot": {"productOrderId": f"20260901{_seq:05d}"},
        "synced_at": datetime.datetime(2026, 9, 1, 0, 0),
    }
    values.update(kwargs)
    row = NaverSettleCase(**values)
    db_session.add(row)
    db_session.commit()
    return row


def _count_queries(fn):
    """`fn` 실행 중 실제로 나간 SQL 문 수를 센다(ORM lazy load 포함)."""
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def _cell_by_order(rows: list[dict], order_id: int) -> dict | None:
    """행 목록에서 특정 주문의 `naver_settlement` 값을 꺼낸다."""
    row = next(r for r in rows if r["order_id"] == order_id)
    return row["naver_settlement"]


def _rows(**kwargs) -> list[dict]:
    """컬럼을 포함한 행 전량(서비스 계층 직접 호출)."""
    return list_settlement_rows(
        db_session(), include_naver_settlement=True, **kwargs
    )["rows"]


# ==========================================================================
# 1. N+1 금지 — 쿼리는 정확히 1회만 늘어난다
# ==========================================================================
def test_naver_settle_map_issues_exactly_one_query(app):
    """주문이 몇 건이든 정산 역조회는 **쿼리 1회**다(group by).

    행마다 묻는 구현은 시드 3건에서도 3회가 되어 여기서 red 가 된다 — 운영 1,978건에서
    처음 발견하면 이미 화면이 죽은 뒤다.
    """
    orders = [_seed_naver_order() for _ in range(3)]
    for order in orders:
        _seed_case(order.id, expect=datetime.date(2026, 9, 5))
    ids = [order.id for order in orders]

    mapping, queries = _count_queries(lambda: _naver_settle_map(db_session(), ids))

    assert queries == 1, f"정산 역조회가 {queries}회 나갔다 — group by 1회여야 한다"
    assert set(mapping) == set(ids)


def test_naver_settle_map_asks_nothing_when_the_population_is_empty(app):
    """모집단이 비면 **쿼리를 아예 걸지 않는다**(빈 IN 절로 DB 를 깨우지 않는다)."""
    mapping, queries = _count_queries(lambda: _naver_settle_map(db_session(), []))

    assert mapping == {}
    assert queries == 0, f"빈 모집단인데 쿼리가 {queries}회 나갔다"


def test_loading_rows_costs_at_most_one_extra_query(app):
    """컬럼을 붙여도 모집단 로드 쿼리는 **+1 이하**다(§8.1 T13 완료기준 ⑥).

    기존: 채널 링크 1 + 주문 1 = 2회. 컬럼 포함: + 정산 역조회 1 = 3회.
    """
    for _ in range(3):
        order = _seed_naver_order()
        _seed_case(order.id, expect=datetime.date(2026, 9, 5))

    _, without = _count_queries(lambda: _load_rows(db_session(), _TODAY))
    _, with_column = _count_queries(
        lambda: _load_rows(db_session(), _TODAY, include_naver_settlement=True)
    )

    assert without == 2, f"기준 쿼리 수가 바뀌었다: {without}"
    assert with_column - without <= 1, (
        f"컬럼 때문에 쿼리가 {with_column - without}회 늘었다 — 1회를 넘으면 N+1 이다"
    )


# ==========================================================================
# 2. 4상태 판정 매트릭스 — 실제 행을 시드해 판정한다
# ==========================================================================
def test_state_is_settled_when_any_case_carries_a_complete_date(app):
    """완료일이 있는 행이 **하나라도** 있으면 정산완료다."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5))
    _seed_case(order.id, expect=datetime.date(2026, 9, 6),
               complete=datetime.date(2026, 9, 7))

    cell = _cell_by_order(_rows(), order.id)

    assert cell["status"] == NAVER_SETTLE_SETTLED
    assert cell["settle_complete_date"] == "2026-09-07"


def test_state_is_pending_when_no_case_carries_a_complete_date(app):
    """완료일이 전부 없으면 대기다(예정일만 있는 상태)."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5))

    cell = _cell_by_order(_rows(), order.id)

    assert cell["status"] == NAVER_SETTLE_PENDING
    assert cell["settle_complete_date"] is None
    assert cell["settle_expect_date"] == "2026-09-05"


def test_state_is_unmatched_when_a_naver_order_has_no_case_rows(app):
    """네이버 주문인데 붙은 정산 행이 0건이면 **미매칭**이다.

    이 상태를 None(해당없음)으로 뭉개면 "네이버 건인데 정산이 안 잡혔다"는 사실이
    화면에서 사라진다 — 그게 바로 회계가 찾아야 하는 행이다.
    """
    order = _seed_naver_order()

    cell = _cell_by_order(_rows(), order.id)

    assert cell["status"] == NAVER_SETTLE_UNMATCHED
    assert cell["settle_expect_date"] is None
    assert cell["settle_complete_date"] is None


def test_non_naver_order_has_no_state_at_all(app):
    """채널이 네이버가 아니면 값 자체가 None 이다(화면은 '—').

    미매칭과 **구분되어야 한다** — 일반 주문은 애초에 네이버 정산 대상이 아니다.
    """
    order = _seed_order(completion="2026-08-10",
                        sd=_money(items_total=1_000_000, deposit=0))

    cell = _cell_by_order(_rows(), order.id)

    assert cell is None, f"비네이버 주문에 상태가 붙었다: {cell}"


# ==========================================================================
# 3. 날짜 선택 — 완료는 최근, 대기는 이른 날
# ==========================================================================
def test_settled_date_is_the_latest_complete_date(app):
    """분할 정산에서 완료일은 **가장 최근** 것이다(마지막으로 돈이 들어온 날)."""
    order = _seed_naver_order()
    _seed_case(order.id, complete=datetime.date(2026, 8, 20))
    _seed_case(order.id, complete=datetime.date(2026, 9, 3))
    _seed_case(order.id, complete=datetime.date(2026, 8, 28))

    cell = _cell_by_order(_rows(), order.id)

    assert cell["settle_complete_date"] == "2026-09-03"


def test_pending_date_is_the_earliest_expect_date(app):
    """대기 예정일은 **가장 이른** 것이다(다음에 들어올 돈)."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 20))
    _seed_case(order.id, expect=datetime.date(2026, 9, 4))
    _seed_case(order.id, expect=datetime.date(2026, 9, 11))

    cell = _cell_by_order(_rows(), order.id)

    assert cell["settle_expect_date"] == "2026-09-04"


def test_pending_survives_when_the_channel_sent_no_dates_yet(app):
    """행은 붙었는데 날짜가 아직 하나도 없으면 **대기 + 날짜 None** 이다.

    미매칭으로 떨어뜨리면 "정산 행이 붙었다"는 사실이 지워진다 — 붙었지만 날짜를 아직
    못 받은 것과 아예 안 붙은 것은 회계가 해야 할 일이 다르다.
    """
    order = _seed_naver_order()
    _seed_case(order.id, expect=None, complete=None)

    cell = _cell_by_order(_rows(), order.id)

    assert cell["status"] == NAVER_SETTLE_PENDING
    assert cell["settle_expect_date"] is None
    assert cell["settle_complete_date"] is None


# ==========================================================================
# 4. 금액 — 원값 그대로 더한다(재계산 금지·부호 보존)
# ==========================================================================
def test_amount_preserves_the_original_sign_across_rows(app):
    """취소·환급 음수 행이 그대로 상계된다(절댓값 합산 금지).

    v1 워터폴 부호 사고와 같은 실패형이다 — 절댓값으로 더하면 환불된 건이 정산 금액이
    가장 큰 건으로 올라온다.
    """
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5), amount=1_000_000)
    _seed_case(order.id, expect=datetime.date(2026, 9, 6), amount=-300_000)

    cell = _cell_by_order(_rows(), order.id)

    assert cell["amount"] == 700_000, "부호가 소실됐다 — 절댓값으로 더했다"


def test_amount_is_none_when_the_channel_sent_no_amount(app):
    """금액이 전부 NULL 이면 0 이 아니라 None 이다(금액 미상 ≠ 0원)."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5), amount=None)

    cell = _cell_by_order(_rows(), order.id)

    assert cell["amount"] is None


def test_case_rows_of_other_orders_never_leak_into_a_row(app):
    """다른 주문에 붙은 정산 행이 옆 주문 칸에 섞이지 않는다(group by 키 오류 방지)."""
    settled = _seed_naver_order()
    pending = _seed_naver_order()
    _seed_case(settled.id, complete=datetime.date(2026, 9, 3), amount=500_000)
    _seed_case(pending.id, expect=datetime.date(2026, 9, 9), amount=800_000)

    rows = _rows()

    assert _cell_by_order(rows, settled.id)["status"] == NAVER_SETTLE_SETTLED
    assert _cell_by_order(rows, settled.id)["amount"] == 500_000
    assert _cell_by_order(rows, pending.id)["status"] == NAVER_SETTLE_PENDING
    assert _cell_by_order(rows, pending.id)["amount"] == 800_000


# ==========================================================================
# 5. 권한 — 키 부재가 계약이다(§6)
# ==========================================================================
def test_denied_actor_gets_no_key_even_when_settlement_rows_exist(client, app):
    """STAFF+CS 응답 행에는 `naver_settlement` 키가 **없고** 플래그가 False 다.

    이 actor 는 행 API 자체는 200 이다(정산 대시보드 권한 보유). 그래서 "403 이니까
    안전하다"가 성립하지 않는다 — 응답 본문에서 키를 빼는 것이 유일한 방어다.
    """
    order = _seed_naver_order()
    _seed_case(order.id, complete=datetime.date(2026, 9, 3), amount=1_234_000)
    role, team = _CHANNEL_DENIED_ACTOR
    _login(client, _make_user(role=role, team=team))

    response = client.get(ROWS_URL)
    body = response.get_json()

    assert response.status_code == 200
    assert body["data"]["channel_settlement_visible"] is False
    assert all("naver_settlement" not in row for row in body["data"]["rows"]), (
        "채널 정산 권한이 없는 actor 의 행에 네이버 정산 키가 실렸다"
    )
    assert "1234000" not in json.dumps(body, ensure_ascii=False), "금액이 응답에 샜다"


def test_allowed_actor_gets_the_key_on_every_row(client, app):
    """회계 권한자는 **모든 행**에 키를 받는다(비네이버 행은 값이 None).

    일부 행에만 키가 있으면 화면이 `<td>` 를 건너뛰어 표가 한 칸씩 밀린다.
    """
    _seed_naver_order()
    _seed_order(completion="2026-08-10", sd=_money(items_total=1_000_000, deposit=0))
    role, team = _CHANNEL_ALLOWED_ACTOR
    _login(client, _make_user(role=role, team=team))

    body = client.get(ROWS_URL).get_json()

    assert body["data"]["channel_settlement_visible"] is True
    assert all("naver_settlement" in row for row in body["data"]["rows"])


# ==========================================================================
# 6. 어휘 — 백엔드는 코드와 날짜만 낸다
# ==========================================================================
def test_backend_emits_status_codes_never_korean_labels(app):
    """상태는 ASCII 코드 3종뿐이다 — 서버가 한글 라벨을 정하지 않는다.

    실무 탭은 "예정"·"수수료" 가 금칙어다(목업 잔재 스캔). 서버가 라벨을 만들면 그
    문자열이 API 응답을 타고 화면에 들어와 소스 스캔을 우회한다.
    """
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5))
    unmatched = _seed_naver_order()
    settled = _seed_naver_order()
    _seed_case(settled.id, complete=datetime.date(2026, 9, 3))

    cells = [
        cell for cell in (row["naver_settlement"] for row in _rows())
        if cell is not None
    ]

    assert {cell["status"] for cell in cells} <= _STATUS_CODES
    assert len(cells) >= 3, "상태 3종이 모두 시드되지 않았다"
    assert unmatched.id  # 미매칭 시드가 실제로 모집단에 있다
    serialized = json.dumps(cells, ensure_ascii=False)
    assert "예정" not in serialized and "수수료" not in serialized, (
        f"백엔드 값에 화면 금칙어가 들어 있다: {serialized}"
    )


def test_dates_are_iso_strings_not_date_objects(app):
    """날짜는 ISO 문자열로만 직렬화한다(§0) — date 객체는 jsonify 에서 RFC 형식이 된다."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5),
               complete=datetime.date(2026, 9, 7))

    cell = _cell_by_order(_rows(), order.id)

    assert cell["settle_expect_date"] == "2026-09-05"
    assert cell["settle_complete_date"] == "2026-09-07"
    assert isinstance(cell["settle_expect_date"], str)


def test_cell_shape_is_exactly_the_agreed_field_set(app):
    """칸 dict 의 키 집합이 계약과 정확히 일치한다(추가·누락 모두 red)."""
    order = _seed_naver_order()
    _seed_case(order.id, expect=datetime.date(2026, 9, 5))

    cell = _cell_by_order(_rows(), order.id)

    assert set(cell) == {
        "status", "settle_expect_date", "settle_complete_date", "amount",
    }, f"칸 키가 계약과 다르다: {sorted(cell)}"
