# FOMS <> ChannelTalk 개인 알림 + 공통 알림 세부 실행 계획
작성일: 2026-03-27
상위 계획: `docs/plans/2026-03-26-foms-channeltalk-integration-focus-plan.md`
목적: `개인 involved 알림 + 공통 notice + 빠른 FOMS 접근` 구조를 실제 구현 가능한 작업 순서로 확정한다.

중요: 아래는 `현재 기능 설명`이 아니라, 2026-03-27 기준 `목표 상태와 실행 순서`를 적은 문서다.

## 1. 이번 실행 계획의 한 줄 목표

`주문/Task 변경이 생기면, 관련 당사자는 개인 메시지로 바로 받고, 팀 전체가 알아야 하는 건은 공통 그룹에서도 받게 만든다.`

## 2. 현재 상태 요약

- 이미 있는 것
  - 그룹 메시지 전송
  - 수동 푸시
  - 일부 자동 푸시
  - 짧은 링크 + WAM read-only
  - 기본 health / backlog / delivery log
- 아직 부족한 것
  - 개인 알림 transport
  - involved person 계산 규칙
  - 하나의 이벤트를 여러 대상에게 보내는 multi-target outbox
  - 관리자용 resend/requeue 운영 화면
  - manager mapping 운영 절차
  - personal/notice 분리 관측성

## 3. 최종 목표 모델

### 3.1 발송 모드

1. `personal`
- involved person에게만 보낸다.
- 예: 담당자 변경, 내 task 변경, 내 일정 변경

2. `notice`
- 공통 그룹에만 보낸다.
- 예: 긴급 공지, 팀 전체 일정 확정, 운영 알림

3. `both`
- 개인 involved person + 공통 그룹 둘 다 보낸다.
- 예: 긴급 일정 변경, 고객 클레임 급건

### 3.2 핵심 정책

- 개인 알림은 `인지`가 목적이다.
- 공통 notice는 `공유`가 목적이다.
- 모든 메시지에는 주문 접근 링크를 넣는다.
- FOMS는 원본이고, ChannelTalk는 전달 창구다.

## 4. 선행 결정사항

### 4.1 개인 알림 대상 규칙

우선순위는 아래 순서로 고정한다.

1. `담당자`
2. `task assignee`
3. `drawing manager`
4. `construction worker`
5. `owner team 실제 수신자`

같은 사람이 여러 역할에 걸리면 1회만 발송한다.

개인 알림의 canonical target identity는 `manager`로 고정한다.
- dedupe, resend, 지표 집계는 manager 단위로 계산한다.
- `direct_chat`은 실제 transport 선택 결과이며, canonical key를 대체하지 않는다.

### 4.2 이벤트 분류 규칙

#### 개인 알림 우선
- `task_assigned`
- `task_status_changed`
- `manager_changed`
- `schedule_changed`
- `approval_requested`
- `payment_confirmation_changed`
- 단, `task_*` 계열은 `task-event-contract.md`가 닫히기 전까지 분류표상 목표 상태로만 두고, 초기 rollout 대상에는 넣지 않는다.

#### 공통 notice 우선
- `urgent`
- `major_stage_changed`
- `construction_issue`
- `operations_notice`

#### 둘 다
- `urgent + involved person 존재`
- `고객 클레임 급건`
- `당일 일정 급변경`

#### 명시 규칙
- `mapping miss` 기본 정책은 `skip + 운영 로그`다.
- personal-only 이벤트를 notice로 자동 승격하지 않는다.
- notice 또는 both로 분류된 이벤트만 공통 그룹 row를 별도로 생성한다.
- 여기서 `fallback`은 `개인 transport fallback`만 뜻한다.
- `personal -> group notice` 자동 승격은 fallback으로 부르지 않는다.
- manual push는 계속 admin/manual group-only 경로로 유지한다.
- WAM/Command는 read-only access surface이며, personal routing transport 자체와 섞지 않는다.
- 이번 실행 계획은 outbound push 확장 문서다. webhook/inbound phase를 자동으로 앞당기지 않는다.

## 5. 구현 워크스트림

### WS-A. Capability Spike
목적: ChannelTalk 개인 메시지 전송 경로를 확정한다.

작업:
1. Native Function 후보 정리
2. `writeUserChatMessage` vs `writeDirectChatMessageAsManager` 비교
3. 현재 앱 권한과 실제 호출 컨텍스트 검증
4. 모바일 푸시 도달률 실험 기준 정의

