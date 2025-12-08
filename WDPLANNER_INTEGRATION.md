# WDPlanner 통합 가이드

## 개요

WDPlanner는 FOMS(가구 주문 관리 시스템)에 통합된 붙박이장 3D 설계 프로그램입니다.

## 통합 상태

✅ **완료된 작업:**
1. 메인 메뉴에 "WDPLANNER" 항목 추가 (관리자 다음)
2. `/wdplanner` 라우트 추가
3. 정적 파일 서빙 설정
4. 빌드 및 배치 스크립트 생성

## 사용 방법

### 1. 초기 설정 (처음 한 번만)

WDPlanner를 사용하려면 먼저 빌드 파일을 생성해야 합니다.

#### 방법 1: 자동 빌드 스크립트 사용 (권장)

```bash
build_wdplanner.bat
```

이 스크립트는 다음 작업을 자동으로 수행합니다:
- 의존성 설치 확인
- 웹 빌드 실행
- 빌드 파일을 `static/wdplanner`로 복사

#### 방법 2: 수동 빌드

1. **WDPlanner 디렉토리로 이동**
   ```bash
   cd "Add In Program\WDPlanner"
   ```

2. **의존성 설치** (처음 한 번만)
   ```bash
   npm install
   ```

3. **웹 빌드 실행**
   ```bash
   npm run build
   ```

4. **빌드 파일 복사**
   ```bash
   # PowerShell
   xcopy /E /I /Y "Add In Program\WDPlanner\dist\*" "static\wdplanner\"
   ```

### 2. 접속

빌드가 완료되면:
1. FOMS 시스템에 로그인
2. 메인 메뉴에서 "WDPLANNER" 클릭
3. 또는 직접 `/wdplanner` 경로로 접속

### 3. 업데이트

WDPlanner 소스 코드를 수정한 경우:
1. `build_wdplanner.bat` 실행
2. 또는 수동으로 빌드 후 파일 복사
3. 브라우저에서 새로고침 (Ctrl+F5)

## 파일 구조

```
FOMS/
├── app.py                          # WDPlanner 라우트 추가됨
├── templates/
│   ├── layout.html                 # WDPLANNER 메뉴 추가됨
│   └── wdplanner_setup.html        # 빌드 안내 페이지
├── static/
│   └── wdplanner/                  # 빌드 파일 배치 위치
│       ├── index.html
│       ├── assets/
│       └── ...
├── build_wdplanner.bat             # 빌드 스크립트
└── Add In Program/
    └── WDPlanner/                   # 원본 소스 코드
        ├── src/
        ├── package.json
        └── ...
```

## 라우트 정보

- **메인 라우트**: `/wdplanner`
- **정적 파일**: `/wdplanner/<filename>` (자동 처리)
- **접근 권한**: 로그인 필요 (`@login_required`)

## 문제 해결

### 빌드 파일이 없다는 메시지가 표시되는 경우

1. `static/wdplanner/index.html` 파일이 존재하는지 확인
2. `build_wdplanner.bat` 실행
3. 브라우저 캐시 삭제 후 새로고침

### 정적 파일(JS, CSS)이 로드되지 않는 경우

1. 빌드 파일이 `static/wdplanner`에 제대로 복사되었는지 확인
2. 브라우저 개발자 도구(F12)에서 네트워크 탭 확인
3. 파일 경로가 올바른지 확인

### 빌드 오류가 발생하는 경우

1. Node.js가 설치되어 있는지 확인 (`node --version`)
2. npm이 설치되어 있는지 확인 (`npm --version`)
3. `Add In Program/WDPlanner` 디렉토리에서 `npm install` 실행
4. 에러 메시지를 확인하고 필요한 패키지 설치

## 주의사항

1. **기존 FOMS 기능 보호**: WDPlanner 통합은 기존 FOMS 시스템에 영향을 주지 않도록 설계되었습니다.
2. **독립적 실행**: WDPlanner는 독립적인 React 애플리케이션으로, FOMS의 다른 기능과 분리되어 있습니다.
3. **빌드 필요**: 소스 코드 수정 후에는 반드시 빌드를 다시 실행해야 합니다.
4. **정적 파일 경로**: 빌드된 파일은 `static/wdplanner`에 있어야 합니다.

## 기술 스택

- **WDPlanner**: React + TypeScript + Vite + Babylon.js
- **FOMS**: Flask (Python)
- **통합 방식**: 정적 파일 서빙

## 개발자 정보

WDPlanner 소스 코드는 `Add In Program/WDPlanner` 디렉토리에 있습니다.
빌드 및 배포는 `build_wdplanner.bat` 스크립트를 사용하세요.



