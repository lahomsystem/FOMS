# FOMS WAM 상세 주문뷰 마스터플랜

작성일: 2026-03-27
상태: 승인 / 최종감리완료
범위: `ChannelTalk -> WAM -> FOMS 특정 주문 상세 조회 경험 고도화`
관련 문서:
- `docs/plans/2026-03-26-foms-channeltalk-integration-focus-plan.md`
- `docs/plans/2026-03-27-foms-channeltalk-personal-routing-execution-plan.md`
- `docs/plans/2026-03-27-wam-design-system-spec.md`
- `docs/plans/2026-03-27-wam-file-skeleton-spec.md`
- `docs/plans/2026-03-27-wam-starter-spec.md`
- `docs/guides/2026-03-27-foms-channeltalk-current-implementation-guide.md`

## 1. 한 줄 결론

현재 WAM은 `주문 요약 카드 + 첨부 링크` 수준이다.
이번 계획의 목표는 이를 `모바일에서 읽기 좋은 FOMS 읽기 전용 상세 주문뷰`로 승격시키는 것이다.

핵심 방향은 아래 3가지다.

1. `기존 ERP 편집 화면 복붙 금지`
2. `WAM 전용 상세 read-model + 섹션형 모바일 UI`
3. `보안 게이트(manager binding / short-link / launch token) 먼저, 상세 확장 나중`

## 2. 근본 원인

현재 정보가 부실한 이유는 데이터가 없어서가 아니다.

- WAM controller는 [`apps/api/channel_wam.py`](apps/api/channel_wam.py) 에서 요약 함수 1개와 첨부 함수 1개만 호출한다.
- WAM summary는 [`services/channel_quick_actions.py`](services/channel_quick_actions.py) 에서 `주문번호, 고객명, 연락처, 주소, 제품명, 상태, 실측일, 시공일, 담당자` 정도만 projection 한다.
- WAM 템플릿은 [`templates/channel_wam_index.html`](templates/channel_wam_index.html) 한 파일에서 이 요약과 첨부를 평면 카드로만 보여준다.
- 반면 실제 FOMS 주문 데이터는 `Order flat columns + structured_data(parties/site/items/schedule/workflow/shipment) + attachments + OrderEvent`까지 훨씬 풍부하다.

즉, 문제는 `데이터 부족`이 아니라 `WAM read-model과 UI 구조가 지나치게 얇은 것`이다.

## 3. 이번 단계 목표와 비목표

### 3.1 목표

- ChannelTalk에서 주문 링크를 눌렀을 때 `FOMS 특정 주문의 거의 모든 핵심 정보`를 읽기 전용으로 확인할 수 있게 한다.
- 모바일에서도 `1초 내 주문 식별`, `3초 내 핵심 일정/주소/담당 확인`, `5초 내 첨부 탐색 시작`이 가능하게 한다.
- 현재 FOMS와 업무 연속성은 유지하되, WAM 표면은 `세계적 ERP 수준의 독립 디자인 토큰 시스템`으로 재설계한다.
- 이후 `개인 알림 -> WAM 상세 -> FOMS 편집` 흐름의 middle surface로 쓸 수 있게 만든다.

### 3.2 비목표

- WAM 안에서 주문 수정/승인/상태 변경
- 기존 [`templates/edit_order.html`](templates/edit_order.html) 전체를 iframe/복제 형태로 재사용
- raw `structured_data` 전체를 클라이언트에 노출
- launch token / short-link 보안 강화를 건너뛴 채 상세화부터 시작

## 4. 현재 상태 진단

### 4.1 현재 WAM이 보여주는 것

- 주문 번호
- 상태
- 고객명
- 연락처
- 주소
- 수주제품
- 담당 매니저
- 실측일
- 시공일
- 첨부파일 목록

### 4.2 현재 WAM이 못 보여주는 것

- 발주자/상담 메타
- 현장 세부 정보
- 실측 시간/시공 시간
- owner team / current quest / 긴급 여부
- 도면 담당 / 시공 담당 / 출고·시공 세부 메타
- 품목별 상세와 옵션
- 금액/예약금/결제 확인 상태
- 최근 변경 이력
- 첨부 카테고리/아이템별 구분/썸네일

### 4.3 바로 재사용 가능한 데이터 축

1. `Order flat columns`
- 고객명, 연락처, 주소, 제품, 메모, 상태, 실측/시공 일정, 결제금액, 배송 관련 메타

2. `structured_data`
- `parties`
- `site`
- `items`
- `schedule`
- `workflow`
- `shipment`
- `flags`

3. `display helper`
- [`services/erp_display.py`](services/erp_display.py)의 `apply_erp_display_fields()`, `_erp_get_stage()`, `_erp_alerts()`

4. `attachments`
- [`models.OrderAttachment`](models.py)
- 현재 WAM용 presigned URL 생성 로직

5. `recent changes`
- [`models.OrderEvent`](models.py) 와 관련 조회 경로

## 5. 선행 게이트

상세 주문뷰 확장은 아래 3개를 닫기 전까지 본격 착수하지 않는다.

### 5.1 보안 게이트

- short link만 가진 외부 사용자가 상세 주문 전체를 볼 수 있는 현재 bearer-link 리스크를 줄여야 한다.
- 목표:
  - manager binding 확인
  - entry/session ticket 분리
  - single-use는 `entry ticket`에만 강제
  - route-level flag gate 도입

