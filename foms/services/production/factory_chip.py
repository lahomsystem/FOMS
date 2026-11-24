"""공장 칩(1공장 · 2공장) 글 — 공장 글이 보이는 자리마다 같은 칩 하나(사장님 2026-11-24 "1공장, 2공장 구분이 잘 안 돼").

글은 그대로 두고 공장 이름("1공장" · "2공장")만 ``<em class="foms-fac foms-fac--N">`` 로 감싼다 — 모양은
``static/css/components/foms-factory-chip.css`` 한 곳. 화면 JS 가 같은 글을 다시 그릴 때도 같은 칩을 만든다
(``foms-packing-factory-view.js`` · ``workbench-sheet-factory.js`` · ``foms-production-pc-sheet.js``).
쿼리 0 · 순수 함수. 빈 글은 그대로 돌려준다(1공장뿐인 화면은 이 칸이 비어 바이트 그대로).
"""

from __future__ import annotations

import re
from typing import Any

from markupsafe import Markup, escape

from foms.services.production.factory_constants import FACTORIES, FACTORY_LABELS

_NUMBER_OF = {FACTORY_LABELS[f]: f for f in FACTORIES}
_LABEL_RE = re.compile("(" + "|".join(re.escape(FACTORY_LABELS[f]) for f in FACTORIES) + ")")
_CHIP = Markup('<em class="foms-fac foms-fac--{n}">{label}</em>')


def factory_chips(text: Any) -> Any:
    """글 안의 공장 이름을 칩으로 — Jinja 거르개 ``factory_chips``.

    Args:
        text: 화면 글(예 "상차 1공장 2장 · 2공장 1장(제작 중)"). None · 빈 글은 그대로.

    Returns:
        이스케이프한 글 + 칩(:class:`markupsafe.Markup`). 공장 이름이 없으면 이스케이프한 글 그대로.
    """
    if text is None or text == "":
        return text
    parts = _LABEL_RE.split(str(text))
    out = [_CHIP.format(n=_NUMBER_OF[part], label=part) if i % 2 else escape(part) for i, part in enumerate(parts)]
    return Markup("").join(out)
