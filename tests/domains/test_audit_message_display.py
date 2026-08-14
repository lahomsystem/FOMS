"""AUDIT-LOG P4 A1: 감사 로그 표시 SSOT 계약.

스펙: ``docs/specs/2026-08-08-audit-log-readability-coverage-design.md`` §3-1.

고정하는 계약:

1. **라벨 사전은 한 벌** — ``foms/web/orders/edit.py`` 는 지역 dict 를 다시 만들지 않고
   이 모듈을 import 한다(두 벌이 되면 화면마다 다른 말이 나온다 — 이번 작업의 발단).
2. **값 표기 규칙** — 빈 값·체크박스·불리언·상태 코드·가능시간 dict·HTML 본문.
3. **역파싱** — 운영에 이미 쌓인 자유 텍스트(실측 원문)를 같은 규격으로 옮기고,
   해석 못 하는 문장은 **원문 그대로** 돌려준다.
4. **오표기 금지** — ``사용자 #58`` 같은 비-주문 번호에 고객명을 붙이지 않는다.
"""

from __future__ import annotations

import pathlib
import re

from foms.services import audit_message_display as amd

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# 운영 `security_logs` 최근 30일 상위 유형에서 그대로 가져온 실제 문장 형태.
_PROD_FIELD_CHANGE = "지방 주문 #4183의 'regional_construction_info_sent' 상태를 'True'(으)로 변경"
_PROD_CLEARED = "주문 #3210의 'as_completed_date' 필드를 ''(으)로 변경"
_PROD_DICT = "주문 #4394의 'as_visit_availability' 필드를 '{'days': 'weekday', 'time': 'any'}'(으)로 변경"
_PROD_HTML = (
    "주문 #4426의 'as_content' 필드를 "
    "'<div>7/22 해피콜 - 고객 일정 확인 후 연락주신다고 하심</div>도어 교체'(으)로 변경"
)


# --------------------------------------------------------------------------
# 1. 사전 SSOT
# --------------------------------------------------------------------------
def test_field_labels_cover_production_top_fields():
    """운영 최근 30일 상위 변경 필드가 전부 한글 라벨을 가진다."""
    observed = [
        "as_visit_date", "as_completed_date", "as_content", "shipping_scheduled_date",
        "regional_order_upload", "scheduled_date", "regional_sales_order_upload",
        "measurement_completed", "regional_blueprint_sent", "measurement_date",
        "regional_cargo_sent", "regional_construction_info_sent", "sales_delivery",
        "as_visit_availability",
    ]
    missing = [f for f in observed if f not in amd.FIELD_LABELS]
    assert not missing, f"라벨 없는 운영 필드: {missing}"


def test_unknown_field_falls_back_to_raw_name():
    """사전에 없는 필드는 감추지 않고 원문 그대로 낸다."""
    assert amd.field_label("brand_new_column") == "brand_new_column"
    assert amd.field_label(None) == ""


def test_label_dictionary_is_not_duplicated_in_edit_route():
    """edit.py 가 라벨 사전을 다시 정의하지 않는다(사전 이중화 = 화면 불일치의 원인)."""
    source = (_REPO_ROOT / "foms" / "web" / "orders" / "edit.py").read_text(encoding="utf-8")
    assert "audit_message_display" in source, "edit.py 가 표시 SSOT 를 쓰지 않는다"
    # 지역 dict 재정의 금지: 'regional_blueprint_sent': '도면 발송' 형태 리터럴이 남으면 안 된다.
    assert not re.search(r"['\"]regional_blueprint_sent['\"]\s*:\s*['\"]", source), (
        "edit.py 에 라벨 리터럴이 남아 있다 — SSOT 로 이관되지 않음"
    )


# --------------------------------------------------------------------------
# 2. 값 표기
# --------------------------------------------------------------------------
def test_checklist_boolean_reads_as_business_state():
    """체크리스트 필드의 True/False 는 '완료/해제'로 읽는다."""
    assert amd.format_value("regional_blueprint_sent", "True") == "완료"
    assert amd.format_value("regional_blueprint_sent", False) == "해제"


