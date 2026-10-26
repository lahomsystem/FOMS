"""도면 마법사 그림 종류 기억 — 사람이 고른 종류를 바로 배우기(실시간 학습).

설계 정본: docs/plans/2026-10-26-drawing-part-memory-spec.md

- 남기기(:func:`save_items`): 브라우저 AI(``static/js/drawing/part-ai.js``)가 이미 계산한 그림 특징
  768개(L2 정규화)를 float16 1,536바이트(base64 2,048자)로 받아 이름표와 함께 둔다. 그림 자체는
  받지 않는다. 같은 주문·같은 그림 키는 한 줄이고, 준 칸만 덮어쓴다(특징은 같은 판이 이미 있으면 그대로).
- 따르기(:func:`follow`): 새로 분류한 그림이 사람이 고른 그림(``src='user'``)과 아주 비슷하면 그 종류를
  알려 준다. 문턱 아래이거나 문턱을 넘은 기억끼리 종류가 갈리면 따르지 않는다. 내부/도어만 다르거나
  AI 가 자신 있던 짐작을 뒤집을 때는 더 높은 문턱(``min_sim_door``)을 쓴다 — 같은 가구의 내부 그림과
  도어 그림은 서로 아주 닮는다.
- 같이 고치기(:func:`spread`): 사람이 한 장을 고치면 같은 시트의 닮은 AI 이름표 그림을 알려 준다.
- 켜고 끄기·문턱(:func:`load_policy`): SystemSetting ``drawing_part_memory`` — 없거나 틀린 칸은 코드 기본값.
- 사람 이름표 줄의 특징은 프로세스 메모리에 들고 있다가 바뀐 줄만(``updated_at``) 다시 읽는다.
  줄이 5만을 넘으면 pgvector 로 옮긴다(설계서 §3.7).
"""
from __future__ import annotations

import base64
import binascii
import re
import threading
import time
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from foms.persistence.main.models import SystemSetting
from foms.services.datetime_kst import now_utc_naive
from models import DrawingPartMemory

__all__ = [
    "DEFAULT_POLICY",
    "PartMemoryError",
    "decide",
    "MAX_ITEMS",
    "POLICY_KEY",
    "follow",
    "load_policy",
    "parse_follow_items",
    "parse_items",
    "parse_spread",
    "save_items",
    "spread",
]

POLICY_KEY = "drawing_part_memory"
#: store 남기기 · follow 새 그림이 사람 기억 따르기 · spread 한 장 고치면 닮은 그림 같이 고치기.
#: strict_conf 이상으로 자신 있던 AI 짐작을 뒤집을 때는 min_sim_door 를 넘어야 한다.
DEFAULT_POLICY = {
    "store": True, "follow": True, "spread": True,
    "min_sim": 0.95, "min_sim_door": 0.985, "strict_conf": 0.8,
}
FEAT_DIM = 768
FEAT_BYTES = FEAT_DIM * 2
FEAT_B64_LEN = 2048
MAX_ITEMS = 30
MAX_ROWS_PER_ORDER = 2000
UNSURE = "미분류"
SOURCES = ("ai", "user")
_FEAT_V_RE = re.compile(r"^[a-z0-9.-]{1,16}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_DOOR_PAIRS = (frozenset({"정면·내부", "정면·도어"}), frozenset({"입체·내부", "입체·도어"}))
_NEIGHBORS = 8
_FULL_RELOAD_S = 600   # 10분마다 통째로 다시 읽어 지워진 주문의 줄을 뺀다


class PartMemoryError(ValueError):
    """요청 형식이 틀렸다(400)."""


# --------------------------------------------------------------------------- 설정

def load_policy(session: Session) -> dict:
    """켜고 끄기·문턱. 저장이 없거나 칸 형식이 틀리면 그 칸은 기본값(마법사가 깨지지 않게 관대하게 읽는다)."""
    policy = dict(DEFAULT_POLICY)
    setting = session.query(SystemSetting).filter(SystemSetting.setting_key == POLICY_KEY).first()
    stored = getattr(setting, "setting_value", None) if setting is not None else None
    if isinstance(stored, dict):
        for key, default in DEFAULT_POLICY.items():
            value = stored.get(key)
            if isinstance(default, bool):
                if isinstance(value, bool):
                    policy[key] = value
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and 0.5 <= value <= 1:
                policy[key] = float(value)
    return policy


# --------------------------------------------------------------------------- 검증

def _decode_feat(text: object) -> Optional[np.ndarray]:
    """base64 float16 × 768 → 정규화한 float32. 길이·유한값·L2(0.9~1.1)가 틀리면 None."""
    if not isinstance(text, str) or len(text) != FEAT_B64_LEN:
        return None
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) != FEAT_BYTES:
        return None
    vec = np.frombuffer(raw, dtype="<f2").astype(np.float32)
    if not np.all(np.isfinite(vec)):
        return None
    norm = float(np.linalg.norm(vec))
    if not 0.9 <= norm <= 1.1:
        return None
    return vec / norm


