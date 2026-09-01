"""반품 거부 **상용구 문장**: 회사 전체가 공유하는 전역 저장 (T8-S3, 2026-09-01).

왜 전역인가
-----------
거부 사유 문장은 **구매자에게 그대로 간다**. 담당자마다 다른 문장을 쓰면 같은 상황에서
회사가 다른 말을 하게 되고, 그 차이가 그대로 분쟁 재료가 된다. 그래서 목록은 사람마다가
아니라 **한 벌**이고(사용자 결정 2026-09-01), 고치는 것은 **관리자만** 한다.

저장 자리
---------
새 표를 파지 않는다 — ``SystemSetting`` 키 하나다. 값 스키마도 도면 마법사 공유
프리셋과 **같은 모양**(``[{"label", "text"}]``)이라, 다음 사람이 둘 중 하나를 읽으면
나머지도 읽을 수 있다(:mod:`foms.services.drawing_wizard_presets`).

동시 저장
---------
``SystemSetting.version`` 으로 낙관적 잠금을 건다. 관리자 둘이 같은 화면을 열어 두고
따로 저장하면 뒤에 누른 쪽이 앞사람 문장을 **조용히 지운다** — 목록 전체를 통째로
덮어쓰는 자원이라 그 사고가 곧 "왜 내 문장이 사라졌지"다. 버전이 어긋나면 409 로 막고
화면이 새로 고치라고 말한다.

멱등 영수증(``SystemSettingReceipt``)까지는 두지 않는다. 이 목록은 **되돌릴 수 있는**
설정이고(다시 저장하면 그만), 재전송이 만드는 최악은 같은 목록을 한 번 더 쓰는 것이다.
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from models import SystemSetting

__all__ = [
    "REJECT_TEMPLATES_KEY",
    "MAX_TEMPLATES",
    "MAX_LABEL_LEN",
    "RejectTemplateError",
    "RejectTemplateConflict",
    "sanitize_templates",
    "load_templates",
    "templates_version",
    "save_templates",
]

#: 전역 설정 키. 도면 프리셋(``drawing_wizard_presets``)과 같은 표를 쓴다.
REJECT_TEMPLATES_KEY = "naver_return_reject_templates"

#: 목록 상한. 더 많으면 모달에서 고르는 일이 쓰는 일보다 오래 걸린다.
MAX_TEMPLATES = 20

#: 라벨(버튼에 보이는 짧은 말) 상한.
MAX_LABEL_LEN = 20


class RejectTemplateError(Exception):
    """상용구 저장을 진행할 수 없는 상태 — 사유를 사람에게 그대로 보여준다."""


class RejectTemplateConflict(RejectTemplateError):
    """다른 관리자가 먼저 저장했다(낙관적 잠금 충돌)."""

    def __init__(self, message: str, *, current_version: int) -> None:
        super().__init__(message)
        self.current_version = int(current_version)


def sanitize_templates(value: Any) -> list[dict[str, str]]:
    """신뢰할 수 없는 입력을 ``[{"label", "text"}]`` 로 정규화한다.

    거르는 것: 리스트가 아닌 값 · dict 가 아닌 항목 · 문자열이 아닌 필드 ·
    **빈 문장**(빈 상용구는 눌렀을 때 아무 일도 안 일어나는 버튼이 된다) ·
    길이 초과 · 라벨 중복(뒤에 온 것이 이긴다 — 같은 이름으로 저장하면 덮어쓰기다).

    문장 길이 상한은 거부 호출과 **같은 값**을 쓴다(:data:`fulfillment.RETURN_REJECT_REASON_MAX`) —
    여기서만 길게 허용하면 저장은 되고 보낼 때 잘리는 문장이 생긴다.

    Args:
        value: 입력값(list[dict] 기대).

    Returns:
        정규화된 목록(최대 :data:`MAX_TEMPLATES` 개).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        RETURN_REJECT_REASON_MAX,
    )

    if not isinstance(value, list):
        return []
    by_label: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label, text = item.get("label"), item.get("text")
        if not isinstance(text, str) or (label is not None and not isinstance(label, str)):
            continue
        text = text.strip()
        label = (label or "").strip()
        if not text or len(text) > RETURN_REJECT_REASON_MAX or len(label) > MAX_LABEL_LEN:
            continue
        if not label:
            # 라벨이 없으면 문장 앞머리를 이름으로 쓴다 — 이름 없는 버튼을 만들지 않는다.
            label = text[:MAX_LABEL_LEN].strip()
        if label not in by_label:
            order.append(label)
        by_label[label] = {"label": label, "text": text}
        if len(order) >= MAX_TEMPLATES:
            break
    return [by_label[label] for label in order]


