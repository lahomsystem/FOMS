"""반품 축 읽기 계약 (T8-S0) — 라벨 구멍 + 수거·환불 축 추출.

근거: `docs/plans/2026-08-26-naver-followup-multiagent-ledger.md` §T8-S0.

두 갈래다.

1. **라벨 구멍** — `BLOCKING_CLAIM_STATUSES` 에는 있는데 `CLAIM_STATUS_LABELS` 에 없는
   상태들이 화면에 **영문 원문**으로 뜬다(`COLLECTING`·`COLLECT_DONE`·`CANCELING`·
   `*_REQUESTED`). 그리고 `RETURN_REJECT` 는 두 집합 어디에도 없다 — 취소는
   `CANCEL_REJECT` 라벨이 있는데 반품만 비대칭이었다.
2. **수거·환불 축** — `collectCompletedDate`·`refundExpectedDate`·`refundStandbyStatus`
   /`Reason`·`collectAddress.*` 는 원본에 이미 온다(인벤토리 §2.5, 회수지 15/281).
   화면이 안 읽었을 뿐이다. 네이버로 나가는 호출은 **0**이다.

**관측되지 않은 것**: 반품 상세가 어느 부모 키에 실려 오는지 실물로 확인된 것은 `cancel`
뿐이다(F-1 이 그 경로로 사유 원문을 읽고 있다). `returnInfo` 등은 폴백이라 여기 픽스처는
**모양 가정**이고, 실물이 들어오면 그때 눈으로 확인한다.
"""
import pytest

from foms.services.integrations.naver_commerce.mapping import (
    BLOCKING_CLAIM_STATUSES,
    CLAIM_STATUS_LABELS,
    extract_claim,
    extract_return_axis,
)

#: ``extract_claim`` 이 원래 주던 키. 뜻도 값도 그대로여야 한다(회귀 방지).
LEGACY_CLAIM_KEYS = ("status", "type", "reason", "requested_at", "label", "blocking",
                     "detailed_reason")


def _snapshot(**product_order) -> dict:
    """실데이터 모양의 상품주문 상세 1건."""
    base = {
        "quantity": 1,
        "totalPaymentAmount": 594000,
        "productName": "라홈 붙박이장",
        "productOrderId": "2026082512345678",
        "shippingAddress": {
            "name": "김실측",
            "tel1": "010-1111-2222",
            "baseAddress": "서울 강남구 테헤란로 1",
            "detailedAddress": "101동 202호",
            "zipCode": "06234",
        },
    }
    base.update(product_order)
    return {
        "order": {"orderId": "2026082599999999", "ordererName": "김실측"},
        "productOrder": base,
    }


# ------------------------------------------------------------------ 라벨 구멍

@pytest.mark.parametrize("status,label", [
    ("COLLECTING", "수거중"),
    ("COLLECT_DONE", "수거 완료"),
    ("CANCELING", "취소 처리중"),
    ("CANCEL_REQUESTED", "취소 요청"),
    ("RETURN_REQUESTED", "반품 요청"),
])
def test_blocking_statuses_all_have_korean_labels(status, label):
    """차단하는 상태는 **전부** 한국어 라벨이 있어야 한다.

    차단은 되는데 라벨이 없으면 배지에 영문 상수가 그대로 뜬다 — 담당자가 왜 잠겼는지
    화면에서 못 읽는다.
    """
    claim = extract_claim(_snapshot(claimStatus=status))
    assert claim["label"] == label
    assert claim["blocking"] is True


def test_every_blocking_status_is_labeled():
    """구멍이 다시 생기지 않게 **집합 대 집합**으로 잠근다."""
    missing = sorted(BLOCKING_CLAIM_STATUSES - set(CLAIM_STATUS_LABELS))
    assert missing == []


