"""
ERP 대시보드 UI 반응형 테스트 스크립트
브라우저에서 창 크기를 조절하며 UI 확인
"""
from playwright.sync_api import sync_playwright
import time
import os

def test_erp_dashboard_responsive():
    """ERP 대시보드 반응형 UI 테스트"""
    with sync_playwright() as p:
        # 브라우저 실행
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='ko-KR'
        )
        page = context.new_page()
        
        try:
            # 1. 로그인 페이지 접속
            print("1. 로그인 페이지 접속 중...")
            page.goto('http://localhost:5000/login', wait_until='networkidle')
            time.sleep(1)
            
            # 2. 로그인
            print("2. 로그인 중...")
            page.fill('input[name="username"]', 'admin')
            page.fill('input[name="password"]', 'Admin123')
            page.click('button[type="submit"]')
            # 로그인 후 페이지 로드 대기
            page.wait_for_load_state('networkidle', timeout=10000)
            time.sleep(2)
            print(f"   현재 URL: {page.url}")
            
            # 3. ERP 대시보드로 이동
            print("3. ERP 대시보드로 이동 중...")
            page.goto('http://localhost:5000/erp/dashboard', wait_until='networkidle')
            time.sleep(3)
            
            # 4. 다양한 화면 크기로 테스트
            viewports = [
                {'name': 'Desktop Full', 'width': 1920, 'height': 1080},
                {'name': 'Desktop Medium', 'width': 1400, 'height': 900},
                {'name': 'Desktop Narrow', 'width': 1200, 'height': 800},
                {'name': 'Tablet', 'width': 992, 'height': 768},
                {'name': 'Mobile', 'width': 576, 'height': 1024},
            ]
            
            screenshots_dir = 'test_screenshots'
            os.makedirs(screenshots_dir, exist_ok=True)
            
            for viewport in viewports:
                print(f"\n4. {viewport['name']} ({viewport['width']}x{viewport['height']}) 테스트 중...")
                context.set_viewport_size(width=viewport['width'], height=viewport['height'])
                time.sleep(2)
                
                # 스크린샷 저장
                screenshot_path = f"{screenshots_dir}/erp_dashboard_{viewport['name'].replace(' ', '_').lower()}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"   스크린샷 저장: {screenshot_path}")
                
                # 작업 큐 테이블 확인
                table = page.query_selector('#erp-grid')
                if table:
                    table_box = table.bounding_box()
                    print(f"   테이블 크기: {table_box['width']}x{table_box['height']}")
                    
                    # 가로 스크롤 확인
                    table_responsive = page.query_selector('.table-responsive')
                    if table_responsive:
                        scroll_width = page.evaluate('''() => {
                            const el = document.querySelector('.table-responsive');
                            return el ? el.scrollWidth : 0;
                        }''')
                        client_width = page.evaluate('''() => {
                            const el = document.querySelector('.table-responsive');
                            return el ? el.clientWidth : 0;
                        }''')
                        print(f"   스크롤 가능 여부: {scroll_width > client_width} (scrollWidth: {scroll_width}, clientWidth: {client_width})")
                
                # 컬럼 텍스트 잘림 확인
                quest_cells = page.query_selector_all('#erp-grid tbody td:nth-child(3)')
                if quest_cells:
                    for i, cell in enumerate(quest_cells[:3]):  # 처음 3개만 확인
                        text = cell.inner_text()
                        is_truncated = '...' in text or len(text) < 10
                        print(f"   퀘스트 컬럼 {i+1}: {text[:50]}... (잘림: {is_truncated})")
            
            print("\n[OK] 테스트 완료!")
            print(f"스크린샷은 {screenshots_dir} 폴더에 저장되었습니다.")
            
        except Exception as e:
            print(f"\n[ERROR] 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\n브라우저를 10초 후 종료합니다...")
            time.sleep(10)
            browser.close()

if __name__ == '__main__':
    test_erp_dashboard_responsive()