#### 5.1A 상세뷰 v2 신뢰 체인 목표 계약

1. 검증된 ChannelTalk callback 또는 내부 안전 경로가 `channel_manager_id`를 서버에 전달한다.
2. 서버는 활성 `ChannelManagerLink`를 조회해 `mapped_foms_user_id`를 확인한다.
3. `/w/{token}`은 `short-link ticket`을 검증한 뒤, `WAM entry ticket`을 1회용으로 발급한다.
4. `/channel/wam` HTML 진입은 이 `WAM entry ticket`을 1회 소비하고, 서버는 `WAM session ticket`을 발급한다.
5. `/channel/wam`과 하위 `/api/*`는 이후 `WAM session ticket`만 신뢰한다.
6. `WAM session ticket`에는 `order_id`, `channel_manager_id`, `mapped_foms_user_id`, `allowed_sections`, `attachment_scope`, `issued_at`, `expires_at`, `nonce`가 담긴다.

고정값:
- short-link ticket TTL: `24시간`
- WAM entry ticket TTL: `30초`
- WAM entry ticket: `single-use 필수`
- WAM session ticket TTL: `5분`
- WAM session ticket: `multi-request 허용`
- binding 실패 시: `무조건 fail-closed`

#### 5.1B binding 실패 / token 실패 fail-closed 계약

| 경로 | 실패 조건 | 응답 |
|------|-----------|------|
| `/w/{token}` | 토큰 만료/변조 | `401` 에러 페이지 |
| `/w/{token}` | manager binding 없음 | `403` 에러 페이지 + relink 안내 |
| `/channel/wam` | entry/session ticket 없음 | `401` |
| `/channel/wam` | binding 불일치 | `403` |
| `/channel/wam/api/*` | session ticket 없음 | `401` |
| `/channel/wam/api/*` | flag off | `404` |
| `/channel/wam/api/*` | ticket 만료 | `401` |

#### 5.1C route-level gate / rollback 계약

- `CHANNEL_WAM_ENABLED=false`
  - `/w/{token}`와 `/channel/wam` 모두 신규 접근을 막는다.
  - 기존 링크는 `WAM이 일시 중지되었습니다` 안내 페이지로 보낸다.
- `CHANNEL_WAM_V2_ENABLED=false`
  - V2 상세뷰 대신 기존 V1 요약 WAM으로 fallback 한다.
- `CHANNEL_WAM_ATTACHMENTS_ENABLED=false`
  - 첨부 섹션 전체 숨김
- `CHANNEL_WAM_ATTACHMENTS_LAZY_ENABLED=false`
  - V2는 유지하되 첨부 lazy endpoint를 끄고 안전한 최소 경로로 되돌림
- rollback 기본 원칙:
  - `V2 -> V1`은 즉시 가능해야 한다.
  - `WAM 전체 off`는 마지막 수단이다.

#### 5.1D 노출 allowlist / redaction 계약

- 상세뷰에서 기본 허용:
  - 주문번호, 상태, 고객명, 연락처, 주소, 일정, 담당자, 품목, 첨부 메타
- Phase 3 이후 정책 승인 후 허용:
  - 결제 금액
  - 결제 확인 상태
  - 현장 메모
  - 내부 메모
  - 최근 변경 이력
- 기본 금지:
  - raw `structured_data`
  - storage key
  - presigned URL 원문
  - 내부 운영용 식별자/권한 디버그 값
- section별 allowlist는 `wam-data-contract.md`에 표로 고정한다.
- `현장` 섹션의 기본 범위는 `주소`, `상세주소`, `지도 열기 링크`까지만이다.
- `현장 메모`는 기본 현장 섹션에 포함하지 않고, `Phase 3 정책 승인` 전까지 `hidden` 상태를 유지한다.

### 5.2 데이터 게이트

- raw `structured_data` 전체를 넘기지 않고 `서버 projection`만 내리는 원칙을 먼저 고정해야 한다.
- 목표:
  - section별 view-model 계약 확정
  - lazy-load 대상 분리
  - live 상태 vs 메시지 시점 snapshot 안내 문구 확정

### 5.3 성능 게이트

- 상세화하면서 첨부와 히스토리가 커지므로 모바일 성능 예산을 먼저 고정한다.
- 목표:
  - 최초 렌더 3초 내
  - 핵심 헤더/요약 first paint 1.5초 내
  - 첨부 리스트 lazy-load
  - 대형 주문에서 DOM 폭증 방지

## 6. 바로 실행 가능한 마스터플랜

### 6.0 실행 승인 체계

| 역할 | 책임 |
|------|------|
| 제품 책임자 | 노출 범위, UX 우선순위, pilot 범위 승인 |
| 백엔드 책임자 | token/binding/read-model/API 계약 승인 |
| 프론트 책임자 | section UI, WAM token system, 모바일 UX 승인 |
| 운영 책임자 | rollout/rollback, telemetry, pilot gate 승인 |
| 보안 검토자 | short-link / launch token / attachment exposure 승인 |

### 6.0A go / no-go 기준

