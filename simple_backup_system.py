import os
import datetime
import subprocess
import shutil
import json
import glob

class SimpleBackupSystem:
    def __init__(self):
        # 백업 설정
        self.db_name = "furniture_orders"
        self.db_user = "postgres"
        self.db_pass = "postgres"
        self.db_host = "localhost"
        # PostgreSQL 설치 경로 확인 (버전에 따라 다를 수 있음)
        possible_paths = [
            r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
            r"C:\Program Files\PostgreSQL\15\bin\pg_dump.exe", 
            r"C:\Program Files\PostgreSQL\14\bin\pg_dump.exe",
            r"C:\Program Files\PostgreSQL\13\bin\pg_dump.exe"
        ]
        
        self.pg_dump_path = None
        for path in possible_paths:
            if os.path.exists(path):
                self.pg_dump_path = path
                break
        
        if not self.pg_dump_path:
            self.pg_dump_path = r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"  # 기본값
        
        # 백업 경로 설정
        self.tier1_path = "backups/tier1_primary"  # 1차: 로컬 백업
        self.tier2_path = "backups/tier2_secondary" # 2차: 다른 폴더
        
        # 백업할 파일들
        self.source_files = [
            "app.py",
            "models.py", 
            "db.py",
            "templates/",
            "static/",
            "requirements.txt",
            "menu_config.json"
        ]
    
    def create_backup_directories(self):
        """백업 디렉토리 생성"""
        # 1차 백업 디렉토리 (항상 생성)
        os.makedirs(self.tier1_path, exist_ok=True)
        print(f"✅ 백업 디렉토리 준비: {self.tier1_path}")
        
        # 2차 백업 디렉토리 (다른 폴더)
        try:
            os.makedirs(self.tier2_path, exist_ok=True)
            print(f"✅ 백업 디렉토리 준비: {self.tier2_path}")
        except Exception as e:
            print(f"⚠️ 2차 백업 디렉토리 생성 실패: {e}")
    
    def backup_database(self, backup_dir):
        """PostgreSQL 데이터베이스 백업"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"database_backup_{timestamp}.sql")
        
        # pg_dump 명령어 구성
        command = [
            self.pg_dump_path,
            "-U", self.db_user,
            "-d", self.db_name, 
            "-h", self.db_host,
            "-f", backup_file,
            "--encoding=UTF8"
        ]
        
        # 비밀번호 환경변수 설정
        env = os.environ.copy()
        env["PGPASSWORD"] = self.db_pass
        
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
            print(f"✅ 데이터베이스 백업 완료: {backup_file}")
            return backup_file
        except subprocess.CalledProcessError as e:
            print(f"❌ 데이터베이스 백업 실패: {e}")
            if e.stderr:
                print(f"에러 상세: {e.stderr}")
            return None
        except FileNotFoundError:
            print(f"❌ pg_dump 실행 파일을 찾을 수 없습니다: {self.pg_dump_path}")
            print("PostgreSQL이 설치되어 있고 경로가 올바른지 확인해주세요.")
            return None
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {e}")
            return None
    
    def backup_files(self, backup_dir):
        """시스템 파일들 백업"""
        files_dir = os.path.join(backup_dir, "system_files")
        os.makedirs(files_dir, exist_ok=True)
        
        backed_up_files = []
        
        for item in self.source_files:
            if os.path.exists(item):
                try:
                    if os.path.isfile(item):
                        # 파일 복사
                        dest_file = os.path.join(files_dir, os.path.basename(item))
                        shutil.copy2(item, dest_file)
                        backed_up_files.append(item)
                    elif os.path.isdir(item):
                        # 디렉토리 복사
                        dest_dir = os.path.join(files_dir, item)
                        if os.path.exists(dest_dir):
                            shutil.rmtree(dest_dir)
                        shutil.copytree(item, dest_dir)
                        backed_up_files.append(item)
                except Exception as e:
                    print(f"⚠️ 파일 백업 실패: {item} - {e}")
            else:
                print(f"⚠️ 파일이 존재하지 않음: {item}")
        
        print(f"✅ 시스템 파일 백업 완료: {len(backed_up_files)}개 항목")
        return backed_up_files
    
    def create_recovery_script(self, backup_dir, db_backup_file):
        """복구 스크립트 생성"""
        script_content = f'''@echo off
echo 🚨 FOMS 시스템 복구 스크립트
echo 실행 전 PostgreSQL 서비스가 실행 중인지 확인하세요.
echo.
echo 현재 백업 위치: {backup_dir}
echo 데이터베이스 백업 파일: {os.path.basename(db_backup_file)}
echo.
pause

echo 데이터베이스 복구를 시작합니다...
set PGPASSWORD={self.db_pass}

REM 기존 데이터베이스 삭제 (주의: 모든 데이터가 삭제됩니다!)
psql -U {self.db_user} -h {self.db_host} -c "DROP DATABASE IF EXISTS {self.db_name};" postgres

REM 새 데이터베이스 생성
psql -U {self.db_user} -h {self.db_host} -c "CREATE DATABASE {self.db_name};" postgres

REM 백업 데이터 복원
psql -U {self.db_user} -h {self.db_host} -d {self.db_name} -f "{db_backup_file}"

echo 데이터베이스 복구가 완료되었습니다!
echo.
echo 시스템 파일들을 수동으로 복원하려면:
echo 1. system_files 폴더의 내용을 프로젝트 루트로 복사
echo 2. app.py를 재시작
echo.
pause
'''
        
        script_file = os.path.join(backup_dir, "🔧_복구_스크립트.bat")
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        print(f"✅ 복구 스크립트 생성: {script_file}")
        return script_file
    
    def create_backup_info(self, backup_dir, db_file, system_files):
        """백업 정보 파일 생성"""
        info = {
            "backup_time": datetime.datetime.now().isoformat(),
            "database_file": os.path.basename(db_file) if db_file else None,
            "system_files": system_files,
            "backup_location": backup_dir,
            "database_size": os.path.getsize(db_file) if db_file and os.path.exists(db_file) else 0
        }
        
        info_file = os.path.join(backup_dir, "backup_info.json")
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        
        return info
    
    def execute_backup(self):
        """전체 백업 실행"""
        print("🚨 FOMS 시스템 백업을 시작합니다...")
        print("=" * 50)
        
        # 백업 디렉토리 생성
        self.create_backup_directories()
        
        results = {
            "tier1": {"success": False, "path": self.tier1_path},
            "tier2": {"success": False, "path": self.tier2_path}
        }
        
        # 1차 백업 (로컬)
        print("\n📁 1차 백업 (로컬) 실행 중...")
        try:
            db_file = self.backup_database(self.tier1_path)
            system_files = self.backup_files(self.tier1_path)
            
            if db_file:
                self.create_recovery_script(self.tier1_path, db_file)
                info = self.create_backup_info(self.tier1_path, db_file, system_files)
                results["tier1"]["success"] = True
                results["tier1"]["info"] = info
                print("✅ 1차 백업 완료!")
            else:
                print("❌ 1차 백업 실패 (데이터베이스)")
        except Exception as e:
            print(f"❌ 1차 백업 중 오류: {e}")
        
        # 2차 백업 (다른 폴더)
        print("\n💾 2차 백업 (다른 폴더) 실행 중...")
        try:
            db_file = self.backup_database(self.tier2_path)
            system_files = self.backup_files(self.tier2_path)
            
            if db_file:
                self.create_recovery_script(self.tier2_path, db_file)
                info = self.create_backup_info(self.tier2_path, db_file, system_files)
                results["tier2"]["success"] = True 
                results["tier2"]["info"] = info
                print("✅ 2차 백업 완료!")
            else:
                print("❌ 2차 백업 실패 (데이터베이스)")
        except Exception as e:
            print(f"❌ 2차 백업 중 오류: {e}")
        
        # 결과 리포트
        print("\n" + "=" * 50)
        print("📊 백업 결과 리포트")
        print("=" * 50)
        
        success_count = sum(1 for r in results.values() if r["success"])
        
        for tier, result in results.items():
            status = "✅ 성공" if result["success"] else "❌ 실패"
            print(f"{tier.upper()}: {status} - {result['path']}")
            
            if result["success"] and "info" in result:
                size_mb = result["info"]["database_size"] / (1024*1024)
                print(f"   📁 데이터베이스 크기: {size_mb:.2f} MB")
                print(f"   📄 시스템 파일: {len(result['info']['system_files'])}개")
        
        print(f"\n🎯 백업 성공률: {success_count}/2 ({success_count*50}%)")
        
        if success_count > 0:
            print("\n✅ 백업이 완료되었습니다!")
            print("복구가 필요할 때는 각 백업 폴더의 '🔧_복구_스크립트.bat'를 실행하세요.")
        else:
            print("\n❌ 모든 백업이 실패했습니다. 시스템 설정을 확인해주세요.")
        
        return results

if __name__ == "__main__":
    try:
        backup_system = SimpleBackupSystem()
        backup_system.execute_backup()
    except Exception as e:
        print(f"백업 실행 중 오류 발생: {e}")
        input("엔터키를 눌러 종료하세요...")  # 콘솔 창이 바로 닫히지 않도록 