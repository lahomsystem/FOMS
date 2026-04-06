import json
import os
import sys
from pathlib import Path


def _load_debug():
    try:
        hook_dir = os.path.dirname(os.path.abspath(__file__))
        if hook_dir not in sys.path:
            sys.path.insert(0, hook_dir)
        from hook_payload_debug import maybe_log_payload, get_payload

        return maybe_log_payload, get_payload
    except Exception as exc:
        try:
            sys.stderr.write(f"before_submit_prompt _load_debug: {exc}\n")
        except Exception:
            pass
        return lambda *args, **kwargs: None, lambda: {}


maybe_log_payload, get_payload = _load_debug()

from shared_utils import extract_project_root, hook_runtime_log


def _load_router():
    repo_root = Path(__file__).resolve().parents[2]
    harness_dir = repo_root / "tools" / "harness"
    if str(harness_dir) not in sys.path:
        sys.path.insert(0, str(harness_dir))
    from prompt_router import build_hook_output

    return build_hook_output


def main() -> None:
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)
    maybe_log_payload("beforeSubmitPrompt", payload, project_root)

    try:
        build_hook_output = _load_router()
        output = build_hook_output(payload, Path(project_root))
    except Exception as exc:
        hook_runtime_log(
            f"beforeSubmitPrompt fail-open: {type(exc).__name__}: {exc}",
            project_root=project_root,
            tag="before_submit",
        )
        output = {"continue": True}

    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
