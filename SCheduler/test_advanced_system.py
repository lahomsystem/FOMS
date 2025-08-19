#!/usr/bin/env python3
"""
고급 AI 시스템 통합 테스트
실패했던 주소들에 대한 고급 제안사항 생성 테스트
"""

from advanced_address_processor import AdvancedAddressProcessor
from address_editor import AddressEditor
from address_learning import AddressLearningSystem
import time

def test_advanced_suggestions():
    """고급 제안 시스템 테스트"""
    
    # 실제 실패했던 주소들
    test_addresses = [
        "성남구 1637, 한도 파크 2단지 207-601",
        "서원 우암 주공 4단지 406-103", 
        "평택 석정공원 파크드림 109-803",
        "파주시 와동마을 2단지 힐튼 매드리안 205-1008",
        "청산 사이더 헤리티지 118-2205",
        "평택시 합정지구 유앤빌 103-901",
        "영통구 대컴로 711번길 19, 새이김 2차 207-203"
    ]
    
    print("🧠 고급 AI 시스템 제안사항 테스트")
    print("="*60)
    
    # 고급 처리기 및 편집기 초기화
    advanced_processor = AdvancedAddressProcessor()
    learning_system = AddressLearningSystem()
    editor = AddressEditor(learning_system)
    
    for i, address in enumerate(test_addresses):
        print(f"\n[{i+1}] 원본 주소: {address}")
        print("-" * 40)
        
        # 1. 고급 AI 분석
        start_time = time.time()
        advanced_result = advanced_processor.process_failed_address(address)
        analysis_time = time.time() - start_time
        
        print(f"🔍 구성요소 분석 (소요시간: {analysis_time:.2f}초):")
        components = advanced_result['components']
        print(f"  • 시/도: {components.get('city', '❌ 누락')}")
        print(f"  • 구/시: {components.get('district', '❌ 불명확')}")
        print(f"  • 동: {components.get('dong', '❌ 없음')}")
        print(f"  • 건물: {components.get('building', '❌ 없음')}")
        print(f"  • 상세: {components.get('detail', '❌ 없음')}")
        print(f"  • 문제점: {', '.join(components['issues']) if components['issues'] else '없음'}")
        
        # 2. 통합 제안사항
        print(f"\n💡 AI 제안사항 ({len(advanced_result['suggestions'])}개):")
        for j, suggestion in enumerate(advanced_result['suggestions']):
            print(f"  {j+1}. {suggestion['address']}")
            print(f"     신뢰도: {suggestion['confidence']:.1%} | 이유: {suggestion['reason']}")
            print(f"     변경사항: {', '.join(suggestion['changes'])}")
        
        # 3. 편집기 통합 제안
        print(f"\n🎯 편집기 통합 제안:")
        try:
            editor_suggestions = editor._get_suggestions(address)
            for j, sug in enumerate(editor_suggestions[:3]):
                print(f"  {j+1}. {sug['address']}")
                print(f"     신뢰도: {sug['confidence']:.1%} | {sug['reason']}")
        except Exception as e:
            print(f"  ❌ 편집기 오류: {e}")
        
        print("\n" + "="*60)
    
    print("\n🎉 고급 AI 시스템 테스트 완료!")
    print("실제 시스템에서 이 제안사항들을 사용하여 수동 교정 가능")

def test_single_address_detailed():
    """단일 주소 상세 분석"""
    address = "성남구 1637, 한도 파크 2단지 207-601"
    
    print(f"\n🔬 상세 분석: {address}")
    print("="*50)
    
    processor = AdvancedAddressProcessor()
    result = processor.process_failed_address(address)
    
    print("📊 분석 결과:")
    print(f"  • 처리된 제안사항: {result['analysis']['suggestions_generated']}개")
    print(f"  • 발견된 문제점: {result['analysis']['issues_found']}개")
    print(f"  • 처리 전략: {result['analysis']['processing_strategy']}")
    
    print("\n🎯 최고 신뢰도 제안:")
    if result['suggestions']:
        best = result['suggestions'][0]
        print(f"  주소: {best['address']}")
        print(f"  신뢰도: {best['confidence']:.1%}")
        print(f"  이유: {best['reason']}")
        print(f"  변경: {', '.join(best['changes'])}")

if __name__ == "__main__":
    test_advanced_suggestions()
    test_single_address_detailed() 