"""P0-02 — drawing workbench mobile card thumb + filter offcanvas."""

import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.drawing_workbench_display import (
    drawing_thumb_enabled,
    resolve_row_thumbnail_url,
)
from foms.web.drawing.workbench import (
    _build_handoff_thread,
    _history_event_at_text,
    _resolve_construction_date_display,
)
from models import Order, User


def _login_drawing_admin(client):
    user = User(
        username="drawing_mobile_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="DRAWING",
        name="Drawing Mobile Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _drawing_order(structured_data=None):
    sd = {
        "parties": {"customer": {"name": "모바일 도면 고객"}, "manager": {"name": "담당A"}},
        "workflow": {"stage": "DRAWING"},
        "drawing": {"status": "IN_PROGRESS"},
        "drawing_current_files": [
            {
                "key": "drawings/test-plan.png",
                "filename": "test-plan.png",
                "view_url": "/api/files/view/drawings/test-plan.png",
            }
        ],
        "drawing_transfer_history": [],
        "drawing_assignees": [],
    }
    if structured_data:
        sd.update(structured_data)
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="모바일 도면",
        phone="010-1111-2222",
        address="Seoul",
        product="북박이",
        status="DRAWING",
        manager_name="담당A",
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _multi_drawing_order():
    return _drawing_order(
        {
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [
                {
                    "key": "drawings/living.png",
                    "filename": "living.png",
                    "view_url": "/api/files/view/drawings/living.png",
                },
                {
                    "key": "drawings/kitchen.png",
                    "filename": "kitchen.png",
                    "view_url": "/api/files/view/drawings/kitchen.png",
                },
            ],
            "drawing_transfer_history": [
                {
                    "action": "TRANSFER",
                    "at": "2026-06-01 10:00:00",
                    "by_user_name": "도면팀A",
                    "note": "1차 전달",
                    "files": [],
                },
                {
                    "action": "REQUEST_REVISION",
                    "at": "2026-06-02 11:00:00",
                    "by_user_name": "영업A",
                    "note": "2번 높이 수정",
                    "target_drawing_keys": ["drawings/kitchen.png"],
                    "target_drawing_numbers": [2],
                    "target_drawing_number": 2,
                },
            ],
        }
    )


def test_drawing_thumb_enabled_respects_env(monkeypatch):
    monkeypatch.delenv("FOMS_V3_DRAWING_THUMB_ENABLED", raising=False)
    assert drawing_thumb_enabled() is False
    assert drawing_thumb_enabled(mobile_v2_active=True) is True
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    assert drawing_thumb_enabled() is True
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    assert drawing_thumb_enabled(mobile_v2_active=True) is False


def test_drawing_workbench_displays_construction_date_column(client, monkeypatch):
    """데스크톱 테이블에 주문/고객 · 시공일 · 다음 액션 순으로 시공일이 표시된다."""
    _login_drawing_admin(client)
    _drawing_order(
        {
            "schedule": {"construction": {"date": "2026-07-15"}},
        }
    )

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert ">시공일</th>" in body
    assert ">다음 액션</th>" in body
    assert body.index(">시공일</th>") < body.index(">다음 액션</th>")
    assert "2026-07-15" in body


def test_resolve_construction_date_display_normalizes_dict_date():
    order = SimpleNamespace(erp_construction_date="2026-09-10")
    sd = {"schedule": {"construction": {"date": {"year": 2026, "month": 8, "day": 1}}}}
    assert _resolve_construction_date_display(order, sd) == "2026-08-01"


def test_drawing_workbench_construction_date_erp_fallback(client):
    """schedule date 비어 있으면 erp_construction_date fallback."""
    _login_drawing_admin(client)
    order = _drawing_order({"schedule": {"construction": {"date": "2026-07-15"}}})
    order.structured_data = {
        **order.structured_data,
        "schedule": {"construction": {"date": ""}},
    }
    order.erp_construction_date = "2026-09-10"
    db_session.commit()

    body = client.get("/erp/drawing-workbench").get_data(as_text=True)
    assert "2026-09-10" in body


def test_drawing_workbench_revision_dropzone_supports_scoped_clipboard_file_paste():
    """Revision attachments should accept pasted files without a document-level paste listener."""
    root = Path(__file__).resolve().parents[2]
    text = (root / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    revision_block = text[
        text.index('id="dw-revision-dropzone"') : text.index('id="dw-revision-preview"')
    ]

    assert 'id="dw-revision-dropzone"' in revision_block
    assert 'tabindex="0"' in revision_block
    assert "Ctrl+V 붙여넣기 가능" in revision_block
    assert "수정 요청 참고 파일 업로드 영역" in revision_block
    assert "function getDropzoneClipboardFiles(event)" in text
    assert "item.kind !== 'file'" in text
    assert "item.getAsFile()" in text
    assert "new File([rawFile], name" in text
    assert "function escapePreviewAttribute(value)" in text
    assert ".replace(/\"/g, '&quot;').replace(/'/g, '&#39;')" in text
    assert 'alt="${escapedAttrName}"' in text
    assert 'title="${escapedAttrName}"' in text
    assert "function setDropzoneInputFiles(input, files)" in text
    assert "new DataTransfer()" in text
    assert "return false;" in text[text.index("function setDropzoneInputFiles") : text.index("function appendFilesToDropzoneInput")]
    assert "catch (_)" in text[text.index("function setDropzoneInputFiles") : text.index("function appendFilesToDropzoneInput")]
    assert "function appendFilesToDropzoneInput(input, files)" in text
    assert "input.dispatchEvent(new Event('change', { bubbles: true }));" in text
    assert "dropzone.addEventListener('paste'" in text
    assert "appendFilesToDropzoneInput(input, files)" in text
    assert "dropzone.dataset.dwDropzoneBound" in text
    assert "setupDropzone('dw-revision-dropzone', 'dw-revision-files');" in text
    assert "renderFilePreview(input.files, previewId, inputId);" in text
    assert "showWorkbenchToast('선택한 파일을 제거하지 못했습니다.', 'error');" in text
    assert "document.addEventListener('paste'" not in text


def test_resolve_row_thumbnail_prefers_view_url(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    db = MagicMock()
    files = [{"key": "k1.png", "filename": "k1.png", "view_url": "/api/files/view/k1.png"}]
    assert resolve_row_thumbnail_url(1, files, db) == "/api/files/view/k1.png"
    db.query.assert_not_called()


def test_resolve_row_thumbnail_uses_attachment_thumb_key(monkeypatch):
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    attachment = MagicMock()
    attachment.thumbnail_key = "thumbs/k1.png"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = attachment
    files = [{"key": "k1.png", "filename": "k1.png"}]
    url = resolve_row_thumbnail_url(42, files, db)
    assert url == "/api/files/view/thumbs/k1.png"


def test_edit_order_drawing_return_to_sets_mobile_back_href(client, monkeypatch):
    """도면 큐 ERP수정 딥링크 return_to는 edit 모바일 셸 back을 drawing-workbench로 연결한다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _drawing_order()

    response = client.get(
        f"/edit/{order.id}?open=erp-order&return_to=erp_drawing_workbench_dashboard"
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-foms-shell-back-href="/erp/drawing-workbench"' in body


def test_drawing_workbench_mobile_queue_card_renders_erp_edit_cta(client, monkeypatch):
    """모바일 도면 큐 카드는 ERP Order 편집(erp-order) 딥링크를 작업 열기 왼쪽에 노출한다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-queue-card__erp-edit" in body
    assert "ERP수정" in body
    assert "open=erp-order" in body
    assert "return_to=erp_drawing_workbench_dashboard" in body
    card_actions = body[body.index("foms-drawing-queue-card__actions") : body.index("foms-drawing-queue-card__actions") + 1200]
    assert "foms-drawing-queue-card__erp-edit" in card_actions
    assert card_actions.index("foms-drawing-queue-card__erp-edit") < card_actions.index("foms-drawing-queue-card__open-work")


def test_drawing_workbench_mobile_markup_with_v2_and_thumb(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "erp-drawing-mobile-controls" in body
    assert "erp-drawing-mobile-filter-drawer" in body
    assert "foms-drawing-mobile-dashboard" in body
    assert "foms-drawing-queue-card__thumb" in body
    assert "erp-drawing-mobile-list" in body
    assert "foms-mobile-surfaces.css" in body
    assert "foms-drawing-mobile-v2" not in body
    assert "erp-pro-card__header--filter d-none d-lg-block" in body


def test_drawing_workbench_thumb_hidden_when_flag_off(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "false")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-queue-card__thumb" not in body


def test_drawing_workbench_mobile_single_list_my_first(client, monkeypatch):
    """단일 리스트 + '내 차례' 서버 우선정렬. 목업 §5.2 '내 차례/상대 차례' 그룹 구분 노출(번호 페이저)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_DRAWING_THUMB_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order()

    response = client.get("/erp/drawing-workbench")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-queue" in body
    assert "data-foms-mobile-queue-scroll" not in body  # 무한스크롤 아닌 번호 페이저
    assert "foms-drawing-queue-card__turn" in body  # 카드별 차례 표시 유지
    # 목업 프레임 A: my_todo 우선정렬 단일 리스트에 '내 차례/상대 차례' 그룹 헤더를 얹는다.
    assert "foms-drawing-queue__group" in body
    assert ("내 차례" in body) or ("상대 차례" in body)


@pytest.mark.parametrize("mobile_v2_active", [False, True])
def test_drawing_workbench_mine_filter_excludes_unrelated_orders_for_admin(
    client,
    monkeypatch,
    mobile_v2_active,
):
    """PC/모바일 모두 ADMIN 작업 권한을 mine 소유권으로 오판하지 않는다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true" if mobile_v2_active else "false")
    user = _login_drawing_admin(client)
    if mobile_v2_active:
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    _drawing_order(
        {
            "parties": {
                "customer": {"name": "내 도면 주문"},
                "manager": {"name": "다른 영업"},
            },
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"drawing_assignee_user_ids": [user.id]},
            "drawing_assignees": [{"id": user.id, "name": user.name}],
        }
    )
    _drawing_order(
        {
            "parties": {
                "customer": {"name": "내 영업 주문"},
                "manager": {"name": user.name},
            },
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"drawing_assignee_user_ids": [user.id + 100]},
            "drawing_assignees": [{"id": user.id + 100, "name": "다른 도면"}],
        }
    )
    _drawing_order(
        {
            "parties": {
                "customer": {"name": "타인 도면 주문"},
                "manager": {"name": "안종훈"},
            },
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"drawing_assignee_user_ids": [user.id + 999]},
            "drawing_assignees": [{"id": user.id + 999, "name": "최상용"}],
        }
    )

    response = client.get("/erp/drawing-workbench?mine=1")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    expected_mode = "true" if mobile_v2_active else "false"
    assert f'data-erp-mobile-v2="{expected_mode}"' in body
    assert "내 도면 주문" in body
    assert "내 영업 주문" in body
    assert "타인 도면 주문" not in body


def test_drawing_workbench_mobile_numbered_pagination(client, monkeypatch):
    """회귀: per_page=25 도면 모바일 큐가 25건 초과 시 하단 PC식 번호 페이저로 페이지 이동."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    for _ in range(30):
        _drawing_order()

    page1 = client.get("/erp/drawing-workbench")
    assert page1.status_code == 200
    body = page1.get_data(as_text=True)
    assert "foms-mobile-pager" in body
    assert "page=2" in body
    assert "data-foms-mobile-queue-scroll" not in body
    assert "data-foms-mobile-queue-sentinel" not in body

    page2 = client.get("/erp/drawing-workbench?page=2")
    assert page2.status_code == 200
    body2 = page2.get_data(as_text=True)
    assert "foms-mobile-pager" in body2
    assert 'aria-current="page"' in body2  # 현재 페이지(2) 표시 → 1페이지 복귀 가능


def test_drawing_workbench_multi_file_detail_opens_mobile_list(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="list"' in body
    assert "foms-drawing-sheet-list" in body
    assert "living.png" in body
    assert "kitchen.png" in body


def test_drawing_workbench_valid_drawing_key_opens_mobile_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=drawings/kitchen.png")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert "foms-drawing-handoff-detail" in body
    assert "도면 2 / 2" in body
    assert "data-selected-drawing-key=\"drawings/kitchen.png\"" in body
    assert "foms-drawing-viewer__download" in body
    assert "/api/files/download/drawings/kitchen.png" in body


def test_drawing_workbench_invalid_drawing_key_returns_mobile_list_notice(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=missing")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="list"' in body
    assert "선택한 도면을 찾을 수 없습니다." in body


def test_drawing_workbench_single_file_invalid_key_normalizes_to_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?drawing_key=missing")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert 'data-selected-drawing-key="drawings/test-plan.png"' in body
    assert "foms-drawing-handoff-detail" in body


def test_drawing_workbench_target_deeplink_prefers_mobile_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_drawing_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}?target_no=2")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-handoff-mode="detail"' in body
    assert "도면 2 / 2" in body
    assert "foms-drawing-thread__msg" in body
    thread_html = body[
        body.index('class="foms-drawing-thread"') : body.index(
            '<div class="foms-drawing-action-bar">'
        )
    ]
    assert thread_html.index("2번 높이 수정") < thread_html.index("1차 전달")
    assert "2026-06-02 20:00:00" in body


def test_drawing_history_at_text_converts_utc_naive_to_kst():
    assert (
        _history_event_at_text({"action": "TRANSFER", "at": "2026-06-29 07:13:00"})
        == "2026-06-29 16:13:00"
    )


def test_drawing_handoff_thread_is_newest_first():
    """모바일 도면 handoff 타임라인은 최신 이력을 최상단에 렌더링한다."""
    thread = _build_handoff_thread(
        [
            {
                "action": "TRANSFER",
                "at": "2026-06-25 07:26:34",
                "by_user_name": "구현진",
                "note": "도면 전달 첨부 1건",
            },
            {
                "action": "REQUEST_REVISION",
                "at": "2026-06-25 07:29:38",
                "by_user_name": "이시영",
                "note": "수정요청: 1번 대상 하부 3단 서랍 추가 요청",
                "target_drawing_numbers": [1],
            },
            {
                "action": "TRANSFER",
                "at": "2026-06-25 07:32:50",
                "by_user_name": "구현진",
                "note": "도면 전달 · 1번 내용 첨부 1건",
            },
            {
                "action": "REQUEST_REVISION",
                "at": "2026-06-29 04:16:29",
                "by_user_name": "이시영",
                "note": "수정요청: 1번 대상 좌측 장 1100 -> 1000으로 수정 요청",
                "target_drawing_numbers": [1],
            },
            {
                "action": "TRANSFER",
                "at": "2026-06-29 08:04:18",
                "by_user_name": "구현진",
                "note": "도면 전달 · 1번 대상 첨부 1건",
            },
        ]
    )

    assert [item["at"] for item in thread] == [
        "2026-06-29 08:04:18",
        "2026-06-29 04:16:29",
        "2026-06-25 07:32:50",
        "2026-06-25 07:29:38",
        "2026-06-25 07:26:34",
    ]
    assert thread[0]["side"] == "left"
    assert thread[1]["side"] == "right"
    assert thread[1]["target_text"] == "1번 대상"


def test_drawing_workbench_non_cohort_keeps_legacy_detail(client, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    _login_drawing_admin(client)
    order = _multi_drawing_order()

    response = client.get(f"/erp/drawing-workbench/{order.id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-drawing-handoff" not in body
    assert "도면 작업실 실행판" in body


def _pipeline_total_count(html: str) -> int | None:
    match = re.search(
        r'erp-pro-pipeline__count[^>]*>(\d+)</div>\s*<div class="erp-pro-pipeline__label">전체</div>',
        html,
    )
    return int(match.group(1)) if match else None


def test_drawing_workbench_pipeline_stats_stable_under_list_filters(client, monkeypatch):
    """프로세스 맵 total은 due_today/unread/status 목록 필터와 무관하게 전체 큐 기준."""
    _login_drawing_admin(client)
    for status in ("RETURNED", "TRANSFERRED", "IN_PROGRESS"):
        _drawing_order({"drawing": {"status": status}, "drawing_status": status})

    base_body = client.get("/erp/drawing-workbench").get_data(as_text=True)
    assert _pipeline_total_count(base_body) == 3
    assert "js/drawing/workbench-dashboard.js" in base_body
    assert "let drawingUsersCache" not in base_body

    due_today_body = client.get("/erp/drawing-workbench?due_today=1").get_data(as_text=True)
    assert _pipeline_total_count(due_today_body) == 3

    unread_body = client.get("/erp/drawing-workbench?unread=1").get_data(as_text=True)
    assert _pipeline_total_count(unread_body) == 3

    status_body = client.get("/erp/drawing-workbench?status=RETURNED").get_data(as_text=True)
    assert _pipeline_total_count(status_body) == 3


def test_drawing_workbench_status_pipeline_clears_quick_filters_in_js() -> None:
    """Status stage click must drop unread/due_today so filter switches do not stack."""
    js_path = Path(__file__).resolve().parents[2] / "static" / "js" / "drawing" / "workbench-dashboard.js"
    source = js_path.read_text(encoding="utf-8")
    status_fn = source.split("function navigatePipelineStatus(status)")[1].split("function navigatePipelineQuickFilter")[0]
    assert "params.delete('unread')" in status_fn
    assert "params.delete('due_today')" in status_fn
    quick_fn = source.split("function navigatePipelineQuickFilter(filterType)")[1].split("function bindPipelineDelegationOnce")[0]
    assert "params.set('unread', '1')" in quick_fn
    assert "params.set('due_today', '1')" in quick_fn
