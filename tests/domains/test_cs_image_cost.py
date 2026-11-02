"""그림 읽기 돈 · 부르기 꼴(설계서 17.11 (c) · (f)) — 최악값 예약에 base64 글자가 안 들어감 · 그림은 픽셀 식 · PDF 는 쪽 식 ·
글만 있는 요청은 예전과 같은 값(음성 대조) · 부르기 인자(Sonnet 처음 값 · 구조화 출력 · base64 · 캐시 표시 없음 · 도구 없음).

금액 숫자는 적지 않는다 — 기대값은 단가표 × 토큰으로 그 자리에서 셈한다.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal

from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import image_brain as ib
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.brain_media import IMAGE_TOKEN_CAP, PDF_TEXT_TOKENS_PER_PAGE, image_tokens, media_tokens
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_prep import Prepared
from tests.support.cs_agent_fakes import at
from tests.support.cs_image_support import encoded, pdf_bytes, plan_image

CFG = st.PanelSettings(dict(st.DEFAULTS))
REF = FileRef("m-1", 0, "image/jpeg", 1, 1, 1, key="k")


def jpeg(width, height):
    data = encoded(plan_image(width, height), "JPEG", quality=95)
    return Prepared(ref=REF, kind="image", media_type="image/jpeg", data=data, sha256="0" * 64, width=width,
                    height=height)


def pdf(pages):
    return Prepared(ref=REF, kind="document", media_type="application/pdf", data=pdf_bytes(pages), sha256="1" * 64,
                    pages=pages)


def params(*items, conversation="[손님] 합성 견적 문의"):
    return ib.build_params(list(items), conversation=conversation, chat_id="uc-1", now=at(2, 9), cfg=CFG)


def old_worst_case(p):
    """고치기 전 셈(요청 글자 수 전부) — 시험 안에서만 되살린 대조용."""
    prices = bp._reserve_prices(p)
    text = json.dumps(dict(p), ensure_ascii=False, default=str)
    input_price = max(max(x.input, x.cache_write_5m, x.cache_write_1h) for x in prices)
    attempts = bp.FALLBACK_ATTEMPTS if p.get("fallbacks") else 1
    micro = ((len(text) + bp.RESERVE_OVERHEAD_TOKENS) * input_price + int(p["max_tokens"]) * max(x.output for x in prices))
    return micro * attempts / Decimal(1_000_000)


def test_image_tokens_follow_the_28px_patch_rule_with_a_cap():
    assert image_tokens(2000, 1500) == 72 * 54 == 3888  # 공식 vision 문서 표의 2000x1500 값과 같다
    assert image_tokens(1000, 1000) == 1296 and image_tokens(3840, 2160) == IMAGE_TOKEN_CAP
    assert image_tokens(0, 0) == IMAGE_TOKEN_CAP  # 모르면 상한


def test_the_reservation_counts_pixels_not_base64_characters():
    p = params(jpeg(2000, 1500))
    stripped, media = media_tokens(p)
    data = p["messages"][0]["content"][1]["source"]["data"]
    assert len(data) > 100_000 and media == 3888
    assert data not in json.dumps(stripped, ensure_ascii=False)  # 글자 수 셈에 base64 가 들어가지 않는다
    new, old = bp.worst_case_cost(p), old_worst_case(p)
    attempts = bp.FALLBACK_ATTEMPTS if p.get("fallbacks") else 1
    price = max(max(x.input, x.cache_write_5m, x.cache_write_1h) for x in bp._reserve_prices(p))
    assert new == old - (len(data) - 3888) * price * attempts / Decimal(1_000_000)
    assert old - new > new  # 예전 셈은 한 장을 base64 글자 수(수십만 '토큰')로 잡아 하루 상한을 바로 채웠다


def test_pdf_pages_are_counted_per_page_text_plus_page_image():
    _, media = media_tokens(params(pdf(3)))
    assert media == 3 * (PDF_TEXT_TOKENS_PER_PAGE + IMAGE_TOKEN_CAP)


def test_negative_control_a_text_only_request_reserves_exactly_as_before():
    for p in ({"model": bp.MODEL, "max_tokens": 16000}, params(), bp_like_draft()):
        assert bp.worst_case_cost(p) == old_worst_case(p)


def bp_like_draft():
    return {"model": bp.MODEL_SONNET, "max_tokens": 8000, "system": [{"type": "text", "text": "합성 지시"}],
            "messages": [{"role": "user", "content": "이번 일: 합성"}], "fallbacks": "default"}


def test_build_params_uses_the_image_panel_fields_and_base64_blocks():
    p = params(jpeg(400, 300), pdf(1))
    assert (p["model"], p["max_tokens"], p["output_config"]["effort"]) == (bp.MODEL_SONNET, 8000, "high")  # D92
    assert p["thinking"] == {"type": "adaptive"} and "tools" not in p
    assert p["output_config"]["format"]["type"] == "json_schema"
    assert all("cache_control" not in block for block in p["system"])  # 캐시 표시 없음
    kinds = [(b["type"], b.get("source", {}).get("type")) for b in p["messages"][0]["content"]]
    assert kinds == [("text", None), ("image", "base64"), ("text", None), ("document", "base64"), ("text", None)]
    image = p["messages"][0]["content"][1]["source"]
    assert base64.b64decode(image["data"]).startswith(b"\xff\xd8") and "\n" not in image["data"]
    assert p["betas"] == ["server-side-fallback-2026-07-01"] and p["fallbacks"] == "default"  # Sonnet 은 대체를 받는다
    haiku = ib.build_params([], conversation="", chat_id="uc-1", now=at(2, 9),
                            cfg=st.PanelSettings({**st.DEFAULTS, "image_model": bp.MODEL_HAIKU}))
    assert "fallbacks" not in haiku  # Haiku 5.5 는 대체가 없다
