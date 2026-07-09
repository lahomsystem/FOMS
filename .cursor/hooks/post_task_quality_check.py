import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def _load_debug():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from hook_payload_debug import maybe_log_payload, get_payload
        return maybe_log_payload, get_payload
    except Exception as e:
        try:
            from shared_utils import hook_runtime_log
            hook_runtime_log(f"_load_debug failed: {e}", tag="post_task_qc")
        except Exception:
            try:
                sys.stderr.write(f"post_task_qc _load_debug: {e}\n")
            except Exception:
                try:
                    os.write(2, f"post_task_qc _load_debug: {e}\n".encode("utf-8", "replace"))
                except Exception:
                    return lambda *a, **k: None, lambda: {}
        return lambda *a, **k: None, lambda: {}
maybe_log_payload, get_payload = _load_debug()

from shared_utils import extract_project_root, harness_runtime_path, hook_runtime_log, read_recent_edited_files

_DEBOUNCE_FILE = ".post_task_qc_debounce.json"
_DEBOUNCE_SEC = 900.0


def _files_fingerprint(files: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(files)).encode("utf-8")).hexdigest()[:24]


def _debounce_allows_full_reminder(project_root: str, fp: str) -> bool:
    path = harness_runtime_path(project_root, _DEBOUNCE_FILE)
    now = time.time()
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            prev_fp = str(st.get("fp", ""))
            prev_ts = float(st.get("ts", 0))
            if prev_fp == fp and (now - prev_ts) < _DEBOUNCE_SEC:
                return False
    except Exception as e:
        hook_runtime_log(f"debounce read fail-open: {e}", project_root=project_root, tag="post_task_qc")
    return True


def _save_debounce_state(project_root: str, fp: str) -> None:
    path = harness_runtime_path(project_root, _DEBOUNCE_FILE)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fp": fp, "ts": time.time()}, f, ensure_ascii=False, indent=0)
    except Exception as e:
        hook_runtime_log(f"debounce write fail-open: {e}", project_root=project_root, tag="post_task_qc")


def _read_recent_edited_files(project_root, limit=5):
    """EDIT_LOG에서 최근 편집 파일을 반환한다(공용 테이블 파서 위임, 레거시 관용)."""
    return read_recent_edited_files(harness_runtime_path(project_root, "EDIT_LOG.md"), limit=limit)


