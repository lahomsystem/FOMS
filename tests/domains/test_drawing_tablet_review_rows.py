"""E2 단계 2 — 도면 작업실 rows 뷰어 3필드 + resolve_row_image_list 계약 (2026-07-27).

스펙: docs/specs/2026-07-27-drawing-tablet-review-station-design.md §E2.

잠그는 것:
  1. ``resolve_row_image_list`` 가 이미지 파일 전체를 GlobalImageViewer 형식으로 반환하고,
     행당 ``OrderAttachment`` 조회가 최대 1회(파일마다 재조회 금지)라는 성능 불변식.
  2. workbench 대시보드 rows 가 ``drawing_files`` / ``can_confirm_receipt_perm`` /
     ``can_request_revision`` 3필드를 싣고, 권한 공식에 ``not is_drawing_team`` 이 있다는 것
     (누락 시 상세에선 숨는 판정 버튼이 태블릿에서만 노출된다).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.drawing_workbench_display import (
    pick_row_thumbnail_url,
    resolve_row_image_list,
)
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = "foms/web/drawing/workbench.py"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- resolve_row_image_list 단위 계약 ----------------------------------------


def test_image_list_returns_all_images_without_db_query(monkeypatch) -> None:
    """sd 에 view_url 이 전부 있으면 조회 0회 — 파일 수와 무관(N+1 재발 방지)."""
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    db = MagicMock()
    files = [
        {
            "key": "drawings/a.png",
            "filename": "a.png",
            "view_url": "/api/files/view/drawings/a.png",
            "download_url": "/api/files/download/drawings/a.png",
        },
        {
            "key": "drawings/b.jpg",
            "filename": "b.jpg",
            "view_url": "/api/files/view/drawings/b.jpg",
            "download_url": "/api/files/download/drawings/b.jpg",
        },
    ]

    result = resolve_row_image_list(7, files, db, mobile_v2_active=True)

    assert [item["key"] for item in result] == ["drawings/a.png", "drawings/b.jpg"]
    assert result[0]["view_url"] == "/api/files/view/drawings/a.png"
    assert result[0]["download_url"] == "/api/files/download/drawings/a.png"
    assert result[0]["filename"] == "a.png"
    db.query.assert_not_called()


def test_image_list_filters_non_image_entries(monkeypatch) -> None:
    """_is_image_file 필터 — PDF 등 비이미지 전달본은 뷰어 대상에서 제외."""
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    db = MagicMock()
    files = [
        {"key": "drawings/spec.pdf", "filename": "spec.pdf", "view_url": "/v/spec.pdf"},
        {"key": "drawings/a.png", "filename": "a.png", "view_url": "/v/a.png"},
        {"key": "", "filename": "nokey.png", "view_url": "/v/nokey.png"},
        "잘못된 항목",
    ]

    result = resolve_row_image_list(7, files, db, mobile_v2_active=True)

    assert [item["key"] for item in result] == ["drawings/a.png"]


def test_image_list_single_query_for_legacy_entries_and_thumb_fallback(monkeypatch) -> None:
    """view_url 없는 레거시 항목이 여러 개여도 조회는 1회, 썸네일은 thumbnail_key 우선."""
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    attachment = MagicMock()
    attachment.storage_key = "k1.png"
    attachment.thumbnail_key = "thumbs/k1.png"
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [attachment]
    files = [
        {"key": "k1.png", "filename": "k1.png"},
        {"key": "k2.png", "filename": "k2.png"},
    ]

    result = resolve_row_image_list(42, files, db, mobile_v2_active=True)

    assert db.query.call_count == 1
    # 뷰어는 항상 원본(full-size)을 연다.
    assert result[0]["view_url"] == "/api/files/view/k1.png"
    assert result[0]["download_url"] == "/api/files/download/k1.png"
    # 카드 썸네일만 파생본 우선 — thumb_url 은 파생본이 있을 때만 실린다(wire 증가 0).
    assert result[0]["thumb_url"] == "/api/files/view/thumbs/k1.png"
    assert "thumb_url" not in result[1]
    assert pick_row_thumbnail_url(result) == "/api/files/view/thumbs/k1.png"


def test_image_list_empty_when_thumbnails_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    db = MagicMock()
    files = [{"key": "a.png", "filename": "a.png", "view_url": "/v/a.png"}]

    assert resolve_row_image_list(1, files, db, mobile_v2_active=True) == []
    assert pick_row_thumbnail_url([]) is None


# --- rows 3필드 (렌더 + 권한 공식) -------------------------------------------


def _login_drawing_admin(client):
    user = User(
        username="drawing_review_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="DRAWING",
        name="Drawing Review Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _drawing_order_with_files() -> Order:
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="뷰어 배선",
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이장",
        status="DRAWING",
        manager_name="담당A",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "뷰어 고객"}, "manager": {"name": "담당A"}},
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [
                {
                    "key": "drawings/living.png",
                    "filename": "living.png",
                    "view_url": "/api/files/view/drawings/living.png",
                    "download_url": "/api/files/download/drawings/living.png",
                },
                {
                    "key": "drawings/spec.pdf",
                    "filename": "spec.pdf",
                    "view_url": "/api/files/view/drawings/spec.pdf",
                },
            ],
            "drawing_transfer_history": [],
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_gallery_card_carries_image_only_viewer_payload(client, monkeypatch) -> None:
    """카드 thumb 이 뷰어 마커 + 이미지만 담긴 파일 JSON 을 싣는다(PDF 제외)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order_with_files()

    response = client.get("/erp/drawing-workbench")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-foms-drawing-viewer" in body
    payload = re.search(r"data-foms-drawing-files='([^']*)'", body)
    assert payload is not None, "카드 thumb 에 뷰어 파일 JSON 부재"
    files = json.loads(payload.group(1).replace("&#34;", '"').replace("&amp;", "&"))
    assert [f["key"] for f in files] == ["drawings/living.png"]  # PDF 제외
    assert files[0]["view_url"] == "/api/files/view/drawings/living.png"
    assert files[0]["download_url"] == "/api/files/download/drawings/living.png"
    assert files[0]["filename"] == "living.png"


def test_workbench_review_permission_formula_excludes_drawing_team() -> None:
    """rows 권한 2필드 = is_admin or (can_sales and not is_drawing_team) — 순수 권한."""
    route = _read(WORKBENCH)
    assert "is_admin or (can_sales and not is_drawing_team)" in route
    assert "'can_confirm_receipt_perm': can_review_perm," in route
    assert "'can_request_revision': can_review_perm," in route
    # 뷰어 파일 목록은 서비스 헬퍼 경유(행당 1조회 불변) — 썸네일도 같은 결과에서 파생.
    assert "resolve_row_image_list(" in route
    assert "'drawing_files': image_files," in route
    assert "'thumbnail_url': pick_row_thumbnail_url(image_files)," in route
    # 상태 합성형(상세 라우트 can_confirm_receipt)과 이름 혼용 금지.
    assert "'can_confirm_receipt':" not in route
