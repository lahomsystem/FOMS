"""승격 대상 파일의 production 바탕 비교 (same / pin_only / differs).

``promote_completeness`` 가 patch-id 대신 파일 내용으로 "이미 들어감"을 판정할 때 쓴다.
"""
from __future__ import annotations

import re
import subprocess


def _run(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """git 서브프로세스 실행."""
    return subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# 자산 핀: ``?v=<토큰>`` (템플릿·테스트 단언 공통). 토큰은 날짜+접미사라 사전순 최대가 최신.
PIN_RE = re.compile(r"\?v=([A-Za-z0-9_.-]+)")

FILE_SAME = "same"
FILE_PIN_ONLY = "pin_only"
FILE_DIFFERS = "differs"


def _blob_id(project_root: str, ref: str, path: str) -> str | None:
    """``ref:path`` blob 해시. 없으면 None."""
    proc = _run(
        project_root, "git", "rev-parse", "--verify", "--quiet", f"{ref}:{path}"
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _blob_text(project_root: str, ref: str, path: str) -> str | None:
    """``ref:path`` 내용. 없으면 None."""
    proc = _run(project_root, "git", "show", f"{ref}:{path}")
    if proc.returncode != 0:
        return None
    return proc.stdout


def normalize_pins(text: str) -> str:
    """자산 핀 토큰을 지운 문자열(핀만 다른 줄 비교용)."""
    return PIN_RE.sub("?v=", text)


def is_pin_only_diff(a: str, b: str) -> bool:
    """두 텍스트가 다르되 다른 줄이 모두 핀 토큰 차이뿐인가."""
    if a == b:
        return False
    la = a.splitlines()
    lb = b.splitlines()
    if len(la) != len(lb):
        return False
    for x, y in zip(la, lb):
        if x != y and normalize_pins(x) != normalize_pins(y):
            return False
    return True


def classify_file(project_root: str, base_ref: str, bottom: str, path: str) -> str:
    """``base_ref:path`` 와 ``bottom:path`` 를 비교해 same/pin_only/differs."""
    a_id = _blob_id(project_root, base_ref, path)
    b_id = _blob_id(project_root, bottom, path)
    if a_id is None and b_id is None:
        return FILE_SAME
    if a_id is None or b_id is None:
        return FILE_DIFFERS  # 한쪽에만 있음(추가·삭제)
    if a_id == b_id:
        return FILE_SAME
    a = _blob_text(project_root, base_ref, path)
    b = _blob_text(project_root, bottom, path)
    if a is not None and b is not None and is_pin_only_diff(a, b):
        return FILE_PIN_ONLY
    return FILE_DIFFERS
