from sqlalchemy import text
from flask import Flask
import db
from app import app

def reset_order_sequence():
    """orders 테이블 시퀀스를 안전하게 초기화
    
    Returns:
        bool: 성공시 True, 실패시 False
    """
    # 애플리케이션 컨텍스트 생성
    with app.app_context():
        db_session = db.get_db()
        
        try:
            print("orders 테이블 시퀀스 초기화 시작...")
            
            # 현재 시퀀스 상태 확인
            seq_query = "SELECT pg_get_serial_sequence('orders', 'id')"
            seq_name = db_session.execute(text(seq_query)).scalar()
            
            if seq_name:
                print(f"orders 테이블의 시퀀스 이름: {seq_name}")
                
                # 시퀀스 이름으로 현재 값 확인
                curr_val_query = f"SELECT last_value FROM {seq_name}"
                curr_val = db_session.execute(text(curr_val_query)).scalar()
                print(f"현재 시퀀스 값: {curr_val}")
                
                # 모든 주문의 최대 ID 값 확인
                max_id_query = "SELECT COALESCE(MAX(id), 0) FROM orders WHERE status != 'DELETED'"
                max_id = db_session.execute(text(max_id_query)).scalar()
                print(f"삭제되지 않은 주문의 최대 ID 값: {max_id}")
                
                # 시퀀스 값을 최대 ID + 1로 설정
                next_id = max_id + 1
                alter_seq_query = f"ALTER SEQUENCE {seq_name} RESTART WITH {next_id}"
                db_session.execute(text(alter_seq_query))
                db_session.commit()
                
                # 설정 후 다시 확인
                after_val_query = f"SELECT last_value FROM {seq_name}"
                after_val = db_session.execute(text(after_val_query)).scalar()
                print(f"설정 후 시퀀스 값: {after_val}")
                
                # 여러 시퀀스 명칭으로도 체크 및 리셋 시도
                possible_sequences = ['orders_id_seq', 'orders_id_seq1']
                for seq in possible_sequences:
                    try:
                        # 시퀀스가 존재하는지 확인
                        exists_query = f"SELECT EXISTS(SELECT 1 FROM pg_sequences WHERE sequencename = '{seq}')"
                        exists = db_session.execute(text(exists_query)).scalar()
                        
                        if exists:
                            print(f"추가 시퀀스 발견: {seq}")
                            # 시퀀스 재설정
                            alter_query = f"ALTER SEQUENCE {seq} RESTART WITH {next_id}"
                            db_session.execute(text(alter_query))
                            db_session.commit()
                            print(f"{seq} 시퀀스가 {next_id}로 재설정되었습니다.")
                    except Exception as e:
                        print(f"⚠️ {seq} 시퀀스 재설정 실패: {str(e)}")
            
                print("✅ orders 테이블 시퀀스 초기화 완료!")
                print(f"⚠️ 주의: 다음 주문 ID는 {next_id}부터 시작합니다.")
                return True
            else:
                print("❌ orders 테이블의 시퀀스를 찾을 수 없습니다.")
                return False
            
        except Exception as e:
            db_session.rollback()
            print(f"❌ 오류 발생: {str(e)}")
            print("데이터베이스 변경사항이 롤백되었습니다.")
            return False

if __name__ == "__main__":
    print("⚠️ 경고: 이 스크립트는 orders 테이블의 시퀀스를 초기화합니다! ⚠️")
    print("데이터를 삭제하지 않고 시퀀스만 초기화합니다.")
    confirm = input("계속하려면 'YES'를 입력하세요: ")
    
    if confirm.upper() != 'YES':
        print("작업이 취소되었습니다.")
    else:
        success = reset_order_sequence()
        if success:
            print("\n✅ 시퀀스 초기화가 성공적으로 완료되었습니다.")
        else:
            print("\n❌ 시퀀스 초기화 중 오류가 발생했습니다. 로그를 확인해주세요.") 