# 실측 대시보드 검색 카테고리 출고 대시보드와 동일화

**일자:** 2026-02-23  
**기준:** 출고 대시보드(erp_shipment_dashboard) 검색·필터 UI

---

## 1. 목표

- 실측 대시보드(erp_measurement_dashboard)의 검색·필터 영역을 **출고 대시보드와 동일한 구성**으로 변경.
- 날짜 범위 제거, 기준날짜 기본값 '전체', 패널에 '전체' 버튼·배지 반영.

---

## 2. 변경 사항

### 2.1 백엔드 `apps/erp_measurement_dashboard.py`

- `req_date = request.args.get('date') or ''` 로 단일 파라미터 사용.
- `use_range` = date_from·date_to 유효 시에만 True.
- `use_single_day` = req_date 유효(날짜 형식 검증) 시에만 True.
- **날짜 미지정 시:** `use_range`·`use_single_day` 모두 False이면 `selected_date = ''` (전체). 기존처럼 `date_from or today_date`로 채우지 않음.
- use_range 검증 실패 시 `selected_date = req_date or ''` 로 정리.
- 패널용 `base_date`: `selected_date`가 빈 문자열이면 기존 try/except로 `today_kst` 사용 유지.

### 2.2 템플릿 `templates/erp_measurement_dashboard.html`

- **날짜 범위 제거:** "날짜 범위" 라벨 및 `date_from`, `date_to` 입력 블록 삭제.
- **기준 날짜:** `value="{{ selected_date }}"`, `placeholder="전체"` 유지.
- **패널:** "전체" 버튼 추가(쿼리스트링에 date 없음), "오늘" 버튼 유지, 배지 `selected_date` 없을 때 "전체" 표시.
- **지도 링크:** `selected_date` 있을 때만 `date=` 전달, 없으면 생략 또는 빈 값 처리.

---

## 3. 검증

- 실측 대시보드 첫 진입 시 날짜 미선택 → 목록·패널 '전체' 동작, 배지 "전체" 표시.
- 기준 날짜 선택 또는 '오늘' 클릭 시 해당 일자만 필터.
- 출고 대시보드와 동일한 필터 레이아웃(검색 + 기준 날짜 + 조회/지도/동선).
