"""반품 거부 **상용구 기본값**이 저장·발송 규칙과 어긋나지 않는지 (2026-09-02).

왜 기본값에 계약이 필요한가
---------------------------
:data:`fulfillment.RETURN_REJECT_FILLS` 는 *아무도 저장하지 않았을 때* 화면에 뜨는 목록이고,
운영에는 아직 저장된 목록이 없다 — 지금 이 상수가 **구매자에게 실제로 나가는 문장**이다.
그런데 이 상수는 :func:`reject_templates.sanitize_templates` 를 거치지 않고
:func:`reject_templates.load_templates` 가 그대로 돌려준다. 그래서 규칙을 어긴 기본값은
**아무 데서도 걸리지 않는다**:

* 문장이 :data:`fulfillment.RETURN_REJECT_REASON_MAX` 를 넘으면 :func:`fulfillment.reject_return`
  이 ``text[:500]`` 으로 **말없이 자른다** — 잘린 문장이 그대로 구매자에게 간다. 되돌릴 수 없다.
* 라벨이 :data:`reject_templates.MAX_LABEL_LEN` 을 넘거나 겹치면, 관리자가 그 목록을 한 번
  저장하는 순간 항목이 조용히 사라진다(정규화가 버리거나 뒤엣것이 덮는다) — 화면에서 보던
  문장이 저장 뒤에 없어지는 모양이다.

그래서 **기본값도 정규화를 통과해야 한다**는 것을 여기서 못 박는다. 문장의 *내용*은 사람이
정하는 값이라 재지 않는다 — 재는 것은 규칙뿐이다.
"""

from __future__ import annotations

from foms.services.integrations.naver_commerce.fulfillment import (
    RETURN_REJECT_FILLS,
    RETURN_REJECT_REASON_MAX,
)
from foms.services.integrations.naver_commerce.reject_templates import (
    MAX_LABEL_LEN,
    MAX_TEMPLATES,
    sanitize_templates,
)


def test_defaults_survive_the_save_normalizer_untouched():
    """기본 목록을 그대로 저장해도 **한 항목도 잃지 않는다**.

    정규화가 하나라도 버리면, 관리자가 "고칠 것 없다"며 저장만 눌러도 목록이 줄어든다.
    """
    cleaned = sanitize_templates([dict(item) for item in RETURN_REJECT_FILLS])

    assert cleaned == [dict(item) for item in RETURN_REJECT_FILLS], cleaned


def test_every_default_sentence_fits_the_send_limit():
    """어떤 기본 문장도 발송 상한을 넘지 않는다 — **잘린 문장은 보내지 않는다**.

    ``reject_return`` 은 넘치면 조용히 자른다. 잘린 자리에서 문장이 끝나면 구매자는
    말이 끊긴 거부 통지를 받고, 그 문장이 분쟁의 근거가 된다.
    """
    for item in RETURN_REJECT_FILLS:
        text = item["text"]
        assert text.strip() == text, f"{item['label']}: 앞뒤 공백이 그대로 나간다"
        assert 0 < len(text) <= RETURN_REJECT_REASON_MAX, (item["label"], len(text))


def test_labels_are_short_and_unique():
    """라벨은 짧고 **겹치지 않는다** — 겹치면 저장 때 뒤엣것이 앞엣것을 덮는다."""
    labels = [item["label"] for item in RETURN_REJECT_FILLS]

    assert len(labels) == len(set(labels)), labels
    assert len(labels) <= MAX_TEMPLATES, labels
    for label in labels:
        assert label.strip() == label and 0 < len(label) <= MAX_LABEL_LEN, label
