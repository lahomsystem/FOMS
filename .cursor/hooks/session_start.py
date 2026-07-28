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

from shared_utils import extract_project_root, find_key_recursive, harness_runtime_path, prepend_session_block

def main():
    input_data = get_payload()
    if not isinstance(input_data, dict):
        input_data = {}

    project_root = extract_project_root(input_data)

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

    # SESSION_LOG 포맷·로테이션은 공용 유틸에 위임(Claude 훅과 단일 포맷/로테이션 공유).
    session_log = harness_runtime_path(project_root, "SESSION_LOG.md")
    prepend_session_block(session_log, conv_id, timestamp)

    # AI 자동 메모리: 세션 시작 시 안내
    system1_message = (
        "[SYSTEM] 새 세션입니다.\n"
        "1. `docs/AI_STATUS.md`는 상단 40줄만 읽으세요 — live 상태는 전부 상단, 아래는 상세 기록(필요 시 grep).\n"
        "2. 새 기능/중대형 수정, 또는 하네스 핵심 변경(Hooks/Rules/Agents/Verification)이면 반드시 조사(R)→계획(P)→실행(I) 순서를 따르세요.\n"
        "   - 조사: docs/harness/policy/DECISIONS.md, docs/ARCHIVE_INDEX.md에서 관련 과거 기록 검색\n"
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