def test_non_checklist_boolean_reads_as_yes_no():
    """체크리스트가 아닌 불리언은 '예/아니오'."""
    assert amd.format_value("sales_delivery", "True") == "예"
    assert amd.format_value("is_regional", False) == "아니오"


def test_empty_values_read_as_cleared():
    """빈 문자열·None 은 '(지움)' — 지웠다는 사실 자체가 감사 대상이다."""
    for raw in ("", None, "None", "  "):
        assert amd.format_value("as_completed_date", raw) == "(지움)"


def test_status_code_reads_as_korean_stage():
    """상태 코드는 한글 단계명으로."""
    assert amd.format_value("status", "MEASURE") == "실측"
    assert amd.format_value("status", "UNKNOWN_CODE") == "UNKNOWN_CODE"


def test_availability_dict_reads_as_sentence():
    """가능시간 dict(파이썬 repr 문자열 포함)은 사람 표기로."""
    assert amd.format_value("as_visit_availability", {"days": "weekday", "time": "am"}) == "평일 · 오전"
    assert amd.format_value("as_visit_availability", "{'days': 'weekend', 'time': 'any'}") == "주말 · 시간무관"


def test_html_body_is_flattened_and_truncated():
    """HTML 본문은 태그를 걷고 길면 줄인다(원장 목록이 마크업으로 도배되지 않게)."""
    out = amd.format_value("as_content", "<div>해피콜 완료</div>도어 교체")
    assert "<div>" not in out
    assert "해피콜 완료 도어 교체" == out

    long_out = amd.format_value("as_content", "<p>" + "가" * 200 + "</p>")
    assert long_out.endswith("…")
    assert len(long_out) <= 61


# --------------------------------------------------------------------------
# 3. 문장 생성 / 역파싱
# --------------------------------------------------------------------------
def test_describe_field_change_includes_customer_and_transition():
    """쓰기 경로 문장: 주문번호·고객명·이전→이후."""
    line = amd.describe_field_change(
        order_id=3210, field="as_completed_date", before="2026-07-02", after="",
        has_before=True, customer_name="이영희",
    )
    assert line == "주문 #3210 (이영희) — AS 완료일: 2026-07-02 → (지움)"


def test_describe_field_change_without_before_marks_checklist_state():
    """이전 값을 모르면 결과만 적되, 체크리스트는 '…로 표시'로 상태 변화를 드러낸다."""
    line = amd.describe_field_change(
        order_id=4183, field="regional_construction_info_sent", after=True,
        customer_name="김철수", order_type="지방 주문",
    )
    assert line == "지방 주문 #4183 (김철수) — 시공정보 발송: 완료로 표시"


def test_humanize_rewrites_production_legacy_messages():
    """운영에 쌓인 구 형식 3종이 같은 규격으로 읽힌다."""
    assert amd.humanize_message(_PROD_FIELD_CHANGE, {4183: "김철수"}) == (
        "지방 주문 #4183 (김철수) — 시공정보 발송: 완료로 표시"
    )
    assert amd.humanize_message(_PROD_CLEARED, {3210: "이영희"}) == (
        "주문 #3210 (이영희) — AS 완료일: (지움)"
    )
    assert amd.humanize_message(_PROD_DICT, {4394: "박민수"}) == (
        "주문 #4394 (박민수) — AS 방문 가능시간: 평일 · 시간무관"
    )
    html_line = amd.humanize_message(_PROD_HTML, {4426: "한지민"})
    assert "<div>" not in html_line and "AS 내용" in html_line


def test_humanize_rewrites_status_transitions_with_korean_stage_names():
    """상태 전이 구 형식의 영문 코드를 단계 이름으로 옮긴다(운영 최근 30일 66건 유형)."""
    assert amd.humanize_message(
        "자가실측 주문 #4679 상태 변경: 'MEASURE' → 'SHIPPED_PENDING'", {4679: "최옥희"}
    ) == "자가실측 주문 #4679 (최옥희) — 상태: 실측 → 상차예정"

    assert amd.humanize_message(
        "주문 #4183 휴지통 이동 (bulk): MEASURE → DELETED", {4183: "조혜리"}
    ) == "주문 #4183 (조혜리) — 휴지통으로 이동: 실측 → 삭제됨"


