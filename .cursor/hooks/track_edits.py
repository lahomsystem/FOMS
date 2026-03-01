import json
import os
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
    if "unknown" not in str(file_path):
        try:
            abs_path = os.path.abspath(file_path)
            root = os.path.abspath(project_root)
            rel = os.path.relpath(abs_path, root)
            if not rel.startswith(".."):
                file_path = rel.replace("\\", "/")
        except Exception:
            file_path = str(file_path).replace("\\", "/")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    edits = payload.get("edits", payload.get("changes", []))
    if not isinstance(edits, list):
        edits = []
    change_size = sum(len(str(e.get("new_string", ""))) for e in edits if isinstance(e, dict))
    change_summary = f"{len(edits)} edit(s), ~{change_size} chars"

    edit_log = os.path.join(project_root, "docs", "context", "EDIT_LOG.md")
    os.makedirs(os.path.dirname(edit_log), exist_ok=True)

    entries = []
    if os.path.exists(edit_log):
        with open(edit_log, "r", encoding="utf-8") as stream:
            for line in stream:
                line = line.rstrip()
                if line.startswith("- `"):
                    entries.append(line)

    new_entry = f"- `{file_path}` <- {change_summary} ({timestamp})"
    entries = [new_entry] + [x for x in entries if x != new_entry]
    entries = entries[:50]

    header = "\n".join([
        "# Edit Log",
        "",
        "> 이 파일은 Cursor Hooks에 의해 자동 관리됩니다.",
        "> 최근 50개 편집 기록만 유지합니다.",
        "",
        "## 최근 파일 편집",
        ""
    ])

    with open(edit_log, "w", encoding="utf-8") as stream:
        stream.write(header + "\n" + "\n".join(entries) + "\n")

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()
