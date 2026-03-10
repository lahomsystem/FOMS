# 출고 대시보드 컬럼 폭 재조정 Spec
> 작성일: 2026-03-10 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 문제 인식
- **시공시간** 컬럼: "예: 10:00" 수준의 짧은 입력만 필요하나 `min-width: 118px`로 과도하게 넓음
- **현장주소** 컬럼: 주소·추가입력(site_extra) 등 정보량이 가장 많은데 `width: 210px`, `max-width: 240px`로 제한됨

### 1.2 설계 원칙 (사용자 의도)
- **정보량 비례**: 정보가 많은 컬럼일수록 넓어야 함
- **시공시간**: 최소 표시만 하면 되므로 좁게
- **주소**: 가장 넓어야 함

### 1.3 최종 결과물
| 컬럼 | 현재 | 변경 후 | 근거 |
|------|------|---------|------|
| 시공시간 | min-width: 118px | width: 82px, min-width: 82px | "10:00" + 아이콘 버튼 2개 수준 |
| 현장주소 | width: 210px, max: 240px | min-width: 280px, max-width: 380px | 주소·추가입력·줄바꿈 유지 |

### 1.4 예외/제약
- 모바일 카드 뷰는 기존 반응형 유지
- 테이블 `min-width`는 1020px 유지 (가로 스크롤 동작 보존)

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `templates/erp_shipment_dashboard.html` | th 시공시간/현장주소 inline style, `.shipment-address-cell` CSS, `.shipment-field-cell`(시공시간 td) 관련 |

### 2.2 구체 변경
1. **thead th**
   - 현장주소: `width: 210px` → `min-width: 280px` (width 제거, min만)
   - 시공시간: `min-width: 118px` → `width: 82px; min-width: 82px`
2. **.shipment-address-cell** (CSS)
   - `width: 210px; min-width: 190px; max-width: 240px` → `min-width: 280px; max-width: 380px` (width 제거)
3. **시공시간 td** (data-label="시공시간")
   - 기존 `min-width` 없음 → 필요 시 `width: 82px` 클래스/스타일 추가 (th와 일치)

### 2.3 의존성
- CSS만 변경, 백엔드/API 없음
- 기존 `white-space: pre-wrap` 등 주소 줄바꿈 스타일 유지

## 3. Steps — 실행 단계
- [x] Step 1: thead th 현장주소·시공시간 스타일 수정
- [x] Step 2: .shipment-address-cell CSS 수정
- [x] Step 3: 시공시간 td에 width 제한 적용 (필요 시)
- [x] Step 4: 로컬에서 출고 대시보드 확인
- [x] Step 5: 클린코드 정리 (th/td inline style → CSS 클래스, 중복 제거)

## 4. 검증 기준
- [ ] `python -c "import app"` 통과
- [ ] `/erp/shipment` 200 OK, 테이블 렌더링
- [ ] 시공시간 컬럼이 주소보다 좁게 보임
- [ ] 주소 컬럼이 가장 넓게 보임, 줄바꿈 정상

## 5. 참고
- 이전 작업: 출고 대시보드 주소 컬럼 폭 축소·extra_input 줄바꿈 (b93617d) — 이번에는 **역방향**: 주소 확대, 시공시간 축소
