"""
안전한 데이터베이스 스키마 마이그레이션 모듈
- SystemExit 대신 안전한 예외 처리
- 트랜잭션 기반 일괄 처리
- 상세한 로깅 및 오류 보고
"""

from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import logging
from sqlalchemy import inspect, text
from db import get_db

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SafeSchemaMigration:
    def __init__(self):
        self.columns_to_add = [
            ('measurement_date', 'VARCHAR'),
            ('measurement_time', 'VARCHAR'),
            ('completion_date', 'VARCHAR'),
            ('manager_name', 'VARCHAR'),
            ('payment_amount', 'INTEGER'),
            ('scheduled_date', 'VARCHAR'),
            ('as_received_date', 'VARCHAR'),
            ('as_completed_date', 'VARCHAR'),
            ('is_regional', 'BOOLEAN DEFAULT FALSE'),
            ('is_self_measurement', 'BOOLEAN DEFAULT FALSE'),
            ('is_cabinet', 'BOOLEAN DEFAULT FALSE'),
            ('cabinet_status', "VARCHAR DEFAULT 'RECEIVED'"),
            ('regional_sales_order_upload', 'BOOLEAN DEFAULT FALSE'),
            ('regional_blueprint_sent', 'BOOLEAN DEFAULT FALSE'),
            ('regional_order_upload', 'BOOLEAN DEFAULT FALSE'),
            ('shipping_scheduled_date', 'VARCHAR'),
            ('shipping_fee', 'INTEGER DEFAULT 0'),
            ('blueprint_image_url', 'TEXT'),
            ('is_erp_order', 'BOOLEAN DEFAULT FALSE'),
            ('raw_order_text', 'TEXT'),
            ('structured_data', 'JSONB'),
            ('structured_schema_version', 'INTEGER DEFAULT 1'),
            ('structured_confidence', 'VARCHAR(20)'),
            ('structured_updated_at', 'TIMESTAMP')
        ]

    def _get_bind(self, db):
        """Return the active SQLAlchemy bind for the current session."""
        try:
            return db.get_bind()
        except Exception:
            return getattr(db, "bind", None)

    def _normalized_column_type(self, db, column_type):
        """Map legacy PostgreSQL-only column types to SQLite-safe types."""
        bind = self._get_bind(db)
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "") or ""
        if dialect_name == "sqlite" and column_type == "JSONB":
            return "JSON"
        return column_type
    
    def check_column_exists(self, db, column_name):
        """컬럼 존재 여부 확인"""
        try:
            bind = self._get_bind(db)
            inspector = inspect(bind)
            columns = inspector.get_columns('orders')
            return any(column.get('name') == column_name for column in columns)
        except Exception as e:
            logger.error(f"컬럼 존재 확인 중 오류 ({column_name}): {str(e)}")
            return False
    
    def add_column_safely(self, db, column_name, column_type):
        """개별 컬럼을 안전하게 추가"""
        try:
            if self.check_column_exists(db, column_name):
                logger.info(f"[SKIP] 컬럼 '{column_name}' 이미 존재함 - 건너뜀")
                return True
            
            resolved_type = self._normalized_column_type(db, column_type)
            alter_query = text(f"ALTER TABLE orders ADD COLUMN {column_name} {resolved_type}")
            db.execute(alter_query)
            logger.info(f"[ADD] 컬럼 '{column_name}' 성공적으로 추가됨")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 컬럼 '{column_name}' 추가 실패: {str(e)}")
            return False

    def normalize_legacy_erp_flag(self, db):
        """Rename the legacy ERP flag column to the canonical name when possible."""
        try:
            has_legacy = self.check_column_exists(db, 'is_erp_beta')
            has_canonical = self.check_column_exists(db, 'is_erp_order')

            if has_legacy and not has_canonical:
                db.execute(text("ALTER TABLE orders RENAME COLUMN is_erp_beta TO is_erp_order"))
                logger.info("[RENAME] legacy 'is_erp_beta' renamed to 'is_erp_order'")
            elif has_legacy and has_canonical:
                logger.info("[SKIP] legacy/canonical ERP flag columns already coexist")
        except Exception as e:
            logger.error(f"[ERROR] ERP flag column rename 실패: {str(e)}")
            raise
    
    def execute_migration(self):
        """전체 마이그레이션 실행"""
        logger.info("=== 안전한 스키마 마이그레이션 시작 ===")
        
        try:
            # 데이터베이스 연결
            db = get_db()
            logger.info("[OK] 데이터베이스 연결 성공")
            
            # 마이그레이션 통계
            success_count = 0
            total_count = len(self.columns_to_add)
            failed_columns = []
            
            # 트랜잭션 시작
            transaction = db.begin()
            
            try:
                self.normalize_legacy_erp_flag(db)
                # 각 컬럼 처리
                for column_name, column_type in self.columns_to_add:
                    if self.add_column_safely(db, column_name, column_type):
                        success_count += 1
                    else:
                        failed_columns.append(column_name)
                
                # 모든 컬럼이 성공한 경우에만 커밋
                if len(failed_columns) == 0:
                    transaction.commit()
                    logger.info(f"[SUCCESS] 마이그레이션 완료: {success_count}/{total_count} 성공")
                    return True
                else:
                    transaction.rollback()
                    logger.error(f"[ERROR] 일부 컬럼 실패로 인한 롤백: {failed_columns}")
                    return False
                    
            except Exception as e:
                transaction.rollback()
                logger.error(f"[ERROR] 트랜잭션 오류로 인한 롤백: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"[ERROR] 데이터베이스 연결 실패: {str(e)}")
            return False
        
        finally:
            try:
                db.close()
                logger.info("[CLOSE] 데이터베이스 연결 정리 완료")
            except:
                pass
    
    def validate_migration(self):
        """마이그레이션 결과 검증"""
        logger.info("=== 마이그레이션 결과 검증 ===")
        
        try:
            db = get_db()
            
            # 모든 필요한 컬럼이 존재하는지 확인
            missing_columns = []
            
            for column_name, _ in self.columns_to_add:
                if not self.check_column_exists(db, column_name):
                    missing_columns.append(column_name)
            
            if missing_columns:
                logger.error(f"[ERROR] 여전히 누락된 컬럼들: {missing_columns}")
                return False
            else:
                logger.info("[OK] 모든 필요한 컬럼이 존재함")
                return True
                
        except Exception as e:
            logger.error(f"[ERROR] 검증 중 오류: {str(e)}")
            return False
        finally:
            try:
                db.close()
            except:
                pass

def run_safe_migration(app_context=None):
    """안전한 마이그레이션 실행 함수"""
    migration = SafeSchemaMigration()
    
    # Flask 앱 컨텍스트가 필요한 경우 설정
    if app_context:
        with app_context:
            success = migration.execute_migration()
            if success:
                if migration.validate_migration():
                    logger.info("[SUCCESS] 마이그레이션이 성공적으로 완료되었습니다!")
                    return True
                else:
                    logger.error("[WARN] 마이그레이션 후 검증에서 문제 발견")
                    return False
            else:
                logger.error("[ERROR] 마이그레이션 실행 실패")
                return False
    else:
        # 독립 실행 모드 (Flask 앱 없이)
        try:
            from app import app
            with app.app_context():
                success = migration.execute_migration()
                if success:
                    if migration.validate_migration():
                        logger.info("[SUCCESS] 마이그레이션이 성공적으로 완료되었습니다!")
                        return True
                    else:
                        logger.error("[WARN] 마이그레이션 후 검증에서 문제 발견")
                        return False
                else:
                    logger.error("[ERROR] 마이그레이션 실행 실패")
                    return False
        except Exception as e:
            logger.error(f"[ERROR] Flask 앱 컨텍스트 설정 실패: {str(e)}")
            return False

if __name__ == "__main__":
    # 독립 실행 테스트
    run_safe_migration()