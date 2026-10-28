"""도면 마법사 그림 종류 분류기 다시 가르치기 도구(3단계) 계약 테스트.

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.5 · §3.7
- 정답 무게: 사람 이름표 1 · 손대지 않고 전달한 AI 이름표 0.5 · 미분류/전달 안 된 AI 이름표는 뺀다.
- 고정 시험 묶음은 주문 번호로만 정해진다(20%).
- 지금 판에서 출발해 고친 기록으로 다시 가르치면 틀리던 종류가 나아진다(합성 자료).
- 판정: 시험 수·전체·제품별·주방 +1%p. 새 판 파일은 브라우저 계약(part-head.json 꼴)을 지킨다.
- 운영 자료 없이 돈다(numpy·PIL 만, onnxruntime·DB·R2 불필요).
"""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from foms.api.drawing import wizard as wizard_api
from tools.drawing_ai import part_embed as pe
from tools.drawing_ai import retrain_data as rd
from tools.drawing_ai import retrain_head as cli
from tools.drawing_ai import retrain_model as rm

ROOT = Path(__file__).resolve().parents[2]
HEAD = ROOT / "static/js/drawing/part-head.json"


def _img(key, label, src, ai=None):
    part = {"label": label, "src": src}
    if ai:
        part["ai"] = ai
    return {"id": key, "type": "image", "key": key, "part": part}


def _dw():
    current = {"id": "s1", "name": "도면", "product_index": 0, "objects": [
        _img("k-user", "입체·내부", "user", ai="입체·도어"),      # 사람이 고침 → 1, corrected
        _img("k-same", "사진", "user", ai="사진"),                # 사람이 확인 → 1, not corrected
        _img("k-ai-new", "정면·도어", "ai", ai="정면·도어"),      # 전달 안 됨 → 뺌
        _img("k-unsure", "미분류", "user", ai="정면·내부"),        # 미분류 → 뺌
        _img("k-flip", "평면·상판", "user", ai="부품 상세"),       # 스냅샷의 AI 이름표를 사람이 바꿈
        {"id": "t", "type": "text", "text": "[SR]"},
    ]}
    snapshot = {"id": "s1", "name": "도면", "product_index": 0, "objects": [
        _img("k-flip", "부품 상세", "ai", ai="부품 상세"),
        _img("k-delivered", "서랍 단면", "ai", ai="서랍 단면"),    # 전달 확인 → 0.5
    ]}
    return {"sheets": [current]}, [snapshot]


def test_records_weights_and_precedence():
    dw, snaps = _dw()
    recs = {r["key"]: r for r in rd.records_for_order(7, dw, [{"product_name": "주방 하부장"}], "주방", snaps)}
    assert set(recs) == {"k-user", "k-same", "k-flip", "k-delivered"}
    assert recs["k-user"]["weight"] == 1.0 and recs["k-user"]["corrected"] is True
    assert recs["k-same"]["corrected"] is False
    assert recs["k-delivered"]["weight"] == 0.5 and recs["k-delivered"]["delivered"] is True
    assert recs["k-flip"]["label"] == "평면·상판" and recs["k-flip"]["weight"] == 1.0   # 사람이 이긴다
    assert {r["family"] for r in recs.values()} == {"주방"}
    s = rd.summarize(list(recs.values()))
    assert s["corrections"] == 2 and s["human"] == 3 and s["confirmed"] == 1
    assert {(c["ai"], c["label"]) for c in s["confusion"]} == {("입체·도어", "입체·내부"), ("부품 상세", "평면·상판")}


@pytest.mark.parametrize("text,family", [
    ("양문형 냉장고장", "냉장고장"), ("주방 하부장", "주방"), ("아일랜드 식탁", "주방"),
    ("몰딩 여닫이 붙박이장", "붙박이장"), ("3연동 슬라이딩", "붙박이장"), ("신발장", "그 밖 장"),
])
def test_family_rules(text, family):
    assert rd.family_of(text) == family


def test_snapshot_pointers_since_filter_and_order():
    dw = {"versions": [
        {"v": 3, "key": "c", "at": "2026-11-02 10:00"}, {"v": 1, "key": "a", "at": "2026-10-01 09:00"},
        {"v": 2, "key": "b", "at": "2026-10-22 18:30"}, {"v": 4, "at": "2026-11-03 10:00"},
    ]}
    assert [p["key"] for p in rd.snapshot_pointers(dw, "2026-10-22")] == ["b", "c"]


