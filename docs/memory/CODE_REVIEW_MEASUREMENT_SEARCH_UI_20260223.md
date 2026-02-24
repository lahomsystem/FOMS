# GDM 코드 리뷰: 실측 대시보드 검색 카테고리 출고와 동일화

**일자:** 2026-02-23  
**기준:** `.cursor/agents/grand-develop-master.md` (개발 품질 감사)  
**계획:** `docs/memory/PLAN_MEASUREMENT_SEARCH_UI.md`

---

## 변경 요약

- **실측 대시보드** 검색·필터 UI를 **출고 대시보드**와 동일한 구성으로 맞춤.
- 날짜 범위 입력 제거, 기준날짜 기본값 '전체', 패널에 '전체' 버튼·배지 추가.

---

## 마무리 코드 리뷰

### 1. 백엔드 `apps/erp_measurement_dashboard.py`

| 항목 | 내용 | 판정 |
|------|------|------|
| 날짜 파라미터 | `req_date = request.args.get('date') or ''`, `use_range`/`use_single_day` 검증 후 `selected_date = req_date` | ✅ 출고와 동일 패턴 |
| 전체 기본값 | `not use_range and not use_single_day` 시 `req_date = ''` | ✅ |
| 패널 base_date | `selected_date` 빈 문자열이면 strptime 예외 → `today_kst` 사용 | ✅ 기존 로직 유지 |
| structured_data | `_ensure_dict` 할당에 `# type: ignore[assignment]` 추가 | ✅ 타입 검사기 대응 |

### 2. 템플릿 `templates/erp_measurement_dashboard.html`

| 항목 | 내용 | 판정 |
|------|------|------|
| 날짜 범위 | "날짜 범위" 라벨 및 date_from/date_to 입력 블록 삭제 | ✅ |
| 기준 날짜 | `value="{{ selected_date }}"`, `placeholder="전체"` | ✅ |
| 패널 | "전체" 버튼(쿼리스트링에 date 없음), "오늘" 버튼, 배지 `{% if selected_date %}...{% else %}전체{% endif %}` | ✅ 출고와 동일 |
| 지도 링크 | `{% if selected_date %}date={{ selected_date }}&{% endif %}` 로 선택일 있을 때만 전달 | ✅ |

### 3. 아키텍처·일관성

- 실측·출고 대시보드 필터 구조 통일(검색 + 기준 날짜 + 조회/보조 버튼).
- date_from/date_to는 백엔드에서만 사용(URL로 진입 시 호환), 템플릿에서는 제거됨.

---

## 수정 파일

| 파일 | 변경 |
|------|------|
| `apps/erp_measurement_dashboard.py` | req_date/selected_date 처리, 날짜 미지정 시 전체, type: ignore 추가 |
| `templates/erp_measurement_dashboard.html` | 날짜 범위 제거, 전체 버튼·배지, 지도 링크 조건부 date |
| `docs/memory/PLAN_MEASUREMENT_SEARCH_UI.md` | 계획서 추가 |
| `docs/memory/CODE_REVIEW_MEASUREMENT_SEARCH_UI_20260223.md` | 본 리뷰 |

---

## 검증 제안

- 실측 대시보드 첫 진입 → 날짜 미선택 시 목록·배지 "전체" 노출.
- '오늘' 클릭 → 해당 일자만 필터.
- 기준 날짜 선택 후 조회 → 해당 일자만 필터.
- 지도 버튼 → 선택일 있을 때만 date 파라미터 포함.
