"""생산 첫 화면 탭 "바뀐 것" — 목업 안 4 받은함대로 채움(사용자 11-21): 줄마다 '누가 · 언제', 머리 숫자,
확인한 것(흐린 장 + "<이름> 확인 M/D HH:MM"), 더 보기, 찾기 탭 바뀐 줄의 '누가 · 언제'.

이름은 모두 지어낸 가짜다. 시각은 서버 시계가 아니라 넣어 준 ``now`` 로 재거나(경계 시험), 날짜가 바뀌어도 같은 글이 되는
'N분 전' 만 단언한다(CI 는 UTC — 'N시간 전' · '어제' 는 KST 자정 근처에서 갈린다).
"""

from __future__ import annotations

import datetime
import re
from types import SimpleNamespace

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production_home_changes import (
    DONE_FILL,
    DONE_MIN,
    ack_when_label,
    change_when_label,
    production_home_changes_view,
)
from models import Order, OrderEvent, ProductionRun, User

HOME = "/erp/production/home"
UTC = datetime.datetime


def _user(username: str, name: str, team: str | None, role: str = "STAFF") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team, name=name, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(stage: str, name: str, day_offset: int = 2, *, run: bool = False, history: list | None = None) -> Order:
    day = (get_today_kst() + datetime.timedelta(days=day_offset)).isoformat()
    sd = {
        "workflow": {"stage": stage},
        "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
        "site": {"address_full": f"{name} 사는 곳"},
        "schedule": {"construction": {"date": day}},
        "items": [{"product_name": "거실장", "spec_width": "3100", "quantity": 1, "unit_price": 1234000}],
        "pricing": {"total": 1234000, "deposit": 300000},
    }
    if history:
        sd["drawing_transfer_history"] = history
    order = Order(
        received_date=get_today_kst().isoformat(), customer_name=name, phone="010-0000-0000", address=f"{name} 사는 곳",
        product="거실장", manager_name="관리", status=stage, is_erp_order=True, structured_data=sd, erp_stage_code=stage,
        erp_construction_date=day, erp_stage_updated_at=now_utc_naive() - datetime.timedelta(days=20),
    )
    db_session.add(order)
    db_session.commit()
    # 생산 진입(D22 바닥선) — 이 뒤의 변경만 센다
    db_session.add(OrderEvent(order_id=order.id, event_type="CUSTOMER_CONFIRMED", payload={"from": "CONFIRM", "to": stage},
                              created_at=now_utc_naive() - datetime.timedelta(days=15)))
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return order


def _date_changed(order: Order, ago: datetime.timedelta, by: User | None) -> None:
    db_session.add(OrderEvent(order_id=order.id, event_type="CONSTRUCTION_DATE_CHANGED",
                              payload={"from": "2026-11-10", "to": "2026-11-12"},
                              created_by_user_id=by.id if by else None, created_at=now_utc_naive() - ago))
    db_session.commit()


def _ack(order: Order, user: User, ago: datetime.timedelta) -> datetime.datetime:
    at = now_utc_naive() - ago
    db_session.add(OrderEvent(order_id=order.id, event_type="PRODUCTION_CHANGE_ACK", payload={"source": "test"},
                              created_by_user_id=user.id, created_at=at))
    db_session.commit()
    return at


def _drawing_entry(action: str, ago: datetime.timedelta, by: User | None, note: str, *, name_only: str = "") -> dict:
    at = (now_utc_naive() - ago).strftime("%Y-%m-%d %H:%M:%S")
    entry = {"action": action, "note": note, "files": [], "files_count": 0,
             "by_user_id": by.id if by else None, "by_user_name": by.name if by else name_only}
    entry["transferred_at" if action == "TRANSFER" else "at"] = at
    return entry


def _cards(html: str, attr: str) -> dict[str, str]:
    """``data-foms-home-inbox`` / ``data-foms-home-done`` 장 → 이름 열쇠 · 장 HTML."""
    out = {}
    for chunk in html.split(f'{attr}="')[1:]:
        body = re.split(r'<div class="fph-al[ "]|<p class="fph-inbox__more"', chunk)[0]
        name = re.search(r'fph-al__name">([^<]+) <small>', body).group(1).strip()
        out[name] = body
    return out


