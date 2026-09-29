# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 P2 나머지 — 이력 탭 쪽(2026-09-30 · 감사 원장 N-16·N-24·N-25·N-26·N-30·N-38·N-39)
계약과 자산 핀. 처리 탭·상세 쪽은 `_p2a`.

음성 대조군: 각 시나리오 안에 둔다(찾기 없음 · 추가결제 아님 · 데스크톱 원문 줄 등).
HEAD(P1, 00568f34c) 코드로 돌리면 이 파일이 빨갛다.
"""

from __future__ import annotations

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_workbench import _collected
from tests.services.integrations.test_naver_workbench_mobile import TEMPLATE, TRIAGE_PATH, _empty_strips, _rule
from tests.services.integrations.test_naver_workbench_mobile_p1 import _js
from tests.services.integrations.test_naver_workbench_mobile_p2a import _p2
from tests.services.integrations.test_naver_workbench_mobile_phase34 import _card, _history, _patch_ingest
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)


def _hist(client, **qs) -> str:
    return client.get(TRIAGE_PATH, query_string={"tab": "all", **qs}).get_data(as_text=True)


# --------------------------------------------------------------------------- #
# N-24 카드 누름 표시 · N-30 추가결제 수량
# --------------------------------------------------------------------------- #

def test_history_cards_say_open_in_work_tab_and_show_a_chevron(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-H1", product="이력 집", amount=100000, place_status="")
    body = _hist(client)
    assert '<span class="wb-dk">워크벤치</span><span class="wb-ph">처리 탭으로</span></a>' in body
    p2 = _p2()
    chevron = _rule(p2, "    .wb-hist tbody tr[data-find] .wb-hist-detail::before")
    assert 'content: "\\203A";' in chevron and "position: absolute;" in chevron
    link = _rule(p2, "    .wb-hist tbody tr[data-find] .wb-hist-open,\n    .wb-hist tbody tr.wb-hist--muted .wb-hist-open")
    assert "color: #4a55b8;" in link, "잠긴 카드도 6.2:1(예전 #9aa3af 2.46:1)"


def test_addon_payment_rows_fold_the_amount_like_quantity(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-AD", product="추가결제 상품", amount=3559500, place_status="")
    _collected(order_no="N-P2-NW", product="보통 상품", amount=100000, place_status="")
    real = naver_ingest._history_view

    def with_addon(db):
        view = real(db)
        for row in view["rows"]:
            if row["external_order_no"] == "N-P2-AD":
                row["relation"], row["relation_label"], row["quantity"] = "ADDON", "추가결제", 3564
            elif row["external_order_no"] == "N-P2-NW":
                row["quantity"] = 2
        return view

    monkeypatch.setattr(naver_ingest, "_history_view", with_addon)
    body = _hist(client)
    addon = body.split("n-p2-ad")[1].split("</tr>")[0]
    plain = body.split("n-p2-nw")[1].split("</tr>")[0]
    assert '<td class="wb-cmp__num wb-hist__qty--addon">3564</td>' in addon
    assert '<td class="wb-cmp__num">2</td>' in plain, "음성 대조군: 보통 상품 수량은 그대로"
    assert "    .wb-hist tbody tr[data-find] > td.wb-hist__qty--addon { display: none; }" in _p2()


# --------------------------------------------------------------------------- #
# N-25 결과 없음 · N-38 찾기 칸
# --------------------------------------------------------------------------- #

def test_empty_search_says_what_was_searched_and_how_to_clear(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    _collected(order_no="N-P2-E", product="있는 집", amount=100000, place_status="")
    body = _hist(client, q="와투와")
    none = body.split('<tr class="wb-hist__none">')[1].split("</tr>")[0]
    assert "‘와투와’(으)로 찾은 주문이 없어요" in none and "이름 · 전화 뒷자리 4개 · 주문번호로 찾아 보세요." in none
    assert 'class="wb-empty__go" href="/admin/naver-ingest/triage?tab=all">찾기 지우기</a>' in none
    assert "수집 이력이 없습니다" not in body, "찾기가 안 맞은 것을 수집 기록이 없다고 말하지 않는다"
    assert "찾은 주문 없음" in body, "찾기 칸 밑 고지(데스크톱)는 그대로"
    clear = body.split('class="wb-find__clear"')[1].split("</a>")[0]
    assert 'aria-label="찾기 지우기"' in clear and 'href="/admin/naver-ingest/triage?tab=all"' in clear
    assert 'value="와투와" enterkeyhint="search"' in body
    # 음성 대조군: 찾기가 없으면 지우기(×)가 없다. 이력이 아예 없을 때만 예전 문장.
    plain = _hist(client)
    assert 'class="wb-find__clear"' not in plain and "wb-empty--find" not in plain


def test_empty_history_without_search_keeps_the_old_sentence(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    body = _hist(client)
    assert '<tr class="wb-hist__none"><td colspan="8" class="wb-empty">수집 이력이 없습니다.</td></tr>' in body
    p2 = _p2()
    assert "    .wb-hist tbody tr.wb-hist__none,\n    .wb-hist tbody tr.wb-hist__none > td { display: block;" in p2
    assert "    .wb-filters:has(+ .table-responsive .wb-empty--find) .wb-find__note { display: none; }" in p2


# --------------------------------------------------------------------------- #
# N-26 이력 원본 = 전체 화면 읽기 전용 · 사람 말 날짜
# --------------------------------------------------------------------------- #

def test_history_detail_reads_human_time_and_opens_full_screen(client, workbench_on, monkeypatch):
    _empty_strips(monkeypatch)
    _login(client)
    link = _collected(order_no="N-P2-D", product="원본 집", amount=100000, place_status="")
    snap = dict(link.raw_snapshot)
    snap["order"] = {**snap["order"], "paymentDate": "2026-09-29T11:57:49.022+09:00"}
    link.raw_snapshot = snap
    from db import db_session
    db_session.commit()
    frag = client.get("/admin/naver-ingest/triage/detail", query_string={"link_id": link.id}).get_data(as_text=True)
    assert ('<span class="wb-dk">2026-09-29T11:57:49.022+09:00</span><span class="wb-ph">09-29 11:57</span>'
            in frag), "데스크톱 원문은 그대로, 폰은 MM-DD HH:mm"
    shell = _hist(client)
    assert '<span class="wb-dk">네이버 원본 — </span><span class="wb-ph">네이버 값 · 읽기 전용 — </span>' in shell
    p2 = _p2()
    dialog = _rule(p2, "    #wb-modal-detail .modal-dialog")
    assert "max-width: none;" in dialog and "margin: 0;" in dialog
    assert "border-radius: 0;" in _rule(p2, "    #wb-modal-detail .modal-content")
    assert "    #wb-modal-detail .modal-body { overflow-x: hidden; }" in p2
    assert "#wb-detail-body .wb-cmp:has(thead .wb-cmp__num) tr {" in p2, "상품 표도 세로 카드로"


# --------------------------------------------------------------------------- #
# N-16 · N-39 관리 시트·상태 카드 말
# --------------------------------------------------------------------------- #

def test_admin_sheet_speaks_field_words_on_phone_only(client, workbench_on, monkeypatch):
    body = _history(client, monkeypatch)
    section = body[body.index('id="wb-ingest-status"'):body.index("</section>", body.index('id="wb-ingest-status"'))]
    assert '<div class="wb-ingest__k wb-ingest__phone">받아온 시각</div>' in section
    assert "9월 29일 08:25:57까지 받았어요" in section and "‘받아온 시각’은 바뀌지 않아요" in section
    for desk, phone in (("커머스API 인증 만료일", "네이버 연결 만료일"), ("지금 수집", "지금 받아오기"),
                        ("과거 주문 소급 수집", "지난 주문 가져오기"), ("과거 긁어오기", "지난 주문 가져오기")):
        assert f'<span class="wb-dk">{desk}</span><span class="wb-ph">{phone}</span>' in section, desk
    js = _js()
    assert "'‘받아온 시각’은 바뀌지 않아요.'" in js and "go: '지금 받아오기'" in js
    assert "'과거 주문 ' + days + '일치를 가져올까요?'" in js, "P0 확인 시트 제목은 그대로"


def test_status_card_says_expiry_date_and_title_time_is_not_repeated(client, workbench_on, monkeypatch):
    card = _card(_history(client, monkeypatch, expires_on=None, days_left=None))
    assert '인증 만료일 <span class="wb-dk">미등록</span><span class="wb-ph">미입력</span>' in card
    _patch_ingest(monkeypatch)
    known = _card(client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True))
    assert "인증 만료 2027-02-23" in known, "음성 대조군: 날짜가 있으면 예전 꼴"
    assert "    .naver-workbench:has(.wb-icard) .wb-bar__sub { display: none; }" in _p2()


# --------------------------------------------------------------------------- #
# 자산 핀
# --------------------------------------------------------------------------- #

def test_workbench_pins_moved_to_20260930g():
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert markup.count("?v=20260930g") == 2
    assert "?v=20260930b" not in markup and "?v=20260930a" not in markup
    assert 'style="' not in markup.split("{% block content %}")[1].split("{% endblock %}")[0].replace(
        'style="{{', ""), "인라인 스타일 금지"