| 항목 | go 기준 | no-go 기준 |
|------|---------|------------|
| binding | pilot 대상 active mapping coverage 95% 이상 | 핵심 대상자 binding 누락 |
| token | short-link 24h, entry ticket 30s single-use, session ticket 5m, 만료 UX 확정 | ticket 계약 미확정 |
| route gate | `/w`, `/channel/wam`, `/api/*` fail-closed 규칙 확정 | flag off 시 동작 불명 |
| 성능 | 모바일 first paint 1.5초, 핵심 정보 3초 내 | 첨부/대형 주문에서 기준 초과 |
| 노출 범위 | section allowlist/redaction 표 확정 | 금액/메모/첨부 노출 범위 미확정 |
| rollback | V2 -> V1 fallback 가능 | V2 문제 시 전체 off만 가능한 구조 |

## Phase 0. Discovery + Gate Freeze

목표:
- 보안, 데이터, 성능 게이트를 문서와 코드 계약으로 먼저 고정

작업:
1. WAM 상세 범위를 `read-only only`로 재확인
2. short-link / launch-token current implementation을 상위 계획 계약에 맞게 매핑
3. `WamPageVM`, `WamSectionVM` 계약 초안 확정
4. 모바일 성능 예산 수치 고정
5. HTML shell route와 JSON API route 분리 계약 확정
6. attachment order-scope / token-scope 검증 계약 확정
7. rollout / rollback 기준 확정
8. 최소 telemetry(`wam_page_opened`, `wam_bootstrap_succeeded`, `wam_bootstrap_failed`, latency) 선행 삽입 위치 확정

산출물:
- `wam-security-gate.md`
- `wam-data-contract.md`
- `wam-performance-budget.md`
- `wam-rollout-gate.md`
- `wam-allowlist-redaction.md`
- `wam-route-split-contract.md`
- `wam-attachment-scope-contract.md`

진입 조건:
- 없음

종료 조건:
- 상세뷰를 넓혀도 되는 보안/성능 경계가 문서화됨
- `/w`, `/channel/wam`, `/api/*`의 fail-closed 응답 정책이 고정됨
- V2 -> V1 rollback semantics가 확정됨
- HTML과 JSON이 같은 예외 응답을 섞지 않도록 route split 원칙이 확정됨
- attachment open/download가 `order scope + token scope` 둘 다 통과해야만 동작하도록 계약이 확정됨

중단 조건:
- manager binding/short-link 정책이 미결정
- raw structured_data 노출 허용 여부가 미결정

## Phase 1. Read Model Expansion

목표:
- WAM 전용 상세 주문 read-model을 만든다.

작업:
1. summary 함수 대신 `order detail` 전용 projection 설계
2. `Order + structured_data + attachment metadata + OrderEvent summary` 조합
3. section별 payload 분리
4. formatter/placeholder/date label 통일

산출물:
- `WamOrderReadModel`
- `WamPageVM`
- `WamSectionVM`

진입 조건:
- Phase 0 종료

종료 조건:
- 템플릿이 raw ORM/structured_data에 직접 의존하지 않음

중단 조건:
- section 정의 없이 flat dict만 계속 키우는 방향으로 흐름

## Phase 2. WAM UI V2 Shell

목표:
- 한 장짜리 카드형 WAM을 상세 섹션형 레이아웃으로 교체

작업:
1. `상단 컨텍스트 헤더`
2. `핵심 일정/주소/연락처` 우선 배치
3. `아코디언/섹션 카드`
4. `읽기 전용 배지/안내`
5. 모바일 sticky CTA(전화/주소복사/지도/첨부)
6. 최소 telemetry(`wam_page_opened`, `wam_bootstrap_succeeded`, `wam_bootstrap_failed`, latency) 선행 삽입

산출물:
- 새 `templates/channel_wam/index.html`
- section partial 세트
- `static/css/channel_wam.css`
- 필요 시 `static/js/channel_wam.js`
- 최소 telemetry event spec + fail-open contract

진입 조건:
- Phase 1 read-model 안정화

종료 조건:
- 모바일 기준 핵심 주문 정보가 첫 화면에서 바로 식별됨
- V2가 문제일 때 flag로 즉시 V1로 되돌릴 수 있음

중단 조건:
- 기존 edit 화면 구조를 그대로 들고오려는 시도

## Phase 3. Attachments / Timeline / Advanced Telemetry

목표:
- 상세뷰를 실제 운영에 쓸 수 있는 수준으로 완성

작업:
1. 첨부 카테고리별 그룹화
2. lazy metadata + open/download resolve
3. 최근 변경 요약 또는 최근 이벤트 타임라인
4. advanced telemetry 수집

산출물:
- attachment grouping service
- timeline section
- advanced telemetry event spec

진입 조건:
- Phase 2 화면 구조 확정

종료 조건:
- 첨부 0/10/50건, 최근 이벤트 0/5/20건 시나리오가 모두 버팀

중단 조건:
- 모든 presigned URL을 첫 HTML에서 한 번에 내리는 구조 유지

## Phase 4. Pilot

목표:
- 실사용자 기준 확인 가능성과 성능 검증

작업:
1. 내부 파일럿 사용자 선정
2. 모바일 WebView 실측
3. 링크/첨부/만료 UX 확인
4. 피드백 반영

종료 조건:
- “정보가 부족하다” 피드백이 핵심 시나리오에서 사라짐
- 모바일에서 핵심 정보 접근 시간이 충분히 짧음

## 7. 거시 > 미시 수준의 아주 상세한 코드 계획

## 7.1 아키텍처 원칙

