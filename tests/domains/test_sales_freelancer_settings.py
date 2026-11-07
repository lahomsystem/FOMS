"""FCOMM-01 T1 — 프리랜서 설정(SystemSetting ``sales_freelancer_settings``) · 설정 API · 설정 화면.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §2.3 · §4.1 · §9 · §11.2 · J5 · J7 · J8.
요율 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.sales_commission.settings import (
    SETTINGS_KEY,
    FreelancerSettingsError,
    active_freelancers,
    add_rate,
    is_freelancer,
    latest_closed_month,
    load_settings,
    match_name_map,
    save_freelancer,
)
from models import SecurityLog, SystemSetting, User
from tests.domains.test_auth_finance import _login, _make_user

API = "/api/admin/sales-freelancers"
PAGE = "/admin/sales-freelancers"
_RATE = {"effective_month": "2030-01", "lahom_bp": 111, "haud_bp": 222, "personal_bp": 333}


@pytest.fixture
def policy_on(app):
    """정책 가드(ADMIN_OPS manifest)를 켠 채로 본다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _payload(**kw):
    base = {"match_name": "가짜프리", "start_month": "2030-01", "tax_type": "WITHHOLD_3_3", "active": True}
    base.update(kw)
    return base


def _save(user, *, version=0, **kw):
    out = save_freelancer(db_session, user.id, _payload(**kw), base_version=version, actor_user_id=None)
    db_session.commit()
    return out


def _error(fn, *args, **kwargs) -> FreelancerSettingsError:
    with pytest.raises(FreelancerSettingsError) as info:
        fn(*args, **kwargs)
    db_session.rollback()
    return info.value


# --------------------------------------------------------------------------
# 서비스 — 저장 · 읽기 · 검사
# --------------------------------------------------------------------------
def test_save_load_roundtrip_and_rate_history(app):
    sales = _make_user("STAFF", "SALES")
    assert load_settings(db_session) == (0, {})
    version, config, changed = _save(sales, match_name="  가짜프리 ")
    assert version == 1 and config.match_name == "가짜프리" and "match_name" in changed
    version, config, rate = add_rate(db_session, sales.id, _RATE, base_version=1, actor_user_id=7)
    db_session.commit()
    assert version == 2 and rate.by == 7 and rate.at
    add_rate(db_session, sales.id, {**_RATE, "effective_month": "2029-06"}, base_version=2, actor_user_id=7)
    db_session.commit()
    version, configs = load_settings(db_session)
    got = configs[sales.id]
    assert version == 3 and got.tax_type == "WITHHOLD_3_3" and got.start_month == "2030-01" and got.active
    assert [r.effective_month for r in got.rates] == ["2029-06", "2030-01"]  # 적용 달 순서
    assert got.rate_for("2029-05") is None and got.rate_for("2029-12").effective_month == "2029-06"
    assert got.rate_for("2031-01").lahom_bp == 111
    row = db_session.get(SystemSetting, SETTINGS_KEY)
    assert row.setting_value["freelancers"][str(sales.id)]["rates"][1]["personal_bp"] == 333


def test_first_rate_with_new_freelancer_and_profile_edit_keeps_rates(app):
    sales = _make_user("STAFF", "SALES")
    _version, config, _ = _save(sales, rate=_RATE)
    assert [r.haud_bp for r in config.rates] == [222]
    _version, config, changed = _save(sales, version=1, tax_type="VAT_10", rate={**_RATE, "effective_month": "2031-01"})
    assert changed == ["tax_type"] and len(config.rates) == 1  # 고칠 때 rate 는 무시 — 요율은 add_rate 로만


def test_stale_version_is_409(app):
    sales = _make_user("STAFF", "SALES")
    _save(sales)
    err = _error(save_freelancer, db_session, sales.id, _payload(), base_version=0, actor_user_id=None)
    assert err.status == 409
    err = _error(add_rate, db_session, sales.id, _RATE, base_version=0, actor_user_id=None)
    assert err.status == 409
    assert load_settings(db_session)[0] == 1


def test_match_name_duplicate_with_other_active_user_rejected(app):
    sales = _make_user("STAFF", "SALES")
    other = _make_user("STAFF", "CS")
    other.name = "가짜동명"
    db_session.commit()
    err = _error(save_freelancer, db_session, sales.id, _payload(match_name=" 가짜동명"), base_version=0,
                 actor_user_id=None)
    assert err.status == 400 and "다른 직원 이름" in str(err)
    # 대조군 1: 본인 이름과 같은 맞출 이름은 된다.
    _save(sales, match_name=sales.name)
    # 대조군 2: 꺼진 사용자 이름과는 겹쳐도 된다.
    other.is_active = False
    db_session.commit()
    second = _make_user("STAFF", "SALES")
    _save(second, version=1, match_name="가짜동명")
    # 프리랜서끼리 같은 맞출 이름은 안 된다.
    third = _make_user("STAFF", "SALES")
    err = _error(save_freelancer, db_session, third.id, _payload(match_name="가짜동명"), base_version=2,
                 actor_user_id=None)
    assert "다른 프리랜서" in str(err)


