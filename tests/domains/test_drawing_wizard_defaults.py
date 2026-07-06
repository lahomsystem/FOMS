"""도면 마법사 자동 채움 defaults 매핑 단위 테스트 (설계서 §4).

DB가 필요 없는 순수 함수 테스트: fake order(SimpleNamespace) + sd(dict) + fake user.
"""

from types import SimpleNamespace

from foms.services.drawing_wizard_defaults import build_wizard_defaults


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
    assert result["phone"] == "010-9263-9140"
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


def test_defaults_logo_lahom_and_none():
    lahom = build_wizard_defaults(_order(), {"parties": {"manager": {"name": "라홈 이영업"}}}, _user())
    none_logo = build_wizard_defaults(_order(), {"parties": {"manager": {"name": "김영업"}}}, _user())

    assert lahom["logo"] == "lahom"
    assert none_logo["logo"] == "none"


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


def test_defaults_drew_blank_when_no_user():
    result = build_wizard_defaults(_order(), {}, None)

    assert result["drew"] == ""
    assert result["manager_phone"] == "-"
