"""PowerShell 스크립트 인코딩 계약 (PS-ENC-01).

Windows PowerShell 5.1은 BOM 없는 `.ps1`을 ANSI 코드페이지(ko-KR 환경에서는
cp949)로 디코드한다. UTF-8로 저장된 한글 스크립트를 BOM 없이 두면 문자열
리터럴이 깨져 파싱 에러까지 난다. 파싱을 통과해도 콘솔 출력 인코딩이 cp949이면
한글 `Write-Host` 결과가 mojibake로 나온다.

따라서 비-ASCII 문자를 담은 `.ps1`은 두 조건을 모두 만족해야 한다.
1. UTF-8 BOM으로 시작한다 (소스 디코딩).
2. `[Console]::OutputEncoding`을 UTF-8로 강제한다 (출력 인코딩).

ASCII 전용 스크립트는 어느 쪽으로 디코드해도 동일하므로 계약 대상이 아니다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 보관용 일회성 스크립트는 동결 대상이라 계약에서 제외한다.
EXCLUDED_PREFIXES = ("docs/context/archive/",)

UTF8_BOM = b"\xef\xbb\xbf"


def _tracked_ps1_files() -> list[str]:
    """git이 추적 중인 `.ps1` 경로 목록을 저장소 상대 경로로 반환한다.

    Returns:
        계약 대상 `.ps1` 상대 경로 목록. git을 쓸 수 없으면 빈 목록.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "*.ps1"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [
        line
        for line in completed.stdout.splitlines()
        if line and not line.startswith(EXCLUDED_PREFIXES)
    ]


def _non_ascii_ps1_files() -> list[str]:
    """비-ASCII 문자를 담은 계약 대상 `.ps1` 경로 목록을 반환한다.

    Returns:
        BOM·콘솔 인코딩 계약을 지켜야 하는 `.ps1` 상대 경로 목록.
    """
    result: list[str] = []
    for rel in _tracked_ps1_files():
        raw = (REPO_ROOT / rel).read_bytes()
        body = raw[len(UTF8_BOM):] if raw.startswith(UTF8_BOM) else raw
        if any(byte > 0x7F for byte in body):
            result.append(rel)
    return result


def test_tracked_ps1_files_are_discoverable() -> None:
    """계약 대상 탐색이 조용히 0건으로 무력화되지 않았는지 확인한다."""
    assert _tracked_ps1_files(), "추적 중인 .ps1을 하나도 찾지 못했다 (git ls-files 실패 의심)"


@pytest.mark.parametrize("rel_path", _non_ascii_ps1_files())
def test_non_ascii_ps1_starts_with_utf8_bom(rel_path: str) -> None:
    """비-ASCII `.ps1`은 UTF-8 BOM으로 시작해야 한다."""
    raw = (REPO_ROOT / rel_path).read_bytes()
    assert raw.startswith(UTF8_BOM), (
        f"{rel_path}: 비-ASCII를 담은 .ps1에 UTF-8 BOM이 없다. "
        "PowerShell 5.1이 cp949로 디코드해 파싱 에러가 난다."
    )


@pytest.mark.parametrize("rel_path", _non_ascii_ps1_files())
def test_non_ascii_ps1_forces_utf8_console(rel_path: str) -> None:
    """비-ASCII `.ps1`은 콘솔 출력 인코딩을 UTF-8로 강제해야 한다."""
    text = (REPO_ROOT / rel_path).read_bytes().decode("utf-8-sig")
    assert "[Console]::OutputEncoding" in text and "UTF8Encoding" in text, (
        f"{rel_path}: 콘솔 UTF-8 강제 구문이 없다. 스크립트 상단(param 블록 뒤)에 "
        "`$OutputEncoding = New-Object System.Text.UTF8Encoding $false` 와 "
        "`[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false` 를 넣어라."
    )