def test_local_store_reads_inside_base_only(tmp_path):
    (tmp_path / "orders").mkdir()
    (tmp_path / "orders" / "a.png").write_bytes(b"png")
    (tmp_path.parent / "outside.txt").write_text("x", encoding="utf-8")
    store = rd.LocalStore(str(tmp_path))
    assert store.get("orders/a.png") == b"png"
    assert store.get("../outside.txt") is None and store.get("orders/none.png") is None


class _Cursor:
    def __init__(self, rows):
        self.rows, self.sql = rows, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.sql = sql

    def __iter__(self):
        return iter(self.rows)


class _Conn:
    def __init__(self, rows):
        self.cur = _Cursor(rows)

    def cursor(self):
        return self.cur


class _Store:
    def __init__(self, files):
        self.files = files

    def get(self, key):
        return self.files.get(key)


def test_collect_writes_manifest_and_images(tmp_path):
    dw, snaps = _dw()
    dw["versions"] = [{"v": 1, "key": "snap-1.json", "at": "2026-10-23 09:00"}]
    files = {"snap-1.json": json.dumps(snaps[0]).encode("utf-8"), "k-user": b"u", "k-same": b"s", "k-flip": b"f"}
    conn = _Conn([(7, dw, [{"product_name": "붙박이장"}], "붙박이장"), (8, None, None, None)])
    summary = rd.collect(conn, _Store(files), tmp_path / "out")
    assert "structured_data->'drawing_wizard'" in conn.cur.sql and "parties" not in conn.cur.sql   # 고객 칸은 읽지 않는다
    recs = rd.read_manifest(tmp_path / "out" / "manifest.jsonl")
    assert {r["key"] for r in recs} == {"k-user", "k-same", "k-flip"}   # k-delivered 는 그림을 못 받아 빠짐
    assert summary["missing"] == 1 and summary["records"] == 3
    assert all((tmp_path / "out" / "imgs" / r["file"]).read_bytes() == files[r["key"]] for r in recs)


def test_holdout_is_stable_and_about_20_percent():
    picks = [rm.in_holdout(i) for i in range(1, 2001)]
    assert picks == [rm.in_holdout(i) for i in range(1, 2001)]
    assert 0.17 < sum(picks) / len(picks) < 0.23


def _synthetic(n_orders, drift, dim=32, seed=0):
    rng = np.random.default_rng(seed)
    k = len(rd.LABELS)
    means = rng.normal(size=(k, dim))
    means /= np.linalg.norm(means, axis=1, keepdims=True)
    W0, b0 = means * 20.0, np.zeros(k)
    X, y, orders = [], [], []
    for o in range(n_orders):
        for c in range(k):
            x = means[c] + 0.3 * rng.normal(size=dim) / np.sqrt(dim) * 3
            if c == 2:
                x = x + drift * (means[3] - means[2])   # 입체·내부 새 그림이 입체·도어 쪽으로 기울었다
            X.append(x / np.linalg.norm(x))
            y.append(c)
            orders.append(1000 + o)
    return np.array(X), np.array(y), np.array(orders), W0, b0


def test_fit_from_current_head_fixes_drifted_class():
    X, y, orders, W0, b0 = _synthetic(120, drift=0.62)
    hold = np.array([rm.in_holdout(o) for o in orders])
    w = np.ones(len(y))
    W, b = rm.fit(X[~hold], y[~hold], rm.balanced_weights(y[~hold], w[~hold]), W0, b0, lam=0.003, iters=300)
    m = y[hold] == 2
    before = (rm.predict_proba(W0, b0, X[hold]).argmax(1)[m] == 2).mean()
    after = (rm.predict_proba(W, b, X[hold]).argmax(1)[m] == 2).mean()
    assert before < 0.5 < after


def _metrics(acc, fams):
    return {"n": sum(n for n, _ in fams.values()), "acc": acc,
            "per_family": {f: {"n": n, "acc": a} for f, (n, a) in fams.items()}}


