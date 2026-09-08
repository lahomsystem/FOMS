"""네이버 도크 자동 입력 — 서버 매핑 계약 (2026-09-08).

**왜 이 파일이 있나.** 도크는 원래 "자동 기입 금지"였다 — 서버는 표시용 값만 만들고 값
전달은 사람이 복사 버튼으로만 했다(``dock.py`` 모듈 docstring · 스펙 확정 결정 3).
2026-09-08 담당자가 그 결정을 **네 칸에 한해** 뒤집었다: 제품명·색상·손잡이·총폭.
그 네 칸 중 **서버가 이름을 댈 수 있는 세 칸**의 정본이 :data:`COPY_TARGET_BY_KEY` 이고,
이 파일이 그 정본을 못박는다.

무엇이 깨지면 무슨 일이 나나.

* 매핑이 틀리면 담당자가 누른 칩이 **엉뚱한 칸**에 들어간다. 화면은 값을 넣은 뒤
  ``input``·``change`` 를 쏘고 자동저장이 그것을 듣는다 — 잘못 들어간 값은 사람이
  눈치채기 전에 서버 draft 까지 간다.
* ``사이즈``·``규격``·``폭`` 에 ``spec_width`` 를 달면 총폭이 **모듈 폭**으로 덮인다.
  실사례: 30cm 모듈 12개 + 1cm 길이추가 12개 = **3,720mm** 인 집의 옵션 원문은
  ``사이즈: 150`` 이다. 150 을 W 칸에 넣으면 1,500mm — 2,220mm 를 잃는다. 그래서 서버는
  ``spec_width`` 를 **절대 내보내지 않는다**(총폭 칩은 화면이 만들고 거기서 단다).
* ``copies`` 가 문자열 목록이 아니게 되면, SW 가 ``staticCacheFirst`` 라 배포 직후 반드시
  생기는 "옛 JS + 새 payload" 창에서 칩이 전부 ``📋 [object Object]`` 로 뜬다. 그래서
  ``copy_chips`` 는 **덧붙이기**이고 ``copies`` 는 그대로 남는다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.dock import (
    COPY_TARGET_BY_KEY,
    build_dock_payload,
    option_copy_chips,
    split_option_copies,
)
from tests.services.integrations.test_naver_dock import (
    _link,
    _naver_order,
    _snapshot,
    _staff,
)

#: 운영에서 실제로 들어온 옵션 원문들 — 파서 두 벌 금지 계약(아래 parity 테스트)의 모집단.
_LIVE_OPTION_TEXTS = (
    "제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입",
    "제품: 보테가 슬라이딩 30cm （풀오토댐퍼 포함） / 컬러: 포그 그레이",
    "사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입",
    "색상 ／ 사이즈: 클린 화이트",
    "사이즈: 150（무몰딩）/ 색상: 클린 화이트 / 피닉스바",
    "서랍: 1단(소)",
    "",
)


def _pairs(option_text: str) -> list[tuple[str, str]]:
    """칩 목록을 ``(값, 들어갈 칸)`` 짝으로 — 읽기 쉬운 비교용.

    Args:
        option_text: 네이버 ``productOption`` 원문.

    Returns:
        ``[(값, target), ...]``.
    """
    return [(chip["value"], chip["target"]) for chip in option_copy_chips(option_text)]


# --------------------------------------------------------------------------- #
# 키 → 칸 매핑 (계약 §2)
# --------------------------------------------------------------------------- #

def test_live_option_text_names_the_erp_field_for_each_chip():
    """운영 옵션 원문의 칩마다 **어느 칸에 들어갈 값인지**가 함께 나온다.

    화면이 한국어 옵션 키를 다시 파싱하지 않는 근거다 — 파서가 두 벌이 되면 서버가
    규칙을 고쳐도 화면만 옛 답을 낸다.
    """
    assert _pairs("제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입") == [
        ("로라 무몰딩 여닫이", "product_name"),
        ("클린 화이트", "color"),
        ("푸쉬타입", "handle"),
    ]
    assert _pairs("제품: 보테가 슬라이딩 30cm （풀오토댐퍼 포함） / 컬러: 포그 그레이") == [
        ("보테가 슬라이딩", "product_name"),
        ("포그 그레이", "color"),
    ]


def test_color_key_variants_all_point_at_the_color_field():
    """``컬러``·``색상`` 은 **둘 다** 운영에서 온다 — 하나만 매핑하면 절반이 복사 전용이 된다.

    ``컬러`` 는 조합형 옵션 상품에서, ``색상`` 은 전각 짝 상품에서 온다(운영 실사례
    2026-09-01 주문 2026090191203001).
    """
    assert _pairs("컬러: 화이트") == [("화이트", "color")]
    assert _pairs("색상: 화이트") == [("화이트", "color")]
    assert COPY_TARGET_BY_KEY["색깔"] == "color"
    assert COPY_TARGET_BY_KEY["핸들"] == "handle"


def test_server_never_names_the_width_field():
    """서버가 ``spec_width`` 를 내보내는 경로는 **없다** (계약 §2 — 2,220mm 유실 방지).

    ``사이즈: 150`` 의 150 은 고객이 고른 **모듈 폭**이지 ERP 총폭이 아니다. 총폭은
    ``모듈 × 수량 + 길이추가`` 라 실사례로 30cm×12 + 1cm×12 = 3,720mm 다. W 칸을 채울
    자격은 화면이 만드는 총폭 칩(이미 mm 정수) 하나뿐이다.
    """
    assert "spec_width" not in set(COPY_TARGET_BY_KEY.values())


def test_size_and_layout_keys_deliberately_have_no_target():
    """``사이즈``·``서랍``·``수납구성`` 값은 **복사 전용**이다 (일부러 비운 자리).

    이 칩들은 사람이 읽고 판단할 재료일 뿐 어느 칸의 정본도 아니다. 여기에 칸 이름이
    붙으면 위 3,720mm 사고가 그대로 난다.
    """
    assert _pairs("사이즈: 150（무몰딩）") == [("150（무몰딩）", "")]
    assert _pairs("서랍: 1단(소)") == [("1단(소)", "")]
    assert _pairs("수납구성: TYPE A") == [("TYPE A", "")]
    assert _pairs("피닉스바") == [("피닉스바", "")]


# --------------------------------------------------------------------------- #
# 전각 짝 파싱 (계약 §3 — 의도된 동작 변경)
# --------------------------------------------------------------------------- #

def test_full_width_pair_becomes_two_chips_with_their_own_targets():
    """``사이즈 ／ 색상: 180cm ／ 클린 화이트`` 는 칩 **두 개**로 갈린다.

    운영 실사례(2026-09-01 주문 2026090191203001)다. 네이버는 그룹을 반각 ``/`` 로,
    그룹 안의 짝을 전각 ``／`` 로 낸다. 갈라 놓지 않으면 키가 ``사이즈 ／ 색상`` 이라
    색상 칩이 어느 칸에도 못 들어간다 — 담당자가 다시 손으로 옮겨 적는다.
    폭 조각(``180cm``)은 여전히 복사 전용이다.
    """
    assert _pairs("사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입") == [
        ("180cm", ""),
        ("클린 화이트", "color"),
        ("푸쉬타입", "handle"),
    ]


def test_full_width_pair_that_does_not_line_up_stays_one_chip():
    """짝 수가 안 맞으면 **오늘 그대로** 칩 하나다 (자리를 못 믿으니 지어내지 않는다).

    같은 규칙을 :func:`size_option_mm` 이 이미 쓴다 — 짝이 모자라면 그 값은 쓰지 않는다.
    엉뚱한 값에 칸 이름을 다느니 사람이 복사하는 편이 낫다.
    """
    assert _pairs("색상 ／ 사이즈: 클린 화이트") == [("클린 화이트", "")]


# --------------------------------------------------------------------------- #
# copies 무회귀 — 옛 JS 안전장치가 계약이다 (계약 §1)
# --------------------------------------------------------------------------- #

def test_split_option_copies_is_unchanged_for_the_old_callers():
    """``copies`` 는 지금도 **문자열 목록**이다 — 덧붙이기라 옛 JS 가 그대로 그린다."""
    copies = split_option_copies("사이즈: 150（무몰딩）/ 색상: 클린 화이트 / 피닉스바")
    assert copies == ["150（무몰딩）", "클린 화이트", "피닉스바"]
    assert all(isinstance(value, str) for value in copies)


@pytest.mark.parametrize("option_text", _LIVE_OPTION_TEXTS)
def test_chip_values_and_copies_come_from_one_parser(option_text: str):
    """칩 값과 ``copies`` 는 **한 파서**에서 나온다 — 길이·순서가 항상 같다.

    갈리면 화면이 ``copies[i]`` 를 그리면서 ``copy_chips[i]`` 의 칸에 넣는다. 색상 값이
    손잡이 칸에 들어가는 종류의 사고다.
    """
    assert [chip["value"] for chip in option_copy_chips(option_text)] == \
        split_option_copies(option_text)


# --------------------------------------------------------------------------- #
# payload 가 실제로 실어 나른다 (계약 §1)
# --------------------------------------------------------------------------- #

def test_payload_carries_copy_chips_beside_copies(app):
    """본품 행에 ``copy_chips`` 가 ``copies`` **옆에** 실린다(덮어쓰지 않는다).

    이 행이 화면 칩의 재료다. 순서가 어긋나면 사람이 누른 칩과 들어가는 값이 달라진다.
    """
    order = _naver_order(_staff())
    _link(order, _snapshot(
        product_name="라홈 로라 붙박이장 30cm",
        option="제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입",
        quantity=12, amount=800000))

    row = build_dock_payload(db_session, order)["rows"][0]

    assert row["copies"] == ["로라 무몰딩 여닫이", "클린 화이트", "푸쉬타입"]
    assert all(isinstance(value, str) for value in row["copies"]), (
        "copies 가 문자열 목록이 아니다 — 옛 JS 가 '📋 [object Object]' 를 그린다")
    assert row["copy_chips"] == [
        {"value": "로라 무몰딩 여닫이", "target": "product_name"},
        {"value": "클린 화이트", "target": "color"},
        {"value": "푸쉬타입", "target": "handle"},
    ]
    assert [chip["value"] for chip in row["copy_chips"]] == row["copies"]


def test_addon_row_chip_is_a_composition_name_and_gets_no_target(app):
    """추가옵션 행의 이름 칩은 **구성 이름**이라 어느 칸에도 안 들어간다.

    ``… ×12`` 수량 꼬리가 붙은 이름이라 ERP 제품명이 아니다. 여기에 ``product_name``
    을 달면 제품명 칸에 수량이 섞여 들어간다.
    """
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="로라 무몰딩 여닫이 30cm",
                           amount=800000, quantity=12))
    _link(order, _snapshot(product_name="로라 무몰딩 여닫이(푸쉬) 1cm",
                           option="길이추가(1cm)", product_class="추가구성상품",
                           amount=33200, quantity=12))

    rows = build_dock_payload(db_session, order)["rows"]
    addon = [row for row in rows if row["role"] == "addon"][0]

    assert addon["copies"] == ["로라 무몰딩 여닫이(푸쉬) 1cm ×12"]
    assert addon["copy_chips"] == [
        {"value": "로라 무몰딩 여닫이(푸쉬) 1cm ×12", "target": ""}]
