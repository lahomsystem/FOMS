"""계산기 값 확인 날(사장님 결정 D74 · 검수 R17-5 · R17-8) — 값 지문 · 바뀐 때 · [계산기 값 확인했어요] 버튼.

확인 날 = 제품 · 옵션 값이 실제로 바뀐 때와 버튼을 누른 때 가운데 늦은 것. 비고 · 현장 스펙 프리셋 저장은 세지 않는다. 처음
보는 지문은 '바뀜'이 아니다(버튼 필요). 지문을 적다가 실패하면 '확인 필요'. 버튼은 ADMIN 만 · CSRF · 정책 가드 · 감사 원장.
시각은 시간대 있는 UTC 글이다. 금액 숫자는 적지 않는다(값 바꿈은 파일 값 + 1 로 만든다).
"""

from __future__ import annotations

import datetime
import os

import pytest
from itsdangerous import URLSafeSerializer
from sqlalchemy.exc import OperationalError

from db import db_session
from foms.services.cs_agent import quote_check as qk
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from foms.services.wdcalculator import catalog as cat
from models import SecurityLog, SystemSetting
from tests.domains.test_cs_admin_panel_api import API, env, flag, login  # noqa: F401 — env · flag 는 fixture
from tests.support.cs_quote_support import CATEGORIES, MOLD, NOW, catalog, confirm_prices

HOUR = datetime.timedelta(hours=1)


def stored():
    db_session.expire_all()
    row = db_session.get(SystemSetting, qk.KEY)
    return None if row is None else row.setting_value


def save(app, products=None, presets=False, notes=False):
    import foms.api.wdcalculator.blueprint as wd

    with app.app_context():
        if products is not None:
            assert wd.save_products(products)
        if presets:
            assert wd.save_spec_field_presets({f: [{"id": 1, "name": "합성"}] for f in wd.SPEC_PRESET_FIELDS})
        if notes:
            assert wd.save_notes_categories([{"id": 1, "name": "합성 비고", "options": [{"id": 1, "name": "합성"}]}])


def test_the_first_fingerprint_is_not_a_change_and_needs_the_button(app):
    first = qk.observe(db_session, catalog(), now=NOW)
    assert (first.confirmed_at, first.needs_check(NOW)) == (None, True)
    value = stored()
    assert value["fingerprint"] == qk.fingerprint(catalog()) and value["changed_at"] is None
    again = qk.observe(db_session, catalog(), now=NOW + HOUR)  # 같은 값 — 아무것도 안 바뀜
    assert again.confirmed_at is None and stored()["changed_at"] is None


def test_only_product_or_option_value_changes_count(app, wdcalculator_settings_env):
    save(app, products=[dict(MOLD)])
    qk.observe(db_session, cat.read_catalog(), now=NOW)  # 처음 봄
    confirm_prices(cat.read_catalog(), when=NOW)
    save(app, presets=True, notes=True)  # 비고 · 현장 스펙 프리셋 — 확인 날에 안 든다
    after_presets = qk.observe(db_session, cat.read_catalog(), now=NOW + 3 * HOUR)
    assert (after_presets.changed_at, after_presets.confirmed_at) == (None, NOW)
    save(app, products=[dict(MOLD, price_30cm=MOLD["price_30cm"] + 1)])  # 값이 실제로 바뀐 저장
    changed = qk.observe(db_session, cat.read_catalog(), now=NOW + 5 * HOUR)
    assert changed.changed_at == changed.confirmed_at == NOW + 5 * HOUR
    assert stored()["changed_at"].endswith("+00:00") and stored()["checked_at"].endswith("+00:00")  # 시간대 있는 UTC


def test_the_confirm_day_is_the_later_of_change_and_button(app):
    qk.observe(db_session, catalog(), now=NOW)
    confirm_prices(catalog(), when=NOW)
    bumped = catalog(products=[dict(MOLD, price_1cm=MOLD["price_1cm"] + 1)])
    changed = qk.observe(db_session, bumped, now=NOW + 2 * HOUR)
    assert changed.confirmed_at == NOW + 2 * HOUR and changed.checked_at == NOW
    late = confirm_prices(bumped, when=NOW + 30 * HOUR)
    check = qk.observe(db_session, bumped, now=NOW + 31 * HOUR)
    assert (check.confirmed_at, check.checked_by) == (NOW + 30 * HOUR, late.id)
    assert not check.needs_check(NOW + 30 * HOUR + datetime.timedelta(days=14))
    assert check.needs_check(NOW + 30 * HOUR + datetime.timedelta(days=14, seconds=1))


