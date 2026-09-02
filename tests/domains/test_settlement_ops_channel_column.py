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
W2-B(프론트) 가 덧붙인 계약 — **§7 이후**(이 파일 끝)
--------------------------------------------------------------------------
`static/js/settlement/operations.js` 와
`templates/cs/partials/settlement_operations_body.html` 를 소유한 W2-B 의 몫이다.
백엔드 담당(W1-C)은 그 두 파일을 열지 않았으므로 여기서 쓰지 않았고, 아래 §7~§9 가 그 자리를
채운다(머리글 순서·게이트별 렌더 대조는 `test_settlement_operations_render.py` 소유):

* ``operations.js`` 소스 계약 — 12번째 칸 렌더가 ``ctx.showChannelCol`` 게이트 뒤에 있고,
  그 값이 **행 데이터가 아니라** 서버 렌더 표식(``data-settlement-ops-channel-col``)에서
  온다(``<th>`` 수와 ``<td>`` 수가 같은 신호를 따라야 두 벌이 안 갈린다).
* ``csvHeaders(ctx)`` 와 ``csvRow(ctx, row)`` 의 칸 수가 같은 조건에서 같다.
* 개명 계약 — ``templates/`` + ``static/js/settlement/`` 전역에 "정산상태" 문자열 0건.
* 금칙어 — 컬럼 문구·CSV 헤더에 "예정"·"수수료" 0건(기존 목업 스캔이 자동으로 잡는다).
* 배지 클래스(``.s-ch-ops-nv`` + ``--done``/``--wait``/``--none``)가
  ``settlement-channel.css`` 에서 온다(W2-A 선행 커밋 — 착수 시점에 아직 없어 §9 는
  `settlement-operations.css` 배선 테스트와 같은 "걸리면 옳아야 한다" 형태다).
  *계약서 §4.3 의 표기(``.s-ch-ops-nv-done`` 단일 하이픈 3종)와 다르다* — Wave 2 착수 시
  W2-A 가 정한 BEM 형(base + `--` modifier, 4종)을 정본으로 쓴다.

