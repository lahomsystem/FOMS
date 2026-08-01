"""ChannelTalk manager identity and permission helpers."""

from __future__ import annotations

import logging
from typing import Optional

from db import db_session
from models import ChannelManagerLink, User

__all__ = [
    "get_user_by_manager_id",
    "is_action_allowed_for_manager",
]

logger = logging.getLogger(__name__)


def get_user_by_manager_id(manager_id: str) -> Optional[User]:
    """
    ChannelTalk manager_id로 매핑된 **canonical active** FOMS User를 조회한다.

    매핑 부재(unmapped)·비활성 매핑(inactive mapping)·비활성 User(inactive user)·DB
    오류는 모두 ``None``(deny)을 반환한다. active mapping 만으로 통과시키지 않으며(비활성
    계정이 canonical User 로 resolve 되는 것을 막는다 — CHANNEL-AUTH-01), 실패는 삼키지
    않고 서버 로그에만 남긴다(호출자에게 raw exception 미노출).
    """
    if not manager_id:
        return None

    session = db_session()
    try:
        link = session.query(ChannelManagerLink).filter(
            ChannelManagerLink.channel_manager_id == manager_id,
            ChannelManagerLink.is_active == True,
        ).first()

        if link and link.user and link.user.is_active:
            return link.user
        return None
    except Exception as e:
        logger.error(f"[ChannelIdentity] Error fetching user for manager_id={manager_id}: {e}", exc_info=True)
        return None
    finally:
        session.close()


def is_action_allowed_for_manager(manager_id: str, action_type: str) -> bool:
    """
    주어진 manager_id가 특정 액션(action_type)을 수행할 권한이 있는지 확인한다.
    기본적으로 매핑된 활성 사용자가 있으면 권한이 있는 것으로 간주한다 (추후 세분화 가능).
    """
    user = get_user_by_manager_id(manager_id)
    if not user:
        return False

    # 향후 action_type에 따른 세부 권한 검사 로직 추가 가능 (예: 관리자 권한 여부 등)
    # 현재는 활성 계정으로 연동되어 있으면 읽기/쓰기 권한을 기본적으로 부여
    return True
