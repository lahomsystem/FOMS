# Progress Ledger — 출고 AS 일정추천 타임라인 + 카카오 지도 (2026-07-30)

플랜: `docs/plans/2026-07-30-shipment-asrec-timeline-kakao-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 타임라인 CSS 컴포넌트 분리 | DONE | `components/foms-as-timeline.css` 신규(코어 33선택자 이전), CS 파일에 남은 6건은 `.as-tl-expand-body` 오버라이드만 |
| T2 매크로 show_more + 출고 partial | DONE | `render_as_timeline(..., show_more=true)` 기본값, 출고 partial은 `can_edit=false, show_more=false` |
| T3 백엔드 timeline HTML 주입 | DONE | `_render_asrec_timelines` 배치 1회 조회·id당 1렌더, prewarm 스킵, legacy 키 pop. 신규 테스트 6건 green |
| T4 출고 JS 본문 렌더 교체 + ?v | DONE | `hydrateAsRecTimelines` + `.asrec-timeline-slot`, `?v=20260730f` 전 핀 일치 |
| T5 공용 카카오 지도 모듈 + Leaflet 제거 | DONE | `static/js/common/foms-schedule-map.js` 신규, 출고 Leaflet 185줄·CS 201줄 제거, 양쪽 위임 호출 |
| T6 출고 kakao_js_key 배선 | DONE | `dashboard.py` 컨텍스트 + `#scheduleMapContainer[data-kakao-js-key]`, 렌더 계약 테스트 추가 |
| T7 최종 검증·커밋·푸시 | IN PROGRESS | 타깃 스윕 154 passed / APP_OK. pre_push_smoke → deploy push → ci_watch 남음 |

## 검증 기록

- `python -c "import app; print('APP_OK')"` → `APP_OK`
- `pytest tests/domains/test_erp_mobile_layout_and_shipment.py test_shipment_asrec_timeline.py
  test_shipment_as_recommendations.py test_as_timeline_wiring.py test_as_timeline_fragment.py
  test_shipment_dashboard_mobile.py tests/performance/test_page_local_defer_contract.py
  test_perf_regression_guard.py -q` → **154 passed**

## 오케스트레이터 직접 수정 (서브에이전트 결과 마무리)

- `templates/shipment/dashboard.html`: 새 CSS 링크를 `{% block head_extra %}`(→ `shipment/layout.html`
  에 대응 블록이 없어 **렌더되지 않는 죽은 블록**)에서 `{% block styles %}` 로 이동. 전체 페이지 로드에서
  타임라인이 미스타일로 뜨는 문제를 막는다. 회귀 방어로 실제 렌더 응답을 검사하는 계약 테스트 추가.

## 남은 것

- 스테이징 실브라우저 확인: 모달 카드 본문 타임라인 렌더 + 지도 버튼 카카오 타일/폴리라인
  (로컬 dev 는 카카오 콘솔 미등록 도메인이라 지도만 폴백 문구로 뜬다 — 코드 문제 아님).
- production 승격은 사용자 승인 후 세션 커밋 cherry-pick.
