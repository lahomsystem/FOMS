import os
import datetime
import subprocess

# --- 설정 ---
BACKUP_DIR = "backups"  # 백업 파일을 저장할 디렉토리
DB_NAME = "furniture_orders"
DB_USER = "postgres"
DB_PASS = "postgres"  # 실제 운영 환경에서는 환경 변수나 다른 보안 방법을 사용하세요.
DB_HOST = "localhost"
PG_DUMP_PATH = r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"

# --- 스크립트 본문 ---
def create_backup():
    """PostgreSQL 데이터베이스를 백업하는 함수"""
    # 백업 디렉토리가 없으면 생성
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"'{BACKUP_DIR}' 디렉토리를 생성했습니다.")

    # 타임스탬프를 포함한 파일명 생성
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file_name = f"backup_{timestamp}.sql"
    backup_file_path = os.path.join(BACKUP_DIR, backup_file_name)

    # pg_dump 명령어 생성
    # PGPASSWORD 환경 변수를 사용하여 비밀번호를 안전하게 전달
    command = [
        PG_DUMP_PATH,
        "-U", DB_USER,
        "-d", DB_NAME,
        "-h", DB_HOST,
        "-f", backup_file_path,
        "--encoding=UTF8" # UTF-8 인코딩 명시
    ]

    # 비밀번호를 환경 변수로 설정
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS

    try:
        print(f"백업을 시작합니다 -> {backup_file_path}")
        # pg_dump 명령어 실행
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
            encoding='utf-8' # 프로세스 출력 인코딩 설정
        )
        print("백업이 성공적으로 완료되었습니다.")
        
    except subprocess.CalledProcessError as e:
        print("백업 실패: 오류가 발생했습니다.")
        print(f"오류 코드: {e.returncode}")
        print(f"오류 메시지 (stdout): {e.stdout}")
        print(f"오류 메시지 (stderr): {e.stderr}")
    except FileNotFoundError:
        print(f"오류: '{PG_DUMP_PATH}' 경로에서 pg_dump 실행 파일을 찾을 수 없습니다.")
        print("PostgreSQL 설치 경로를 확인하고 PG_DUMP_PATH 변수를 수정해주세요.")
    except Exception as e:
        print(f"예상치 못한 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    create_backup() 