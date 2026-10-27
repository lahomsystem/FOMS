"""도면 마법사 그림 종류 기억(실시간 학습) API · 서비스 시험.

설계 정본: docs/plans/2026-10-26-drawing-part-memory-spec.md
- 남기기: 특징(float16 base64) · 이름표를 주문·그림 키마다 덮어쓴다. 형식이 하나라도 틀리면 400.
- 따르기: 사람이 고른 아주 비슷한 그림의 종류. 문턱 · 갈림 · 내부/도어 문턱 · 자신 있던 AI 문턱 · 자기 제외 · 판 다름.
- 같이 고치기: 고친 그림과 닮은 같은 시트 AI 이름표 그림.
- 켜고 끄기: SystemSetting ``drawing_part_memory`` (틀린 칸은 기본값).
"""

import base64
import json
from datetime import date

import numpy as np
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.main.models import SystemSetting
from foms.services import drawing_wizard_part_memory as pm
from models import DrawingPartMemory, Order, User


@pytest.fixture(autouse=True)
def _fresh_index():
    pm._INDEX.reset()   # 시험마다 DB 가 새로 만들어지므로 프로세스 캐시도 비운다
    yield
    pm._INDEX.reset()


def _login(client, *, username="mem-admin", role="ADMIN", team="DRAWING"):
    user = User(username=username, password=generate_password_hash("x"), role=role, team=team,
                name=f"{username}-name", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order():
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="시험", phone="010-0000-0000",
                  address="대구", product="붙박이장", status="DRAWING", manager_name="시험 담당",
                  is_erp_order=True, structured_data={"items": [{"product_name": "여닫이장"}]})
    db_session.add(order)
    db_session.commit()
    return order.id


def _unit(seed):
    v = np.random.default_rng(seed).standard_normal(768).astype(np.float32)
    return v / np.linalg.norm(v)


def _near(v, sim, seed=99):
    """v 와 코사인이 sim 인 단위 벡터."""
    r = np.random.default_rng(seed).standard_normal(768).astype(np.float32)
    r -= r.dot(v) * v
    r /= np.linalg.norm(r)
    w = sim * v + np.sqrt(1 - sim ** 2) * r
    return w / np.linalg.norm(w)


def _b64(v):
    return base64.b64encode(np.asarray(v, dtype="<f2").tobytes()).decode()


def _key(order_id, name):
    return f"orders/{order_id}/drawing_wizard/assets/{name}.png"


def _save(client, order_id, items):
    return client.post(f"/api/orders/{order_id}/drawing-wizard/part-memory", json={"items": items})