# ── 언제: 서버 KST 상대 시간 경계 ──

def test_언제_글은_KST_기준_방금_분_시간_어제_날짜() -> None:
    now = UTC(2026, 11, 21, 5, 0, 0)  # KST 11/21 14:00
    assert change_when_label(now, now) == "방금"
    assert change_when_label(now - datetime.timedelta(seconds=59), now) == "방금"
    assert change_when_label(now + datetime.timedelta(seconds=30), now) == "방금"  # 시계가 조금 앞선 기록
    assert change_when_label(now - datetime.timedelta(seconds=60), now) == "1분 전"
    assert change_when_label(now - datetime.timedelta(minutes=59, seconds=59), now) == "59분 전"
    assert change_when_label(now - datetime.timedelta(hours=1), now) == "1시간 전"
    assert change_when_label(UTC(2026, 11, 20, 15, 0), now) == "14시간 전"  # KST 11/21 00:00 = 오늘 첫 시각
    assert change_when_label(UTC(2026, 11, 20, 14, 59), now) == "어제 23:59"  # KST 11/20 23:59
    assert change_when_label(UTC(2026, 11, 19, 15, 0), now) == "어제 00:00"
    assert change_when_label(UTC(2026, 11, 19, 14, 59), now) == "11/19"  # KST 11/19 23:59 = 그저께
    assert change_when_label(None, now) == "" and change_when_label("2026-11-21", now) == ""


def test_언제_글은_UTC_날짜가_아니라_KST_날짜로_가른다() -> None:
    """KST 자정 직후(UTC 로는 아직 전날): 90분 전 기록은 KST 로 어제라 '어제 HH:MM' — UTC 날짜로 가르면 'N시간 전'이 된다."""
    now = UTC(2026, 11, 20, 15, 30)  # KST 11/21 00:30
    assert change_when_label(UTC(2026, 11, 20, 14, 0), now) == "어제 23:00"
    assert change_when_label(UTC(2026, 11, 20, 15, 0), now) == "30분 전"
    now = UTC(2026, 11, 21, 14, 30)  # KST 11/21 23:30 (UTC 로는 같은 날 14:30)
    assert change_when_label(UTC(2026, 11, 20, 16, 0), now) == "22시간 전"  # KST 11/21 01:00 = 오늘


def test_확인_시각_글은_KST_월_일_시_분() -> None:
    assert ack_when_label(UTC(2026, 11, 3, 5, 10)) == "11/3 14:10"  # 목업 "이철호 확인 11/3 14:10"
    assert ack_when_label(UTC(2026, 12, 31, 15, 5)) == "1/1 00:05"
    assert ack_when_label(None) == ""


# ── 받은함: 누가 · 언제 · 머리 숫자 · 생산 단계만 ──

