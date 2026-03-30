# FOMS WAM 파일 초안 설계서
작성일: 2026-03-27
상태: 승인 / 구현직전초안
범위: `WAM 상세 주문뷰`의 CSS, 템플릿, JS, 서버-클라이언트 계약을 실제 파일 단위로 분해한 설계서
연관 문서:
- `docs/plans/2026-03-27-wam-detailed-order-view-master-plan.md`
- `docs/plans/2026-03-27-wam-design-system-spec.md`
- `docs/plans/2026-03-27-wam-starter-spec.md`

## 1. 한 줄 결론

이 문서는 `WAM 상세 주문뷰를 실제 구현하기 직전`, 어떤 파일을 만들고 각 파일이 무엇을 책임져야 하는지를 고정한다.

핵심 원칙은 4개다.

1. 서버 source of truth는 `page_vm` 하나다.
2. 템플릿은 표시만 하고 데이터 가공을 하지 않는다.
3. JS는 보조만 담당하고 business rule을 넣지 않는다.
4. CSS는 `--wam-*` 토큰과 `.wam-*` 클래스만 사용한다.

## 2. 구현 기본 원칙

### 2.1 서버

- 서버는 `page_vm`과 `bootstrap_payload`만 만든다.
- ORM 객체와 raw `structured_data`는 템플릿으로 직접 넘기지 않는다.
- HTML shell과 JSON API는 분리된 경로/응답 정책을 유지한다.

### 2.2 템플릿

- 템플릿은 `page_vm` 또는 명시된 section view-model만 소비한다.
- include 순서는 서버가 정한 section 순서를 그대로 따른다.
- 템플릿 안에서 비즈니스 로직을 다시 판단하지 않는다.

### 2.3 JS

- JS는 `lazy load`, `copy`, `expand/collapse`, `telemetry`만 담당한다.
- section의 내용 shape를 JS에서 수정하지 않는다.
- telemetry 실패가 렌더 실패로 이어지면 안 된다.

### 2.4 CSS

- `erp-pro.css`는 참고 배경일 뿐이다.
- WAM 마크업은 `.wam-*`와 `--wam-*`만 사용한다.
- inline style, raw hex, raw px는 WAM CSS 계층 밖에서 쓰지 않는다.

## 3. 권장 파일 구조

```text
templates/channel_wam/
  layout.html
  index.html
  _macros.html
  sections/
    _header.html
    _summary_strip.html
    _customer.html
    _site.html
    _schedule.html
    _people.html
    _items.html
    _attachments.html
    _timeline.html
    _sticky_action_bar.html
  states/
    _empty.html
    _error.html

static/css/wam/
  tokens.css
  base.css
  layout.css
  components.css
  order-detail.css

static/js/wam/
  core.js
  telemetry.js
  attachments.js
  order-detail.js
```

## 4. CSS 파일별 책임

### 4.1 `static/css/wam/tokens.css`

책임:

- `--wam-ref-*`
- `--wam-sys-*`
- `--wam-comp-*`
- z-index, motion, breakpoints, spacing, fixed size, status tone 정의

포함 가능:

- 토큰 정의만

금지:

- 클래스 selector
- element selector
- layout 규칙
- component 스타일

DoD:

- semantic/component layer direct raw value 없음
- `--erp-*` 직접 참조 없음

### 4.2 `static/css/wam/base.css`

책임:

- body / html 기본값
- typography default
- links / buttons / lists / images 기본 reset
- focus-visible
- reduced-motion
- word-break, line-height, touch target 기본값

포함 가능:

- 앱 전역에 가까운 WAM 기본 스타일

금지:

- 특정 card, badge, attachment rail 스타일
- page-specific spacing hack

### 4.3 `static/css/wam/layout.css`

책임:

- `.wam-page`
- `.wam-shell`
- `.wam-main`
- `.wam-section-stack`
- sticky header / sticky action bar 외곽 레이아웃
- mobile-first grid와 breakpoint 전환

포함 가능:

- 페이지 골격
- 상단/하단 persistent chrome 위치 규칙

금지:

- 특정 section 내용 스타일
- 특정 badge 색상 스타일

### 4.4 `static/css/wam/components.css`

책임:

- `.wam-card`
- `.wam-badge`
- `.wam-kv-row`
- `.wam-section`
- `.wam-section-header`
- `.wam-chip`
- `.wam-empty-state`
- `.wam-error-state`
- generic action button