def test_return_reject_is_labeled_and_not_blocking():
    """반품 거부는 라벨이 있고 **차단하지 않는다** — 취소 거부와 같은 규칙.

    거부는 클레임이 무산됐다는 뜻이라 주문이 정상 진행한다
    (`BLOCKING_CLAIM_STATUSES` 주석: "거부·철회는 정상 진행이라 뺀다").
    지금까지 `RETURN_REJECT` 만 두 집합 어디에도 없어 영문으로 떴다.
    """
    claim = extract_claim(_snapshot(claimStatus="RETURN_REJECT"))
    assert claim["label"] == "반품 거부"
    assert claim["blocking"] is False


def test_exchange_reject_is_labeled():
    """교환 거부도 같은 비대칭이었다."""
    assert extract_claim(_snapshot(claimStatus="EXCHANGE_REJECT"))["label"] == "교환 거부"


def test_unknown_status_still_falls_back_to_raw_text():
    """모르는 상태는 **숨기지 않고 원문 그대로** 보여준다(기존 규율 회귀 방지)."""
    claim = extract_claim(_snapshot(claimStatus="SOMETHING_NEW"))
    assert claim["label"] == "SOMETHING_NEW"
    assert claim["blocking"] is False


def test_legacy_claim_keys_unchanged_for_cancel_block():
    """기존 7키의 뜻과 값은 그대로다."""
    detail = _snapshot(claimStatus="CANCEL_REQUEST")
    detail["cancel"] = {
        "claimStatus": "CANCEL_REQUEST",
        "claimType": "CANCEL",
        "cancelReason": "SIMPLE_INTENT_CHANGED",
        "cancelDetailedReason": "일시불 재결제 예정",
        "claimRequestDate": "2026-08-25T11:00:00.000+09:00",
    }
    claim = extract_claim(detail)
    for key in LEGACY_CLAIM_KEYS:
        assert key in claim
    assert claim["status"] == "CANCEL_REQUEST"
    assert claim["reason"] == "SIMPLE_INTENT_CHANGED"
    assert claim["detailed_reason"] == "일시불 재결제 예정"
    assert claim["requested_at"] == "2026-08-25T11:00:00.000+09:00"


def test_return_detailed_reason_reachable_from_return_block():
    """반품 사유 원문이 `cancel` 이 아닌 반품 블록에 실려 와도 읽는다.

    기존 코드는 `returnDetailedReason` 을 **`cancel` 블록 안에서만** 찾았다. 반품이 별도
    블록으로 오면 그 값은 영영 빈 문자열이었다(조용한 유실 — 배송메모 사건과 같은 모양).
    """
    detail = _snapshot(claimStatus="RETURN_REQUEST")
    detail["returnInfo"] = {
        "claimStatus": "RETURN_REQUEST",
        "returnReason": "PRODUCT_DEFECT",
        "returnDetailedReason": "문짝 모서리가 찍혀서 왔어요",
        "claimRequestDate": "2026-08-26T09:30:00.000+09:00",
    }
    claim = extract_claim(detail)
    assert claim["reason"] == "PRODUCT_DEFECT"
    assert claim["detailed_reason"] == "문짝 모서리가 찍혀서 왔어요"
    assert claim["requested_at"] == "2026-08-26T09:30:00.000+09:00"


# ------------------------------------------------------- 수거 · 환불 축 (S0)

def test_return_axis_empty_when_no_claim():
    """클레임이 없으면 **아무것도 안다고 하지 않는다**.

    `known` 이 False 여야 화면이 줄 자체를 안 낸다 — 빈 칸이나 `-` 로 채우면 거짓말이다.
    """
    axis = extract_return_axis(_snapshot())
    assert axis["known"] is False
    assert axis["collect_completed_at"] == ""
    assert axis["refund_expected_at"] == ""
    assert axis["collect_address"]["address"] == ""


