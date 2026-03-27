# FOMS <> ChannelTalk 현재 구현 비교와 쉬운 사용 설명서
작성일: 2026-03-27
기준 계획서: `docs/plans/2026-03-26-foms-channeltalk-integration-focus-plan.md`
문서 목적: 계획서와 실제 구현을 비교하고, 지금 당장 무엇을 사용할 수 있는지 아주 쉽게 설명한다.

독자 기준:
- `3~4장`은 일반 사용자도 읽을 수 있는 사용 설명이다.
- `5~7장`은 운영자/관리자 확인용 설명이다.

## 1. 가장 먼저 이해할 것

- FOMS는 `주문 원본 시스템`이다.
- ChannelTalk는 `알림을 받고, 빨리 확인하고, 링크로 들어가는 창구`다.
- 현재 구현은 `수동 푸시`, `일부 자동 푸시`, `읽기 전용 WAM`, `읽기 전용 Command`, `기본 Webhook inbound`까지 들어와 있다.
- 아직 없는 것은 `ChannelTalk 안에서 직접 쓰기`, `정교한 관리자-사용자 매핑 UI`, `자동 Command 등록`, `완성형 그룹 라우팅`이다.

쉽게 한 줄로 말하면:

`지금은 ChannelTalk를 메신저/알림창으로 쓰고, 실제 수정은 대부분 FOMS에서 한다.`

## 2. 계획서 vs 현재 구현

| 영역 | 계획서 목표 | 현재 구현 상태 | 지금 사용 가능? | 비고 |
|---|---|---|---|---|
| 수동 푸시 | ERP 화면에서 ChannelTalk로 수동 전송 | 구현됨 | 예 | ERP Beta 화면의 `푸쉬` 버튼으로 사용 가능 |
| 자동 푸시 | 주문 변경 시 outbox + worker로 자동 전송 | 구현됨 | 예 | 다만 모든 변경이 아니라 일부 경로만 연결됨 |
| 변경 내용 표시 | 상태/담당자/일정 등 무엇이 바뀌었는지 보여주기 | 구현됨 | 예 | change line 방식으로 메시지에 표시 |
| 주문 상세 링크 | ChannelTalk에서 주문 상세 열기 | 구현됨 | 예 | 새 메시지는 짧은 `/w/<token>` 링크 사용 |
| WAM | ChannelTalk에서 읽기 전용 상세 보기 | 구현됨 | 예 | 주문 요약 + 첨부 보기 가능 |
| Health / Readiness | 운영 상태 점검 | 구현됨 | 예 | 관리자 페이지 Pilot 지표에서 사용 |
| Delivery Log 조회 | 최근 전송 상태 조회 | 부분 구현 | 제한적 | API는 있으나 관리자 화면에 완전 연결되진 않음 |
| Command | `/foms 주문/일정/담당` 읽기 | 구현됨 | 조건부 예 | ChannelTalk 앱 쪽 연결과 manager mapping이 필요 |
| Webhook inbound | ChannelTalk 메시지를 받아 파싱 | 구현됨 | 조건부 예 | 환경변수, 서명, 허용 그룹 설정 필요 |
| inbound 생성 | 메시지에서 ERP 데이터 생성 | 부분 구현 | 조건부 예 | 현재는 새 ERP Beta 주문 생성 중심, Task 생성은 없음 |
| Channel manager <> FOMS user 매핑 | 권한 있는 사용자만 읽기/쓰기 | 부분 구현 | 아니오에 가까움 | 모델/서비스는 있으나 운영 UI와 완성된 흐름이 없음 |
| WAM write action | WAM 안에서 수정/처리 | 미구현 | 아니오 | 현재 WAM은 read-only |
| Command 자동 등록 | 앱 시작 시 Command bootstrap | 미구현 | 아니오 | handler만 있고 자동 등록 코드는 없음 |
| 그룹 라우팅 | 팀/상태별 그룹 분기 | 부분 구현 | 제한적 | 현재 대부분 `CHANNEL_GROUP_MEASUREMENT`로 감 |
| 운영 지표 정합성 | backlog/parse/success 정확 집계 | 부분 구현 | 제한적 | 특히 inbound 파싱 성공률은 보수적으로 봐야 함 |

## 3. 지금 실제로 생긴 기능

### 3.1 ERP 내부 사용자가 바로 쓸 수 있는 기능