def test_judge_rules():
    cur = _metrics(0.90, {"주방": (12, 0.80), "붙박이장": (30, 0.95)})
    good = _metrics(0.93, {"주방": (12, 0.82), "붙박이장": (30, 0.95)})
    assert rm.judge(cur, good)["ok"] is True
    assert rm.judge(cur, _metrics(0.89, {"주방": (12, 0.85), "붙박이장": (30, 0.95)}))["ok"] is False      # 전체 내려감
    assert rm.judge(cur, _metrics(0.93, {"주방": (12, 0.805), "붙박이장": (30, 0.95)}))["ok"] is False     # 주방 +1%p 미달
    assert rm.judge(cur, _metrics(0.93, {"주방": (12, 0.85), "붙박이장": (30, 0.94)}))["ok"] is False      # 붙박이장 내려감
    few_kitchen = rm.judge(cur, _metrics(0.93, {"주방": (5, 1.0), "붙박이장": (30, 0.96)}))
    assert few_kitchen["ok"] is False and any("주방 시험 그림" in r for r in few_kitchen["reasons"])
    assert rm.judge(cur, _metrics(0.99, {"주방": (3, 1.0), "붙박이장": (10, 1.0)}))["ok"] is False        # 시험 30장 미만


def test_export_head_keeps_browser_contract():
    base = json.loads(HEAD.read_text(encoding="utf-8"))
    W = np.array(base["W"]) * 0.5
    head = rm.export_head(W, np.array(base["b"]), base, {"n": 10})
    assert head["version"] == rm.next_version(base["version"]) and head["version"] != base["version"]
    assert set(head["labels"]) <= set(wizard_api._PART_LABELS) - {"미분류"}
    assert len(head["W"]) == len(head["labels"]) == len(head["b"]) and all(len(r) == 768 for r in head["W"])
    for key in ("model", "prep", "threshold"):
        assert head[key] == base[key]
    assert rm.next_version("h9") == "h10"