def test_받은함_줄마다_누가_언제와_머리_숫자(client) -> None:
    viewer = _user("chg_viewer", "가생산", "PRODUCTION")
    sales = _user("chg_sales", "나영업", "SALES")
    drawer = _user("chg_drawer", "다도면", "DRAWING")
    cs = _user("chg_cs", "라상담", "CS")
    _login(client, viewer)
    a = _order("PRODUCTION", "영업바꿈", run=True)
    _date_changed(a, datetime.timedelta(minutes=10), sales)
    b = _order("PRODUCTION", "도면바꿈", history=[_drawing_entry("TRANSFER", datetime.timedelta(minutes=5), drawer, "측면 1장 추가")])
    c = _order("PRODUCTION", "상담요청", history=[_drawing_entry("REQUEST_REVISION", datetime.timedelta(minutes=20), cs, "거실장만 만들어요")])
    d = _order("PRODUCTION", "누군지모름")
    _date_changed(d, datetime.timedelta(minutes=30), None)
    e = _order("PRODUCTION", "이름만", history=[_drawing_entry("TRANSFER", datetime.timedelta(minutes=40), None, "", name_only="마외부")])
    # 대조군(D20): 도면 기다림 · 제작 완료 주문의 변경은 받은함 · 숫자에 안 든다
    _date_changed(_order("DRAWING", "도면단계"), datetime.timedelta(minutes=10), sales)
    _date_changed(_order("CONSTRUCTION", "제작완료"), datetime.timedelta(minutes=10), sales)

    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert '<h2 class="fph-inbox__h">바뀐 것 <b>5</b></h2>' in html
    assert '>바뀐 것 <small class="is-hot">5</small></a>' in html  # 머리 숫자 = 탭 숫자
    cards = _cards(html, "data-foms-home-inbox")
    assert set(cards) == {"영업바꿈", "도면바꿈", "상담요청", "누군지모름", "이름만"}
    assert '<span class="fph-al__m">영업 나영업 · 10분 전</span>' in cards["영업바꿈"]
    assert '<strong>11/12</strong>' in cards["영업바꿈"]
    assert '<span class="fph-al__m">도면팀 다도면 · 5분 전 · 측면 1장 추가</span>' in cards["도면바꿈"]
    assert '<span class="fph-al__m">CS 라상담 · 20분 전 · 거실장만 만들어요</span>' in cards["상담요청"]
    assert '<span class="fph-al__m">30분 전</span>' in cards["누군지모름"]  # 기록에 사람이 없으면 '언제'만(지어내지 않는다)
    assert '<span class="fph-al__m">마외부 · 40분 전</span>' in cards["이름만"]
    assert "data-foms-home-done" not in html and "fph-inbox__more" not in html
    assert html.count('data-kanban-action="change-ack"') == 5  # [확인했어요] 계약 그대로
    # 금액 없음(D7)
    assert "1,234,000" not in html and "1234000" not in html and "300,000" not in html
    for o in (a, b, c):
        assert f"#{o.id}</small>" in html


def test_한_주문에_여러_변경이면_최근_것부터(client) -> None:
    viewer = _user("chg_multi_viewer", "가생산", "PRODUCTION")
    sales = _user("chg_multi_sales", "나영업", "SALES")
    drawer = _user("chg_multi_drawer", "다도면", "DRAWING")
    _login(client, viewer)
    o = _order("PRODUCTION", "둘다바뀜", history=[_drawing_entry("TRANSFER", datetime.timedelta(minutes=3), drawer, "문짝")])
    _date_changed(o, datetime.timedelta(minutes=25), sales)
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    card = _cards(html, "data-foms-home-inbox")["둘다바뀜"]
    assert card.index("도면팀 다도면 · 3분 전") < card.index("영업 나영업 · 25분 전")
    # 찾기 탭 바뀐 줄 = 가장 최근 변경 + 누가 · 언제 + 그 외 n건(목업 안 1 "… · 영업 이서연 · 2시간 전")
    found = client.get(HOME + "?tab=all").get_data(as_text=True)
    assert '<span class="foms-prod-home__chg">도면 재전달 문짝 · 도면팀 다도면 · 3분 전 · 그 외 1건</span>' in found
    # 날짜 탭 줄은 누가 · 언제 없이 그대로(짧은 줄)
    date = client.get(HOME + f"?day={(get_today_kst() + datetime.timedelta(days=2)).isoformat()}").get_data(as_text=True)
    assert "<em>도면 재전달 문짝 · 그 외 1건</em>" in date and "다도면" not in date


# ── 확인한 것: 내 확인 · 정렬 · 개수 · 더 보기 ──

