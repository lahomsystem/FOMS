"""Process-wide logging bootstrap for FOMS (AUDIT-LOG T1).

프로덕션(gunicorn) 경로에는 로깅 설정이 전혀 없어 root=WARNING + 핸들러 0개로
INFO 로그가 전량 소실됐다(느린 요청 로그·RUM 집계 등). 이 모듈이 단일 SSOT로
root logger를 구성한다:

- root 레벨 INFO + stderr ``StreamHandler`` 1개(고유 name으로 멱등).
- **핸들러 레벨** 필터 2종: :class:`~foms.services.error_logging.RedactionFilter`
  (비밀값 마스킹 — 로거 레벨 부착은 전파 레코드에 무효하므로 핸들러에 단다) +
  :class:`RequestIdFilter` (모든 레코드에 ``request_id`` 속성 주입).
- ``FOMS_STARTUP_LOG_PATH`` env가 있으면 같은 포맷·필터의 파일 핸들러 opt-in.

호출 지점: ``foms.platform.app_factory.build_app`` 초입(gunicorn 경로) +
``run.py``(로컬 dev). 멱등이라 pytest/alembic/tools 재초기화에서 no-op.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from flask import g, has_request_context

from foms.services.error_logging import RedactionFilter

STARTUP_LOG_PATH_ENV = "FOMS_STARTUP_LOG_PATH"

ROOT_HANDLER_NAME = "foms-root-handler"
STARTUP_FILE_HANDLER_NAME = "foms-startup-file-handler"

LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s"

_REQUEST_ID_FILTER_NAME = "foms_request_id"


class RequestIdFilter(logging.Filter):
    """모든 LogRecord에 ``request_id`` 속성을 주입하는 핸들러 필터.

    포맷 문자열의 ``%(request_id)s`` 토큰이 서드파티 레코드에서도 항상
    치환되도록, 레코드가 통과할 때마다 속성을 무조건 설정한다. Flask 요청
    컨텍스트 안이면 ``g.request_id``(``register_http_bootstrap``의
    before_request가 발급, 없으면 ``'-'``), 컨텍스트 밖이면 ``'-'``.

    ``has_request_context()`` + ``getattr`` 기본값 조합만 사용하므로 예외
    경로가 없다 — 로깅 자체를 절대 죽이지 않는다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = _REQUEST_ID_FILTER_NAME

    def filter(self, record: logging.LogRecord) -> bool:
        """레코드에 ``request_id`` 속성을 주입하고 항상 통과시킨다.

        Args:
            record: 포맷 직전의 로그 레코드(서드파티 레코드 포함).

        Returns:
            항상 ``True`` — 레코드를 드롭하지 않는다.
        """
        request_id: str = "-"
        if has_request_context():
            request_id = getattr(g, "request_id", None) or "-"
        record.request_id = request_id
        return True


def get_startup_log_path() -> str | None:
    """``FOMS_STARTUP_LOG_PATH`` env를 절대경로 문자열로 해석한다(opt-in 파일 로그).

    Returns:
        env가 비어 있으면 ``None``, 아니면 cwd 기준으로 해석한 절대경로 문자열.
    """
    raw_path = os.environ.get(STARTUP_LOG_PATH_ENV, "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


def _has_handler(root: logging.Logger, name: str) -> bool:
    """root logger에 지정 이름의 핸들러가 이미 붙어 있는지 확인한다.

    Args:
        root: 검사할 root logger.
        name: 멱등성 판정용 핸들러 이름.

    Returns:
        같은 이름의 핸들러가 하나라도 있으면 ``True``.
    """
    return any(existing.name == name for existing in root.handlers)


def _attach_foms_handler(handler: logging.Handler, name: str) -> logging.Handler:
    """핸들러에 고유 name·표준 포맷·필터 2종을 달아 돌려준다.

    Args:
        handler: 새로 만든 핸들러(stream 또는 file).
        name: 멱등성 판정에 쓰는 고유 핸들러 이름.

    Returns:
        설정을 마친 동일 핸들러(``addHandler`` 체이닝용).
    """
    handler.name = name
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RedactionFilter())
    handler.addFilter(RequestIdFilter())
    return handler


def configure_logging() -> None:
    """root logger를 프로덕션 표준으로 구성한다(멱등).

    - root 레벨 INFO.
    - name=``foms-root-handler``인 stderr ``StreamHandler`` 1개
      (이미 있으면 추가하지 않는다 — 재호출 no-op).
    - ``FOMS_STARTUP_LOG_PATH`` env가 있으면 같은 포맷·필터의
      ``FileHandler``(name=``foms-startup-file-handler``)를 추가(동일 멱등).

    Returns:
        None. 부수효과로 root logger 구성만 바꾼다.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not _has_handler(root, ROOT_HANDLER_NAME):
        root.addHandler(
            _attach_foms_handler(logging.StreamHandler(sys.stderr), ROOT_HANDLER_NAME)
        )

    startup_log_path = get_startup_log_path()
    if startup_log_path and not _has_handler(root, STARTUP_FILE_HANDLER_NAME):
        Path(startup_log_path).parent.mkdir(parents=True, exist_ok=True)
        root.addHandler(
            _attach_foms_handler(
                logging.FileHandler(startup_log_path, encoding="utf-8"),
                STARTUP_FILE_HANDLER_NAME,
            )
        )