def test_status_transition_without_before_omits_arrow():
    """이전 상태가 기록되지 않은 구 bulk 행은 '(지움) →' 로 쓰지 않는다(사실과 다르다)."""
    assert amd.humanize_message("주문 #4183 휴지통 이동 (bulk): → DELETED", {}) == (
        "주문 #4183 — 휴지통으로 이동: 삭제됨"
    )


def test_humanize_annotates_readable_messages_with_customer_name():
    """이미 읽을 만한 문장은 고쳐 쓰지 않고 고객명만 덧붙인다."""
    out = amd.humanize_message("주문 #4109 AS 접수 등록 (접수일: 2026-07-01)", {4109: "최영수"})
    assert out == "주문 #4109 (최영수) AS 접수 등록 (접수일: 2026-07-01)"


def test_humanize_returns_original_when_unparseable():
    """해석 못 하는 문장은 원문 그대로 — 감사 화면은 값을 감추지 않는다."""
    for raw in ("권한 없는 접근 시도: /trash", "로그인 성공: 사용자 upperkill (ID: 3)", "엑셀 업로드 22건"):
        assert amd.humanize_message(raw, {}) == raw


def test_non_order_hash_number_is_never_annotated():
    """``사용자 #58`` 의 58 에 주문 58 의 고객명을 붙이지 않는다(오표기 = 오판)."""
    out = amd.humanize_message("사용자 #58 삭제", {58: "엉뚱한고객"})
    assert out == "사용자 #58 삭제"
    assert amd.extract_order_ids("사용자 #58 삭제") == []


def test_extract_and_collect_order_ids():
    """화면이 고객명을 배치 조회할 수 있도록 주문 id 를 뽑는다(N+1 방지 입력)."""
    assert amd.extract_order_ids(_PROD_FIELD_CHANGE) == [4183]
    ids = amd.collect_order_ids([_PROD_CLEARED, _PROD_DICT, _PROD_CLEARED, None, "로그인 성공"])
    assert ids == [3210, 4394]


def test_order_label_without_customer_name_keeps_number_only():
    """고객명을 모르면(삭제된 주문 등) 번호만 낸다 — 없는 이름을 지어내지 않는다."""
    assert amd.order_label(4382) == "주문 #4382"
    assert amd.order_label(4382, order_type="자가실측") == "자가실측 #4382"


# --- AUDIT-LOG P4 C1: 행위 문장 SSOT -------------------------------------------------


def test_action_label_translates_known_codes():
    """행위 코드는 업무 라벨로 나온다(``CONSTRUCTION_COMPLETED`` 를 외우게 하지 않는다)."""
    assert amd.action_label("CONSTRUCTION_COMPLETED") == "시공 완료"
    assert amd.action_label("AS_BILLING_DECIDED") == "AS 비용 판정"
    assert amd.action_label("FILE_DELETED") == "파일 삭제"


def test_unknown_action_falls_back_to_the_raw_code():
    """사전에 없는 코드는 코드 그대로 — 배선이 라벨을 빠뜨려도 기록은 읽힌다."""
    assert amd.action_label("BRAND_NEW_ACTION") == "BRAND_NEW_ACTION"
    assert amd.action_label(None) == ""


def test_describe_order_action_puts_customer_name_next_to_the_order():
    """행위 문장도 필드 변경과 같은 주문 표기를 쓴다(화면에서 한 줄로 섞여 읽힌다)."""
    assert amd.describe_order_action(
        order_id=4109, action="CONSTRUCTION_COMPLETED",
        customer_name="홍길동", order_type="주문",
    ) == "주문 #4109 (홍길동) — 시공 완료"
    assert amd.describe_order_action(
        order_id=4183, action="AS_STARTED",
        customer_name="김철수", order_type="지방 주문",
    ) == "지방 주문 #4183 (김철수) — AS 시작"


