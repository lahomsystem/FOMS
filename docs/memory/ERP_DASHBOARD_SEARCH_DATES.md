# 실측/출고 대시보드 검색·날짜 개선 (2026-02-23)

## 요약
- **검색**: 담당자만 → **고객·담당자·시공자·주소** 전체 검색 (단일 입력 `q`, 기존 `manager` 쿼리 호환).
- **날짜**: 기준일만 → **기준일** / **날짜 범위(date_from~date_to)** / **전체 기간**(날짜 미지정 시).

## 적용 파일
| 구간 | 파일 | 변경 |
|------|------|------|
| 실측 백엔드 | `apps/erp_measurement_dashboard.py` | `_erp_order_search_filter()`, `q`/`date_from`/`date_to`, 전체 기간 시 날짜 미적용 |
| 출고 백엔드 | `apps/erp_shipment_page.py` | `_erp_order_search_filter()`, `q`/`date_from`/`date_to`, 전체 기간 분기 |
| 실측 템플릿 | `templates/erp_measurement_dashboard.html` | 검색 라벨/placeholder, 날짜 범위 입력, `search_q` |
| 출고 템플릿 | `templates/erp_shipment_dashboard.html` | 동일 |

## 검색 로직
- Order 컬럼: `customer_name`, `manager_name`, `address` ILIKE `%q%`.
- ERP Beta: `cast(structured_data, String).ilike('%q%')` 로 JSON 내 고객/담당자/시공자/주소 등 전 필드 검색.
- SQL 인젝션: `q`는 파라미터 바인딩으로 전달되며, `%`/`_` 등 특수문자는 사용자 입력 그대로 검색(와일드카드 아님).

## 날짜 로직
- **실측**: `date_from`+`date_to` 있으면 해당 범위(날짜 컬럼·received_date 60일)로 필터; `date`만 있으면 기존 단일일; 둘 다 없으면 **전체 기간**(검색어만 적용).
- **출고**: `date_from`+`date_to` 있으면 시공일 기준 Python 필터; `date`만 있으면 해당일; 없으면 **전체 기간**.

## GDM 리뷰 요약
- 검색 조건은 OR로 통일, ERP Beta는 JSON 텍스트 검색으로 시공자 등 포함.
- 날짜 파싱 실패 시 실측은 오늘 기준일로 폴백.
- 기존 `manager` 쿼리 파라미터 유지로 하위 호환.
