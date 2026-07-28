"""Claude Code PostToolUse(Bash) 디스패처: stdin 1회 읽어 두 훅 로직을 순차 실행.

기존에 Bash 1회당 python 프로세스 2개(record_commit_ledger + post_push_watch)가
뜨던 것을 1개로 합친다(~70ms 절약). 각 모듈 로직은 무변경 — `process(payload)` 를
그대로 호출한다. stdin 은 여기서만 읽고(이중 읽기 금지) 파싱 결과를 인자로 넘긴다.
stdout JSON 은 post_push_watch 만 내보낸다(push 성공 시 CI-GATE 주입).

한쪽 실패가 다른 쪽을 막지 않도록 호출마다 try/except + hook_log(fail-open, exit 0).
"""
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)
from post_push_watch import process as process_push  # type: ignore[import-not-found]  # noqa: E402
from record_commit_ledger import process as process_commit  # type: ignore[import-not-found]  # noqa: E402
from shared_utils import hook_log, read_stdin_json  # type: ignore[import-not-found]  # noqa: E402

# (태그, 처리 함수) — 순서 = 실행 순서. ledger 기록이 먼저, CI-GATE 주입이 나중.
_HANDLERS = (
    ("commit_ledger", process_commit),
    ("post_push_watch", process_push),
)


def main() -> None:
    """PostToolUse(Bash) 페이로드를 읽어 등록된 처리기를 순차 호출한다."""
    payload = read_stdin_json()
    for tag, handler in _HANDLERS:
        try:
            handler(payload)
        except Exception as exc:  # noqa: BLE001 - 한쪽 실패가 다른 쪽을 막지 않도록
            hook_log(
                f"post_bash {tag} fail-open: {type(exc).__name__}: {exc}",
                tag="post_bash",
            )
    sys.exit(0)


if __name__ == "__main__":
    main()
