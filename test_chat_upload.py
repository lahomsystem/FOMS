"""
Quest 3 테스트: 채팅 파일 업로드 API 테스트
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Quest 3: 채팅 파일 업로드 API 테스트")
    print("=" * 60)
    
    # app.py import 테스트
    print("\n[1/2] app.py import 중...")
    from app import app, allowed_chat_file, get_chat_file_max_size
    print("[OK] app.py import 성공")
    
    # 파일 검증 함수 테스트
    print("\n[2/2] 파일 검증 함수 테스트...")
    
    # 확장자 검증
    test_files = [
        ('test.jpg', True),
        ('test.png', True),
        ('test.mp4', True),
        ('test.pdf', True),
        ('test.exe', False),
        ('test.unknown', False)
    ]
    
    for filename, expected in test_files:
        result = allowed_chat_file(filename)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"  {status} {filename} -> {result} (예상: {expected})")
    
    # 파일 크기 제한 테스트
    print("\n파일 크기 제한 테스트...")
    size_tests = [
        ('test.jpg', 10 * 1024 * 1024),  # 10MB
        ('test.mp4', 500 * 1024 * 1024),  # 500MB
        ('test.pdf', 50 * 1024 * 1024)  # 50MB
    ]
    
    for filename, expected_size in size_tests:
        max_size = get_chat_file_max_size(filename)
        status = "[OK]" if max_size == expected_size else "[FAIL]"
        print(f"  {status} {filename} -> {max_size / 1024 / 1024:.0f}MB (예상: {expected_size / 1024 / 1024:.0f}MB)")
    
    print("\n" + "=" * 60)
    print("[OK] Quest 3 테스트 완료!")
    print("=" * 60)
    print("\n다음 단계: Quest 4 (파일 다운로드 및 미리보기 API)")
    
except ImportError as e:
    print(f"\n[ERROR] Import 오류: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] 오류 발생: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