def test_return_axis_from_return_block():
    """실물 `return` 블록에서 수거·환불 값을 읽는다.

    2026-08-27 정정: 이 테스트는 원래 `cancel` 블록에 값을 넣었다("실물로 확인된 유일한
    경로"라고 적혀 있었다). 그때는 `return` 이 미관측이라 그랬지만, 스테이징에 실물
    `return` 블록 33건이 관측됐고 **`cancel` 을 반품 축으로 읽는 것이 결함**이었다
    (취소만 된 50건에 "반품 진행" 줄이 떴다). 픽스처를 실물 모양으로 바꾼다.
    """
    detail = _snapshot(claimStatus="COLLECT_DONE")
    detail["return"] = {
        "claimStatus": "COLLECT_DONE",
        "collectDeliveryMethod": "DELIVERY",
        "collectCompletedDate": "2026-08-26T14:05:00.000+09:00",
        "refundExpectedDate": "2026-08-28T00:00:00.000+09:00",
        "refundStandbyStatus": "WAIT",
        "refundStandbyReason": "회수 상품 검수 대기",
    }
    axis = extract_return_axis(detail)
    assert axis["known"] is True
    assert axis["collect_method"] == "DELIVERY"
    assert axis["collect_completed_at"] == "2026-08-26T14:05:00.000+09:00"
    assert axis["refund_expected_at"] == "2026-08-28T00:00:00.000+09:00"
    assert axis["refund_standby_status"] == "WAIT"
    assert axis["refund_standby_reason"] == "회수 상품 검수 대기"


def test_return_axis_collect_address_is_joined_like_shipping():
    """회수지 주소는 배송지와 **같은 규칙**으로 합친다(base + detailed).

    2026-08-27 정정: "자사 회수라 우리 차가 직접 간다"는 사실이 아니었다(실물이 오가지
    않는다). 그래도 합치는 규칙은 그대로다 — 네이버가 준 주소를 **틀리게 보여주지 않기**
    위해서다. 이 주소가 없으면 담당자가 판매자센터를 연다.
    """
    detail = _snapshot(claimStatus="COLLECTING")
    detail["return"] = {
        "claimStatus": "COLLECTING",
        "collectAddress": {
            "name": "김실측",
            "tel1": "010-1111-2222",
            "baseAddress": "서울 강남구 테헤란로 1",
            "detailedAddress": "101동 202호",
            "zipCode": "06234",
        },
    }
    address = extract_return_axis(detail)["collect_address"]
    assert address["address"] == "서울 강남구 테헤란로 1 101동 202호"
    assert address["name"] == "김실측"
    assert address["tel"] == "010-1111-2222"
    assert address["zip_code"] == "06234"


def test_return_axis_from_current_claim_nesting():
    """`currentClaim` 아래로 접혀 오는 변형도 읽는다(`extract_claim` 과 같은 규율)."""
    detail = _snapshot(claimStatus="RETURN_REQUEST")
    detail["currentClaim"] = {
        "returnInfo": {
            "claimStatus": "RETURN_REQUEST",
            "refundExpectedDate": "2026-08-30T00:00:00.000+09:00",
        },
    }
    axis = extract_return_axis(detail)
    assert axis["known"] is True
    assert axis["refund_expected_at"] == "2026-08-30T00:00:00.000+09:00"


def test_return_axis_does_not_raise_on_garbage():
    """표시용 보조라 여기서 터지면 멀쩡한 화면이 통째로 죽는다."""
    for garbage in (None, [], "", 0, {"cancel": "not-a-dict"}):
        axis = extract_return_axis(garbage)
        assert axis["known"] is False


# ------------------------- `_claim_blocks` 가 바꾼 우선순위 (CEO 리뷰 A1)