1. ERP Beta 화면에서 ChannelTalk 수동 푸시
- 위치: 주문 상세의 ERP Beta 탭
- 버튼: `푸쉬`
- 동작: 변환 텍스트를 만들고, 현재 주문 첨부를 모아서 ChannelTalk로 바로 보낸다.

2. 주문 변경 시 자동 푸시
- 모든 저장이 아니라, 현재 연결된 일부 저장 경로에서만 자동으로 ChannelTalk에 메시지가 간다.
- 현재 연결된 주요 변경:
  - 구조화 주문 저장
  - 상태 변경
  - 담당자 변경
  - 담당 팀 변경
  - 실측일/시공일 변경
  - 실측 담당/주소/연락처 변경
  - 출고/시공 정보 변경
  - 결제 확인 변경

3. 관리자 페이지에서 ChannelTalk 상태 보기
- 위치: 관리자 페이지
- 볼 수 있는 것:
  - Push 성공률
  - 중복 비율
  - Inbound 파싱 성공률
  - 대기 백로그
  - readiness fail 경고

### 3.2 ChannelTalk 안에서 바로 쓸 수 있는 기능

1. 주문 상세 보기 링크
- 새 메시지에는 긴 `launch_token` URL 대신 짧은 `/w/<token>` 링크가 들어간다.
- 클릭하면 내부에서 진짜 WAM 토큰으로 바꿔서 주문 상세를 연다.
- 이 링크는 로그인 세션보다 `링크 자체`로 열리는 read-only 링크에 가깝다.

2. WAM 읽기 전용 화면
- 볼 수 있는 것:
  - 주문 번호
  - 고객명
  - 연락처
  - 주소
  - 제품명
  - 담당 매니저
  - 실측일
  - 시공일
  - 첨부파일
- 할 수 없는 것:
  - 수정
  - 승인
  - 상태 변경

3. `/foms` 읽기 전용 Command
- 예시:
  - `/foms 주문 2762`
  - `/foms 일정 2762`
  - `/foms 담당 2762`
- 결과:
  - 텍스트 요약을 ChannelTalk 안에서 바로 받는다.
- 권한 모델 차이:
  - Command는 manager mapping 같은 계정 연동 준비가 필요하다.
  - WAM은 현재 링크 기반 read-only 접근이다.

### 3.3 운영자가 조건부로 쓸 수 있는 기능

1. Webhook inbound 수신
- ChannelTalk에서 들어온 메시지를 서버가 받는다.
- 서명을 검증하고, 중복 여부를 확인하고, worker로 넘긴다.

2. Inbound 주문 생성
- 메시지 내용이 정해진 형식이면 ERP Beta 주문을 자동 생성할 수 있다.
- 현재 읽는 항목:
  - 고객명
  - 연락처
  - 주소
  - 수주제품

## 4. 아주 쉽게 보는 사용법

### 4.1 수동 푸시 사용법

1. FOMS에서 주문 상세를 연다.
2. `ERP Beta` 탭으로 간다.
3. 필요하면 `변환` 버튼으로 텍스트를 확인한다.
4. `푸쉬` 버튼을 누른다.
5. ChannelTalk에 주문 내용과 첨부가 전송된다.

참고:
- 수동 푸시는 주문 첨부를 모아 보내는 경향이 강하다.
- 자동 푸시와 첨부 규칙이 완전히 같지 않다.

이 기능은 이런 상황에 좋다:

- 오늘 바로 공유해야 하는 주문
- 자동 푸시가 아닌 특별 공지
- 첨부까지 한 번에 보내고 싶은 경우

### 4.2 자동 푸시 사용법

1. FOMS에서 자동 푸시가 연결된 주문 정보를 수정한다.
2. 저장이 성공하면 시스템이 `배달 로그`를 만든다.
3. worker가 그 로그를 읽는다.
4. ChannelTalk에 메시지를 보낸다.
5. 메시지에는 `무엇이 바뀌었는지`가 bullet로 찍힌다.

예시:

- 상태: 실측 -> 도면
- 담당자: 이시영 -> 망고
- 실측일: 2026-03-28 -> 2026-03-30

### 4.3 주문 상세 보기 사용법

1. ChannelTalk 메시지에서 `주문 상세 보기` 링크를 누른다.
2. 짧은 링크 `/w/<token>`로 들어간다.
3. 서버가 내부에서 WAM launch token을 다시 발급한다.
4. 읽기 전용 상세 화면이 열린다.

