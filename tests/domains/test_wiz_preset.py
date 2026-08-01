"""WIZ-PRESET-01 계약 테스트 — 도면 마법사 전역 preset 저장 command.

전역 도면 마법사 preset 저장(``update_wizard_presets`` / POST ``/drawing-wizard/presets``)의
불변식을 검증한다:

* DRAWING/Admin 정책만 저장(그 외 403·VIEWER 403·미인증 401) — evaluate_policy(순수).
* 명시 schema: ``label``/``text`` 외 임의 필드·비-딕트 항목·비-리스트 payload 거부(400).
* SystemSetting version(If-Match): 최초 생성 → bump, stale 409(silent overwrite 차단),
  누락 428, receipt/idempotency replay(중복 write 0), SecurityLog audit 를 한 tx 에.
* Order 불변: preset 저장은 전역 SystemSetting collection 이라 Order(mutation_version·
  OrderMutationReceipt)를 건드리지 않는다.

정책/스키마 테스트는 DB 없이 항상 돈다. version/idempotency/audit/Order-불변 테스트는
앱 인메모리 DB(``app`` 픽스처, ``tests/conftest.py``)를 쓴다. 커밋 파일에 비밀 0.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.drawing_wizard_presets import (
    DRAWING_WIZARD_PRESETS_KEY,
    WIZ_PRESET_POLICY_ID,
    PresetUpdateResult,
    WizardPresetConflictError,
    WizardPresetIdempotencyConflictError,
    WizardPresetPreconditionError,
    WizardPresetSchemaError,
    update_wizard_presets,
    validate_wizard_presets,
)
from models import (
    Order,
    OrderMutationReceipt,
    SecurityLog,
    SystemSetting,
    SystemSettingReceipt,
    User,
)

_SEQ = [0]


def _user(role="STAFF", team=None, uid=1):
    return SimpleNamespace(role=role, team=team, id=uid, is_active=True)


def _suffix() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


# --------------------------------------------------------------------------- #
# 1. DRAWING/Admin 정책 (순수 — DB 불요)
# --------------------------------------------------------------------------- #
def test_policy_allows_drawing_staff_and_admin_manager():
    policy = POLICY_REGISTRY[WIZ_PRESET_POLICY_ID]
    assert evaluate_policy(policy, _user(role="STAFF", team="DRAWING")).allowed
    assert evaluate_policy(policy, _user(role="ADMIN")).allowed
    assert evaluate_policy(policy, _user(role="MANAGER")).allowed


def test_policy_denies_other_teams_and_viewer_and_anon():
    policy = POLICY_REGISTRY[WIZ_PRESET_POLICY_ID]
    # CS/SALES 는 구 _can_manage_presets 가 허용했으나 이제 거부(WIZ-PRESET-01 조임).
    assert evaluate_policy(policy, _user(role="STAFF", team="CS")).status == 403
    assert evaluate_policy(policy, _user(role="STAFF", team="SALES")).status == 403
    assert evaluate_policy(policy, _user(role="STAFF", team="PRODUCTION")).status == 403
    assert evaluate_policy(policy, _user(role="VIEWER")).status == 403
    assert evaluate_policy(policy, None).status == 401


# --------------------------------------------------------------------------- #
# 2. 명시 schema (순수 — 임의 필드 거부)
# --------------------------------------------------------------------------- #
def test_schema_rejects_arbitrary_field_400():
    with pytest.raises(WizardPresetSchemaError):
        validate_wizard_presets([{"label": "x", "text": "y", "injected": 1}])


def test_schema_rejects_non_list_and_non_dict_item_400():
    with pytest.raises(WizardPresetSchemaError):
        validate_wizard_presets("nope")
    with pytest.raises(WizardPresetSchemaError):
        validate_wizard_presets([{"label": "x", "text": "y"}, "not-a-dict"])


def test_schema_accepts_valid_and_sanitizes_values():
    # 유효 키(label/text)는 통과하되 값 정규화(trim·빈 본문/길이초과 제거)는 sanitize 위임.
    out = validate_wizard_presets([
        {"label": "  라벨  ", "text": "  본문  "},
        {"label": "빈본문", "text": "   "},          # 본문 없음 → drop(400 아님)
        {"text": "라벨없음본문"},                      # label 없음 → 첫 줄로 자동 라벨
    ])
    assert out == [
        {"label": "라벨", "text": "본문"},
        {"label": "라벨없음본문", "text": "라벨없음본문"},
    ]


# --------------------------------------------------------------------------- #
# 3. version(If-Match)·receipt·audit — 앱 인메모리 DB (app 픽스처)
# --------------------------------------------------------------------------- #
def _seed_actor(team="DRAWING"):
    user = User(username=f"wizpreset_{_suffix()}", password="pw-not-committed",
                name="프리셋담당", role="STAFF", team=team, is_active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _presets(*labels):
    return [{"label": lab, "text": f"[SR] {lab}"} for lab in labels]


def test_pg_create_then_bump_version_with_receipt_and_audit(app):
    actor = _seed_actor()
    # 최초: 저장 row 없음 → current version 0, If-Match 0 으로 생성 → version 1.
    r1 = update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("컷1"), if_match_version=0)
    db_session.commit()
    assert isinstance(r1, PresetUpdateResult)
    assert r1.version == 1 and r1.replayed is False
    assert r1.presets == _presets("컷1")

    setting = db_session.query(SystemSetting).filter_by(
        setting_key=DRAWING_WIZARD_PRESETS_KEY).one()
    assert setting.version == 1 and setting.setting_value == _presets("컷1")

    # receipt + audit 한 transaction 에.
    assert db_session.query(SystemSettingReceipt).filter_by(resulting_version=1).count() == 1
    assert db_session.query(SecurityLog).filter(
        SecurityLog.message.like("DRAWING_WIZARD_PRESET_UPDATE%")).count() == 1

    # 다음 저장: If-Match 1 → version 2.
    r2 = update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("컷1", "컷2"), if_match_version=1)
    db_session.commit()
    assert r2.version == 2
    db_session.refresh(setting)
    assert setting.version == 2 and setting.setting_value == _presets("컷1", "컷2")


def test_pg_stale_if_match_conflict_409_no_silent_overwrite(app):
    actor = _seed_actor()
    update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("원본"), if_match_version=0)
    db_session.commit()
    # stale version(0)으로 재저장 시도 → 409, 조용한 전역 덮어쓰기 0.
    with pytest.raises(WizardPresetConflictError) as ei:
        update_wizard_presets(
            db_session, actor_user_id=actor.id, payload=_presets("덮어쓰기"), if_match_version=0)
    assert ei.value.status_code == 409 and ei.value.current_version == 1
    db_session.rollback()
    setting = db_session.query(SystemSetting).filter_by(
        setting_key=DRAWING_WIZARD_PRESETS_KEY).one()
    assert setting.version == 1 and setting.setting_value == _presets("원본")  # 미변경


def test_pg_missing_if_match_428(app):
    actor = _seed_actor()
    with pytest.raises(WizardPresetPreconditionError) as ei:
        update_wizard_presets(
            db_session, actor_user_id=actor.id, payload=_presets("컷"), if_match_version=None)
    assert ei.value.status_code == 428
    db_session.rollback()
    # 저장 0(전역 덮어쓰기 없음).
    assert db_session.query(SystemSetting).filter_by(
        setting_key=DRAWING_WIZARD_PRESETS_KEY).count() == 0


def test_pg_idempotency_replay_single_write(app):
    actor = _seed_actor()
    key = f"idem-{_suffix()}"
    r1 = update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("컷"),
        if_match_version=0, idempotency_key=key)
    db_session.commit()
    # 같은 key + 같은 payload 재요청 → replay(두 번째 write·version bump 없음).
    r2 = update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("컷"),
        if_match_version=0, idempotency_key=key)
    db_session.commit()
    assert r2.replayed is True and r2.version == r1.version == 1
    assert r2.presets == _presets("컷")
    assert db_session.query(SystemSettingReceipt).filter_by(idempotency_key=key).count() == 1

    # 같은 key + 다른 payload → 409(replay 아님).
    with pytest.raises(WizardPresetIdempotencyConflictError):
        update_wizard_presets(
            db_session, actor_user_id=actor.id, payload=_presets("다른컷"),
            if_match_version=0, idempotency_key=key)
    db_session.rollback()


# --------------------------------------------------------------------------- #
# 4. Order 불변: preset 저장은 Order 를 건드리지 않는다 (app 픽스처)
# --------------------------------------------------------------------------- #
def test_pg_preset_save_does_not_touch_order(app):
    actor = _seed_actor()
    order = Order(
        received_date="2026-07-24", customer_name="테스트고객", phone="010-0000-0000",
        address="서울시 어딘가", product="붙박이장",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id
    version_before = order.mutation_version
    orders_before = db_session.query(Order).count()
    receipts_before = db_session.query(OrderMutationReceipt).count()

    update_wizard_presets(
        db_session, actor_user_id=actor.id, payload=_presets("컷"), if_match_version=0)
    db_session.commit()

    reloaded = db_session.query(Order).filter_by(id=order_id).one()
    # Order mutation_version·event(OrderMutationReceipt)·row 수 모두 불변.
    assert reloaded.mutation_version == version_before
    assert db_session.query(Order).count() == orders_before
    assert db_session.query(OrderMutationReceipt).count() == receipts_before
