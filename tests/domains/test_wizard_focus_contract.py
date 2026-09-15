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


def test_focus_helper_reports_whether_it_actually_took() -> None:
    """`focus()` 호출만으로 성공을 단정하면 안 된다 — 아이폰은 조용히 무시한다."""
    src = _src()
    assert "return document.activeElement === el;" in src


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


def test_entry_focus_is_skipped_on_ios() -> None:
    """아이폰에서는 진입 자동 포커스를 **하지 않는다.**

    사파리는 제스처 안에서 일어난 진짜 포커스 변화에만 자판을 올린다. 진입 시 미리
    포커스를 줘 버리면 그 뒤 사용자가 그 칸을 탭해도 포커스 변화가 없어 자판이 영영
    안 올라온다 — 우리가 넣은 편의 기능이 원래 되던 동작을 망가뜨린 것이다
    (2026-09-15 제보 4회, 2단계 제품명은 멀쩡히 되는 것이 대조군이었다).
    """
    src = _src()
    assert "function isIosLike(" in src
    assert "if (!isIosLike()) {" in src, "아이폰에서 진입 포커스를 건너뛰는 분기가 없다"
    # 재주(강제 blur→focus)로 되돌리려던 구조는 남아 있으면 안 된다.
    assert "armEntryKeyboard" not in src
    assert "bindKeyboardRescue" not in src


def test_step_transition_focus_is_not_gated_by_platform() -> None:
    """단계 전환은 버튼 탭 제스처 안이라 아이폰에서도 자판이 뜬다 — 막지 않는다."""
    src = _src()
    body = src.split("#foms-wizard-next", 1)[1]
    assert "focusStepFirstField(root, currentStep);" in body
