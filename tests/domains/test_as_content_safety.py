"""Tests for AS content safety helpers."""

import pytest

from foms.services.as_content_safety import (
    as_content_html_to_text,
    combined_as_content_text,
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


def test_sanitize_escapes_unterminated_tag_at_top_level() -> None:
    """미종결 태그는 원문 통과 금지 — 렌더 측 |safe + 뒤 마크업이 태그를 완성해 실행된다.

    top-level 텍스트 노드를 str()로 이어붙이면 이스케이프가 걸리지 않아
    `hi <img src=x onerror=alert(9);//` 가 그대로 저장·출력됐다.
    """
    sanitized = sanitize_as_content_html("hi <img src=x onerror=alert(9);//")

    assert "<img" not in sanitized
    assert sanitized == "hi &lt;img src=x onerror=alert(9);//"


def test_sanitize_unterminated_tag_is_parser_version_independent() -> None:
    """미종결 조각은 파서에 닿기 전에 이스케이프된다 — 어느 Python에서도 텍스트가 보존된다.

    html.parser의 EOF 미종결 태그 처리는 패치 버전마다 다르다(3.12.10=데이터로 유지,
    3.12.13=태그로 취급). 허용 태그 조각(`<b`)이면 태그 취급된 쪽에서 내용 없는 태그로
    지워져 사용자 텍스트가 조용히 사라졌다(XSS는 아니지만 데이터 유실).
    """
    assert sanitize_as_content_html("hi <b") == "hi &lt;b"
    assert sanitize_as_content_html("메모 <div") == "메모 &lt;div"

    # 이스케이프 결과를 다시 통과시켜도 누적 이스케이프가 없어야 한다(저장→편집→재저장 경로).
    once = sanitize_as_content_html("hi <img src=x onerror=alert(9);//")
    assert sanitize_as_content_html(once) == once


def test_sanitize_escapes_bare_angle_and_ampersand_in_text() -> None:
    """허용 태그는 보존하면서 인접 평문의 `<`/`&`만 이스케이프한다."""
    sanitized = sanitize_as_content_html("<b>굵게</b> a < b & c")

    assert sanitized == "<b>굵게</b> a &lt; b &amp; c"


def test_as_content_html_to_text_normalizes_line_breaks() -> None:
    html = "<div>첫째<br/>둘째</div><ul><li>셋째</li></ul>"

    text = as_content_html_to_text(html)

    assert text == "첫째\n둘째\n셋째"


def test_combined_as_content_text_merges_tabs_and_notes_fallback() -> None:
    sd = {
        "shipment": {
            "as_content": "<div>탭1</div>",
        },
    }
    assert combined_as_content_text(sd, notes_fallback="노트 폴백") == "탭1\n\n노트 폴백"

    sd_tab2 = {
        "shipment": {
            "as_content": "<div>탭1</div>",
            "as_content_2": "<div>탭2</div>",
        },
    }
    assert combined_as_content_text(sd_tab2) == "탭1\n\n탭2"


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