def test_current_claim_itself_is_read_when_no_named_block():
    """`currentClaim` 이 **평평하게** 오는 모양도 읽는다 — 옛 규칙은 못 읽었다.

    옛 코드는 `cancel` 과 `currentClaim.cancel` 두 자리만 봤다. 그래서 클레임 상세가
    `currentClaim` 자신에 평평하게 실려 오면 `order.claimStatus`(더 뭉뚱그린 값)로
    떨어졌다. **이건 값이 바뀌는 변경이다** — "기존 동작 불변"이 아니라 "더 구체적인
    소스를 먼저 본다"가 정확한 진술이고, 그래서 여기에 단언으로 못박는다.
    """
    detail = _snapshot()
    detail["order"]["claimStatus"] = "CANCEL_DONE"
    detail["currentClaim"] = {"claimStatus": "RETURN_DONE", "returnReason": "PRODUCT_DEFECT"}
    claim = extract_claim(detail)
    assert claim["status"] == "RETURN_DONE"
    assert claim["reason"] == "PRODUCT_DEFECT"


def test_named_claim_block_wins_over_current_claim():
    """이름 있는 블록(`cancel`)이 `currentClaim` 자신보다 앞선다 — 우선순위를 잠근다."""
    detail = _snapshot()
    detail["cancel"] = {"claimStatus": "CANCEL_REQUEST", "cancelReason": "MISTAKE_ORDER"}
    detail["currentClaim"] = {"claimStatus": "RETURN_DONE", "returnReason": "PRODUCT_DEFECT"}
    claim = extract_claim(detail)
    assert claim["status"] == "CANCEL_REQUEST"
    assert claim["reason"] == "MISTAKE_ORDER"


# ------------------------------------------------- 취소 블록이 반품 축으로 새지 않는다


def test_cancel_only_does_not_render_return_axis():
    """**취소만 된 건은 반품 축이 비어 있어야 한다** (2026-08-27 CEO A1).

    `cancel` 블록에도 `refundExpectedDate`·`refundStandbyStatus` 가 실려 온다.
    반품 축이 `_claim_blocks`(첫 항목이 `cancel`)를 그대로 쓰면 그 값이 새어 들어와
    화면 머리는 배지 `취소 완료` 를 달고 몸통은 `반품 진행` 을 말한다.
    스테이징 실데이터 344 링크 중 **50건**이 그 상태였다 — 합성 음성 사례가
    "클레임 아예 없음" 뿐이라 테스트가 못 잡았다.
    """
    detail = _snapshot(claimStatus="CANCEL_DONE")
    detail["cancel"] = {
        "claimStatus": "CANCEL_DONE",
        "refundExpectedDate": "2026-08-23T00:00:00.000+09:00",
        "refundStandbyStatus": "환불처리완료",
        "refundStandbyReason": "취소 진행중건 존재",
    }
    axis = extract_return_axis(detail)
    assert axis["refund_expected_at"] == ""
    assert axis["refund_standby_status"] == ""
    assert axis["refund_standby_reason"] == ""
    assert axis["known"] is False


def test_cancel_block_does_not_shadow_a_real_return():
    """취소와 반품이 함께 있으면 **반품 값**을 읽는다 — 취소를 뺀 것이 반품을 가리지 않는다."""
    detail = _snapshot(claimStatus="RETURN_DONE")
    detail["cancel"] = {"refundExpectedDate": "2026-01-01T00:00:00.000+09:00"}
    detail["return"] = {
        "claimStatus": "RETURN_DONE",
        "refundExpectedDate": "2026-09-04T00:00:00.000+09:00",
        "collectCompletedDate": "2026-08-26T09:17:35.539+09:00",
        "collectDeliveryMethod": "RETURN_INDIVIDUAL",
    }
    axis = extract_return_axis(detail)
    assert axis["refund_expected_at"] == "2026-09-04T00:00:00.000+09:00"
    assert axis["collect_completed_at"] == "2026-08-26T09:17:35.539+09:00"
    assert axis["known"] is True


