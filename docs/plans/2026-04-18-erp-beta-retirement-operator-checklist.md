# ERP_BETA Retirement Operator Checklist

이 문서는 “실제 은퇴 배치를 시작하려면 지금 사용자가 무엇을 해야 하는가”를 아주 간단히 정리한 체크리스트다.

## 이미 확인된 것

- Railway 로그인 상태: 확인됨
- Railway 프로젝트: `FOMS-DEV`
- Railway 환경: `production`
- Railway 앱 서비스: `FOMS`
- G-DB: production 기준 확보됨
- G-ENV: 확보됨 (`ERP_ORDER_ENABLED=true`, legacy `ERP_BETA_ENABLED`/`ERP_BETA_DEBUG` 미설정)
- G-IN: 앱 로그 기준 약한 음성 신호만 있음
- G-DATA: Codex가 읽기 전용 SQL로 확인 완료, 현재 **차단 상태**
- URL 정책: 배포 후 `GET /add?open=erp-beta`, `GET /edit/<id>?open=erp-beta` 는 **302** 로 동일 경로에 `open=erp-order` 이 적용된 주소로 이동한다(나머지 쿼리 유지). 스모크에서 주소창에 `erp-beta` 가 남지 않는지 확인한다.

## 지금 사용자에게 필요한 것

### 1. Railway에 `ERP_ORDER_ENABLED=true`를 명시한다

이건 현재 default 동작을 “의도된 canonical flag”로 명시하는 단계다.
이 변경은 deploy를 유발할 수 있으므로 사용자가 승인하고 진행해야 한다.

가장 쉬운 방법:
- Railway 대시보드 열기
- `FOMS-DEV` 프로젝트의 `production` 환경 선택
- `FOMS` 서비스 선택
- Variable 추가
  - key: `ERP_ORDER_ENABLED`
  - value: `true`

완료 후 사용자 메시지:
- `1번 완료`

### 2. G-DATA 읽기 전용 SQL을 실행한다

지금은 이 단계가 **이미 완료**됐다.
즉, 사용자가 지금 당장 다시 할 필요는 없다.

다음 파일의 SQL을 Railway Postgres query UI 또는 읽기 전용 psql에서 실행한다.

- [erp_beta_retirement_g_data_readonly.sql](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/tools/harness/erp_beta_retirement_g_data_readonly.sql)

사용자가 저에게 보내야 하는 것:
- 첫 번째 결과 테이블 1개
- 두 번째 결과 테이블 1개

이미 확인된 핵심 결과:
- active 주문 1,738건
- `customer_name='ERP Beta'` 564건
- `product='ERP Beta'` 565건
- JSONB 내부 legacy literal 0건
- `structured_data.meta.draft=true` 0건

뜻:
- 문제는 JSONB가 아니라 **flat 컬럼에 남은 ERP Beta placeholder 값**이다.
- 그래서 아직 placeholder suppressor 제거 배치를 시작하면 안 된다.

### 3. Edge/access log에서 legacy inbound 사용량을 확인한다

앱 로그만으로는 `open=erp-beta`, `create_mode=ERP_BETA` 쿼리스트링이 안 찍힐 수 있다.
그래서 Cloudflare/Nginx/WAF/access log 같은 edge log가 가장 좋다.

찾아야 할 문자열:
- `open=erp-beta`
- `create_mode=ERP_BETA`

권장 윈도우:
- 최근 7일 또는 30일

사용자가 저에게 보내야 하는 것:
- 7일/30일 기준 검색 결과 count
- 가능하면 스크린샷 또는 텍스트 1개

만약 edge log 접근이 없으면:
- `3번 불가 (edge log 없음)` 이라고 알려주면 된다.

### 4. 여기까지 오면 Codex가 다시 이어서 한다

사용자가 아래 중 하나로 답하면 된다.

- `1번 완료 + 2번 결과 붙여넣음 + 3번 결과 붙여넣음`
- 또는 `1번 완료 + 2번 결과 붙여넣음 + 3번 불가`

그 다음 내가 할 일:
- gate evidence 정리
- P2 시작 가능 여부 판정
- 가능하면 바로 P2 batch 구현 시작

## 사용자가 헷갈리면 이것만 기억하면 된다

1. `ERP_ORDER_ENABLED=true`를 Railway `FOMS` production 변수에 추가
2. SQL 파일 실행 후 결과 2개 붙여넣기
3. edge log에서 `open=erp-beta`, `create_mode=ERP_BETA` 검색 결과 알려주기

이 3개가 오면 다음 코딩 배치를 바로 시작할 수 있다.