포함 가능:

- 재사용 가능한 UI primitives

금지:

- 주문 상세 화면에만 있는 예외 스타일
- timeline/attachment 전용 레이아웃 세부값

### 4.5 `static/css/wam/order-detail.css`

책임:

- WAM 주문 상세 전용 예외 스타일
- compact header 조립
- summary strip 조립
- items / attachments / timeline 세부 배치
- sticky action bar의 상세 미세조정

포함 가능:

- 이 화면에만 필요한 예외

금지:

- generic token 정의
- 공용 primitive 재정의 남발

### 4.6 실제 로딩 순서

`layout.html` 기준 권장 순서:

| 순서 | 파일 | 이유 |
|------|------|------|
| 1 | `static/css/erp-pro.css` | 참고 배경과 기본 제품군 스타일 로딩 |
| 2 | `static/css/wam/tokens.css` | WAM token source of truth |
| 3 | `static/css/wam/base.css` | reset / typography / focus / motion |
| 4 | `static/css/wam/layout.css` | page shell / stack / sticky frame |
| 5 | `static/css/wam/components.css` | card / badge / kv / state primitives |
| 6 | `static/css/wam/order-detail.css` | 화면 전용 조립과 미세조정 |

JS 권장 순서:

| 순서 | 파일 | 이유 |
|------|------|------|
| 1 | `static/js/wam/core.js` | 공통 util과 bootstrap parse |
| 2 | `static/js/wam/telemetry.js` | fail-open 계측 |
| 3 | `static/js/wam/attachments.js` | lazy attachment 흐름 |
| 4 | `static/js/wam/order-detail.js` | 페이지 초기화 진입점 |

## 5. 템플릿 파일별 책임

### 5.1 `templates/channel_wam/layout.html`

책임:

- WAM 전용 HTML skeleton
- CSS / JS asset 로딩
- `<script type="application/json">` bootstrap 주입
- meta, title, body class, page-level flag/state 주입

포함 가능:

- head / body shell
- asset order

금지:

- 주문 상세 콘텐츠 마크업
- section 개별 렌더 로직

### 5.2 `templates/channel_wam/index.html`

책임:

- `page_vm`를 받아 전체 화면 조립
- header
- summary strip
- section stack
- sticky action bar 배치

포함 가능:

- include 순서
- page-level empty/error fallback

금지:

- raw dict 탐색
- 비즈니스 조건 분기

section key -> partial allowlist:

| section key | partial |
|-------------|---------|
| `header` | `sections/_header.html` |
| `summary_strip` | `sections/_summary_strip.html` |
| `customer` | `sections/_customer.html` |
| `site` | `sections/_site.html` |
| `schedule` | `sections/_schedule.html` |
| `people` | `sections/_people.html` |
| `items` | `sections/_items.html` |
| `attachments` | `sections/_attachments.html` |
| `timeline` | `sections/_timeline.html` |
| `sticky_action_bar` | `sections/_sticky_action_bar.html` |

원칙:

- include 대상은 위 allowlist에 고정한다.
- 템플릿 이름을 payload에서 직접 받지 않는다.

### 5.3 `templates/channel_wam/_macros.html`

책임:

- `section_shell(section)`
- `kv_row(label, value, tone='default')`
- `badge(label, tone='default')`
- `icon_action(...)`
- `empty_block(...)`
- `error_block(...)`

포함 가능:

- 단순 표시 헬퍼

금지:

- DB/권한/flag 로직

### 5.4 `templates/channel_wam/sections/_header.html`

책임:

- 주문번호
- 상태 badge
- 긴급 / owner team badge
- 고객명
- 읽기 전용 안내
- 최근 변경 시각

### 5.5 `templates/channel_wam/sections/_summary_strip.html`

책임:

- 실측일
- 시공일
- 주소
- 연락처

원칙:

- 첫 화면에서 항상 보여야 한다.
- 기본 접힘 금지

### 5.6 `templates/channel_wam/sections/_customer.html`

책임:

- 고객명
- 연락처
- 발주자
- 상담 / 담당 매니저

### 5.7 `templates/channel_wam/sections/_site.html`

책임:

- 주소
- 상세주소
- 지도 열기

주의:

- 현장 메모는 Phase 3 정책 승인 전 hidden이면 렌더 금지