def _follow(client, order_id, vec, *, ai="정면·내부", conf=0.4, key="", fv="f1-dv2s-8b1f", label=None):
    item = {"id": "o-new", "f": _b64(vec), "fv": fv, "key": key, "ai": ai, "conf": conf}
    if label is not None:
        item["label"] = label
    resp = client.post(f"/api/orders/{order_id}/drawing-wizard/part-memory/match", json={"mode": "follow", "items": [item]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]["items"]["o-new"]


def _human(client, order_id, name, vec, label):
    resp = _save(client, order_id, [{"key": _key(order_id, name), "f": _b64(vec), "fv": "f1-dv2s-8b1f",
                                     "label": label, "src": "user", "ai": "정면·내부", "conf": 0.42, "head": "h1"}])
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_human_label_is_followed_by_a_near_identical_picture_in_another_order(client):
    _login(client)
    first, second = _order(), _order()
    v = _unit(1)
    _human(client, first, "door", v, "정면·도어")

    got = _follow(client, second, _near(v, 0.995), ai="정면·내부", conf=0.55)
    assert got["label"] == "정면·도어" and got["scope"] == "other" and got["n"] == 1 and not got["conflict"]
    # 내부/도어만 다르면 높은 문턱(0.985) — 0.97 은 따르지 않는다
    assert _follow(client, second, _near(v, 0.97), ai="정면·내부", conf=0.55) is None
    # 보기가 다른 짐작(미분류 · 낮은 확신)은 기본 문턱(0.95)만 넘으면 따른다
    assert _follow(client, second, _near(v, 0.96), ai="서랍 단면", conf=0.3)["label"] == "정면·도어"
    # 문턱 아래 · 판이 다른 특징은 따르지 않는다
    assert _follow(client, second, _near(v, 0.90), ai="서랍 단면", conf=0.3) is None
    assert _follow(client, second, _near(v, 0.995), ai="서랍 단면", conf=0.3, fv="f2-other") is None


def test_confident_ai_needs_the_strict_threshold_and_conflicts_do_not_follow(client):
    _login(client)
    first, second = _order(), _order()
    v = _unit(2)
    _human(client, first, "a", v, "부품 상세")
    # 자신 있던 AI(0.9) 짐작을 뒤집으려면 0.985 를 넘어야 한다
    assert _follow(client, second, _near(v, 0.96), ai="서랍 단면", conf=0.9) is None
    assert _follow(client, second, _near(v, 0.995), ai="서랍 단면", conf=0.9)["label"] == "부품 상세"
    # 같은 종류면 바꿀 것이 없다 — 단, AI 가 헷갈려 미분류로 둔 그림은 첫 짐작이 같아도 기억을 따른다
    assert _follow(client, second, _near(v, 0.995), ai="부품 상세", conf=0.6, label="부품 상세") is None
    assert _follow(client, second, _near(v, 0.96), ai="부품 상세", conf=0.3, label="미분류")["label"] == "부품 상세"
    # 문턱을 넘은 기억끼리 종류가 갈리면 따르지 않는다
    _human(client, first, "b", _near(v, 0.99, seed=7), "서랍 단면")
    got = _follow(client, second, _near(v, 0.995), ai="평면·상판", conf=0.3)
    assert got["conflict"] is True and got["label"] is None


def test_own_picture_is_not_its_own_memory_and_ai_rows_are_not_followed(client):
    _login(client)
    order = _order()
    v = _unit(3)
    _human(client, order, "self", v, "입체·도어")
    assert _follow(client, order, v, ai="서랍 단면", key=_key(order, "self")) is None
    # 같은 주문의 다른 그림은 기억을 쓴다(scope order)
    assert _follow(client, order, _near(v, 0.99), ai="서랍 단면", key=_key(order, "other"))["scope"] == "order"
    # 사람 → AI 로 바뀐 줄은 캐시에서 빠진다
    resp = _save(client, order, [{"key": _key(order, "self"), "label": "입체·도어", "src": "ai"}])
    assert resp.status_code == 200
    assert _follow(client, order, _near(v, 0.99), ai="서랍 단면", key=_key(order, "other")) is None


def test_save_upserts_given_fields_and_reports_missing_features(client):
    user_id = _login(client).id   # 요청 뒤에는 세션에서 떨어지므로 먼저 읽어 둔다
    order = _order()
    key = _key(order, "p1")
    resp = _save(client, order, [{"key": key, "label": "사진", "src": "user"}])
    assert resp.status_code == 200 and resp.get_json()["data"] == {"saved": 1, "missing": [key], "enabled": True}

    v, w = _unit(4), _unit(5)
    assert _save(client, order, [{"key": key, "f": _b64(v), "fv": "f1-dv2s-8b1f"}]).get_json()["data"]["missing"] == []
    _save(client, order, [{"key": key, "f": _b64(w), "fv": "f1-dv2s-8b1f", "ai": "사진", "conf": 0.97, "head": "h1"}])
    row = db_session.query(DrawingPartMemory).filter_by(order_id=order, asset_key=key).one()
    stored = np.frombuffer(row.feat, dtype="<f2").astype(np.float32)
    assert float(stored @ v) > 0.99   # 같은 판 특징은 처음 것 그대로
    assert (row.label, row.src, row.ai, row.conf, row.head) == ("사진", "user", "사진", 0.97, "h1")
    assert row.created_by == user_id and row.updated_by == user_id
    _save(client, order, [{"key": key, "f": _b64(w), "fv": "f2-new"}])
    db_session.expire_all()
    row = db_session.query(DrawingPartMemory).filter_by(order_id=order, asset_key=key).one()
    assert row.feat_v == "f2-new" and float(np.frombuffer(row.feat, dtype="<f2").astype(np.float32) @ w) > 0.99


@pytest.mark.parametrize("item", [
    {"key": "orders/1/other/a.png", "label": "사진", "src": "user"},
    {"label": "사진", "src": "user"},
    {"key": "KEY", "f": "abc", "fv": "f1"},
    {"key": "KEY", "f": "NAN", "fv": "f1"},
    {"key": "KEY", "f": "BIG", "fv": "f1"},
    {"key": "KEY", "f": "OK", "fv": "BAD FV"},
    {"key": "KEY", "label": "의자", "src": "user"},
    {"key": "KEY", "label": "사진", "src": "robot"},
    {"key": "KEY", "ai": "의자"},
    {"key": "KEY", "conf": 1.5},
    {"key": "KEY", "head": "h1 bad"},
])
def test_save_rejects_any_bad_item(client, item):
    _login(client)
    order = _order()
    item = dict(item)
    if item.get("key") == "KEY":
        item["key"] = _key(order, "x")
    special = {"NAN": np.full(768, np.nan, dtype=np.float32), "BIG": _unit(6) * 2, "OK": _unit(6)}
    if item.get("f") in special:
        item["f"] = _b64(special[item["f"]])
    assert _save(client, order, [item]).status_code == 400
    assert db_session.query(DrawingPartMemory).count() == 0


def test_save_limits_permissions_and_size(client):
    _login(client, username="viewer", role="STAFF", team="CS")
    order = _order()
    assert _save(client, order, [{"key": _key(order, "a"), "label": "사진", "src": "user"}]).status_code == 403
    _login(client)
    assert _save(client, 999999, [{"key": _key(999999, "a"), "label": "사진", "src": "user"}]).status_code == 404
    many = [{"key": _key(order, f"k{i}"), "label": "사진", "src": "ai"} for i in range(31)]
    assert _save(client, order, many).status_code == 400
    assert _save(client, order, []).status_code == 400


def test_spread_finds_similar_ai_pictures_with_the_door_rule(client):
    _login(client)
    order = _order()
    base = _unit(8)
    rows = {"fixed": (base, "정면·도어", "user"), "twin": (_near(base, 0.99, 1), "정면·내부", "ai"),
            "close": (_near(base, 0.97, 2), "정면·내부", "ai"), "far": (_unit(9), "정면·내부", "ai"),
            "human": (_near(base, 0.995, 3), "정면·내부", "user")}
    _save(client, order, [{"key": _key(order, n), "f": _b64(v), "fv": "f1-dv2s-8b1f", "label": lab, "src": src}
                          for n, (v, lab, src) in rows.items()])
    items = [{"id": n, "key": _key(order, n), "label": rows[n][1]} for n in ("twin", "close", "far", "human")]

    def spread(label):
        resp = client.post(f"/api/orders/{order}/drawing-wizard/part-memory/match",
                           json={"mode": "spread", "key": _key(order, "fixed"), "label": label, "items": items})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        return [x["id"] for x in resp.get_json()["data"]["ids"]]

    assert spread("정면·도어") == ["twin"]            # 내부/도어만 다르면 0.985 — 0.97 은 빼고, 사람 그림도 뺀다
    assert spread("서랍 단면") == ["twin", "close"]   # 다른 종류로 고치면 0.95


def test_policy_switches_and_tolerant_loading(client):
    _login(client)
    order = _order()
    db_session.add(SystemSetting(setting_key=pm.POLICY_KEY, version=1,
                                 setting_value={"store": False, "follow": False, "min_sim": "x", "min_sim_door": 0.99}))
    db_session.commit()
    policy = pm.load_policy(db_session)
    assert policy["store"] is False and policy["follow"] is False and policy["spread"] is True
    assert policy["min_sim"] == 0.95 and policy["min_sim_door"] == 0.99
    resp = _save(client, order, [{"key": _key(order, "a"), "label": "사진", "src": "user"}])
    assert resp.get_json()["data"]["enabled"] is False and db_session.query(DrawingPartMemory).count() == 0
    resp = client.post(f"/api/orders/{order}/drawing-wizard/part-memory/match",
                       json={"mode": "follow", "items": [{"id": "o1", "f": _b64(_unit(1)), "fv": "f1"}]})
    assert resp.get_json()["data"] == {"enabled": False}


def test_decide_rules_directly():
    policy = dict(pm.DEFAULT_POLICY)
    assert pm.decide("정면·내부", 0.3, [], policy) is None
    assert pm.decide("정면·내부", 0.3, [(0.97, "정면·도어", 1)], policy) is None          # 내부/도어 → 0.985
    assert pm.decide("정면·내부", 0.3, [(0.99, "정면·도어", 1)], policy)["label"] == "정면·도어"
    assert pm.decide("미분류", 0.2, [(0.96, "사진", 1)], policy)["label"] == "사진"
    assert pm.decide("평면·상판", 0.85, [(0.96, "부품 상세", 1)], policy) is None          # 자신 있던 AI → 0.985
    assert pm.decide("평면·상판", 0.3, [(0.97, "사진", 1), (0.96, "부품 상세", 2)], policy)["conflict"] is True
    assert pm.decide("사진", 0.3, [(0.96, "사진", 1)], policy, shown="미분류")["label"] == "사진"   # 헷갈린 그림은 첫 짐작과 같아도
    assert pm.decide("사진", 0.9, [(0.96, "사진", 1)], policy, shown="사진") is None


def test_wizard_page_config_carries_memory_switches(client):
    _login(client)
    order = _order()
    resp = client.get(f"/erp/drawing-workbench/{order}/wizard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    start = html.index('id="drawing-wizard-config" type="application/json">') + len('id="drawing-wizard-config" type="application/json">')
    cfg = json.loads(html[start:html.index("</script>", start)])
    assert cfg["part_memory"] == {"store": True, "follow": True, "spread": True}
    assert "js/drawing/part-memory.js" in html
    assert html.index("js/drawing/part-memory.js") < html.index("js/drawing/wizard.js")
