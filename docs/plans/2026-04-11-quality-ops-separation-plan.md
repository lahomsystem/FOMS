# Quality / Operations Separation Plan
> 작성일: 2026-04-11
> 상태: active
> 목적: large-file 구조 배치와 섞이면 안 되는 품질/보안/운영 검증 항목을 별도 트랙으로 고정한다.

## 1. 배경
- `FOMS Final Modular Roadmap`는 구조 분해 배치와 품질/운영 배치를 분리하도록 명시했다.
- Wave A/B 구조 분해는 public contract 유지와 boundary 축소가 목적이므로, 보안 수정·동작 수정·운영 수동 검증은 같은 배치에서 처리하지 않는다.
- 이미 남아 있던 품질 후보는 기존 실행 문서와 상태 문서에서 반복적으로 식별됐다.

## 2. 별도 트랙으로 유지할 항목

### Track A. `foms/services/app_init.py`
- 근거:
  - `docs/AI_STATUS.md`의 알려진 이슈: 기본 관리자 자격 증명 fallback 잔존
  - `docs/plans/2026-04-10-step3-batch44-app-init-run-record.md`: fallback 정책 자체는 구조 턴에서 제외
  - `docs/plans/2026-04-08-step3-batch18-order-geocode-run-record.md`: 코어 변경이므로 승인형 품질 배치로 유지
- 분리 이유:
  - Auth/bootstrap 경계에 닿는 코어 변경이다.
  - 구조-only batch와 섞으면 root-cause 검증 범위가 불필요하게 커진다.
- 다음 액션:
  - Research: bootstrap/admin fallback 실제 사용 경로와 운영 의존성 재확인
  - Plan: fallback 제거/대체 정책, 로깅 정책, 초기 부트스트랩 운영 절차를 별도 spec으로 확정
  - Implement: 사용자 승인 후 별도 배치에서만 진행
- 완료 기준:
  - 기본 관리자 fallback 제거 또는 명시적 운영용 대체 절차 확정
  - `APP_OK`, focused tests, bootstrap smoke 재검증

### Track B. `apps/api/erp_orders_structured.py`
- 근거:
  - `docs/AI_STATUS.md`의 알려진 이슈: `structured_data` 미전달 분기에서도 Channel payload/mark 로직 선실행 가능
  - `docs/plans/2026-04-08-step3-batch18-order-geocode-run-record.md`: Channel gating / 빈 주소 reset 조건은 별도 품질 배치로 유지
  - `docs/plans/2026-04-08-step3-batch20-channel-wam-view-models-run-record.md`: 같은 품질 후보가 다시 고우선으로 식별됨
- 분리 이유:
  - API side effect 순서와 external channel payload 계약에 닿는다.
  - structure-only refactor와 함께 다루면 behavior change 여부 판단이 어려워진다.
- 다음 액션:
  - Research: `structured_data`, empty address, channel payload/mark 순서의 실제 호출 흐름 캡처
  - Plan: 순서 보장 규칙과 negative cases를 별도 spec으로 고정
  - Implement: 승인 후 focused regression과 함께 독립 수행
- 완료 기준:
  - `structured_data` 미전달/빈 주소/Channel payload 순서에 대한 focused tests 확보
  - 기존 동작과 바뀐 동작의 차이가 명시적으로 문서화됨

### Track C. Measurement legacy JS / CSP
- 근거:
  - `docs/AI_STATUS.md`: legacy measurement JS shim은 계속 `document.write` loader 사용
  - `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md`: strict CSP / async loader / bundler 전환은 별도 단계 필요
- 분리 이유:
  - 프론트엔드 runtime load-order와 CSP 정책 변경은 명백한 behavior/security change다.
  - Step 5/6의 structure-only JS 분해와 섞으면 root cause가 흐려진다.
- 다음 액션:
  - Inventory: current loader contract, global symbol 의존, CSP blockers 정리
  - Plan: `document.write` 제거, async loader, strict CSP 호환 전략을 별도 frontend quality plan으로 설계
  - Implement: 브라우저 회귀와 CSP smoke를 포함한 독립 배치
- 완료 기준:
  - measurement legacy loader 제거 또는 명시적 compat shim 축소
  - strict CSP 시나리오와 브라우저 load-order 회귀 검증 완료

### Track D. `docs/AI_STATUS.md` 수동 검증 항목
- 현재 운영 체크리스트:
  - 실측 summary panel vs 지도/대시보드 parity 확인
  - `/erp/measurement?open_map=1` 지도 E2E
  - `python scripts/fix_geocode_status_inconsistency.py` 1회 실행
  - 시공팀 접근 제한 + mine 필터 수동 테스트
  - 출고 대시보드 시공자 그룹 파스텔 색상 확인
  - 성능 체감 속도 확인
- 분리 이유:
  - 모두 운영 확인 또는 수동 QA이며 구조 배치의 완료 기준과 다르다.
  - 구조 refactor batch에 묶으면 “코드 변경 없음”인데도 검증 책임이 섞인다.
- 다음 액션:
  - 운영 QA checklist로 유지
  - 배포 전/후 수동 실행 결과를 별도 run record에 남긴다
- 완료 기준:
  - 각 체크 항목이 pass/fail + 근거와 함께 기록됨

## 3. 운영 규칙
- 위 4개 트랙은 구조 분해 batch의 acceptance criteria에 넣지 않는다.
- `app_init.py`, `erp_orders_structured.py`는 코어 변경이므로 Research -> Plan -> 사용자 승인 후 구현한다.
- measurement loader/CSP는 frontend quality batch로만 연다.
- `docs/AI_STATUS.md` 수동 검증은 release/ops checklist로만 관리한다.

## 4. 이번 턴의 판정
- Wave A/B large-file decomposition 완료와 별개로, 위 항목들은 의도적으로 미구현 상태로 남긴다.
- 미구현은 누락이 아니라 roadmap에서 요구한 separation completion이다.