### 5.8 `templates/channel_wam/sections/_schedule.html`

책임:

- 접수일
- 실측일 / 시간
- 시공일
- 보조 일정
- AS 방문일

### 5.9 `templates/channel_wam/sections/_people.html`

책임:

- 담당 매니저
- 도면 담당
- 시공자
- owner team
- 출고 / 시공 메타

### 5.10 `templates/channel_wam/sections/_items.html`

책임:

- 품목 리스트
- 품목별 옵션
- item card 반복

### 5.11 `templates/channel_wam/sections/_attachments.html`

책임:

- attachment group
- preview tile
- count
- open/download action
- lazy placeholder

원칙:

- 첫 HTML에 presigned URL 전부 싣지 않는다.
- 기본은 preview만

### 5.12 `templates/channel_wam/sections/_timeline.html`

책임:

- 최근 변경 이력
- event badge
- 시간
- 1줄 설명

원칙:

- 전용 토큰을 새로 만들기보다 section card + badge + key-value primitives 재사용 우선

### 5.13 `templates/channel_wam/sections/_sticky_action_bar.html`

책임:

- 전화
- 주소 복사
- 지도 열기
- 첨부 보기
- 조건부 `FOMS에서 열기`

원칙:

- primary CTA 최대 1개
- page-level error 시 숨김 가능해야 한다

### 5.14 `templates/channel_wam/states/_empty.html`

책임:

- 데이터 없음
- 아직 없음
- 노출 안 함과 구분되는 empty copy

### 5.15 `templates/channel_wam/states/_error.html`

책임:

- recoverable error
- section-level error copy

금지:

- stack trace
- 내부 식별자 노출

## 6. JS 파일별 책임

### 6.1 `static/js/wam/core.js`

책임:

- bootstrap JSON parse
- DOM helper
- event delegation helper
- copy helper
- accordion helper
- fetch wrapper 기본형

금지:

- 비즈니스 데이터 shape 수정

### 6.2 `static/js/wam/telemetry.js`

책임:

- `emit(eventName, payload)`
- fail-open telemetry
- sampling / debounce

필수 이벤트:

- `wam_page_opened`
- `wam_bootstrap_succeeded`
- `wam_bootstrap_failed`
- `wam_attachment_clicked`

### 6.3 `static/js/wam/attachments.js`

책임:

- `/api/attachments` lazy fetch
- preview open/download
- skeleton -> loaded/error state 전환
- group expand/collapse

금지:

- presigned URL 장기 캐시

### 6.4 `static/js/wam/order-detail.js`

책임:

- 페이지 진입점
- lazy section 초기화
- sticky action wiring
- telemetry / attachments init 호출

금지:

- 서버가 만든 section shape 변경

## 7. 서버-클라이언트 계약

### 7.1 HTML

`layout.html`에 이것만 내려준다.

```html
<script id="wam-bootstrap" type="application/json">
  {{ bootstrap_payload|tojson }}
</script>
```

### 7.2 Bootstrap Payload

최소 필드:

- `page`
- `flags`
- `sections`
- `api`
- `telemetry`

`api` 안의 최소 필드:

- `bootstrap_url`
- `attachments_url`
- `timeline_url`

원칙:

- JS는 route를 하드코딩하지 않는다.

### 7.3 Attachments API 계약

`GET /channel/wam/api/attachments` 최소 응답 예시:

```json
{
  "ok": true,
  "order_id": 2762,
  "groups": [
    {
      "category": "measurement",
      "label": "실측 첨부",
      "count": 3,
      "preview": [
        {
          "attachment_id": 101,
          "label": "실측도 1",
          "thumbnail_url": "/channel/wam/api/attachments/101/open?mode=thumb",
          "open_url": "/channel/wam/api/attachments/101/open",
          "download_url": "/channel/wam/api/attachments/101/download"
        }
      ],
      "has_more": true
    }
  ]
}
```

에러 응답 예시:

```json
{
  "ok": false,
  "error": {
    "code": "ticket_expired",
    "message": "세션이 만료되었습니다."
  }
}
```

원칙:

- `storage_key`, presigned 원문 URL, 내부 디버그 값은 응답 금지
- `attachment_id`는 action route 안에서만 쓰이고, 클라이언트 비즈니스 키로 승격하지 않는다
- `ticket_expired`, `forbidden`, `not_found`, `temporarily_unavailable` 정도의 안정된 code set을 유지한다

