"""PASSWORD-POLICY-01: 비밀번호 강도 정책 버전·legacy 이행 계약 테스트 (SQLite 도메인 레인).

강도는 ``users.password_policy_version`` 컬럼이 유일한 SSOT 다(hash rehash 추정 금지).
새/변경/reset 은 항상 strong, legacy 는 WARN(업무 비차단)+persistent banner, active legacy
count 0 이면 ENFORCED, inactive legacy 는 blind reactivate 금지, weak rollback 금지,
CLI 는 비밀번호를 argv/env/stdout 로 흘리지 않는다.

이 파일은 항상 도는 SQLite ``client``/``db_session`` 레인이다(``app`` 픽스처가 테이블을
테스트별 생성·삭제해 격리). PG 전용(컬럼 server_default backfill·실 PG count)은
``tests/postgres/test_password_policy.py`` 가 opt-in 으로 검증한다. 앱 요청 teardown 이
세션을 remove 하므로 요청 후에는 미리 캡처한 정수 id 로 재조회한다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from db import db_session
from models import User
from foms.services.security.password_policy import (
    POLICY_VERSION_LEGACY,
    POLICY_VERSION_STRONG,
    WeakPasswordError,
    active_legacy_count,
    is_password_legacy,
    is_policy_enforced,
    legacy_counts_by_role,
    set_strong_password,
    validate_password_strength,
)
from tools.ops.password_policy_audit import run_audit, run_rotate

_STRONG_PW = "Abcdef12"   # 8자+영문+숫자 → strong 통과
_WEAK_PW = "abc"          # 강도 미달


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _make_user(username, *, role="STAFF", team=None, is_active=True,
               version=POLICY_VERSION_LEGACY, raw_password="whatever"):
    """지정 정책 버전으로 User 를 만든다(hash 는 강도와 무관하게 직접 설정)."""
    user = User(
        username=username,
        password=generate_password_hash(raw_password),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=is_active,
        password_policy_version=version,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


# --------------------------------------------------------------------------
# 강도 검사 + set_strong_password (chokepoint)
# --------------------------------------------------------------------------
def test_validate_strength_accepts_strong_rejects_weak(app):
    ok, _ = validate_password_strength(_STRONG_PW)
    assert ok is True
    for weak in ["", "short1", "abcdefgh", "12345678", _WEAK_PW]:
        bad_ok, reason = validate_password_strength(weak)
        assert bad_ok is False and reason  # 사유 문자열 존재


def test_set_strong_password_records_strong_and_hashes(app):
    user = _make_user("setter", version=POLICY_VERSION_LEGACY)
    set_strong_password(user, _STRONG_PW)
    assert user.password_policy_version == POLICY_VERSION_STRONG
    assert check_password_hash(user.password, _STRONG_PW)


def test_set_strong_password_rejects_weak_no_mutation(app):
    """약한 비번은 거부하고 user 를 건드리지 않는다(약한 비번 거부)."""
    user = _make_user("weakset", version=POLICY_VERSION_LEGACY)
    before_hash = user.password
    with pytest.raises(WeakPasswordError):
        set_strong_password(user, _WEAK_PW)
    assert user.password == before_hash
    assert user.password_policy_version == POLICY_VERSION_LEGACY


def test_weak_rollback_forbidden_on_strong_account(app):
    """한번 strong 이면 약한 값으로 되돌릴 수 없다(weak rollback 금지)."""
    user = _make_user("norollback", version=POLICY_VERSION_STRONG)
    with pytest.raises(WeakPasswordError):
        set_strong_password(user, _WEAK_PW)
    assert user.password_policy_version == POLICY_VERSION_STRONG


# --------------------------------------------------------------------------
# 컬럼 SSOT (hash rehash 추정 안 함)
# --------------------------------------------------------------------------
def test_version_is_ssot_not_hash_strength(app):
    """legacy 판정은 컬럼만 본다 — hash 의 실제 강도와 무관."""
    # 강한 평문이지만 버전 LEGACY → legacy 로 취급(추정 금지)
    strong_hash_legacy = _make_user("stronghash", version=POLICY_VERSION_LEGACY,
                                    raw_password=_STRONG_PW)
    assert is_password_legacy(strong_hash_legacy) is True
    # 약한 평문이지만 버전 STRONG → legacy 아님(컬럼이 SSOT)
    weak_hash_strong = _make_user("weakhash", version=POLICY_VERSION_STRONG,
                                  raw_password=_WEAK_PW)
    assert is_password_legacy(weak_hash_strong) is False


# --------------------------------------------------------------------------
# count / ENFORCED 전이
# --------------------------------------------------------------------------
def test_active_legacy_count_and_enforced_transition(app):
    a = _make_user("leg-a", role="STAFF", version=POLICY_VERSION_LEGACY)
    b = _make_user("leg-b", role="MANAGER", version=POLICY_VERSION_LEGACY)
    _make_user("strong-c", version=POLICY_VERSION_STRONG)
    _make_user("inactive-leg", is_active=False, version=POLICY_VERSION_LEGACY)

    assert active_legacy_count(db_session) == 2  # active legacy 만(비활성 제외)
    assert is_policy_enforced(db_session) is False
    counts = legacy_counts_by_role(db_session, active_only=True)
    assert counts.get("STAFF") == 1 and counts.get("MANAGER") == 1

    set_strong_password(a, _STRONG_PW); db_session.commit()
    assert active_legacy_count(db_session) == 1
    set_strong_password(b, _STRONG_PW); db_session.commit()
    assert active_legacy_count(db_session) == 0
    assert is_policy_enforced(db_session) is True  # active count 0 → ENFORCED


# --------------------------------------------------------------------------
# 라우트: 새/reset always strong, WARN 비차단, banner, admin filter, reactivate
# --------------------------------------------------------------------------
def test_add_user_rejects_weak_and_records_strong(client, app):
    admin = _make_user("admin1", role="ADMIN", version=POLICY_VERSION_STRONG)
    _login(client, admin)

    weak = client.post("/admin/users/add", data={
        "username": "newweak", "password": _WEAK_PW, "role": "STAFF"}, follow_redirects=True)
    assert weak.status_code == 200
    assert db_session.query(User).filter_by(username="newweak").first() is None

    client.post("/admin/users/add", data={
        "username": "newstrong", "password": _STRONG_PW, "role": "STAFF"}, follow_redirects=True)
    created = db_session.query(User).filter_by(username="newstrong").first()
    assert created is not None
    assert created.password_policy_version == POLICY_VERSION_STRONG


def test_profile_self_change_enforces_strong_and_records(client, app):
    user = _make_user("selfchg", role="STAFF", version=POLICY_VERSION_LEGACY,
                      raw_password="oldpass1")
    uid = user.id
    _login(client, user)
    # 약한 새 비번 거부
    client.post("/profile", data={"name": "n", "current_password": "oldpass1",
                                  "new_password": _WEAK_PW, "confirm_password": _WEAK_PW})
    assert db_session.get(User, uid).password_policy_version == POLICY_VERSION_LEGACY
    # 강한 새 비번 → STRONG 기록
    client.post("/profile", data={"name": "n", "current_password": "oldpass1",
                                  "new_password": _STRONG_PW, "confirm_password": _STRONG_PW})
    refreshed = db_session.get(User, uid)
    assert refreshed.password_policy_version == POLICY_VERSION_STRONG
    assert check_password_hash(refreshed.password, _STRONG_PW)


def test_admin_reset_decrements_legacy_count(client, app):
    admin = _make_user("admin2", role="ADMIN", version=POLICY_VERSION_STRONG)
    target = _make_user("legtarget", role="STAFF", version=POLICY_VERSION_LEGACY)
    target_id = target.id
    _login(client, admin)
    assert active_legacy_count(db_session) == 1

    client.post(f"/admin/users/edit/{target_id}", data={
        "name": "t", "role": "STAFF", "team": "", "is_active": "on",
        "new_password": _STRONG_PW}, follow_redirects=True)
    refreshed = db_session.get(User, target_id)
    assert refreshed.password_policy_version == POLICY_VERSION_STRONG
    assert active_legacy_count(db_session) == 0


def test_legacy_login_not_blocked_warn_only(client, app):
    """legacy 사용자 로그인은 차단되지 않는다(WARN — 가장 중요한 함정)."""
    _make_user("legin", role="STAFF", version=POLICY_VERSION_LEGACY, raw_password="legpass1")
    resp = client.post("/login", data={"username": "legin", "password": "legpass1"})
    assert resp.status_code == 302  # 성공 리다이렉트(재렌더 200 아님) → 비차단
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_no_password_change_nag_for_legacy(client, app):
    """legacy 사용자에게도 비밀번호 변경 배너/유도 문구를 노출하지 않는다(2026-08 제거).

    강도 정책 자체(새/변경 비번 strong 강제, weak rollback 불가)는 유지되며,
    사용자에게 변경을 요구하는 UI 표면만 제거되었다.
    """
    legacy = _make_user("banleg", role="STAFF", version=POLICY_VERSION_LEGACY)
    _login(client, legacy)
    html = client.get("/profile").get_data(as_text=True)
    assert "data-foms-legacy-password-banner" not in html
    assert "보안 강화를 위해 비밀번호를 변경해주세요" not in html


def test_admin_user_list_shows_legacy_badge_and_filter(client, app):
    admin = _make_user("admin3", role="ADMIN", version=POLICY_VERSION_STRONG)
    _make_user("listleg", role="STAFF", version=POLICY_VERSION_LEGACY)
    _make_user("liststrong", role="STAFF", version=POLICY_VERSION_STRONG)
    _login(client, admin)

    full = client.get("/admin/users").get_data(as_text=True)
    assert "data-legacy-badge" in full  # 최소 1명 legacy 배지

    filtered = client.get("/admin/users?policy=legacy").get_data(as_text=True)
    assert "listleg" in filtered
    assert "liststrong" not in filtered  # legacy 필터에는 strong 계정 미표시


def test_inactive_legacy_blind_reactivate_forbidden(client, app):
    """비활성 legacy 계정은 강도 재검사 없이 재활성화되지 않는다(blind reactivate 금지)."""
    admin = _make_user("admin4", role="ADMIN", version=POLICY_VERSION_STRONG)
    dormant = _make_user("dormant", role="STAFF", is_active=False,
                         version=POLICY_VERSION_LEGACY)
    dormant_id = dormant.id
    _login(client, admin)

    # 새 비번 없이 재활성 시도 → 차단(여전히 비활성·legacy)
    client.post(f"/admin/users/edit/{dormant_id}", data={
        "name": "d", "role": "STAFF", "team": "", "is_active": "on"},
        follow_redirects=True)
    refreshed = db_session.get(User, dormant_id)
    assert refreshed.is_active is False
    assert refreshed.password_policy_version == POLICY_VERSION_LEGACY

    # 강한 새 비번 동반 → 재활성 허용 + STRONG 기록
    client.post(f"/admin/users/edit/{dormant_id}", data={
        "name": "d", "role": "STAFF", "team": "", "is_active": "on",
        "new_password": _STRONG_PW}, follow_redirects=True)
    refreshed = db_session.get(User, dormant_id)
    assert refreshed.is_active is True
    assert refreshed.password_policy_version == POLICY_VERSION_STRONG


# --------------------------------------------------------------------------
# CLI: 비밀번호 유출 0
# --------------------------------------------------------------------------
def test_cli_audit_reports_no_password_or_hash(app, capsys):
    user = _make_user("cliaud", role="STAFF", version=POLICY_VERSION_LEGACY,
                      raw_password=_STRONG_PW)
    user_hash = user.password
    rc = run_audit(db_session)
    out = capsys.readouterr().out
    assert rc == 0
    assert "cliaud" in out          # 상태는 보고
    assert _STRONG_PW not in out    # 평문 미노출
    assert user_hash not in out     # hash 미노출


def test_cli_rotate_sets_strong_and_hides_password(app, capsys, monkeypatch):
    user = _make_user("clirot", role="STAFF", version=POLICY_VERSION_LEGACY)
    uid = user.id
    monkeypatch.setattr("getpass.getpass", lambda _prompt: _STRONG_PW)
    rc = run_rotate(db_session, "clirot")
    out = capsys.readouterr().out
    assert rc == 0
    refreshed = db_session.get(User, uid)
    assert refreshed.password_policy_version == POLICY_VERSION_STRONG
    assert check_password_hash(refreshed.password, _STRONG_PW)
    assert _STRONG_PW not in out  # 회전 성공 출력에 비밀번호 없음


def test_cli_rotate_rejects_weak(app, capsys, monkeypatch):
    user = _make_user("cliweak", role="STAFF", version=POLICY_VERSION_LEGACY)
    uid = user.id
    monkeypatch.setattr("getpass.getpass", lambda _prompt: _WEAK_PW)
    rc = run_rotate(db_session, "cliweak")
    out = capsys.readouterr().out
    assert rc == 2
    refreshed = db_session.get(User, uid)
    assert refreshed.password_policy_version == POLICY_VERSION_LEGACY
    assert _WEAK_PW not in out
