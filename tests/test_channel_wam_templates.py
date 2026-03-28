from pathlib import Path

from flask import Flask, render_template


ROOT = Path(__file__).resolve().parents[1]


def build_test_app():
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["TESTING"] = True
    return app


def test_channel_wam_index_wrapper_renders_v1_fallback_shell():
    app = build_test_app()
    summary = {
        "order_id": 1234,
        "status_kr": "실측 예정",
        "customer_name": "홍길동",
        "phone": "010-1234-5678",
        "address": "서울시 강남구 테스트로 123",
        "product": "맞춤장 세트",
        "manager_name": "담당 매니저",
        "measurement_date": "2026-04-01",
        "construction_date": "2026-04-08",
    }
    attachments = [
        {
            "name": "도면.pdf",
            "category": "도면",
            "url": "https://example.com/a.pdf",
        }
    ]

    with app.test_request_context("/channel/wam/?launch_token=test"):
        html = render_template(
            "channel_wam_index.html",
            summary=summary,
            attachments=attachments,
            token="test",
        )

    assert "css/wam/tokens.css" in html
    assert "wam-header__surface" in html
    assert "wam-summary-strip" in html
    assert "Rollback V1" in html
    assert "주문 #1234" in html


def test_channel_wam_error_wrapper_renders_error_state():
    app = build_test_app()

    with app.test_request_context("/channel/wam/?launch_token=bad"):
        html = render_template(
            "channel_wam_error.html",
            message="만료되거나 유효하지 않은 토큰입니다.",
        )

    assert "wam-error-state" in html
    assert "접근할 수 없습니다" in html
    assert "만료되거나 유효하지 않은 토큰입니다." in html
