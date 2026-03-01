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

from shared_utils import find_key_recursive

def main():
    input_data = get_payload()
    if not isinstance(input_data, dict):
        input_data = {}

    project_root = find_key_recursive(input_data, ["workspace_roots", "workspaceRoots"], default=None)
    if isinstance(project_root, list) and len(project_root) > 0:
        project_root = str(project_root[0])
    elif project_root is not None:
        project_root = str(project_root)

    if not project_root or project_root.lower() == "none" or project_root == "unknown":
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    maybe_log_payload("sessionStart", input_data, project_root)

    conv_id = find_key_recursive(input_data, [
        "conversation_id", "conversationId", "session_id", "sessionId", "id",
        "chatId", "chat_id", "threadId", "thread_id", "conversationId"
    ])
    if isinstance(conv_id, list): conv_id = conv_id[0]
    if isinstance(conv_id, dict): conv_id = conv_id.get("id") or str(conv_id)
    if conv_id == "unknown":
        pass
    conv_id = str(conv_id)[:8] if conv_id and str(conv_id) != "unknown" else "unknown"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    session_log = os.path.join(project_root, "docs", "context", "SESSION_LOG.md")
    os.makedirs(os.path.dirname(session_log), exist_ok=True)

    existing = ""
    if os.path.exists(session_log):
        with open(session_log, "r", encoding="utf-8") as f:
            existing = f.read()

    header = "# Session Log\n\n> 이 파일은 Cursor Hooks에 의해 자동 관리됩니다.\n\n## 최근 세션\n\n"

    sessions_part = existing.split("## 최근 세션\n\n")[-1] if "## 최근 세션" in existing else ""
    session_count = sessions_part.count("### Session:")
    if session_count > 20:
        lines = sessions_part.split("\n### Session:")
        sessions_part = "\n### Session:".join(lines[-20:])

    new_entry = f"### Session: {conv_id}\n"
    new_entry += f"- **시작**: {timestamp}\n"
    new_entry += f"- **상태**: 진행중\n"
    new_entry += f"- **편집 파일**: (기록 중)\n"
    new_entry += f"- **종료**: -\n\n"

    with open(session_log, "w", encoding="utf-8") as f:
        f.write(header + new_entry + sessions_part)

    # AI 자동 메모리: 세션 시작 시 안내
    system1_message = (
        "[SYSTEM] 새 세션입니다.\n"
        "1. `docs/AI_STATUS.md`를 읽어 현재 상황을 파악하세요.\n"
        "2. 새 기능/중대형 수정이면 반드시 조사(R)→계획(P)→실행(I) 순서를 따르세요.\n"
        "   - 조사: DECISIONS.md, ARCHIVE_INDEX.md에서 관련 과거 기록 검색\n"
        "   - 계획: docs/guides/SPEC_TEMPLATE.md 기반으로 Spec 작성 → 사용자 승인 대기\n"
        "   - 실행: 승인 후 코딩 시작\n"
        "3. 대화가 길어지면 핵심을 요약하고 새 세션을 권유하세요 (Dumb Zone 회피)."
    )

    output = {
        "continue": True,
        "agentMessage": system1_message
    }
    sys.stdout.write(json.dumps(output))

if __name__ == "__main__":
    main()