def test_return_axis_block_keys_exclude_cancel():
    """이름 목록을 **집합으로** 잠근다 — `cancel` 이 다시 들어오면 여기서 빨개진다."""
    from foms.services.integrations.naver_commerce.mapping import RETURN_BLOCK_KEYS

    assert "cancel" not in RETURN_BLOCK_KEYS
    assert set(RETURN_BLOCK_KEYS) == {"returnInfo", "return", "exchange"}


# --------------------------------------------- 반품 **단계**(R-5 · R-6) 2026-08-28

def _return_done_detail() -> dict:
    """운영 `RETURN_DONE` 25건과 **같은 모양**의 상세 1건.

    필드 구성은 실측이다(D-live-data 부록 B — 네 값 전부 25/25 보유).
    """
    detail = _snapshot(claimStatus="RETURN_DONE")
    detail["productOrder"]["claimType"] = "RETURN"
    detail["return"] = {
        "claimStatus": "RETURN_DONE",
        "claimType": "RETURN",
        "collectCompletedDate": "2026-08-26T09:17:35.539+09:00",
        "collectDeliveryMethod": "RETURN_INDIVIDUAL",
        "returnCompletedDate": "2026-08-27T10:02:11.000+09:00",
        "refundExpectedDate": "2026-09-04T00:00:00.000+09:00",
        "refundStandbyStatus": "환불처리완료",
    }
    return detail


def test_return_axis_reads_return_completed_date():
    """끝났음을 말할 수 있는 유일한 값을 읽는다 — 지금까지 소비처가 **0곳**이었다.

    운영 25건 전부 `returnCompletedDate` 를 갖고 있는데 코드가 한 번도 안 읽어서,
    화면이 끝난 반품을 `반품 진행` 이라고 말했다.
    """
    axis = extract_return_axis(_return_done_detail())
    assert axis["return_completed_at"] == "2026-08-27T10:02:11.000+09:00"


def test_return_axis_knows_the_claim_phase():
    """축이 `claimStatus` 를 읽는다 — 예전에는 한 번도 안 봤다."""
    assert extract_return_axis(_return_done_detail())["phase"] == "done"


def test_return_axis_phase_is_in_progress_for_collect_done():
    """**음성 대조군** — 수거가 끝난 것은 반품 확정이 아니다.

    이게 없으면 "제목을 통째로 완료로 바꾸는" 오수정이 통과한다.
    """
    detail = _snapshot(claimStatus="COLLECT_DONE")
    detail["return"] = {"claimStatus": "COLLECT_DONE",
                        "collectCompletedDate": "2026-08-26T09:17:35.539+09:00"}
    axis = extract_return_axis(detail)
    assert axis["phase"] == "in_progress"
    assert axis["progress_title"] == "반품 진행"
    assert axis["refund_expected_pending"] is False   # 값 자체가 없다


def test_return_axis_progress_title_says_done():
    """끝난 반품의 줄 제목은 `반품 완료` 다(고정 문자열 `반품 진행` 이 아니라)."""
    assert extract_return_axis(_return_done_detail())["progress_title"] == "반품 완료"


def test_return_axis_progress_title_follows_claim_type_for_exchange():
    """R-6 — 교환 블록 값이 `반품` 이라는 이름으로 뜨지 않는다.

    `exchange` 를 반품 축 블록 목록에 남긴 것은 옳다(수거는 반품·교환 양쪽에서 온다).
    틀린 것은 **줄 제목이 고정 문자열**이라 교환이 반품으로 불린 것이다 —
    `cancel` 을 뺀 이유(취소 50건이 "반품 진행"으로 뜬 사고)와 같은 형태의 누출이다.
    """
    detail = _snapshot(claimStatus="EXCHANGE_DONE")
    detail["productOrder"]["claimType"] = "EXCHANGE"
    detail["exchange"] = {
        "claimStatus": "EXCHANGE_DONE",
        "claimType": "EXCHANGE",
        "collectCompletedDate": "2026-08-26T09:17:35.539+09:00",
    }
    axis = extract_return_axis(detail)
    assert axis["kind_label"] == "교환"
    assert axis["progress_title"] == "교환 완료"


