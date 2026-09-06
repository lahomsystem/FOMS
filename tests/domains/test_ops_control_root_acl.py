"""ACL 가드가 한국어 Windows 의 icacls 출력에서도 **판정**을 내는지 잠근다.

2026-09-07 실측: `text=True` 로 받던 시절, 한국어 Windows 가 icacls 꼬리에 붙이는 cp949
요약 줄 때문에 프로세스 기본 인코딩이 UTF-8 인 환경에서 reader 스레드가 죽고 `stdout` 이
`None` 이 됐다. 그러면 이 함수는 docstring 이 약속한 fail-closed(False) 가 아니라
`TypeError` 로 터진다 — 운영 백필 dry-run 이 실제로 이 지점에서 멈췄다.

판정에 쓰는 principal 이름은 전부 ASCII 이므로, 깨지는 것은 요약 줄뿐이고 판정은 살아야 한다.
"""

from __future__ import annotations

import subprocess

from foms.services.security.ops_control_root import _windows_acl_ok

# 한국어 Windows 실측 출력(요약 줄은 cp949, ACL 줄은 ASCII).
_LOCKED = (
    "C:\\tmp\\x BUILTIN\\Administrators:(OI)(CI)(F)\r\n"
    "          NT AUTHORITY\\SYSTEM:(OI)(CI)(F)\r\n"
).encode("ascii") + "\r\n1개 파일을 처리했습니다.\r\n".encode("cp949")

_INHERITED = (
    "C:\\tmp\\x BUILTIN\\Administrators:(I)(OI)(CI)(F)\r\n"
    "          BUILTIN\\Users:(I)(OI)(CI)(RX)\r\n"
).encode("ascii") + "\r\n1개 파일을 처리했습니다.\r\n".encode("cp949")


class _Completed:
    """subprocess.run 결과 대역(바이트 stdout)."""

    def __init__(self, returncode: int, stdout: bytes | None) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = b""


def _patch(monkeypatch, result) -> None:
    """icacls 호출을 대역으로 바꾼다."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: result)


def test_locked_acl_with_korean_summary_line_is_ok(monkeypatch, tmp_path) -> None:
    """cp949 요약 줄이 붙어도 잠긴 ACL 은 통과한다(예외 없음)."""
    _patch(monkeypatch, _Completed(0, _LOCKED))
    assert _windows_acl_ok(tmp_path) is True


def test_inherited_broad_principal_is_rejected(monkeypatch, tmp_path) -> None:
    """음성 대조군 — 상속된 BUILTIN\\Users 가 보이면 거부한다."""
    _patch(monkeypatch, _Completed(0, _INHERITED))
    assert _windows_acl_ok(tmp_path) is False


def test_missing_stdout_fails_closed_not_raises(monkeypatch, tmp_path) -> None:
    """stdout 이 None 이어도 예외가 아니라 False 다(docstring 이 약속한 fail-closed)."""
    _patch(monkeypatch, _Completed(0, None))
    assert _windows_acl_ok(tmp_path) is False


def test_nonzero_exit_fails_closed(monkeypatch, tmp_path) -> None:
    """icacls 가 실패하면 False."""
    _patch(monkeypatch, _Completed(1, b""))
    assert _windows_acl_ok(tmp_path) is False


def test_oserror_fails_closed(monkeypatch, tmp_path) -> None:
    """icacls 자체가 없으면 False."""

    def _boom(*_args, **_kwargs):
        raise OSError("icacls not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert _windows_acl_ok(tmp_path) is False