1. `controller thin`
- route는 토큰 검증, flag gate, context 생성만 담당

2. `service orchestrates`
- 조회/권한/section 조립/telemetry는 service 계층이 담당

3. `view-model first`
- template는 ORM이나 raw JSON을 직접 다루지 않음

4. `section rendering`
- summary/schedule/people/items/payment/attachments/timeline을 partial로 분리

5. `lazy heavy data`
- 첨부 전체, 히스토리 전체는 lazy load 가능하게 설계

## 7.2 파일 단위 변경 계획

### A. Route / API Layer

대상:
- `apps/api/channel_wam.py`

변경 방향:
- `channel_wam_bp`
  - `GET /channel/wam/`
  - HTML shell 전용
  - 실패 시 HTML `401/403/404` 에러 페이지 반환
- `channel_wam_api_bp`
  - `GET /channel/wam/api/bootstrap`
  - `GET /channel/wam/api/attachments`
  - `GET /channel/wam/api/attachments/<id>/open`
  - `GET /channel/wam/api/attachments/<id>/download`
  - optional `GET /channel/wam/api/timeline`
  - JSON/redirect 응답만 반환
  - 실패 시 JSON envelope 또는 redirect만 반환, HTML page 절대 반환 금지

DoD:
- route는 service 호출만 하고, payload shaping을 직접 하지 않는다.
- HTML shell과 JSON API는 blueprint 수준에서 분리되어, XHR이 HTML 에러 페이지를 받지 않는다.

### B. Application Service Layer

신규 권장:
- `services/channel_wam_service.py`

책임:
- request context 생성
- order read-model 조회
- section list 생성
- feature flag 반영
- telemetry trigger

핵심 함수:
- `build_wam_page(context) -> WamPageVM`
- `build_wam_bootstrap(page_vm) -> dict`
- `resolve_attachment_access(context, attachment_id, action) -> RedirectSpec`

DoD:
- controller는 이 서비스 하나만 호출해도 page 구성이 끝난다.
- `WamPageVM`이 canonical source of truth이고, bootstrap JSON은 `page_vm`에서 파생된다.

### C. View Model Layer

신규 권장:
- `services/channel_wam_view_models.py`

핵심 dataclass:
- `WamRequestContext`
- `WamHeaderVM`
- `WamSectionVM`
- `AttachmentItemVM`
- `AttachmentGroupVM`
- `WamPageVM`

DoD:
- 템플릿에는 `summary` 대신 `page_vm` 하나만 들어간다.

### D. Read Model / Projection Layer

신규 권장:
- `services/channel_wam_read_model.py`

책임:
- `Order`
- `structured_data`
- display helper
- attachment metadata
- recent events
를 section-friendly dict로 projection

DoD:
- raw ORM 객체를 template에 직접 넘기지 않는다.

### E. Section Builder Layer

신규 권장:
- `services/channel_wam_sections.py`

핵심 함수:
- `build_header_section()`
- `build_customer_section()`
- `build_site_section()`
- `build_schedule_section()`
- `build_people_section()`
- `build_items_section()`
- `build_payment_section()`
- `build_attachments_section()`
- `build_timeline_section()`

DoD:
- 각 section은 `ready | empty | hidden | error` 상태를 가진다.

### F. Attachments Layer

신규 권장:
- `services/channel_wam_attachments.py`

책임:
- attachment grouping
- thumbnail/open/download 링크 분리
- category/item_index 기반 정렬
- more_count / preview_count 계산
- `attachment.order_id == context.order_id` 검증
- session ticket의 `allowed_sections`, `attachment_scope` 검증
- `attachment_id`만으로는 접근 불가, 항상 `context scope + order scope` 동시 검증

DoD:
- 첫 렌더에서 모든 presigned URL을 발급하지 않는다.
- 다른 주문 첨부, 다른 토큰 컨텍스트, 만료 토큰으로는 open/download가 절대 성공하지 않는다.

### G. Feature Flag / Rollout Layer

신규 권장:
- `services/channel_feature_flags.py`

필요 토글:
- `CHANNEL_WAM_ENABLED`
- `CHANNEL_WAM_V2_ENABLED`
- `CHANNEL_WAM_ATTACHMENTS_ENABLED`
- `CHANNEL_WAM_ATTACHMENTS_LAZY_ENABLED`
- `CHANNEL_WAM_TIMELINE_ENABLED`
- `CHANNEL_WAM_TELEMETRY_ENABLED`

DoD:
- route-level gate와 section-level gate가 분리된다.

### H. Telemetry Layer

신규 권장:
- `services/channel_wam_telemetry.py`

이벤트:
- `wam_page_opened`
- `wam_bootstrap_succeeded`
- `wam_bootstrap_failed`
- `wam_section_rendered`
- `wam_attachment_clicked`
- `wam_timeline_opened`

DoD:
- page latency, section count, attachment count를 추적 가능
- 최소 telemetry(`wam_page_opened`, `wam_bootstrap_succeeded`, `wam_bootstrap_failed`, latency)는 Phase 1~2부터 활성화한다.
- telemetry 실패는 page render를 깨지 않는 `fail-open` 규칙을 따른다.

### I. Template Layer

신규 권장 구조:

