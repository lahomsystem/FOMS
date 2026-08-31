"""운영 worker 재배포 안전 판정 계약 (NVREPAY-05 후속).

**왜 필요한가**: 운영 worker 는 1대라 재배포 = 큐 전면 정지다. 2026-08-31 에 자동 조회 주기를
바꾸며 재배포했더니 실사용자가 14분 전에 넣은 47집 요청이 그만큼 밀렸다(첫 스탬프 +852초).
"돌고 있나"를 물어볼 자리가 사람 기억밖에 없어서 생긴 사고다.

이 파일이 무는 것: **모르면 멈춘다**(판정 불가는 안전이 아니다), 진행 중이거나 큐에 일이 남아
있으면 재배포 금지, 그리고 화면과 같은 함수로 진행을 판정한다는 것.
"""

from __future__ import annotations

from pathlib import Path

from tools.ops.check_worker_redeploy_safe import main, verdict

REPO_ROOT = Path(__file__).resolve().parents[3]

IDLE = {"queued": 0, "started": 0}


def test_idle_worker_is_safe_to_redeploy():
    """진행 중도 없고 큐도 비면 재배포해도 된다."""
    code, lines = verdict(None, IDLE)

    assert code == 0
    assert any("재배포해도 된다" in line for line in lines)


def test_running_refresh_blocks_redeploy():
    """돌고 있는 전체 다시 읽기가 있으면 막는다 — 누가 눌렀는지까지 말한다."""
    code, lines = verdict({"actor": "이시영", "total": 47, "done": 12,
                           "elapsed_seconds": 30, "eta": "약 1~2분"}, IDLE)

    assert code == 1
    assert any("이시영" in line and "47주문 중 12주문" in line for line in lines)
    assert any("재배포하지 마라" in line for line in lines)


def test_queued_jobs_block_redeploy_even_without_a_refresh():
    """전체 다시 읽기가 아니어도 큐에 일이 남아 있으면 막는다.

    큐에는 알림톡·발주확인 등 다른 일도 들어간다 — 다시 읽기만 보면 그것들을 통째로 놓친다.
    """
    code, lines = verdict(None, {"queued": 3, "started": 1})

    assert code == 1
    assert any("3건 대기" in line and "1건 실행 중" in line for line in lines)


def test_missing_urls_are_not_reported_as_safe(capsys):
    """URL 을 모르면 **판정 불가(2)** 다 — 0 을 주면 모르는 채로 재배포된다."""
    assert main(["--database-url", "", "--redis-url", ""]) == 2


def test_guard_reuses_the_screen_predicate():
    """진행 판정을 두 벌로 만들지 않는다 — 화면이 쓰는 함수를 그대로 부른다."""
    source = (REPO_ROOT / "tools" / "ops" / "check_worker_redeploy_safe.py").read_text(
        encoding="utf-8")

    assert "running_refresh_all" in source
    assert "security_logs" not in source, "SQL 을 여기서 다시 쓰면 판정이 갈린다"
