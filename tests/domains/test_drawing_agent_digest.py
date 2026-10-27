"""AI 도면팀원 학습 요약 — 토큰 길 · 고객 정보 빼기 · 쪽 넘기기 시험.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §3 · §4
- 서버는 토큰 원문을 모른다: 환경 변수에는 sha256 지문만. 지문이 없으면 404, 토큰이 틀리면 401.
- 고객 이름 · 전화 · 주소 · 머리칸 · 시트 이름 · 메모 글 · 그림 파일 이름(key) · 사람 번호는 응답 어디에도 없다.
- 자재표는 머리글 아래 숫자 줄만, 그림 key 는 지문, 사람은 익명 번호.
"""

import base64
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import drawing_agent_digest as agent_digest
from models import DrawingPartMemory, Order, User

TOKEN = "t0k3n-" + "x" * 40
URL = "/api/drawing-agent/digest"
SECRET_WORDS = ("김비밀", "010-9999-1234", "비밀동 1번지", "담당자박", "고객메모", "김비밀주방", "s-secret", "비밀 시트")


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setenv(agent_digest.TOKEN_ENV, hashlib.sha256(TOKEN.encode()).hexdigest())


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def _feat(seed):
    v = np.random.default_rng(seed).normal(size=768).astype(np.float32)
    return (v / np.linalg.norm(v)).astype("<f2").tobytes()


def _seed():
    user = User(username="digest-user", password=generate_password_hash("x"), role="STAFF", team="DRAWING",
                name="담당자박", is_active=True)
    db_session.add(user)
    db_session.commit()
    key = "orders/{oid}/drawing_wizard/assets/김비밀주방.png"
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="김비밀", phone="010-9999-1234",
                  address="비밀동 1번지", product="붙박이장", status="DRAWING", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    sheet = {
        "id": "s-secret", "name": "비밀 시트", "product_index": 0,
        "form": {"customer_name": "김비밀", "phone": "010-9999-1234", "address": "비밀동 1번지", "sales_manager": "담당자박"},
        "objects": [
            {"id": "o-1", "type": "image", "key": key.format(oid=order.id), "x": 10, "y": 20, "w": 300, "h": 200,
             "natural_w": 600, "natural_h": 400, "rotation": 0,
             "part": {"label": "정면·내부", "src": "user", "ai": "정면·도어", "conf": 0.7, "head": "h1", "arr": [1, 2, 3, 4]}},
            {"id": "o-2", "type": "text", "x": 0, "y": 0, "w": 100,
             "text": "[SR] 60*2440=2\n120*2440=1\n[도어]\n483*2160=4\nㄴ피닉스바 2EA\n고객메모 문 손잡이 왼쪽"},
            {"id": "o-3", "type": "text", "x": 0, "y": 0, "w": 100, "text": "고객메모: 김비밀 010-9999-1234"},
        ],
        "calc": {"in": {"W": 3500}, "out": "[SR]\n60*2440=2", "rules": "d1", "mode": "shadow"},
        "review": {"off": ["head:phone"], "seen": ["head:phone", "unsorted"]},
    }
    order.structured_data = {"drawing_wizard": {"v": 1, "sheets": [sheet]}, "parties": {"customer": {"name": "김비밀"}}}
    db_session.add(order)
    rows = [
        DrawingPartMemory(order_id=order.id, asset_key=key.format(oid=order.id), feat=_feat(1), feat_v="f1-dv2s-8b1f",
                          ai="정면·도어", conf=0.7, head="h1", label="정면·내부", src="user", active=True,
                          created_by=user.id, updated_by=user.id),
        DrawingPartMemory(order_id=order.id, asset_key=f"orders/{order.id}/drawing_wizard/assets/b.png", feat=_feat(2),
                          feat_v="f1-dv2s-8b1f", ai="사진", conf=0.99, head="h1", label="사진", src="ai", active=True),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return order.id, user.id, [r.id for r in rows]


def test_disabled_without_fingerprint(client, monkeypatch):
    monkeypatch.delenv(agent_digest.TOKEN_ENV, raising=False)
    resp = client.get(URL, headers=_auth())
    assert resp.status_code == 404 and resp.get_json()["error"] == "disabled"


@pytest.mark.parametrize("headers", [{}, _auth("t0k3n-" + "y" * 40), {"Authorization": f"Basic {TOKEN}"},
                                     {"Authorization": "Bearer short"}, {"Authorization": f"bearer {TOKEN}"}])
def test_wrong_or_missing_token_is_401(client, armed, headers):
    resp = client.get(URL, headers=headers)
    assert resp.status_code == 401 and resp.get_json()["success"] is False
    assert resp.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("query", ["?kind=orders", "?kind=memory&since=어제", "?kind=memory&after=x", "?kind=sheets&limit=abc"])
def test_bad_query_is_400(client, armed, query):
    assert client.get(URL + query, headers=_auth()).status_code == 400


def test_summary_counts(client, armed):
    _seed()
    resp = client.get(URL, headers=_auth())
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "no-store"
    mem = resp.get_json()["data"]["memory"]
    assert mem["total"] == 2 and mem["user"] == 1 and mem["ai"] == 1 and mem["user_changed_ai"] == 1
    assert mem["user_by_label"] == {"정면·내부": 1} and mem["feat_versions"] == {"f1-dv2s-8b1f": 2}


def test_memory_rows_hash_keys_and_anonymize_people(client, armed):
    order_id, user_id, ids = _seed()
    body = client.get(URL + "?kind=memory", headers=_auth()).get_json()["data"]
    assert body["next"] is None and [r["id"] for r in body["items"]] == ids
    first = body["items"][0]
    assert first["order"] == order_id and first["label"] == "정면·내부" and first["src"] == "user"
    assert len(first["key"]) == 16 and "김비밀" not in json.dumps(body, ensure_ascii=False)
    assert len(base64.b64decode(first["feat"])) == 1536
    assert first["by"] == agent_digest.anon_id(user_id, str(client.application.config.get("SECRET_KEY") or "")) != f"p{user_id}"
    assert body["items"][1]["by"] is None
    page = client.get(URL + "?kind=memory&limit=1", headers=_auth()).get_json()["data"]
    assert [r["id"] for r in page["items"]] == ids[:1] and page["next"] == ids[0]
    rest = client.get(URL + f"?kind=memory&after={page['next']}", headers=_auth()).get_json()["data"]
    assert [r["id"] for r in rest["items"]] == ids[1:]
    future = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)).isoformat()
    assert client.get(URL + f"?kind=memory&since={future}", headers=_auth()).get_json()["data"]["items"] == []


