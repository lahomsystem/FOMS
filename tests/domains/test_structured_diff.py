"""주문 구조화 변경 비교 계약 (ORDER-DIFF-00).

감사 원장에 남는 값이라 "무엇을 변경으로 볼 것인가"가 곧 기록의 신뢰도다. 여기서 고정하는 것:
빈값 동치(소음 차단)·화이트리스트 경계·상한 절단의 정직성·품목 위치 매칭의 알려진 한계.
"""

from foms.services.audit_message_display import describe_change, path_label
from foms.services.orders.structured_diff import MAX_CHANGES, diff_structured


def _sd(**overrides):
    """비교 기준이 되는 최소 주문 문서를 만든다."""
    base = {
        "schedule": {"measurement": {"date": "2026-08-12"}},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "totals": {"final_amount": "1,300,000"},
        "items": [{"product_name": "붙박이장", "price": "500000"}],
    }
    base.update(overrides)
    return base


def test_empty_variants_are_not_changes():
    """``None``·빈 문자열·키 부재는 같은 상태다 — 저장만 눌러도 변경이 쌓이면 원장이 소음이 된다."""
    old = {"parties": {"customer": {"name": "", "phone": None}}, "notes": None}
    new = {"parties": {"customer": {}}, "notes": ""}

    result = diff_structured(old, new)

    assert result.changes == []
    assert result.total == 0


def test_numeric_amounts_compare_by_value_not_text():
    """금액은 ``"1,300,000"`` 과 ``1300000`` 이 같은 값이다(표기 차이는 변경이 아니다)."""
    result = diff_structured(_sd(), _sd(totals={"final_amount": 1300000}))

    assert result.changes == []


def test_amount_change_is_recorded_with_before_and_after():
    """금액이 실제로 바뀌면 이전값과 새값이 함께 남는다."""
    result = diff_structured(_sd(), _sd(totals={"final_amount": "1,500,000"}))

    assert result.total == 1
    change = result.changes[0]
    assert change["path"] == "totals.final_amount"
    assert change["before"] == "1300000"
    assert change["after"] == "1500000"
    assert change["op"] == "set"


def test_add_and_clear_ops_are_distinguished():
    """빈값→값은 ``add``, 값→빈값은 ``clear`` 다(둘을 뭉치면 "지웠다"가 사실과 달라진다)."""
    added = diff_structured({}, {"notes": "현장 협의 필요"})
    cleared = diff_structured({"notes": "현장 협의 필요"}, {"notes": ""})

    assert added.changes[0]["op"] == "add"
    assert cleared.changes[0]["op"] == "clear"


def test_paths_outside_whitelist_are_ignored():
    """화이트리스트 밖(파생·캐시·별도 원장 보유)은 기록하지 않는다."""
    old = _sd()
    new = _sd()
    new["quests"] = [{"id": 1}]
    new["meta"] = {"draft": True}
    new["drawing_status"] = "READY"

    assert diff_structured(old, new).changes == []


def test_item_field_change_carries_item_name():
    """품목 변경에는 저장 시점 품목명이 붙는다 — 인덱스만으로는 어느 품목인지 알 수 없다."""
    new = _sd(items=[{"product_name": "붙박이장", "price": "620000"}])

    result = diff_structured(_sd(), new)

    assert result.total == 1
    change = result.changes[0]
    assert change["path"] == "items.0.price"
    assert change["item"] == "붙박이장"
    assert path_label(change["path"]) == "1번 품목 단가"


def test_item_append_and_remove_are_single_entries():
    """품목 추가/삭제는 필드별로 흩어지지 않고 품목 1건으로 남는다."""
    added = diff_structured(_sd(), _sd(items=[
        {"product_name": "붙박이장", "price": "500000"},
        {"product_name": "수납장"},
    ]))
    removed = diff_structured(_sd(), _sd(items=[]))

    assert [(c["path"], c["op"], c["after"]) for c in added.changes] == [("items.1", "add", "수납장")]
    assert [(c["path"], c["op"], c["before"]) for c in removed.changes] == [("items.0", "remove", "붙박이장")]


def test_item_insert_at_head_reports_shifted_fields():
    """**알려진 한계**: 품목 배열에 안정 identity 가 없어 맨 앞 삽입이 "여러 품목 변경"으로 읽힌다.

    위치 인덱스로 짝짓기 때문이며(ITEM-ID-00 이후 해소 대상), 지금은 이 동작을 숨기지 않고
    문서화한다 — 감사 화면을 읽는 사람이 품목명(``item``)으로 판별할 수 있어야 한다.
    """
    new = _sd(items=[
        {"product_name": "수납장", "price": "100000"},
        {"product_name": "붙박이장", "price": "500000"},
    ])

    result = diff_structured(_sd(), new)
    paths = [change["path"] for change in result.changes]

    assert "items.0.product_name" in paths  # 붙박이장 → 수납장 으로 보인다(실제는 삽입)
    assert "items.1" in paths               # 밀려난 붙박이장이 "추가"로 보인다


def test_spec_rows_summarized_by_row_count():
    """규격표는 셀 단위가 아니라 행 수 요약으로 남긴다(v1 범위)."""
    old = _sd(items=[{"product_name": "붙박이장", "spec_rows": [{"w": "1200"}]}])
    new = _sd(items=[{"product_name": "붙박이장", "spec_rows": [{"w": "1200"}, {"w": "900"}]}])

    result = diff_structured(old, new)

    assert result.total == 1
    assert result.changes[0]["path"] == "items.0.spec_rows"
    assert (result.changes[0]["before"], result.changes[0]["after"]) == ("1행", "2행")


def test_truncation_reports_dropped_count():
    """상한을 넘겨도 절단 사실을 감추지 않는다(개수를 남긴다)."""
    old = {"items": [{"product_name": f"품목{i}"} for i in range(MAX_CHANGES + 5)]}
    new = {"items": [{"product_name": f"변경{i}"} for i in range(MAX_CHANGES + 5)]}

    result = diff_structured(old, new)

    assert result.total == MAX_CHANGES + 5
    assert len(result.changes) == MAX_CHANGES
    assert result.truncated == 5


def test_long_values_are_clipped_with_marker():
    """긴 값은 잘라 저장하되 잘렸다는 표시를 남긴다."""
    result = diff_structured({}, {"notes": "가" * 300})

    assert result.changes[0]["after"].endswith("…")
    assert len(result.changes[0]["after"]) == 121


def test_non_dict_documents_are_tolerated():
    """구조가 깨진 문서(문자열·``None``)가 와도 저장 경로를 죽이지 않는다."""
    assert diff_structured(None, None).changes == []
    assert diff_structured("bad", {"notes": "새 비고"}).total == 1


def test_stage_change_reads_as_korean_stage_name():
    """단계 코드는 화면에서 한글 단계명으로 읽힌다(표시 SSOT 재사용)."""
    result = diff_structured(
        {"workflow": {"stage": "RECEIVED"}},
        {"workflow": {"stage": "MEASURE"}},
    )

    text = describe_change(result.changes[0])

    assert text.startswith("단계 ")
    assert "RECEIVED" not in text
    assert "MEASURE" not in text
