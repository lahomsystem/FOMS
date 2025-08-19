import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime, date
from streamlit_folium import st_folium
import folium
from folium import plugins

from address_converter import AddressConverter
from map_generator import MapGenerator
from address_learning import AddressLearningSystem
from address_editor import AddressEditor
from web_address_learner import WebAddressLearner


# 페이지 설정
st.set_page_config(
    page_title="주소 변환 시스템",
    page_icon="📍",
    layout="wide"
)

# 제목 및 설명
st.title("📍 주소 변환 시스템")
st.write("Excel 업로드 → 날짜 선택 → 주소 변환 → 지도 표시")

# 사이드바 설정
st.sidebar.header("⚙️ 설정")

# 지도 크기 설정 추가
st.sidebar.subheader("🗺️ 지도 크기 설정")
map_size_options = {
    "작게 (600x400)": (600, 400),
    "보통 (800x600)": (800, 600), 
    "크게 (1000x700)": (1000, 700),
    "매우 크게 (1200x800)": (1200, 800),
    "전체화면 (1400x900)": (1400, 900)
}

selected_size = st.sidebar.selectbox(
    "지도 크기를 선택하세요:",
    options=list(map_size_options.keys()),
    index=3,  # 기본값: 매우 크게 (1200x800)
    key="map_size_selector"  # 고유 키 추가
)

map_width, map_height = map_size_options[selected_size]

# 전체화면 모드 추가
fullscreen_mode = st.sidebar.checkbox(
    "🖥️ 전체화면 지도 모드",
    help="지도를 브라우저 전체 크기로 표시합니다",
    key="fullscreen_map_mode"
)

if fullscreen_mode:
    map_width, map_height = "100%", "100vh"

# 세션 상태 초기화
if 'conversion_results' not in st.session_state:
    st.session_state.conversion_results = None

if 'corrected_results' not in st.session_state:
    st.session_state.corrected_results = []

# AI 학습 시스템 초기화
@st.cache_resource
def initialize_ai_systems():
    learning_system = AddressLearningSystem()
    converter = AddressConverter(learning_system)
    editor = AddressEditor(learning_system)
    web_learner = WebAddressLearner()
    return learning_system, converter, editor, web_learner

learning_system, converter, editor, web_learner = initialize_ai_systems()

# 1단계: Excel 파일 업로드
st.header("1️⃣ Excel 파일 업로드")
uploaded_file = st.file_uploader(
    "Excel 파일을 선택하세요",
    type=['xlsx'],
    help="주소 정보가 포함된 .xlsx 파일을 업로드하세요"
)

