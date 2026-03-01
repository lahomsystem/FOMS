import json
import sys
import os
from datetime import datetime

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

from shared_utils import find_key_recursive, extract_project_root

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)

    conv_id = find_key_recursive(payload, ["conversation_id", "conversationId", "session_id", "id"])
    if isinstance(conv_id, list): conv_id = conv_id[0]
    if isinstance(conv_id, dict): conv_id = conv_id.get("id") or str(conv_id)
    conv_id = str(conv_id)[:8] if conv_id and str(conv_id) != "unknown" else "unknown"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    checkpoint_dir = os.path.join(project_root, "docs", "context")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_file = os.path.join(checkpoint_dir, "COMPACT_CHECKPOINT.md")

    edit_log_path = os.path.join(checkpoint_dir, "EDIT_LOG.md")
    recent_edits = []
    if os.path.exists(edit_log_path):
        with open(edit_log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("- `"):
                    recent_edits.append(line.rstrip())
                    if len(recent_edits) >= 10:
                        break

    # AI_STATUS.md에서 "진행 중" 섹션 읽기
    ai_status_path = os.path.join(project_root, "docs", "AI_STATUS.md")
    active_tasks = []
    if os.path.exists(ai_status_path):
        in_progress = False
        with open(ai_status_path, "r", encoding="utf-8") as f:
            for line in f:
                if "## 진행 중" in line:
                    in_progress = True
                    continue
                if in_progress and line.startswith("## "):
                    break
                if in_progress and line.strip() and line.strip() != "(없음)":
                    active_tasks.append(line.rstrip())

    content = f"""# Context Compact Checkpoint

> **경고**: 컨텍스트 압축이 발생했습니다. 이 파일을 읽어 이전 작업을 복원하세요.
> 생성 시각: {timestamp}
> 세션: {conv_id}

## 압축 직전 상태

### 최근 편집된 파일
{chr(10).join(recent_edits) if recent_edits else '(없음)'}

### 진행 중이던 작업
{chr(10).join(active_tasks) if active_tasks else '(없음)'}

## 복원 지침

1. `docs/AI_STATUS.md` 읽기 → 전체 프로젝트 상태 파악 (50줄)
2. `docs/AI_CHANGELOG.md` 읽기 → 최근 작업 이력 확인
3. `docs/context/DECISIONS.md` 읽기 → 이전 결정사항 확인
4. `docs/ARCHIVE_INDEX.md` 읽기 → 과거 장애/분석 기록 검색 (키워드 기반)
5. `docs/context/EDIT_LOG.md` 읽기 → 최근 편집 파일 확인
6. 핵심 코어 변경 작업이면 RPI 프로토콜(조사→계획→실행)을 따를 것
"""

    with open(checkpoint_file, "w", encoding="utf-8") as f:
        f.write(content)

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()