def _key_ok(order_id: int, key: object) -> bool:
    prefix = f"orders/{order_id}/drawing_wizard/assets/"
    return isinstance(key, str) and key.startswith(prefix) and len(key) <= 500 and ".." not in key


def _items_list(items: object) -> list:
    if not isinstance(items, list) or not items:
        raise PartMemoryError("기억할 그림이 없습니다.")
    if len(items) > MAX_ITEMS:
        raise PartMemoryError(f"한 번에 {MAX_ITEMS}장까지 보낼 수 있습니다.")
    return items


def parse_items(order_id: int, items: object, *, labels: tuple, head_re: re.Pattern) -> list[dict]:
    """남기기 줄 검증 → ``[{key, feat?, fv?, ai?, conf?, head?, label?, src?}]``. 하나라도 틀리면 PartMemoryError."""
    rows = []
    for item in _items_list(items):
        if not isinstance(item, dict) or not _key_ok(order_id, item.get("key")):
            raise PartMemoryError("그림 키가 올바르지 않습니다.")
        row = {"key": item["key"]}
        if "f" in item:
            vec = _decode_feat(item.get("f"))
            fv = item.get("fv")
            if vec is None or not (isinstance(fv, str) and _FEAT_V_RE.match(fv)):
                raise PartMemoryError("그림 특징 값이 올바르지 않습니다.")
            row["feat"] = vec.astype("<f2").tobytes()
            row["fv"] = fv
        if "label" in item:
            if item["label"] not in labels or item.get("src") not in SOURCES:
                raise PartMemoryError("그림 종류 값이 올바르지 않습니다.")
            row["label"], row["src"] = item["label"], item["src"]
        if "ai" in item:
            if item["ai"] not in labels:
                raise PartMemoryError("그림 종류 AI 짐작 값이 올바르지 않습니다.")
            row["ai"] = item["ai"]
        if "conf" in item:
            conf = item["conf"]
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
                raise PartMemoryError("그림 종류 확신 값이 올바르지 않습니다.")
            row["conf"] = float(conf)
        if "head" in item:
            if not (isinstance(item["head"], str) and head_re.match(item["head"])):
                raise PartMemoryError("그림 종류 판 번호가 올바르지 않습니다.")
            row["head"] = item["head"]
        rows.append(row)
    return rows


def parse_follow_items(items: object, *, labels: tuple) -> list[dict]:
    """따르기 줄 검증 → ``[{id, vec, fv, key?, ai?, conf?, label?}]`` (label = 화면 이름표 — 확신이 낮으면 미분류)."""
    out = []
    for item in _items_list(items):
        if not isinstance(item, dict) or not (isinstance(item.get("id"), str) and _ID_RE.match(item["id"])):
            raise PartMemoryError("그림 id 가 올바르지 않습니다.")
        vec = _decode_feat(item.get("f"))
        fv = item.get("fv")
        if vec is None or not (isinstance(fv, str) and _FEAT_V_RE.match(fv)):
            raise PartMemoryError("그림 특징 값이 올바르지 않습니다.")
        ai = item.get("ai")
        conf = item.get("conf")
        shown = item.get("label")
        out.append({
            "id": item["id"], "vec": vec, "fv": fv,
            "key": item.get("key") if isinstance(item.get("key"), str) else "",
            "ai": ai if ai in labels else "",
            "label": shown if shown in labels else (ai if ai in labels else ""),
            "conf": float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.0,
        })
    return out


def parse_spread(order_id: int, body: dict, *, labels: tuple) -> dict:
    """같이 고치기 요청 검증 → ``{key, label, items: [{id, key, label}]}``."""
    if not _key_ok(order_id, body.get("key")) or body.get("label") not in labels or body.get("label") == UNSURE:
        raise PartMemoryError("고친 그림 값이 올바르지 않습니다.")
    items = []
    for item in _items_list(body.get("items")):
        if (not isinstance(item, dict) or not (isinstance(item.get("id"), str) and _ID_RE.match(item["id"]))
                or not _key_ok(order_id, item.get("key")) or item.get("label") not in labels):
            raise PartMemoryError("같이 고칠 그림 값이 올바르지 않습니다.")
        items.append({"id": item["id"], "key": item["key"], "label": item["label"]})
    return {"key": body["key"], "label": body["label"], "items": items}


