"""모바일 생산/시공 카드 액션과 단계 배지 라벨 계약(C-D1·C-D2·C-D3).

화면 잣대 == 서버 잣대를 지키는지 본다 — 권한 없는 사람에게 버튼이 보이면
"눌러도 거부당하는 버튼" 이 되고, 권한이 있는데 버튼이 없으면 막다른 길이 된다.
음성 대조군(권한 없는 팀)을 반드시 함께 세어야 "전수 확인" 이다.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_mobile_order_display import stage_badge_label
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]


def _make_user(client, username: str, team: str | None, role: str = "STAFF") -> User:
    """주어진 팀·권한으로 사용자를 만들고 세션에 로그인시킨다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _enable_v2(monkeypatch, user_id: int) -> None:
    """v2 모바일 셸을 켠다(코호트 env 이름은 역사적 FOMS_V3_SHELL_COHORT)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user_id))


def _add_order(
    stage: str,
    name: str,
    *,
    construction_started: bool = False,
    manager_name: str = "Bob",
) -> Order:
    """주어진 메인 단계로 ERP 주문 1건을 만든다.

    시공팀은 항상 "내 담당" 으로만 큐를 보므로(erp_mine_only_for_construction),
    시공 화면 테스트는 ``manager_name`` 에 로그인 사용자 이름을 넣어 seed 한다.
    """
    today = date.today().strftime("%Y-%m-%d")
    workflow: dict = {"stage": stage}
    if construction_started:
        workflow["history"] = [{"note": "시공 시작"}]
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status=stage,
        manager_name=manager_name,
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data={"workflow": workflow},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _seed_production_orders() -> dict[str, Order]:
    """생산 큐 3버킷(제작대기·제작중·제작완료) 주문을 1건씩 만든다."""
    waiting = _add_order("PRODUCTION", "생산 제작대기")
    running = _add_order("PRODUCTION", "생산 제작중")
    db_session.add(
        ProductionRun(order_id=running.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True)
    )
    done = _add_order("CONSTRUCTION", "생산 제작완료")
    db_session.commit()
    return {"waiting": waiting, "running": running, "done": done}


def _count_action(body: str, action: str) -> int:
    """응답 본문에서 해당 data-action 버튼 개수."""
    return len(re.findall(r'data-action="%s"' % re.escape(action), body))


def _mobile_queue_section(body: str, aria_label: str) -> str:
    """모바일 작업 큐 ``<section>`` 만 잘라 낸다.

    같은 응답에는 태블릿 작업모드·PC 본문도 함께 실린다(CSS 로 숨긴다). 모바일 큐의
    권한 계약을 재려면 그 구간만 세야 다른 표면의 버튼이 섞여 들어오지 않는다.
    """
    marker = f'aria-label="{aria_label}"'
    assert marker in body, aria_label
    start = body.index(marker)
    return body[start:body.index("</section>", start)]


def _order_ids_for_action(body: str, action: str) -> list[str]:
    """해당 data-action 버튼들이 달고 있는 data-order-id 목록."""
    pattern = re.compile(
        r'data-order-id="(\d+)"[^>]*data-action="%s"' % re.escape(action)
    )
    return pattern.findall(body)


# --- v2 모바일: 생산 -------------------------------------------------------


def test_생산_권한자_모바일_큐에_되돌리기_버튼이_해당_단계에만_나온다(client, monkeypatch):
    user = _make_user(client, "mpa_prod_staff", "PRODUCTION")
    _enable_v2(monkeypatch, user.id)
    orders = _seed_production_orders()

    res = client.get("/erp/production/dashboard")
    assert res.status_code == 200
    body = res.get_data(as_text=True)

    assert _count_action(body, "productionRework") == 1
    assert _count_action(body, "productionCancel") == 1
    assert _count_action(body, "productionUncomplete") == 1
    # 제작중 카드에만 수정 제작·제작 취소가, 제작완료 카드에만 완료 취소가 붙는다.
    assert _order_ids_for_action(body, "productionRework") == [str(orders["running"].id)]
    assert _order_ids_for_action(body, "productionCancel") == [str(orders["running"].id)]
    assert _order_ids_for_action(body, "productionUncomplete") == [str(orders["done"].id)]


def test_생산_권한_없는_팀에게는_생산_액션_버튼이_하나도_없다(client, monkeypatch):
    """음성 대조군 — 도면팀은 서버(_production_steps_edit_required)가 403 을 준다.

    되돌리기뿐 아니라 시작·완료도 같은 데코레이터를 지나므로 화면에서도 전부 사라져야
    한다(눌러도 거부당할 버튼 0). 단계 배지는 남아 지금 상태는 여전히 읽을 수 있다.
    """
    user = _make_user(client, "mpa_drawing_staff", "DRAWING")
    _enable_v2(monkeypatch, user.id)
    _seed_production_orders()

    res = client.get("/erp/production/dashboard")
    assert res.status_code == 200
    queue = _mobile_queue_section(res.get_data(as_text=True), "생산 모바일 작업 큐")

    assert _count_action(queue, "productionRework") == 0
    assert _count_action(queue, "productionCancel") == 0
    assert _count_action(queue, "productionUncomplete") == 0
    assert _count_action(queue, "startProduction") == 0
    assert _count_action(queue, "completeProduction") == 0
    # 배지는 남는다 — 권한이 없어도 무슨 단계인지는 보인다(정보까지 빼앗지 않는다).
    assert "제작중" in queue


# --- v2 모바일: 시공 -------------------------------------------------------


def test_시공팀에게만_시공_불가_버튼이_시공중_카드에_나온다(client, monkeypatch):
    user = _make_user(client, "mpa_constr_staff", "CONSTRUCTION")
    _enable_v2(monkeypatch, user.id)
    running = _add_order(
        "CONSTRUCTION", "시공중 현장", construction_started=True, manager_name=user.name
    )
    _add_order("CONSTRUCTION", "시공대기 현장", manager_name=user.name)

    res = client.get("/erp/construction/dashboard")
    assert res.status_code == 200
    body = res.get_data(as_text=True)

    assert _count_action(body, "constructionFail") == 1
    assert _order_ids_for_action(body, "constructionFail") == [str(running.id)]


def test_음성_대조군_도면팀에게는_시공_액션_버튼이_없다(client, monkeypatch):
    """음성 대조군 — 서버(erp_construction_edit_required)가 실제로 403 을 주는 팀(도면팀)."""
    user = _make_user(client, "mpa_drawing_cons", "DRAWING")
    _enable_v2(monkeypatch, user.id)
    _add_order("CONSTRUCTION", "시공중 현장2", construction_started=True)

    res = client.get("/erp/construction/dashboard")
    assert res.status_code == 200
    queue = _mobile_queue_section(res.get_data(as_text=True), "시공 모바일 작업 큐")

    assert _count_action(queue, "constructionFail") == 0
    assert _count_action(queue, "startConstruction") == 0
    assert _count_action(queue, "openCompleteGate") == 0
    assert _count_action(queue, "completeConstruction") == 0


def test_양성_대조군_CS팀도_시공_버튼을_본다(client, monkeypatch):
    """양성 대조군 — CS 팀은 서버가 200 을 주므로 버튼이 보여야 한다(막다른 길 0).

    화면이 시공팀으로만 좁히면 CS·영업팀 담당자는 할 수 있는 일을 못 하게 된다.
    """
    user = _make_user(client, "mpa_cs_staff", "CS")
    _enable_v2(monkeypatch, user.id)
    running = _add_order("CONSTRUCTION", "CS 시공중 현장", construction_started=True)

    running_id = running.id
    res = client.get("/erp/construction/dashboard")
    assert res.status_code == 200
    queue = _mobile_queue_section(res.get_data(as_text=True), "시공 모바일 작업 큐")

    assert _order_ids_for_action(queue, "constructionFail") == [str(running_id)]
    assert _count_action(queue, "completeConstruction") == 1
    assert _count_action(queue, "openCompleteGate") == 1


# --- 사유 시트(window.prompt 전면 금지) ------------------------------------


def test_모바일_세_화면_응답에_window_prompt_가_없다(client, monkeypatch):
    """음성 대조군 — prompt 가 한 번이라도 남으면 패턴 통일이 깨진 것이다."""
    user = _make_user(client, "mpa_admin_prompt", "CS", role="ADMIN")
    _enable_v2(monkeypatch, user.id)
    _seed_production_orders()
    _add_order("CONSTRUCTION", "prompt 점검 현장", construction_started=True)

    for path in (
        "/erp/production/dashboard",
        "/erp/construction/dashboard",
        "/erp/dashboard",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
        body = res.get_data(as_text=True)
        assert "window.prompt(" not in body, path

    # 공용 사유 시트 원본에도 prompt 가 없다.
    for rel in (
        "static/js/foms/foms-reason-sheet.js",
        "static/js/foms/tablet-domain-sheets.js",
        "static/js/foms/tablet-construction-workmode.js",
        "static/js/construction/dashboard.js",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "window.prompt(" not in src, rel


def test_사유_시트_공개_API_가_그대로다():
    src = (ROOT / "static/js/foms/foms-reason-sheet.js").read_text(encoding="utf-8")
    assert "window.__FOMS_REASON_SHEET_BOUND" in src
    assert "window.FomsReasonSheet = { open: open, close: close };" in src
    markup = (ROOT / "templates/partials/shared/foms_reason_sheet.html").read_text(encoding="utf-8")
    assert "data-foms-reason-sheet" in markup
    assert "data-foms-reason-submit" in markup


# --- 라벨(C-D3) ------------------------------------------------------------


def test_CS_단계_배지가_AS_가_아니라_CS_다():
    assert stage_badge_label("CS") == "CS"
    assert stage_badge_label("COMPLETED") == "완료"
    assert stage_badge_label("MEASURE") == "실측"


def test_강제_단계_변경_화면_LABELS_가_정본과_같다():
    """erp-stage-override.js 의 단계 이름표가 erp_policy_constants.STAGE_LABELS 와 같은 값인지."""
    src = (ROOT / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    rank_block = src.split("var RANK = {", 1)[1].split("};", 1)[0]
    label_block = src.split("var LABELS = {", 1)[1].split("};", 1)[0]
    rank_codes = re.findall(r"^\s*([A-Z_]+)\s*:", rank_block, re.M)
    labels = dict(re.findall(r"^\s*([A-Z_]+)\s*:\s*'([^']*)'", label_block, re.M))
    assert len(rank_codes) >= 8
    assert set(labels) == set(rank_codes)
    for code in rank_codes:
        assert labels[code] == STAGE_LABELS[code], code


def test_완료_요건_미충족_문구가_사람_말로_바뀌고_채우러_갈_길을_준다():
    """서버는 missing 코드만 준다 — 화면이 사람 말로 옮기고 완료 준비 시트로 보낸다."""
    src = (ROOT / "static/js/construction/dashboard.js").read_text(encoding="utf-8")
    assert "완료 사진 2장" in src
    assert "고객 서명" in src
    assert 'data-action="openCompleteGate"' in src
