from types import SimpleNamespace

from foms.services.erp_shipment_settings import (
    DEFAULT_ERP_WORKER_CAPACITY,
    is_order_assigned_to_user_for_construction,
    is_order_mine_for_user,
    normalize_erp_shipment_workers,
    normalize_measurement_managers,
)


def _make_order(*, structured_data=None, manager_name=""):
    return SimpleNamespace(
        structured_data=structured_data if structured_data is not None else {},
        manager_name=manager_name,
    )


def _make_user(*, name="", username=""):
    return SimpleNamespace(name=name, username=username)


def test_normalize_measurement_managers_normalizes_names_and_sort_orders() -> None:
    result = normalize_measurement_managers(
        [
            "  홍길동  ",
            {"name": "김영희", "sort_order": "2"},
            {"name": "이철수", "sort_order": "bad"},
            {"name": "   ", "sort_order": 1},
        ]
    )

    assert result == [
        {"name": "홍길동", "sort_order": 999, "phone": ""},
        {"name": "김영희", "sort_order": 2, "phone": ""},
        {"name": "이철수", "sort_order": 999, "phone": ""},
    ]


def test_normalize_measurement_managers_preserves_phone() -> None:
    result = normalize_measurement_managers(
        [
            {"name": "한용희", "sort_order": 1, "phone": "010-1111-2222"},
            "문자열만",
        ]
    )
    assert result == [
        {"name": "한용희", "sort_order": 1, "phone": "010-1111-2222"},
        {"name": "문자열만", "sort_order": 999, "phone": ""},
    ]


def test_normalize_erp_shipment_workers_normalizes_capacity_and_off_dates() -> None:
    result = normalize_erp_shipment_workers(
        [
            {
                "name": "  김시공  ",
                "capacity": "3",
                "off_dates": ["2026-04-01", "2026-04-01", "  "],
            },
            {
                "text": "이출고",
                "daily_capacity": "bad",
                "offDays": ["2026-04-02", "2026-04-02"],
            },
            " 박지원 ",
        ]
    )

    assert result == [
        {
            "name": "김시공",
            "capacity": 3,
            "off_dates": ["2026-04-01"],
        },
        {
            "name": "이출고",
            "capacity": DEFAULT_ERP_WORKER_CAPACITY,
            "off_dates": ["2026-04-02"],
        },
        {
            "name": "박지원",
            "capacity": DEFAULT_ERP_WORKER_CAPACITY,
            "off_dates": [],
        },
    ]


def test_is_order_assigned_to_user_for_construction_matches_case_insensitively() -> None:
    order = _make_order(
        structured_data={
            "shipment": {
                "construction_workers": [
                    "김시공",
                    {"name": "이출고"},
                ]
            }
        }
    )

    assert is_order_assigned_to_user_for_construction(order, " 김시공 ")
    assert is_order_assigned_to_user_for_construction(order, "이출고")
    assert not is_order_assigned_to_user_for_construction(order, "박지원")


def test_is_order_mine_for_user_supports_manager_fields_and_username_fallback() -> None:
    order = _make_order(
        structured_data={
            "parties": {
                "manager": {
                    "name": "담당매니저",
                }
            },
            "workflow": {
                "current_quest": {
                    "owner_person": "quest-owner",
                }
            },
        },
        manager_name="컬럼담당자",
    )

    assert is_order_mine_for_user(order, _make_user(name="담당매니저"))
    assert is_order_mine_for_user(order, _make_user(username="quest-owner"))
    assert is_order_mine_for_user(order, _make_user(username="컬럼담당자"))
    assert not is_order_mine_for_user(order, _make_user(name="다른사람"))


# --- 요청당 캐시(원장 P3-8) ------------------------------------------------------
#
# 출고 설정은 한 요청 안에서 1~3번 읽혔다. 이제 같은 요청 안에서는 DB 를 한 번만 읽는다.
# 지키는 것: 같은 요청 두 번째 호출은 SELECT 0(양성) · 요청이 다르거나 요청 밖이면 다시
# 읽는다(음성) · 같은 요청에서 고치면 새 값(저장·대입·flush·롤백) · 받은 dict 를 고쳐도
# 다음 호출 값은 그대로.

