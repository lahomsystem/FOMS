"""Claude Code hooks 공용 유틸리티."""
import json
import os
import sys


def read_stdin_json() -> dict:
    """stdin에서 Claude Code hook payload(JSON)를 읽어 dict로 반환."""
    try:
        raw = sys.stdin.read()
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


def get_project_root() -> str:
    """프로젝트 루트 경로 반환."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def write_stdout_json(data: dict):
    """결과 JSON을 stdout에 출력."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False))


def ensure_dir(path: str):
    """디렉토리가 없으면 생성."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
