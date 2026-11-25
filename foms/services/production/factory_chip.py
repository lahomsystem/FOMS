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


_SEG = " · "


def factory_line_chips(text: Any) -> Any:
    """공장마다 한 덩이로 끊는 줄 — 상차 줄("상차 1공장 2장(제작 중) · 2공장 1장(제작 중)") 거르개 ``factory_line_chips``.

    글은 그대로(이어 붙이면 같은 글). 공장 몫마다 ``foms-fac-seg``(공장 칩 + 장 수는 한 덩이, "(제작 중)"도 한 덩이 — 칸이
    모자랄 때만 그 둘 사이에서 꺾인다), 두 번째 몫 앞 " · " 는 ``foms-fac-sep`` — 줄이 갈려 몫이 줄 머리에 서면 CSS 가 가린다
    (``foms-load-split.css``). 맨 앞 글머리("상차 ")는 첫 몫 안 첫 줄 앞. 빈 글은 그대로.
    """
    if text is None or text == "":
        return text
    segs = []
    for i, part in enumerate(str(text).split(_SEG)):
        hit = _LABEL_RE.search(part)
        head, core = (part[:hit.start()], part[hit.start():]) if hit else (part, "")
        body, tail = core, ""
        if core.endswith(")") and "(" in core:
            body, tail = core[:core.rfind("(")], core[core.rfind("("):]
        inner = Markup('<span class="foms-fac-sep">{}</span>').format(_SEG) if i else Markup("")
        inner += escape(head)
        if body:
            inner += Markup('<span class="foms-fac-nw">{}</span>').format(factory_chips(body))
        if tail:
            inner += Markup('<wbr><span class="foms-fac-nw">{}</span>').format(tail)
        segs.append(Markup('<span class="foms-fac-seg">{}</span>').format(inner))
    return Markup('<span class="foms-fac-line"><span class="foms-fac-line__in">{}</span></span>').format(Markup("").join(segs))