import contextlib  # noqa: E402

from sqlalchemy import event  # noqa: E402

from db import db_session, engine  # noqa: E402
from foms.services.erp_shipment_settings import (  # noqa: E402
    ERP_SHIPMENT_SETTINGS_KEY,
    load_erp_shipment_settings,
    save_erp_shipment_settings,
)
from models import SystemSetting  # noqa: E402


@contextlib.contextmanager
def _count_settings_selects():
    seen: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if "system_settings" in statement and statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _seed_settings(managers: list[str]) -> None:
    db_session.add(SystemSetting(
        setting_key=ERP_SHIPMENT_SETTINGS_KEY,
        setting_value={"measurement_manager": [{"name": n} for n in managers]},
    ))
    db_session.commit()


def _manager_names(settings: dict) -> list[str]:
    return [m["name"] for m in settings["measurement_manager"]]


def test_second_load_in_same_request_does_not_query(app) -> None:
    _seed_settings(["가"])
    with app.test_request_context("/"), _count_settings_selects() as seen:
        first = load_erp_shipment_settings()
        second = load_erp_shipment_settings()
        third = load_erp_shipment_settings()
    assert len(seen) == 1, seen
    assert first == second == third
    assert _manager_names(first) == ["가"]


def test_each_request_and_non_request_context_reads_again(app) -> None:
    """음성 대조군: 요청이 다르면 다시 읽고, 요청 밖(워커 등)에서는 기억하지 않는다."""
    _seed_settings(["가"])
    with _count_settings_selects() as seen:
        with app.test_request_context("/"):
            load_erp_shipment_settings()
        with app.test_request_context("/"):
            load_erp_shipment_settings()
        with app.app_context():
            load_erp_shipment_settings()
            load_erp_shipment_settings()
    assert len(seen) == 4, seen


def test_save_in_same_request_is_seen_by_next_load(app) -> None:
    _seed_settings(["가"])
    with app.test_request_context("/"):
        assert _manager_names(load_erp_shipment_settings()) == ["가"]
        assert save_erp_shipment_settings({"measurement_manager": [{"name": "나"}]})
        assert _manager_names(load_erp_shipment_settings()) == ["나"]


def test_unflushed_assignment_and_rollback_drop_the_cache(app) -> None:
    """저장 함수를 거치지 않은 ORM 대입(_write_canonical 방식)도 기억을 지우고, 롤백하면
    DB 의 옛 값으로 돌아간다 — 기억이 롤백된 값을 붙들지 않는다."""
    _seed_settings(["가"])
    with app.test_request_context("/"):
        load_erp_shipment_settings()
        row = db_session.query(SystemSetting).filter_by(setting_key=ERP_SHIPMENT_SETTINGS_KEY).one()
        row.setting_value = {"measurement_manager": [{"name": "다"}]}
        assert _manager_names(load_erp_shipment_settings()) == ["다"]
        db_session.rollback()
        assert _manager_names(load_erp_shipment_settings()) == ["가"]


def test_other_setting_rows_do_not_drop_the_cache(app) -> None:
    """음성 대조군: 다른 설정 키를 고쳐도 출고 설정 기억은 그대로다(다시 읽지 않는다)."""
    _seed_settings(["가"])
    with app.test_request_context("/"), _count_settings_selects() as seen:
        load_erp_shipment_settings()
        db_session.add(SystemSetting(setting_key="p38_other_key", setting_value={"x": 1}))
        db_session.flush()
        load_erp_shipment_settings()
    assert len(seen) == 1, seen


def test_caller_mutation_does_not_leak_into_next_load(app) -> None:
    """두 번째 호출도 새로 투영한 dict 를 받는다 — 앞 호출부가 받은 dict 의 키를 바꾸거나
    정규화된 목록에 덧붙여도 다음 호출 값은 그대로다(투영은 예전처럼 호출마다 한다)."""
    _seed_settings(["가"])
    with app.test_request_context("/"):
        first = load_erp_shipment_settings()
        first["measurement_manager"].append({"name": "침입"})
        first["construction_time"] = ["바뀜"]
        second = load_erp_shipment_settings()
    assert _manager_names(second) == ["가"]
    assert second["construction_time"] == []
