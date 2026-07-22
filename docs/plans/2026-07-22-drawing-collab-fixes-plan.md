# 도면 협업 수정 6건 (2026-07-22, 사용자 항목별 승인 완료)

조사 원자료: 세션 조사(erp_orders_revision/drawing/draftsman·workbench·erp-dashboard-detail-dom 전수) + 브리핑 artifact. 아래 file:line은 조사 확정값.

## 승인된 범위
1. **컨펌 후 수정요청 진입로**: ERP 도면탭 CONFIRMED 분기 + 워크벤치 목록 CONFIRMED 조회 — 둘 다
2. **수령확정 상태 가드**: `drawing_status=='TRANSFERRED'`에서만 허용
3. **알림 추가 2종**: 전달취소→영업, 수정요청취소→도면팀 (수령확정 알림은 미승인 — 제외)
4. **Blueprint V3 죽은 코드 삭제**: `api_drawing_request_revision`(erp_orders_revision.py:456)·`api_drawing_complete_revision`(:522) + 전용 헬퍼·테스트
5. 도면팀 자가 수정요청: **무변경** (승인상 현행 유지)
6. **담당 미지정 배지**: 워크벤치 목록만 (벨 알림 없음)

## B (백엔드 — impl-backend)
- **가드**: `erp_orders_draftsman.py:286` `api_order_confirm_drawing_receipt` — 본문 초입에 `drawing_status != 'TRANSFERRED'` → 400 `{'success': False, 'message': '전달된 도면(확정 대기 상태)에서만 수령 확정할 수 있습니다.'}`. ADMIN·오버라이드 포함 전원 적용(상태 정합성 가드는 권한 우회 대상 아님).
- **알림 A — 전달취소→영업**: `erp_orders_drawing.py` cancel-transfer 라우트(:494 부근)에 Notification 생성 — type `DRAWING_TRANSFER_CANCELLED`, 타깃 라우팅은 전달 알림(:227-233)과 동일 규칙(매니저명 라홈→CS/하우드→HAUDD/그외→SALES+target_manager_name). fan_out+commit후 finalize(기존 전달 알림 패턴 미러).
- **알림 B — 수정요청취소→도면팀**: `erp_orders_revision.py` `api_order_cancel_revision_request`(:274)에 type `DRAWING_REVISION_CANCELLED`, target_team='DRAWING'. 동일 패턴.
- **죽은 코드 삭제**: 두 라우트 + 이들만 쓰는 blueprint.revisions 헬퍼·상수·테스트 grep 전수 제거. 삭제 전 호출 0건 재확인(`{js,html,py}` grep).
- **워크벤치 CONFIRMED 조회**: `workbench.py:330-333` seed 확장 — query param `include_confirmed=1`일 때 `drawing_status=='CONFIRMED'`(stage CONFIRM) 주문 포함. 기본 목록 불변(노이즈 방지). row에 `drawing_status` 이미 있으면 재사용.
- **담당 미지정 플래그**: workbench rows dict에 `no_assignee: bool`(DRAWING_DOMAIN assignee 0명) 추가.
- pytest: 가드(TRANSFERRED 외 400·TRANSFERRED 정상)·알림 2종(생성+타깃+fan_out, 취소류 조건)·죽은코드 라우트 404·include_confirmed 필터·no_assignee 플래그.

## F (프론트 — impl-frontend)
- **ERP 도면탭 CONFIRMED 분기**: `static/js/orders/dashboard/erp-dashboard-detail-dom.js:316-401` — 현재 `stage==='DRAWING'` 게이트를 확장: `stage==='CONFIRM' && drawing_status==='CONFIRMED'`이면 축약 블록 렌더 — 상태 라벨("도면 완료") + [수정 요청] 버튼(기존 `openRevisionRequestModal` 재사용, 노출 조건은 TRANSFERRED 분기의 영업측 조건과 동일 `canEdit && (sales/manager/admin)`). 도면팀측 버튼은 렌더 안 함.
- **워크벤치 토글**: 대시보드 필터 영역에 "컨펌 포함" 토글(링크/체크 — `include_confirmed=1` 쿼리 왕복, fragment 링크 규약 준수).
- **담당 미지정 배지**: 목록 행 `r.no_assignee` → 경고 배지 "담당 미지정" (기존 `dw-order-change-badge` 문법 참고, danger 톤).
- 캐시: erp-dashboard-detail-dom.js 로드 지점 ?v 확인 후 범프+핀 grep 전수(정본 절차). 워크벤치 템플릿 인라인 스타일 partial 체계 준수(인라인 스타일 신규 금지 — 기존 partial 스타일 블록에 추가).
- 계약 테스트: CONFIRMED 분기 문자열·토글·배지 assert.

## 검증 (오케스트레이터 직접 — dev 서버 E2E)
1. pytest 전 스위트 서브셋 + APP_OK
2. 로컬 dev 서버 기동(포트 5000 stale 서버 PowerShell 정리 후 단일 서버 — 메모리 함정) + gstack browse:
   - 시드 주문으로 전달→수정요청→반영완료 체크→재전달→수령확정 전 사이클 API/UI 확인
   - 가드: RETURNED 상태에서 수령확정 API 직접 호출 → 400 확인
   - 전달취소/수정요청취소 → Notification row + 대상 팀 확인 (DB 직접 조회)
   - CONFIRMED 주문: ERP 도면탭 수정요청 버튼 렌더 + 실제 요청 → RETURNED 복귀 + 워크벤치 목록 재노출
   - include_confirmed 토글·담당 미지정 배지 렌더
   - 죽은 라우트 404
3. pre_push_smoke → push → CI 3종

## 경계
- 생산 칸반·production_change_alerts 무터치(도면 변경 감지는 transfer_history 기반이라 자동 연동 — cancel류 action은 감지 대상 아님 유지).
- `_can_modify_sales_domain`·권한 모델 무변경(항목5 승인대로).
