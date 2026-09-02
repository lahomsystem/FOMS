"""마법사 초안(Order 행 없음) 알림톡 sd 발송 계층 테스트 (WIZ-SEND-01 T1).

DB 를 전혀 쓰지 않는 계층이라 픽스처는 env·monkeypatch 뿐이다
(``send_alimtalk_for_sd`` 는 이력·OrderEvent 를 쓰지 않는 것이 계약).
"""
import copy
import re

import pytest

from foms.services import kakao_alimtalk as ka

_MEASURE_SD = {
    "parties": {
        "customer": {"name": "임다슬", "phone": "010-2473-6730"},
        "orderer": {"name": "라홈시스템"},
    },
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
    "items": [{"product_name": "무몰딩 여닫이"}],
}


def _sd(**overrides) -> dict:
    """실측 예약이 잡힌 유효 sd 사본(부분 덮어쓰기 지원)."""
    sd = copy.deepcopy(_MEASURE_SD)
    sd.update(overrides)
    return sd


@pytest.fixture
def solapi_env(monkeypatch):
    """LAHOM 브랜드만 발송 가능한 환경(기존 발송 테스트와 같은 조합)."""
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")
    monkeypatch.delenv("SOLAPI_PF_ID_HAUD", raising=False)
    monkeypatch.delenv("SOLAPI_TEMPLATE_MEASURE_ID_HAUD", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_LAHOM", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_HAUD", raising=False)


@pytest.fixture
def dispatch_never(monkeypatch):
    """미자격이면 ``_dispatch`` 가 절대 불려서는 안 된다."""
    def _boom(sd):
        raise AssertionError("미자격인데 _dispatch 가 호출됐다")

    monkeypatch.setattr(ka, "_dispatch", _boom)


# --------------------------------------------------------------------------
# draft_ineligible_reason — 사유 코드
# --------------------------------------------------------------------------


def test_draft_reason_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("SOLAPI_API_KEY", raising=False)
    monkeypatch.delenv("SOLAPI_API_SECRET", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_LAHOM", raising=False)
    assert ka.draft_ineligible_reason(_sd()) == "not_configured"


def test_draft_reason_not_eligible_without_measure_date(solapi_env):
    sd = _sd(schedule={"measurement": {"date": "", "time": "3시"}})
    assert ka.draft_ineligible_reason(sd) == "not_eligible"


def test_draft_reason_no_valid_phone(solapi_env):
    sd = _sd()
    sd["parties"]["customer"]["phone"] = "02-123-4567"
    assert ka.draft_ineligible_reason(sd) == "no_valid_phone"


def test_draft_reason_brand_profile_missing(solapi_env):
    """HAUD 브랜드는 pf_id·template 쌍이 없어 프로필 미비."""
    sd = _sd()
    sd["parties"]["orderer"]["name"] = "하우드"
    assert ka.draft_ineligible_reason(sd) == "brand_profile_missing"


def test_draft_reason_none_when_eligible(solapi_env):
    assert ka.draft_ineligible_reason(_sd()) is None


# --------------------------------------------------------------------------
# 공통 헬퍼 회귀 방지 — 주문 축 판정과 sd 축 코드가 같아야 한다
# --------------------------------------------------------------------------


class _FakeOrder:
    """``_ineligible_reason`` 의 order 축만 만족시키는 최소 스텁(DB 불필요)."""

    id = 1
    status = "ERPORDER"
    deleted_at = None


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda sd: sd, None),
        (lambda sd: {**sd, "schedule": {"measurement": {"date": "", "time": ""}}}, "not_eligible"),
        (
            lambda sd: {**sd, "parties": {**sd["parties"],
                                          "customer": {"name": "임다슬", "phone": "02-1-2"}}},
            "no_valid_phone",
        ),
        (
            lambda sd: {**sd, "parties": {**sd["parties"], "orderer": {"name": "하우드"}}},
            "brand_profile_missing",
        ),
    ],
)
def test_draft_reason_matches_order_reason_on_sd_axis(solapi_env, mutate, expected):
    """sd 축에서 초안 판정과 주문 판정이 같은 코드를 낸다(구현 이중화 방지)."""
    sd = mutate(_sd())
    assert ka.draft_ineligible_reason(sd) == expected
    assert ka._ineligible_reason(_FakeOrder(), sd) == expected


