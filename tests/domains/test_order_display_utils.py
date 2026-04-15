"""Tests for order display helpers."""

from foms.services.order_display_utils import _ensure_dict, format_options_for_display


def test_ensure_dict_parses_stringified_json_and_falls_back_to_empty_dict() -> None:
    assert _ensure_dict({"name": "라홈"}) == {"name": "라홈"}
    assert _ensure_dict('{"name": "라홈"}') == {"name": "라홈"}
    assert _ensure_dict("not-json") == {}
    assert _ensure_dict(None) == {}


def test_format_options_for_display_renders_direct_option_details() -> None:
    options_json = (
        '{"option_type":"direct","details":{"product_name":"붙박이장","color":"화이트","handle":"골드"}}'
    )

    rendered = format_options_for_display(options_json)

    assert rendered == "제품명: 붙박이장, 색상: 화이트, 손잡이: 골드"


def test_format_options_for_display_preserves_online_summary_line_breaks_as_br() -> None:
    options_json = '{"option_type":"online","online_options_summary":"발주사 : 라홈\\n규격 : 1800"}'

    rendered = format_options_for_display(options_json)

    assert rendered == "발주사 : 라홈<br>규격 : 1800"


def test_format_options_for_display_supports_legacy_korean_keys() -> None:
    options_json = '{"제품명":"붙박이장","색상":"화이트"}'

    rendered = format_options_for_display(options_json)

    assert rendered == "제품명: 붙박이장, 색상: 화이트"


def test_format_options_for_display_returns_original_string_on_invalid_json() -> None:
    options_json = "{broken"

    rendered = format_options_for_display(options_json)

    assert rendered == "{broken"