중요:

- 이미 예전에 보낸 긴 링크 메시지는 그대로 남아 있다.
- 새로 보내는 메시지부터 짧은 링크로 보인다.
- 짧은 링크는 기본 30일, WAM 화면과 첨부 링크는 보통 1시간 기준으로 다시 발급이 필요할 수 있다.
- 이 링크는 bearer-link 성격이 있으므로 외부 공유에 주의해야 한다.

### 4.4 `/foms` Command 사용법

1. ChannelTalk에서 `/foms 주문 2762` 같은 형식으로 입력한다.
2. 서버가 서명을 검증한다.
3. 주문 데이터를 읽는다.
4. 텍스트 요약을 답장한다.

현재는 읽기만 된다.
- manager mapping이 없으면 `/foms`는 권한 부족 또는 조회 불가로 끝날 수 있다.
- 반대로 `/w` short link는 유효 token이면 read-only WAM이 열릴 수 있다.

### 4.5 운영자용 Webhook inbound 확인법

1. ChannelTalk 메시지가 webhook으로 들어온다.
2. 서버가 `X-Signature`를 검증한다.
3. 중복 메시지인지 확인한다.
4. worker가 내용을 파싱한다.
5. 조건이 맞으면 새 ERP Beta 주문을 생성한다.

현재 파싱이 잘 되려면 메시지가 어느 정도 형식을 따라야 한다.

예시 형식:

```text
고객명: 홍길동
연락처: 010-1234-5678
주소: 서울시 강남구 테헤란로 123
수주제품: 주방 외 5조
```

## 5. 기능이 실제로 어떻게 작동해야 하는가

### 5.1 수동 푸시 흐름

1. 사용자가 FOMS에서 `푸쉬` 버튼을 누른다.
2. 브라우저가 `/api/channel/push-manual`을 호출한다.
3. 서버가 주문 텍스트와 첨부를 모은다.
4. ChannelTalk Native Function으로 바로 전송한다.
5. 성공하면 structured_data에 수동 푸시 이력을 남긴다.

첨부 규칙:
- 수동 푸시는 주문 첨부를 모아 보내는 수동 공유용 흐름이다.
- 자동 푸시는 이벤트 정책에 따라 일부 이미지/링크만 붙을 수 있다.

### 5.2 자동 푸시 흐름

1. 주문 저장 API가 변경을 감지한다.
2. `ChannelDeliveryLog`에 pending row를 만든다.
3. `channel_source_seq`를 증가시킨다.
4. commit 후 RQ enqueue를 시도한다.
5. worker가 배달 로그를 읽는다.
6. 메시지 본문을 만든다.
7. ChannelTalk에 보낸다.
8. 성공이면 `sent`, 실패면 `api_failed` 또는 queue 관련 상태로 남긴다.

핵심 포인트:

- FOMS가 원본이다.
- ChannelTalk는 전달 창구다.
- 먼저 DB에 기록하고, 그 다음 queue로 보내는 outbox 패턴이다.

### 5.3 짧은 링크 + WAM 흐름

1. 메시지 생성 시 `/w/<token>` 짧은 링크를 만든다.
2. 사용자가 그 링크를 누른다.
3. 서버가 짧은 링크 토큰을 검증한다.
4. 서버가 새 `launch_token`을 발급한다.
5. `/channel/wam/?launch_token=...`로 리다이렉트한다.
6. WAM이 read-only 화면을 렌더링한다.

이렇게 한 이유:

- 채팅창에는 링크를 짧게 보이게 하고
- 실제 WAM 인증은 기존 보안 토큰 구조를 그대로 유지하기 위해서다.

### 5.4 Command 흐름

1. ChannelTalk가 Function Endpoint를 호출한다.
2. 서버가 서명을 검증한다.
3. `/foms` 명령을 파싱한다.
4. 필요하면 manager mapping으로 읽기 권한을 확인한다.
5. 텍스트 응답을 반환한다.

### 5.5 Webhook inbound 흐름

1. ChannelTalk webhook이 들어온다.
2. 서버가 서명을 검증한다.
3. dedupe_key, creation_key, payload_hash를 만든다.
4. raw payload를 `ChannelInboundEventLog`에 저장한다.
5. queue로 넘긴다.
6. worker가 텍스트를 파싱한다.
7. create enabled이면 새 주문을 만든다.

