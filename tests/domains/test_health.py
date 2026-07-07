"""/healthz 라이브니스 계약 — status + commit(배포 SHA) 필드.

perf-gate 의 배포 완료 대기(tools/perf/wait_staging_deploy.py)가 이 commit 필드에
의존하므로 계약으로 고정한다.
"""

from __future__ import annotations


def test_healthz_ok_and_commit_field(client) -> None:
    """status=ok(200) + commit 키 존재(기존 최소 응답 계약 보존)."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "commit" in data  # 배포 완료 대기가 대조하는 필드


def test_healthz_commit_reflects_railway_env(client, monkeypatch) -> None:
    """commit 은 RAILWAY_GIT_COMMIT_SHA 를 반영(요청 시점 os.environ 조회)."""
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc1234deadbeef")
    resp = client.get("/healthz")
    assert resp.get_json()["commit"] == "abc1234deadbeef"


def test_healthz_commit_empty_without_env(client, monkeypatch) -> None:
    """env 부재(로컬/비Railway) → 빈 문자열."""
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    resp = client.get("/healthz")
    assert resp.get_json()["commit"] == ""
