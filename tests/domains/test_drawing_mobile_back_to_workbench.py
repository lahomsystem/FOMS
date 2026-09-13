"""도면 작업실 모바일 — 상태 리본 안 뒤로가기 앵커의 자리 계약.

2026-09-13 운영 제보: 모바일 도면 상세에서 도면 작업실 목록으로 나갈 길이 없었다.
고친 방식은 "새 블록을 만들지 않고 이미 있는 상태 리본(`.foms-drawing-turn`) 첫 칼럼에
아이콘 앵커 하나를 넣는다" 이다. 이 파일이 고정하는 것은 네 가지다.

1. 앵커는 상태 리본 **안쪽**에 있고(목록 뷰·상세 뷰 공통), 하단 액션바보다 앞에 온다.
2. 목적지를 URL 로 명시한다 — history.back() 계열이 아니다.
3. 상단 블록 수가 늘지 않는다(리본 높이·화면 위치를 밀지 않는다).
4. 스타일은 컴포넌트 CSS 에만 있고 인라인 style 은 없다.

주의(브리프 6절 함정): 데스크톱 본문과 모바일 partial 은 **같은 응답 안에 함께** 온다.
그래서 이 파일의 모든 카운트는 구간을 갈라서 센다.
"""

import io
from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

CSS_PATH = "static/css/components/foms-drawing-mobile.css"
TEMPLATE_PATH = "templates/drawing/partials/workbench_mobile_handoff.html"

BACK_CLASS = "foms-drawing-turn__back"
WORKBENCH_URL = "/erp/drawing-workbench"

# 모바일 구간의 상단 블록 수 — 이번 변경 전후로 같아야 한다.
# 실측(2026-09-13): 상세 뷰 `<section` 4 + `<details` 1 = 5, 목록 뷰 `<section` 3 + `<details` 0 = 3.
#   상세 뷰: 상태 리본 / 주문 요약 / 도면 상세(뷰어) / 대화 스레드 + 제작 자료(details)
#   목록 뷰: 상태 리본 / 주문 요약 / 도면 목록
# 뒤로가기는 리본 **안**에 들어가므로 이 수가 변하면 블록을 새로 만든 것이다.
DETAIL_TOP_BLOCKS = 5
LIST_TOP_BLOCKS = 3

CHANGES = [
    {"path": "items.0.spec", "label": "항목1 스펙", "from": "1170", "to": "1165*620*2311"},
]


