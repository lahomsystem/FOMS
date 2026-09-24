"""실측 모바일 한눈 목록(글랜스) — 화면 계약.

소스 문자열 계약(템플릿·CSS·JS 원문)과 HTTP 렌더 계약으로 나눈다.
고정하는 회귀축:
- "다음 방문" 히어로가 사라지고 담당자 묶음 체크리스트가 그 자리에 있을 것
- 담당 띠의 둥근 전화 버튼이 tel: 링크일 것(카드와 같은 번호 정규화). 이름은 접기 단추다(통합 화면)
- 체크 버튼은 단일 날짜 모드 + ERP 수정 권한일 때만 눌린다
- 모바일 이미지 저장이 PC 와 같은 함수를 쓰고, PC 표식은 어떤 CSS 도 고르지 않는다
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from foms.web.measurement import dashboard as erp_measurement_dashboard
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User

ROOT = Path(__file__).resolve().parents[2]

MOBILE_LIST = "templates/measurement/partials/mobile_list.html"
QUEUE_CARD = "templates/partials/shared/erp_mobile_queue_card_v2.html"
DASHBOARD_MAIN = "templates/measurement/partials/dashboard_main.html"
DASHBOARD_SCRIPTS = "templates/measurement/partials/dashboard_scripts.html"
GLANCE_CSS = "static/css/contexts/measurement/measurement-mobile-glance.css"
IMAGE_EXPORT_JS = "static/js/measurement/image-export.js"
GLANCE_JS = "static/js/measurement/mobile-glance.js"
SAVE_SHEET_JS = "static/js/measurement/image-save-sheet.js"
ENTRY_JS = "static/js/measurement/measurement-entry.js"

PHONE_FILTER = "|replace('-', '')|replace(' ', '')"
FAKE_TODAY = date(2026, 4, 8)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _missing(text: str, needles: list[str]) -> list[str]:
    return [n for n in needles if n not in text]


def _present(text: str, needles: list[str]) -> list[str]:
    return [n for n in needles if n in text]


# ------------------------------------------------------------ A. 템플릿 계약

def test_mobile_list_has_glance_contract_names():
    tpl = _read(MOBILE_LIST)
    required = [
        'data-meas-glance aria-label="실측 한눈 목록"',
        'class="foms-meas-glance foms-meas-glance--unified',
        "foms-meas-glance__head",
        "foms-meas-glance__title",
        "foms-meas-glance__count",
        "data-meas-glance-count",
        'class="foms-meas-glance__save" data-meas-export-image',
        "fa-file-image",
        "이미지 저장",
        "data-meas-glance-msg",
        "foms-meas-glance__grp",
        "data-meas-glance-grp",
        "foms-meas-glance__gname",
        '<progress class="foms-meas-glance__prog"',
        "data-meas-glance-grp-count",
        # 담당 이름은 접기 단추, 오른쪽 둥근 버튼만 전화(통합 화면 SPEC §3 담당 띠).
        'class="foms-meas-glance__call" href="tel:{{ _gp }}" data-queue-card-call-link',
        "(g.manager_phone or '')" + PHONE_FILTER,
        'class="foms-meas-glance__check" data-meas-visit-toggle="{{ o.id }}" data-meas-visit-date=',
        "aria-pressed=",
        'href="#meas-card-{{ o.id }}" data-meas-glance-go="{{ o.id }}" aria-haspopup="dialog"',
        "foms-meas-glance__name",
        "foms-meas-glance__addr",
        "foms-meas-glance__prod",
        "foms-meas-glance__time",
        "channel_mark(o.channel_source|default(none, true))",
        'id="meas-card-{{ o.id }}"',
        # 유지
        "foms-v2dh-status",
        "render_queue_card_v2",
    ]
    assert _missing(tpl, required) == []


def test_mobile_list_drops_next_visit_hero():
    """방문 시간은 전날 확정 예정값이라 '다음 방문' 안내는 틀린 안내가 된다."""
    tpl = _read(MOBILE_LIST)
    forbidden = ["foms-v2dh-hero", "_mhero", "mobile_hero_row", "다음 방문", "style="]
    assert _present(tpl, forbidden) == []


def test_manager_phone_normalization_matches_queue_card():
    """글랜스 담당자 번호 정규화가 카드(erp_mobile_queue_card_v2.html:29)와 같은 필터 체인."""
    card = _read(QUEUE_CARD)
    assert "(order.manager_phone or '')" + PHONE_FILTER in card
    assert PHONE_FILTER in _read(MOBILE_LIST)


# ------------------------------------------------------------ B. 링크 계약

def test_dashboard_main_links_glance_css_before_desktop_body():
    main = _read(DASHBOARD_MAIN)
    link = "css/contexts/measurement/measurement-mobile-glance.css') }}?v=20260924a"
    anchor = "{% set _fos_desktop_body %}"
    assert link in main
    assert anchor in main
    assert main.index(link) < main.index(anchor)
    assert 'id="btn-export-image"' in main, "PC 이미지 저장 버튼은 그대로여야 한다"


# ------------------------------------------------------------ C. CSS 계약

def test_glance_css_contract():
    css = _read(GLANCE_CSS)
    required = [
        ".foms-meas-export-host",
        ".is-capturing",
        ".is-glance-flash",
        ".foms-meas-glance__prog",
        "::-webkit-progress-value",
        "scroll-margin-top",
        ".foms-meas-glance__check",
    ]
    assert _missing(css, required) == []


def test_glance_css_does_not_touch_pc_export_or_hero():
    """data-meas-export-target 을 고르는 규칙이 호스트 밖에 생기면 PC PNG 가 달라진다.

    모바일 복제본용 규칙(리사이저의 td overflow:hidden 대체)은 화면 밖 호스트 안에서만 허용한다
    — PC 캡처에는 호스트가 없으므로 PC 결과는 그대로다.
    """
    css = _read(GLANCE_CSS)
    forbidden = [".measurement-table", ".foms-v2dh-", ".foms-hero-"]
    assert _present(css, forbidden) == []
    no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    target_selectors = [
        sel.strip()
        for block in re.findall(r"([^{}]+)\{", no_comments)
        for sel in block.split(",")
        if "data-meas-export-target" in sel
    ]
    assert target_selectors, "모바일 캡처 overflow 규칙이 있어야 한다"
    assert all(sel.startswith(".foms-meas-export-host ") for sel in target_selectors), target_selectors
    assert "overflow: hidden" in no_comments.split("[data-meas-export-target] > tbody > tr > th", 1)[1].split("}", 1)[0]


# ------------------------------------------------------------ D. JS 계약

def test_image_export_js_shares_pc_capture_path():
    js = _read(IMAGE_EXPORT_JS)
    required = [
        "data-meas-export-target",
        "[data-meas-export-target]",
        "[data-meas-export-image]",
        "btn-export-image",
        "getClientRects",
        "cloneNode(true)",
        "foms-meas-export-host",
        "is-capturing",
        "FomsMeasSaveSheet.open",
        "ensureHtml2canvas",
        "localDateIso()",
        "Math.max(2, Math.min(window.devicePixelRatio || 1, 3))",
        "' 실측 일정.png'",
        "canvas.toDataURL('image/png')",
        "prepareExportTable(clonedDoc, clonedTable, titleText)",
    ]
    assert _missing(js, required) == []


def test_image_export_js_hands_mobile_png_to_save_sheet():
    """휴대폰은 캡처를 기다린 뒤 공유를 부르면 탭 효력이 끝나 막힌다 — 저장은 시트 버튼에서만 부른다."""
    js = _read(IMAGE_EXPORT_JS)
    assert _present(js, ["navigator.share", "pendingShare", "눌러서 공유"]) == []
    # 크기 측정 복제본에도 캡처와 같은 표식을 달아 호스트 CSS(width:auto)가 똑같이 먹게 한다.
    probe_block = js.split("function measureOffscreenScale", 1)[1].split("prepareExportTable(probeDoc", 1)[0]
    assert "probe.setAttribute('data-meas-export-target', '1')" in probe_block


def test_save_sheet_js_platform_paths():
    js = _read(SAVE_SHEET_JS)
    required = [
        "window.FomsMeasSaveSheet",
        "navigator.share({ files: [file] })",
        "canShare",
        "AbortError",
        "NotAllowedError",
        "IS_IOS",
        "IS_ANDROID",
        "사진 앱에 저장",
        "갤러리에 저장",
        "사진 앱에 추가",
        "URL.createObjectURL",
        "revokeObjectURL",
    ]
    assert _missing(js, required) == []
    # 아이폰은 <a download> 가 사진 앱이 아닌 "파일" 앱으로 가고 홈 화면 앱에선 동작하지 않는다.
    ios_branch = js.split("function onPrimary", 1)[1].split("downloadBlob(file", 1)[0]
    assert "if (IS_IOS)" in ios_branch and "return;" in ios_branch
    # 핵심: 공유는 클릭 핸들러의 첫 동작이어야 한다(앞에 await 가 있으면 탭 효력이 끝난다).
    for fn in ("function onPrimary", "function shareFile"):
        body = js.split(fn, 1)[1].split("\n    }\n", 1)[0]
        assert "await" not in body, fn
    assert "IS_INAPP" in js and "InvalidStateError" in js
    # data: 주소는 크롬 2MB 한도에 걸린다 — 시트는 blob 주소만 쓴다.
    assert "toDataURL" not in js
    assert _present(js, ["jQuery", "innerHTML", ".style."]) == []
    assert len(js.splitlines()) < 300


def test_image_export_js_finds_target_by_marker_not_hidden_table():
    js = _read(IMAGE_EXPORT_JS)
    assert "clonedDoc.querySelector('.measurement-table')" not in js


def test_mobile_glance_js_contract():
    js = _read(GLANCE_JS)
    required = [
        "__FOMS_MEAS_GLANCE_BOUND",
        "/measurement-visit",
        "data-meas-visit-toggle",
        "aria-pressed",
        "data.success",
        "foms:meas-glance:visit",
        "넘김 ",
        "data-meas-glance-handed",
        "data-meas-glance-tab-count",
        "체크를 저장하지 못했어요. 다시 눌러 주세요",
    ]
    assert _missing(js, required) == []


def test_mobile_glance_js_forbidden_and_size():
    js = _read(GLANCE_JS)
    # X-CSRF: csrf_bootstrap.html 전역 fetch 래퍼가 붙인다.
    assert _present(js, ["X-CSRF", "jQuery", "다음 방문"]) == []
    assert len(js.splitlines()) < 300


def test_measurement_entry_pin_and_chain_order():
    entry = _read(ENTRY_JS)
    assert "MEAS_JS_V = '20260923g'" in entry
    assert "measurement/image-export.js" in entry
    assert "measurement/mobile-glance.js" in entry
    assert "measurement/image-save-sheet.js" in entry
    assert entry.index("measurement/image-save-sheet.js") < entry.index("measurement/image-export.js")
    assert entry.index("measurement/image-export.js") < entry.index("measurement/mobile-glance.js")
    # 통합 화면: 체크 → 탭 → 시트 순(시트의 딥링크가 탭 모듈의 reveal 을 쓴다).
    assert entry.index("measurement/mobile-glance.js?") < entry.index("measurement/mobile-glance-tabs.js")
    assert entry.index("measurement/mobile-glance-tabs.js") < entry.index("measurement/mobile-glance-sheet.js")


def test_dashboard_scripts_pin_and_single_script():
    scripts = _read(DASHBOARD_SCRIPTS)
    assert "measurement_js_v = '20260923g'" in scripts
    assert scripts.count("<script src") == 1


# ------------------------------------------------------------ E. HTTP 렌더

def _login(client, *, username: str, role: str, team: str) -> User:
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


def _prepare(client, monkeypatch, *, username="meas_glance_admin", role="ADMIN", team="CS") -> str:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: FAKE_TODAY)
    user = _login(client, username=username, role=role, team=team)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    return FAKE_TODAY.strftime("%Y-%m-%d")


def _add_order(today: str, *, customer: str, manager: str, phone: str | None,
               visited: bool = False, time: str | None = None) -> int:
    manager_party = {"name": manager}
    if phone:
        manager_party["phone"] = phone
    sd: dict = {
        "parties": {"manager": manager_party},
        "items": [{"product_name": "붙박이장", "quantity": 1}],
    }
    if visited:
        sd["measurement_visits"] = {
            today: {"at": "2026-04-08T10:00:00+09:00", "by_user_id": 1, "by_name": manager},
        }
    if time:
        sd["schedule"] = {"measurement": {"date": today, "time": time}}
    order = Order(
        received_date=today,
        customer_name=customer,
        phone="010-9999-0000",
        address="서울 강남구",
        product="붙박이장",
        status="MEASURE",
        manager_name=manager,
        is_erp_order=True,
        structured_data=sd,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderScheduleDate(
        order_id=order.id, kind="measurement", date=today, source="beta_schedule",
    ))
    db_session.commit()
    return order.id


def _seed_three(today: str) -> dict[str, int]:
    return {
        "choi_done": _add_order(today, customer="글랜스고객A", manager="최진호",
                                phone="010-1234-5678", visited=True),
        "choi_open": _add_order(today, customer="글랜스고객B", manager="최진호",
                                phone="010-1234-5678", time="10:00"),
        "kim": _add_order(today, customer="글랜스고객C", manager="김도윤", phone=None),
    }


def _get(client, url: str = "/erp/measurement") -> str:
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _glance(body: str) -> str:
    start = body.index('<section class="foms-meas-glance ')
    end = body.index("</section>", start)
    return body[start:end + len("</section>")]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _check_tags(glance: str) -> list[str]:
    return re.findall(r'<button[^>]*class="foms-meas-glance__check"[^>]*>', glance)


def _group_chunks(glance: str) -> list[str]:
    starts = [m.start() for m in re.finditer(r"data-meas-glance-grp(?![-\w])", glance)]
    return [glance[s:e] for s, e in zip(starts, starts[1:] + [len(glance)])]


def test_glance_renders_checklist_grouped_by_manager(client, monkeypatch):
    today = _prepare(client, monkeypatch)
    ids = _seed_three(today)

    body = _get(client)
    glance = _glance(body)
    text = _text(glance)

    assert "3곳 · 실측 1 · 넘김 0" in text
    assert "실측 1/2" in text
    assert "실측 0/1" in text
    assert 'value="1" max="2"' in glance

    assert glance.count('aria-pressed="true"') == 1
    assert glance.count('aria-pressed="false"') == 2

    # 담당 이름은 접기 단추, 전화는 오른쪽 둥근 버튼(tel:) 하나
    assert glance.count('href="tel:01012345678"') == 1
    assert re.search(r'class="foms-meas-glance__call" href="tel:01012345678"', glance)
    assert 'class="foms-meas-glance__mgr"' not in glance
    # 전화 없는 담당자는 텍스트
    assert re.search(r'foms-meas-glance__mgr-text[^>]*>\s*김도윤', glance)

    assert f'data-meas-visit-date="{today}"' in glance
    checks = _check_tags(glance)
    assert len(checks) == 3
    assert [t for t in checks if " disabled" in t] == [], "ADMIN 은 체크 버튼이 눌려야 한다"

    for oid in ids.values():
        assert f'href="#meas-card-{oid}"' in glance
    assert "data-daypart=" in glance

    # 행 순서 그대로 담당자별 묶음: 최진호 2행이 한 묶음 안에 연속
    chunks = _group_chunks(glance)
    assert len(chunks) == 2
    choi = [c for c in chunks if "최진호" in c]
    assert len(choi) == 1
    assert f'data-meas-glance-go="{ids["choi_done"]}"' in choi[0]
    assert f'data-meas-glance-go="{ids["choi_open"]}"' in choi[0]
    assert f'data-meas-glance-go="{ids["kim"]}"' not in choi[0]

    # 글랜스 밖(본문 전체)
    for oid in ids.values():
        assert body.count(f'id="meas-card-{oid}"') == 1
    assert "foms-v2dh-hero" not in body
    # 예전 요약 줄은 통합 머리 숫자와 겹쳐 뺐다(목업 기준, 원장 B2).
    assert 'class="foms-visit-summary"' not in body


def test_glance_check_disabled_without_erp_edit(client, monkeypatch):
    """STAFF·DRAWING 은 체크 API 정책(ERP_EDIT)이 거부 → 체크 버튼 전부 disabled.

    CONSTRUCTION 팀은 before_request 가드(foms/platform/http.py _erp_construction_team_restrict)가
    /erp/measurement 를 출고 대시보드로 302 보내 화면 자체를 못 연다. 그래서 편집 권한이 없고
    화면은 여는 DRAWING 팀으로 판정한다.
    """
    today = _prepare(client, monkeypatch, username="meas_glance_drw", role="STAFF", team="DRAWING")
    _seed_three(today)

    glance = _glance(_get(client))
    checks = _check_tags(glance)
    assert len(checks) == 3
    assert all(" disabled" in t for t in checks)


def test_glance_check_enable_follows_erp_edit_policy_not_can_edit_erp(client, monkeypatch):
    """버튼 활성은 API 와 같은 ERP_EDIT 정책을 따른다: STAFF·SALES 는 켜지고 날짜 표식이 실린다."""
    today = _prepare(client, monkeypatch, username="meas_glance_sales", role="STAFF", team="SALES")
    _seed_three(today)

    glance = _glance(_get(client))
    assert f'data-meas-glance-date="{today}"' in glance
    checks = _check_tags(glance)
    assert len(checks) == 3
    assert not any(" disabled" in t for t in checks)


def test_glance_check_disabled_for_viewer(client, monkeypatch):
    """VIEWER 는 체크 API 가 403 이므로 버튼도 disabled(누르면 403 나는 버튼을 켜 두지 않는다)."""
    today = _prepare(client, monkeypatch, username="meas_glance_viewer", role="VIEWER", team="SALES")
    _seed_three(today)

    resp = client.get("/erp/measurement")
    if resp.status_code != 200:
        return  # 화면 자체를 못 여는 역할이면 판정 대상이 아니다.
    glance = _glance(resp.get_data(as_text=True))
    checks = _check_tags(glance)
    assert checks
    assert all(" disabled" in t for t in checks)


def test_glance_group_call_link_uses_first_row_with_phone(client, monkeypatch):
    """묶음 첫 주문에 담당자 번호가 없어도, 같은 묶음 다른 주문의 번호로 이름·전화 버튼이 tel: 링크가 된다."""
    today = _prepare(client, monkeypatch)
    _add_order(today, customer="번호없음고객", manager="박실측", phone=None)
    _add_order(today, customer="번호있음고객", manager="박실측", phone="010-7777-8888")

    glance = _glance(_get(client))
    assert 'class="foms-meas-glance__call" href="tel:01077778888"' in glance
    assert glance.count('href="tel:01077778888"') == 1


def test_glance_check_disabled_in_range_mode(client, monkeypatch):
    """기간 모드는 selected_date 를 검증하지 않으므로 체크 날짜를 비우고 전부 disabled."""
    today = _prepare(client, monkeypatch)
    _seed_three(today)

    glance = _glance(_get(client, f"/erp/measurement?date_from={today}&date_to={today}"))
    assert 'data-meas-visit-date=""' in glance
    assert f'data-meas-visit-date="{today}"' not in glance
    checks = _check_tags(glance)
    assert checks
    assert all(" disabled" in t for t in checks)
    assert 'aria-pressed="true"' not in glance


def test_glance_absent_when_no_orders(client, monkeypatch):
    _prepare(client, monkeypatch)

    body = _get(client)
    assert "data-meas-glance" not in body
    assert "foms-v2dh-status" in body
