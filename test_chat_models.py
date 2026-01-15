"""
Quest 1 테스트: 채팅 모델 import 및 구조 확인
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Quest 1: 채팅 모델 테스트")
    print("=" * 60)
    
    # 모델 import 테스트
    print("\n[1/3] 모델 import 중...")
    from models import ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment
    print("[OK] 모든 채팅 모델 import 성공")
    
    # 모델 구조 확인
    print("\n[2/3] 모델 구조 확인 중...")
    
    # ChatRoom
    print(f"  - ChatRoom 테이블명: {ChatRoom.__tablename__}")
    print(f"    컬럼 수: {len(ChatRoom.__table__.columns)}")
    
    # ChatRoomMember
    print(f"  - ChatRoomMember 테이블명: {ChatRoomMember.__tablename__}")
    print(f"    컬럼 수: {len(ChatRoomMember.__table__.columns)}")
    
    # ChatMessage
    print(f"  - ChatMessage 테이블명: {ChatMessage.__tablename__}")
    print(f"    컬럼 수: {len(ChatMessage.__table__.columns)}")
    
    # ChatAttachment
    print(f"  - ChatAttachment 테이블명: {ChatAttachment.__tablename__}")
    print(f"    컬럼 수: {len(ChatAttachment.__table__.columns)}")
    
    # 관계 확인
    print("\n[3/3] 모델 관계 확인 중...")
    print(f"  - ChatRoom.messages: {hasattr(ChatRoom, 'messages')}")
    print(f"  - ChatRoom.members: {hasattr(ChatRoom, 'members')}")
    print(f"  - ChatMessage.room: {hasattr(ChatMessage, 'room')}")
    print(f"  - ChatMessage.user: {hasattr(ChatMessage, 'user')}")
    print(f"  - ChatAttachment.message: {hasattr(ChatAttachment, 'message')}")
    
    print("\n" + "=" * 60)
    print("[OK] Quest 1 테스트 완료!")
    print("=" * 60)
    print("\n다음 단계: Quest 2 (스토리지 추상화 계층 구현)")
    
except ImportError as e:
    print(f"\n[ERROR] Import 오류: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] 오류 발생: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