def _login(client, *, username="dw_back_admin"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="DRAWING",
        name="도면 담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, files=1, with_change=True):
    history = []
    if with_change:
        history.append(
            {
                "action": "ERP_ORDER_CHANGED",
                "at": "2026-09-11 04:58:00",
                "by_user_name": "최진호",
                "changes": CHANGES,
            }
        )
    drawing_files = [
        {
            "key": f"drawings/back-{i}.png",
            "filename": f"back-{i}.png",
            "view_url": f"/api/files/view/drawings/back-{i}.png",
        }
        for i in range(1, files + 1)
    ]
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="최승희",
        phone="010-0000-0000",
        address="송파구 충민로4길 19",
        product="몰딩여닫이",
        status="DRAWING",
        manager_name="최진호",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "최승희"}, "manager": {"name": "최진호"}},
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "IN_PROGRESS", "order_change_pending": with_change},
            "drawing_current_files": drawing_files,
            "drawing_transfer_history": history,
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _render_full(client, order, monkeypatch, user, query=""):
    """응답 전체(데스크톱 본문 + 모바일 partial)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    response = client.get(f"/erp/drawing-workbench/{order.id}{query}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _mobile(body):
    """모바일 구간만: `foms-drawing-handoff__body` 시작 ~ `foms-drawing-action-bar` 시작."""
    start = body.index("foms-drawing-handoff__body")
    end = body.index("foms-drawing-action-bar", start)
    return body[start:end]


def _desktop(body):
    """데스크톱 구간만: `dw-legacy-detail` 이후 전부."""
    return body[body.index("dw-legacy-detail") :]


def _back_tag(section):
    """뒤로가기 앵커의 여는 태그 문자열."""
    at = section.index(BACK_CLASS)
    return section[section.rindex("<a", 0, at) : section.index(">", at) + 1]


def test_back_link_sits_inside_the_status_ribbon(client, monkeypatch):
    """앵커는 새 블록이 아니라 이미 있는 상태 리본 섹션 **안쪽**에 있다."""
    user = _login(client)
    full = _render_full(client, _order(), monkeypatch, user)
    mobile = _mobile(full)

    ribbon_at = mobile.index('class="foms-drawing-turn')
    ribbon_end = mobile.index("</section>", ribbon_at)
    back_at = mobile.index(BACK_CLASS)

    assert ribbon_at < back_at < ribbon_end
    # 하단 고정 액션바보다 앞 — 화면 위쪽 리본 자리를 지킨다.
    assert full.index(BACK_CLASS) < full.index("foms-drawing-action-bar")


def test_back_link_names_its_destination_and_label(client, monkeypatch):
    """목적지를 URL 로 명시한다 — history.back() 함정 회귀 방지.

    셸 헤더의 `data-foms-shell-back` 핸들러는 `history.length > 1` 이면 `history.back()` 을
    부른다. 도면 페이저(이전/다음)를 몇 번 누른 뒤에는 목록이 아니라 직전 도면으로 돌아가고,
    알림 딥링크로 들어온 사람은 앱 밖으로 나간다. 그래서 순수 `<a href>` 여야 한다.
    """
    user = _login(client)
    full = _render_full(client, _order(), monkeypatch, user)
    tag = _back_tag(_mobile(full))

    assert f'href="{WORKBENCH_URL}"' in tag
    assert 'aria-label="도면 작업실 목록으로 돌아가기"' in tag
    assert "data-foms-shell-back" not in full
    assert "history.back" not in tag


def test_back_link_shows_in_both_list_and_detail_views(client, monkeypatch):
    """도면 2장 주문의 목록 뷰·상세 뷰 양쪽에서 정확히 1개씩(계약 E)."""
    user = _login(client)
    order = _order(files=2)

    list_body = _render_full(client, order, monkeypatch, user)
    assert 'data-handoff-mode="list"' in list_body
    detail_body = _render_full(
        client, order, monkeypatch, user, query="?drawing_key=drawings/back-1.png"
    )
    assert 'data-handoff-mode="detail"' in detail_body

    for body in (list_body, detail_body):
        assert _mobile(body).count(BACK_CLASS) == 1
        assert _desktop(body).count(BACK_CLASS) == 0
        assert f'href="{WORKBENCH_URL}"' in _back_tag(_mobile(body))


def test_back_link_survives_orders_without_change_line(client, monkeypatch):
    """주문 변경 줄이 없어도 뒤로가기는 있다(변경 줄 유무와 독립)."""
    user = _login(client)
    body = _render_full(client, _order(with_change=False), monkeypatch, user)

    assert "dwOrderChangeLine" not in body
    assert _mobile(body).count(BACK_CLASS) == 1
    assert _desktop(body).count(BACK_CLASS) == 0


def test_top_block_count_is_unchanged(client, monkeypatch):
    """뒤로가기는 리본 **안**에 들어가므로 이 수가 변하면 블록을 새로 만든 것이다."""
    user = _login(client)

    detail = _mobile(_render_full(client, _order(), monkeypatch, user))
    assert detail.count("<section") + detail.count("<details") == DETAIL_TOP_BLOCKS

    list_body = _mobile(_render_full(client, _order(files=2), monkeypatch, user))
    assert "foms-drawing-sheet-list" in list_body
    assert list_body.count("<section") + list_body.count("<details") == LIST_TOP_BLOCKS


def test_back_link_is_not_mistaken_for_the_change_action(client, monkeypatch):
    """뒤로가기가 변경 줄의 액션·포커스 훅으로 오인되지 않는다(계약 F)."""
    user = _login(client)
    mobile = _mobile(_render_full(client, _order(), monkeypatch, user))

    assert mobile.count("data-dw-order-change-focus") == 1
    assert mobile.count("foms-drawing-turn__change-act") == 1

    tag = _back_tag(mobile)
    assert "data-dw-order-change-focus" not in tag
    assert "foms-drawing-turn__change-act" not in tag


def test_back_link_styles_live_in_the_component_css():
    """스타일은 컴포넌트 CSS 에만 — 인라인 style 금지(ratchet)."""
    css = io.open(CSS_PATH, encoding="utf-8").read()
    assert f".{BACK_CLASS}" in css
    assert "grid-template-columns: auto 0.75rem minmax(0, 1fr)" in css

    template = io.open(TEMPLATE_PATH, encoding="utf-8").read()
    at = template.index(BACK_CLASS)
    tag = template[template.rindex("<a", 0, at) : template.index(">", at) + 1]
    assert "style=" not in tag
