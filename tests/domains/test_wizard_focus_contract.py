"""마법사 자동 포커스의 **iOS 제약**을 코드에 못 박는다.

behavior 테스트가 아니라 소스 계약이다. 이 파일이 지키는 것은 실기기에서만 드러나는
규칙이라, 한 줄만 잘못 옮겨도 조용히 되돌아간다(2026-09-15 사용자 제보로 실제로 겪었다):

* 아이폰 사파리는 **사용자 활성화(제스처) 없이는** 입력 칸에 포커스를 주지 않는다.
  마법사 진입은 새 문서를 여는 일반 이동이라 제스처가 없다 — 그래서 안드로이드는 되고
  아이폰은 안 됐다. 진입 포커스가 실패하면 첫 탭을 빌리는 대비책이 걸려야 한다.
* 단계 전환은 버튼 탭 **제스처 안**이라 되는데, focus() 를 setTimeout/await 뒤로 미루면
  캐럿만 옮겨지고 키보드가 안 뜬다. setStep 바로 다음 줄에서 동기로 불러야 한다.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIZARD_JS = ROOT / "static" / "js" / "foms" / "wizard.js"


def _src() -> str:
    return WIZARD_JS.read_text(encoding="utf-8")


def test_entry_focus_falls_back_to_first_tap_when_the_browser_refuses() -> None:
    """진입 포커스가 먹지 않으면(아이폰) 첫 탭을 빌리는 대비책이 걸려야 한다."""
    src = _src()
    assert "function armFirstTapFocus(" in src
    assert "if (!focusStepFirstField(root, currentStep)) {" in src, (
        "진입 포커스의 성공 여부를 안 보고 넘어가면 아이폰에서 아무 일도 안 일어난다"
    )
    assert "armFirstTapFocus(root, currentStep);" in src


def test_focus_helper_reports_whether_it_actually_took() -> None:
    """`focus()` 호출만으로 성공을 단정하면 안 된다 — 아이폰은 조용히 무시한다."""
    src = _src()
    assert "return document.activeElement === el;" in src


def test_first_tap_fallback_yields_to_a_deliberate_tap() -> None:
    """사용자가 다른 칸·버튼을 직접 겨눴으면 대비책은 물러나야 한다."""
    src = _src()
    block = src.split("function armFirstTapFocus(", 1)[1].split("\n  }\n", 1)[0]
    assert "input, select, textarea, button, a, label" in block
    assert 'root.addEventListener("focusin", disarm, true);' in block, (
        "사용자가 스스로 커서를 놓았는데도 대비책이 살아 있으면 다음 탭에서 칸이 튄다"
    )


def test_step_transition_focus_stays_inside_the_tap_gesture() -> None:
    """setStep 과 focus 사이에 타이머·await 가 끼면 아이폰에서 키보드가 안 뜬다."""
    src = _src()
    calls = [
        i for i, line in enumerate(src.splitlines())
        if "focusStepFirstField(root, currentStep)" in line
    ]
    assert calls, "단계 전환 포커스 호출이 사라졌다"
    lines = src.splitlines()
    for i in calls:
        window = "\n".join(lines[max(0, i - 6):i])
        assert "setTimeout" not in window and "await " not in window, (
            f"{i + 1}행 앞에 비동기가 끼었다 — 제스처가 끊겨 아이폰 키보드가 안 뜬다"
        )


def test_date_pickers_stay_out_of_auto_focus() -> None:
    """날짜 칸 자동 포커스는 네이티브 피커를 열어 화면 절반을 덮는다(3단계 첫 칸)."""
    src = _src()
    block = src.split("FOCUS_SKIP_TYPES = [", 1)[1].split("]", 1)[0]
    for t in ("date", "time", "datetime-local", "month", "week"):
        assert f'"{t}"' in block
