"""AI 도면팀원 시스템 계정 — 노트 · 메모를 남기는 이름(로그인은 못 한다).

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §4 (2026-10-27 사용자 승인 "추천대로" — §7-1 예)

- 처음 쓸 때 만든다(마이그레이션 없이 — 운영 · 스테이징 · 시험 DB 모두 같은 길). 이름이 같은 계정이 있으면 그대로 쓴다.
- 로그인 화면으로는 못 들어온다: ``is_active=False``(로그인 · 세션 모두 거절 — foms/web/auth/routes.py) +
  아무도 모르는 무작위 비밀번호 해시. 비활성이라 팀 알림 수신자 · 담당 후보에도 끼지 않는다.
- 팀(team)은 비워 둔다 — 도면팀 목록 · 배정 후보에 섞이지 않게. 초안 맡기(A4)를 만들 때 다시 정한다.
"""

from __future__ import annotations

import secrets

from foms.services.security.password_policy import hash_password
from models import User

AGENT_USERNAME = 'ai-drawing-agent'
AGENT_NAME = 'AI 도면팀원'


def ensure_agent_user(db) -> User:
    """계정을 찾고, 없으면 만든다(flush 만 — 커밋은 부르는 쪽)."""
    user = db.query(User).filter(User.username == AGENT_USERNAME).first()
    if user is not None:
        return user
    user = User(
        username=AGENT_USERNAME,
        password=hash_password(secrets.token_urlsafe(48)),
        name=AGENT_NAME,
        role='VIEWER',
        team=None,
        is_active=False,
    )
    db.add(user)
    db.flush()
    return user