def test_확인한_것은_내가_확인한_주문만_흐리게_확인_시각_늦은_순(client) -> None:
    viewer = _user("chg_done_viewer", "가생산", "PRODUCTION")
    mate = _user("chg_done_mate", "바동료", "PRODUCTION")
    sales = _user("chg_done_sales", "나영업", "SALES")
    _login(client, viewer)
    acked = {}
    for i, hours in enumerate((30, 5, 50)):
        o = _order("PRODUCTION", f"확인{i}")
        _date_changed(o, datetime.timedelta(hours=hours + 2), sales)
        acked[f"확인{i}"] = _ack(o, viewer, datetime.timedelta(hours=hours))
    other = _order("PRODUCTION", "동료만확인")  # 동료가 확인해도 내 받은함엔 남는다(사람마다 확인)
    _date_changed(other, datetime.timedelta(hours=3), sales)
    _ack(other, mate, datetime.timedelta(hours=1))
    later = _order("PRODUCTION", "확인뒤또바뀜")  # 내가 확인한 뒤 또 바뀌면 미확인 장으로(확인한 것 아님)
    _date_changed(later, datetime.timedelta(hours=9), sales)
    _ack(later, viewer, datetime.timedelta(hours=8))
    _date_changed(later, datetime.timedelta(minutes=15), sales)
    done_wait = _order("DRAWING", "도면단계확인")  # 대조군(D20): 생산 단계 아닌 주문은 확인한 것에도 없다
    _date_changed(done_wait, datetime.timedelta(hours=3), sales)
    _ack(done_wait, viewer, datetime.timedelta(hours=1))

    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert set(_cards(html, "data-foms-home-inbox")) == {"동료만확인", "확인뒤또바뀜"}
    done = _cards(html, "data-foms-home-done")
    assert list(done) == ["확인1", "확인0", "확인2"]  # 확인 시각 늦은 순
    for name, at in acked.items():
        assert f'<div class="fph-al__ok">가생산 확인<br>{ack_when_label(at)}</div>' in done[name]
        assert 'data-kanban-action="change-ack"' not in done[name]
        assert "영업 나영업 · " in done[name]
    assert re.search(r'<div class="fph-al is-done" data-foms-home-done="\d+">', html)
    assert "fph-inbox__more" not in html  # 다 보인다(받은함 2 + 3 ≤ 채움 8)


def _seed_done(viewer: User, sales: User, n: int, prefix: str) -> None:
    for i in range(n):
        o = _order("PRODUCTION", f"{prefix}{i:02d}")
        _date_changed(o, datetime.timedelta(hours=i + 3), sales)
        _ack(o, viewer, datetime.timedelta(hours=i + 1))


def test_확인한_것은_화면을_채울_만큼만_보이고_나머지는_더_보기(client) -> None:
    viewer = _user("chg_more_viewer", "가생산", "PRODUCTION")
    sales = _user("chg_more_sales", "나영업", "SALES")
    _login(client, viewer)
    _seed_done(viewer, sales, 12, "끝")
    for i in range(3):
        _date_changed(_order("PRODUCTION", f"새{i}"), datetime.timedelta(minutes=5 + i), sales)

    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    keep = DONE_FILL - 3
    done = list(_cards(html, "data-foms-home-done"))
    assert done == [f"끝{i:02d}" for i in range(keep)]  # 가장 최근 확인부터 5장
    more = re.search(r'<p class="fph-inbox__more"><a href="([^"]+)">확인한 것 (\d+)건 더 보기</a></p>', html)
    assert more and more.group(2) == str(12 - keep)
    assert more.group(1) == HOME + "?tab=changes&amp;done=all"  # 주소는 home_href 한 곳에서
    # 더 보기 = 같은 탭 다시 받기: 12장 모두, 링크 없음, 받은함 · 숫자는 그대로
    full = client.get(more.group(1).replace("&amp;", "&")).get_data(as_text=True)
    assert list(_cards(full, "data-foms-home-done")) == [f"끝{i:02d}" for i in range(12)]
    assert "fph-inbox__more" not in full and '바뀐 것 <b>3</b>' in full


