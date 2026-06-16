"""KST datetime 표시 SSOT(format_datetime_kst) 계약 테스트."""
from datetime import datetime
from pathlib import Path

from flask import Flask
import pytz

from db import db_session
from foms.services.context_processors import register_context_processors
from foms.services.datetime_kst import format_datetime_kst
from models import OrderEstimate, User
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


def test_format_datetime_kst_none_returns_none() -> None:
    assert format_datetime_kst(None) is None


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
    assert "user.last_login.strftime" not in template


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
