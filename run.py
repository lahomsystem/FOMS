"""FOMS 서버 기동 스크립트 (app.py에서 분리). python app.py 또는 python run.py로 실행."""
import logging
import os
import sys


def main():
    """서버 기동 및 초기화 수행."""
    from app import app, socketio, SOCKETIO_AVAILABLE
    from db import init_db
    from wdcalculator_db import init_wdcalculator_db
    from apps.api.attachments import (
        ensure_order_attachments_category_column,
        ensure_order_attachments_item_index_column,
    )

    _use_reloader = (os.environ.get('FLASK_USE_RELOADER', '1') == '1')
    _is_reloader_child = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
    _should_run_startup_tasks = (not _use_reloader) or _is_reloader_child

    try:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('app_startup.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logger = logging.getLogger('FOMS_Startup')

        if _should_run_startup_tasks:
            logger.info("[START] FOMS 애플리케이션 시작 중...")
            startup_success = True

            try:
                init_db()
                with app.app_context():
                    ensure_order_attachments_category_column()
                    ensure_order_attachments_item_index_column()
                logger.info("[OK] FOMS 데이터베이스 초기화 완료")
            except Exception as e:
                logger.error(f"[ERROR] FOMS 데이터베이스 초기화 실패: {str(e)}")
                startup_success = False

            try:
                with app.app_context():
                    init_wdcalculator_db()
                logger.info("[OK] 견적 계산기 데이터베이스 초기화 완료")
            except Exception as e:
                logger.warning(f"[WARN] 견적 계산기 데이터베이스 초기화 실패 (견적 기능 제한): {str(e)}")

            try:
                from safe_schema_migration import run_safe_migration
                with app.app_context():
                    migration_success = run_safe_migration(app.app_context())
                    if migration_success:
                        logger.info("[OK] 스키마 마이그레이션 완료")
                    else:
                        logger.warning("[WARN] 스키마 마이그레이션 실패 - 기존 스키마로 계속 진행")
                        startup_success = False
            except Exception as e:
                logger.error(f"[ERROR] 스키마 마이그레이션 중 예외: {str(e)}")
                startup_success = False

            if startup_success:
                logger.info("[SUCCESS] 모든 시작 프로세스가 성공적으로 완료되었습니다!")
                print("[OK] FOMS 시스템이 준비되었습니다!")
            else:
                logger.warning("[WARN] 일부 시작 프로세스에서 오류가 발생했지만 앱은 정상적으로 시작됩니다.")
        else:
            logger.info("[SKIP] 리로더 부모 프로세스에서는 시작 초기화를 건너뜁니다.")

        if _should_run_startup_tasks:
            print("[START] 웹 서버를 시작합니다...")
            print(f"[INFO] SOCKETIO_AVAILABLE: {SOCKETIO_AVAILABLE}")
            print(f"[INFO] socketio 객체 존재: {socketio is not None}")

        if SOCKETIO_AVAILABLE and socketio:
            if _should_run_startup_tasks:
                print("[INFO] Socket.IO 모드로 서버를 시작합니다...")
            socketio.run(
                app,
                host='0.0.0.0',
                port=5000,
                debug=True,
                use_reloader=_use_reloader,
                allow_unsafe_werkzeug=True,
            )
        else:
            if _should_run_startup_tasks:
                print("[WARN] Socket.IO가 비활성화되어 일반 Flask 모드로 시작합니다...")
            app.run(
                host='0.0.0.0',
                port=5000,
                debug=True,
                use_reloader=_use_reloader,
            )

    except KeyboardInterrupt:
        print("\n[STOP] 사용자에 의해 서버가 중단되었습니다.")
    except Exception as e:
        print(f"[ERROR] 서버 시작 중 오류: {str(e)}")
        print("[INFO] 로그 파일(app_startup.log)을 확인해주세요.")
    finally:
        if _should_run_startup_tasks:
            print("[END] FOMS 시스템을 종료합니다.")


if __name__ == '__main__':
    main()
