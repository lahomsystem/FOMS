# 배포 전 코드 리뷰 (2026-02-23, GDM 기준)

## 리뷰 대상 변경 요약
- 실측/출고 대시보드: 전체 검색(q)·날짜 범위·전체 기간
- ERP 대시보드 날짜 기준: KST(한국 시간) 통일 (get_today_kst)
- 업로드 진행률: ERP Beta 첨부·도면작업실 수정요청
- wdcalculator: received_date isoformat 제거

## GDM 감사 결과

### 보안 (양호)
- 검색어 `q`: SQLAlchemy `.ilike(term)`로 바인딩 전달, raw 문자열 연결 없음. SQL 인젝션 없음.
- 날짜 파라미터: strptime 검증 또는 문자열 비교, 서버 측 검증 유지.

### 아키텍처 (양호)
- Blueprint·서비스 분리 유지. get_today_kst()는 erp_display에 두고 실측/출고/AS/API에서 공통 사용.
- 검색 필터는 각 Blueprint 내 _erp_order_search_filter 동일 로직 (추후 서비스로 추출 가능).

### 품질 (양호)
- get_today_kst() fallback으로 pytz 미설치 시 date.today() 사용.
- 날짜 파싱 실패 시 실측은 오늘로 폴백. 기존 manager 파라미터 호환 유지.

### 결론
이상 없음. deploy 푸시 후 production 푸시 진행.
