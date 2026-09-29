"""알림톡 ``#{문서종류}`` 회차 이름 + 공유 화면 제목 회차(설계서 2026-09-29 §4.3 · Q3 · Q6).

스위치 ``FOMS_SHARE_ROUND_DOC_LABEL`` 은 ``"1"`` 일 때만 켜진다(기본 꺼짐 — 운영 첫 발송
확인 전에는 고객 이름이 지금과 같다). 켜지면 회차(``drawing_round_info`` — 1 + 마지막 전달
앞 수정요청 수) 2 이상에서 "수정 도면(N차)". 수정요청 없이 더 올린 전달은 "도면" 그대로다.
알림톡·회사 문자·내 폰 문자 본문이 같은 함수를 쓴다. 통합(버튼 2개) 템플릿에는 변수가 없다.
"""
from __future__ import annotations

import datetime
from contextlib import contextmanager

import pytest
from flask import template_rendered
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
import foms.services.storage as storage_module
from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from foms.services.orders import drawing_customer_send_view as view_mod
from foms.services.orders.drawing_customer_send import (
    SHARE_ROUND_DOC_LABEL_ENV,
    share_doc_label,
    share_round_label,
)
from models import Order, User

_ENV_KEYS = ('SOLAPI_PF_ID_LAHOM', 'SOLAPI_PF_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_BOTH_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD',
             'SOLAPI_SENDER_PHONE_LAHOM', 'SOLAPI_SENDER_PHONE_HAUD',
             'SOLAPI_SENDER_FALLBACK_LAHOM', 'SOLAPI_SENDER_FALLBACK_HAUD',
             'SOLAPI_SENDER_PHONE')


def _hist(*actions):
    out = []
    for i, a in enumerate(actions):
        out.append({"action": a, "at": f"2026-09-2{i} 01:00:00"})
    return out


def _sd_round(n: int) -> dict:
    """회차 n 인 sd(n=0 전달 없음, n≥1 은 앞에 수정요청 n-1 건)."""
    if n == 0:
        return {"drawing_transfer_history": []}
    actions = ["TRANSFER"]
    for _ in range(n - 1):
        actions += ["REQUEST_REVISION", "TRANSFER"]
    return {"drawing_transfer_history": _hist(*actions)}


@pytest.fixture
def label_off(monkeypatch):
    monkeypatch.delenv(SHARE_ROUND_DOC_LABEL_ENV, raising=False)


@pytest.fixture
def label_on(monkeypatch):
    monkeypatch.setenv(SHARE_ROUND_DOC_LABEL_ENV, "1")


_FIXED = {"drawing": "도면", "estimate": "견적서", "bundle": "도면·계약서", "weird": "문서"}


@pytest.mark.parametrize("n", [0, 1, 2, 3])
@pytest.mark.parametrize("kind", list(_FIXED))
def test_switch_off_is_fixed_table(label_off, n, kind):
    assert share_doc_label(_sd_round(n), kind) == _FIXED[kind]
    assert share_round_label(_sd_round(n)) == ""


@pytest.mark.parametrize("value", ["", "0", "true", "yes", " 2 "])
def test_switch_other_values_are_off(monkeypatch, value):
    monkeypatch.setenv(SHARE_ROUND_DOC_LABEL_ENV, value)
    assert share_doc_label(_sd_round(2), "drawing") == "도면"


_ON = {
    ("drawing", 0): "도면", ("drawing", 1): "도면", ("drawing", 2): "수정 도면(2차)", ("drawing", 3): "수정 도면(3차)",
    ("bundle", 0): "도면·계약서", ("bundle", 1): "도면·계약서", ("bundle", 2): "수정 도면(2차)·계약서",
    ("bundle", 3): "수정 도면(3차)·계약서",
    ("estimate", 0): "견적서", ("estimate", 2): "견적서",
    ("weird", 2): "문서",
}


@pytest.mark.parametrize("key", list(_ON))
def test_switch_on_table(label_on, key):
    kind, n = key
    assert share_doc_label(_sd_round(n), kind) == _ON[key]


def test_append_without_revision_stays_first(label_on):
    sd = {"drawing_transfer_history": _hist("TRANSFER", "TRANSFER", "TRANSFER")}
    assert share_doc_label(sd, "drawing") == "도면"
    assert share_round_label(sd) == ""


def test_share_round_label_on(label_on):
    assert share_round_label(_sd_round(1)) == ""
    assert share_round_label(_sd_round(2)) == "2차"


def test_both_template_prefix_same_as_share_route():
    assert view_mod.BOTH_TEMPLATE_ENV_PREFIX == share_routes._BOTH_TEMPLATE_ENV_PREFIX