## 6. 꼭 알아야 할 주의사항

1. 새 메시지부터 짧은 링크다
- 기존에 이미 발송된 메시지는 긴 링크 그대로다.

2. WAM은 읽기 전용이다
- 보기만 된다.
- 수정 버튼, 상태 변경 버튼, 승인 버튼은 아직 없다.

3. 자동 푸시는 모든 변경에 다 붙어 있지 않다
- 현재 연결된 경로만 자동 푸시된다.
- 즉, “어떤 수정은 바로 알림이 오고 어떤 수정은 아직 안 올 수 있다.”

3-1. WAM 링크는 read-only 공유 링크에 가깝다
- 현재 WAM은 로그인된 FOMS 사용자 화면과 같은 권한 모델이 아니다.
- short link는 기본 30일, launch token과 첨부 링크는 대체로 1시간 기준으로 본다.
- 외부 공유에 주의해야 한다.

4. 그룹 라우팅은 아직 단순하다
- 현재 정책 함수는 대부분의 이벤트를 `CHANNEL_GROUP_MEASUREMENT`로 보낸다.
- 계획서처럼 팀별/상태별 정교한 분기는 아직 덜 완성됐다.

5. Command 권한은 운영 준비가 더 필요하다
- backend는 있지만 manager mapping UI가 없다.
- ChannelTalk 앱 쪽 Command 연결도 자동 등록이 아니다.
- Command는 계정 연동 기반이고, WAM은 현재 링크 기반 read-only라는 점이 다르다.

6. inbound는 완성형 접수봇이 아니다
- 현재는 정해진 텍스트 형식을 읽어 새 ERP Beta 주문을 만드는 최소 구현이다.
- Task 생성, 실패 안내 Quick Reply, 복잡한 대화 흐름은 아직 없다.

7. 관리자 지표는 참고용으로 봐야 한다
- backlog, readiness는 유용하다.
- 하지만 inbound 파싱 성공률은 현재 상태 코드와 100% 완전히 맞물리지 않아 보수적으로 해석해야 한다.
- 즉 `parse_success_rate`는 운영 참고 지표이지, 단독 자동 판정 수치로 과신하면 안 된다.

8. worker와 환경변수가 살아 있어야 한다
- 자동 푸시는 web만 켜져 있다고 되는 게 아니다.
- Redis, worker, ChannelTalk 환경변수까지 맞아야 실제 발송된다.

## 7. 운영 체크리스트

### 7.1 수동 푸시가 안 될 때

- `CHANNEL_APP_SECRET`, `CHANNEL_ID`, `CHANNEL_GROUP_MEASUREMENT`, `FOMS_BASE_URL` 확인
- web 서비스에 값이 있는지 확인
- 첨부 presigned URL이 생성되는지 확인

### 7.2 자동 푸시가 안 될 때

- `REDIS_URL` 확인
- worker 실행 여부 확인
- worker에도 ChannelTalk 환경변수가 들어갔는지 확인
- `/api/channel/health`에서 `readiness`, `worker_count`, `backlog_count` 확인

### 7.3 Command / Webhook이 안 될 때

- `CHANNEL_SIGNING_KEY` 확인
- `CHANNEL_REPLAY_WINDOW_SECONDS` 확인
- webhook/function endpoint가 앱 쪽에 연결됐는지 확인

### 7.4 inbound 생성이 안 될 때

- `CHANNEL_INBOUND_CREATE_ENABLED=true` 확인
- `CHANNEL_ALLOWED_GROUP_IDS` 설정 확인
- 메시지가 파싱 가능한 형식인지 확인

## 8. 지금 시점의 현실적인 정리

현재 FOMS <> ChannelTalk 연동은 `알림 중심 1차 운영` 단계로 보면 된다.

- 잘 되는 것:
  - 수동 푸시
  - 일부 자동 푸시
  - 변경 내역이 보이는 메시지
  - 짧은 주문 상세 링크
  - 읽기 전용 WAM
  - 기본 Command
  - 기본 inbound

- 아직 더 다듬어야 하는 것:
  - 쓰기 액션
  - manager mapping 운영 UI
  - 정교한 그룹 라우팅
  - resend/requeue 운영 화면
  - inbound 고도화
  - 운영 지표 정합성

즉, 지금은 `실무에서 써볼 수 있는 단계`까지는 왔고, `완성형 협업 플랫폼 단계`는 아직 아니다.