def test_받은함이_길어도_확인한_것은_적어도_두_장(client) -> None:
    viewer = _user("chg_min_viewer", "가생산", "PRODUCTION")
    sales = _user("chg_min_sales", "나영업", "SALES")
    _login(client, viewer)
    _seed_done(viewer, sales, 4, "끝")
    for i in range(DONE_FILL + 1):
        _date_changed(_order("PRODUCTION", f"새{i:02d}"), datetime.timedelta(minutes=5), sales)
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert len(_cards(html, "data-foms-home-inbox")) == DONE_FILL + 1
    assert list(_cards(html, "data-foms-home-done")) == ["끝00", "끝01"][:DONE_MIN]
    assert "확인한 것 2건 더 보기" in html


def test_바뀐_것도_확인한_것도_없으면_빈_글과_초록_0(client) -> None:
    viewer = _user("chg_empty_viewer", "가생산", "PRODUCTION")
    _login(client, viewer)
    _order("PRODUCTION", "조용한주문", run=True)
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    assert '<h2 class="fph-inbox__h">바뀐 것 <b class="is-zero">0</b></h2>' in html
    assert "새로 바뀐 것이 없어요." in html and "data-foms-home-done" not in html


def test_보기_모델_순수_규칙() -> None:
    """``production_home_changes_view`` — 쿼리 없이(사람 id 없음) 개수 규칙 · 묘비 · 원래 행 불변."""
    at = UTC(2026, 11, 20, 1, 0)
    rows = [
        {"id": i, "customer_name": f"끝{i}", "home_alerts": [], "home_view": "prod",
         "home_done": [{"kind": "drawing", "label": "도면 재전달", "detail": "", "at": at, "by_id": None, "by_name": ""}],
         "home_acked_at": at + datetime.timedelta(minutes=i)} for i in range(10)
    ]
    rows.append({"id": 99, "customer_name": "새", "home_view": "prod", "home_done": [], "home_acked_at": None,
                 "home_alerts": [{"kind": "construction_date", "label": "시공일 변경", "detail": "", "from_md": "11/1",
                                  "to_md": "11/3", "at": at, "by_id": None, "by_name": "사외부"}]})
    view = production_home_changes_view(None, None, rows, [{"id": 7, "customer_name": "취소", "deleted_md": "11/20"}],
                                        now=UTC(2026, 11, 21, 5, 0))
    assert view["count"] == 2 and [it["kind"] for it in view["inbox"]] == ["change", "cancelled"]
    assert [it["id"] for it in view["done"]] == [9, 8, 7, 6, 5, 4] and view["done_more"] == 4
    assert view["inbox"][0]["alerts"][0]["m"] == "사외부 · 어제 10:00"
    assert view["inbox"][1]["alerts"][0]["m"] == "만들고 있었다면 멈춰요"  # 묘비: 사람 · 시각 기록 없음 → 안내만
    assert "m" not in rows[10]["home_alerts"][0]  # 원래 행 사전은 건드리지 않는다
    assert view["done"][0]["ack_by"] == "" and view["done"][0]["ack_when"] == "11/20 10:09"


# ── 쿼리 수: 사람 이름 읽기 1회, 주문이 늘어도 같다 ──

def _count(fn):
    box = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, box["n"]


# 실측(2026-11-21, SQLite 레인): 날짜 탭 9 (그대로) · 바뀐 것 탭 10 · 찾기 탭 10 — 두 탭은 사람 이름 · 팀 읽기
# (``User.id IN``) 1회가 더해진다. 주문 4 → 12건에도 같다. 상한 = 실측 + 30%.
CHANGES_TAB_QUERY_CAP = 13