# --------------------------------------------------------------------------- 남기기

def save_items(session: Session, order_id: int, user_id: Optional[int], rows: list[dict]) -> dict:
    """줄을 덮어쓴다(준 칸만). 호출부가 commit 한다. → ``{saved, missing: [특징 없는 키]}``."""
    keys = [r["key"] for r in rows]
    existing = {
        m.asset_key: m for m in session.query(DrawingPartMemory)
        .filter(DrawingPartMemory.order_id == order_id, DrawingPartMemory.asset_key.in_(keys))
    }
    room = None
    now = now_utc_naive()
    saved, missing = 0, []
    for row in rows:
        mem = existing.get(row["key"])
        if mem is None:
            if room is None:
                room = MAX_ROWS_PER_ORDER - session.query(DrawingPartMemory).filter(
                    DrawingPartMemory.order_id == order_id).count()
            if room <= 0:
                continue
            room -= 1
            mem = DrawingPartMemory(order_id=order_id, asset_key=row["key"], label=UNSURE, src="ai",
                                    created_by=user_id, created_at=now)
            session.add(mem)
            existing[row["key"]] = mem
        if "feat" in row and (mem.feat is None or mem.feat_v != row["fv"]):
            mem.feat, mem.feat_v = row["feat"], row["fv"]
        for field in ("label", "src", "ai", "conf", "head"):
            if field in row:
                setattr(mem, field, row[field])
        mem.updated_by = user_id
        mem.updated_at = now
        saved += 1
        if mem.feat is None:
            missing.append(row["key"])
    return {"saved": saved, "missing": missing}


# --------------------------------------------------------------------------- 사람 기억 캐시