```text
templates/channel_wam/index.html
templates/channel_wam/_header.html
templates/channel_wam/_summary_strip.html
templates/channel_wam/_customer.html
templates/channel_wam/_site.html
templates/channel_wam/_schedule.html
templates/channel_wam/_people.html
templates/channel_wam/_items.html
templates/channel_wam/_payment.html
templates/channel_wam/_attachments.html
templates/channel_wam/_timeline.html
templates/channel_wam/_empty_state.html
templates/channel_wam/_error_state.html
```

원칙:
- partial은 view-model만 소비
- 로직 최소화
- if/for는 section 상태 제어 정도만 허용

### J. CSS / JS Layer

신규 권장:
- `static/css/channel_wam.css`
- `static/js/channel_wam.js`

원칙:
- inline style 제거
- WAM 전용 토큰 사용, ERP는 시각 정합성 참고 기준으로만 사용
- JS는 `section expand/collapse`, `copy`, `attachment lazy load` 정도만 담당

### K. Tests

신규 권장:
- `tests/test_channel_wam_service.py`
- `tests/test_channel_wam_sections.py`
- `tests/test_channel_wam_attachments.py`
- `tests/test_channel_wam_routes.py`
- `tests/test_channel_wam_security.py`

필수 검증:
- token 유효/만료/변조
- route flag off
- 큰 structured_data projection
- attachment grouping
- empty section
- section state
- short-link redirect

## 7.3 섹션별 상세 정보 계획

### 헤더

- 주문번호
- 상태 배지
- 긴급 배지
- owner team
- 최근 변경 시각

### 고객 / 발주

- 고객명
- 연락처
- 발주자
- 상담/담당 매니저

### 현장

- 주소
- 상세주소
- 지도 열기 링크
- 현장 메모: `Phase 3 정책 승인 후` 별도 hidden section으로 승격

### 일정

- 접수일
- 실측일
- 실측시간
- 시공일
- 시공 관련 보조 일정
- AS 방문일

### 제품 / 옵션

- 품목 목록
- 품목별 제품명
- 규격
- 내부/색상/옵션/손잡이/기타

### 담당 / 출고 / 시공

- 담당 매니저
- 도면 담당
- 시공자
- owner team
- 출고/시공 관련 메타

### 금액 / 결제

- Phase 3 정책 승인 후에만 노출
- 총액
- 예약금
- 잔금
- 결제 확인 상태

### 첨부

- 카테고리별 그룹
- 썸네일 preview
- 전체 건수
- 보기 / 다운로드

### 최근 변경

- Phase 3 정책 승인 후에만 노출
- 최근 상태 변경
- 일정 변경
- 담당 변경
- 결제 확인 변경

## 8. 모던, 세련된 디자인 UI/UX 방향

## 8.1 외부 레퍼런스에서 가져올 원칙

이번 WAM 디자인은 아래 3축에서 원칙을 가져온다.

### SAP Fiori

레퍼런스:
- Object Page Floorplan: https://experience.sap.com/fiori-design-web/object-page/
- Fiori principle 참고: https://learning.sap.com/learning-journeys/introducing-sap-abap-platform-fundamentals/introducing-sap-fiori-1

가져올 것:
- object page형 `섹션 기반 정보 구조`
- `dynamic header`
- `anchor/tab navigation`은 모바일 기본값이 아니라, 섹션 수가 많고 본문 길이가 길 때만 선택적으로 켠다.
- `role-based, adaptive, simple` 원칙

### Microsoft Fluent 2 / Modern Model-Driven Apps

레퍼런스:
- Fluent 2 Typography: https://fluent2.microsoft.design/typography
- Modern refreshed look: https://learn.microsoft.com/tr-tr/power-platform/release-plan/2024wave2/power-apps/use-modern-refreshed-look-model-driven-apps

가져올 것:
- 명확한 `type ramp`
- updated styling의 `fonts / colors / borders / shadows`
- 밝은 surface 위에 적당한 depth
- 읽기 쉬운 정보 밀도

### Oracle Redwood

레퍼런스:
- Oracle Design: https://design.oracle.com/

가져올 것:
- enterprise지만 consumer-grade에 가까운 polish
- “one-size-fits-all”이 아닌 역할/상황별 정보 배치
- state-of-the-art but calm enterprise tone

## 8.2 디자인 원칙

1. `모바일 우선`
- WAM은 모바일 WebView 경험을 우선한다.

2. `첫 화면은 식별 + 일정 + 행동`
- 주문이 맞는지
- 언제 움직이는지
- 어디로/누가 가는지

3. `dense but breathable`
- ERP답게 정보량은 많되, 섹션과 위계를 강하게 준다.

4. `read-only clarity`
- 수정 가능한 듯한 UI는 금지
- “읽기 전용 / 수정은 FOMS” 문구를 상단에 노출

5. `attachment-heavy safe layout`
- 첨부가 많아도 헤더와 핵심 정보가 아래로 밀리지 않게 한다.

## 8.3 디자인 토큰 방향

토큰 source of truth:
- WAM V2의 시각 기준은 `WAM 전용 토큰 시스템`이다.
- 구현 source of truth는 `static/css/channel_wam.css` 또는 분리된 `channel_wam.tokens.css`다.
- [`static/css/erp-pro.css`](static/css/erp-pro.css)는 업무 제품군 간 시각 정합성을 확인하는 `참고 기준`이지, WAM 토큰의 상속 원본이 아니다.

### 8.3A 독립 토큰 원칙

