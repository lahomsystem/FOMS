"""도면 마법사 — 단축키 도움말 · 줌(Ctrl+휠·단축키·400%) · 터치 영역 문자열 계약."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
HTML = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")


def test_help_modal_markup_and_button():
    assert 'id="dws-btn-help"' in HTML
    assert 'id="dws-help"' in HTML and 'role="dialog"' in HTML
    assert 'id="dws-help-close"' in HTML
    assert "단축키 도움말" in HTML


def test_help_lists_existing_shortcuts():
    body = HTML.split('id="dws-help"', 1)[1]
    for label in ("저장", "실행취소", "다시 실행", "제자리 복제", "전체 잠금 해제",
                  "화면 옮기기", "줄 바꿈", "화면 폭 맞춤", "100% 보기", "복제하며 이동"):
        assert label in body, label
    for key in ("<kbd>V</kbd>", "<kbd>U</kbd>", "<kbd>P</kbd>", "<kbd>E</kbd>",
                "<kbd>I</kbd>", "<kbd>T</kbd>", "<kbd>J</kbd>", "<kbd>Space</kbd>"):
        assert key in body, key


def test_help_js_open_close_and_question_key():
    assert "function openHelp()" in JS and "function closeHelp()" in JS
    assert "e.key === '?'" in JS
    assert "if (isHelpOpen())" in JS


def test_tool_titles_have_shortcut_keys():
    for t in ("선택 · 이동 (V)", "텍스트 추가 (T)", "도형 그리기 (U)", "이미지 추가 (I)"):
        assert t in HTML, t


def test_zoom_max_400_everywhere():
    assert 'max="400"' in HTML and 'max="250"' not in HTML
    assert "ZOOM_MIN = 0.5, ZOOM_MAX = 4" in JS
    assert "clamp(pct, 50, 400)" in JS
    assert "0.5, 2.5)" not in JS


def test_ctrl_wheel_and_zoom_shortcuts():
    assert "!e.altKey && !e.ctrlKey && !e.metaKey" in JS
    assert "{ passive: false }" in JS
    assert "fitZoom(); return;" in JS
    assert "setZoom(1); return;" in JS
    assert "zoomByStep(0.1)" in JS and "zoomByStep(-0.1)" in JS


def test_coarse_pointer_touch_targets():
    block = CSS.split("@media (pointer: coarse) {")[-1]
    for sel in (".dws-tab-x::before", ".dws-tab-dup::before", ".dws-products-toggle::before",
                ".dws-photos-toggle::before", ".dws-pending-toggle::before", ".dws-del-saved::before"):
        assert sel in block, sel
    assert "width: 36px;" in block and "height: 36px;" in block
    assert "opacity: 1;" in block


def test_no_inline_style_in_help():
    body = HTML.split('id="dws-help"', 1)[1].split("토스트", 1)[0]
    assert "style=" not in body


def test_dialogs_and_help_overlay_are_not_nested():
    """병합 사고 회귀: 닫는 태그가 빠져 도움말 오버레이가 자동 채움 <dialog> 안에 갇히면 화면에 안 보인다."""
    import re
    from html.parser import HTMLParser
    src = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", "", Path("templates/drawing/wizard.html").read_text(encoding="utf-8"), flags=re.S)
    void = {"br", "img", "input", "meta", "link", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.errors, self.nested = [], [], []

        def handle_starttag(self, tag, attrs):
            if tag in void:
                return
            el_id = dict(attrs).get("id")
            if (tag == "dialog" or el_id == "dws-help") and any(t == "dialog" for t, _ in self.stack):
                self.nested.append(el_id)
            self.stack.append((tag, el_id))

        def handle_endtag(self, tag):
            if tag in void:
                return
            if self.stack and self.stack[-1][0] == tag:
                self.stack.pop()
            else:
                self.errors.append((tag, self.getpos()[0]))

    p = P()
    p.feed(src)
    assert not p.errors, p.errors
    assert not p.stack, p.stack
    assert not p.nested, p.nested


def test_appbar_title_space_rules_desktop_only():
    css = Path("static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    tpl = Path("templates/drawing/wizard.html").read_text(encoding="utf-8")
    assert '<span class="dws-appbar-title-prefix">도면 마법사 · </span>' in tpl
    assert "@media (min-width: 901px) and (max-width: 1600px)" in css
    assert ".dws-appbar-title-prefix { display: none; }" in css
