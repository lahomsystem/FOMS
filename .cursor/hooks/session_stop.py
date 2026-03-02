import json
import os
import re
import sys
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

def _read_recent_edited_files(project_root, limit=10):
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

def _replace_or_append_line(block, label, value):
    pattern = rf"(?m)^- \*\*{re.escape(label)}\*\*: .*$"
    new_line = f"- **{label}**: {value}"
    if re.search(pattern, block):
        return re.sub(pattern, new_line, block, count=1)
    if not block.endswith("\n"):
        block += "\n"
    return block + new_line + "\n"

def _find_target_match(content, conv_id):
    block_pattern = r"(?ms)(^### Session: (?P<sid>[^\n]+)\n)(?P<body>.*?)(?=^### Session: |\Z)"
    matches = list(re.finditer(block_pattern, content))
    if not matches:
        return None
    if conv_id != "unknown":
        for match in matches:
            if match.group("sid").strip() == conv_id:
                return match
    for match in matches:
        body = match.group("body")
        if "- **종료**: -" in body or "- **상태**: 진행중" in body:
            return match
    return matches[0] if matches else None

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)

    maybe_log_payload("stop", payload, project_root)

    conv_id = find_key_recursive(payload, [
        "conversation_id", "conversationId", "session_id", "sessionId", "id",
        "chatId", "chat_id", "threadId", "thread_id", "conversationId"
    ])
    if isinstance(conv_id, list): conv_id = conv_id[0]
    if isinstance(conv_id, dict): conv_id = conv_id.get("id") or str(conv_id)
    conv_id = str(conv_id)[:8] if conv_id and str(conv_id) != "unknown" else "unknown"

    status = find_key_recursive(payload, ["status"], default="unknown")
    ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    session_log = os.path.join(project_root, "docs", "context", "SESSION_LOG.md")
    if os.path.exists(session_log):
        with open(session_log, "r", encoding="utf-8") as stream:
            content = stream.read()

        edited_files = _read_recent_edited_files(project_root)
        files_text = ", ".join(f"`{x}`" for x in edited_files) if edited_files else "(없음)"
        
        match = _find_target_match(content, conv_id)
        if match:
            body = match.group("body")
            body = _replace_or_append_line(body, "상태", status)
            body = _replace_or_append_line(body, "종료", ended_at)
            body = _replace_or_append_line(body, "편집 파일", files_text)
            updated = content[:match.start()] + match.group(1) + body + content[match.end():]
            
            with open(session_log, "w", encoding="utf-8") as stream:
                stream.write(updated)

    # ── AI 자동 메모리 업데이트 ──────────────────────────────
    try:
        from auto_memory import run as auto_memory_run
        auto_memory_run(project_root)
    except Exception:
        pass  # 메모리 업데이트 실패는 세션 종료를 막지 않음

    # ── 작업용 임시/테스트 파일 클린업 (commit_msg.txt, tmp_*.txt 등) ──
    try:
        from cleanup_temp import cleanup_temp_files
        cleanup_temp_files(project_root)
    except Exception:
        pass

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()