@pytest.mark.parametrize("role,team,active", [
    ("MANAGER", "CS", True), ("STAFF", "CS", True), ("STAFF", "ACCOUNTING", True), ("ADMIN", None, True),
    ("STAFF", "SALES", False), ("MANAGER", "SALES", False),
])
def test_only_active_staff_sales_accounts(app, role, team, active):
    user = _make_user(role, team)
    user.is_active = active
    db_session.commit()
    err = _error(save_freelancer, db_session, user.id, _payload(), base_version=0, actor_user_id=None)
    assert err.status == 400
    assert load_settings(db_session) == (0, {})


def test_missing_user_is_404_and_inactive_account_can_still_be_turned_off(app):
    assert _error(save_freelancer, db_session, 999999, _payload(), base_version=0, actor_user_id=None).status == 404
    sales = _make_user("STAFF", "SALES")
    _save(sales)
    sales.is_active = False
    db_session.commit()
    _version, config, _ = _save(sales, version=1, active=False)
    assert config.active is False and active_freelancers(db_session) == {}


@pytest.mark.parametrize("field,value", [
    ("lahom_bp", -1), ("haud_bp", 10001), ("personal_bp", "abc"), ("lahom_bp", None), ("haud_bp", True),
])
def test_bp_out_of_range_rejected(app, field, value):
    sales = _make_user("STAFF", "SALES")
    _save(sales)
    err = _error(add_rate, db_session, sales.id, {**_RATE, field: value}, base_version=1, actor_user_id=None)
    assert err.status == 400


def test_bp_edges_allowed(app):
    sales = _make_user("STAFF", "SALES")
    _save(sales)
    _v, config, _r = add_rate(db_session, sales.id, {**_RATE, "lahom_bp": 0, "haud_bp": 10000}, base_version=1,
                              actor_user_id=None)
    assert (config.rates[0].lahom_bp, config.rates[0].haud_bp) == (0, 10000)


@pytest.mark.parametrize("month", ["2030-13", "2030-1", "203001", "", "2030-00", "abcd-ef"])
def test_bad_month_rejected(app, month):
    sales = _make_user("STAFF", "SALES")
    assert _error(save_freelancer, db_session, sales.id, _payload(start_month=month), base_version=0,
                  actor_user_id=None).status == 400
    _save(sales)
    assert _error(add_rate, db_session, sales.id, {**_RATE, "effective_month": month}, base_version=1,
                  actor_user_id=None).status == 400


def test_bad_tax_type_and_empty_match_name_rejected(app):
    sales = _make_user("STAFF", "SALES")
    assert _error(save_freelancer, db_session, sales.id, _payload(tax_type="VAT_3"), base_version=0,
                  actor_user_id=None).status == 400
    assert _error(save_freelancer, db_session, sales.id, _payload(match_name="   "), base_version=0,
                  actor_user_id=None).status == 400


def test_duplicate_effective_month_rejected(app):
    sales = _make_user("STAFF", "SALES")
    _save(sales)
    add_rate(db_session, sales.id, _RATE, base_version=1, actor_user_id=None)
    db_session.commit()
    err = _error(add_rate, db_session, sales.id, {**_RATE, "lahom_bp": 999}, base_version=2, actor_user_id=None)
    assert err.status == 400 and str(err) == "같은 달 요율이 이미 있어요."


def test_rate_for_unknown_freelancer_is_404(app):
    sales = _make_user("STAFF", "SALES")
    assert _error(add_rate, db_session, sales.id, _RATE, base_version=0, actor_user_id=None).status == 404


def test_latest_closed_month_is_none_until_closings_table(app):
    sales = _make_user("STAFF", "SALES")
    assert latest_closed_month(db_session, sales.id) is None  # 마감 표(T9) 전에는 검사 생략


def test_match_name_map_and_is_freelancer(app):
    on = _make_user("STAFF", "SALES")
    off = _make_user("STAFF", "SALES")
    stranger = _make_user("STAFF", "SALES")
    _save(on, match_name="가짜켬")
    _save(off, version=1, match_name="가짜끔", active=False)
    assert match_name_map(db_session) == {"가짜켬": on.id}
    assert set(active_freelancers(db_session)) == {on.id}
    assert is_freelancer(db_session, on) and not is_freelancer(db_session, off)
    assert not is_freelancer(db_session, stranger) and not is_freelancer(db_session, None)
    with app.test_request_context("/"):
        assert is_freelancer(db_session, on) and not is_freelancer(db_session, stranger)


# --------------------------------------------------------------------------
# API · 화면 권한(§11.2)
# --------------------------------------------------------------------------
_READERS = [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]
_OUTSIDERS = [("MANAGER", "CS"), ("STAFF", "SALES"), ("STAFF", "CS"), ("VIEWER", None)]


def _as(app, role, team):
    client = app.test_client()
    user = _make_user(role, team)
    _login(client, user)
    return client, user


