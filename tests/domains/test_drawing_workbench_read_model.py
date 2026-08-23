"""Drawing workbench read-model 모집단 술어 + seed cap tests."""
from unittest.mock import MagicMock

from foms.services.drawing_workbench_read_model import (
    DRAWING_WORKBENCH_SEED_CAP,
    build_drawing_queue_filter,
    fetch_drawing_seed_order_ids,
)

MIGRATION = "migrations/versions/drawqueue_00_drawing_status_partial_indexes.py"


def _mock_query():
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.with_entities.return_value = q
    q.limit.return_value = q
    return q


def test_fetch_drawing_seed_order_ids_respects_cap():
    q = _mock_query()
    q.all.return_value = [(1,), (2,)]

    ids = fetch_drawing_seed_order_ids(q)

    q.limit.assert_called_with(DRAWING_WORKBENCH_SEED_CAP)
    assert ids == [1, 2]


def test_fetch_drawing_seed_order_ids_scopes_before_cap():
    """cap 은 도면 모집단 술어 **뒤에** 적용된다(접수순 창 밖 누락 차단)."""
    q = _mock_query()
    q.all.return_value = [(7,)]

    fetch_drawing_seed_order_ids(q)

    assert q.filter.called, "모집단 술어 없이 cap 만 적용하면 도면 주문이 창 밖으로 밀린다"
    # filter → order_by 순서(술어가 정렬·cap 앞).
    assert q.method_calls[0][0] == "filter"


def _bound_values(clause) -> list:
    """컴파일된 절의 바인드 파라미터 값 목록(JSON path 타입은 literal_binds 불가)."""
    compiled = clause.compile()
    return list(compiled.params.values())


def test_queue_filter_keeps_returned_axis():
    """RETURNED 축은 단계와 별개로 유지 — 수령확정 후 수정요청은 stage 무변경."""
    values = _bound_values(build_drawing_queue_filter())
    assert "RETURNED" in values, "RETURNED 축이 술어에서 빠지면 컨펌 후 수정요청 주문이 사라진다"
    assert ("drawing", "status") in values, "중첩 상태 키 축 누락"
    assert "drawing_status" in values, "flat 상태 키 축 누락"


def test_queue_filter_covers_stage_mirror_and_source():
    """단계는 미러 컬럼과 원본(workflow.stage) 양쪽으로 잡는다(드리프트 내성)."""
    clause = build_drawing_queue_filter()
    assert "erp_stage_code" in str(clause)
    assert ("workflow", "stage") in _bound_values(clause)


def test_queue_filter_confirmed_is_opt_in():
    """컨펌 포함은 opt-in — 기본 술어에는 CONFIRMED 항이 없다."""
    assert "CONFIRMED" not in _bound_values(build_drawing_queue_filter())
    assert "CONFIRMED" in _bound_values(
        build_drawing_queue_filter(include_confirmed=True)
    )


def test_queue_filter_binds_drawing_stage_codes():
    """도면 단계 표기는 코드·한글 라벨 둘 다 잡는다(미러 컬럼 값 혼재)."""
    values = _bound_values(build_drawing_queue_filter())
    flat = [v for value in values for v in (value if isinstance(value, list) else [value])]
    assert "DRAWING" in flat
    assert "도면" in flat
    assert "RETURNED" in flat


def test_partial_indexes_match_predicate_expressions():
    """부분 인덱스 식이 술어 컴파일 결과와 일치 — 어긋나면 조용히 Seq Scan 으로 추락한다."""
    from pathlib import Path

    from sqlalchemy.dialects import postgresql

    sql = str(
        build_drawing_queue_filter(include_confirmed=True).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    ddl = (Path(__file__).resolve().parents[2] / MIGRATION).read_text(encoding="utf-8")

    # 컴파일된 JSON 경로 식(공백 포함 표기)을 인덱스 DDL 표기로 정규화해 비교한다.
    for compiled_expr, index_expr in (
        ("structured_data #>> '{workflow, stage}'", "structured_data #>> '{workflow,stage}'"),
        ("structured_data #>> '{drawing, status}'", "structured_data #>> '{drawing,status}'"),
        ("structured_data ->> 'drawing_status'", "structured_data ->> 'drawing_status'"),
    ):
        assert compiled_expr in sql, f"술어에서 사라진 축: {compiled_expr}"
        assert index_expr in ddl, f"부분 인덱스가 덮지 않는 축: {index_expr}"