def test_바뀐_것_탭과_찾기_탭_쿼리는_사람_읽기_한_번만_더한다(client) -> None:
    viewer = _user("chg_qc_viewer", "가생산", "PRODUCTION")
    _login(client, viewer)
    # 요청이 끝나면 세션이 닫혀 ORM 객체 값을 다시 못 읽는다 — 두 번째 씨앗은 id · 이름만 쓴다
    viewer, sales, drawer = (SimpleNamespace(id=u.id, name=u.name) for u in (
        viewer, _user("chg_qc_sales", "나영업", "SALES"), _user("chg_qc_drawer", "다도면", "DRAWING")))

    def seed(prefix: str, n: int) -> None:
        for i in range(n):
            o = _order("PRODUCTION", f"{prefix}{i}", run=bool(i % 2),
                       history=[_drawing_entry("TRANSFER", datetime.timedelta(minutes=7), drawer, "")])
            _date_changed(o, datetime.timedelta(minutes=9), sales)
            if i % 3 == 0:  # 일부는 확인한 것(변경 하나 더 · 내 확인)
                _ack(o, viewer, datetime.timedelta(minutes=1))

    seed("작", 4)
    assert client.get(HOME + "?tab=changes").status_code == 200  # warmup
    (_, q_date) = _count(lambda: client.get(HOME))
    resp, q_small = _count(lambda: client.get(HOME + "?tab=changes"))
    assert "도면팀 다도면" in resp.get_data(as_text=True)
    _, q_all_small = _count(lambda: client.get(HOME + "?tab=all"))
    seed("큰", 8)
    resp, q_big = _count(lambda: client.get(HOME + "?tab=changes"))
    assert resp.get_data(as_text=True).count("data-foms-home-inbox=") == 7  # 12건 중 확인한 5건 빼고
    _, q_all_big = _count(lambda: client.get(HOME + "?tab=all"))
    assert q_big == q_small and q_all_big == q_all_small, (q_small, q_big, q_all_small, q_all_big)
    assert q_small - q_date == 1 and q_all_small - q_date == 1, (q_date, q_small, q_all_small)
    assert q_big <= CHANGES_TAB_QUERY_CAP and q_all_big <= CHANGES_TAB_QUERY_CAP


# ── 바뀐 것 탭 자리(사용자 11-22 "빈 공간이 너무 많아. CSS 정렬 시켜") ──

ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parents[2]


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start: css.index("}", start)]


