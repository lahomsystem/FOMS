import json
import os
import sys

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

from shared_utils import (
    append_edit_row,
    extract_project_root,
    find_key_recursive,
    harness_runtime_path,
    hook_runtime_log,
    is_within_tree,
)

def _normalize_uri_to_path(uri):
    if not uri or not isinstance(uri, str):
        return None
    s = uri.strip()
    for prefix in ("file:///", "file://", "file:"):
        if s.startswith(prefix):
            s = s[len(prefix):].lstrip("/")
            break
    return s.replace("\\", "/") if s else None

_PATH_KEYS = ["file_path", "path", "filePath", "file", "uri", "relativeWorkspacePath", "target_file", "resource", "document"]

def _get_file_path(payload):
    # 1) 최상위 path 우선 (Cursor afterFileEdit payload는 file_path가 최상위에 옴)
    top = find_key_recursive(payload, _PATH_KEYS, default=None)
    if top and top != "unknown":
        if isinstance(top, list):
            top = top[0]
        out = _normalize_uri_to_path(str(top)) or str(top)
        if out:
            return out
    # 2) edits[0] 안에서 path 검사
    edits = payload.get("edits", payload.get("changes"))
    if isinstance(edits, list) and len(edits) > 0:
        edit = edits[0]
        if isinstance(edit, dict):
            path = find_key_recursive(edit, _PATH_KEYS, default=None)
            if path:
                out = _normalize_uri_to_path(path) or path
                if out and out != "unknown":
                    return out
    # 3) 단일 edit 객체
    edit_one = payload.get("edit")
    if isinstance(edit_one, dict):
        path = find_key_recursive(edit_one, _PATH_KEYS, default=None)
        if path:
            out = _normalize_uri_to_path(path) or path
            if out and out != "unknown":
                return out
    return "unknown"

def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)

    maybe_log_payload("afterFileEdit", payload, project_root)

    file_path = _get_file_path(payload)
    if "unknown" in str(file_path):
        sys.stdout.write(json.dumps({"continue": True}))
        return

    # 트리밖 편집(전역 메모리·스크래치패드 등)은 commonpath 판정으로 스킵.
    abs_path = os.path.abspath(file_path)
    if not is_within_tree(project_root, abs_path):
        hook_runtime_log(f"트리밖 편집 스킵: {file_path}", project_root=project_root, tag="track_edits")
        sys.stdout.write(json.dumps({"continue": True}))
        return
    rel_path = os.path.relpath(abs_path, os.path.abspath(project_root)).replace("\\", "/")

    # EDIT_LOG 포맷·dedup·캡은 공용 유틸에 위임(Claude 훅과 단일 테이블 포맷).
    append_edit_row(harness_runtime_path(project_root, "EDIT_LOG.md"), rel_path, "Cursor")

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()
