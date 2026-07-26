"""SHIPMENT-REFERENCE-01 계약 테스트 (PGTEST-00 lane + 순수 스키마/정책 단위).

출고 reference 설정 command(``UPDATE_SHIPMENT_REFERENCE_LISTS``)의 불변식을 검증한다:

* SHIPMENT/Admin 정책 200·그 외 403 (evaluate_policy — 순수).
* exact four-list schema: 임의 필드/``construction_workers``/타입/길이/개수 400, 중복 422.
* old drawing 필드(``drawing_manager``+``drawing_manager_en``) → 한 object array 무손실.
* SystemSetting version(If-Match): stale 409·누락 428·정상 version bump (실 PostgreSQL).
* collection receipt/idempotency replay + SecurityLog audit 를 한 transaction 에.
* construction worker master(CREW installation_workers)·per-order write 혼합 안 함.

정책/스키마/정규화 테스트는 DB 없이 항상 돈다. version/receipt/audit/보존 테스트는
``pg_session``(``FOMS_TEST_DATABASE_URL`` 없으면 conftest 가 skip). 커밋 파일에 PG 비번 0.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.shipment_reference import (
    SHIPMENT_REFERENCE_POLICY_ID,
    SHIPMENT_REFERENCE_SETTING_KEY,
    ShipmentReferenceConflictError,
    ShipmentReferenceDuplicateError,
    ShipmentReferenceIdempotencyConflictError,
    ShipmentReferencePreconditionError,
    ShipmentReferenceSchemaError,
    backfill_drawing_managers_from_legacy,
    project_to_legacy_shape,
    update_shipment_reference_lists,
    validate_reference_payload,
)
from models import InstallationWorker, Order, SecurityLog, SystemSetting, SystemSettingReceipt

_SEQ = [0]


def _user(role="STAFF", team=None, uid=1):
    return SimpleNamespace(role=role, team=team, id=uid, is_active=True)


def _suffix() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"


def _payload(**over):
    base = {
        "construction_time": ["10:00"],
        "drawing_managers": [{"name": "김한비", "english_name": "KIM HANBI"}],
        "measurement_managers": [{"name": "홍길동", "phone": "010-1", "sort_order": 1}],
        "site_extra": ["서울 추가주소"],
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# 1. SHIPMENT/Admin 정책 (순수 — DB 불요)
# --------------------------------------------------------------------------- #
def test_policy_allows_shipment_staff_and_admin_manager():
    policy = POLICY_REGISTRY[SHIPMENT_REFERENCE_POLICY_ID]
    assert evaluate_policy(policy, _user(role="STAFF", team="SHIPMENT")).allowed
    assert evaluate_policy(policy, _user(role="ADMIN")).allowed
    assert evaluate_policy(policy, _user(role="MANAGER")).allowed


def test_policy_denies_other_teams_and_viewer_and_anon():
    policy = POLICY_REGISTRY[SHIPMENT_REFERENCE_POLICY_ID]
    assert evaluate_policy(policy, _user(role="STAFF", team="SALES")).status == 403
    assert evaluate_policy(policy, _user(role="STAFF", team="CS")).status == 403
    assert evaluate_policy(policy, _user(role="VIEWER")).status == 403
    assert evaluate_policy(policy, None).status == 401


# --------------------------------------------------------------------------- #
# 2. exact four-list schema (순수)
# --------------------------------------------------------------------------- #
def test_schema_rejects_construction_workers_400():
    with pytest.raises(ShipmentReferenceSchemaError):
        validate_reference_payload(_payload(construction_workers=[{"name": "김시공"}]))


def test_schema_rejects_unknown_field_400():
    with pytest.raises(ShipmentReferenceSchemaError):
        validate_reference_payload(_payload(surprise=[1, 2, 3]))


def test_schema_rejects_over_length_and_over_count_400():
    with pytest.raises(ShipmentReferenceSchemaError):
        validate_reference_payload(_payload(construction_time=["x" * 51]))
    with pytest.raises(ShipmentReferenceSchemaError):
        validate_reference_payload(_payload(construction_time=[f"t{i}" for i in range(51)]))
    with pytest.raises(ShipmentReferenceSchemaError):
        validate_reference_payload(
            _payload(measurement_managers=[{"name": "x", "sort_order": 10000}])
        )


def test_schema_rejects_duplicates_422():
    with pytest.raises(ShipmentReferenceDuplicateError):
        validate_reference_payload(_payload(construction_time=["10:00", "10:00"]))
    with pytest.raises(ShipmentReferenceDuplicateError):
        validate_reference_payload(
            _payload(drawing_managers=[{"name": "김"}, {"name": "김"}])
        )


def test_schema_normalizes_and_trims():
    out = validate_reference_payload(
        _payload(
            construction_time=["  09:00  ", ""],
            measurement_managers=[{"name": " 홍 ", "phone": "", "sort_order": "3"}],
        )
    )
    assert out["construction_time"] == ["09:00"]
    assert out["measurement_managers"] == [{"name": "홍", "phone": "", "sort_order": 3}]


# --------------------------------------------------------------------------- #
# 3. old drawing 필드 safe normalize (순수, 무손실)
# --------------------------------------------------------------------------- #
def test_backfill_old_drawing_fields_lossless():
    managers = backfill_drawing_managers_from_legacy(
        ["김한비", "이도면"], {"김한비": "KIM HANBI", "박추가": "PARK"}
    )
    # 순서: drawing_manager 우선, en-only 이름은 유실 없이 뒤에 붙는다.
    names = [m["name"] for m in managers]
    assert names == ["김한비", "이도면", "박추가"]
    en = {m["name"]: m["english_name"] for m in managers if m["english_name"]}
    assert en == {"김한비": "KIM HANBI", "박추가": "PARK"}


def test_project_legacy_shape_from_both_representations():
    canonical = {"drawing_managers": [{"name": "김", "english_name": "KIM"}]}
    legacy = {"drawing_manager": ["김"], "drawing_manager_en": {"김": "KIM"}}
    for stored in (canonical, legacy):
        out = project_to_legacy_shape(stored)
        assert out["drawing_manager"] == ["김"]
        assert out["drawing_manager_en"] == {"김": "KIM"}


def test_project_preserves_construction_workers():
    out = project_to_legacy_shape({"construction_workers": [{"name": "김시공", "capacity": 3}]})
    assert out["construction_workers"] == [{"name": "김시공", "capacity": 3}]


# --------------------------------------------------------------------------- #
# 4. version(If-Match)·receipt·audit — 실 PostgreSQL (pg_session)
# --------------------------------------------------------------------------- #
def _seed_actor(session):
    from models import User

    user = User(username=f"shipref_{_suffix()}", password="pw-not-committed",
                name="설정담당", role="STAFF", team="SHIPMENT", is_active=True)
    session.add(user)
    session.flush()
    return user


def test_pg_create_then_bump_version_with_receipt_and_audit(pg_session):
    actor = _seed_actor(pg_session)
    # 최초: 저장 row 없음 → current version 0, If-Match 0 으로 생성 → version 1.
    r1 = update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id, payload=_payload(), if_match_version=0,
    )
    assert r1.version == 1 and r1.replayed is False
    setting = pg_session.query(SystemSetting).filter_by(
        setting_key=SHIPMENT_REFERENCE_SETTING_KEY).one()
    assert setting.version == 1
    assert setting.setting_value["drawing_managers"] == [
        {"name": "김한비", "english_name": "KIM HANBI"}]

    # receipt + audit 한 transaction 에.
    assert pg_session.query(SystemSettingReceipt).filter_by(
        resulting_version=1).count() == 1
    assert pg_session.query(SecurityLog).filter(
        SecurityLog.message.like("SHIPMENT_REFERENCE_UPDATE%")).count() == 1

    # 다음 저장: If-Match 1 → version 2.
    r2 = update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id,
        payload=_payload(construction_time=["11:00"]), if_match_version=1,
    )
    assert r2.version == 2
    pg_session.refresh(setting)
    assert setting.version == 2 and setting.setting_value["construction_time"] == ["11:00"]


def test_pg_stale_if_match_conflict_409_no_write(pg_session):
    actor = _seed_actor(pg_session)
    update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id, payload=_payload(), if_match_version=0)
    with pytest.raises(ShipmentReferenceConflictError) as ei:
        update_shipment_reference_lists(
            pg_session, actor_user_id=actor.id,
            payload=_payload(construction_time=["99:99"]), if_match_version=0)  # stale
    assert ei.value.status_code == 409 and ei.value.current_version == 1
    setting = pg_session.query(SystemSetting).filter_by(
        setting_key=SHIPMENT_REFERENCE_SETTING_KEY).one()
    assert setting.version == 1  # 미변경


def test_pg_missing_if_match_428(pg_session):
    actor = _seed_actor(pg_session)
    with pytest.raises(ShipmentReferencePreconditionError) as ei:
        update_shipment_reference_lists(
            pg_session, actor_user_id=actor.id, payload=_payload(), if_match_version=None)
    assert ei.value.status_code == 428


def test_pg_idempotency_replay_single_write(pg_session):
    actor = _seed_actor(pg_session)
    key = f"idem-{_suffix()}"
    r1 = update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id, payload=_payload(),
        if_match_version=0, idempotency_key=key)
    # 같은 key + 같은 payload 재요청 → replay(두 번째 version bump·receipt 없음).
    r2 = update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id, payload=_payload(),
        if_match_version=0, idempotency_key=key)
    assert r2.replayed is True and r2.version == r1.version == 1
    assert pg_session.query(SystemSettingReceipt).filter_by(idempotency_key=key).count() == 1
    # 같은 key + 다른 payload → 409 conflict(replay 아님).
    with pytest.raises(ShipmentReferenceIdempotencyConflictError):
        update_shipment_reference_lists(
            pg_session, actor_user_id=actor.id,
            payload=_payload(construction_time=["12:00"]),
            if_match_version=0, idempotency_key=key)


# --------------------------------------------------------------------------- #
# 5. 경계: worker master·per-order write 혼합 안 함 (pg_session)
# --------------------------------------------------------------------------- #
def test_pg_preserves_construction_workers_and_touches_nothing_else(pg_session):
    actor = _seed_actor(pg_session)
    # 기존 저장에 construction_workers(용량/휴무 참조)와 legacy drawing 필드 존재.
    pg_session.add(SystemSetting(
        setting_key=SHIPMENT_REFERENCE_SETTING_KEY, version=5,
        setting_value={
            "construction_workers": [{"name": "김시공", "capacity": 3, "off_dates": []}],
            "drawing_manager": ["이도면"], "drawing_manager_en": {"이도면": "LEE"},
        },
    ))
    pg_session.flush()
    workers_before = pg_session.query(InstallationWorker).count()
    orders_before = pg_session.query(Order).count()

    update_shipment_reference_lists(
        pg_session, actor_user_id=actor.id, payload=_payload(), if_match_version=5)

    setting = pg_session.query(SystemSetting).filter_by(
        setting_key=SHIPMENT_REFERENCE_SETTING_KEY).one()
    # construction_workers 보존, drawing 은 canonical 로 대체(legacy 키 제거).
    assert setting.setting_value["construction_workers"] == [
        {"name": "김시공", "capacity": 3, "off_dates": []}]
    assert "drawing_manager" not in setting.setting_value
    assert setting.setting_value["drawing_managers"] == [
        {"name": "김한비", "english_name": "KIM HANBI"}]
    # CREW installation_workers·주문(per-order shipment) 무변경(혼합 금지).
    assert pg_session.query(InstallationWorker).count() == workers_before
    assert pg_session.query(Order).count() == orders_before