- WAM 토큰은 ERP 토큰 alias가 아니라 `독립 semantic system`으로 정의한다.
- 구조는 `reference -> semantic -> component` 3계층으로 설계한다.
- ERP와 비슷해 보이는 값이 있더라도 그것은 `의도된 시각 정합성`이지 상속을 의미하지 않는다.
- 우선순위:
  - 1. 모바일 주문 상세 가독성
  - 2. 엔터프라이즈 정보 밀도
  - 3. 상태 인지 속도
  - 4. 읽기 전용 안전성

### 8.3B 토큰 거버넌스

1. reference token은 순수 값만 가진다.
2. semantic token은 UI 의미를 가진다.
3. component token은 주문뷰 전용 조립값만 가진다.
4. raw 값은 reference layer에만 넣는다.
5. semantic/component layer에서 hex, px를 직접 쓰지 않는다.
6. ERP와의 유사성은 `시각 정합성 리뷰`로만 관리한다.

### 8.3C 토큰 계층 구조

- `Reference tokens`
  - 색, radius, shadow, spacing, type scale의 순수 값
- `Semantic tokens`
  - page, surface, border, text, status, action 같은 의미 토큰
- `Component tokens`
  - header, summary card, section card, sticky bar, badge, attachment rail 같은 WAM 전용 토큰

예시:

```css
:root {
  --wam-ref-neutral-0: #ffffff;
  --wam-ref-neutral-50: #f7f9fc;
  --wam-ref-neutral-100: #eef2f7;
  --wam-ref-neutral-200: #e2e8f0;
  --wam-ref-neutral-300: #cbd5e1;
  --wam-ref-neutral-500: #64748b;
  --wam-ref-neutral-700: #334155;
  --wam-ref-neutral-900: #0f172a;

  --wam-ref-brand-500: #2563eb;
  --wam-ref-brand-600: #1d4ed8;
  --wam-ref-brand-700: #1e40af;

  --wam-sys-bg-page: var(--wam-ref-neutral-50);
  --wam-sys-surface-card: var(--wam-ref-neutral-0);
  --wam-sys-border-subtle: var(--wam-ref-neutral-200);
  --wam-sys-text-primary: var(--wam-ref-neutral-900);
  --wam-sys-text-secondary: var(--wam-ref-neutral-700);
  --wam-sys-action-primary: var(--wam-ref-brand-600);

  --wam-comp-header-bg: rgba(255, 255, 255, 0.88);
  --wam-comp-section-padding: 20px;
  --wam-comp-sticky-bar-height: 72px;
}
```

### 8.3D WAM 기본 토큰 정의

아래 표는 WAM의 기본 토큰 정의다. ERP와의 유사성은 의도된 시각 정합성이며, 값 상속을 의미하지 않는다.

### Reference Color Tokens

| 토큰 | 값 | 용도 |
|------|----|------|
| `--wam-ref-neutral-0` | `#FFFFFF` | 순수 white |
| `--wam-ref-neutral-50` | `#F7F9FC` | 페이지 캔버스 |
| `--wam-ref-neutral-100` | `#EEF2F7` | subtle panel |
| `--wam-ref-neutral-200` | `#E2E8F0` | subtle border |
| `--wam-ref-neutral-300` | `#CBD5E1` | strong border |
| `--wam-ref-neutral-500` | `#64748B` | tertiary text |
| `--wam-ref-neutral-700` | `#334155` | secondary text |
| `--wam-ref-neutral-900` | `#0F172A` | primary text |
| `--wam-ref-brand-500` | `#2563EB` | primary brand |
| `--wam-ref-brand-600` | `#1D4ED8` | pressed / focus-adjacent |
| `--wam-ref-brand-700` | `#1E40AF` | high-emphasis action |
| `--wam-ref-teal-600` | `#0F766E` | schedule/site accent |
| `--wam-ref-green-500` | `#16A34A` | success |
| `--wam-ref-amber-500` | `#D97706` | warning |
| `--wam-ref-red-500` | `#DC2626` | danger |
| `--wam-ref-sky-500` | `#0284C7` | info |
| `--wam-ref-status-info-bg` | `#EFF6FF` | info surface |
| `--wam-ref-status-success-bg` | `#DCFCE7` | success surface |
| `--wam-ref-status-warning-bg` | `#FEF3C7` | warning surface |
| `--wam-ref-status-danger-bg` | `#FEE2E2` | danger surface |
| `--wam-ref-status-info-fg` | `#1D4ED8` | info foreground |
| `--wam-ref-status-success-fg` | `#166534` | success foreground |
| `--wam-ref-status-warning-fg` | `#92400E` | warning foreground |
| `--wam-ref-status-danger-fg` | `#991B1B` | danger foreground |

### Semantic Surface / Text / Status Tokens

