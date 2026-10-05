"""정산 얇은 문서(성능 원장 P3-6) — **읽는 양만** 줄었고 정산 숫자는 그대로라는 계약.

정산 집계·실무 탭·단계 카드는 모집단 전량의 ``structured_data`` 를 통째로 읽었다(2026-10-05
스테이징 1,586행 출력 3,675kB). 이제는 :data:`settlement_source.SETTLEMENT_SD_SPEC` 이 남기는
경로만 싣는다. 돈 화면이라 지키는 것은 둘이다.

1. 판정 소비자 전부를 **통째 원본 + 경로 추적기**로 돌려, 읽힌 자리가 전부 투영 안에 있다
   (새 판정이 투영 밖 경로를 읽기 시작하면 이 테스트가 빨개진다).
2. 같은 입력에서 투영으로 낸 답 == 통째 원본으로 낸 답 — 행 판정 단위와 화면 응답 전체
   (``aggregate_settlement``·``list_settlement_rows``) 둘 다.

둘 다 음성 대조군을 붙인다 — 경로 하나를 뺀 투영으로 같은 측정을 돌리면 잡아내야 한다.
SQLite 레인은 투영을 파이썬 정본(:func:`project_settlement_sd`)으로 하고, SQL 투영이 그 정본과
같다는 증명은 PG 레인(``tests/postgres/test_settlement_source_pg.py``)이 맡는다.
"""
from __future__ import annotations

import copy
import json

import pytest

from db import db_session
from foms.services import settlement_aggregation, settlement_rows
from foms.services import settlement_source as ss
from tests.domains.settlement_source_helpers import (
    CONSUMERS,
    SHAPES,
    row_for,
    seed_shapes,
    spec_without,
    uncovered_reads,
)
from tests.services.integrations.naver_list_snapshot_helpers import traced

#: 음성 대조군이 빼는 경로 — 예약금·잔금·현금영수증이 모두 이 갈래에서 나온다.
DROPPED = ("payment",)
#: 품목 단가 폴백 — 품목합이 저장되지 않은 주문의 출고가가 여기서 나온다.
DROPPED_PRICE = ("items", ss.ARRAY_ITEMS, "price")

_AGG_CASES = (("2026-09", "2026-10", "day"), ("2025-11", "2026-10", "week"),
              ("2026-02", "2026-03", "month"), ("2030-01", "2030-01", "day"))
_ROW_CASES = (dict(), dict(period="31"), dict(settlement="issued"), dict(channel="NAVER"),
              dict(aging="D91_PLUS"), dict(period="7", settlement="pending", aging="LE7"))


def _trace_consumers() -> set:
    """판정 소비자 전부를 표본마다 **통째 원본 + 추적기**로 돌려 읽힌 경로를 모은다."""
    ops: set = set()
    for sd, attrs in SHAPES.values():
        for consume in CONSUMERS.values():
            consume(row_for(traced(copy.deepcopy(sd), (), ops), attrs))
    return ops


def test_consumers_read_only_projected_paths():
    """판정이 읽는 자리는 전부 투영 안에 있다."""
    ops = _trace_consumers()

    # 추적기가 실제로 돌았다는 증거(빈 기록끼리 통과하는 거짓 초록을 막는다).
    assert (("items", "[]", "price"), "get") in ops, "품목 단가 폴백까지 탔어야 한다"
    assert (("items",), "iter") in ops
    assert (("payment", "deposit"), "contains") in ops, "'없음'과 null 을 가르는 자리"
    assert (("payments", "deposit"), "contains") in ops, "레거시 payments 폴백까지 탔어야 한다"
    assert (("settlement", "deductions"), "iter") in ops
    assert (("shipment", "as_billing"), "get") in ops
    assert (("parties", "manager", "name"), "get") in ops
    assert (("parties", "customer", "name"), "get") in ops
    assert (("schedule", "construction", "date"), "get") in ops

    missing = uncovered_reads(ops, ss.SETTLEMENT_SD_SPEC)
    assert not missing, f"투영 밖 경로를 읽는다 — SETTLEMENT_SD_SPEC 에 더하라: {sorted(missing)}"


def test_coverage_check_catches_a_dropped_path_negative_control():
    """음성 대조군 — 경로 하나를 뺀 투영이면 같은 측정이 그 경로를 짚는다."""
    ops = _trace_consumers()

    assert (("payment", "deposit"), "contains") in uncovered_reads(
        ops, spec_without(ss.SETTLEMENT_SD_SPEC, DROPPED))
    assert (DROPPED_PRICE, "get") in uncovered_reads(
        ops, spec_without(ss.SETTLEMENT_SD_SPEC, DROPPED_PRICE))
    # 통째 마디(차감 목록)를 잘게 자르면 순회 접근이 걸린다.
    sliced = copy.deepcopy(ss.SETTLEMENT_SD_SPEC)
    sliced["settlement"] = {"deductions": {"department": None}, "cash_receipt": None}
    assert (("settlement", "deductions"), "iter") in uncovered_reads(ops, sliced)


