"""Tests for AS content safety helpers."""

import pytest

from foms.services.as_content_safety import (
    as_content_html_to_text,
    load_structured_data_dict_or_raise,
    sanitize_as_content_html,
)


def test_sanitize_as_content_html_preserves_only_supported_rich_markup() -> None:
    raw_html = """
    <!-- remove me -->
    <div class="wrapper">
        시작
        <span style="color: #ff0000; font-weight: bold;">강조</span>
        <font color="blue" size="3">파랑</font>
        <a href="https://example.com">링크</a>
    </div>
    """

    sanitized = sanitize_as_content_html(raw_html)

    assert "<!--" not in sanitized
    assert 'class=' not in sanitized
    assert '<a' not in sanitized
    assert 'href=' not in sanitized
    assert '<span style="color: red;">강조</span>' in sanitized
    assert '<font color="blue">파랑</font>' in sanitized
    assert '링크' in sanitized


def test_as_content_html_to_text_normalizes_line_breaks() -> None:
    html = "<div>첫째<br/>둘째</div><ul><li>셋째</li></ul>"

    text = as_content_html_to_text(html)

    assert text == "첫째\n둘째\n셋째"


def test_load_structured_data_dict_or_raise_returns_deepcopied_dict() -> None:
    original = {"shipment": {"as_content": "메모"}}

    loaded = load_structured_data_dict_or_raise(original)
    loaded["shipment"]["as_content"] = "변경"

    assert original["shipment"]["as_content"] == "메모"


def test_load_structured_data_dict_or_raise_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON dict"):
        load_structured_data_dict_or_raise('["not", "dict"]')


def test_load_structured_data_dict_or_raise_propagates_invalid_json_error() -> None:
    with pytest.raises(ValueError):
        load_structured_data_dict_or_raise("{broken")