def _load_find_latest_spec():
    """Load the shared recursive Spec resolver from `tools/harness/`."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        harness_dir = repo_root / "tools" / "harness"
        if str(harness_dir) not in sys.path:
            sys.path.insert(0, str(harness_dir))
        from spec_utils import find_latest_spec  # type: ignore[import-not-found]

        return find_latest_spec
    except Exception as exc:
        hook_runtime_log(f"spec_utils import fail-open: {exc}", tag="post_task_qc")
        return None


def _latest_spec_name(project_root: str) -> str | None:
    find_latest_spec = _load_find_latest_spec()
    if find_latest_spec is None:
        return None
    project_root_path = Path(project_root)
    latest_spec = find_latest_spec(project_root_path)
    if latest_spec is None:
        return None
    specs_root = project_root_path / "docs" / "specs"
    return latest_spec.resolve().relative_to(specs_root.resolve()).as_posix()

_CI_GATE_MARKER = ".cursor_ci_gate_pending.json"
_CI_GATE_STALE_SEC = 3600
_QUICK_TIMEOUT_SEC = 15.0


def _run_quick(project_root: str, branch: str, timeout: float = _QUICK_TIMEOUT_SEC) -> tuple[int, str]:
    """`ci_watch.py --quick` 를 subprocess 로 실행. 반환 (returncode, combined_output).

    논블로킹 루프의 핵심 — afterAgentResponse 에서 CI 상태를 단발 조회한다.
    타임아웃/실행 실패는 예외로 전파해 호출부(_consume_ci_gate_marker)가 fail-open 처리한다.
    """
    cmd = [
        sys.executable,
        os.path.join("tools", "harness", "ci_watch.py"),
        "--quick", "HEAD", branch,
    ]
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _quick_detail(output: str, limit: int = 12) -> str:
    """quick 출력에서 의미 있는 마지막 몇 줄만 뽑아 리마인더에 덧붙인다."""
    lines = [ln.rstrip() for ln in (output or "").splitlines() if ln.strip()]
    return "\n".join(lines[-limit:])


def _manual_ci_gate_message(branch: str) -> str:
    """quick 불가(gh 미준비/타임아웃) 시의 수동 안내(논블로킹 폴백)."""
    command = (
        "python tools/harness/ci_watch.py"
        if branch == "deploy"
        else f"python tools/harness/ci_watch.py HEAD {branch}"
    )
    return (
        f"[CI-GATE] push 감지 ({branch}). 자동 CI 상태 확인 불가 — "
        f"`{command}`를 백그라운드로 실행(블로킹 금지)하거나 `{command} --quick`로 "
        "즉시 상태만 확인하고 작업을 계속하라. exit 1이면 근본 수정 후 재푸시. 이 게이트는 생략 금지."
    )


def _consume_ci_gate_marker(project_root: str) -> str | None:
    """CI 게이트 마커를 소비해 `ci_watch.py --quick` 결과별 리마인더를 만든다(논블로킹).

    afterShellExecution(after_shell_execution.py)이 push 성공 시 기록한 마커를
    소비한다. afterShellExecution 은 관측 전용(주입 불가)이므로 실제 상태 조회·리마인더는
    주입 가능한 이 afterAgentResponse 채널에서 방출한다. 블로킹 완주 대기 없이 quick 단발
    조회 결과로 분기한다:
      - green(0)/실패(1)/불가(3·예외) → 마커 삭제(1회 발화로 종료)
      - 진행 중(4) → 마커 유지 → 다음 afterAgentResponse 에서 자동 재확인(논블로킹 루프)
    stale(1시간 초과) 마커는 quick 실행 없이 조용히 정리한다.
    """
    path = harness_runtime_path(project_root, _CI_GATE_MARKER)
    if not os.path.isfile(path):
        return None
    branch = "deploy"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        ts = float(state.get("ts", 0))
        branch = str(state.get("branch", "deploy"))
        if (time.time() - ts) > _CI_GATE_STALE_SEC:
            os.remove(path)  # stale 정리(발화 없음)
            return None

        rc, output = _run_quick(project_root, branch)
        detail = _quick_detail(output)

        if rc == 4:  # 진행 중 — 마커 유지(다음 턴 자동 재확인), 블로킹 대기 금지
            return (
                f"[CI-GATE] CI 진행 중 ({branch}) — 블로킹 대기 금지, 다른 작업을 계속하라. "
                f"다음 턴에 자동으로 재확인한다.\n{detail}"
            )

        # 최종 상태(green/실패/불가) — 마커 삭제로 루프 종료
        os.remove(path)
        if rc == 0:
            return f"[CI-GATE] ALL GREEN ✓ ({branch}) — CI 통과.\n{detail}"
        if rc == 1:
            return (
                f"[CI-GATE] CI 실패 ({branch}) — 아래 로그를 분석해 근본 원인을 수정한 뒤 "
                f"pre_push_smoke → 재푸시까지 완료하라.\n{detail}"
            )
        return _manual_ci_gate_message(branch)  # rc == 3(gh 미준비) 등 → 수동 안내
    except Exception as e:  # noqa: BLE001 - fail-open + 기록(타임아웃/실행 실패 포함)
        hook_runtime_log(
            f"ci_gate quick fail-open: {type(e).__name__}: {e}",
            project_root=project_root,
            tag="ci_gate",
        )
        try:
            if os.path.isfile(path):
                os.remove(path)  # 무한 재시도 방지 — 예외 시에도 1회로 종료
        except OSError as rm_exc:
            hook_runtime_log(
                f"ci_gate marker remove fail: {rm_exc}", project_root=project_root, tag="ci_gate"
            )
        return _manual_ci_gate_message(branch)


def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)
    maybe_log_payload("afterAgentResponse", payload, project_root)

    messages: list[str] = []

    # 1) push 후 CI 감시 게이트(마커 기반, 1회 발화) — 편집 여부와 무관하게 최우선.
    ci_gate_msg = _consume_ci_gate_marker(project_root)
    if ci_gate_msg:
        messages.append(ci_gate_msg)

    # 2) 셀프 체크 리마인더(디바운스 적용) — 편집된 파일이 있을 때만.
    edited_files = _read_recent_edited_files(project_root)
    if edited_files:
        fp = _files_fingerprint(edited_files)
        if _debounce_allows_full_reminder(project_root, fp):
            file_list_str = "\n".join([f"- {f}" for f in edited_files])

            reminder_msg = f"""
---
[SYSTEM 3: 셀프 체크 리마인더]
방금 수정한 아래 파일들에 대해 스스로 품질을 점검하세요.
{file_list_str}

1. 혹시 에러 처리(try-except, 상태 코드 변환 등)는 누락 없이 추가했나요?
2. 보안상 위험한 부분(하드코딩된 변수, XSS 위험, 쿼리 인젝션 방어)은 없나요?
3. 규칙 매뉴얼(클린 코드, 아키텍처 패턴 등)은 100% 준수했나요?

발견된 문제가 있다면 지적받기 전에 즉시 스스로 보완 및 수정 작업을 진행하세요.
---
"""

            latest_spec = _latest_spec_name(project_root)
            if latest_spec:
                reminder_msg += f"\n4. 현재 작업의 Spec(`docs/specs/{latest_spec}`)이 존재합니다. Spec의 검증 기준도 확인하세요."

            reminder_msg += "\n5. evolution/ 이나 incidents/ 에 새 파일을 추가했다면, `docs/ARCHIVE_INDEX.md`에도 반드시 인덱싱을 추가하세요."

            _save_debounce_state(project_root, fp)
            messages.append(reminder_msg)

    if not messages:
        sys.stdout.write(json.dumps({"continue": True}, ensure_ascii=False))
        return

    output = {
        "continue": True,
        "agentMessage": "\n".join(messages),
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    main()