def _write_dataset(d, X, y, orders, families, max_corrected=80):
    """사람 확인 기록. 입체·내부는 AI 가 입체·도어로 짐작했던 것 — 그중 앞의 max_corrected 건만 '고침' 표시."""
    d.mkdir(parents=True, exist_ok=True)
    keys, lines, corrected = [], [], 0
    for i, (label_idx, order, fam) in enumerate(zip(y.tolist(), orders.tolist(), families)):
        key = f"orders/{order}/drawing_wizard/assets/{i}.png"
        label = rd.LABELS[label_idx]
        ai = rd.LABELS[3] if label_idx == 2 and corrected < max_corrected else label
        corrected += int(ai != label)
        keys.append(key)
        lines.append(json.dumps({"key": key, "label": label, "weight": 1.0, "src": "user", "ai": ai,
                                 "order_id": order, "family": fam, "corrected": ai != label}))
    (d / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    np.save(d / "features.npy", X.astype(np.float32))
    (d / "feature_keys.json").write_text(json.dumps(keys), encoding="utf-8")


def test_cli_train_end_to_end_writes_report_and_new_head(tmp_path):
    X, y, orders, W0, b0 = _synthetic(140, drift=0.62, dim=32, seed=3)
    head = {"version": "h1", "labels": list(rd.LABELS), "W": W0.tolist(), "b": b0.tolist(), "threshold": 0.5,
            "model": {"url": "u", "sha256": "s"}, "prep": {"size": 224}, "trained_on": {"n": 1201}}
    (tmp_path / "head.json").write_text(json.dumps(head), encoding="utf-8")
    _write_dataset(tmp_path / "data", X, y, orders, ["주방"] * len(y))
    out = tmp_path / "h2.json"
    args = ["train", "--data", str(tmp_path / "data"), "--head", str(tmp_path / "head.json"), "--out", str(out)]
    assert cli.main(args) == 2   # 기본 문턱: 고친 기록 100건 미만이면 가르치지 않는다
    code = cli.main(args + ["--min-corrections", "50"])
    rep = json.loads((tmp_path / "data" / "report.json").read_text(encoding="utf-8"))
    assert code == 0 and rep["verdict"]["ok"] is True, rep["verdict"]
    assert rep["test"]["candidate"]["acc"] > rep["test"]["current"]["acc"]
    new_head = json.loads(out.read_text(encoding="utf-8"))
    assert new_head["version"] == "h2" and new_head["trained_on"]["from"] == "h1"
    assert "판정: 통과" in (tmp_path / "data" / "report.md").read_text(encoding="utf-8")


def test_cli_train_adds_new_view_class_once_people_labeled_enough(tmp_path):
    """탑뷰 · 사이드뷰(2026-10-28 사용자 요청)는 머리가 아직 모른다 — 사람 기록이 --min-new 장 넘으면 머리에 새 줄로 더하고,
    모자라면 그 기록은 빼고 다음에(기록 장수는 보고서에)."""
    X, y, orders, W0, b0 = _synthetic(140, drift=0.62, dim=32, seed=3)
    head = {"version": "h1", "labels": list(rd.LABELS), "W": W0.tolist(), "b": b0.tolist(), "threshold": 0.5,
            "model": {"url": "u", "sha256": "s"}, "prep": {"size": 224}, "trained_on": {"n": 1201}}
    (tmp_path / "head.json").write_text(json.dumps(head), encoding="utf-8")
    data = tmp_path / "data"
    _write_dataset(data, X, y, orders, ["주방"] * len(y))
    rng = np.random.default_rng(11)
    top = rng.normal(size=32)
    top /= np.linalg.norm(top)
    new = np.array([(top + 0.15 * rng.normal(size=32)) for _ in range(60)])
    new /= np.linalg.norm(new, axis=1, keepdims=True)
    keys = json.loads((data / "feature_keys.json").read_text(encoding="utf-8"))
    lines = (data / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    for i in range(60):   # 위에서 본 그림 — AI 는 평면·상판으로 짐작했고 사람이 탑뷰로 고쳤다
        key, order = f"orders/{2000 + i}/drawing_wizard/assets/top{i}.png", 2000 + i
        keys.append(key)
        lines.append(json.dumps({"key": key, "label": "탑뷰", "weight": 1.0, "src": "user", "ai": "평면·상판",
                                 "order_id": order, "family": "주방", "corrected": True}))
    (data / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    np.save(data / "features.npy", np.vstack([np.load(data / "features.npy"), new.astype(np.float32)]))
    (data / "feature_keys.json").write_text(json.dumps(keys), encoding="utf-8")
    out = tmp_path / "h2.json"
    args = ["train", "--data", str(data), "--head", str(tmp_path / "head.json"), "--out", str(out), "--min-corrections", "50"]
    assert cli.main(args) == 0
    rep = json.loads((data / "report.json").read_text(encoding="utf-8"))
    new_head = json.loads(out.read_text(encoding="utf-8"))
    assert rep["new_labels"] == ["탑뷰"] and rep["new_counts"] == {"탑뷰": 60, "사이드뷰": 0}
    assert new_head["labels"] == list(rd.LABELS) + ["탑뷰"] and len(new_head["W"]) == len(new_head["b"]) == len(rd.LABELS) + 1
    assert set(new_head["labels"]) <= set(wizard_api._PART_LABELS) - {"미분류"}   # 브라우저 · 서버 닫힌 목록 안
    cli.main(args + ["--min-new", "100"])
    rep2 = json.loads((data / "report.json").read_text(encoding="utf-8"))
    assert rep2["new_labels"] == [] and rep2["new_counts"]["탑뷰"] == 60       # 모자라면 다음에


def test_cli_collect_requires_db_env(tmp_path, monkeypatch):
    monkeypatch.delenv("RETRAIN_DB_URL", raising=False)
    assert cli.main(["collect", "--out", str(tmp_path / "o")]) == 2


def test_prep_and_pool_match_training_recipe():
    x = pe.prep(Image.new("RGB", (300, 100), (0, 0, 0)))
    assert x.shape == (1, 3, 224, 224) and x.dtype == np.float32
    white = (1.0 - np.array(pe.MEAN)) / np.array(pe.STD)
    assert np.allclose(x[0, :, 0, 0], white, atol=1e-5)     # 흰 여백(위쪽)
    assert x[0, 0, 112, 112] < 0                             # 가운데는 검은 그림
    last = np.random.default_rng(0).normal(size=(1, 257, 384))
    v = pe.pool(last)
    assert v.shape == (768,) and abs(np.linalg.norm(v) - 1.0) < 1e-9


def test_prep_puts_transparent_png_on_white_like_browser():
    """마법사에 올린 스케치업 PNG 는 투명 칸의 색이 검정(0,0,0) — 흰 바탕에 얹어야 브라우저(part-ai.js 흰 캔버스)와 같은 특징이 된다."""
    rgba = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    rgba.paste((40, 40, 40, 255), (60, 30, 140, 90))
    flat = Image.new("RGB", (200, 120), (255, 255, 255))
    flat.paste((40, 40, 40), (60, 30, 140, 90))
    assert np.allclose(pe.prep(rgba), pe.prep(flat), atol=1e-6)
    assert np.allclose(pe.prep(rgba.convert("LA")), pe.prep(flat.convert("L")), atol=1e-6)
