import hashlib
import json
import os
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


def _consume_ci_gate_marker(project_root: str) -> str | None:
    """CI 게이트 마커가 있고 최근(1시간 내)이면 리마인더를 만들고 마커를 삭제한다.

    afterShellExecution(after_shell_execution.py)이 push 성공 시 기록한 마커를
    소비한다. 삭제로 1회만 발화하며, stale(1시간 초과) 마커는 조용히 정리한다.
    afterShellExecution 은 관측 전용(에이전트 주입 불가)이므로, 실제 리마인더는
    주입 가능한 afterAgentResponse 채널(이 훅)에서 방출한다.
    """
    path = harness_runtime_path(project_root, _CI_GATE_MARKER)
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        os.remove(path)  # 1회 발화
        ts = float(state.get("ts", 0))
        branch = str(state.get("branch", "deploy"))
        if (time.time() - ts) > 3600:
            return None
        command = (
            "python tools/harness/ci_watch.py"
            if branch == "deploy"
            else f"python tools/harness/ci_watch.py HEAD {branch}"
        )
        return (
            f"[CI-GATE] push 감지 ({branch}). 지금 `{command}`를 실행해 CI 완료를 확인하라. "
            "exit 1이면 실패 로그를 분석해 근본 수정 후 재푸시까지 완료해야 한다. 이 게이트는 생략 금지."
        )
    except Exception as e:  # noqa: BLE001 - fail-open + 기록
        hook_runtime_log(
            f"ci_gate marker read fail-open: {e}", project_root=project_root, tag="ci_gate"
        )
        return None


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