def test_order_reason_keeps_order_axis(solapi_env):
    """order 축(없음·삭제·draft)은 초안 판정에 없고 주문 판정에는 남아 있다."""
    assert ka._ineligible_reason(None, _sd()) == "order_not_found"

    deleted = _FakeOrder()
    deleted.deleted_at = "2026-09-01"
    assert ka._ineligible_reason(deleted, _sd()) == "order_not_found"

    draft_order = _FakeOrder()
    draft_order.status = "DRAFT"
    assert ka._ineligible_reason(draft_order, _sd()) == "not_eligible"
    assert ka.draft_ineligible_reason(_sd()) is None


# --------------------------------------------------------------------------
# send_alimtalk_for_sd
# --------------------------------------------------------------------------


def test_send_for_sd_success_shape(solapi_env, monkeypatch):
    seen = {}

    def _fake_dispatch(sd):
        seen["sd"] = sd
        return "MSG-1", None

    monkeypatch.setattr(ka, "_dispatch", _fake_dispatch)
    result = ka.send_alimtalk_for_sd(_sd(), sent_by=7, dedupe_key="k-1")

    assert result == {"sent": True, "error": None, "message_id": "MSG-1"}
    assert seen["sd"]["parties"]["customer"]["name"] == "임다슬"


def test_send_for_sd_vendor_error_shape(solapi_env, monkeypatch):
    monkeypatch.setattr(ka, "_dispatch", lambda sd: (None, "network"))
    result = ka.send_alimtalk_for_sd(_sd(), sent_by=None, dedupe_key="k-2")
    assert result == {"sent": False, "error": "network", "message_id": None}


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda sd: {**sd, "schedule": {"measurement": {"date": ""}}}, "not_eligible"),
        (
            lambda sd: {**sd, "parties": {**sd["parties"],
                                          "customer": {"name": "임다슬", "phone": "없음"}}},
            "no_valid_phone",
        ),
    ],
)
def test_send_for_sd_ineligible_never_dispatches(solapi_env, dispatch_never, mutate, expected):
    result = ka.send_alimtalk_for_sd(mutate(_sd()), sent_by=1, dedupe_key="k-3")
    assert result == {"sent": False, "error": expected, "message_id": None}


