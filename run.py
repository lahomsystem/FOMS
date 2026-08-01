"""FOMS 서버 기동 스크립트 (app.py에서 분리). python app.py 또는 python run.py로 실행."""
import logging
import os
from pathlib import Path
import sys
from typing import Any

STARTUP_LOG_PATH_ENV = "FOMS_STARTUP_LOG_PATH"
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off", ""}
_REPO_ROOT = Path(__file__).resolve().parent
_MIGRATIONS_DIR = _REPO_ROOT / "scripts" / "migrations"
if str(_MIGRATIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_MIGRATIONS_DIR))


def _get_startup_log_path() -> str | None:
    """Return optional absolute path for dev startup file logging."""
    raw_path = os.environ.get(STARTUP_LOG_PATH_ENV, "").strip()
    if not raw_path:
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


def _build_startup_logging_handlers(
    enable_file_logging: bool = True,
) -> tuple[list[logging.Handler], str | None]:
    """Build stdout-first handlers for the local dev startup path."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if not enable_file_logging:
        return handlers, None

    log_path = _get_startup_log_path()
    if not log_path:
        return handlers, None

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    return handlers, log_path


def _configure_startup_logging(
    enable_file_logging: bool,
) -> tuple[logging.Logger, str | None]:
    """Configure deterministic logging for the local dev startup path."""
    requested_startup_log_path = _get_startup_log_path()
    handlers, startup_log_path = _build_startup_logging_handlers(
        enable_file_logging=enable_file_logging,
    )
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True,
    )
    logger = logging.getLogger('FOMS_Startup')

    if startup_log_path:
        logger.info("[INFO] Startup file logging enabled: %s", startup_log_path)
    elif requested_startup_log_path:
        logger.info(
            "[INFO] Startup file logging is configured and will be enabled in the reloader child: %s",
            requested_startup_log_path,
        )
    else:
        logger.info(
            "[INFO] Startup file logging disabled. Set %s to enable file logging.",
            STARTUP_LOG_PATH_ENV,
        )
    return logger, startup_log_path


def _parse_bool_env(name: str) -> bool | None:
    """Parse common boolean environment variable formats."""
    raw_value = os.environ.get(name)
    if raw_value is None:
        return None

    normalized = raw_value.strip().lower()
    if normalized in _TRUE_ENV_VALUES:
        return True
    if normalized in _FALSE_ENV_VALUES:
        return False
    return True


def _resolve_debug_mode(use_reloader: bool) -> bool:
    """Keep single-process QA deterministic unless debug is explicitly requested."""
    explicit_debug = _parse_bool_env("FLASK_DEBUG")
    if explicit_debug is not None:
        return explicit_debug
    return use_reloader


def _run_startup_tasks(app: Any, logger: logging.Logger) -> None:
    """Verify the local DB schema is current before the dev server starts.

    STARTUP-PURE-01: dev startup performs no DDL / ``create_all`` / migration
    mutation. The schema is owned by Alembic (``alembic upgrade head``, run in
    ``predeploy.sh`` for deploys and manually for local dev). Here we only fail
    closed when migrations are pending, so a stale local schema is upgraded
    explicitly instead of the server silently migrating it.

    Args:
        app: The Flask app (unused; kept for the stable startup-hook signature).
        logger: Startup logger for deterministic dev-boot messages.

    Raises:
        StartupReadinessError: When the local PostgreSQL schema is behind the
            Alembic head — surfaced loudly by ``main`` so the server never
            starts on a stale schema.
    """
    from foms.services.app_init import verify_migrations_current
    from db import engine

    logger.info("[START] FOMS 애플리케이션 시작 중...")
    verify_migrations_current(engine)
    logger.info("[OK] DB 스키마가 Alembic head와 일치합니다.")
    print("[OK] FOMS 시스템이 준비되었습니다!")


def _run_dev_server(
    app: Any,
    socketio: Any,
    socketio_available: bool,
    use_reloader: bool,
    debug_enabled: bool,
    should_run_startup_tasks: bool,
) -> None:
    """Run the local development server with Socket.IO when available."""
    port = int(os.environ.get('PORT', '5000'))
    if should_run_startup_tasks:
        print("[START] 웹 서버를 시작합니다...")
        print(f"[INFO] SOCKETIO_AVAILABLE: {socketio_available}")
        print(f"[INFO] socketio 객체 존재: {socketio is not None}")
        print(f"[INFO] DEBUG_ENABLED: {debug_enabled}")

    if socketio_available and socketio:
        if should_run_startup_tasks:
            print("[INFO] Socket.IO 모드로 서버를 시작합니다...")
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=debug_enabled,
            use_reloader=use_reloader,
            allow_unsafe_werkzeug=True,
        )
        return

    if should_run_startup_tasks:
        print("[WARN] Socket.IO가 비활성화되어 일반 Flask 모드로 시작합니다...")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug_enabled,
        use_reloader=use_reloader,
    )


def _report_startup_exception(startup_log_path: str | None) -> None:
    """Print the most useful recovery hint for dev startup failures."""
    if startup_log_path:
        print(f"[INFO] 로그 파일({startup_log_path})을 확인해주세요.")
        return

    print(
        "[INFO] 콘솔 로그를 확인하거나 "
        f"{STARTUP_LOG_PATH_ENV} 환경변수로 파일 로그를 활성화하세요."
    )


def main() -> None:
    """서버 기동 및 초기화 수행."""
    _use_reloader = _parse_bool_env('FLASK_USE_RELOADER')
    if _use_reloader is None:
        _use_reloader = True
    _debug_enabled = _resolve_debug_mode(_use_reloader)
    _is_reloader_child = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
    # 세션 worktree(c:/tmp/foms-s-*)에서는 startup DDL이 공유 DB 스키마를
    # 타 브랜치 기준으로 바꾸므로 기본 생략 (FOMS_SKIP_STARTUP_TASKS=0으로 강제 실행)
    _in_session_worktree = os.path.basename(
        os.path.dirname(os.path.abspath(__file__))
    ).lower().startswith('foms-s-')
    _skip_startup = os.environ.get(
        'FOMS_SKIP_STARTUP_TASKS', '1' if _in_session_worktree else '0'
    ) == '1'
    if _in_session_worktree and _skip_startup:
        print('[INFO] 세션 worktree — startup DDL 생략 (FOMS_SKIP_STARTUP_TASKS=0으로 강제 실행 가능)')
    _should_run_startup_tasks = ((not _use_reloader) or _is_reloader_child) and not _skip_startup

    startup_log_path: str | None = None

    try:
        logger, startup_log_path = _configure_startup_logging(_should_run_startup_tasks)
        from app import app, socketio, SOCKETIO_AVAILABLE

        if _should_run_startup_tasks:
            _run_startup_tasks(app, logger)
        else:
            logger.info("[SKIP] 리로더 부모 프로세스에서는 시작 초기화를 건너뜁니다.")

        _run_dev_server(
            app,
            socketio,
            SOCKETIO_AVAILABLE,
            _use_reloader,
            _debug_enabled,
            _should_run_startup_tasks,
        )

    except KeyboardInterrupt:
        print("\n[STOP] 사용자에 의해 서버가 중단되었습니다.")
    except Exception as e:
        print(f"[ERROR] 서버 시작 중 오류: {str(e)}")
        _report_startup_exception(startup_log_path)
    finally:
        if _should_run_startup_tasks:
            print("[END] FOMS 시스템을 종료합니다.")


if __name__ == '__main__':
    main()