@pytest.mark.parametrize("role,team", _READERS)
def test_get_allowed_for_accounting_and_admin(app, policy_on, role, team):
    sales_id = _make_user("STAFF", "SALES").id
    client, _user = _as(app, role, team)
    resp = client.get(API)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["version"] == 0 and body["data"]["freelancers"] == []
    assert sales_id in [c["user_id"] for c in body["data"]["candidates"]]


@pytest.mark.parametrize("role,team", _OUTSIDERS)
def test_get_denied_for_others(app, policy_on, role, team):
    client, _user = _as(app, role, team)
    resp = client.get(API)
    assert resp.status_code == 403 and resp.get_json()["success"] is False


def test_get_unauthenticated_is_401(app):
    assert app.test_client().get(API).status_code == 401


def test_admin_post_save_and_rate_with_audit_and_409(app, policy_on):
    sales = _make_user("STAFF", "SALES")
    sales_id, sales_username = sales.id, sales.username
    client, admin = _as(app, "ADMIN", None)
    admin_id = admin.id
    body = {"user_id": sales_id, **_payload(), "rate": _RATE, "version": 0}
    resp = client.post(API, json=body)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["version"] == 1 and data["candidates"] == []
    row = data["freelancers"][0]
    assert row["match_name"] == "가짜프리" and row["username"] == sales_username and len(row["rates"]) == 1
    assert client.post(API, json=body).status_code == 409  # 낡은 version
    resp = client.post(f"{API}/{sales_id}/rates", json={**_RATE, "effective_month": "2031-02", "version": 1})
    assert resp.status_code == 200 and resp.get_json()["data"]["version"] == 2
    resp = client.post(f"{API}/{sales_id}/rates", json={**_RATE, "effective_month": "2031-02", "version": 2})
    assert resp.status_code == 400 and resp.get_json()["error"] == "같은 달 요율이 이미 있어요."
    logs = db_session.query(SecurityLog).filter(SecurityLog.user_id == admin_id).order_by(SecurityLog.id).all()
    assert [log.action for log in logs] == ["SALES_FREELANCER_SAVED", "SALES_FREELANCER_RATE_ADDED"]
    assert logs[1].detail["effective_month"] == "2031-02" and logs[0].target_id == sales_id


@pytest.mark.parametrize("role,team", [("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING"), ("MANAGER", "CS"),
                                       ("STAFF", "SALES")])
def test_post_denied_for_non_admin(app, policy_on, role, team):
    sales = _make_user("STAFF", "SALES")
    client, _user = _as(app, role, team)
    resp = client.post(API, json={"user_id": sales.id, **_payload(), "version": 0})
    assert resp.status_code == 403
    resp = client.post(f"{API}/{sales.id}/rates", json={**_RATE, "version": 0})
    assert resp.status_code == 403
    assert db_session.get(SystemSetting, SETTINGS_KEY) is None


def test_post_denied_by_handler_even_without_policy_engine(app):
    sales = _make_user("STAFF", "SALES")
    client, _user = _as(app, "MANAGER", "ACCOUNTING")
    assert client.post(API, json={"user_id": sales.id, **_payload(), "version": 0}).status_code == 403


def test_page_admin_has_edit_controls(app):
    client, _user = _as(app, "ADMIN", None)
    resp = client.get(PAGE)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'data-can-edit="1"' in html and "data-sf-form" in html and "data-sf-rate-form" in html
    assert "js/admin/sales-freelancers.js?v=" in html


@pytest.mark.parametrize("role,team", [("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")])
def test_page_accounting_is_read_only(app, role, team):
    client, _user = _as(app, role, team)
    resp = client.get(PAGE)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'data-can-edit="0"' in html and "data-sf-form" not in html and "data-sf-rate-form" not in html
    assert "보기만 할 수 있어요" in html


@pytest.mark.parametrize("role,team", _OUTSIDERS)
def test_page_denied_for_others(app, role, team):
    client, _user = _as(app, role, team)
    assert client.get(PAGE).status_code == 403


def test_page_requires_login(app):
    resp = app.test_client().get(PAGE)
    assert resp.status_code in (301, 302) and "/login" in resp.headers["Location"]


def test_admin_menu_links_to_page(app):
    client, _user = _as(app, "ADMIN", None)
    assert PAGE in client.get("/admin").get_data(as_text=True)


def test_no_user_rows_leak_into_candidates(app):
    """추가 후보는 켜진 영업팀 직원 · 매니저만(D27 — 운영 영업 계정은 매니저 등급. 대조군: 꺼진 영업 · CS 직원 · CS 매니저)."""
    keep = _make_user("STAFF", "SALES").id
    manager = _make_user("MANAGER", "SALES").id
    cs = _make_user("STAFF", "CS").id
    cs_manager = _make_user("MANAGER", "CS").id
    gone = _make_user("STAFF", "SALES")
    gone.is_active = False
    db_session.commit()
    gone = gone.id
    client, _user = _as(app, "ADMIN", None)
    ids = [c["user_id"] for c in client.get(API).get_json()["data"]["candidates"]]
    assert {keep, manager} <= set(ids) and not {cs, cs_manager, gone} & set(ids)
    assert db_session.query(User).count() == 6