def test_describe_order_action_appends_note_when_present():
    """전달 메모·결제 종류 같은 부연은 뒤에 붙는다."""
    assert amd.describe_order_action(
        order_id=4382, action="DRAWING_DELIVERED", customer_name="박민수", note="3차 수정본",
    ) == "주문 #4382 (박민수) — 도면 전달 완료: 3차 수정본"


def test_describe_order_action_summarizes_long_or_markup_notes():
    """부연이 HTML·장문이어도 로그 한 줄을 넘기지 않는다(원장 도배 방지)."""
    out = amd.describe_order_action(
        order_id=1, action="AS_LOG_ADDED", note="<div>" + ("가" * 90) + "</div>",
    )
    assert out.startswith("주문 #1 — AS 기록 추가: ")
    assert "<div>" not in out
    assert out.endswith("…")


def test_describe_order_action_without_note_has_no_dangling_colon():
    """부연이 없으면 콜론을 남기지 않는다."""
    assert amd.describe_order_action(order_id=7, action="AS_COMPLETED", note="") == (
        "주문 #7 — AS 완료"
    )


# --- 2026-08-10 운영 실측 결함 2건 ---------------------------------------------------


def test_message_that_already_names_the_customer_is_not_annotated_twice():
    """쓰기 경로가 만든 문장은 이미 고객명을 품고 있다 — 화면이 또 붙이면 안 된다.

    운영 실측: ``주문 #4704 (황인영) (황인영) — 주문 저장: 전체 저장``.
    """
    written = "주문 #4704 (황인영) — 주문 저장: 전체 저장"
    assert amd.humanize_message(written, {4704: "황인영"}) == written


def test_legacy_message_without_a_name_still_gets_one():
    """반대로 이름이 없는 구 형식 문장에는 그대로 덧붙인다(기능 유지)."""
    assert amd.humanize_message("주문 #4373의 메모를 업데이트", {4373: "김재민"}) == (
        "주문 #4373 (김재민)의 메모를 업데이트"
    )


def test_empty_before_and_empty_after_is_not_rendered_as_a_change():
    """원래 없던 값을 비운 것은 변화가 아니다 — ``(없음) → (지움)`` 로 쓰지 않는다.

    운영 실측: ``AS 방문일: (없음) → (지움)`` (기록 원문은 ``AS 방문일: (지움)``).
    """
    assert amd.describe_field_change(
        order_id=4243, field="as_visit_date", before=None, after="", has_before=True,
        customer_name="박인영 AS",
    ) == "주문 #4243 (박인영 AS) — AS 방문일: (지움)"


def test_real_clear_still_shows_the_value_that_was_erased():
    """값이 있던 것을 지운 경우는 그대로 ``이전 → (지움)`` 이다(되돌림 근거 보존)."""
    assert amd.describe_field_change(
        order_id=3210, field="as_completed_date", before="2026-07-02", after="",
        has_before=True, customer_name="이영희",
    ) == "주문 #3210 (이영희) — AS 완료일: 2026-07-02 → (지움)"


def test_object_values_read_as_korean_not_json():
    """비고 객체는 JSON 원문이 아니라 사람 말로 읽힌다(표기 SSOT 재사용).

    원장은 값을 문자열 한 칸에 담으므로 객체·목록은 직렬화된 채 남는다. 운영 실측
    (2026-08-14): ``비고 (없음) → {"address_note": "", "construction_note": …``.
    """
    rendered = amd.format_value(None, '{"address_note": "경비실 호출", "construction_note": "오전만"}')

    assert "주소 특이사항 경비실 호출" in rendered
    assert "시공 특이사항 오전만" in rendered
    assert "{" not in rendered


def test_list_values_read_as_a_comma_list():
    """목록 값(시공 인원 등)도 대괄호가 아니라 쉼표 나열로 읽힌다."""
    assert amd.format_value(None, '["홍", "시공자"]') == "홍, 시공자"


def test_non_json_text_is_left_alone():
    """중괄호로 시작하지 않는 평범한 문자열은 손대지 않는다."""
    assert amd.format_value(None, "경기도 용인시 수지구 광교마을로 134") == (
        "경기도 용인시 수지구 광교마을로 134"
    )