def test_바뀐_것_탭은_신문_단으로_빈틈_없이_채우고_단_수는_장_최소_너비가_정한다() -> None:
    """11-22 실측(1176×626, 가짜 주문 12 · 7 · 3 · 1 · 0장): 두 칸 격자 + 칸마다 제 키라 키 큰 장 옆이 줄마다 최대 96px 비었고,
    화면 크기 80% 는 장마다 글 끝 ~ 단추 사이가 평균 270 · 최대 336px 비었다. 사장님 선택 "빈틈 없이 채우기": 신문 단(multi-column) —
    장은 제 키 그대로 단을 위에서 아래로 채우고(구멍 0), 단 수는 장 최소 너비(column-width)가 정한다. 장 1 · 2장이면 단 수 = 장 수."""
    css = (ROOT_DIR / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    pc = (ROOT_DIR / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    page = _rule(css, ".fph-inbox--page")
    assert "display: block;" in page and "column-width: var(--fph-al-min);" in page and "column-gap: 10px;" in page
    assert "grid-template-columns" not in page and "align-items" not in page  # 옛 격자 · 키 맞춤 없음(장은 제 키)
    assert ".fph-inbox--page > .fph-al { break-inside: avoid; margin: 0 0 10px; }" in css  # 장은 단 사이에서 쪼개지지 않는다
    assert ".fph-inbox--page:has(> div.fph-al:only-of-type) { column-count: 1; }" in css  # 1장 = 전체 폭
    assert ".fph-inbox--page:has(> div.fph-al:nth-of-type(2):last-of-type) { column-count: 2; }" in css  # 2장 = 두 단까지
    wide = css.split("@media (min-width: 992px) {\n  .fph-panes")[1].split("\n}\n")[0]
    assert "fph-inbox" not in wide  # 옛 두 칸 → 한 칸 컨테이너 쿼리 없음
    tablet = re.search(r"--fph-al-min: calc\(([^;]+)\);", page).group(1)
    pc_min = re.search(r"\.foms-prod-home\.is-pc \.fph-inbox--page \{ --fph-al-min: calc\(([^;]+)\); \}", pc).group(1)

    def _px(expr: str, fs: float) -> float:  # 1rem = 16px × 글자 배율
        return eval(re.sub(r"(\d+(?:\.\d+)?)rem", rf"(\1*{16 * fs})", expr).replace("px", ""), {"max": max})  # noqa: S307

    def _cols(content_w: float, expr: str, fs: float) -> int:  # column-width: 단 수 = (너비 + 틈) ÷ (최소 너비 + 틈), 틈 10px
        return max(1, int((content_w + 10) // (_px(expr, fs) + 10)))

    # 실측 단 너비(CSS px, 좌우 여백 32 뺌): 태블릿 100% 1048 · 화면 크기 80% 1342 · PC 1440×900 1384 · 세로 800 은 992 아래(한 단 규칙)
    assert abs(_px(tablet, 1) - (2 + 28 + 12 + 128 + 16 * 16)) < 0.01
    assert _cols(1048, tablet, 1) == 2 and _cols(1342, tablet, 1) == 3 and _cols(1048, tablet, 1.2) == 2
    assert _cols(1048, tablet, 1.5) == 1 and _cols(1342, tablet, 1.5) == 2
    # PC(1440×900 단 1384 · 글자 150% 1372)는 시공일 칸이 더 있고 글 칸 10.5rem — 글자 100 ~ 150% 모두 두 단(한 단이면 장 안이 600px 넘게 빈다)
    assert abs(_px(pc_min, 1) - (58 + 8.5 * 16 + 128 + 10.5 * 16)) < 0.01
    assert _cols(1384, pc_min, 1) == 2 and _cols(1372, pc_min, 1.5) == 2 and _cols(1860, pc_min, 1) == 3
    # 머리 · 빈 글 · 더 보기는 모든 단을 가로지른다 · 빈 글은 머리 아래 한 줄(가운데 큰 상자 아님)
    assert (".fph-inbox--page > .fph-inbox__h, .fph-inbox--page > .fph-inbox__more, .fph-inbox--page > .foms-prod-home__empty "
            "{ column-span: all; }") in css
    assert ".fph-inbox--page > .foms-prod-home__empty { padding: 6px 4px; margin-bottom: 10px; text-align: left; }" in css
    assert ".fph-inbox--page .fph-al { background: var(--fph-surface); word-break: keep-all; overflow-wrap: anywhere; }" in css
    # 누르는 곳: 화면 크기 80% 에서도 실제 48px 이상
    btn = re.search(r"\.fph-al \.foms-prod-home__btn \{ min-width: 128px; min-height: (\d+)px; \}", css)
    more = re.search(r"\.fph-inbox__more a \{ min-height: (\d+)px;", css)
    assert btn and more and int(btn.group(1)) * 0.8 >= 48 and int(more.group(1)) * 0.8 >= 48
    # 세로 · 폰(992 아래)은 한 단(2장 규칙보다 강하게)
    phone = css[css.index("@media (max-width: 991.98px) {"):]
    assert (".fph-inbox--page, .fph-inbox--page:has(> div.fph-al:nth-of-type(2):last-of-type) "
            "{ column-count: 1; padding: 12px 12px 90px; }") in phone


def test_바뀐_것_탭_장_마크업은_그대로다(client) -> None:
    """자리만 CSS 로 바꿨다 — 장 · [확인했어요] · 확인한 것 · 빈 글 마크업과 순서(받은함 → 확인한 것 → 더 보기)는 그대로."""
    viewer = _user("chg_lay_viewer", "가생산", "PRODUCTION")
    sales = _user("chg_lay_sales", "나영업", "SALES")
    _login(client, viewer)
    _seed_done(viewer, sales, 9, "끝")
    _date_changed(_order("PRODUCTION", "새장", run=True), datetime.timedelta(minutes=5), sales)
    html = client.get(HOME + "?tab=changes").get_data(as_text=True)
    page = html[html.index('<div class="fph-inbox fph-inbox--page" aria-label="바뀐 것">'):]
    assert page.index('data-foms-home-inbox="') < page.index('data-foms-home-done="') < page.index('class="fph-inbox__more"')
    assert page.count('data-kanban-action="change-ack"') == 1 and 'style="' not in page.split("</section>")[0]