def test_return_axis_progress_title_says_rejected():
    """거부된 반품을 `진행` 이라 부르지 않는다 — 주문은 살아 있다."""
    detail = _snapshot(claimStatus="RETURN_REJECT")
    detail["return"] = {"claimStatus": "RETURN_REJECT",
                        "collectCompletedDate": "2026-08-26T09:17:35.539+09:00"}
    assert extract_return_axis(detail)["progress_title"] == "반품 거부"


def test_collect_method_label_is_korean():
    """`RETURN_INDIVIDUAL` 영문 상수를 사람에게 보여주지 않는다.

    원문(`collect_method`)은 그대로 남긴다 — 라벨은 표시용이고 판정은 원문으로 한다.
    """
    axis = extract_return_axis(_return_done_detail())
    assert axis["collect_method"] == "RETURN_INDIVIDUAL"
    assert axis["collect_method_label"] == "자사 회수"


def test_unknown_collect_method_keeps_the_raw_value():
    """모르는 회수 방법은 **원문 그대로** — 다른 라벨 맵과 같은 규율(숨기지 않는다)."""
    detail = _snapshot(claimStatus="RETURN_DONE")
    detail["return"] = {"claimStatus": "RETURN_DONE",
                        "collectDeliveryMethod": "RETURN_SOMETHING_NEW"}
    assert extract_return_axis(detail)["collect_method_label"] == "RETURN_SOMETHING_NEW"


def test_refund_done_only_when_the_value_says_so():
    """환불 완료 판정은 **아는 값**일 때만. 모르는 값을 완료로 읽지 않는다."""
    assert extract_return_axis(_return_done_detail())["refund_done"] is True

    detail = _return_done_detail()
    detail["return"]["refundStandbyStatus"] = "환불보류"
    axis = extract_return_axis(detail)
    assert axis["refund_done"] is False
    assert axis["refund_standby_status"] == "환불보류"


def test_refund_expected_is_not_pending_once_the_return_is_done():
    """끝난 반품에서 `환불 예정` 은 미래형 거짓말이다 — 화면이 안 내도록 표식을 준다."""
    done = extract_return_axis(_return_done_detail())
    assert done["refund_expected_at"] == "2026-09-04T00:00:00.000+09:00"   # 값은 안 지운다
    assert done["refund_expected_pending"] is False

    detail = _snapshot(claimStatus="COLLECT_DONE")
    detail["return"] = {"claimStatus": "COLLECT_DONE",
                        "refundExpectedDate": "2026-09-04T00:00:00.000+09:00"}
    assert extract_return_axis(detail)["refund_expected_pending"] is True


def test_return_completed_date_alone_opens_the_row():
    """완료 시각만 온 건도 `known` 이다 — 그 값 하나로 화면이 할 말이 생긴다."""
    detail = _snapshot(claimStatus="RETURN_DONE")
    detail["return"] = {"claimStatus": "RETURN_DONE",
                        "returnCompletedDate": "2026-08-27T10:02:11.000+09:00"}
    assert extract_return_axis(detail)["known"] is True


def test_cancel_only_order_has_no_return_phase_line():
    """**음성 대조군** — 취소만 된 건은 여전히 아무 말도 하지 않는다.

    단계를 읽게 됐다고 해서 취소 건에 반품 줄이 열리면 50건 사고의 재발이다.
    """
    detail = _snapshot(claimStatus="CANCEL_DONE")
    detail["cancel"] = {
        "claimStatus": "CANCEL_DONE",
        "refundExpectedDate": "2026-08-23T00:00:00.000+09:00",
        "refundStandbyStatus": "환불처리완료",
    }
    axis = extract_return_axis(detail)
    assert axis["known"] is False
    assert axis["return_completed_at"] == ""
    assert axis["refund_done"] is False
