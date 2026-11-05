"""[보내기] · [수정하기] 화면의 권한과 한 번용 서명 표(플랜 C10-3 · 설계서 17.2.1 '고른 길' 1 링크 길 · 원장 R10-15).

- **권한(:func:`can_use_send_screen`)**: 상담 직원(CS 팀 — 회계팀은 CS 권한을 함께 가진다, :func:`team_has_capability`)과 ADMIN 만.
  조회 전용 · 협력사 · 꺼진 계정은 안 된다. 정책 엔진의 ``CS_AGENT_SEND`` 가 이 함수를 게이트로 부르고, 화면 · API 도
  가드가 꺼진 자리(시험 등)에서 한 번 더 부른다.
- **서명 표(:func:`issue_send_token` · :func:`check_send_token`)**: 링크 주소에는 표를 넣지 않는다(메신저 미리 읽기 · 기록에
  남는다). 화면(GET)이 그때 그 직원 · 그 차례 · 그 메모로 서명한 표를 ``data-*`` 로 싣고, 화면 자바스크립트가 CSRF 와 함께 POST
  에 넣는다. 표는 :data:`TOKEN_MAX_AGE` (30분) 뒤 만료되고, 다른 차례 · 다른 직원 · 바뀐 메모(다시 쓰기 뒤)면 거절한다. GET 은
  표를 쓰지 않는다(미리 읽기가 표를 써 버리지 않는다). 한 번만 쓰이는 것은 차례 줄의 조건부 쓰기가 보장한다 — 보냄 · 버림 ·
  다시 쓰기 뒤에는 같은 표로 다시 할 일이 없다.
- 표에는 글 · 상담 id 가 없다(차례 id · 직원 id · 메모 id · 무작위 값).
- **확인표(:func:`confirm_stamp`)**: '확인 후 보내기' 경고가 나간 그 글(빈칸을 하나로 맞춘 글) · 그 경고 코드 · 그 차례 · 그 직원에
  묶인 서명(HMAC). 두 번째 누름은 같은 확인표가 있어야 보낸다 — 글을 바꾸면 새 경고를 다시 본다(검수 R15-1). 확인표에도 글은
  없다(서명 값뿐).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Iterable, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from foms.services.orders.order_mutation_policy import team_has_capability
from foms.services.auth.partner_scope import is_partner_user

__all__ = [
    "SEND_TEAMS", "SIGN_SALT", "TOKEN_MAX_AGE", "SendTokenError", "can_use_send_screen", "check_send_token",
    "confirm_matches", "confirm_stamp", "issue_send_token", "normalized",
]

#: 서명 소금(비밀이 아니다 — 이 화면 서명을 다른 서명과 가르는 이름). 비밀은 앱 비밀 키다.
SIGN_SALT = "foms.cs-agent.send.v1"
#: 서명 표 만료(초) — 설계서 17.2.1 '만료 30분'.
TOKEN_MAX_AGE = 30 * 60
#: 보내기 화면을 쓰는 팀(STAFF · MANAGER) — ADMIN 은 팀과 상관없이 쓴다.
SEND_TEAMS = ("CS",)
TOKEN_EXPIRED, TOKEN_BAD, TOKEN_OTHER_TURN = "token_expired", "token_bad", "token_other_turn"
TOKEN_OTHER_USER, TOKEN_STALE = "token_other_user", "token_stale"


class SendTokenError(ValueError):
    """서명 표 거절 — :attr:`code` 로 가른다(표 값은 싣지 않는다)."""

    def __init__(self, code: str) -> None:
        """거절 코드를 싣는다."""
        super().__init__(code)
        self.code = code


def can_use_send_screen(user: Any) -> bool:
    """[보내기] · [수정하기] 화면 · API 를 쓸 수 있나 — ADMIN, 또는 CS 권한 팀의 STAFF · MANAGER(켜진 우리 직원만)."""
    if user is None or getattr(user, "is_active", None) is False or is_partner_user(user):
        return False
    role = (getattr(user, "role", None) or "").strip().upper()
    if role == "ADMIN":
        return True
    return role in ("STAFF", "MANAGER") and team_has_capability(getattr(user, "team", None), SEND_TEAMS)


def _serializer(secret_key: Any) -> URLSafeTimedSerializer:
    """앱 비밀 키로 서명하는 꼴(소금은 이 화면 전용)."""
    if not secret_key:
        raise RuntimeError("앱 비밀 키가 없다 — 서명 표를 만들 수 없다")
    return URLSafeTimedSerializer(secret_key, salt=SIGN_SALT)


def issue_send_token(secret_key: Any, *, turn_id: int, user_id: int, memo_id: Optional[str]) -> str:
    """그 직원 · 그 차례 · 그 메모로 서명한 표(만료 30분). GET 화면이 만들어 ``data-*`` 로 싣는다."""
    payload = {"t": int(turn_id), "u": int(user_id), "m": memo_id or "", "n": secrets.token_hex(8)}
    return _serializer(secret_key).dumps(payload)


def check_send_token(secret_key: Any, token: Any, *, turn_id: int, user_id: int, memo_id: Optional[str],
                     max_age: int = TOKEN_MAX_AGE) -> None:
    """표를 확인한다 — 서명 · 만료 · 그 차례 · 그 직원 · 지금 메모와 같은가.

    Raises:
        SendTokenError: 만료(``token_expired``) · 서명 · 꼴이 틀림(``token_bad``) · 다른 차례(``token_other_turn``) · 다른
            직원(``token_other_user``) · 메모가 바뀜(``token_stale`` — 다시 쓰기 뒤 옛 화면).
    """
    if not isinstance(token, str) or not token or len(token) > 512:
        raise SendTokenError(TOKEN_BAD)
    try:
        data = _serializer(secret_key).loads(token, max_age=max_age)
    except SignatureExpired:
        raise SendTokenError(TOKEN_EXPIRED) from None
    except BadSignature:
        raise SendTokenError(TOKEN_BAD) from None
    if not isinstance(data, dict):
        raise SendTokenError(TOKEN_BAD)
    if data.get("t") != int(turn_id):
        raise SendTokenError(TOKEN_OTHER_TURN)
    if data.get("u") != int(user_id):
        raise SendTokenError(TOKEN_OTHER_USER)
    if data.get("m") != (memo_id or ""):
        raise SendTokenError(TOKEN_STALE)


def normalized(text: str) -> str:
    """확인표가 보는 글 — 빈칸 · 줄바꿈을 하나로 맞춘 글(빈칸만 다른 같은 글은 같은 글)."""
    return " ".join((text or "").split())


def confirm_stamp(secret_key: Any, *, turn_id: int, user_id: Any, text: str, codes: Iterable[str]) -> str:
    """'확인 후 보내기' 확인표 — 그 차례 · 그 직원 · 그 글 · 그 경고 코드에 묶인 HMAC(앞 40자). 직원은 FOMS 번호(정수) 또는
    작은 창 길의 채널톡 상담원 표지(글 — ``m:<번호>``, :attr:`.send_flow.SendRequest.who`)."""
    key = hashlib.sha256(SIGN_SALT.encode("utf-8") + b":confirm:" + str(secret_key).encode("utf-8")).digest()
    who = user_id if isinstance(user_id, str) else int(user_id)
    body = json.dumps([int(turn_id), who, sorted(set(codes)), normalized(text)], ensure_ascii=False)
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def confirm_matches(secret_key: Any, stamp: Any, *, turn_id: int, user_id: Any, text: str,
                    codes: Iterable[str]) -> bool:
    """두 번째 누름의 확인표가 지금 글 · 지금 경고에 맞는가(글자열이 아니면 아니다)."""
    if not isinstance(stamp, str) or not stamp:
        return False
    expected = confirm_stamp(secret_key, turn_id=turn_id, user_id=user_id, text=text, codes=codes)
    return hmac.compare_digest(stamp, expected)
