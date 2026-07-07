"""도면 마법사 자동 채움 defaults 매핑 단위 테스트 (설계서 §4).

DB가 필요 없는 순수 함수 테스트: fake order(SimpleNamespace) + sd(dict) + fake user.
"""

from types import SimpleNamespace

import pytest

from foms.services import erp_mobile_order_display as _display_mod
from foms.services.drawing_wizard_defaults import (
    build_wizard_defaults,
    resolve_assignee_drew_en,
)


@pytest.fixture(autouse=True)
def _stub_manager_phone_lookup(monkeypatch):
    """담당 연락처 설정 룩업을 기본 '없음'으로 스텁한다(단위 테스트 DB I/O 차단).

    ``build_wizard_defaults`` 는 ``manager.phone`` 이 없을 때 큐 리졸버를 지연
    import해 호출한다. 기본값은 빈 문자열(매핑 없음)이며, 룩업 성공 케이스는
    개별 테스트에서 monkeypatch로 이 스텁을 덮어쓴다.
    """
    monkeypatch.setattr(
        _display_mod,
        "resolve_manager_phone_for_queue",
        lambda parties, *, manager_name="", order=None, manager_phone_map=None: "",
    )


def _order(**kwargs):
    kwargs.setdefault("erp_construction_date", None)
    kwargs.setdefault("manager_name", None)
    return SimpleNamespace(**kwargs)


def _user(name="최상용"):
    return SimpleNamespace(name=name, role="ADMIN", team="DRAWING", id=1)


def test_defaults_maps_full_structured_data():
    sd = {
        "schedule": {"construction": {"date": "2026-07-09"}},
        "parties": {
            "customer": {"name": "서으뜸", "phone": "01092639140"},
            "manager": {"name": "하우드 김성일", "phone": ""},
        },
        "site": {"address_full": "대구 희망로 24길 24"},
        "items": [
            {
                "product_name": "여단이 붙박이장",
                "color": "클린화이트",
                "width": "3500",
                "depth": "620",
                "height": "2300",
                "handle": "피닉스바 아이보리",
                "internal": "657*6",
                "misc": "멀티탭 고객 준비",
                "spec_rows": [{"spec_width": "3500"}],
            }
        ],
    }

    result = build_wizard_defaults(_order(), sd, _user("최상용"))

    assert result["construction_date"] == "7월 9일"
    assert result["customer_name"] == "서으뜸"
    assert result["phone"] == "9263-9140"
    assert result["address"] == "대구 희망로 24길 24"
    assert result["product_name"] == "여단이 붙박이장"
    assert result["color"] == "클린화이트"
    assert result["site_spec"] == "3500×620×2300"
    assert result["spec_w300"] == str(round(3500 / 300, 1))  # 11.7
    assert result["handle"] == "피닉스바 아이보리"
    assert result["drawer"] == "657*6"
    assert result["misc"] == "멀티탭 고객 준비"
    assert result["sales_manager"] == "하우드 김성일"
    assert result["manager_phone"] == "-"
    assert result["logo"] == "haud"
    assert result["drew"] == "최상용"
    assert result["page_no"] == "-"
    assert result["checks"] == {
        "d_site": False,
        "d_double": False,
        "d_order": False,
        "p_prod": False,
        "p_glass": False,
        "p_light": False,
        "p_handle": False,
        "p_etc": False,
    }


def test_defaults_blanks_consultation_placeholder():
    sd = {
        "items": [
            {
                "product_name": "가구",
                "color": "상담",
                "handle": " 상담 ",
                "internal": "상담",
                "misc": "상담",
                "option_detail": "상담",
            }
        ]
    }

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["color"] == ""
    assert result["handle"] == ""
    assert result["drawer"] == ""
    assert result["misc"] == ""


