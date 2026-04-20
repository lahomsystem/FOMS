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

from shared_utils import extract_project_root, harness_runtime_path, hook_runtime_log

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
    edit_log_path = harness_runtime_path(project_root, "EDIT_LOG.md")
    if not os.path.exists(edit_log_path):
        return []

    files = []
    seen = set()
    with open(edit_log_path, "r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not (line.startswith("- `") and "` <-" in line):
                continue
            try:
                file_name = line.split("`")[1]
            except Exception:
                continue
            if file_name in seen:
                continue
            seen.add(file_name)
            files.append(file_name)
            if len(files) >= limit:
                break
    return files


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

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)
    maybe_log_payload("afterAgentResponse", payload, project_root)

    edited_files = _read_recent_edited_files(project_root)
    if not edited_files:
        sys.stdout.write(json.dumps({"continue": True}))
        return

    fp = _files_fingerprint(edited_files)
    if not _debounce_allows_full_reminder(project_root, fp):
        sys.stdout.write(json.dumps({"continue": True}, ensure_ascii=False))
        return

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

    output = {
        "continue": True,
        "agentMessage": reminder_msg
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    main()
