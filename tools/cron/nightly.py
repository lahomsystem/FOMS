"""Nightly FOMS-cron runner — runs each cleanup step as its own process.

Railway builds the FOMS-cron service from the root ``Dockerfile``, and a Dockerfile
service's start command is exec'd **without a shell**. The old start command
``A && B && C`` therefore only ever ran ``A``: the two retention purges never started
(docs/specs/2026-09-29-nightly-cron-single-runner-spec.md). This runner needs no shell —
the start command is just ``python tools/cron/nightly.py``.

Steps are independent: a failing step does not stop the next one (they clean unrelated
tables, and each is batch-committed and advisory-locked, so the next night resumes).
Each step has a timeout because Railway skips the next scheduled run while a previous
one is still running — one hung step would otherwise stop every later night.

Exit 0 only when every step exited 0.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger("nightly")

REPO_ROOT = Path(__file__).resolve().parents[2]
STEP_TIMEOUT_SECONDS = 20 * 60
TIMEOUT_EXIT_CODE = 124
LAUNCH_ERROR_EXIT_CODE = 127


@dataclass(frozen=True)
class NightlyStep:
    """One nightly cleanup: a repo-relative script and its CLI arguments."""

    name: str
    script: str
    args: tuple[str, ...]


# ``--execute`` / ``--apply`` are part of the contract: without them each tool is a
# dry-run that "succeeds" every night while deleting nothing.
#
# 보류(2026-10-05 사용자 결정): 초안 표식 규칙 감시 ``tools/ops/check_draft_flag_invariant.py``
# (읽기만, 위반 시 exit 3)는 운영 숨은 초안 7건을 정리한 뒤에 ``cleanup_order_drafts`` 바로
# 다음 단계로 넣는다. 지금 넣으면 그 7건 때문에 매일 밤 실패로 울린다.
NIGHTLY_STEPS: tuple[NightlyStep, ...] = (
    NightlyStep("cleanup_order_drafts", "tools/cron/cleanup_order_drafts.py", ("--execute",)),
    NightlyStep(
        "purge_order_mutation_receipts",
        "tools/ops/purge_order_mutation_receipts.py",
        ("--retention-days", "7", "--batch-size", "1000", "--apply"),
    ),
    NightlyStep("purge_audit_logs", "tools/ops/purge_audit_logs.py", ("--apply",)),
    # AI 도면팀원 주간 노트 — 그 주 노트가 이미 있으면 아무것도 안 한다(설계서 2026-10-27-drawing-ai-teammate-spec A3).
    NightlyStep("drawing_agent_note", "tools/cron/drawing_agent_note.py", ("--apply",)),
    # AI 상담 [수정하기] 자세한 이유 사진 원본 90일 지우기(설계서 2026-10-27-cs-ai-agent 17.6.1 (b) · D94). 지울 줄이 없으면
    # 저장소를 열지 않는다. 저장소가 R2 가 아니면(이 서비스에 R2 env 없음) 줄을 '지움'으로 적지 않고 실패(exit 3)로 알린다.
    NightlyStep("purge_cs_edit_photos", "tools/cron/purge_cs_edit_photos.py", ("--apply",)),
    # 회사 지식 AI 제안 4주 '기간 끝남' 닫기 · 기준 판 바뀐 열린 제안 표시(설계서 2026-11-02-haud-master-brain 7.7 · D103 · D104).
    # 사람 제안은 닫지 않는다. 닫을 것이 없으면 아무것도 쓰지 않고 exit 0.
    NightlyStep("expire_brain_proposals", "tools/cron/expire_brain_proposals.py", ("--apply",)),
    # 회사 지식 물어보기 기록 1년 지우기(설계서 2026-11-02-haud-master-brain 10.3). 지울 것이 없으면 exit 0.
    NightlyStep("purge_brain_questions", "tools/cron/purge_brain_questions.py", ("--apply",)),
    # 회사 지식 빈 지식 목록 주 1회(10.3 — 설정 '빈 지식 묶기'가 꺼져 있으면(처음 값) 아무것도 안 하고 exit 0,
    # 이번 주 목록이 있으면 exit 0, 켜 놓고 부를 수 없으면 exit 3).
    NightlyStep("brain_chat_gaps", "tools/cron/brain_chat_gaps.py", ("--apply",)),
    # 회사 지식 의미 찾기 벡터 다시 넣기(사장님 D114 — 설정 '의미 찾기'가 꺼져 있으면(처음 값) · 열쇠 env · 돈 상한 · pgvector
    # 표가 없으면 아무것도 안 하고 exit 0, 켜 놓고 부르다 실패하면 exit 3).
    NightlyStep("brain_embed", "tools/cron/brain_embed.py", ("--apply",)),
    # 접목판 ERP 할 일 제안 기간 끝남 닫기 · 되맞추기(설계서 2026-11-14-foms-graft 3.4). 제안이 없으면 아무것도 안 쓰고 exit 0.
    NightlyStep("erp_actions_expire", "tools/cron/erp_actions_expire.py", ("--apply",)),
    # 접목판 운영 AI · 일정 AI 규칙 훑기(3.10 — 제안만, 알림톡 · 푸시 없음). FOMS_GRAFT_PROPOSERS_ENABLED 가 꺼져 있으면(처음 값)
    # 아무것도 안 하고 exit 0. 기간 끝남 닫기 뒤에 돌아 닫힌 자리에 새 제안이 들어설 수 있다.
    NightlyStep("ai_staff_sweep", "tools/cron/ai_staff_sweep.py", ("--apply",)),
)

Runner = Callable[..., subprocess.CompletedProcess]


def run_step(step: NightlyStep, runner: Runner = subprocess.run) -> int:
    """Run one step in a child process (inheriting stdout/stderr) and return its exit code."""
    command = [sys.executable, str(REPO_ROOT / step.script), *step.args]
    try:
        completed = runner(command, cwd=REPO_ROOT, timeout=STEP_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        logger.error("[nightly] step=%s timed out after %ds", step.name, STEP_TIMEOUT_SECONDS)
        return TIMEOUT_EXIT_CODE
    except OSError:
        logger.exception("[nightly] step=%s could not start", step.name)
        return LAUNCH_ERROR_EXIT_CODE
    return completed.returncode


def main(steps: Sequence[NightlyStep] = NIGHTLY_STEPS, runner: Runner = subprocess.run) -> int:
    """Run every step in order; one summary line per step, exit 1 if any step failed."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    failed: list[str] = []
    for step in steps:
        started = time.monotonic()
        code = run_step(step, runner)
        logger.info(
            "[nightly] step=%s rc=%d elapsed=%.1fs", step.name, code, time.monotonic() - started
        )
        if code != 0:
            failed.append(step.name)
    logger.info("[nightly] done steps=%d failed=%s", len(steps), ",".join(failed) or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