def test_sheets_carry_learning_fields_without_customer_info(client, armed):
    order_id, _, _ = _seed()
    body = client.get(URL + "?kind=sheets", headers=_auth()).get_json()["data"]
    text = json.dumps(body, ensure_ascii=False)
    for word in SECRET_WORDS:
        assert word not in text, word
    assert "form" not in text and "customer" not in text
    (sheet,) = body["items"]
    assert sheet["order"] == order_id and sheet["sheet"] == 0 and sheet["product_index"] == 0 and sheet["family"] == "붙박이장"
    img = sheet["images"][0]
    assert img["part"] == {"label": "정면·내부", "src": "user", "ai": "정면·도어", "conf": 0.7, "head": "h1", "arr": [1, 2, 3, 4]}
    assert img["w"] == 300 and img["natural_w"] == 600 and len(img["key"]) == 16
    assert sheet["bom"] == [{"sec": "SR", "a": 60, "b": 2440, "q": 2}, {"sec": "SR", "a": 120, "b": 2440, "q": 1},
                            {"sec": "DOOR", "a": 483, "b": 2160, "q": 4}, {"sec": "DOOR", "ea": 2}]
    assert sheet["calc"]["out"] == [{"sec": "SR", "a": 60, "b": 2440, "q": 2}] and sheet["calc"]["in"] == {"W": 3500}
    assert sheet["review"] == {"off": ["head:phone"], "seen": ["head:phone", "unsorted"]}


def test_bom_lines_and_token_unit(monkeypatch):
    assert agent_digest.bom_lines(["60*2440=2", "[옷봉]\n925=3\n925 = 1 EA", None, "[선반] 500×300＝2"]) == [
        {"sec": "옷봉", "a": 925, "q": 3}, {"sec": "옷봉", "a": 925, "q": 1}, {"sec": "기타", "a": 500, "b": 300, "q": 2}]
    monkeypatch.setenv(agent_digest.TOKEN_ENV, hashlib.sha256(TOKEN.encode()).hexdigest().upper())
    assert agent_digest.token_configured() and agent_digest.token_ok(f"Bearer {TOKEN}")
    assert not agent_digest.token_ok(None) and not agent_digest.token_ok(f"Bearer {TOKEN}x")
    monkeypatch.setenv(agent_digest.TOKEN_ENV, "not-a-hash")
    assert not agent_digest.token_configured() and not agent_digest.token_ok(f"Bearer {TOKEN}")
    assert agent_digest.anon_id(7, "s") == agent_digest.anon_id(7, "s") != agent_digest.anon_id(8, "s")
    assert agent_digest.key_hash(None) is None


def test_family_rule_matches_retrain_tool():
    from tools.drawing_ai.retrain_data import family_of as tool_family

    for text in ("냉장고장 키큰", "주방 하부장", "몰딩 여닫이장", "슬라이딩 붙박이", "신발장", "", "홈카페장"):
        assert agent_digest.family_of(text) == tool_family(text)