def load_templates(session: Session) -> list[dict[str, str]]:
    """지금 쓰는 상용구 목록을 준다 — **저장된 것이 없으면 기본 5종**.

    기본값을 DB 에 미리 심지 않는다. 심어 두면 관리자가 전부 지웠을 때 다음 배포가
    되살리거나, 반대로 "기본으로 되돌리기"가 불가능해진다. 빈 목록은 **비어 있다는
    뜻이 아니라 아직 손대지 않았다는 뜻**이라, 그때만 코드 상수를 보여준다.

    Args:
        session: DB 세션.

    Returns:
        ``[{"label", "text"}]``.
    """
    from foms.services.integrations.naver_commerce.fulfillment import RETURN_REJECT_FILLS

    row = (session.query(SystemSetting)
           .filter(SystemSetting.setting_key == REJECT_TEMPLATES_KEY)
           .first())
    if row is not None and row.setting_value:
        cleaned = sanitize_templates(row.setting_value)
        if cleaned:
            return cleaned
    return [dict(item) for item in RETURN_REJECT_FILLS]


def templates_version(session: Session) -> int:
    """낙관적 잠금 버전(저장 행이 없으면 0 — 화면이 그 값을 그대로 되보낸다).

    Args:
        session: DB 세션.

    Returns:
        ``SystemSetting.version`` 정수.
    """
    row = (session.query(SystemSetting)
           .filter(SystemSetting.setting_key == REJECT_TEMPLATES_KEY)
           .first())
    return int(getattr(row, "version", 0) or 0) if row is not None else 0


def save_templates(session: Session, *, items: Any, actor_user_id: Optional[int] = None,
                   if_match_version: Optional[int] = None) -> dict[str, Any]:
    """상용구 목록을 통째로 저장한다 (커밋은 호출자가 소유한다).

    **목록 전체를 덮어쓴다.** 항목 단위 병합을 하지 않는 이유는 삭제 때문이다 — 병합만
    하면 지운 문장이 되살아나고, 지우는 경로를 따로 파면 두 벌이 된다.

    Args:
        session: DB 세션.
        items: 저장할 목록(정규화 전).
        actor_user_id: 누가 저장했는지(기록은 라우트의 감사 로그가 한다).
        if_match_version: 화면이 읽은 버전. 지금 값과 다르면 저장하지 않는다.

    Returns:
        ``{"templates": [...], "version": int}``.

    Raises:
        RejectTemplateError: 정규화 결과가 비었을 때(빈 목록으로 덮어쓰면 화면에 기본
            5종이 되살아나는데, 그건 "지웠다"와 다른 뜻이라 사고로 읽힌다).
        RejectTemplateConflict: 다른 관리자가 먼저 저장했을 때.
    """
    cleaned = sanitize_templates(items)
    if not cleaned:
        raise RejectTemplateError(
            "저장할 문장이 없습니다 — 이름과 문장을 모두 채우세요"
            "(전부 지우려면 문장을 하나만 남기세요).")

    row = (session.query(SystemSetting)
           .filter(SystemSetting.setting_key == REJECT_TEMPLATES_KEY)
           .with_for_update()
           .first())
    current = int(getattr(row, "version", 0) or 0) if row is not None else 0
    if if_match_version is not None and int(if_match_version) != current:
        raise RejectTemplateConflict(
            "다른 관리자가 먼저 저장했습니다 — 화면을 새로 고친 뒤 다시 저장하세요.",
            current_version=current)

    if row is None:
        row = SystemSetting(setting_key=REJECT_TEMPLATES_KEY,
                            setting_value=copy.deepcopy(cleaned),
                            description="네이버 반품 거부 상용구(전역 공유, 관리자만 수정)",
                            version=1)
        session.add(row)
        next_version = 1
    else:
        # JSONB 는 통째로 갈아 끼우고 flag_modified 를 붙인다(프로젝트 규약).
        row.setting_value = copy.deepcopy(cleaned)
        flag_modified(row, "setting_value")
        next_version = current + 1
        row.version = next_version
    session.flush()
    return {"templates": cleaned, "version": next_version}