| 토큰 | 값 | 용도 |
|------|----|------|
| `--wam-sys-bg-page` | `var(--wam-ref-neutral-50)` | page bg |
| `--wam-sys-surface-card` | `var(--wam-ref-neutral-0)` | 기본 카드 |
| `--wam-sys-surface-subtle` | `var(--wam-ref-neutral-100)` | 섹션 헤더 / info strip |
| `--wam-sys-border-subtle` | `var(--wam-ref-neutral-200)` | 기본 보더 |
| `--wam-sys-border-strong` | `var(--wam-ref-neutral-300)` | 강조 구분선 |
| `--wam-sys-text-primary` | `var(--wam-ref-neutral-900)` | 제목 / 핵심 값 |
| `--wam-sys-text-secondary` | `var(--wam-ref-neutral-700)` | 기본 본문 |
| `--wam-sys-text-tertiary` | `var(--wam-ref-neutral-500)` | 메타 / 보조 |
| `--wam-sys-action-primary` | `var(--wam-ref-brand-600)` | primary action |
| `--wam-sys-action-primary-hover` | `var(--wam-ref-brand-700)` | hover / active |
| `--wam-sys-status-info-bg` | `var(--wam-ref-status-info-bg)` | info badge bg |
| `--wam-sys-status-success-bg` | `var(--wam-ref-status-success-bg)` | success badge bg |
| `--wam-sys-status-warning-bg` | `var(--wam-ref-status-warning-bg)` | warning badge bg |
| `--wam-sys-status-danger-bg` | `var(--wam-ref-status-danger-bg)` | danger badge bg |
| `--wam-sys-status-info-fg` | `var(--wam-ref-status-info-fg)` | info badge text |
| `--wam-sys-status-success-fg` | `var(--wam-ref-status-success-fg)` | success badge text |
| `--wam-sys-status-warning-fg` | `var(--wam-ref-status-warning-fg)` | warning badge text |
| `--wam-sys-status-danger-fg` | `var(--wam-ref-status-danger-fg)` | danger badge text |

### Typography Tokens

Fluent 2의 type ramp를 참고하되, SAP/Oracle 계열처럼 차분한 `humanist enterprise sans` 톤으로 운용한다.

| 토큰 | 값 | 용도 |
|------|----|------|
| `--wam-ref-font-sans` | `"Segoe UI Variable Text", "Segoe UI", "Noto Sans KR", system-ui, sans-serif` | 기본 서체 |
| `--wam-sys-font-family` | `var(--wam-ref-font-sans)` | semantic font |
| `--wam-ref-text-xs` | `12px / 16px` | 메타 |
| `--wam-ref-text-sm` | `13px / 18px` | 보조 본문 |
| `--wam-ref-text-md` | `14px / 20px` | 기본 본문 |
| `--wam-ref-text-lg` | `16px / 22px` | subsection title |
| `--wam-ref-text-xl` | `20px / 28px` | main title |
| `--wam-ref-text-2xl` | `24px / 32px` | hero number/title |

폰트 운영 원칙:
- 기본은 `WAM 독립 서체 스택`을 사용한다.
- ERP와의 정합성은 alias가 아니라 시각 리뷰로 맞춘다.
- 전용 서체 변경은 `프론트 책임자 + 제품 책임자` 공동 승인 후 적용한다.

### Radius / Shadow / Spacing / Motion Tokens

| 토큰 | 값 | 용도 |
|------|----|------|
| `--wam-ref-radius-sm` | `10px` | badge / chip |
| `--wam-ref-radius-md` | `14px` | input / compact card |
| `--wam-ref-radius-lg` | `18px` | section card |
| `--wam-ref-radius-xl` | `24px` | hero card |
| `--wam-ref-shadow-sm` | `0 1px 2px rgba(15,23,42,0.06)` | 미세 depth |
| `--wam-ref-shadow-md` | `0 8px 24px rgba(15,23,42,0.08)` | 기본 카드 |
| `--wam-ref-shadow-lg` | `0 20px 48px rgba(15,23,42,0.12)` | overlay / panel |
| `--wam-ref-overlay-glass` | `rgba(255,255,255,0.88)` | sticky glass surface |
| `--wam-ref-backdrop-blur` | `blur(14px)` | sticky header blur |
| `--wam-ref-space-1` | `4px` | spacing |
| `--wam-ref-space-2` | `8px` | spacing |
| `--wam-ref-space-3` | `12px` | spacing |
| `--wam-ref-space-4` | `16px` | spacing |
| `--wam-ref-space-5` | `20px` | spacing |
| `--wam-ref-space-6` | `24px` | spacing |
| `--wam-ref-space-8` | `32px` | spacing |
| `--wam-ref-size-attachment-preview` | `72px` | attachment preview |
| `--wam-ref-size-sticky-bar` | `72px` | sticky bar height |
| `--wam-ref-size-content-max` | `960px` | content max width |
| `--wam-ref-radius-pill` | `999px` | pill radius |
| `--wam-ref-transition-fast` | `140ms ease-out` | hover |
| `--wam-ref-transition-base` | `220ms ease` | accordion |
| `--wam-ref-transition-slow` | `320ms ease` | section reveal |
| `--wam-ref-bp-sm` | `480px` | small mobile |
| `--wam-ref-bp-md` | `768px` | tablet / wide mobile |
| `--wam-ref-bp-lg` | `1024px` | desktop fallback |

### Component Tokens

| 토큰 | 값 | 용도 |
|------|----|------|
| `--wam-comp-header-bg` | `var(--wam-ref-overlay-glass)` | compact context header |
| `--wam-comp-header-backdrop` | `var(--wam-ref-backdrop-blur)` | sticky header glass |
| `--wam-comp-card-padding` | `var(--wam-ref-space-5)` | section card padding |
| `--wam-comp-card-gap` | `var(--wam-ref-space-4)` | card gap |
| `--wam-comp-summary-grid-gap` | `var(--wam-ref-space-3)` | summary strip gap |
| `--wam-comp-badge-radius` | `var(--wam-ref-radius-pill)` | pill badge |
| `--wam-comp-sticky-bar-height` | `var(--wam-ref-size-sticky-bar)` | bottom action bar |
| `--wam-comp-attachment-preview-size` | `var(--wam-ref-size-attachment-preview)` | attachment rail thumb |
| `--wam-comp-section-max-width` | `var(--wam-ref-size-content-max)` | content container |