if uploaded_file is not None:
    try:
        # Excel 파일 읽기
        df = pd.read_excel(uploaded_file)
        
        st.success(f"✅ 파일 업로드 완료: {len(df)}행 {len(df.columns)}열")
        
        # 컬럼 정보 표시
        st.write("**📋 컬럼 정보:**")
        st.write(f"컬럼: {', '.join(df.columns.tolist())}")
        
        # 미리보기
        with st.expander("📖 데이터 미리보기 (처음 5행)"):
            st.dataframe(df.head())
        
        # 컬럼 자동 감지
        address_columns = [col for col in df.columns 
                          if '주소' in col or 'address' in col.lower()]
        date_columns = [col for col in df.columns 
                       if '날짜' in col or 'date' in col.lower() or '일자' in col]
        
        # 주소 컬럼 선택
        st.header("2️⃣ 컬럼 선택")
        
        if address_columns:
            address_col = st.selectbox(
                "📍 주소 컬럼을 선택하세요:",
                address_columns,
                help="주소 정보가 포함된 컬럼을 선택하세요",
                key="address_col_filtered"
            )
        else:
            address_col = st.selectbox(
                "📍 주소 컬럼을 선택하세요:",
                df.columns.tolist(),
                help="주소 정보가 포함된 컬럼을 선택하세요",
                key="address_col_all"
            )
        
        # 날짜 컬럼 선택 및 필터링
        if date_columns:
            st.subheader("📅 날짜 필터링")
            
            date_col = st.selectbox(
                "날짜 컬럼을 선택하세요:",
                date_columns,
                help="날짜 정보가 포함된 컬럼을 선택하세요",
                key="date_col_selector"
            )
            
            # 날짜 컬럼 변환 (Arrow 호환성 개선)
            try:
                # 먼저 문자열로 변환하여 Arrow 호환성 확보
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                # NaT 값을 None으로 변경
                df[date_col] = df[date_col].where(pd.notna(df[date_col]), None)
                # 날짜 표시용으로 문자열 변환 (Arrow 호환)
                df[f'{date_col}_display'] = df[date_col].dt.strftime('%Y-%m-%d').fillna('')
            except Exception as e:
                st.warning(f"⚠️ 날짜 변환 중 오류: {str(e)}")
                df[f'{date_col}_display'] = df[date_col].astype(str)
            
            # 유효한 날짜 범위 확인
            valid_dates = df[date_col].dropna()
            if len(valid_dates) > 0:
                min_date = valid_dates.min().date()
                max_date = valid_dates.max().date()
                
                st.info(f"📊 날짜 범위: {min_date} ~ {max_date}")
                
                # 날짜 선택
                selected_date = st.date_input(
                    "변환할 날짜를 선택하세요:",
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                    key="selected_date_input"
                )
                
                # 날짜로 필터링
                filtered_df = df[df[date_col].dt.date == selected_date]
                
                if len(filtered_df) > 0:
                    st.success(f"✅ 선택한 날짜의 데이터: {len(filtered_df)}건")
                    
                    # 필터링된 데이터 미리보기
                    with st.expander("📖 필터링된 데이터 미리보기"):
                        st.dataframe(filtered_df[[address_col, date_col]].head())
                else:
                    st.warning("⚠️ 선택한 날짜에 해당하는 데이터가 없습니다.")
                    filtered_df = pd.DataFrame()
            else:
                st.error("❌ 유효한 날짜 데이터가 없습니다.")
                filtered_df = pd.DataFrame()
        else:
            st.info("📌 날짜 컬럼이 없어 전체 주소를 변환합니다.")
            filtered_df = df
            selected_date = date.today()
        
        # 3단계: 주소 변환
        if not filtered_df.empty:
            st.header("3️⃣ 주소 변환")
            
            # 변환할 주소 목록
            addresses_to_convert = filtered_df[address_col].dropna().tolist()
            
            st.info(f"🔄 변환할 주소: {len(addresses_to_convert)}개")
            
            if st.button("🚀 주소 변환 시작", type="primary", key="start_conversion_btn"):
                if len(addresses_to_convert) > 0:
                    # 변환 시작 (AI 학습 시스템 포함)
                    
                    # 진행률 표시
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("주소 변환 중..."):
                        results = []
                        total = len(addresses_to_convert)
                        
                        for i, address in enumerate(addresses_to_convert):
                            # 진행률 업데이트
                            progress = (i + 1) / total
                            progress_bar.progress(progress)
                            status_text.text(f"변환 중... {i+1}/{total} ({progress:.1%})")
                            
                            # 주소 변환
                            lat, lng, status = converter.convert_address(address)
                            
                            result = {
                                '주소': address,
                                '위도': lat,
                                '경도': lng,
                                '상태': status,
                                '변환날짜': selected_date.strftime('%Y-%m-%d'),
                                '변환시간': datetime.now().strftime('%H:%M:%S')
                            }
                            results.append(result)
                    
                    # 결과 저장
                    st.session_state.conversion_results = results
                    
                    # 변환 완료
                    progress_bar.progress(1.0)
                    status_text.text("✅ 변환 완료!")
                    
                    # 결과 통계
                    success_count = sum(1 for r in results if r['상태'] == '성공')
                    success_rate = (success_count / len(results)) * 100 if results else 0
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("전체 주소", len(results))
                    with col2:
                        st.metric("변환 성공", success_count)
                    with col3:
                        st.metric("성공률", f"{success_rate:.1f}%")
                else:
                    st.warning("⚠️ 변환할 주소가 없습니다.")
        
        # 변환 결과 표시 및 다운로드
        if st.session_state.conversion_results:
            st.header("4️⃣ 변환 결과")
            
            results_df = pd.DataFrame(st.session_state.conversion_results)
            
            # 결과 데이터프레임 표시
            st.dataframe(results_df, use_container_width=True)
            
            # Excel 다운로드
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                results_df.to_excel(writer, index=False, sheet_name='변환결과')
            excel_data = excel_buffer.getvalue()
            
            st.download_button(
                label="📥 결과 다운로드 (Excel)",
                data=excel_data,
                file_name=f"주소변환결과_{selected_date.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # 5단계: 지도 표시 (AI 편집 결과 포함)
            st.header("5️⃣ 지도 표시")
            
            # 지도 새로고침 버튼
            if st.button("🔄 지도 새로고침", help="AI 편집 후 지도를 업데이트합니다", key="refresh_map_btn"):
                st.rerun()
            
            # === 디버그 정보 표시 ===
            with st.expander("🔍 디버그 정보", expanded=False):
                st.write("**세션 상태 정보:**")
                st.write(f"- 원본 변환 결과 개수: {len(st.session_state.conversion_results) if st.session_state.conversion_results else 0}")
                st.write(f"- AI 편집 결과 개수: {len(st.session_state.corrected_results)}")
                
                if st.session_state.conversion_results:
                    original_success = [r for r in st.session_state.conversion_results if r['상태'] == '성공']
                    original_failed = [r for r in st.session_state.conversion_results if r['상태'] != '성공']
                    st.write(f"- 원본 성공: {len(original_success)}개")
                    st.write(f"- 원본 실패: {len(original_failed)}개")
                    
                    st.write("**원본 성공 주소 목록:**")
                    for i, r in enumerate(original_success, 1):
                        st.write(f"  {i}. {r['주소']} → ({r['위도']:.6f}, {r['경도']:.6f})")
                
                if st.session_state.corrected_results:
                    corrected_success = [r for r in st.session_state.corrected_results if '성공' in r['상태']]
                    st.write(f"- AI 편집 성공: {len(corrected_success)}개")
                    
                    st.write("**AI 편집 성공 주소 목록:**")
                    for i, r in enumerate(corrected_success, 1):
                        st.write(f"  {i}. {r['주소']} → ({r['위도']:.6f}, {r['경도']:.6f})")
            
            # 지도 표시용 데이터 준비: 원본 성공 + 수정된 실패 주소들
            original_success = [r for r in st.session_state.conversion_results if r['상태'] == '성공']
            corrected_success = [r for r in st.session_state.corrected_results if '성공' in r['상태']]
            
            # 중복 제거 (원본 성공 주소는 그대로, 실패했던 주소 중 수정 성공한 것만 추가)
            unique_success_results = []
            original_addresses = {r['주소'] for r in original_success}
            
            # 1. 원본 성공 주소들 먼저 추가
            unique_success_results.extend(original_success)
            
            # 2. 원본에서 실패했지만 수정으로 성공한 주소들만 추가
            for corrected in corrected_success:
                if corrected['주소'] not in original_addresses:
                    unique_success_results.append(corrected)
            
            # 디버그 정보 업데이트
            total_original = len(st.session_state.conversion_results)
            original_success_count = len(original_success)
            corrected_success_count = len(corrected_success)
            final_display_count = len(unique_success_results)
            
            st.write(f"🔍 **디버그**: 원본 {total_original}개 (성공 {original_success_count}개), AI수정 {corrected_success_count}개, 지도표시 {final_display_count}개")
            
            if unique_success_results:
                map_generator = MapGenerator()
                folium_map = map_generator.create_map(unique_success_results, width=map_width, height=map_height)
                
                if folium_map:
                    st.success(f"🗺️ 총 {len(unique_success_results)}개 위치를 지도에 표시합니다.")
                    if corrected_success_count > 0:
                        st.info(f"📍 원본 성공: {original_success_count}개 | 🧠 AI 수정 성공: {corrected_success_count}개 | 📊 지도 표시: {len(unique_success_results)}개")
                    
                    # 지도 표시 (크기 변경 즉시 반영)
                    if fullscreen_mode:
                        map_key = f"fullscreen_map_{len(unique_success_results)}_{selected_size}"
                        st_folium(folium_map, width="100%", height=800, key=map_key)
                    else:
                        map_key = f"normal_map_{map_width}x{map_height}_{len(unique_success_results)}_{selected_size}"
                        st_folium(folium_map, width=map_width, height=map_height, key=map_key)
                else:
                    st.error("❌ 지도를 생성할 수 없습니다.")
            else:
                st.warning("⚠️ 지도에 표시할 성공한 좌표가 없습니다.")
            
            # 지도와 AI 편집 시스템 사이의 여백 완전 제거 (항상 적용)
            st.markdown(f"""
                <style>
                    /* 강력한 여백 제거 - 전체화면 모드와 관계없이 항상 적용 */
                    div[data-testid="stVerticalBlock"] > div:has(iframe),
                    .element-container:has(iframe),
                    .stApp div:has(iframe) {{
                        margin-bottom: -50px !important;
                        margin-top: -20px !important;
                        padding-bottom: 0 !important;
                        padding-top: 0 !important;
                    }}
                    
                    /* 지도 다음 요소의 마진 제거 - 항상 적용 */
                    div[data-testid="stVerticalBlock"] > div:has(iframe) + div,
                    div[data-testid="stVerticalBlock"] > div:has(iframe) + div > div,
                    .element-container:has(iframe) + .element-container,
                    .stApp div:has(iframe) + div {{
                        margin-top: -50px !important;
                        padding-top: 0 !important;
                    }}
                    
                    /* Streamlit 기본 여백 줄이기 */
                    .main .block-container {{
                        padding-top: 1rem;
                        padding-bottom: 0.5rem;
                        max-width: 100%;
                    }}
                    
                    /* 헤더 간 간격 줄이기 */
                    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
                        margin-top: 0.5rem !important;
                        margin-bottom: 0.5rem !important;
                    }}
                    
                    /* 폴리움 맵 컨테이너 직접 조정 - 항상 적용 */
                    .folium-map {{
                        margin-bottom: 0 !important;
                        padding-bottom: 0 !important;
                    }}
                    
                    /* iframe 자체 스타일 조정 */
                    iframe {{
                        margin-bottom: 0 !important;
                        padding-bottom: 0 !important;
                    }}
                    
                    /* 전체화면 모드 전용 스타일 */
                    {"" if not fullscreen_mode else '''
                    .stApp > div[data-testid="stVerticalBlock"] > div:has(iframe) {
                        width: 100vw !important;
                        height: 90vh !important;
                        margin-left: -1rem !important;
                        margin-right: -1rem !important;
                        margin-bottom: -60px !important;
                    }
                    .stApp > div[data-testid="stVerticalBlock"] > div:has(iframe) iframe {
                        width: 100% !important;
                        height: 90vh !important;
                    }
                    '''}
                </style>
            """, unsafe_allow_html=True)
            
            # �� AI 주소 편집 및 학습 시스템
            st.header("🧠 AI 주소 편집 시스템")
            
            # 실패한 주소 추출
            failed_results = [r for r in st.session_state.conversion_results if r['상태'] != '성공']
            
            if failed_results:
                # 편집 방법 선택
                edit_tab1, edit_tab2, edit_tab3 = st.tabs(["🔧 개별 수정", "🔄 일괄 수정", "📊 AI 학습 현황"])
                
                with edit_tab1:
                    # 개별 주소 편집 (안전한 오류 처리)
                    try:
                        corrected_individual = editor.show_failed_addresses_editor(failed_results)
                        if corrected_individual:
                            # 세션 상태 업데이트
                            st.session_state.corrected_results.extend(corrected_individual)
                            
                            # 성공 메시지와 함께 즉시 새로고침
                            st.success(f"✅ {len(corrected_individual)}개 주소가 수정되었습니다.")
                            st.info("🔄 지도를 업데이트합니다...")
                            
                            # 약간의 지연 후 새로고침
                            import time
                            time.sleep(0.5)
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ 개별 편집 중 오류: {str(e)}")
                
                with edit_tab2:
                    # 일괄 주소 편집 (안전한 오류 처리)
                    try:
                        corrected_batch = editor.show_batch_editor(failed_results)
                        if corrected_batch:
                            # 세션 상태 업데이트
                            st.session_state.corrected_results.extend(corrected_batch)
                            
                            # 성공 메시지와 함께 즉시 새로고침
                            st.success(f"✅ {len(corrected_batch)}개 주소가 일괄 수정되었습니다.")
                            st.info("🔄 지도를 업데이트합니다...")
                            
                            # 약간의 지연 후 새로고침
                            import time
                            time.sleep(0.5)
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ 일괄 편집 중 오류: {str(e)}")
                
                with edit_tab3:
                    # AI 학습 현황 대시보드 (안전한 오류 처리)
                    try:
                        editor.show_learning_dashboard()
                    except Exception as e:
                        st.error(f"❌ 학습 현황 표시 중 오류: {str(e)}")
                
                # 수정된 결과가 있으면 전체 결과 업데이트
                if st.session_state.corrected_results:
                    st.subheader("✅ 수정 완료된 결과")
                    
                    # 전체 결과 통합 (원본 + 수정된 결과)
                    all_results = st.session_state.conversion_results + st.session_state.corrected_results
                    updated_df = pd.DataFrame(all_results)
                    
                    # 올바른 통계 계산 (원본 주소 수 기준)
                    original_total = len(st.session_state.conversion_results)
                    original_success = len([r for r in st.session_state.conversion_results if r['상태'] == '성공'])
                    corrected_success = len([r for r in st.session_state.corrected_results if '성공' in r['상태']])
                    final_success = original_success + corrected_success
                    final_success_rate = (final_success / original_total) * 100 if original_total > 0 else 0
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("전체 주소", original_total)
                    with col2:
                        st.metric("최종 성공", final_success, f"+{corrected_success}")
                    with col3:
                        st.metric("최종 성공률", f"{final_success_rate:.1f}%")
                    
                    # 업데이트된 결과 표시
                    st.dataframe(updated_df, use_container_width=True)
                    
                    # 업데이트된 Excel 다운로드
                    excel_buffer = BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        updated_df.to_excel(writer, index=False, sheet_name='최종변환결과')
                    excel_data = excel_buffer.getvalue()
                    
                    st.download_button(
                        label="📥 최종 결과 다운로드 (Excel)",
                        data=excel_data,
                        file_name=f"최종_주소변환결과_{selected_date.strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    # AI 편집 완료 후 페이지 새로고침으로 위의 지도가 자동 업데이트됩니다
                    st.success("✅ AI 편집이 완료되었습니다. 위의 '5️⃣ 지도 표시' 섹션에서 업데이트된 지도를 확인하세요!")
                    st.info("💡 페이지를 새로고침하면 최신 결과가 지도에 반영됩니다.")
            
            # 오류 분석 (수정되지 않은 실패 주소만)
            original_failed = [r for r in st.session_state.conversion_results if r['상태'] != '성공']
            corrected_addresses = {r['주소'] for r in st.session_state.corrected_results if '성공' in r['상태']}
            still_failed = [r for r in original_failed if r['주소'] not in corrected_addresses]
            
            if still_failed:
                st.subheader("🔍 오류 분석 (미해결)")
                
                error_df = pd.DataFrame(still_failed)
                
                # 오류 유형별 통계
                error_stats = error_df['상태'].value_counts()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**미해결 오류 유형별 통계:**")
                    for error_type, count in error_stats.items():
                        st.write(f"- {error_type}: {count}건")
                
                with col2:
                    with st.expander("🔎 미해결 실패 주소 목록"):
                        st.dataframe(error_df[['주소', '상태']])

    except Exception as e:
        st.error(f"❌ 파일 처리 중 오류가 발생했습니다: {str(e)}")

else:
    st.info("👆 Excel 파일을 업로드하여 시작하세요.")
    
    # 사용 방법 안내
    with st.expander("📖 사용 방법"):
        st.markdown("""
        ### 📋 사용 단계
        1. **Excel 파일 업로드**: 주소 정보가 포함된 .xlsx 파일을 업로드
        2. **컬럼 선택**: 주소가 포함된 컬럼 선택
        3. **날짜 필터링**: 날짜 컬럼이 있는 경우 특정 날짜 선택
        4. **AI 주소 변환**: 학습된 패턴을 활용한 스마트 주소 변환
        5. **실패 주소 수정**: AI 제안 또는 직접 수정으로 변환 재시도
        6. **지도 표시**: 변환된 좌표를 지도에 마커로 표시
        7. **결과 다운로드**: 최종 변환 결과를 Excel 파일로 다운로드
        
        ### 🧠 AI 기능
        - **학습 시스템**: 사용자 수정 내용을 학습하여 정확도 향상
        - **스마트 전처리**: 주소 패턴 분석 및 자동 정규화
        - **웹 학습**: 인터넷 검색을 통한 주소 패턴 학습
        - **제안 시스템**: 실패한 주소에 대한 AI 기반 수정 제안
        - **일괄 처리**: 다양한 자동 수정 옵션으로 일괄 재변환
        
        ### 📌 지원 형식
        - **파일**: .xlsx (Excel 2007 이상)
        - **주소**: 한국 내 모든 주소 (도로명주소, 지번주소, 랜드마크)
        - **날짜**: 다양한 날짜 형식 자동 인식
        
        ### ⚠️ 주의사항
        - 인터넷 연결이 필요합니다 (카카오 API 사용)
        - AI 학습 데이터는 로컬에 저장됩니다
        - 대량 데이터의 경우 시간이 소요될 수 있습니다
        - API 호출 제한으로 인해 요청 간격을 두고 처리합니다
        """) 