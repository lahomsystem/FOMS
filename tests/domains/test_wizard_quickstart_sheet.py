"""아이폰 빠른 시작 시트 계약.

아이폰 사파리는 **사용자 제스처 안에서 일어난 진짜 포커스 변화**에만 자판을 올린다.
마법사 진입은 새 문서를 여는 이동이라 제스처가 없어, 스크립트로는 원리상 자판을 못 띄운다
(2026-09-15, `focus()`·`blur()+focus()` 로 세 번 실패). 그래서 ＋ 를 탭한 **그 제스처
안에서** 지금 화면 위에 고객명 한 칸을 열고 포커스한다.

여기서 지키는 것은 그 원리가 코드에서 깨지지 않게 하는 조건들이다. 실기기에서만 드러나는
규칙이라 한 줄만 잘못 옮겨도 조용히 되돌아간다.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static" / "js" / "foms" / "wizard-quickstart.js"
WIZARD_JS = ROOT / "static" / "js" / "foms" / "wizard.js"
LAYOUT_SCRIPTS = ROOT / "templates" / "partials" / "shared" / "layout_scripts.html"
ERP_PRO_CSS = ROOT / "static" / "css" / "foundation" / "erp-pro.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sheet_is_built_up_front_not_inside_the_tap() -> None:
    """탭 순간에 DOM 을 만들면 제스처 안 동기 포커스가 흔들린다 — 만들기는 로드 때 끝낸다."""
    src = _read(JS)
    init = src.split("function init(", 1)[1].split("\n  }\n", 1)[0]
    assert "buildSheet()" in init, "시트를 로드 시점에 만들지 않는다"
    open_fn = src.split("function open(href)", 1)[1].split("\n  }\n", 1)[0]
    assert "buildSheet" not in open_fn, "탭 핸들러 안에서 DOM 을 만들면 안 된다"
    assert "els.input.focus();" in open_fn


def test_open_is_synchronous_inside_the_tap_handler() -> None:
    """타이머·await 뒤로 미루면 제스처가 끊겨 자판이 안 뜬다."""
    src = _read(JS)
    open_fn = src.split("function open(href)", 1)[1].split("\n  }\n", 1)[0]
    assert "setTimeout" not in open_fn
    assert "await " not in open_fn
    assert "requestAnimationFrame" not in open_fn


def test_sheet_is_ios_only() -> None:
    """안드로이드는 진입 즉시 커서·자판이 이미 된다 — 한 단계를 늘리지 않는다."""
    src = _read(JS)
    assert "function isIosLike(" in src
    init = src.split("function init(", 1)[1].split("\n  }\n", 1)[0]
    assert "!isIosLike()" in init


def test_draft_resume_links_are_left_alone() -> None:
    """초안 이어쓰기는 이미 쓰던 주문을 여는 것이라 고객명을 새로 묻지 않는다."""
    src = _read(JS)
    assert 'indexOf("key=") !== -1) return;' in src


def test_name_travels_out_of_the_url() -> None:
    """고객명이 주소창·기록에 남지 않게 세션 저장소로 건넨다."""
    src = _read(JS)
    assert "sessionStorage.setItem" in src
    assert "customer_name=" not in src, "고객명을 주소에 실으면 기록·공유에 남는다"


def test_wizard_applies_the_name_and_survives_draft_recovery() -> None:
    """초안 복구가 나중에 덮어써도 방금 사람이 친 이름이 이긴다."""
    src = _read(WIZARD_JS)
    assert "function applyQuickstartName()" in src
    assert src.count("applyQuickstartName();") >= 2, (
        "초안 복구 뒤에도 다시 적용하지 않으면 옛 값에 밀린다"
    )
    assert "sessionStorage.removeItem" in src, "한 번 쓰고 지우지 않으면 다음 주문에 새어 나온다"


def test_script_and_style_are_registered_with_cache_pins() -> None:
    """핀 없이 내보내면 브라우저가 옛 파일을 계속 쥔다."""
    scripts = _read(LAYOUT_SCRIPTS)
    line = next(ln for ln in scripts.splitlines() if "wizard-quickstart.js" in ln)
    assert "?v=" in line
    assert "defer" in line
    css = _read(ERP_PRO_CSS)
    assert ".foms-quickstart__panel" in css, "시트 스타일은 CSS 파일에 있어야 한다(인라인 금지)"
    assert "font-size: 16px" in css.split(".foms-quickstart__input", 1)[1][:400], (
        "16px 미만이면 사파리가 포커스 때 화면을 확대한다"
    )


def test_script_is_loaded_outside_the_erp_path_gate() -> None:
    """＋ 버튼은 /erp/ 밖 화면(실측·도면·생산·CS)에도 있다.

    `/erp/` 조건 안에 두면 그 화면들에서 시트가 아예 안 뜬다(2026-09-15 스테이징에서
    실제로 그랬다).
    """
    scripts = _read(LAYOUT_SCRIPTS)
    head, tail = scripts.split("js/foms/wizard-quickstart.js", 1)
    gate = "{% if request.path.startswith('/erp/') %}"
    assert gate not in head.rsplit("{% endif %}", 1)[-1], (
        "스크립트가 /erp/ 경로 조건 안에 있다 — 다른 대시보드의 ＋ 에서 안 걸린다"
    )