### 8.3E ERP 시각 정합성 참조표

ERP는 source of truth가 아니라 `시각 정합성 확인용 비교 기준`으로만 사용한다.

| 비교 축 | WAM 기준 | ERP와의 관계 |
|---------|----------|---------------|
| 정보 구조 | object-page lite | 주문 업무 흐름만 정합 |
| 색감 | neutral + brand blue + calm status | 제품군 간 너무 튀지만 않게 조정 |
| 타이포 | Segoe UI Variable 계열 중심 | 필요 시 한글 fallback만 공유 |
| depth | subtle layered cards | ERP보다 조금 더 polished 허용 |
| spacing | mobile-first 8pt 계열 | ERP보다 여유 있게 허용 |

## 8.4 UI 레이아웃 제안

### 상단 고정 영역

- 주문번호
- 상태 배지
- 긴급/owner team 배지
- 고객명
- 읽기 전용 안내
- 모바일 기본 persistent chrome은 `상단 컨텍스트 1개 + 하단 액션바 1개`까지만 허용하고, anchor/tab nav를 동시에 기본 활성화하지 않는다.

### 본문 1순위 카드

- 실측일
- 시공일
- 주소
- 연락처

### 본문 2순위 카드

- 담당/도면/시공
- 발주자
- 제품 요약

### 접힘 섹션

- 품목 상세
- 결제 상세
- 첨부 전체
- 최근 변경
- 모바일 기본 규칙:
  - 한 번에 하나의 heavy section만 확장
  - 첨부는 미리보기 건수와 전체 건수를 함께 표시
  - 접힘/펼침 후 현재 스크롤 위치를 최대한 유지

### 하단 sticky action bar

읽기 전용 범위에서만 허용:
- 전화
- 주소 복사
- 지도 열기
- 첨부 보기
- FOMS에서 열기

노출 조건:
- `FOMS에서 열기`는 `binding 확인 + 내부 사용자 + FOMS 접근 가능`일 때만 1차 CTA로 노출
- 그 외에는 overflow 또는 숨김 처리

## 9. 실행 티켓 초안

### WAM-00 보안/게이트 문서화
- manager binding
- short-link / entry / session ticket TTL
- entry ticket single-use 구현 계약
- route-level gate
- HTML/API route split
- attachment order-scope + token-scope

### WAM-01 read-model 설계
- WamOrderReadModel
- WamPageVM
- section contract
- bootstrap JSON 파생 규칙
- 최소 telemetry 삽입 지점

### WAM-02 section builder 구현 계획
- summary
- schedule
- people
- items
- payment
- attachments
- timeline

### WAM-03 template / CSS / JS 재설계
- shell
- partial
- css tokens
- accordion / sticky action

### WAM-04 첨부 lazy-load 계획
- metadata
- open/download
- grouping
- thumbnail

### WAM-05 telemetry / pilot
- telemetry events
- mobile performance
- rollout / rollback
- Phase 1~2 선행 telemetry 검증

## 10. 검증 계획

### 10.0 dual-run / cutover 계획

- 기본 전략:
  - `V1 summary WAM` 유지
  - `V2 detailed WAM`을 flag로 병행
- cutover 순서:
  1. 내부 사용자에만 V2 오픈
  2. 파일럿 그룹 확대
  3. V2 안정화 후 default 전환
- rollback 순서:
  1. `CHANNEL_WAM_V2_ENABLED=false`
  2. 필요 시 attachment/timeline만 개별 off
  3. 최후에만 `CHANNEL_WAM_ENABLED=false`

### 10.1 성능 측정 환경

- iPhone Safari WebView
- Android Chrome WebView
- 4G 수준 네트워크
- 첨부 0/10/50건 주문
- structured_data 크기 small / medium / large

측정 지표:
- first paint `<= 1.5초`
- 주문 식별 가능 시점 `<= 1초`
- 핵심 정보 확인 가능 시점 `<= 3초`
- 첨부 section 첫 open latency `<= 5초`
- 전체 DOM node count

### 10.2 Unit

- section builder
- formatter
- attachment grouping
- empty state

### 10.3 Integration

- `/w/{token}` -> `/channel/wam`
- token 만료/변조
- attachment open/download
- flag off

### 10.4 Manual / UI

- iPhone Safari WebView
- Android Chrome WebView
- 첨부 0/10/50건
- 긴 주소/긴 제품명

### 10.5 Security

- 링크 공유
- launch token 재사용
- short-link 만료
- route gate

## 11. 최종 판정

이 계획은 `바로 실행 가능한 마스터플랜`으로 사용 가능하다.

단, 실제 구현 착수 순서는 반드시 아래를 따른다.

1. 보안 게이트
2. read-model 계약
3. WAM UI V2
4. attachments/timeline/telemetry
5. 파일럿

즉, `상세화부터 먼저`가 아니라 `보안/계약부터 먼저`가 정답이다.
