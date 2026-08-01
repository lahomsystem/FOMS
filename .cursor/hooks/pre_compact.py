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

from shared_utils import extract_project_root, find_key_recursive, harness_runtime_path, read_recent_edited_files

# 체크포인트 본문 조립은 .claude 쌍둥이와 공유 (tools/harness/status_sections.py).
_TOOLS_HARNESS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
    "harness",
)
if _TOOLS_HARNESS not in sys.path:
    sys.path.append(_TOOLS_HARNESS)
from status_sections import build_compact_checkpoint

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)

    # session_id 원본 유지 — 표시용 8자 절단은 build_compact_checkpoint 내부에서만.
    conv_id = find_key_recursive(payload, ["conversation_id", "conversationId", "session_id", "id"])
    if isinstance(conv_id, list): conv_id = conv_id[0]
    if isinstance(conv_id, dict): conv_id = conv_id.get("id") or str(conv_id)
    conv_id = str(conv_id) if conv_id else "unknown"

    checkpoint_file = harness_runtime_path(project_root, "COMPACT_CHECKPOINT.md")
    os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)

    # EDIT_LOG 파싱·순서는 공용 유틸(테이블 포맷·newest-first)에 위임.
    edit_log_path = harness_runtime_path(project_root, "EDIT_LOG.md")
    recent_edits = [f"- `{name}`" for name in read_recent_edited_files(edit_log_path, limit=10)]

    content = build_compact_checkpoint(project_root, conv_id, recent_edits)

    with open(checkpoint_file, "w", encoding="utf-8") as f:
        f.write(content)

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()