def test_send_for_sd_not_configured_never_dispatches(monkeypatch, dispatch_never):
    monkeypatch.delenv("SOLAPI_API_KEY", raising=False)
    monkeypatch.delenv("SOLAPI_API_SECRET", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_LAHOM", raising=False)
    result = ka.send_alimtalk_for_sd(_sd(), sent_by=1, dedupe_key="k-4")
    assert result == {"sent": False, "error": "not_configured", "message_id": None}


def test_send_for_sd_touches_no_db(solapi_env, monkeypatch):
    """세션 팩토리를 건드리면 실패한다 — 이력 쓰기는 호출자 몫이라는 계약."""
    def _boom():
        raise AssertionError("send_alimtalk_for_sd 가 DB 세션을 열었다")

    monkeypatch.setattr(ka, "_session_factory", _boom)
    monkeypatch.setattr(ka, "_dispatch", lambda sd: ("MSG-9", None))
    assert ka.send_alimtalk_for_sd(_sd(), sent_by=3, dedupe_key="k-5")["sent"] is True


# --------------------------------------------------------------------------
# 이력 entry / 멱등키 빌더
# --------------------------------------------------------------------------

#: 주문 정본 이력(`_record_history`)이 쓰는 키 집합 — 승계 시 무변환 복사 계약.
_ORDER_HISTORY_KEYS = {
    "sent_at", "message_id", "dedupe_key", "error",
    "sent_by", "sent_by_name", "channel", "channel_checked_at",
}


def test_draft_history_entry_key_set_matches_order_history():
    """정본 키를 모두 담고, 추가 키는 ``draft_schedule`` 하나뿐이다(WIZ-SEND-01 D4')."""
    entry = ka.build_draft_history_entry(
        dedupe_key="k", message_id="M", error=None, sent_by=1, sent_by_name="홍길동",
        draft_schedule="2026-09-20:14:00",
    )
    assert _ORDER_HISTORY_KEYS <= set(entry)
    assert set(entry) - _ORDER_HISTORY_KEYS == {"draft_schedule"}
    assert entry["draft_schedule"] == "2026-09-20:14:00"


def test_draft_history_entry_key_set_matches_source_of_truth():
    """키 집합을 소스(`_record_history` 리터럴)에서 직접 뽑아 대조한다."""
    import inspect

    source = inspect.getsource(ka._record_history)
    body = source.split('sd["alimtalk_measurement"] = {', 1)[1].split("}", 1)[0]
    order_keys = set(re.findall(r'"([a-z_]+)":', body))
    entry = ka.build_draft_history_entry(
        dedupe_key=None, message_id=None, error="network", sent_by=None, sent_by_name=None,
        draft_schedule=None,
    )
    assert order_keys <= set(entry)
    assert set(entry) - order_keys == {"draft_schedule"}


def test_draft_history_entry_success_stamps_sent_at():
    entry = ka.build_draft_history_entry(
        dedupe_key="k", message_id="M", error=None, sent_by=2, sent_by_name="김실측",
        draft_schedule="2026-09-20:14:00",
    )
    assert entry["sent_at"] is not None
    assert entry["error"] is None
    assert entry["sent_by"] == 2
    assert entry["sent_by_name"] == "김실측"
    assert entry["channel"] is None and entry["channel_checked_at"] is None


def test_draft_history_entry_failure_has_no_sent_at():
    entry = ka.build_draft_history_entry(
        dedupe_key="k", message_id=None, error="no_valid_phone", sent_by=2, sent_by_name="김실측",
        draft_schedule="2026-09-20:14:00",
    )
    assert entry["sent_at"] is None
    assert entry["message_id"] is None


def test_draft_dedupe_key_is_unique_per_call():
    a = ka.build_draft_dedupe_key("D-1")
    b = ka.build_draft_dedupe_key("D-1")
    assert a != b
    assert a.startswith("alimtalk:measure:draft:D-1:manual:")
    assert re.fullmatch(r"alimtalk:measure:draft:D-1:manual:[0-9a-f]{32}", a)


# --------------------------------------------------------------------------
# 일정 서명 + 승계 이력 기반 중복 차단 (WIZ-SEND-01 D4')
# --------------------------------------------------------------------------


class _SdOrder:
    """``_already_sent`` 가 읽는 것은 ``structured_data`` 하나뿐이다."""

    def __init__(self, structured_data: dict) -> None:
        self.id = 1
        self.structured_data = structured_data


def test_schedule_signature_is_dedupe_key_without_order_id():
    """서명 = 멱등키에서 주문 id 축만 뺀 값 — 두 함수가 같은 정본을 본다는 계약."""
    sd = _sd()
    signature = ka.build_draft_schedule_signature(sd)
    assert signature == "2026-08-14:3시 30분"
    assert ka.build_dedupe_key(42, sd) == f"alimtalk:measure:42:{signature}"


def test_schedule_signature_none_without_schedule():
    assert ka.build_draft_schedule_signature(_sd(schedule={})) is None
    assert ka.build_draft_schedule_signature(None) is None


def test_schedule_signature_normalizes_multiple_dates():
    """여러 날짜는 정렬·중복제거되어 같은 일정이면 같은 서명이 나온다."""
    a = _sd(schedule={"measurement": {"date": "2026-08-15,2026-08-14", "time": "오전"}})
    b = _sd(schedule={"measurement": {"date": "2026-08-14,2026-08-15,2026-08-14",
                                      "time": "오전"}})
    assert ka.build_draft_schedule_signature(a) == ka.build_draft_schedule_signature(b)
    assert ka.build_draft_schedule_signature(a) == "2026-08-14|2026-08-15:오전"


def _inherited_sd(*, draft_schedule: str | None, error=None, message_id="MSG-1", **overrides):
    """초안에서 승계된 알림톡 이력을 단 새 주문 sd."""
    sd = _sd(**overrides)
    sd["alimtalk_measurement"] = ka.build_draft_history_entry(
        dedupe_key="alimtalk:measure:draft:new.x:manual:" + "0" * 32,
        message_id=message_id,
        error=error,
        sent_by=7,
        sent_by_name="테스터",
        draft_schedule=draft_schedule,
    )
    return sd


def test_already_sent_true_when_inherited_schedule_matches():
    """일정 서명이 같으면 멱등키가 전혀 달라도 자동 재발송을 막는다."""
    sd = _inherited_sd(draft_schedule=ka.build_draft_schedule_signature(_sd()))
    order = _SdOrder(sd)
    key = ka.build_dedupe_key(99, sd)
    assert key is not None
    assert sd["alimtalk_measurement"]["dedupe_key"] != key
    assert ka._already_sent(order, key) is True


def test_already_sent_false_when_schedule_changed():
    """일정이 바뀌면 서명이 달라져 자동 재발송이 정상 동작해야 한다."""
    sd = _inherited_sd(draft_schedule="2026-08-14:3시 30분")
    sd["schedule"] = {"measurement": {"date": "2026-08-20", "time": "3시 30분"}}
    order = _SdOrder(sd)
    assert ka._already_sent(order, ka.build_dedupe_key(99, sd)) is False


def test_already_sent_false_when_time_changed():
    """날짜가 같아도 시간이 바뀌면 다른 안내다."""
    sd = _inherited_sd(draft_schedule="2026-08-14:3시 30분")
    sd["schedule"] = {"measurement": {"date": "2026-08-14", "time": "5시"}}
    order = _SdOrder(sd)
    assert ka._already_sent(order, ka.build_dedupe_key(99, sd)) is False


def test_already_sent_false_for_failed_inherited_history():
    """실패 이력은 승계되어도 재발송을 막지 않는다."""
    sd = _inherited_sd(
        draft_schedule=ka.build_draft_schedule_signature(_sd()),
        error="network",
        message_id=None,
    )
    order = _SdOrder(sd)
    assert ka._already_sent(order, ka.build_dedupe_key(99, sd)) is False


def test_already_sent_unaffected_for_order_native_history():
    """주문 정본 이력(draft_schedule 없음)은 예전처럼 멱등키로만 판정한다."""
    sd = _sd()
    key = ka.build_dedupe_key(99, sd)
    sd["alimtalk_measurement"] = {
        "sent_at": "2026-08-10T00:00:00", "message_id": "M", "dedupe_key": key,
        "error": None, "sent_by": None, "sent_by_name": None,
        "channel": None, "channel_checked_at": None,
    }
    order = _SdOrder(sd)
    assert ka._already_sent(order, key) is True
    assert ka._already_sent(order, "alimtalk:measure:99:2026-09-01:오전") is False


def test_already_sent_false_when_no_schedule_at_all():
    """일정이 없으면 서명이 None 이라 None==None 으로 잘못 맞아떨어지면 안 된다."""
    sd = _inherited_sd(draft_schedule=None, schedule={})
    order = _SdOrder(sd)
    assert sd["alimtalk_measurement"]["draft_schedule"] is None
    assert ka.build_draft_schedule_signature(sd) is None
    assert ka._already_sent(order, None) is False


def test_already_sent_manual_axis_ignores_schedule_signature():
    """수동 발송은 누른 만큼 나간다 — 서명 축으로 막으면 무음 실패가 된다."""
    sd = _inherited_sd(draft_schedule=ka.build_draft_schedule_signature(_sd()))
    order = _SdOrder(sd)
    manual_key = "alimtalk:measure:99:manual:abcd"
    assert ka._already_sent(order, manual_key) is True          # 자동 경로는 막는다
    assert ka._already_sent(order, manual_key, manual=True) is False


def test_already_sent_manual_axis_still_honors_same_dedupe_key():
    """수동이라도 정확히 같은 멱등키면 재전달이므로 막는다."""
    sd = _sd()
    key = ka.build_dedupe_key(99, sd)
    sd["alimtalk_measurement"] = {
        "sent_at": "2026-08-10T00:00:00", "message_id": "M", "dedupe_key": key,
        "error": None, "sent_by": 3, "sent_by_name": "수동",
        "channel": None, "channel_checked_at": None,
    }
    assert ka._already_sent(_SdOrder(sd), key, manual=True) is True