class _HumanIndex:
    """사람 이름표 줄(켜짐·미분류 아님·특징 있음)의 특징 — 바뀐 줄만 다시 읽는다(프로세스마다 하나).

    주문이 지워지면(CASCADE) 그 줄은 '바뀐 줄'로 안 보이므로 10분마다 통째로 다시 읽는다.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rows: dict[int, tuple] = {}
        self.since = None
        self.mats: dict[str, tuple] = {}
        self.loaded = 0.0

    def reset(self) -> None:
        with self.lock:
            self.rows, self.since, self.mats = {}, None, {}

    def refresh(self, session: Session) -> None:
        if self.since is not None and time.monotonic() - self.loaded > _FULL_RELOAD_S:
            self.rows, self.since, self.mats = {}, None, {}
        if self.since is None:
            self.loaded = time.monotonic()
        q = session.query(
            DrawingPartMemory.id, DrawingPartMemory.order_id, DrawingPartMemory.asset_key,
            DrawingPartMemory.label, DrawingPartMemory.src, DrawingPartMemory.active,
            DrawingPartMemory.feat, DrawingPartMemory.feat_v, DrawingPartMemory.updated_at,
        )
        if self.since is None:   # 처음엔 쓸 줄만, 그다음엔 바뀐 줄 전부(사람 → AI 로 바뀐 줄을 빼야 한다)
            q = q.filter(DrawingPartMemory.active.is_(True), DrawingPartMemory.src == "user",
                         DrawingPartMemory.label != UNSURE, DrawingPartMemory.feat.isnot(None))
        else:
            q = q.filter(DrawingPartMemory.updated_at >= self.since)
        changed = False
        for r in q:
            entry = None
            if r.active and r.src == "user" and r.label != UNSURE and r.feat is not None and r.feat_v:
                vec = np.frombuffer(r.feat, dtype="<f2").astype(np.float32)
                norm = float(np.linalg.norm(vec))
                if vec.shape[0] == FEAT_DIM and norm > 0:
                    entry = (vec / norm, r.label, r.order_id, r.asset_key, r.feat_v)
            if entry is not None:
                self.rows[r.id] = entry
                changed = True
            elif self.rows.pop(r.id, None) is not None:
                changed = True
            if self.since is None or r.updated_at > self.since:
                self.since = r.updated_at
        if changed or not self.mats:
            self.mats = {}
            for rid, (vec, label, oid, key, fv) in self.rows.items():
                self.mats.setdefault(fv, ([], []))
                self.mats[fv][0].append(vec)
                self.mats[fv][1].append((rid, label, oid, key))
            self.mats = {fv: (np.vstack(v), meta) for fv, (v, meta) in self.mats.items()}


_INDEX = _HumanIndex()


def _door_only(a: str, b: str) -> bool:
    return a != b and any(a in pair and b in pair for pair in _DOOR_PAIRS)


def decide(head_label: str, head_conf: float, neighbors: list[tuple], policy: dict,
           shown: Optional[str] = None) -> Optional[dict]:
    """이웃(닮음 큰 순 ``[(sim, label, order_id)]``) → 따를 종류 또는 None.

    ``head_label`` 은 AI 첫 짐작(가장 큰 확률), ``shown`` 은 화면 이름표(확신이 문턱보다 낮으면 미분류 — 없으면 첫 짐작).
    - 가장 닮은 것이 min_sim 아래면 None. 문턱을 넘은 기억끼리 종류가 갈리면 ``{conflict: True}``.
    - 기억 종류가 화면 이름표와 같으면 바꿀 것이 없다(None). AI 가 헷갈려 미분류로 둔 그림은 첫 짐작이 같아도 따른다.
    - 내부/도어만 다르거나 AI 가 strict_conf 이상 자신 있던 짐작을 뒤집을 때는 min_sim_door 를 넘어야 한다.
    """
    shown = head_label if shown is None else shown
    if not neighbors or neighbors[0][0] < policy["min_sim"]:
        return None
    agree = [n for n in neighbors if n[0] >= policy["min_sim"]]
    labels = {n[1] for n in agree}
    top_sim = round(float(neighbors[0][0]), 3)
    if len(labels) > 1:
        return {"label": None, "sim": top_sim, "n": len(agree), "conflict": True}
    label = agree[0][1]
    if label == shown:
        return None
    strict = _door_only(label, head_label) or (
        label != head_label and shown not in ("", UNSURE) and head_conf >= policy["strict_conf"])
    if strict and neighbors[0][0] < policy["min_sim_door"]:
        return None
    return {"label": label, "sim": top_sim, "n": len(agree), "conflict": False}


def follow(session: Session, order_id: int, items: list[dict], policy: dict) -> dict:
    """새 그림마다 사람 기억에서 따를 종류 → ``{id: {label, sim, n, conflict, scope} | None}``."""
    out: dict = {}
    with _INDEX.lock:
        _INDEX.refresh(session)
        for item in items:
            mat_meta = _INDEX.mats.get(item["fv"])
            if mat_meta is None:
                out[item["id"]] = None
                continue
            mat, meta = mat_meta
            sims = mat @ item["vec"]
            order = np.argsort(-sims)[: _NEIGHBORS + 1]
            neighbors, top_scope = [], None
            for i in order:
                rid, label, oid, key = meta[int(i)]
                if oid == order_id and key == item["key"]:
                    continue   # 자기 자신
                neighbors.append((float(sims[int(i)]), label, oid))
                if top_scope is None:
                    top_scope = "order" if oid == order_id else "other"
                if len(neighbors) >= _NEIGHBORS:
                    break
            verdict = decide(item["ai"], item["conf"], neighbors, policy, shown=item["label"])
            if verdict is not None:
                verdict["scope"] = top_scope
            out[item["id"]] = verdict
    return out


def spread(session: Session, order_id: int, req: dict, policy: dict) -> list[dict]:
    """고친 그림과 닮은 같은 시트 AI 이름표 그림 → ``[{id, sim}]`` (닮음 큰 순)."""
    keys = [req["key"]] + [i["key"] for i in req["items"]]
    rows = {
        m.asset_key: m for m in session.query(DrawingPartMemory).filter(
            DrawingPartMemory.order_id == order_id, DrawingPartMemory.asset_key.in_(keys),
            DrawingPartMemory.feat.isnot(None))
    }
    base = rows.get(req["key"])
    if base is None:
        return []
    bvec = np.frombuffer(base.feat, dtype="<f2").astype(np.float32)
    bvec /= max(float(np.linalg.norm(bvec)), 1e-9)
    out = []
    for item in req["items"]:
        mem = rows.get(item["key"])
        if (mem is None or item["key"] == req["key"] or item["label"] == req["label"]
                or mem.feat_v != base.feat_v or mem.src == "user"):
            continue   # 사람이 고른 그림은 같이 고치지 않는다
        vec = np.frombuffer(mem.feat, dtype="<f2").astype(np.float32)
        sim = float(vec @ bvec) / max(float(np.linalg.norm(vec)), 1e-9)
        need = policy["min_sim_door"] if _door_only(item["label"], req["label"]) else policy["min_sim"]
        if sim >= need:
            out.append({"id": item["id"], "sim": round(sim, 3)})
    out.sort(key=lambda x: -x["sim"])
    return out
