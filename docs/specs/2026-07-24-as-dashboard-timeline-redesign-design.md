# AS 대시보드 개편 — 구조화 타임라인 + 무상/유상 2단계 판정 (B안)

- 날짜: 2026-07-24
- 상태: 사용자 방향 승인(B안), 스펙 리뷰 대기
- 근거: 코드 조사(백엔드/프론트 인벤토리), 필드서비스 SaaS UX 리서치(D365 FS·ServiceMax·Oracle·Zendesk·GetStream), 실사용 스크린샷(주문 #3602 — "-----" 구분 수기 이력)

## 1. 문제

1. **AS 내용 = 통짜 문자열 덮어쓰기.** `sd['shipment']['as_content']`/`as_content_2`에 HTML 한 덩어리, blur 시 `POST /api/update_order_field`로 전체 교체. 이력 없음, "-----" 수기 구분. **동시 편집 시 마지막 blur가 상대 기록을 통째로 삭제하는 잠복 결함.**
2. **무상/유상 개념 부재.** 코드베이스 전체 grep 0건. 유상 건 식별·필터·매출 추적 불가.
3. **이력 인프라 반쪽.** `sd['as_info']`(append 리스트)·`OrderEvent`(AS_STARTED/COMPLETED)는 있으나 접수(`as/register`) 경로는 문자열만 덮어씀.

## 2. 설계 원칙 (사용자 확정 사항 포함)

- **수기 입력이 본체다.** 각 타임라인 항목의 내용은 지금처럼 직접 타이핑한다. 프리셋 칩은 유형 분류 보조·시스템 자동 이벤트 전용이며 수기 입력을 대체하지 않는다. (사용자 명시 요구)
- 타임라인 = 수기 항목 + 시스템 이벤트 혼합 스트림 (Zendesk 이벤트 스트림 패턴).
- 무상/유상 = 접수 시 추정 → 방문 후 확정 2단계. 전환은 사유 필수 + 자동 이력.
- append-only가 분쟁 방어력. 과거 항목 수정은 제한적 허용(작성자+관리자, 수정 표식).
- 기존 JSONB(`structured_data`) 패턴 내 해결. 신규 테이블 없음 (C안 제외).

## 3. 데이터 모델 (`sd['shipment']` 신설 키)

### 3.1 `as_log` — append-only 항목 리스트

```json
[{
  "id": "al_<epoch_ms>_<rand4>",
  "ts": "<now_utc_naive ISO>",
  "by": "사용자 이름",
  "by_id": 123,
  "type": "reception|call|action|material|schedule|memo|system",
  "text": "<sanitize_as_content_html 통과한 수기 본문>",
  "edited_at": null,
  "edited_by": null
}]
```

- 유형 7종 고정 enum: 접수(reception)·통화(call)·방문/조치(action)·자재(material)·일정(schedule)·메모(memo, 기본값)·시스템(system, 서버 전용).
- `system` 항목은 서버만 생성. 클라이언트 페이로드의 `type=system`은 거부.
- 타임스탬프는 `now_utc_naive` 필수 (`datetime.now` 금지 — 프로젝트 규약).
- 사진의 항목 단위 첨부는 후속(P3 이후). 첨부는 기존 category `as` 체계 유지.

### 3.2 `as_billing` — 무상/유상 판정

```json
{
  "type": "free|paid|undecided",
  "confirmed": false,
  "amount": null,
  "reason": "",
  "decided_by": "이름",
  "decided_at": "<ISO>"
}
```

- 접수 시 기본 `free`(무상 추정)·`confirmed=false`. 접수 모달에서 3값 선택.
- 확정(confirm) 및 유형 전환은 전용 API로만. 전환 시 `reason` 필수 → `as_log`에 system 항목 자동 append ("무상→유상 전환: <사유>").
- `amount`는 기록용 정수(원). 견적/잔금/출고가 체계와 연계하지 않는다 (결정: 금액 기록만).

### 3.3 기존 필드 처리

- `as_content`/`as_content_2`: **신규 쓰기 퇴역.** 읽기는 마이그레이션 전 데이터 표시용으로 유지.
- 마이그레이션 = **lazy**: 대시보드 렌더 시 `as_log`가 없고 `as_content`가 있으면, 서버가 표시 시점에 "이전 기록" 항목(type=memo, 읽기 전용 플래그 `legacy: true`)으로 변환해 렌더. 최초 신규 항목 append 시점에 변환 결과를 `as_log`로 영구 저장. 일괄 스크립트 불요, 데이터 유실 0.
- `as_content_2`(탭2): 동일하게 "이전 기록(탭2)" 항목으로 흡수 후 퇴역 (결정: 탭 UI 제거).
- `update_order_field`의 `as_content`/`as_content_2` allowlist 항목은 P2 완료 시 제거. `as_pending`/`as_blueprint`/날짜 필드는 현행 유지.

## 4. API

| 메서드/경로 | 역할 |
|---|---|
| `POST /api/orders/<id>/as/log` | 항목 append. body: `{type, text}`. sanitize 후 저장, 응답에 렌더된 항목 |
| `PATCH /api/orders/<id>/as/log/<log_id>` | 본문 수정. 작성자 본인 또는 관리자만. `edited_*` 기록 |
| `POST /api/orders/<id>/as/billing` | 판정 확정/전환. body: `{type, amount?, reason(전환 시 필수)}` → system 로그 자동 |
| `POST /api/orders/<id>/as/register` (기존 확장) | `billing_type`(+유상 시 `amount?`) 수신, textarea 내용을 첫 `as_log` 항목(type=reception)으로 저장 |
| `GET /erp/as/timeline/<id>` | PC 확장 행용 타임라인 fragment (모바일 `card-detail` lazy 패턴 복제) |

- 공통: `_load_order_structured_data_for_update` + `copy.deepcopy` + `flag_modified` 패턴, `sync_erp_flat_columns`, `_invalidate_shipment_asrec_caches`, `SecurityLog`.
- 삭제 API 없음(P2 범위 외). 필요 시 관리자 soft-hide 후속.
- 부수 정리: `as_orders.py:100` `datetime.datetime.now()` → `now_utc_naive` 통일.

## 5. UI

### 5.1 접수 모달 (`#asReceiveModal`)
- 무상/유상 세그먼트 3값 (기본: 무상 추정, Bootstrap `btn-check` 세그먼트). 유상 선택 시에만 금액 입력 노출(점진 공개, 미입력 허용).
- 시공 관련 날짜 기반 "시공 후 N개월 경과" 자동 배지 — 판단 보조 (판정 강제 아님, 날짜 없으면 hidden).
- 필드 순서: ① AS 내용 textarea(필수, 현행) → ② 비용 세그먼트 → ③ 지방 상차일 → ④ 사진. 통화 중 접수 맥락: 문제를 먼저 받아적고 비용 판단은 말미.

### 5.2 PC 테이블 (12컬럼 밀도 유지)
- AS내용 셀 교체: 접수 원문 1줄 clamp + 최근 항목 1줄(유형 칩 포함) + "타임라인 N" 배지. 빈 건 "기록 없음 · 클릭해 첫 기록".
- 확장 = **full-width 삽입 행**(`<tr colspan="12">`, 셀 내부 아님 — 450px 셀에 20건 이력 불가). `GET /erp/as/timeline/<id>` fragment lazy fetch(모바일 card-detail 패턴 복제). 다건 동시 확장 허용. 무한스크롤 청크 append는 기존 확장 행 무영향(유지), 정렬/필터 재조회는 소멸(정상, persist 안 함).
- **billing 배지 정책: 무상 확정은 무배지** (대다수가 무상 — 배지 도배 방지). 표시는 유상("유상", 주황 채움)·미정("미정", 회색)·유상 미확정("유상?", 점선 테두리)만. 위계: 상태 배지 > billing 배지(아래 줄, 더 작게). 색은 접수 모달 세그먼트와 동일 계열.
- 필터 select `billing` 추가(데스크톱 form + 모바일 offcanvas 양쪽): 전체/무상/유상/미정. 서버 쿼리는 JSONB `->>` 비교 (hot path ILIKE 금지 규칙 준수 — 등호 비교라 인덱스 부담 낮음, EXPLAIN 확인).
- 미완료 탭 KPI 스트립 4→5 pill: "유상 미확정 N건" 추가(`?billing=paid_unconfirmed` 버킷 링크). CSS grid `repeat(4)`→`repeat(5)`, 모바일 2열 3행.

### 5.3 모바일 v2 카드 / 태블릿
- 카드 lazy 영역(`/erp/as/card-detail/<id>`)의 탭 에디터 → 타임라인 + quick-add로 교체 (macro 교체로 자동 반영).
- 원탭 프리셋 버튼 4종(부재중/조치 완료/재방문 필요/자재 필요): 탭 시 해당 유형 + 기본 문구로 항목 생성, **문구는 전송 전 수정 가능** (수기 입력 원칙 유지).
- 태블릿 전/후 사진 대조 표면 현행 유지.

### 5.4 렌더 SSOT
- `render_as_content_tabs` 매크로(`as_card_macros.html`) → `render_as_timeline`으로 교체. PC 테이블·모바일 카드·무한스크롤 청크 3표면 동시 반영.
- **입력기 = `<textarea>` 확정** (contenteditable 폐기 — IME 조합·blur 취약성 근본 제거). 저장은 명시 버튼("기록 추가") + Ctrl/⌘+Enter(단, `e.isComposing || keyCode===229` 가드). Enter=줄바꿈. optimistic 렌더: 성공 시 응답 항목 prepend + textarea clear, 실패 시 텍스트 보존·에러 표시.
- **퇴역 범위**: 리치툴바(`as-rich-toolbar-template`, B/색상 버튼)·2탭 시스템(`as-content-tab-btn`/`as_content_2`)·contenteditable autosave 경로(as-dashboard.js 탭 전환·flush·draft)·관련 CSS 전부.
- **`sales_delivery` 토글 이전 필수**: 현 영업/전달 토글(`.as-sales-delivery-btn`)이 리치툴바 소속이라 퇴역 시 소실 위험 — PC 확장 행 헤더 + 모바일 상세 헤더로 이전. 기능 보존 계약 테스트 동반.
- **검색 하이라이트 신규 정적 함수**: 현 `maybeApplyAsContentHighlight`는 contenteditable 전용 → 타임라인 정적 텍스트·접힘 셀 요약용 함수 신설(`mark.as-search-highlight` 스타일 재사용, 확장 fragment 주입 후 재적용).
- JS: **`?v=` 캐시 버스트 범프 필수 + 참조 핀 전수 grep** (SW staticCacheFirst 함정).
- fragment 재실행 안전: 신규 리스너는 document 위임 + `window.__FOMS_*_BOUND` 싱글톤 가드 (perf 가드 G4).
- 인라인 `style="min-height: 60px"` 등 인라인 스타일 제거 → `as-dashboard-body.css`로.

### 5.5 UX 상세 결정 (persona 설계 확정분)

- **타임라인 구조**: 접수 원문은 **앵커 슬롯 상단 고정**(스트림에서 제외, 중복 없음) — 이력이 길어도 "무엇이 문제인가" 상시 노출. 나머지는 역시간순 스트림, 기본 최근 8개 + "이전 기록 더보기".
- **항목 렌더**: 수기 = `[유형 칩][작성자][시각]` + 본문. 시스템 이벤트 = 칩 대신 아이콘 + 옅은 배경(수기와 시각 분리). 유형 칩 색: 접수=남색·통화=파랑·방문/조치=초록·자재=주황·일정=보라·메모=회색.
- **시각 표기**: 상대 표기 기본("N분 전"/"어제"), `title`+`datetime`에 절대 KST(분쟁 추적용). 저장 UTC-naive → 렌더 시 KST 변환.
- **유형 칩 흐름**: 기본값 memo, 저장 후 memo 리셋 ("최근 사용 유형 기억"은 YAGNI 기각).
- **모바일 프리셋 4종**(부재중·조치 완료·재방문 필요·자재 필요, 부재중이 첫 버튼): 탭 → textarea에 초안 문구 주입 + 유형 자동 설정 + focus → **수기 수정 후 저장** (자동 전송 아님 — 수기 입력 본체 원칙). 위치는 lazy 상세 내부 quick-add 위(항상 보이는 footer 아님 — 이력 맥락 없는 중복 기록 방지).
- **수정 표식**: `edited_at` 있으면 "(수정됨)" 회색 접미 + title에 수정 시각·수정자. PATCH 후 해당 항목만 교체.
- **동시성**: append 독립 id라 충돌 없음(현행 blur 덮어쓰기 clobber 근본 해소). 확장 중 타 사용자 append는 재조회 전 미표시 허용.
- **legacy 표시**: 마이그레이션 전 통짜 기록은 앵커 슬롯에 "이전 기록" 라벨·옅은 배경·읽기 전용으로 렌더. `as_content_2`는 legacy 항목 하나 더로 흡수.
- **과도기 안내**: 온보딩 투어 기각. 1회 dismissible 힌트 배너("AS 내용이 이력 형식으로 바뀌었습니다. 기존 내용은 '이전 기록'에 그대로 있습니다.", localStorage 기억)만.

## 6. 시스템 이벤트 자동 기록 (P3)

`as_log`에 system 항목 자동 append: AS 접수됨(register), 방문일 확정(schedule), 무상↔유상 전환(billing), AS 완료(complete). 기존 `as_info`/`OrderEvent` 기록은 병행 유지(불변).

## 7. 단계·검증

| 단계 | 범위 | 완료 기준 |
|---|---|---|
| P1 | `as_billing` + 접수 모달 세그먼트 + 필터/배지/KPI | 신규 pytest(모달 등록→필터→배지), `APP_OK`, 기존 AS 테스트 10파일 green |
| P2 | `as_log` + API 3종(log/patch/fragment) + 매크로/JS 교체 + lazy 마이그레이션 + `update_order_field` 퇴역 | 신규 pytest(append·수정 권한·sanitize·lazy 변환·legacy 보존·**sales_delivery 토글 보존**), 3표면 렌더 계약, gstack browse E2E |
| P3 | 시스템 이벤트 + 모바일 프리셋 + billing 전환 로그 | 이벤트 발생 계약 테스트, 모바일 E2E |

- 각 단계 push 전 `pre_push_smoke.ps1` exit 0, push 후 `ci_watch` green.
- 성능: 대시보드 TTFB 측정 + EXPLAIN Seq Scan 없음 확인 (billing 필터), fragment 바이트 예산 (타임라인은 셀 요약만 eager, 전체는 확장 시).

## 8. 범위 제외 (YAGNI)

- 음성 입력, 오프라인 큐 확장, 항목 단위 사진 첨부, 견적/청구 라인 연계, AS 별도 테이블 정규화(C안), 삭제 API. 필요가 실증되면 후속.