# ── 라우트 ───────────────────────────────────────────────────────────────────
def _mk_order(n: int) -> Order:
    sd = {
        'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
        'items': [{'product_name': '무몰딩 여닫이', 'quantity': 1, 'price': 100000}],
        **_sd_round(n),
    }
    order = Order(received_date=datetime.date(2026, 8, 18), customer_name='임다슬', phone='010-2473-6730',
                  address='Seoul', product='가구', status='ERPORDER', is_erp_order=True, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username):
    user = User(username=username, password=generate_password_hash('pw'), role='STAFF', team='CS',
                name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess['user_id'], sess['username'], sess['role'] = user.id, username, 'STAFF'


@pytest.fixture
def ata_stub(monkeypatch):
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return 'ATA-1'

    monkeypatch.setattr(ka, '_solapi_send', _fake)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_PF_ID_HAUD', 'PF-HAUD')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_ID_HAUD', 'TPL-HAUD')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    return calls


@pytest.fixture
def sms_stub(monkeypatch):
    calls = []

    def _fake(*, to, from_, text):
        calls.append({'to': to, 'from_': from_, 'text': text})
        return 'SMS-1'

    monkeypatch.setattr(ka, '_solapi_send_text', _fake)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    return calls


def _share(order_id, kind='drawing'):
    snapshot = None
    if kind == 'bundle':
        snapshot = osvc.build_estimate_snapshot(db_session.get(Order, order_id))
    row, token = osvc.create_share_token(db_session, order_id, kind, snapshot=snapshot)
    db_session.commit()
    return row.id, token


def test_alimtalk_doc_label_round2_switch_on(client, ata_stub, label_on):
    order = _mk_order(2)
    _login(client, 'lbl1')
    sid, token = _share(order.id)
    res = client.post(f'/api/share/send-alimtalk/{sid}', json={'token': token})
    assert res.status_code == 200, res.get_json()
    assert ata_stub[0]['variables']['#{문서종류}'] == '수정 도면(2차)'


def test_alimtalk_doc_label_round2_switch_off(client, ata_stub, label_off):
    order = _mk_order(2)
    _login(client, 'lbl2')
    sid, token = _share(order.id)
    assert client.post(f'/api/share/send-alimtalk/{sid}', json={'token': token}).status_code == 200
    assert ata_stub[0]['variables']['#{문서종류}'] == '도면'


def test_sms_body_uses_round_label(client, sms_stub, label_on):
    order = _mk_order(3)
    _login(client, 'lbl3')
    sid, token = _share(order.id)
    res = client.post(f'/api/share/send-sms/{sid}', json={'token': token})
    assert res.status_code == 200, res.get_json()
    assert '요청하신 수정 도면(3차) 열람 링크' in sms_stub[0]['text']


def test_create_sms_text_uses_round_label(client, label_on):
    order = _mk_order(2)
    _login(client, 'lbl4')
    res = client.post(f'/api/share/create/{order.id}', json={'kind': 'bundle'})
    assert res.status_code == 200, res.get_json()
    assert '요청하신 수정 도면(2차)·계약서 열람 링크' in res.get_json()['data']['sms_text']


def test_both_template_bundle_has_no_doc_label_variable(client, ata_stub, label_on, monkeypatch):
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD', 'TPL-BOTH')
    order = _mk_order(2)
    _login(client, 'lbl5')
    sid, token = _share(order.id, 'bundle')
    assert client.post(f'/api/share/send-alimtalk/{sid}', json={'token': token}).status_code == 200
    assert ata_stub[0]['template_id'] == 'TPL-BOTH'
    assert '#{문서종류}' not in ata_stub[0]['variables']


# ── 공유 화면 제목 값(Q3) ────────────────────────────────────────────────────
class _R2:
    storage_type = "r2"

    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return f"https://r2.example/{key}"


@contextmanager
def _captured(app):
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template.name, context))

    template_rendered.connect(record, app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app)


@pytest.mark.parametrize("n,on,expected", [(2, True, "2차"), (1, True, ""), (2, False, "")])
def test_share_view_passes_share_round_label(app, client, monkeypatch, n, on, expected):
    if on:
        monkeypatch.setenv(SHARE_ROUND_DOC_LABEL_ENV, "1")
    else:
        monkeypatch.delenv(SHARE_ROUND_DOC_LABEL_ENV, raising=False)
    monkeypatch.setattr(storage_module, "_storage_instance", _R2())
    order = _mk_order(n)
    _, token = _share(order.id)
    with _captured(app) as rendered:
        res = client.get(f'/s/{token}')
    assert res.status_code == 200
    ctx = next(c for name, c in rendered if name == 'orders/share_view.html')
    assert ctx['share_round_label'] == expected
