"""KST datetime 표시 SSOT(format_datetime_kst) 계약 테스트."""
from datetime import date, datetime
from pathlib import Path

from flask import Flask
import pytz

from db import db_session
from foms.services.context_processors import register_context_processors
from foms.services.datetime_kst import format_datetime_kst, get_today_kst, to_utc_naive
from foms.services import erp_display
from models import ChatRoom, Notification, OrderAttachment, OrderEstimate, User
from wdcalculator_models import Estimate

ROOT = Path(__file__).resolve().parents[2]


def test_format_datetime_kst_converts_utc_naive_to_kst() -> None:
    """Railway naive UTC(04:57) → KST(13:57) 변환."""
    assert format_datetime_kst(datetime(2026, 6, 9, 4, 57, 29)) == "2026-06-09 13:57:29"


def test_format_datetime_kst_accepts_custom_display_format() -> None:
    """관리자 목록처럼 분 단위 표시도 같은 KST SSOT를 사용한다."""
    assert (
        format_datetime_kst(datetime(2026, 6, 16, 7, 30, 4), "%Y-%m-%d %H:%M")
        == "2026-06-16 16:30"
    )


def test_format_datetime_kst_converts_aware_utc_to_kst() -> None:
    aware = pytz.UTC.localize(datetime(2026, 6, 9, 4, 57, 29))
    assert format_datetime_kst(aware) == "2026-06-09 13:57:29"


def test_format_datetime_kst_parses_utc_iso_string_to_kst() -> None:
    assert format_datetime_kst("2026-06-09T04:57:29Z") == "2026-06-09 13:57:29"


def test_to_utc_naive_normalizes_aware_stage_timestamp() -> None:
    value = to_utc_naive("2026-06-09T04:57:29+09:00")
    assert value == datetime(2026, 6, 8, 19, 57, 29)


def test_format_datetime_kst_none_returns_none() -> None:
    assert format_datetime_kst(None) is None


def test_get_today_kst_uses_kst_not_utc_server_date(monkeypatch) -> None:
    """KST 06-17 07:56 고정 시 get_today_kst()는 17일을 반환 (UTC 서버 date.today()와 분리)."""
    kst = pytz.timezone("Asia/Seoul")
    fixed = kst.localize(datetime(2026, 6, 17, 7, 56, 0))

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return fixed.astimezone(tz)
            return fixed.replace(tzinfo=None)

    monkeypatch.setattr("foms.services.datetime_kst.datetime.datetime", _FixedDatetime)
    assert get_today_kst() == date(2026, 6, 17)


def test_format_datetime_kst_registered_as_global_jinja_filter() -> None:
    app = Flask(__name__)

    register_context_processors(app)

    assert "format_datetime_kst" in app.jinja_env.filters
    assert (
        app.jinja_env.filters["format_datetime_kst"](
            datetime(2026, 6, 16, 7, 30, 4),
            "%Y-%m-%d %H:%M",
        )
        == "2026-06-16 16:30"
    )


def test_admin_user_list_uses_kst_filter_for_recent_login() -> None:
    template = (ROOT / "templates/auth/user_list.html").read_text(encoding="utf-8")

    assert "last_login|format_datetime_kst('%Y-%m-%d %H:%M')" in template
    assert "user.created_at|format_datetime_kst('%Y-%m-%d')" in template
    assert "user.last_login.strftime" not in template
    assert "user.created_at.strftime" not in template


def test_admin_user_list_renders_recent_login_in_kst(client) -> None:
    admin = User(
        username="kst_admin",
        password="unused",
        role="ADMIN",
        name="관리자",
        is_active=True,
    )
    user = User(
        username="kst_recent_login",
        password="unused",
        role="STAFF",
        name="최근로그인",
        is_active=True,
        created_at=datetime(2026, 6, 16, 0, 0, 0),
        last_login=datetime(2026, 6, 16, 7, 30, 4),
    )
    db_session.add_all([admin, user])
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    response = client.get("/admin/users")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "2026-06-16 16:30" in html
    assert "2026-06-16 07:30" not in html


def test_admin_user_list_sorts_users_by_team_order(client) -> None:
    admin = User(
        username="sort_admin",
        password="unused",
        role="ADMIN",
        team="SHIPMENT",
        name="정렬관리자",
        is_active=True,
    )
    users = [
        User(username="sort_z_con", password="unused", role="STAFF", team="CONSTRUCTION", name="시공나중", is_active=True),
        User(username="sort_a_sales", password="unused", role="STAFF", team="SALES", name="영업먼저", is_active=True),
        User(username="sort_b_drawing", password="unused", role="STAFF", team="DRAWING", name="도면중간", is_active=True),
        User(username="sort_c_none", password="unused", role="STAFF", team=None, name="팀없음", is_active=True),
    ]
    db_session.add_all([admin, *users])
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    response = client.get("/admin/users")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.index(">sort_a_sales<") < html.index(">sort_b_drawing<")
    assert html.index(">sort_b_drawing<") < html.index(">sort_z_con<")
    assert html.index(">sort_z_con<") < html.index(">sort_admin<")
    assert html.index(">sort_admin<") < html.index(">sort_c_none<")


