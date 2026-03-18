# ERP 작업 큐 thead 스크롤 고정(Sticky) 구현

**날짜**: 2026-03-18  
**트리거**: 사용자 요청 (스크롤 다운 시 헤더가 같이 올라가서 상태변경 불가)  
**GDM 감리**: code-reviewer 통과

## 목표
ERP 프로세스 대시보드, 생산 대시보드, 시공 대시보드의 작업 큐 테이블(#erp-grid) thead(경보, 단계, 고객 등 컬럼 헤더)를 스크롤 시 상단에 고정하여, 하단 주문의 상태 변경 시에도 헤더를 참조할 수 있도록 함.

## 변경 사항

### 1. HTML 구조
| 파일 | 변경 |
|------|------|
| `erp_production_filters_grid.html` | `erp-grid-scroll-wrap` 래퍼로 `table-responsive` 감싸기 |
| `erp_construction_filters_grid.html` | 동일 |

### 2. CSS
| 파일 | 변경 |
|------|------|
| `erp_production_styles.html` | `.erp-grid-scroll-wrap` 정의, `#erp-grid thead th`에 `position:sticky; top:0; z-index:10` |
| `erp_construction_styles.html` | 동일 |
| `erp_dashboard_styles.html` | `#erp-grid thead th`에 `position:sticky; top:0; z-index:10` (기존 erp-grid-scroll-wrap 유지) |

### 3. 동작 원리
- `erp-grid-scroll-wrap`: `overflow-y: auto`, `max-height: min(calc(100vh - 280px), 72vh)` → 이 컨테이너 기준으로 세로 스크롤
- `position: sticky`는 스크롤 컨테이너 내부에서만 동작. 이 래퍼가 있어야 thead가 상단 고정됨
- 생산/시공 대시보드는 기존에 `erp-grid-scroll-wrap`가 없어 페이지 전체 스크롤 기준이었음 → 래퍼 추가로 메인 대시보드와 동일 구조로 통일

## 감리 결과 (code-reviewer)
- HTML 구조: ✅ erp-grid-scroll-wrap → table-responsive → table 순서, 닫는 태그 정상
- CSS sticky: ✅ position:sticky, top:0, z-index:10, background-color 적용
- 스크롤 컨테이너: ✅ overflow-y:auto, max-height 적용
- 모바일: ✅ @media (max-width: 992px) 내 thead display:none 유지
- 중복/충돌: ✅ 기본 sticky와 @media (min-width:993px) sticky 동일 방향, 충돌 없음

## 권장 후속 (low)
- thead th 인라인 스타일 → CSS 클래스로 이전 (Phase D-8 연계)