@pytest.mark.parametrize("label", sorted(SHAPES))
def test_each_consumer_answers_the_same_on_the_projection(label):
    """모양마다·소비자마다 투영 문서의 답 == 통째 원본의 답."""
    sd, attrs = SHAPES[label]
    projected = ss.project_settlement_sd(copy.deepcopy(sd))
    for name, consume in CONSUMERS.items():
        full = consume(row_for(copy.deepcopy(sd), attrs))
        thin = consume(row_for(copy.deepcopy(projected), attrs))
        assert json.dumps(thin, ensure_ascii=False) == json.dumps(full, ensure_ascii=False), name


def test_projection_negative_control_changes_answers():
    """음성 대조군 — 단가·예약금 갈래를 뺀 투영이면 같은 비교가 갈린다(비교에 이가 있다)."""
    fallback_sd, attrs = SHAPES["품목합-폴백-단가모양"]
    consume = CONSUMERS["aggregation._settlement_row"]
    full = consume(row_for(copy.deepcopy(fallback_sd), attrs))
    no_price = ss.project_settlement_sd(copy.deepcopy(fallback_sd),
                                        spec_without(ss.SETTLEMENT_SD_SPEC, DROPPED_PRICE))
    no_payment = ss.project_settlement_sd(copy.deepcopy(fallback_sd),
                                          spec_without(ss.SETTLEMENT_SD_SPEC, DROPPED))

    assert consume(row_for(no_price, attrs))["shipping_price"] != full["shipping_price"]
    assert consume(row_for(no_payment, attrs))["deposit"] != full["deposit"]


def test_projection_drops_unread_branches_and_keeps_item_count():
    """안 읽는 큰 갈래는 빠지고, 품목은 원소 수·순서를 그대로 둔 채 단가만 남는다."""
    sd, _attrs = SHAPES["품목합-폴백-단가모양"]
    projected = ss.project_settlement_sd(copy.deepcopy(sd))

    assert not {"quests", "site", "workflow", "notes"} & set(projected)
    assert len(projected["items"]) == len(sd["items"])
    assert projected["items"][0] == {"price": "1,000,000"}
    assert projected["items"][-1] == {}, "단가 없는 원소도 자리는 남는다"
    assert projected["items"][5] == "dict 아닌 원소"
    assert "deposit" not in ss.project_settlement_sd({"payment": {}})["payment"]
    assert ss.project_settlement_sd({"payment": {"deposit": None}}) == {"payment": {"deposit": None}}
    assert ss.project_settlement_sd("문자") == "문자"
    assert ss.project_settlement_sd(None) is None


def _outputs() -> tuple[list, list]:
    aggregates = [settlement_aggregation.aggregate_settlement(
        db_session, month_from=mf, month_to=mt, granularity=g) for mf, mt, g in _AGG_CASES]
    rows = [settlement_rows.list_settlement_rows(db_session, include_naver_settlement=inc, **case)
            for case in _ROW_CASES for inc in (False, True)]
    return aggregates, rows


def test_screen_outputs_match_the_full_document_path(app, monkeypatch):
    """화면 응답 전체 — 투영 경로 == 통째 원본 경로(옛 동작). 음성 대조군 포함."""
    seed_shapes(db_session)
    db_session.commit()

    projected = _outputs()
    assert projected[0][0]["kpi"]["completed_count"] > 0, "빈 결과끼리 같다는 거짓 통과"
    assert projected[1][0]["total_count"] == len(SHAPES)

    monkeypatch.setattr(ss, "project_settlement_sd", lambda raw, spec=None: raw)
    full = _outputs()
    assert json.dumps(projected, ensure_ascii=False) == json.dumps(full, ensure_ascii=False)

    # 음성 대조군: 예약금 갈래를 뺀 투영이면 같은 비교가 갈린다.
    dropped = spec_without(ss.SETTLEMENT_SD_SPEC, DROPPED)
    monkeypatch.setattr(ss, "project_settlement_sd",
                        lambda raw, spec=None: ss._project(raw, dropped))
    assert json.dumps(_outputs(), ensure_ascii=False) != json.dumps(full, ensure_ascii=False)