완료 기준:
- 개인 메시지 transport를 하나로 결정
- fallback transport를 하나 더 정리
- `transport-decision.md`
- `payload-fixture-proof.md`
- `mobile-push-test-matrix.md`

### WS-B. Identity / Mapping
목적: FOMS 사용자와 ChannelTalk manager를 연결한다.

작업:
1. `ChannelManagerLink` 조회/생성/비활성화 운영 흐름 정의
2. 관리자용 매핑 확인 API 추가
3. 매핑 누락 시 처리 규칙 정의
4. 개인 알림 대상 계산 헬퍼 작성

완료 기준:
- `get_personal_targets(order, event)` 계열 서비스가 존재
- 매핑 누락 시 `skip + 운영 로그` 정책 확정
- `mapping-readiness.md`에 pilot 대상자 coverage가 기록됨

### WS-C. Routing Policy
목적: 한 이벤트가 personal / notice / both 중 어디로 가는지 고정한다.

작업:
1. runtime policy 함수 추가
2. 이벤트별 send_mode 정의
3. target list 반환 계약 정의
4. dedupe 규칙: 동일 대상 중복 제거

완료 기준:
- `resolve_delivery_targets(event_type, payload, order_snapshot)`가 target list를 반환
- `event-matrix`, `routing-policy-table`, `message-template-catalog`의 용어가 서로 일치

### WS-D. Outbox / Dispatch 확장
목적: 하나의 이벤트가 여러 대상에게 가도 delivery log가 분리되게 한다.

작업:
1. `ChannelDeliveryLog` 생성기를 multi-target 지원으로 확장
2. `target_type=group|manager|direct_chat` 처리
3. dispatch service에서 target_type별 전송 분기
4. stale / retry / failure 상태 유지

완료 기준:
- 하나의 이벤트가 개인 2명 + 그룹 1개면 delivery row 3개 생성

### WS-E. ERP 이벤트 연결
목적: 현재 자동 푸시 경로를 새 라우팅 정책에 연결한다.

작업:
1. structured save 경로 연결
2. measurement update 경로 연결
3. shipment settings 경로 연결
4. payment confirmation 경로 연결
5. task 변경 경로는 `task source-of-truth / source_version 계약`이 먼저 닫힌 뒤 별도 단계로 추가

완료 기준:
- 적어도 `담당자 변경`, `일정 변경`, `긴급 변경`이 personal/notice 정책에 맞게 발송
- task 이벤트는 초기 personal rollout의 필수 종료 조건으로 잡지 않는다.

### WS-F. 운영 / 관측성
목적: 운영자가 backlog와 실패를 실제로 다룰 수 있게 한다.

작업:
1. delivery-status API 보강
2. resend / requeue API 추가
3. 개인 알림 / 공통 알림 분리 지표 추가
4. health에 mapping / direct transport 점검 항목 추가

완료 기준:
- 관리자 화면 또는 API에서 `personal sent`, `notice sent`, `mapping miss`, `direct send fail` 확인 가능
- 최소 `requeue` 경로가 pilot 이전에 존재

## 6. 단계별 실행 순서

### Phase P0. Capability / Mapping Gate
1. 개인 메시지 transport 확정
2. manager mapping 흐름 확정
3. 이벤트 분류표 확정
4. task source-of-truth 범위 결정
5. 모바일 푸시 측정 기준 확정

산출물:
- `transport-decision.md`
- `routing-policy-table.md`
- `mapping-readiness.md`
- `mobile-push-test-matrix.md`
- `payload-fixture-proof.md`
- `mapping 운영 규칙`
- `task-event-contract.md`

진입 조건:
- 없음

종료 조건:
- 개인 알림 transport를 코드에 넣어도 되는 상태
- pilot 대상자 mapping coverage와 fallback 정책이 문서로 판정 가능한 상태

### Phase P1. Multi-target Core
1. routing service 구현
2. multi-target outbox 구현
3. dispatch 분기 구현
4. 최소 관측성 추가
5. 최소 requeue 경로 추가
6. 단위 테스트 추가

종료 조건:
- 그룹/개인 혼합 발송이 테스트로 검증됨
- `personal sent`, `notice sent`, `mapping miss`, `direct send fail`, `fallback used`를 API/지표로 확인 가능

### Phase P2. ERP 연결
1. 담당자 변경 -> personal
2. 일정 변경 -> personal or both
3. 긴급 이벤트 -> both
4. manual push는 group-only 유지 확인