def test_a_write_failure_or_the_seed_file_means_needs_check(app):
    class Broken:
        def get(self, *args, **kwargs):
            raise OperationalError("합성", {}, Exception("합성"))

        def rollback(self):
            self.rolled = True

    broken = Broken()
    failed = qk.observe(broken, catalog(), now=NOW)
    assert (failed.failed, failed.needs_check(NOW), broken.rolled) == (True, True, True)
    assert qk.observe(db_session, catalog(seed=True), now=NOW).needs_check(NOW) and stored() is None
    with pytest.raises(qk.CheckError):
        qk.confirm(db_session, catalog(seed=True), actor_user_id=1, now=NOW)
    with pytest.raises(ValueError):
        qk.observe(db_session, catalog(), now=NOW.replace(tzinfo=None))  # 시간대 없는 시각은 받지 않는다


def test_the_fingerprint_skips_notes_and_presets_but_sees_any_product_or_option_field():
    base = qk.fingerprint(catalog())
    assert qk.fingerprint(cat.Catalog(catalog().products, catalog().option_categories)) == base
    assert qk.fingerprint(catalog(products=[dict(MOLD, quote_rule="hinge")])) != qk.fingerprint(
        catalog(products=[dict(MOLD)]))
    assert qk.fingerprint(catalog(categories=[{"id": 9, "name": "합성", "options": []}])) != base


# ── [계산기 값 확인했어요] 버튼 ──────────────────────────────────────────
def test_the_button_is_admin_only_audited_and_moves_the_confirm_day(app, client, env, wdcalculator_settings_env):
    save(app, products=[dict(MOLD)])
    assert client.post(f"{API}/calculator-check").status_code == 401
    login(client, role="STAFF")
    denied = client.post(f"{API}/calculator-check")
    assert (denied.status_code, denied.get_json()["success"], stored()) == (403, False, None)
    with client.session_transaction() as sess:
        sess.clear()
    uid = login(client, role="ADMIN", name="합성 확인자")
    resp = client.post(f"{API}/calculator-check")
    data = resp.get_json()["data"]
    assert resp.status_code == 200 and data["state"]["quote_check"]["checked_by"] == "합성 확인자"
    assert data["state"]["quote_check"]["needs_check"] is False and data["state"]["quote_check"]["pending"] is False
    value = stored()
    assert value["checked_by"] == uid and value["fingerprint"] == qk.fingerprint(cat.read_catalog())
    log = db_session.query(SecurityLog).filter_by(action=qk.AUDIT_ACTION).one()
    assert log.user_id == uid and log.detail["key"] == qk.KEY
    page = client.get("/admin/cs-agent").get_data(as_text=True)
    assert "계산기 값 확인했어요" in page and "data-cs-calc-check" in page and 'data-calc-check-url="' in page


def test_the_button_refuses_the_seed_file(client, env, wdcalculator_settings_env):
    login(client)
    resp = client.post(f"{API}/calculator-check")
    assert resp.status_code == 400 and stored() is None


def test_the_button_needs_csrf_and_the_admin_policy(app, client, env, flag, wdcalculator_settings_env):
    save(app, products=[dict(MOLD)])
    flag("WRITE_GUARD_ENABLED")
    login(client)
    blocked = client.post(f"{API}/calculator-check")
    assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked" and stored() is None
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
    assert client.post(f"{API}/calculator-check", headers={"X-CSRF-Token": token}).status_code == 200


def test_the_policy_guard_refuses_a_manager(client, env, flag, wdcalculator_settings_env):
    flag("AUTH_POLICY_ENABLED")
    login(client, role="MANAGER")
    denied = client.post(f"{API}/calculator-check")
    assert denied.status_code == 403 and denied.headers.get("X-Auth-Policy") == "denied" and stored() is None


def test_the_panel_view_reports_pending_changes_without_writing(app, wdcalculator_settings_env):
    save(app, products=[dict(MOLD)])
    confirm_prices(cat.read_catalog(), when=NOW)
    save(app, products=[dict(MOLD, price_30cm=MOLD["price_30cm"] + 1)])
    before = stored()
    view = qk.view(db_session, now=NOW + HOUR)
    assert (view["pending"], view["needs_check"], view["seed"]) == (True, False, False) and stored() == before
    assert view["confirmed"] is not None and view["fresh_days"] == 14
    assert CATEGORIES  # 처음 채우기 파일의 옵션 목록을 읽었다
