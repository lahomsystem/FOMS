"""Claude Code Stop hook: 작업 완료 후 품질 체크 리마인더.

세션 종료 시 최근 수정 파일 목록과 품질 체크리스트를 notification으로 출력.
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import get_project_root, write_stdout_json  # type: ignore[import-not-found]


def main():
    project_root = get_project_root()

    # EDIT_LOG에서 최근 수정 파일 추출
    edit_log_path = os.path.join(project_root, "docs", "context", "EDIT_LOG.md")
    edited_files = []
    if os.path.exists(edit_log_path):
        with open(edit_log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("| 20") and "`" in line:
                    parts = line.split("`")
                    if len(parts) >= 2:
                        edited_files.append(parts[1])

    edited_files = list(dict.fromkeys(reversed(edited_files)))[:10]

    if not edited_files:
        return

    files_list = "\n".join(f"  - {f}" for f in edited_files)
    message = f"""[Quality Check] 수정된 파일:
{files_list}

체크리스트:
- [ ] 에러 처리 누락 없는지?
- [ ] 보안 취약점(XSS/SQL Injection) 없는지?
- [ ] FOMS 코딩 규칙 준수했는지?
- [ ] docs/AI_STATUS.md 갱신 필요한지?"""

    write_stdout_json({"message": message})


if __name__ == "__main__":
    main()
