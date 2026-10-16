# 지방 대시보드 직접 완료 Spec
> 작성일: 2026-10-16 | 상태: ✅ 구현·로컬 검증 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
지방 대시보드 설치 예정 주문의 [완료]를 누르면 현재 ERP 단계가 생산이어도
CS 단계 이동이나 CS 퀘스트 승인을 거치지 않고 최종 완료한다.
완료한 주문은 같은 보드의 완료 섹션으로 이동한다.

### 1.2 기능 요구사항
1. 서버의 `Order.is_regional`이 참인 ERP 주문에만 직접 완료 정책을 적용한다.
2. 기존 완료 버튼과 확인창을 사용하고, 기존 완료 API가 서버 주문 속성으로 정책을 선택한다.
3. 지방 주문은 CS 단계 전제와 CS 퀘스트 승인을 요구하지 않는다.
4. 권한, 보류, 진행 중 AS, 삭제, 미승격 초안, 동시 수정 충돌 검사는 유지한다.
5. canonical 전이 엔진으로 최종 상태를 기록하고, 현재 시공 attempt 종료·완료 이력·감사 로그를
   같은 트랜잭션으로 남긴다. 이력에는 실제 행위인 '지방 주문 완료'를 기록한다.
6. 일반 주문의 CS 완료 규칙과 AS 전용 완료 버튼은 유지한다.

### 1.3 예외/제약 조건
- 현재 주문 #5498 자체는 변경하지 않는다. 기능 변경과 테스트만 수행한다.
- 요청 body, Referer 또는 화면에서 보낸 플래그로 지방 주문 여부를 결정하지 않는다.
- 관리자의 강제 진행 기능을 자동 호출하거나, 거치지 않은 단계를 완료했다고 꾸미지 않는다.
- 일반 `field_update(status=COMPLETED)` 우회로를 열지 않는다.
- 신규 DB 컬럼·마이그레이션·목록 쿼리 추가는 없다.
- 기존 AS 완료 오버레이가 있는 주문은 AS 이력을 보존하고, 기존 AS 완료 탭 표시를 유지한다.
  일반 설치 예정 주문은 지방 완료 섹션으로 이동한다.
- 이번 지방 완료 변경의 배포는 별도 요청 범위로 판단한다. 앞선 문구 수정의 deploy 배포와 분리한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/services/orders/complete_path_policy.py` | 서버 지방 판정과 직접 완료 CTA, 보류·AS·권한 사유 일치 |
| `foms/services/orders/cs_complete_service.py` | 지방 전용 canonical 완료 command와 정책 선택, 공통 완료 후처리 재사용 |
| `foms/api/cs/complete.py` | 기존 완료 API의 지방 완료 성공 안내와 서비스 연결 |
| `foms/services/order_event_display.py` | 지방 완료 이벤트의 한국어 제목·설명 |
| `tests/domains/test_cs_complete_from_measure_board.py` | 지방 생산 단계→완료, UI/API 일치, 일반 주문·권한·보류·AS 대조군 |
| `tests/domains/test_regional_direct_complete.py` | 지방 완료·receipt 경계·전체 원복·실제 보드 섹션 검증 |
| 관련 완료·전이 테스트 | 중복 요청, 버전 충돌, 완료 부수효과·감사 검증 |
| `docs/ARCHIVE_INDEX.md` | 스펙 인덱스 등록 |

### 2.2 아키텍처 방향
- 현재 지방 보드는 `build_complete_ctas` 결과를 그대로 렌더한다.
- 현재 `complete_block_reason`은 모든 ERP 주문에 CS 단계 전제를 부과한다.
- 현재 완료 서비스는 `CS_COMPLETE` command의 source를 CS로 제한한다.
- 지방 정책을 CTA와 서비스가 함께 사용하고, 지방 전용 command는 기존 canonical 활성 단계에서
  COMPLETED로 이동한다. 일반 CS command의 source 범위는 넓히지 않는다.
- 완료 후처리는 재사용하되 지방 완료를 CS 승인 완료로 기록하지 않는다.
- 완료 후 남은 물류 SCHEDULED가 main COMPLETED를 가리는 것이 테스트에서 확인됐다.
  같은 트랜잭션에서 기존 `SET_LOGISTICS_STATUS` 전이로 물류 축을 NONE으로 종료한다.
  일반 주문이나 공용 투영 우선순위는 변경하지 않는다.

### 2.3 의존성 및 영향 범위
- 지방 주문에만 새 업무 정책을 적용한다. 수도권·자가실측 일반 주문의 완료 정책은 유지한다.
- 기존 전이 엔진의 행 잠금·expected_from·mutation_version·receipt·outbox 규약을 유지한다.
- 이벤트·정책 추가 시 mutation policy 및 상태 guard 인벤토리 소비자를 대조한다.

## 3. Steps — 실행 단계
- [x] 실제 지방 템플릿, CTA, 완료 API, 완료 서비스, 전이 command 추적
- [x] DECISIONS.md·ARCHIVE_INDEX.md 조사와 영향 범위 확정
- [x] 사용자 계획 승인
- [x] 지방 직접 완료 정책과 canonical command 구현
- [x] UI/API 및 일반 주문 대조 테스트
- [x] 결과 검증·성능 가드·코드 재검토

## 4. 검증 기준
- [x] 지방 ERP 주문: main PRODUCTION + board SCHEDULED에서 버튼 활성화 및 API 완료 성공
- [x] 지방 ERP 주문: CS 퀘스트 미승인이 직접 완료를 막지 않음
- [x] 일반 ERP 주문: 생산 단계 완료 거부와 CS 필수 승인 규칙 유지
- [x] 권한 없음·보류·진행 중 AS·삭제·미승격 초안은 완료 거부
- [x] 완료 후 workflow.stage·erp_stage_code·order.status 및 완료 섹션 일치(AS 완료 오버레이 예외 유지)
- [x] 시공 attempt 종료와 지방 완료 이력·감사 로그가 정상 기록됨
- [x] 중복 요청의 추가 이벤트·side effect 없음, 동시 수정 충돌 유지
- [x] `python -c "import app; print('APP_OK')"` 통과
- [x] 관련 pytest, 성능 가드, `verify_result.py --require-spec --json` 통과

### 검증 근거와 범위
- 지방 전용 테스트 22개, 완료·권한·REV·상태 guard 관련 테스트 129개 통과.
- 최종 `pre_push_smoke.ps1`: 전체 12,575 passed / 714 skipped, UI 구조 174 passed / 27 skipped.
- gstack browse + 로컬 Flask + 별도 SQLite: 실제 완료 버튼·확인창·API·페이지 새로고침·완료 섹션 이동 확인.
- 독립 재검토 CLEAR. 다른 주문의 같은 key 재사용(순차 및 동시 승자 receipt 모의 경계) 거부 확인.
- 실제 PostgreSQL 병렬 경합 및 실서버 배포 검증은 이번 로컬 검증 범위에 포함하지 않았다.
- 실주문 #5498은 변경하지 않았다.

## 5. 참고 자료
- `docs/harness/policy/DECISIONS.md`
- `docs/ARCHIVE_INDEX.md`
- `templates/measurement/regional_dashboard.html`: 설치 예정 섹션의 완료 컨트롤
- `templates/partials/shared/status_select_options.html`: 서버 CTA 기반 버튼 렌더
- `foms/services/orders/complete_path_policy.py`: 화면·서버 완료 경로 판정
- `foms/services/orders/cs_complete_service.py`: canonical 완료와 동일 트랜잭션 후처리
