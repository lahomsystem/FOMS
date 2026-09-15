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


def test_entry_arms_the_first_tap_unconditionally() -> None:
    """첫 탭 예약은 **조건 없이** 걸려야 한다.

    1차 시도는 `document.activeElement` 로 포커스가 먹었는지 보고 실패했을 때만 걸었는데,
    아이폰은 포커스를 주기는 준다 — 키보드만 안 띄운다. 그래서 예약이 아예 안 걸렸고
    사용자에게는 여전히 아무 일도 없었다(2026-09-15 2차 제보).
    """
    src = _src()
    assert "function armEntryKeyboard(" in src
    assert "armEntryKeyboard(root, currentStep);" in src
    assert "if (!focusStepFirstField(root, currentStep)) {" not in src, (
        "포커스 성공 여부로 예약을 가르면 아이폰에서 다시 안 걸린다"
    )


def test_focus_helper_reports_whether_it_actually_took() -> None:
    """`focus()` 호출만으로 성공을 단정하면 안 된다 — 아이폰은 조용히 무시한다."""
    src = _src()
    assert "return document.activeElement === el;" in src


def test_first_tap_yields_to_a_deliberate_tap_and_to_scrolling() -> None:
    """다른 칸을 겨눈 탭·스크롤에는 물러나야 한다."""
    src = _src()
    block = src.split("function armEntryKeyboard(", 1)[1]
    assert "input, select, textarea, button, a, label" in block
    assert "if (moved)" in block, "손가락이 움직인 스크롤에 키보드가 튀어나오면 안 된다"
    assert "if (ev.target !== target) disarm();" in block, (
        "사용자가 스스로 다른 칸에 커서를 놓았는데도 예약이 살아 있으면 다음 탭에서 칸이 튄다"
    )


def test_first_tap_re_focuses_so_the_keyboard_actually_comes_up() -> None:
    """이미 포커스된 칸에 focus() 를 다시 부르면 아무 일도 없다 — blur 를 거쳐야 한다."""
    src = _src()
    block = src.split("function armEntryKeyboard(", 1)[1]
    assert "if (document.activeElement === target) target.blur();" in block


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


def test_tapping_the_already_focused_field_still_raises_the_keyboard() -> None:
    """그 칸 자신을 겨눈 탭에는 물러나면 안 된다.

    진입 시 커서를 미리 놓기 때문에 사파리 눈에는 포커스 변화가 없어 자판이 안 올라온다.
    실사용에서 가장 흔한 탭이 하필 이 경우다(2026-09-15 기기 로그로 확인).
    """
    src = _src()
    block = src.split("function armEntryKeyboard(", 1)[1]
    assert "if (hit && hit !== target) {" in block, (
        "그 칸 자신을 겨눈 탭까지 물러나면 사용자가 칸을 눌러도 자판이 안 뜬다"
    )


def test_keyboard_rescue_only_fires_while_the_keyboard_is_down() -> None:
    """입력 중(자판이 올라온 상태)에 blur→focus 를 하면 캐럿이 튄다."""
    src = _src()
    assert "function bindKeyboardRescue(" in src
    block = src.split("function bindKeyboardRescue(", 1)[1].split("\n  }\n", 1)[0]
    assert "if (base - h > 100) return;" in block, "자판이 올라와 있으면 건드리지 않아야 한다"
    assert "if (document.activeElement !== field) return;" in block
    assert "if (!vp) return;" in block, "판정 수단이 없으면 아예 개입하지 않는다"
