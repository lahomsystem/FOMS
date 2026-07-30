# 시공 특이사항 신설 + 출고 대시보드 표시 (플랜 + Progress Ledger)

- 날짜: 2026-07-30 / 등급: **B (하루)
- 목표 3건:
  1. ERP 주문탭 시공일 아래 '시공 특이사항' 필드 신설 (실측 특이사항 패턴 미러)
  2. 입력 내용이 /erp/shipment 현장주소 아래 표시 (기존 extra_input 자동표시 유지, 추가 표시)
  3. AS 건: as_log 최신 '자재(material)' 항목 내용을 AS 박스에 표시 (항상 최신)

## 조사 확정 사실 (file:line)

- 실측 특이사항 데이터 흐름 (미러 대상):
  - PC 템플릿: `templates/orders/partials/erp_order_tab.html:266-279` (collapse `#erp-collapse-measure-note` + input `#erp-measurement-note`), 시공시간 블록 293-305
  - 모바일 템플릿: `templates/orders/partials/erp_order_tab_mobile.html:177-188` (같은 id, textarea)
  - JS 수집: `static/js/orders/erp-order-shared.js:2080-2084` — `notes: {phone_note, address_note, measurement_note}` dict
  - JS 로드: `erp-order-shared.js:1870` — `sd?.notes?.measurement_note || ''`
  - 백엔드: `PUT /api/orders/<id>/structured` → projection allowlist에 top-level `notes` 포함(`foms/services/orders/structured_form_projection.py:49`) → 백엔드 수정 불필요
- 출고 대시보드 주소셀: `templates/shipment/partials/dashboard_main.html:552-616` — `shipment-site-extra-list` ul 안에 extra_input 자동표시 static li(556-567) + site_extra 편집 리스트(569-607)
- AS 박스: `dashboard_main.html:519-522` — `r.as_content_text` 표시. AS 판정 = `r.status in ('AS','AS_RECEIVED','AS_COMPLETED')`
- 행 보강: `foms/services/shipment_dashboard_display.py:32-86` `enrich_shipment_rows` — `as_content_text` 파생 위치
- as_log: `sd['shipment']['as_log']` append-only. 항목 키 `{id, ts, by, by_id, type, text, edited_at, edited_by}`. 최신 판정 = `deleted is True` 제외 후 `(ts, 삽입 index)` 역순 (`foms/services/orders/as_log.py:192-214` 패턴). type enum에 `material`(자재) 존재. material 전용 리더 없음 → 신설.

## 함정 (브리프에 필수 포함)

- **레거시 notes=문자열**: 구 주문 `sd['notes']`가 dict가 아닌 문자열인 케이스 존재 (과거 500 사고). shipment 템플릿에서 `is mapping` 가드 필수, 서비스에서 `isinstance(dict)` 가드 필수.
- **기존 JS 수정 = ?v 범프 필수**: SW staticCacheFirst 때문에 `erp-order-shared.js` 참조 핀 전수 grep 후 범프.
- **인라인 스타일 금지**, erp-pro.css 체계. 신규 static li는 기존 `shipment-site-extra-static` 클래스 재사용.
- as_log 항목 text는 클라 raw 저장 — shipment 표시는 Jinja autoescape(기본)로 렌더, `|safe` 금지.

## Tasks (Progress Ledger — task 완료 시 상태 갱신)

| # | Task | 모델 | 상태 | 완료 기준 |
|---|------|------|------|----------|
| T1 | ERP 주문탭 '시공 특이사항' 필드: PC(293-305 시공시간 뒤 col-12 collapse)+모바일(188 뒤) 템플릿, id `erp-construction-note` / collapse `erp-collapse-construction-note`, JS 수집 `notes.construction_note` 추가(:2083 뒤), JS 로드 추가(:1870 패턴), erp-order-shared.js ?v 핀 전수 범프 | sonnet | DONE(diff·APP_OK 직접 검증) | `python -c "import app"` APP_OK; grep으로 PC/모바일 템플릿·collect·load 4곳 존재 확인; ?v 핀 grep 전수 범프 확인 |