테스트 데이터 규율은 `test_settlement_rows_api` 와 같다 — 실제 Order·링크·정산 행을 만든다.
"""

from __future__ import annotations

import datetime
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
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


# ==========================================================================
# 7. (W2-B) 프론트 소스 계약 — 컬럼 게이트는 **서버 렌더 표식** 하나다
#
# 여기부터는 DB 를 쓰지 않는 소스 리터럴 검사다(`tests/domains` 관례). JS 는 서버 렌더에
# 나오지 않아 이쪽으로만 잡을 수 있고, 이 파일이 백엔드 계약과 **같은 자리**에 있어야
# "서버가 키를 만드는 조건"과 "화면이 칸을 그리는 조건"이 갈렸을 때 한눈에 보인다.
# ==========================================================================
_REPO = Path(__file__).resolve().parents[2]

_OPS_JS = "static/js/settlement/operations.js"
_OPS_TEMPLATE = "templates/cs/partials/settlement_operations_body.html"
#: 배지 클래스 소유 파일. W2-A(채널 표면) 소유라 W2-B 는 읽기만 한다.
_CHANNEL_CSS = "static/css/settlement/settlement-channel.css"

#: 서버가 렌더에 심는 표식. `<th>`(템플릿)와 `<td>`(JS)가 **이 하나**를 함께 본다.
_CHANNEL_COL_ATTR = "data-settlement-ops-channel-col"

#: 이 컬럼이 쓰는 클래스 전량(배지 base + 상태 3종 + 날짜 보조). 계약서 §4.3 의 단일 하이픈
#: 표기가 아니라 W2-A 가 실제로 쓰는 BEM 형이 정본이다(파일 머리말 참조). 날짜는 배지 **안쪽**
#: 자식이라 `.s-ch-ops-nv` 의 inline-flex + gap 을 그대로 탄다.
_BADGE_CLASSES = (
    "s-ch-ops-nv",
    "s-ch-ops-nv--done",
    "s-ch-ops-nv--wait",
    "s-ch-ops-nv--none",
    "s-ch-ops-nv-date",
)

#: 실무 탭 금칙어. 목업 잔재 스캔(`test_settlement_operations_render.py`)과 같은 낱말이지만,
#: 여기서는 **이번에 새로 들어온 표면**(컬럼 문구·CSV 헤더)만 좁혀 다시 못 박는다.
_FORBIDDEN_WORDS = ("예정", "수수료")

_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_JS_LINE_COMMENT_RE = re.compile(r"(?m)^\s*//.*$")
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.S)


def _source(rel: str) -> str:
    """저장소 상대 경로 파일 원문. 없으면 사람이 읽는 red 로 죽인다.

    Args:
        rel: 저장소 루트 기준 상대 경로.

    Returns:
        파일 내용.
    """
    path = _REPO / rel
    assert path.exists(), f"산출물이 없다: {rel}"
    return path.read_text(encoding="utf-8", errors="ignore")


def _code(rel: str) -> str:
    """주석을 걷어낸 본문(규칙을 **설명하는 주석**이 위반으로 잡히는 거짓 red 방지).

    Args:
        rel: 저장소 루트 기준 상대 경로.

    Returns:
        Jinja/JS 주석이 제거된 본문.
    """
    text = _JINJA_COMMENT_RE.sub(" ", _source(rel))
    text = _JS_BLOCK_COMMENT_RE.sub(" ", text)
    return _JS_LINE_COMMENT_RE.sub(" ", text)


def _array_literal(js: str, anchor: str) -> str:
    """`anchor` 뒤 첫 `[` 부터 짝이 맞는 `]` 까지의 원문.

    Args:
        js: 검사 대상 소스.
        anchor: 배열 앞에 오는 고정 문자열(예: ``"var CSV_HEADERS ="``).

    Returns:
        대괄호를 포함한 배열 리터럴 원문.
    """
    start = js.index("[", js.index(anchor))
    depth = 0
    for idx in range(start, len(js)):
        char = js[idx]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return js[start:idx + 1]
    raise AssertionError(f"{anchor}: 배열 리터럴이 닫히지 않았다")


def _top_level_items(literal: str) -> int:
    """대괄호 리터럴의 **최상위** 원소 수(중첩 괄호·따옴표 안의 콤마는 세지 않는다).

    Args:
        literal: `[` 로 시작해 `]` 로 끝나는 배열 원문.

    Returns:
        최상위 원소 개수.
    """
    body = literal.strip()[1:-1]
    depth = 0
    quote = ""
    items = 1 if body.strip() else 0
    for char in body:
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            items += 1
    return items - 1 if body.rstrip().endswith(",") else items


def test_column_render_sits_behind_the_server_rendered_flag():
    """12번째 `<td>` 는 `ctx.showChannelCol` 게이트 뒤에서만 그려진다.

    게이트가 없으면 권한 없는 사용자의 표에 `<th>` 없는 `<td>` 가 하나 더 붙어 모든 칸이
    한 칸씩 밀린다(응답에 키가 없어도 `undefined` 칸이 그려진다).
    """
    js = _code(_OPS_JS)

    assert re.search(
        r"if\s*\(\s*ctx\.showChannelCol\s*\)\s*tr\.appendChild\(\s*naverSettleCell\(",
        js,
    ), "12번째 칸 렌더가 ctx.showChannelCol 게이트 뒤에 있지 않다"


def test_the_flag_comes_from_the_server_marker_not_from_row_data():
    """`showChannelCol` 은 **서버 렌더 표식**에서만 온다(행 데이터 판정 금지).

    행 데이터(`row.naver_settlement` 유무)로 판정하면 권한자여도 네이버 행이 0건인
    페이지에서 `<td>` 수가 `<th>` 수보다 적어져 표가 통째로 밀린다.
    """
    js = _code(_OPS_JS)

    assert re.search(
        r"showChannelCol\s*:\s*root\.hasAttribute\(\s*CHANNEL_COL_ATTR\s*\)", js
    ), "showChannelCol 을 루트 속성으로 판정하지 않는다"
    assert re.search(
        r"CHANNEL_COL_ATTR\s*=\s*'" + re.escape(_CHANNEL_COL_ATTR) + r"'", js
    ), f"표식 이름이 {_CHANNEL_COL_ATTR} 가 아니다"
    assert _CHANNEL_COL_ATTR in _code(_OPS_TEMPLATE), (
        "템플릿이 같은 표식을 내지 않는다 — <th> 와 <td> 가 다른 신호를 본다"
    )


def test_the_template_marker_and_the_header_share_one_jinja_gate():
    """표식과 `<th>` 가 **같은 서버 판정** 뒤에 있다(§6 권한 SSOT).

    두 hunk 가 다른 변수를 보면 표식만 있고 머리글이 없는(또는 그 반대) 렌더가 나온다.
    """
    template = _code(_OPS_TEMPLATE)

    gates = re.findall(
        r"\{%\s*if\s+([a-z_]+)\s*%\}[^\n]*(?:"
        + re.escape(_CHANNEL_COL_ATTR)
        + r"|네이버 정산)",
        template,
    )
    assert gates == ["can_view_channel_settlement"] * 2, f"게이트가 하나가 아니다: {gates}"


def test_the_column_never_renders_the_amount():
    """칸 렌더가 `amount` 를 읽지 않는다 — 상태와 날짜만 낸다(§4.2 · 노출 최소화).

    서버는 `amount` 를 함께 내려주지만 그것은 다른 표면(채널 탭)의 값이다. 실무 탭에
    금액이 뜨면 CS·영업이 옆에서 보는 화면에 채널 정산액이 상시 노출된다.
    """
    js = _code(_OPS_JS)

    body = re.search(r"function naverSettleCell\(row\)\s*\{(.*?)\n  \}", js, re.S)
    assert body, "naverSettleCell 을 찾지 못했다"
    assert "amount" not in body.group(1), f"칸이 금액을 그린다: {body.group(1)}"


def test_the_column_uses_only_the_channel_owned_badge_classes():
    """배지 클래스가 W2-A 소유 4종뿐이다(실무 탭 CSS 를 열지 않는다는 설계의 증거).

    `s-ops-b--*` 를 새로 만들면 `settlement-operations.css` 를 열어야 하고, 그 파일은
    목업 스캔·핀 사슬이 걸려 있어 T13 의 변경 범위가 통째로 넓어진다.
    """
    js = _code(_OPS_JS)

    used = set(re.findall(r"s-ch-ops-nv(?:-{1,2}[a-z]+)?", js))
    assert used == set(_BADGE_CLASSES), f"배지 클래스가 계약과 다르다: {sorted(used)}"


def test_the_column_labels_are_exactly_the_agreed_vocabulary():
    """상태 문구 3종이 계약 어휘 그대로다(금칙어 우회 문구가 끼어들지 않는다)."""
    js = _code(_OPS_JS)

    literal = re.search(r"var NAVER_SETTLE_TEXT = \{(.*?)\};", js, re.S)
    assert literal, "상태 문구 표를 찾지 못했다"
    assert dict(re.findall(r"(\w+):\s*'([^']+)'", literal.group(1))) == {
        NAVER_SETTLE_SETTLED: "정산완료",
        NAVER_SETTLE_PENDING: "정산대기",
        NAVER_SETTLE_UNMATCHED: "미매칭",
    }, literal.group(1)


# ==========================================================================
# 8. (W2-B) CSV — 헤더와 데이터가 **같은 조건**으로 늘어난다
# ==========================================================================
def test_csv_headers_and_rows_grow_under_the_same_condition():
    """`csvHeaders(ctx)` 와 `csvRow(ctx,row)` 가 같은 게이트로 정확히 1칸씩 는다.

    한쪽만 늘면 회계 프로그램이 열 매핑을 통째로 어긋나게 읽는다 — 파일은 화면과 달리
    "이상하다"가 눈에 안 띄고 그대로 장부에 들어간다.
    """
    js = _code(_OPS_JS)

    headers = re.search(r"function csvHeaders\(ctx\)\s*\{(.*?)\n  \}", js, re.S)
    row = re.search(r"function csvRow\(ctx, row\)\s*\{(.*?)\n  \}", js, re.S)
    assert headers and row, "csvHeaders / csvRow 를 찾지 못했다"
    assert headers.group(1).count("ctx.showChannelCol") == 1
    assert row.group(1).count("ctx.showChannelCol") == 1
    assert len(re.findall(r"\.concat\(\[", headers.group(1))) == 1, (
        "헤더가 한 번에 한 칸만 늘지 않는다"
    )
    assert len(re.findall(r"cells\.push\(", row.group(1))) == 1, (
        "데이터가 한 번에 한 칸만 늘지 않는다"
    )


def test_csv_base_column_count_matches_between_headers_and_rows():
    """게이트가 꺼진 상태의 기본 칸 수가 헤더와 데이터에서 같다."""
    js = _code(_OPS_JS)

    headers = _top_level_items(_array_literal(js, "var CSV_HEADERS ="))
    cells = _top_level_items(_array_literal(js, "var cells ="))

    assert headers == cells, f"헤더 {headers}칸 vs 데이터 {cells}칸"


def test_csv_exports_the_status_word_only():
    """CSV 의 네이버 정산 칸은 **화면과 같은 상태 문구**뿐이다(날짜·금액 없음).

    파일이 화면보다 많이 말하지 않는다 — 조건 전체를 담는 서버 CSV(T14)가 회계 전용
    게이트 + 감사 뒤에 따로 있고, 이 blob CSV 는 "현재 페이지"라고 스스로 못 박고 있다.
    """
    js = _code(_OPS_JS)

    row = re.search(r"function csvRow\(ctx, row\)\s*\{(.*?)\n  \}", js, re.S)
    assert row, "csvRow 를 찾지 못했다"
    pushed = re.search(r"cells\.push\((.*?)\);", row.group(1), re.S)
    assert pushed, "네이버 정산 칸을 넣는 자리를 찾지 못했다"
    assert "NAVER_SETTLE_TEXT" in pushed.group(1), "상태 문구 표를 쓰지 않는다"
    for field in ("settle_expect_date", "settle_complete_date", "amount"):
        assert field not in pushed.group(1), f"CSV 에 {field} 가 실린다"


# ==========================================================================
# 9. (W2-B) 개명·금칙어·배지 CSS 소유
# ==========================================================================
def test_the_old_column_name_is_gone_repo_wide():
    """옛 이름이 `templates/` · `static/js/` 어디에도 없다(§8.1 T13 완료기준 ④).

    한 표에 뜻이 다른 "정산"이 둘이면 경리가 남의 축을 보고 판단한다. 주석까지 포함해
    지우는 이유: 다음 사람이 주석의 옛 이름을 보고 화면을 되돌린다.
    """
    old_name = "정산상태"
    hits = [
        str(path.relative_to(_REPO))
        for root in ("templates", "static/js")
        for path in (_REPO / root).rglob("*")
        if path.is_file()
        and path.suffix in {".html", ".js"}
        and old_name in path.read_text(encoding="utf-8", errors="ignore")
    ]

    assert hits == [], f"옛 이름이 남아 있다: {hits}"


def test_the_new_column_name_is_in_both_the_header_and_the_csv():
    """개명이 화면 머리글·필터 라벨·CSV 헤더 **세 곳 모두**에 반영됐다."""
    template = _code(_OPS_TEMPLATE)
    js = _code(_OPS_JS)

    assert template.count("차감청구") == 2, "머리글 또는 필터 라벨 중 하나가 안 바뀌었다"
    assert "'차감청구'" in js, "CSV 헤더가 안 바뀌었다"


@pytest.mark.parametrize("word", _FORBIDDEN_WORDS)
def test_forbidden_words_never_reach_the_ops_surface(word):
    """금칙어가 실무 탭 템플릿·JS 에 **주석까지 포함해** 0건이다.

    기존 목업 스캔은 주석을 걷어낸 뒤 보므로 주석에 남은 낱말을 놓친다. 다음 사람이 그
    주석을 보고 라벨을 되돌리면 CI 가 그때서야 red 가 된다 — 여기서 미리 막는다.
    """
    for rel in (_OPS_TEMPLATE, _OPS_JS):
        assert word not in _source(rel), f"{rel}: 금칙어 '{word}'"


@pytest.mark.skipif(
    "s-ch-ops-nv"
    not in (_REPO / _CHANNEL_CSS).read_text(encoding="utf-8", errors="ignore"),
    reason="배지 CSS 는 W2-A(채널 표면) 가 건다 — 걸린 뒤부터 게이트로 작동한다",
)
@pytest.mark.parametrize("cls", _BADGE_CLASSES)
def test_badge_classes_are_defined_in_the_channel_stylesheet(cls):
    """배지 클래스 4종이 `settlement-channel.css` 에 실재한다.

    이 파일은 회계 게이트 뒤에서만 로드된다 — 컬럼이 그려지는 조건과 **정확히 같아서**
    실무 탭 CSS 를 열지 않아도 된다는 것이 T13 설계의 전제다. 한 클래스라도 빠지면
    배지가 스타일 없는 맨 글자로 뜬다(권한자만 보는 화면이라 회귀를 늦게 발견한다).
    """
    css = _source(_CHANNEL_CSS)

    assert re.search(r"\." + re.escape(cls) + r"(?![\w-])", css), (
        f"{_CHANNEL_CSS} 에 .{cls} 규칙이 없다"
    )
