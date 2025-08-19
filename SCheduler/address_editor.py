import streamlit as st
import pandas as pd
from address_converter import AddressConverter
from address_learning import AddressLearningSystem
from web_address_learner import WebAddressLearner
from advanced_address_processor import AdvancedAddressProcessor
from datetime import datetime


class AddressEditor:
    """주소 편집 및 수정 시스템 (고급 AI 처리 지원)"""
    
    def __init__(self, learning_system=None):
        """편집기 초기화"""
        self.learning_system = learning_system or AddressLearningSystem()
        self.web_learner = WebAddressLearner()
        self.address_converter = AddressConverter(self.learning_system)
        self.advanced_processor = AdvancedAddressProcessor()
    
    def show_failed_addresses_editor(self, failed_results):
        """실패한 주소들의 편집 인터페이스 표시"""
        if not failed_results:
            st.info("🎉 모든 주소 변환이 성공했습니다!")
            return []
        
        st.subheader("🔧 실패한 주소 수정하기")
        st.write(f"총 {len(failed_results)}개의 주소 변환이 실패했습니다. 직접 수정하여 다시 변환할 수 있습니다.")
        
        corrected_results = []
        
        # 실패한 주소들을 탭으로 구성
        if len(failed_results) > 5:
            # 많은 경우 페이지네이션
            corrected_results = self._show_paginated_editor(failed_results)
        else:
            # 적은 경우 탭으로 표시
            corrected_results = self._show_tabbed_editor(failed_results)
        
        return corrected_results
    
    def _show_paginated_editor(self, failed_results):
        """페이지네이션된 편집기"""
        page_size = 5
        total_pages = (len(failed_results) - 1) // page_size + 1
        
        # 페이지 선택
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            current_page = st.selectbox(
                f"페이지 선택 (총 {total_pages}페이지)",
                range(1, total_pages + 1),
                key="page_selector"
            )
        
        # 현재 페이지의 데이터
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, len(failed_results))
        current_results = failed_results[start_idx:end_idx]
        
        corrected_results = []
        
        for i, result in enumerate(current_results):
            actual_idx = start_idx + i
            corrected = self._show_single_address_editor(result, actual_idx)
            if corrected:
                corrected_results.append(corrected)
        
        return corrected_results
    
    def _show_tabbed_editor(self, failed_results):
        """탭으로 구성된 편집기"""
        tabs = st.tabs([f"주소 {i+1}" for i in range(len(failed_results))])
        
        corrected_results = []
        
        for i, (tab, result) in enumerate(zip(tabs, failed_results)):
            with tab:
                corrected = self._show_single_address_editor(result, i)
                if corrected:
                    corrected_results.append(corrected)
        
        return corrected_results
    
    def _show_single_address_editor(self, result, index):
        """개별 주소 편집 인터페이스"""
        try:
            original_address = result.get('주소', '')
            error_status = result.get('상태', '알 수 없는 오류')
            
            st.write(f"**원본 주소:** `{original_address}`")
            st.write(f"**오류 상태:** `{error_status}`")
            
            # 웹 학습 기반 제안사항 표시 (안전한 오류 처리)
            suggestions = []
            try:
                suggestions = self._get_suggestions(original_address)
            except Exception as e:
                st.warning(f"제안사항을 가져오는 중 오류가 발생했습니다: {str(e)}")
                # 기본 제안사항 제공
                suggestions = [{
                    "address": original_address,
                    "confidence": 0.5,
                    "reason": "기본 제안 (오류로 인한 대체)"
                }]
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # 제안사항 선택 또는 직접 입력
                edit_option = st.radio(
                    "수정 방법 선택:",
                    ["제안사항 선택", "직접 입력"],
                    key=f"edit_option_{index}",
                    horizontal=True
                )
                
                if edit_option == "제안사항 선택" and suggestions:
                    # 제안사항 표시
                    suggestion_options = ["선택하세요"] + [
                        f"{sug['address']} (신뢰도: {sug['confidence']:.1%}, {sug['reason']})"
                        for sug in suggestions
                    ]
                    
                    selected_suggestion = st.selectbox(
                        "제안사항 선택:",
                        suggestion_options,
                        key=f"suggestion_{index}"
                    )
                    
                    if selected_suggestion != "선택하세요":
                        # 선택된 제안사항에서 주소만 추출
                        corrected_address = selected_suggestion.split(" (신뢰도:")[0]
                    else:
                        corrected_address = ""
                else:
                    # 직접 입력
                    corrected_address = st.text_input(
                        "수정된 주소 입력:",
                        value=original_address,
                        key=f"corrected_{index}",
                        help="정확한 주소를 입력하세요"
                    )
            
            with col2:
                st.write("**🤖 AI 제안**")
                if suggestions:
                    for i, sug in enumerate(suggestions[:2]):  # 상위 2개만
                        st.write(f"**{i+1}.** {sug['address']}")
                        st.write(f"   신뢰도: {sug['confidence']:.1%}")
                        st.write(f"   이유: {sug['reason']}")
                        st.write("---")
                else:
                    st.write("제안사항이 없습니다.")

            # 변환 버튼
            if st.button(f"🚀 변환 테스트", key=f"test_{index}"):
                if corrected_address:
                    # 수정된 주소로 변환 테스트
                    lat, lng, status = self.address_converter.convert_address(corrected_address)
                    
                    if status == "성공":
                        st.success(f"✅ 변환 성공: ({lat:.6f}, {lng:.6f})")
                        
                        # 학습 시스템에 수정 사례 저장
                        self.learning_system.add_correction(original_address, corrected_address, lat, lng)
                        
                        # 결과 반환
                        return {
                            '주소': corrected_address,
                            '위도': lat,
                            '경도': lng,
                            '상태': '수동 수정 성공',
                            '원본주소': original_address,
                            '변환날짜': datetime.now().strftime('%Y-%m-%d'),
                            '변환시간': datetime.now().strftime('%H:%M:%S')
                        }
                    else:
                        st.error(f"❌ 변환 실패: {status}")
                else:
                    st.warning("⚠️ 수정된 주소를 입력하세요.")
            
            return None
            
        except Exception as e:
            st.error(f"❌ 편집기 오류: {str(e)}")
            return None
    
    def _get_suggestions(self, address):
        """주소에 대한 제안사항 가져오기 (고급 AI 분석 포함)"""
        suggestions = []
        
        try:
            # 1. 고급 AI 처리기로 스마트 분석
            advanced_result = self.advanced_processor.process_failed_address(address)
            for sug in advanced_result['suggestions']:
                suggestions.append({
                    "address": sug['address'],
                    "confidence": sug['confidence'],
                    "reason": f"🧠 AI 분석: {sug['reason']}"
                })
            
            # 2. 기존 학습 시스템에서 제안사항 가져오기
            learning_suggestions = self.learning_system.suggest_correction(address)
            for sug in learning_suggestions:
                suggestions.append({
                    "address": sug.get("suggested", sug.get("address", "")),
                    "confidence": sug.get("similarity", sug.get("confidence", 0.5)),
                    "reason": f"📚 학습 기반: {sug.get('reason', '학습된 패턴')}"
                })
        
        except Exception as e:
            st.warning(f"고급 분석 중 오류: {str(e)}")
        
        try:
            # 3. 웹 학습에서 제안사항 가져오기
            web_enhancement = self.web_learner.enhance_address_with_context(address)
            if web_enhancement:
                suggestions.append({
                    "address": web_enhancement["enhanced_address"],
                    "confidence": web_enhancement["confidence"],
                    "reason": f"🌐 웹 학습: {web_enhancement['method']}"
                })
        except Exception as e:
            pass
        
        try:
            # 4. 웹 패턴 분석 제안
            patterns = self.web_learner._extract_address_patterns(address)
            pattern_suggestions = self.web_learner._generate_suggestions(address, patterns)
            for sug in pattern_suggestions:
                suggestions.append({
                    "address": sug.get("suggested", sug.get("address", "")),
                    "confidence": sug.get("similarity", sug.get("confidence", 0.5)),
                    "reason": f"🔍 패턴 분석: {sug.get('reason', '패턴 기반')}"
                })
        except Exception as e:
            pass
        
        # 중복 제거 및 정렬
        unique_suggestions = {}
        for sug in suggestions:
            addr = sug["address"]
            if addr and addr.strip() and addr != address:
                if addr not in unique_suggestions or sug["confidence"] > unique_suggestions[addr]["confidence"]:
                    unique_suggestions[addr] = sug
        
        # 신뢰도 순으로 정렬
        sorted_suggestions = sorted(unique_suggestions.values(), key=lambda x: x["confidence"], reverse=True)
        
        return sorted_suggestions[:5]  # 최대 5개
    
    def show_batch_editor(self, failed_results):
        """일괄 편집 인터페이스"""
        st.subheader("🔄 일괄 재변환")
        
        if not failed_results:
            return []
        
        st.write("실패한 주소들을 자동으로 수정하여 재변환합니다.")
        
        # 자동 수정 옵션
        auto_fix_options = st.multiselect(
            "자동 수정 옵션 선택:",
            [
                "학습된 패턴 적용",
                "시/도명 확장", 
                "띄어쓰기 정규화",
                "웹 패턴 분석 적용",
                "랜드마크 인식"
            ],
            default=["학습된 패턴 적용", "시/도명 확장", "띄어쓰기 정규화"]
        )
        
        if st.button("🚀 일괄 재변환 시작"):
            corrected_results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, result in enumerate(failed_results):
                progress = (i + 1) / len(failed_results)
                progress_bar.progress(progress)
                status_text.text(f"처리 중... {i+1}/{len(failed_results)}")
                
                original_address = result['주소']
                
                # 자동 수정 적용
                corrected_address = self._apply_auto_corrections(
                    original_address, 
                    auto_fix_options
                )
                
                if corrected_address and corrected_address != original_address:
                    # 재변환 시도
                    lat, lng, status = self.address_converter.convert_address(corrected_address)
                    
                    if status == "성공":
                        # 학습 데이터에 추가
                        self.learning_system.add_correction(
                            original_address,
                            corrected_address,
                            lat,
                            lng
                        )
                        
                        corrected_results.append({
                            '주소': corrected_address,
                            '원본_주소': original_address,
                            '위도': lat,
                            '경도': lng,
                            '상태': '자동 수정 성공',
                            '변환날짜': result['변환날짜'],
                            '변환시간': result['변환시간'],
                            '수정_방법': '자동 수정'
                        })
            
            progress_bar.progress(1.0)
            status_text.text("✅ 일괄 처리 완료!")
            
            if corrected_results:
                st.success(f"🎉 {len(corrected_results)}개 주소가 성공적으로 수정되었습니다!")
                return corrected_results
            else:
                st.warning("⚠️ 자동 수정으로 변환된 주소가 없습니다. 수동으로 수정해주세요.")
        
        return []
    
    def _apply_auto_corrections(self, address, options):
        """자동 수정 옵션들을 적용"""
        corrected = address
        
        if "학습된 패턴 적용" in options:
            corrected = self.learning_system.preprocess_address(corrected)
        
        if "웹 패턴 분석 적용" in options:
            patterns = self.web_learner._extract_address_patterns(corrected)
            suggestions = self.web_learner._generate_suggestions(corrected, patterns)
            if suggestions:
                # 가장 신뢰도 높은 제안 적용
                best_suggestion = max(suggestions, key=lambda x: x["confidence"])
                if best_suggestion["confidence"] > 0.8:
                    corrected = best_suggestion["address"]
        
        if "랜드마크 인식" in options:
            enhancement = self.web_learner.enhance_address_with_context(corrected)
            if enhancement and enhancement["confidence"] > 0.8:
                corrected = enhancement["enhanced_address"]
        
        return corrected
    
    def show_learning_dashboard(self):
        """학습 현황 대시보드"""
        st.subheader("📊 AI 학습 현황")
        
        # 학습 통계
        learning_stats = self.learning_system.get_learning_stats()
        web_stats = self.web_learner.get_learning_summary()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "총 수정 사례",
                learning_stats["총_수정_사례"],
                help="사용자가 수정한 주소 데이터 수"
            )
        
        with col2:
            st.metric(
                "학습된 패턴",
                learning_stats["학습된_패턴"],
                help="AI가 학습한 주소 패턴 수"
            )
        
        with col3:
            st.metric(
                "웹 학습 패턴",
                web_stats["총_학습된_패턴"],
                help="웹에서 학습한 패턴 수"
            )
        
        # 최근 학습 내용
        if learning_stats["총_수정_사례"] > 0:
            with st.expander("📈 최근 학습 데이터"):
                st.write(f"**마지막 학습:** {learning_stats['마지막_학습']}")
                
                # 학습 데이터 표시 (최근 5개)
                recent_corrections = self.learning_system.learning_data.get("corrections", [])[-5:]
                if recent_corrections:
                    df = pd.DataFrame(recent_corrections)
                    st.dataframe(df[['original', 'corrected', 'timestamp']], use_container_width=True) 