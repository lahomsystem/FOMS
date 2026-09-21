from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _js() -> str:
    return (_root() / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")


def test_as_round_chart_dock_accepts_clipboard_capture() -> None:
    """AS 입력 도크는 erporder 처럼 클립보드 캡처를 바로 첨부한다."""
    js = _js()

    assert "function dockClipboardImageFiles(event)" in js
    # 이미지 item 만 첨부 — 텍스트 붙여넣기는 막지 않는다.
    assert "item.kind !== 'file'" in js
    assert "String(item.type || '').indexOf('image/') !== 0" in js
    # 도크 밖 붙여넣기는 건드리지 않는다(스코프 제한).
    assert "closest('.as-rchart-dock')" in js
    assert "if (ctl) ctl.addFiles(files);" in js


def test_as_round_chart_dock_paste_has_visual_feedback() -> None:
    """붙여넣기 순간의 피드백 — 안내 문구와 깜빡임 클래스가 함께 있어야 뜻이 통한다."""
    root = _root()
    js = _js()
    template = (root / "templates/cs/partials/as_round_chart.html").read_text(encoding="utf-8")
    css = (root / "static/css/components/foms-as-round-chart.css").read_text(encoding="utf-8")

    assert "as-rchart-dock__hint" in template
    assert "Ctrl+V" in template
    assert "is-paste-hit" in js
    assert ".as-rchart-dock__hint {" in css
    assert ".as-rchart-dock.is-paste-hit {" in css
