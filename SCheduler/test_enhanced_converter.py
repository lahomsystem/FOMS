#!/usr/bin/env python3
"""
개선된 주소 변환기 성능 테스트
실제 실패했던 주소들로 성능 개선 확인
"""

from address_converter import AddressConverter
from address_learning import AddressLearningSystem
import time

def test_enhanced_converter():
    """개선된 변환기 테스트"""
    
    # 실제 실패했던 주소들 (사용자 데이터 기반)
    test_addresses = [
        "서울 강남구 역삼1동 683-26",
        "성남구 1637, 한도 파크 2단지 207-601",
        "서원 우암 주공 4단지 406-103",
        "평택 석정공원 파크드림 109-803",
        "파주시 와동마을 2단지 힐튼 매드리안 205-1008",
        "청산 사이더 헤리티지 118-2205",
        "평택시 합정지구 유앤빌 103-901",
        "종로구 대학로11길 38-10 304호",
        "영통구 대컴로 711번길 19, 새이김 2차 207-203",
        "서울 용산구 한남동 267-9번지"
    ]
    
    print("🔧 개선된 주소 변환기 성능 테스트")
    print("="*50)
    
    # 학습 시스템과 함께 초기화
    learning_system = AddressLearningSystem()
    converter = AddressConverter(learning_system)
    
    success_count = 0
    total_count = len(test_addresses)
    
    print(f"📊 테스트 대상: {total_count}개 주소")
    print()
    
    for i, address in enumerate(test_addresses):
        print(f"[{i+1:2d}/{total_count}] {address}")
        
        start_time = time.time()
        lat, lng, status = converter.convert_address(address)
        end_time = time.time()
        
        if status == "성공":
            success_count += 1
            print(f"    ✅ 성공: ({lat:.6f}, {lng:.6f}) [{end_time-start_time:.2f}초]")
        else:
            print(f"    ❌ 실패: {status} [{end_time-start_time:.2f}초]")
        
        print()
    
    # 결과 요약
    success_rate = (success_count / total_count) * 100
    print("="*50)
    print("📈 성능 테스트 결과")
    print("="*50)
    print(f"전체 주소: {total_count}개")
    print(f"변환 성공: {success_count}개")
    print(f"변환 실패: {total_count - success_count}개")
    print(f"성공률: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("\n🎉 목표 성공률 80% 달성!")
    elif success_rate >= 70:
        print("\n👍 양호한 성능 (70% 이상)")
    else:
        print("\n⚠️ 추가 개선 필요")

if __name__ == "__main__":
    test_enhanced_converter() 