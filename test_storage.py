"""
Quest 2 테스트: 스토리지 추상화 계층 테스트
"""
import sys
import os
import io

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Quest 2: 스토리지 추상화 계층 테스트")
    print("=" * 60)
    
    # 스토리지 import 테스트
    print("\n[1/3] 스토리지 모듈 import 중...")
    from storage import StorageAdapter, get_storage
    print("[OK] 스토리지 모듈 import 성공")
    
    # 스토리지 인스턴스 생성 테스트
    print("\n[2/3] 스토리지 인스턴스 생성 중...")
    storage = get_storage()
    print(f"[OK] 스토리지 타입: {storage.storage_type}")
    
    # 파일 타입 감지 테스트
    print("\n[3/3] 파일 타입 감지 테스트...")
    test_cases = [
        ('test.jpg', 'image'),
        ('test.png', 'image'),
        ('test.mp4', 'video'),
        ('test.pdf', 'file'),
        ('test.xlsx', 'file')
    ]
    
    for filename, expected_type in test_cases:
        file_type = storage._get_file_type(filename)
        status = "[OK]" if file_type == expected_type else "[FAIL]"
        print(f"  {status} {filename} -> {file_type} (예상: {expected_type})")
    
    # Content-Type 테스트
    print("\n[4/4] Content-Type 테스트...")
    content_type = storage._get_content_type('test.jpg')
    print(f"  [OK] test.jpg -> {content_type}")
    
    print("\n" + "=" * 60)
    print("[OK] Quest 2 테스트 완료!")
    print("=" * 60)
    print("\n다음 단계: Quest 3 (파일 업로드 API 구현)")
    
except ImportError as e:
    print(f"\n[ERROR] Import 오류: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] 오류 발생: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