| T2 | 출고 주소셀 표시: dashboard_main.html extra_input static 블록(556-567) **삭제**, 그 자리에 시공 특이사항 static li 추가, `notes is mapping` 가드, title "시공 특이사항 연동" | sonnet | DONE(diff·is mapping 가드 직접 검증) | APP_OK; 로컬 렌더에서 시드 주문 주소 아래 표시 + extra_input 미표시; notes=문자열 주문 가드 (템플릿 mapping 체크 코드 확인) |
| T3 | AS 최신 자재 표시: `as_log.py`에 `latest_client_log_text(sd, log_type)` 헬퍼(soft-delete 제외, (ts,idx) 역순), `enrich_shipment_rows`에서 AS 건만 `r.as_material_text` 파생, AS 박스(519-522)에 "자재" 라벨+내용 추가 표시, pytest 단위테스트 | sonnet | DONE(diff·22 passed 직접 검증) | 신규 pytest green (deleted 제외·tie-break·타 type 무시·빈 로그); APP_OK; 로컬 렌더 확인 |
| T4 | 코드 리뷰 (2판정: 스펙 준수 / 코드 품질 분리) + 지적 반영 재위임 | opus | DONE(F1~F8 반영, 85 passed 직접 검증) | 리뷰 finding 전부 처리(수정 또는 근거 기각), diff 재확인 |
| T5 | 검증·배포·dev 테스트: pre_push_smoke exit 0 → 커밋 → deploy push → ci_watch green → lahom-dev 실데이터 시드로 3기능 직접 테스트(시드→확인→정리) → 최종 보고 | 메인 | DONE(CI green·lahom-dev E2E 22체크 ALL PASS·시드 정리 완료) | ci_watch exit 0; lahom-dev에서 (1) 저장·재로드 유지 (2) 주소 아래 표시 (3) AS 자재 최신 표시 육안 확인 |

## 결정 사항 (승인 시 확정)

- D1 (사용자 확정 2026-07-30): 주소셀 기존 extra_input 자동표시 **삭제**, 시공 특이사항 내용만 static 표시 (데이터는 items에 유지, 표시만 제거)
- D2: AS 박스는 기존 AS 내용 유지 + 아래 "자재: 최신내용" **추가** (대체 아님)
- D3: 표시 범위 = 데스크톱 출고 대시보드만 (모바일 큐·태블릿 시트는 이번 범위 제외)

## T4 리뷰 결과 (2026-07-30)

- 수정 반영(F1~F8 재위임): HIGH 2 — ?v 핀 계약테스트 2건 레드(test_erp_order_shared_form_scripts.py:70), as_material_text가 sanitize-HTML 그대로 노출(→ as_content_html_to_text(already_sanitized=True) 변환). MED — 신규 인라인 스타일 클래스화(+css 핀 범프), enrich 단위테스트 신설, CRITICAL_ERP_IDS 등재. LOW — helper legacy 제외, 함수 docstring, PC label for.
- 기각(근거): B7 비-dict shipment 방어 — 기존 build_as_timeline_view·enrich와 동일 패턴, 신규 위험 아님(별도 과제). B4b 템플릿 계약 테스트 — F6 단위테스트+F7 등재+T5 dev 육안이 커버. B9/B10 정보성(무위험 확인).

## 범위 밖 (손대지 않음)

- `foms/api/erp_orders_structured.py` (projection이 이미 통과시킴)
- site_extra 편집/저장 경로 (`foms/api/shipment/settings.py`, `foms/services/shipment/writer.py`)
- AS 대시보드 타임라인 UI (`templates/cs/`, `static/js/cs/as-dashboard.js`)
- 변환 텍스트 내보내기(erp-order-shared.js:4347) — 시공 특이사항 미포함
