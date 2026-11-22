"""열어 둔 탭도 새 화면으로 — 지금 서버가 내보내는 릴리스 식별자(STALE-TAB-01, 2026-11-22).

2026-11-21 운영 실측: 공장 태블릿이 03:39 UTC 에 연 생산 첫 화면이 뒤에서 멈춰 있다가 10:47 에
깨어났는데, 그 사이 나간 배포(#886 등)를 받지 못하고 **옛 HTML + 옛 핀 CSS/JS** 를 그대로 보였다.
셸이 깨어날 때 다시 받는 것은 미리 받아 둔 조각뿐이고, 지금 문서 자체는 그대로였기 때문이다.

이 모듈은 "이 서버가 지금 어느 릴리스인가"를 한 곳에서 정한다.

* 값 = :data:`foms.services.common.fragment_revalidation.RELEASE_ID`(조각 버전 키와 같은 축).
* 출처가 프로세스 uuid(최후 수단)면 **빈 문자열** — 워커마다 값이 달라 탭이 새로고침을 되풀이한다.
* 문서는 그린 릴리스를 ``<script data-foms-release>`` 로 싣고(``layout_scripts.html``), 서버는 HTML · 셸
  조각(304 포함) 응답 머리글 :data:`RELEASE_HEADER` 와 ``GET /api/foms/release`` 로 지금 릴리스를 알린다.
  둘이 다르면 ``static/js/runtime/foms-release-watch.js`` 가 한가할 때 한 번 새로 읽는다.
"""

from __future__ import annotations

import re
from typing import Any, Final

from foms.services.common import fragment_revalidation as _fr

__all__ = ["RELEASE_HEADER", "attach_release_header", "public_release_id"]

#: 지금 서버 릴리스를 싣는 응답 머리글.
RELEASE_HEADER: Final[str] = "X-Foms-Release"
#: 탭의 되풀이 방지 표식(`바라던|시각|횟수|떠난`)이 `|` 로 칸을 가른다 — 알리는 값은 이 글자들만.
_UNSAFE_CHARS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")


def public_release_id() -> str:
    """탭에 알려도 되는 릴리스 식별자.

    Returns:
        워커 · 컨테이너가 같은 값을 내는 식별자(배포 env · 템플릿 digest, 영숫자 · ``.`` · ``_`` · ``-`` 만).
        프로세스 uuid 면 빈 문자열.
    """
    if _fr.RELEASE_ID_SOURCE == _fr.RELEASE_SOURCE_PROCESS:
        return ""
    return _UNSAFE_CHARS.sub("", _fr.RELEASE_ID)


def attach_release_header(response: Any) -> Any:
    """HTML 문서 · 셸 조각 응답과 304(하트비트 재검증)에 지금 릴리스 머리글을 붙인다.

    304 는 werkzeug 가 Content-Type 을 지워 HTML 판정으로는 못 잡는다 — 셸 하트비트 응답 대부분이 304 라
    따로 센다. 이미 붙은 값은 덮지 않는다.

    Args:
        response: Flask/werkzeug 응답 객체.

    Returns:
        같은 응답 객체.
    """
    release = public_release_id()
    if release and (response.mimetype == "text/html" or response.status_code == 304):
        response.headers.setdefault(RELEASE_HEADER, release)
    return response
