#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
주소 변환 시스템 런처
Streamlit 앱을 실행하고 브라우저를 자동으로 엽니다.
"""

import subprocess
import webbrowser
import time
import os
import sys
import threading
from pathlib import Path

def find_free_port(start_port=8501):
    """사용 가능한 포트를 찾습니다."""
    import socket
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    return start_port

def open_browser(url, delay=3):
    """지정된 시간 후 브라우저를 엽니다."""
    time.sleep(delay)
    webbrowser.open(url)

def main():
    print("🚀 주소 변환 시스템을 시작합니다...")
    
    # 현재 스크립트 디렉토리 확인
    script_dir = Path(__file__).parent
    main_app_path = script_dir / "main_app.py"
    
    if not main_app_path.exists():
        print(f"❌ 오류: {main_app_path} 파일을 찾을 수 없습니다.")
        input("엔터를 눌러 종료하세요...")
        return
    
    # 사용 가능한 포트 찾기
    port = find_free_port()
    url = f"http://localhost:{port}"
    
    print(f"📍 포트 {port}에서 서버를 시작합니다...")
    print(f"🌐 브라우저에서 {url}이 자동으로 열립니다...")
    
    # 브라우저 열기 (3초 후)
    browser_thread = threading.Thread(target=open_browser, args=(url, 3))
    browser_thread.daemon = True
    browser_thread.start()
    
    # Streamlit 앱 실행
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", 
            str(main_app_path),
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false"
        ]
        
        print("⚡ Streamlit 서버를 시작합니다...")
        print("종료하려면 Ctrl+C를 누르세요.")
        print("-" * 50)
        
        subprocess.run(cmd, cwd=script_dir)
        
    except KeyboardInterrupt:
        print("\n✅ 서버가 정상적으로 종료되었습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        input("엔터를 눌러 종료하세요...")

if __name__ == "__main__":
    main() 