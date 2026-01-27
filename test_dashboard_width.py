"""
대시보드 전체 너비 문제 진단 스크립트
브라우저에서 직접 확인하고 문제점 파악
"""
from playwright.sync_api import sync_playwright
import time

def diagnose_dashboard_width():
    """대시보드 전체 너비 문제 진단"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='ko-KR'
        )
        page = context.new_page()
        
        try:
            # 1. 로그인
            print("1. 로그인 중...")
            page.goto('http://localhost:5000/login', wait_until='networkidle')
            time.sleep(1)
            page.fill('input[name="username"]', 'admin')
            page.fill('input[name="password"]', 'Admin123')
            page.click('button[type="submit"]')
            page.wait_for_load_state('networkidle', timeout=10000)
            time.sleep(2)
            
            # 2. ERP 대시보드 확인
            print("\n2. ERP 대시보드 확인 중...")
            page.goto('http://localhost:5000/erp/dashboard', wait_until='networkidle')
            time.sleep(3)
            
            # 컨테이너 너비 확인
            erp_container = page.query_selector('.erp-dashboard')
            if erp_container:
                erp_box = erp_container.bounding_box()
                viewport_width = page.viewport_size['width']
                print(f"   ERP 대시보드 컨테이너 너비: {erp_box['width']}px")
                print(f"   뷰포트 너비: {viewport_width}px")
                print(f"   사용률: {erp_box['width'] / viewport_width * 100:.1f}%")
                
                # 작업 큐 너비 확인
                workqueue = page.query_selector('.erp-dashboard-workqueue')
                if workqueue:
                    wq_box = workqueue.bounding_box()
                    print(f"   작업 큐 너비: {wq_box['width']}px")
                    print(f"   작업 큐 사용률: {wq_box['width'] / erp_box['width'] * 100:.1f}%")
                
                # 실제 계산된 스타일 확인
                erp_styles = page.evaluate('''() => {
                    const el = document.querySelector('.erp-dashboard');
                    if (!el) return null;
                    const styles = window.getComputedStyle(el);
                    return {
                        width: styles.width,
                        maxWidth: styles.maxWidth,
                        marginLeft: styles.marginLeft,
                        marginRight: styles.marginRight,
                        paddingLeft: styles.paddingLeft,
                        paddingRight: styles.paddingRight,
                        boxSizing: styles.boxSizing
                    };
                }''')
                print(f"   실제 스타일: {erp_styles}")
            
            # 3. 지방 주문 대시보드 확인
            print("\n3. 지방 주문 대시보드 확인 중...")
            page.goto('http://localhost:5000/regional_dashboard', wait_until='networkidle')
            time.sleep(3)
            
            regional_container = page.query_selector('.regional-dashboard')
            if regional_container:
                reg_box = regional_container.bounding_box()
                viewport_width = page.viewport_size['width']
                print(f"   지방 주문 대시보드 컨테이너 너비: {reg_box['width']}px")
                print(f"   뷰포트 너비: {viewport_width}px")
                print(f"   사용률: {reg_box['width'] / viewport_width * 100:.1f}%")
                
                # 테이블 너비 확인
                table_resp = page.query_selector('.regional-dashboard .table-responsive')
                if table_resp:
                    tbl_box = table_resp.bounding_box()
                    print(f"   테이블 컨테이너 너비: {tbl_box['width']}px")
                    print(f"   테이블 사용률: {tbl_box['width'] / reg_box['width'] * 100:.1f}%")
                
                # 실제 계산된 스타일 확인
                reg_styles = page.evaluate('''() => {
                    const el = document.querySelector('.regional-dashboard');
                    if (!el) return null;
                    const styles = window.getComputedStyle(el);
                    return {
                        width: styles.width,
                        maxWidth: styles.maxWidth,
                        marginLeft: styles.marginLeft,
                        marginRight: styles.marginRight,
                        paddingLeft: styles.paddingLeft,
                        paddingRight: styles.paddingRight,
                        boxSizing: styles.boxSizing
                    };
                }''')
                print(f"   실제 스타일: {reg_styles}")
            
            # 4. 부모 요소들 확인
            print("\n4. 부모 요소 체인 확인 중...")
            parent_chain = page.evaluate('''() => {
                const erp = document.querySelector('.erp-dashboard');
                if (!erp) return null;
                const chain = [];
                let current = erp;
                while (current && current !== document.body) {
                    const styles = window.getComputedStyle(current);
                    chain.push({
                        tag: current.tagName,
                        class: current.className,
                        width: styles.width,
                        maxWidth: styles.maxWidth,
                        paddingLeft: styles.paddingLeft,
                        paddingRight: styles.paddingRight,
                        marginLeft: styles.marginLeft,
                        marginRight: styles.marginRight
                    });
                    current = current.parentElement;
                }
                return chain;
            }''')
            if parent_chain:
                print("   부모 요소 체인:")
                for i, elem in enumerate(parent_chain):
                    print(f"     {i+1}. {elem['tag']} .{elem['class']}")
                    print(f"        width: {elem['width']}, maxWidth: {elem['maxWidth']}")
                    print(f"        padding: {elem['paddingLeft']} / {elem['paddingRight']}")
                    print(f"        margin: {elem['marginLeft']} / {elem['marginRight']}")
            
            # 5. 스크린샷 저장
            print("\n5. 스크린샷 저장 중...")
            page.screenshot(path='test_dashboard_width_erp.png', full_page=True)
            page.goto('http://localhost:5000/regional_dashboard', wait_until='networkidle')
            time.sleep(2)
            page.screenshot(path='test_dashboard_width_regional.png', full_page=True)
            print("   저장 완료: test_dashboard_width_erp.png, test_dashboard_width_regional.png")
            
            print("\n[OK] 진단 완료!")
            print("브라우저를 10초 후 종료합니다...")
            time.sleep(10)
            
        except Exception as e:
            print(f"\n[ERROR] 오류 발생: {e}")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()

if __name__ == '__main__':
    diagnose_dashboard_width()
