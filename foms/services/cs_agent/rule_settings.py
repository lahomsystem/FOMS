"""코드에 박혀 있던 규칙 값 넷을 설정으로(master brain 설계서 7.8 다음 4 · 사장님 D116) — 견적 최소 길이 · 반통 기준 · 그림 읽기
벽 쪽 값. brain 항목은 ``setting:<키>#<칸>`` 으로 이 값을 가리킨다(값을 베끼지 않는다).

설정 줄 둘(SystemSetting JSON — 칸 이름 → 정수 mm):

- ``cs_quote_rules``: ``hinge_min_mm``(여닫이 최소 · 처음 값 1500) · ``slide_min_mm``(슬라이딩 최소 · 2400 — 규칙 칸이 빈
  '모름' 제품의 최소도 이 값을 따른다) · ``hinge_half_mm``(반통 기준 · 1200 — 여닫이 최소보다 작아야 한다).
- ``drawing_dimension_rules``: ``wall_side_mm``(벽 포함 치수에서 벽 쪽마다 빼는 값 · 150).

**읽기는 설정 → 없으면 지금 값**(바뀜 0): 줄이 없거나 칸이 빠지거나 틀리면(정수 아님 · 범위 밖) 그 칸만 처음 값 — 관리 패널
설정 읽기(:func:`.settings.read_settings`)와 같은 꼴이고 칸 검사도 같은 함수(:func:`.settings.check_value`)다. 처음 값은 코드
상수(:data:`.quote_rules.HINGE_MIN_MM` · :data:`.image_rules.WALL_SIDE_MM` …)라 시험이 둘을 맞춘다. 계산 함수(견적 규칙 ·
벽 범위)는 그대로 순수 함수이고 값을 인자로 받는다 — DB 는 부르는 쪽이 한 번 읽는다(:func:`quote_limits` · :func:`wall_side_mm`).
쓰기 화면은 아직 없다(값은 사장님 승인 뒤 설정 쓰기 길로).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from foms.services.cs_agent.image_rules import WALL_SIDE_MM
from foms.services.cs_agent.quote_rules import HINGE_HALF_MM, HINGE_MIN_MM, SLIDE_MIN_MM, QuoteLimits
from foms.services.cs_agent.settings import check_value
from foms.services.cs_agent.settings_field import KIND_INT, Field
from models import SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "DIMENSION_FIELDS", "DIMENSION_RULES_KEY", "KNOWN_FIELDS", "QUOTE_FIELDS", "QUOTE_RULES_KEY", "limits_from",
    "quote_limits", "rule_values", "wall_side_from", "wall_side_mm",
]

QUOTE_RULES_KEY, DIMENSION_RULES_KEY = "cs_quote_rules", "drawing_dimension_rules"
_GROUP_QUOTE, _GROUP_DRAWING = "견적 규칙(라홈 규격)", "그림 읽기 치수"
QUOTE_FIELDS: tuple[Field, ...] = (
    Field("hinge_min_mm", "여닫이 최소 가로", KIND_INT, HINGE_MIN_MM, _GROUP_QUOTE, low=300, high=10_000, unit="mm"),
    Field("slide_min_mm", "슬라이딩 최소 가로", KIND_INT, SLIDE_MIN_MM, _GROUP_QUOTE, low=300, high=10_000, unit="mm"),
    Field("hinge_half_mm", "여닫이 반통 기준", KIND_INT, HINGE_HALF_MM, _GROUP_QUOTE, low=100, high=10_000, unit="mm"),
)
DIMENSION_FIELDS: tuple[Field, ...] = (
    Field("wall_side_mm", "벽 쪽마다 빼는 값", KIND_INT, WALL_SIDE_MM, _GROUP_DRAWING, low=0, high=1_000, unit="mm"),
)
#: 설정 키 → 칸 이름 → 처음 값. 줄이 없어도 처음 값이 있는 칸이라 brain 의 ``setting:<키>#<칸>`` 가리킴은 실재로 본다
#: (:mod:`foms.services.brain.external`).
KNOWN_FIELDS: dict[str, dict[str, Any]] = {
    QUOTE_RULES_KEY: {f.name: f.default for f in QUOTE_FIELDS},
    DIMENSION_RULES_KEY: {f.name: f.default for f in DIMENSION_FIELDS},
}


def rule_values(stored: Any, fields: tuple[Field, ...]) -> tuple[dict[str, Any], list[str]]:
    """저장 값 → (칸마다 쓰는 값, 처음 값으로 둔 칸 가운데 값이 있었는데 틀린 칸). 줄이 없으면(``None``) 모두 처음 값(틀림 0).

    순수 함수 — 칸 검사는 관리 패널과 같은 :func:`.settings.check_value`."""
    source = stored if isinstance(stored, Mapping) else {}
    broken = stored is not None and not isinstance(stored, Mapping)
    values, wrong = {}, []
    for field in fields:
        present = field.name in source
        ok, value = check_value(field, source[field.name]) if present else (False, None)
        values[field.name] = value if ok else field.default
        if (present and not ok) or broken:
            wrong.append(field.name)
    return values, wrong


def limits_from(stored: Any) -> QuoteLimits:
    """``cs_quote_rules`` 저장 값 → :class:`.quote_rules.QuoteLimits`(순수). 반통 기준이 여닫이 최소보다 작지 않으면 둘 다 처음 값
    (1.5통 구간이 뒤집히지 않게)."""
    values, _wrong = rule_values(stored, QUOTE_FIELDS)
    if values["hinge_half_mm"] >= values["hinge_min_mm"]:
        values.update(hinge_half_mm=HINGE_HALF_MM, hinge_min_mm=HINGE_MIN_MM)
    return QuoteLimits(**values)


def wall_side_from(stored: Any) -> int:
    """``drawing_dimension_rules`` 저장 값 → 벽 쪽마다 빼는 값(순수)."""
    return int(rule_values(stored, DIMENSION_FIELDS)[0]["wall_side_mm"])


def _stored(session: Any, key: str) -> Optional[Any]:
    """설정 줄 값(없으면 ``None``) — 틀린 칸은 칸 이름만 경고."""
    row = session.get(SystemSetting, key, populate_existing=True)  # 매번 DB 에서 새로(저장하면 다음 차례부터)
    if row is None:
        return None
    fields = QUOTE_FIELDS if key == QUOTE_RULES_KEY else DIMENSION_FIELDS
    _values, wrong = rule_values(row.setting_value, fields)
    if wrong:
        logger.warning("[규칙 설정] 칸이 틀려 처음 값으로 둔다 key=%s fields=%s", key, ",".join(wrong))
    return row.setting_value


def quote_limits(session: Any) -> QuoteLimits:
    """견적 최소 길이 · 반통 기준(설정 → 없으면 코드 상수)."""
    return limits_from(_stored(session, QUOTE_RULES_KEY))


def wall_side_mm(session: Any) -> int:
    """그림 읽기 벽 쪽 값(설정 → 없으면 코드 상수)."""
    return wall_side_from(_stored(session, DIMENSION_RULES_KEY))

