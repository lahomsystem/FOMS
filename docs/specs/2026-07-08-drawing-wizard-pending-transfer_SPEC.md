# 도면 마법사 — 저장/전달 분리 + 작업실 일괄 전송 Spec
> 작성일: 2026-07-08 | 상태: 🟢 승인됨 (사용자 워크플로 확정: 마법사=저장만, 작업실 일괄 전송) | 작성: Claude (Advisor)

## 배경
현재: 마법사 [저장] = 시트 상태 PUT + PNG를 주문 '도면' 탭(OrderAttachment category='drawing')에 자동 저장. 담당자 전달 = 마법사 내보내기→도면 전달(개별). 사용자 요구: **저장 시 도면 탭 저장 금지, 담당자 전송은 도면 작업실에서 여러 주문 골라 일괄**.

## 새 워크플로
1. 마법사: 도면 그림 → [저장] = 시트 상태 + **PNG를 '전달 대기'로 보관**(도면 탭 아님). 담당자 전송 안 함.
2. 도면 작업실 대시보드: 주문 행에 **전달 대기 N장** 표시 + 체크박스 → 상단 **[선택 도면 일괄 전송]** → 메모/모드 → 각 주문의 대기 도면을 담당자에게 transfer.

## 설계 결정
- **전달 대기 보관 = structured_data['drawing_wizard']['pending']** (dict `{sheet_id: {key, filename, at, sheet_name}}`). R2 PNG는 `orders/{id}/drawing_wizard/exports/`. **OrderAttachment 미생성**(도면 탭과 완전 분리). 같은 sheet_id 재저장 = 덮어쓰기 + 구 R2 삭제. 시트 삭제 시 pending 정리(선택, v1은 전달 시 정리).
- 전달 실행 = 기존 `transfer-drawing` API 재사용(알림·drawing_current_files·히스토리 SSOT 불변). 작업실 일괄 = 프론트가 선택 주문별로 순차 호출(또는 신규 배치 래퍼).

## 파일/작업 (순차: U → V)

### W-U (백엔드 + 마법사 프론트)
- `foms/api/drawing/wizard.py`:
  - `sheet-png` 변경: OrderAttachment(category='drawing') 저장 제거 → R2 exports 업로드 후 `sd.drawing_wizard.pending[sheet_id] = {key, filename, at(KST), sheet_name}` 기록(deepcopy+flag_modified, updated_at 무변경=낙관잠금 무충돌). 구 pending key 있으면 R2 삭제. 응답 `{success, data:{key}}`(attachment_id 제거).
  - 신규 `GET /<id>/drawing-wizard/pending` (login): pending 목록 반환.
  - 신규 `POST /<id>/drawing-wizard/transfer-pending` (참여자/ADMIN): body `{note, mode}` → 그 주문 pending의 key들을 files로 만들어 **transfer-drawing 내부 로직 호출**(또는 동일 처리) → 성공 시 pending 비움(전달됨). 담당자 알림 등은 transfer-drawing이 처리. 응답 `{success, data:{count}}`.
    - 구현: transfer-drawing의 핵심을 공용 함수로 추출하거나, files 조립 후 기존 엔드포인트 함수 재사용. gateway-upload 불필요(pending key가 이미 R2에 있음 → files=[{key,filename}] 직접).
  - GET `/drawing-wizard` 응답에 `pending_count` 추가(선택).
- `static/js/drawing/wizard.js` / `wizard.html`:
  - 저장: saveSheetPng 유지하되 응답 처리에서 attachment_id 로직 제거, 토스트 "저장됨 · 전달 대기함에 보관"으로. 시트에 attachment_id 대신 무관.
  - **"도면 전달" 제거**: 내보내기 메뉴에서 `dws-btn-export-transfer` 항목 제거(PNG 다운로드는 유지). 전달 다이얼로그/runBatchTransfer/시트 체크박스 등 전달 관련 코드 제거 또는 비활성(죽은 코드 정리). 버전 스냅샷은 전달 트리거였으므로 → v1은 전달이 작업실로 이동하니 스냅샷 시점도 작업실 전송 시로(또는 유지·후속). **간결화: 마법사에서 전달 경로만 제거, 스냅샷은 작업실 transfer-pending 성공 시 서버에서 처리하거나 생략.**
  - 캐시버스터 상향.
- 테스트: sheet-png가 pending 저장(OrderAttachment 미생성) 왕복, transfer-pending이 transfer-drawing 효과(drawing_current_files/status) + pending 비움, 권한.

### W-V (작업실 대시보드 일괄 전송 UI)
- `foms/web/drawing/workbench.py`: 대시보드 row에 `pending_count`(sd.drawing_wizard.pending 길이) 추가.
- `templates/drawing/partials/workbench_dashboard_*`: 행에 "대기 N" 배지 + 체크박스(대기>0인 행만), 상단 "선택 도면 일괄 전송" 버튼 → 다이얼로그(메모/모드 select) → 선택 주문별 `POST transfer-pending` 순차 → 진행/요약 토스트, 대시보드 새로고침.
- 모바일 v2 핸드오프는 범위 밖(데스크톱 대시보드만).
- 테스트: dashboard render에 pending 배지, transfer-pending 호출 계약.

## 검증
- APP_OK, node --check, 위저드+워크벤치 pytest green, perf guard green.
- E2E: 마법사 저장→도면 탭에 안 생김·pending에 기록 확인 → 작업실 대시보드 "대기 N" 표시 → 일괄 전송 → transfer-drawing 효과(status TRANSFERRED, drawing_current_files) + pending 비움, 콘솔 0.
- 기존 저장 주문/기존 전달 히스토리 회귀 없음.

## 리스크
| 리스크 | 완화 |
|--------|------|
| 기존 도면 탭에 저장된 PNG(구 sheet-png) | 남겨둠(과거 저장분). 신규 저장만 pending으로. 마이그레이션 불필요 |
| transfer-drawing 로직 재사용 시 중복/side effect | 핵심 함수 추출 or files 조립 후 동일 경로. 알림 1회 보장 |
| 낙관잠금 | pending/versions는 updated_at 안 건드림(별도 필드) |
