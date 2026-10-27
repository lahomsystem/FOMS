"""AI 도면팀원 받기 도구(tools/drawing_ai/fetch_digest.py) · 연구 노트 시험.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 B1 · B2
- 쪽을 끝까지 넘겨 받고, 토큰은 출력 · 파일 어디에도 남기지 않는다. 404 → 종료 2, 401 → 3.
- to-retrain 은 사람 이름표만, 가장 많은 특징 판만 골라 retrain_head.py 가 읽는 꼴(features.npy · feature_keys.json ·
  manifest.jsonl)로 쓴다 — 그대로 load_dataset 이 읽는다.
"""

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from tools.drawing_ai import fetch_digest as tool
from tools.drawing_ai import retrain_head

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "secret-token-" + "q" * 40


def _feat(seed):
    v = np.random.default_rng(seed).normal(size=768).astype(np.float32)
    return base64.b64encode((v / np.linalg.norm(v)).astype("<f2").tobytes()).decode()


def _row(i, label, src="user", fv="f1-dv2s-8b1f", ai="정면·도어", active=True, order=7):
    return {"id": i, "order": order, "key": f"k{i:015d}", "feat": _feat(i), "fv": fv, "ai": ai, "conf": 0.6,
            "head": "h1", "label": label, "src": src, "active": active, "by": "pabc12345", "at": "2026-10-20T03:00:00"}


def test_fetch_pages_until_done_and_never_writes_token(tmp_path, monkeypatch):
    calls = []
    pages = {
        "summary": [{"memory": {"total": 3}}],
        "memory": [{"items": [_row(1, "정면·내부")], "next": 1}, {"items": [_row(2, "사진")], "next": None}],
        "sheets": [{"items": [{"order": 7, "sheet": 0, "family": "주방", "images": [{"key": "k000000000000001"}]}], "next": None}],
        "notes": [{"items": [{"id": "2026-W44", "questions": []}]}],
    }
    seen = {k: 0 for k in pages}

    def fake_open(url, token):
        assert token == TOKEN
        calls.append(url)
        kind = url.split("kind=")[1].split("&")[0]
        data = pages[kind][seen[kind]]
        seen[kind] += 1
        return {"success": True, "data": data}

    monkeypatch.setattr(tool, "_open", fake_open)
    counts = tool.fetch("https://foms.example", TOKEN, tmp_path / "d", since="2026-10-01")
    assert counts == {"memory": 2, "sheets": 1, "notes": 1}
    assert "after=1" in calls[2] and "since=2026-10-01" in calls[1] and calls[0].startswith("https://foms.example/api/drawing-agent/digest?")
    for f in (tmp_path / "d").iterdir():
        assert TOKEN not in f.read_text(encoding="utf-8")


@pytest.mark.parametrize("status,code", [(404, 2), (401, 3), (500, 4), (0, 4)])
def test_main_exit_codes(monkeypatch, tmp_path, capsys, status, code):
    def boom(url, token):
        raise tool.DigestError(status, f"HTTP {status}")

    monkeypatch.setattr(tool, "_open", boom)
    monkeypatch.setenv(tool.TOKEN_ENV, TOKEN)
    assert tool.main(["fetch", "--out", str(tmp_path / "x")]) == code
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_main_without_token(monkeypatch, tmp_path):
    monkeypatch.delenv(tool.TOKEN_ENV, raising=False)
    assert tool.main(["fetch", "--out", str(tmp_path / "x")]) == 3


def test_to_retrain_writes_retrain_head_input(tmp_path):
    digest = tmp_path / "digest"
    digest.mkdir()
    rows = [_row(1, "정면·내부"), _row(2, "정면·도어"), _row(3, "사진", src="ai"), _row(4, "서랍 단면", active=False),
            _row(5, "부품 상세", fv="old-v"), _row(6, "모르는 이름표"), _row(7, "평면·상판", order=9)]
    (digest / "memory.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    sheets = [{"order": 7, "sheet": 0, "family": "주방", "images": [{"key": rows[0]["key"]}, {"key": rows[1]["key"]}]}]
    (digest / "sheets.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in sheets), encoding="utf-8")
    out = tmp_path / "rt"
    res = tool.to_retrain(digest, out)
    assert res == {"rows": 3, "feat_version": "f1-dv2s-8b1f", "corrections": 2}
    X, meta = retrain_head.load_dataset(out, list(tool.LABELS))
    assert X.shape == (3, 768) and np.allclose(np.linalg.norm(X, axis=1), 1, atol=1e-3)
    assert [m["family"] for m in meta] == ["주방", "주방", "그 밖 장"]
    assert [m["corrected"] for m in meta] == [True, False, True] and {m["src"] for m in meta} == {"user"}
    assert meta[2]["order_id"] == 9 and meta[0]["key"] == "7:" + rows[0]["key"]


def test_notebook_files_and_rules():
    folder = ROOT / "docs/research/drawing-agent"
    for name in ("AGENT.md", "JOURNAL.md", "METRICS.md", "BACKLOG.md", "TEAM-RULES.md"):
        assert (folder / name).exists(), name
    agent = (folder / "AGENT.md").read_text(encoding="utf-8")
    for must in ("고객에게 나가는 일은 하지 않는다", "운영(production) 브랜치에 푸시하지 않는다", "FOMS_DRAWING_AGENT_TOKEN",
                 "fetch_digest.py fetch", "to-retrain", "retrain_head.py train", "drawing_agent_changes.json"):
        assert must in agent, must