## 8. 화면 조립 우선순위

구현 순서:

1. `layout.html` + `_header.html`
2. `_summary_strip.html`
3. `section card` + `key-value group` primitive
4. `_empty.html` + `_error.html`
5. `_sticky_action_bar.html`
6. `_attachments.html`
7. `_timeline.html`

화면 순서:

1. header
2. summary strip
3. primary key-value groups
4. folded sections
5. attachments
6. sticky action bar

원칙:

- `schedule`, `site`, `people`는 기본 펼침
- `attachments`, `timeline`은 heavy section으로 기본 접힘
- heavy section은 한 번에 하나만 펼침
- 모바일 persistent chrome은 `상단 1개 + 하단 1개`까지만 허용

## 9. 단계적 적용 전략

### Phase A

- `layout.html`
- `tokens.css`
- `base.css`
- 기존 V1 WAM을 새 shell 안으로 옮김

### Phase B

- `index.html`
- `_macros.html`
- `components.css`
- summary / attachments를 section 구조로 분해

### Phase C

- 서버를 `summary/attachments dict`에서 `page_vm`으로 전환

### Phase D

- `layout.css`
- `order-detail.css`
- sticky action bar

### Phase E

- `attachments.js`
- `/api/attachments`
- lazy path 전환

### Phase F

- `telemetry.js`
- `timeline`
- advanced polish

## 10. 병렬 작업 분해

### Track A

- `tokens.css`
- `base.css`
- `layout.css`
- `layout.html`

### Track B

- `_macros.html`
- `index.html`
- `sections/*`
- `states/*`
- `components.css`
- `order-detail.css`

### Track C

- `page_vm`
- section builder
- bootstrap payload 계약

### Track D

- `core.js`
- `telemetry.js`
- `attachments.js`
- `order-detail.js`

## 11. Acceptance

### 11.1 구조

- 템플릿은 `page_vm` 또는 명시된 section VM만 소비
- raw `structured_data` 직접 참조 금지
- HTML shell과 JSON API 분리 유지

### 11.2 보안

- 첨부 열기/다운로드는 `order scope + token scope` 둘 다 통과
- allowlist 밖 필드 노출 금지
- read-only 화면에서 수정 affordance 금지

### 11.3 UI

- 첫 paint `1.5초 이내`
- 주문 식별 `1초 이내`
- 핵심 정보 인지 `3초 이내`
- 첨부 탐색 시작 `5초 이내`
- section empty/hidden/error 구분 가능
- sticky header / sticky bar / anchor nav 동시 기본 활성화 금지

측정 기준:

- iPhone Safari WebView
- Android Chrome WebView
- 4G 수준 네트워크

### 11.4 스타일

- `--erp-*` 직접 사용 금지
- raw hex/px inline style 금지
- component CSS에서 semantic/reference를 건너뛰는 직접값 사용 금지

## 12. Anti-Pattern

- 기존 ERP 편집 화면 복붙
- iframe 재사용
- flat dict 계속 확장
- HTML에서 모든 presigned URL 선발급
- bootstrap JSON과 HTML의 이중 source of truth
- 하나의 티켓에서 토큰, 레이아웃, API 계약을 동시에 다 뒤집기

## 13. Rollback

### 13.1 기본 순서

1. `V2 -> V1`
2. attachments off
3. timeline off
4. 마지막에만 WAM 전체 off

실행 단위:

- `CHANNEL_WAM_V2_ENABLED=false`
- `CHANNEL_WAM_ATTACHMENTS_ENABLED=false`
- `CHANNEL_WAM_ATTACHMENTS_LAZY_ENABLED=false`
- `CHANNEL_WAM_TIMELINE_ENABLED=false`
- 최후에 `CHANNEL_WAM_ENABLED=false`

### 13.2 원칙

- `header`, `summary`, `sticky action bar`는 최우선 복구 대상
- 신규 토큰에는 fallback 값이 있어야 한다
- deprecated 토큰은 bridge 유지
- telemetry, animation, polish는 쉽게 끌 수 있어야 한다

## 14. 바로 다음 작업

1. `tokens.css` starter spec
2. `layout.html` / `index.html` starter skeleton
3. `_macros.html`에 필요한 macro 인터페이스 정의
4. `attachments.js` lazy contract 상세 명세
