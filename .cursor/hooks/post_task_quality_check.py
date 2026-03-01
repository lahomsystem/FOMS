import json
import sys
import os

def _load_debug():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from hook_payload_debug import maybe_log_payload, get_payload
        return maybe_log_payload, get_payload
    except Exception:
        return lambda *a, **k: None, lambda: {}
maybe_log_payload, get_payload = _load_debug()

from shared_utils import find_key_recursive

def _read_recent_edited_files(project_root, limit=5):
    edit_log_path = os.path.join(project_root, "docs", "context", "EDIT_LOG.md")
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

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = find_key_recursive(payload, ["workspace_roots", "workspaceRoots"], default=None)
    if isinstance(project_root, list) and project_root:
        project_root = str(project_root[0])
    elif project_root is not None:
        project_root = str(project_root)
    if not project_root or project_root.lower() == "none" or project_root == "unknown":
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    edited_files = _read_recent_edited_files(project_root)
    file_list_str = "\n".join([f"- {f}" for f in edited_files]) if edited_files else "(수정된 파일 없음)"

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

    spec_dir = os.path.join(project_root, "docs", "specs")
    if os.path.exists(spec_dir):
        specs = [f for f in os.listdir(spec_dir) if f.endswith("_SPEC.md") and not f.startswith(".")]
        if specs:
            latest_spec = sorted(specs)[-1]
            reminder_msg += f"\n4. 현재 작업의 Spec(`docs/specs/{latest_spec}`)이 존재합니다. Spec의 검증 기준도 확인하세요."

    reminder_msg += "\n5. evolution/ 이나 incidents/ 에 새 파일을 추가했다면, `docs/ARCHIVE_INDEX.md`에도 반드시 인덱싱을 추가하세요."

    output = {
        "continue": True,
        "agentMessage": reminder_msg
    }
    sys.stdout.write(json.dumps(output))

if __name__ == "__main__":
    main()
