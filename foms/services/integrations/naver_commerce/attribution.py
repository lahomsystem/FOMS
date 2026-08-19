"""추가옵션이 **어느 본품의 구성인가**(귀속) 판정 (NAVER-INGEST-01 T15-K).

네이버 커머스API 는 추가옵션에 부모 본품 링크를 주지 않는다. 그래서 원본에서 읽을 수 있는
두 가지 단서를 순서대로 쓴다 — 둘 다 2026-08-18~19 스테이징 실데이터로 확인했다.

1. **수집 순서**: 응답이 ``본품 → 그 본품의 옵션들`` 로 섞여 오는 집이 있다
   (예: `2026081822487841` = `M a a a a a M a a a a a a a`). 이때는 순서가 정본이다.
2. **사양 축 일치**: 본품이 앞에 몰려 오는 집도 있다(`M M a a a a` — 36집 중 3집).
   이때 순서로 보면 옵션이 전부 마지막 본품에 붙어 틀린다. 대신 몰딩/문 방식/손잡이가
   **정확히 한 본품과만** 맞으면 그 본품으로 붙이고, 갈리면 **미정**으로 두고 사람이 고른다.

축 값은 **옵션 원문이 정본**이다. 라홈 상품명은 라인 이름으로 ``무몰딩`` 을 달고 있는데
고객이 옵션에서 ``몰딩`` 을 고르는 조합이 실재한다(본품류 100건 중 10건).

이 모듈은 순수 함수만 둔다 — 매핑(품목 생성)과 도크(화면 표시)가 **같은 판정**을 쓰도록
한 곳에 모았다. 한쪽만 바뀌면 품목 금액과 화면 귀속이 어긋난다.
"""

from __future__ import annotations

from typing import Any, Optional

#: 본품과 추가옵션의 사양이 갈리는 축. **부분문자열 함정** 때문에 긴 값을 먼저 검사한다
#: ('몰딩' 은 '무몰딩' 안에도 있다).
SPEC_AXES = (
    ("몰딩", ("무몰딩", "몰딩")),
    ("문 방식", ("슬라이딩", "미닫이", "여닫이")),
    ("손잡이", ("피닉스바", "푸쉬")),
)

#: 귀속 근거 문구(화면에 그대로 뜬다).
REASON_SEQUENCE = "수집 순서 — 바로 위 본품의 구성"
REASON_SEQUENCE_FIRST = "수집 순서 — 첫 본품의 구성"
REASON_SPEC = "사양 일치({axes})로 추정"
REASON_UNRESOLVED = "본품 사양이 갈린다 — 어느 본품의 구성인지 선택 필요"
REASON_NO_MAIN = "본품 없음"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _axis_value(text: str) -> dict[str, str]:
    """한 문자열에서 축별 값을 읽는다(없는 축은 키 자체가 없다)."""
    lowered = _text(text)
    found: dict[str, str] = {}
    for axis, values in SPEC_AXES:
        for value in values:
            if value in lowered:
                found[axis] = value
                break
    return found


def axis_values(product_name: str, option_text: str) -> dict[str, str]:
    """사양 축 값 — **옵션 원문 우선**, 그 축이 옵션에 없을 때만 상품명으로 보완.

    Args:
        product_name: 상품명(라인 이름이라 실제 선택과 다를 수 있다).
        option_text: 고객이 고른 옵션 원문(정본).

    Returns:
        축 이름 → 값 dict.
    """
    axes = _axis_value(product_name)
    axes.update(_axis_value(option_text))
    return axes


def _is_interleaved(is_main: list[bool]) -> bool:
    """본품 사이에 옵션이 끼어 있는가(= 순서가 귀속을 말해 주는 배치인가)."""
    mains = [i for i, flag in enumerate(is_main) if flag]
    if len(mains) < 2:
        return True
    return any(not is_main[i] for i in range(mains[0], mains[-1]))


def _spec_owner(addon_axes: dict[str, str],
                main_axes: list[tuple[int, dict[str, str]]]) -> tuple[Optional[int], str]:
    """사양 축이 **정확히 한 본품과만** 맞으면 그 본품, 아니면 미정."""
    if not addon_axes:
        return (None, REASON_UNRESOLVED)
    hits: list[tuple[int, list[str]]] = []
    for index, axes in main_axes:
        shared = [axis for axis in addon_axes if axis in axes]
        if shared and all(axes[axis] == addon_axes[axis] for axis in shared):
            hits.append((index, shared))
    if len(hits) == 1:
        index, shared = hits[0]
        return (index, REASON_SPEC.format(axes="·".join(shared)))
    return (None, REASON_UNRESOLVED)


def attribute_addons(rows: list[dict[str, Any]]) -> list[tuple[Optional[int], str]]:
    """각 행의 귀속 본품 인덱스와 근거를 계산한다.

    Args:
        rows: 수집 순서대로 정렬된 행 목록. 각 행은
            ``{"is_main": bool, "product_name": str, "option_text": str}``.

    Returns:
        행마다 ``(귀속 본품 인덱스 또는 None, 사람이 읽는 근거)``.
        본품 행은 ``(None, "")``. 본품이 하나도 없으면 전부 ``(None, "본품 없음")``.
    """
    flags = [bool(row.get("is_main")) for row in rows]
    mains = [i for i, flag in enumerate(flags) if flag]
    out: list[tuple[Optional[int], str]] = [(None, "")] * len(rows)
    if not mains:
        return [(None, REASON_NO_MAIN) if not flag else (None, "") for flag in flags]

    if _is_interleaved(flags):
        current: Optional[int] = None
        for index, row in enumerate(rows):
            if flags[index]:
                current = index
                continue
            if current is None:
                out[index] = (mains[0], REASON_SEQUENCE_FIRST)
            else:
                out[index] = (current, REASON_SEQUENCE)
        return out

    # 본품이 앞에 몰려 온 배치 — 순서로는 못 가른다. 사양 축으로만 붙인다.
    main_axes = [
        (index, axis_values(_text(rows[index].get("product_name")),
                            _text(rows[index].get("option_text"))))
        for index in mains
    ]
    for index, row in enumerate(rows):
        if flags[index]:
            continue
        addon_axes = axis_values(_text(row.get("product_name")),
                                 _text(row.get("option_text")))
        out[index] = _spec_owner(addon_axes, main_axes)
    return out


__all__ = [
    "REASON_NO_MAIN",
    "REASON_SEQUENCE",
    "REASON_SEQUENCE_FIRST",
    "REASON_SPEC",
    "REASON_UNRESOLVED",
    "SPEC_AXES",
    "attribute_addons",
    "axis_values",
]