종료 조건:
- 대표 시나리오 4개 이상이 실발송 검증 완료

### Phase P3. 운영 안정화
1. delivery-status 보강
2. resend / requeue
3. health 보강
4. 관리자용 운영 점검표
5. task 이벤트 확장 여부 결정 및 별도 계약 착수

종료 조건:
- 운영자가 backlog와 실패를 직접 추적 가능

### Phase P4. 파일럿
1. 소규모 팀 파일럿
2. 모바일 백그라운드 알림 실측
3. 소음 조정
4. 전체 확대 여부 결정

종료 조건:
- 개인 알림 도달률과 소음 수준이 허용 범위에 들어옴

## 7. 구현 티켓 초안

### EP-01 개인 메시지 transport spike
- 공식 문서 기준 Native Function 후보 확정
- 앱 권한 요구사항 정리
- 채택 transport 1개와 fallback 1개를 문서로 고정
- 실제 payload/permission proof 확보

### EP-02 manager mapping 운영 API
- 조회 API
- 활성/비활성 전환 API
- 누락 상태 조회 API
- pilot 대상자 coverage 집계

### EP-03 personal target resolver
- order snapshot -> manager/user/direct chat target 계산
- canonical key는 manager로 고정

### EP-04 routing policy runtime module
- event_type + payload -> send_mode + targets 계산

### EP-05 multi-target delivery row 생성
- event 1건 -> delivery N건

### EP-06 dispatch target_type 분기
- group
- manager
- direct_chat

### EP-07 task 이벤트 연동
- task assign / status change 시 payload 생성
- 단, `task-event-contract.md`가 닫힌 뒤 후속 티켓으로 분리

### EP-08 admin observability 확장
- personal / notice 지표 추가
- mapping miss 추가
- direct send fail 추가
- fallback used 추가

### EP-09 resend / requeue 운영 API
- 실패건 재시도
- backlog 강제 enqueue
- pilot 이전 최소 버전 선행

### EP-10 pilot 운영 점검표
- 알림 수신 여부
- 모바일 푸시 여부
- 클릭 후 접근 시간
- 앱 설정별 수신 결과

## 8. 감리 체크포인트

### 감리 1. 계획 반영 감리
확인 항목:
- 계획서가 개인 알림 + 공통 notice 구조로 바뀌었는가
- group-only 설명이 남아 있지 않은가
- mobile push 목적이 문서에 명시됐는가

### 감리 2. 실행 계획 감리
확인 항목:
- 개인 transport 확정 전에 outbox 확장부터 들어가려는 순서 오류가 없는가
- mapping 없이는 개인 알림이 동작하지 않는다는 점이 반영됐는가
- 운영/관측성 단계가 빠지지 않았는가
- `mapping miss` 기본 정책이 문서 안에서 하나로 고정돼 있는가
- task 이벤트가 order outbox 계약과 충돌 없이 분리돼 있는가

### 감리 3. 최종 감리
확인 항목:
- 개인 / 공통 / 둘 다 기준이 오해 없이 정리됐는가
- 현재 구현과 미래 계획이 섞여 있지 않은가
- 설명서에 반드시 들어가야 할 주의사항이 실행 계획에도 반영됐는가

## 9. 리스크와 대응

1. 개인 메시지 transport가 앱 권한/컨텍스트에 맞지 않을 수 있다
- 대응: Phase P0 capability spike를 선행

2. manager mapping이 운영적으로 비어 있을 수 있다
- 대응: 매핑 누락 시 기본 `skip + 운영 로그`, 자동 group fallback 금지

3. 개인 알림이 너무 많아질 수 있다
- 대응: send_mode 표와 dedupe 규칙을 먼저 확정

4. 모바일 푸시가 ChannelTalk 앱 설정에 좌우될 수 있다
- 대응: 파일럿 단계에서 앱 설정 가이드 포함

5. task 이벤트를 섣불리 붙이면 order source-of-truth 계약과 충돌할 수 있다
- 대응: task 이벤트는 별도 contract 문서가 닫힌 뒤 후속 단계에서 연다

## 10. 이번 문서의 최종 판정

이 실행 계획은 `지금 구현된 group 중심 연동`을 버리는 계획이 아니라,
`그 위에 personal routing을 올려서 원래 목적이었던 즉시 인지`를 달성하기 위한 확장 계획이다.