def test_wdcalculator_estimate_to_dict_uses_kst_created_at() -> None:
    """WDCalculator Estimate API 직렬화가 KST 생성일을 반환한다."""
    estimate = Estimate(
        customer_name="이철기",
        estimate_data={"totalPrice": 1000},
    )
    estimate.id = 700
    estimate.created_at = datetime(2026, 6, 9, 4, 57, 29)
    estimate.updated_at = datetime(2026, 6, 9, 4, 57, 29)

    payload = estimate.to_dict()

    assert payload["created_at"] == "2026-06-09 13:57:29"
    assert payload["updated_at"] == "2026-06-09 13:57:29"


def test_order_estimate_to_dict_uses_kst_timestamps() -> None:
    """ERP OrderEstimate API 직렬화가 KST 생성·수정 시각을 반환한다."""
    estimate = OrderEstimate(
        order_id=1,
        estimate_number="20260609_1",
        customer_name="이철기",
        estimate_date="2026-06-09",
        items=[],
        total_amount=0,
    )
    estimate.created_at = datetime(2026, 6, 9, 4, 57, 29)
    estimate.updated_at = datetime(2026, 6, 9, 4, 57, 29)

    payload = estimate.to_dict()

    assert payload["created_at"] == "2026-06-09 13:57:29"
    assert payload["updated_at"] == "2026-06-09 13:57:29"


def test_core_display_serializers_use_kst_timestamps() -> None:
    attachment = OrderAttachment(
        order_id=1,
        filename="site.jpg",
        file_type="image",
        category="measurement",
        file_size=1,
        storage_key="orders/1/site.jpg",
    )
    attachment.created_at = datetime(2026, 6, 9, 4, 57, 29)
    assert attachment.to_dict()["created_at"] == "2026-06-09 13:57:29"

    notification = Notification(
        notification_type="ANNOUNCEMENT",
        title="공지",
        created_at=datetime(2026, 6, 9, 4, 57, 29),
    )
    assert notification.to_dict()["created_at"] == "2026-06-09 13:57:29"

    room = ChatRoom(
        name="채팅방",
        created_by=1,
        created_at=datetime(2026, 6, 9, 4, 57, 29),
        updated_at=datetime(2026, 6, 9, 5, 0, 0),
    )
    payload = room.to_dict()
    assert payload["created_at"] == "2026-06-09 13:57:29"
    assert payload["updated_at"] == "2026-06-09 14:00:00"


def test_erp_alerts_handles_aware_stage_timestamp_for_drawing_overdue(monkeypatch) -> None:
    monkeypatch.setattr(
        erp_display,
        "now_utc_naive",
        lambda: datetime(2026, 6, 30, 0, 0, 0),
    )

    overdue = erp_display._erp_alerts(
        None,
        {"workflow": {"stage": "DRAWING", "stage_updated_at": "2026-06-27T23:00:00Z"}},
        0,
    )
    recent = erp_display._erp_alerts(
        None,
        {"workflow": {"stage": "DRAWING", "stage_updated_at": "2026-06-29T23:00:00Z"}},
        0,
    )

    assert overdue["drawing_overdue"] is True
    assert recent["drawing_overdue"] is False


def test_frontend_business_date_paths_avoid_utc_iso_fallbacks() -> None:
    paths = [
        ROOT / "static/js/cs/as-dashboard.js",
        ROOT / "static/js/shipment/image-export.js",
        ROOT / "static/js/measurement/image-export.js",
        ROOT / "templates/measurement/map_view.html",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert ".toISOString().split('T')[0]" not in source
        assert ".toISOString().slice(0, 10)" not in source
        assert "localDateIso()" in source


def test_order_date_only_display_does_not_construct_utc_date() -> None:
    for relative in ("templates/orders/add_order.html", "templates/orders/edit_order.html"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "new Date(dateString)" not in source
        assert "String(dateString).split('-').map(Number)" in source


def test_chat_datetime_scripts_parse_kst_strings_explicitly() -> None:
    utils = (ROOT / "templates/partials/chat_scripts_utils.html").read_text(encoding="utf-8")
    notifications = (ROOT / "templates/partials/chat_scripts_notifications.html").read_text(encoding="utf-8")

    assert "function parseKstDateTime" in utils
    assert "Date.UTC(year, month, day, hour - 9" in utils
    assert "timeZone: 'Asia/Seoul'" in utils
    assert "new Date(dateString)" not in utils
    assert "parseKstDateTime(dateString)" in notifications
    assert "timeZone: 'Asia/Seoul'" in notifications