def test_defaults_all_blank_when_no_items():
    sd = {"parties": {"customer": {"name": "홍길동"}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["product_name"] == ""
    assert result["color"] == ""
    assert result["site_spec"] == ""
    assert result["spec_w300"] == ""
    assert result["handle"] == ""
    assert result["drawer"] == ""
    assert result["misc"] == ""
    assert result["customer_name"] == "홍길동"


def test_defaults_logo_lahom_only_else_haud():
    """발주사명에 '라홈' 포함 → lahom, 그 외 전부(하우드/기타/미지정) → haud."""
    lahom = build_wizard_defaults(_order(), {"parties": {"manager": {"name": "라홈 이영업"}}}, _user())
    haud = build_wizard_defaults(_order(), {"parties": {"manager": {"name": "하우드 김성일"}}}, _user())
    other = build_wizard_defaults(_order(), {"parties": {"manager": {"name": "김성일 실장"}}}, _user())
    blank = build_wizard_defaults(_order(), {"parties": {}}, _user())

    assert lahom["logo"] == "lahom"
    assert haud["logo"] == "haud"
    assert other["logo"] == "haud"
    assert blank["logo"] == "haud"


def test_defaults_construction_date_falls_back_to_order_column():
    sd = {"schedule": {"construction": {"date": ""}}}

    result = build_wizard_defaults(_order(erp_construction_date="2026-09-10"), sd, _user())

    assert result["construction_date"] == "9월 10일"


def test_defaults_construction_date_joins_multiple_comma_items():
    sd = {"schedule": {"construction": {"date": "2026-07-09, 2026-07-10"}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["construction_date"] == "7월 9일, 7월 10일"


def test_defaults_site_spec_falls_back_to_spec_text_when_dims_missing():
    sd = {"items": [{"spec": "현장 실측 예정"}]}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["site_spec"] == "현장 실측 예정"


def test_defaults_sales_manager_falls_back_to_order_manager_name():
    result = build_wizard_defaults(_order(manager_name="박실장"), {"parties": {}}, _user())

    assert result["sales_manager"] == "박실장"


def test_defaults_product_name_joins_nonempty_only():
    sd = {"items": [{"product_name": "장A"}, {"product_name": ""}, {"product_name": "장B"}]}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["product_name"] == "장A / 장B"


def test_defaults_phone_blank_when_missing():
    sd = {"parties": {"customer": {"name": "홍길동"}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["phone"] == ""


def test_defaults_manager_phone_uses_structured_phone_stripping_010():
    """parties.manager.phone가 있으면 그 값을 '010' 제거 포맷으로 쓴다(룩업 생략)."""
    sd = {"parties": {"manager": {"name": "하우드 김성일", "phone": "01011112222"}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["manager_phone"] == "1111-2222"


def test_defaults_manager_phone_falls_back_to_queue_lookup(monkeypatch):
    """manager.phone가 없으면 큐 리졸버 룩업값을 '010' 제거 포맷으로 쓴다."""
    monkeypatch.setattr(
        _display_mod,
        "resolve_manager_phone_for_queue",
        lambda parties, *, manager_name="", order=None, manager_phone_map=None: "01033334444",
    )
    sd = {"parties": {"manager": {"name": "하우드 김성일", "phone": ""}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["manager_phone"] == "3333-4444"


def test_defaults_manager_phone_dash_when_no_phone_and_no_lookup():
    """manager.phone도 룩업도 없으면 '-'를 유지한다(스텁 기본값 = 빈 문자열)."""
    sd = {"parties": {"manager": {"name": "하우드 김성일", "phone": ""}}}

    result = build_wizard_defaults(_order(), sd, _user())

    assert result["manager_phone"] == "-"


def test_defaults_drew_blank_when_no_user():
    result = build_wizard_defaults(_order(), {}, None)

    assert result["drew"] == ""
    assert result["manager_phone"] == "-"


def _patch_drawing_manager_en(monkeypatch, en_map):
    """설정 로더를 monkeypatch해 ``drawing_manager_en`` 매핑만 주입한다 (DB I/O 차단)."""
    from foms.services import drawing_wizard_defaults as mod

    monkeypatch.setattr(
        mod, "load_erp_shipment_settings", lambda: {"drawing_manager_en": en_map}
    )


def test_defaults_drew_maps_assignee_korean_to_english(monkeypatch):
    """도면 담당자 한글명이 설정 영문명으로 매핑되면 DREW는 영문명이 된다."""
    _patch_drawing_manager_en(monkeypatch, {"김한비": "KIM HANBI"})
    sd = {"drawing_assignees": [{"id": 7, "name": "김한비"}]}

    result = build_wizard_defaults(_order(), sd, _user("최상용"))

    assert result["drew"] == "KIM HANBI"


def test_defaults_drew_falls_back_to_korean_when_no_english_mapping(monkeypatch):
    """영문 매핑이 없으면 담당자 한글명으로 폴백한다(현재 사용자명 아님)."""
    _patch_drawing_manager_en(monkeypatch, {})
    sd = {"drawing_assignees": [{"id": 7, "name": "김한비"}]}

    result = build_wizard_defaults(_order(), sd, _user("최상용"))

    assert result["drew"] == "김한비"


def test_defaults_drew_falls_back_to_current_user_when_no_assignee(monkeypatch):
    """도면 담당자 미지정이면 current_user.name으로 폴백하고 설정 로더는 호출하지 않는다."""
    from foms.services import drawing_wizard_defaults as mod

    def _boom():
        raise AssertionError("담당자 미지정 시 설정 로더를 호출하면 안 된다")

    monkeypatch.setattr(mod, "load_erp_shipment_settings", _boom)

    result = build_wizard_defaults(_order(), {}, _user("최상용"))

    assert result["drew"] == "최상용"


def test_resolve_assignee_drew_en_returns_english_when_mapping_exists(monkeypatch):
    """담당자 지정 + 영문 매핑 성공 → 영문명 반환."""
    _patch_drawing_manager_en(monkeypatch, {"김한비": "KIM HANBI"})
    sd = {"drawing_assignees": [{"id": 7, "name": "김한비"}]}

    assert resolve_assignee_drew_en(sd) == "KIM HANBI"


def test_resolve_assignee_drew_en_blank_when_no_mapping(monkeypatch):
    """담당자 지정됐어도 영문 매핑이 없으면 빈 문자열(한글명 폴백 안 함)."""
    _patch_drawing_manager_en(monkeypatch, {})
    sd = {"drawing_assignees": [{"id": 7, "name": "김한비"}]}

    assert resolve_assignee_drew_en(sd) == ""


def test_resolve_assignee_drew_en_blank_when_no_assignee(monkeypatch):
    """담당자 미지정이면 빈 문자열이며 설정 로더는 호출하지 않는다."""
    from foms.services import drawing_wizard_defaults as mod

    def _boom():
        raise AssertionError("담당자 미지정 시 설정 로더를 호출하면 안 된다")

    monkeypatch.setattr(mod, "load_erp_shipment_settings", _boom)

    assert resolve_assignee_drew_en({}) == ""
