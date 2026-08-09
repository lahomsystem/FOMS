# 감사 로그 가독성·커버리지 설계 (AUDIT-LOG P4)

- 작성: 2026-08-08
- 상태: **승인 대기** (구현 착수 전)
- 선행 정본: `docs/specs/2026-08-05-system-audit-logging-design.md`(T1~T12),
  `docs/harness/runtime/HANDOFF_AUDIT_LOGGING.md`
- 목표(사용자 문장): **"모든 사용자의 모든 행위를 기록·감시·추적한다. 로그를 보고
  무엇을 했는지 아주 자세히, 명확히 알 수 있어야 한다."**

---

## 1. 실측 (운영 `lahom-production`, 읽기 전용 조회, 2026-08-08)

| 지표 | 값 | 조회 |
|---|---|---|
| `security_logs` 총량 | 24,605행 (2025-05-15 ~ 현재) | `count(*)` |
| 최근 30일 | 1,471건 | `timestamp > now()-30d` |
| 그 중 `권한 없는 접근 시도: /trash` | **474건 (32%)**, 최다 1인 282건(wntm0714) | `message LIKE` |
| 활성 사용자 29명 중 최근 30일 보안로그 0건 | **12명** | `users ⨝ security_logs` |
| `order_events` 최근 30일 | 11,497행 중 15종 이벤트 | `group by event_type` |
| 쓰기 라우트(POST/PUT/PATCH/DELETE) | 172개 | AST 유사 스캔 |
| 그 중 감사 기록 호출 없음 | **102개 (59%)** | 본문에 writer 심볼 부재 |
| 운영 DB `security_logs.action/target_type/target_id/detail` | **컬럼 없음** | `information_schema` |

**운영 DB에는 T8 구조화 컬럼이 아직 없다** — 즉 현재 운영 로그는 100% 자유 텍스트다.
구조화 필터·구조화 detail 은 승격(T4~T11 마이그레이션) 이후에만 운영에서 동작한다.

### 1-1. 실제 로그 원문 (운영, 최근 30일 상위 유형)

```
474  권한 없는 접근 시도: /trash
426  주문 #4109의 'as_visit_date' 필드를 '2026-07-23'(으)로 변경
103  지방 주문 #4336의 'regional_blueprint_sent' 상태를 'True'(으)로 변경
 97  주문 #3210의 'as_completed_date' 필드를 ''(으)로 변경
 34  주문 #4426의 'as_content' 필드를 '<div>7/22 해피콜 - 고객 일정 확인 …</div>도어 교체'(으)로 변경
  2  주문 #4394의 'as_visit_availability' 필드를 '{'days': 'weekday', 'time': 'any'}'(으)로 변경
```

### 1-2. 행위자별 기록 편차 (최근 30일)

| 사용자 | security_logs | order_events(실제 주문 변경) |
|---|---|---|
| wlsghv2 | **0** | 126 |
| kmk0909 | 1 | 88 |
| jdsjjh | 2 | 64 |
| ds5izi | 6 | 74 |
| wntm0714 | 745 (282=거부 로그) | 87 |

**주문을 126번 바꾼 사람의 보안 로그가 0건**이다. 지금 원장으로는 "누가 무엇을 했는가"를
물을 수 없다.

---

## 2. 문제 정의 (관리자 페르소나)

| # | 문제 | 증거 | 영향 |
|---|---|---|---|
| P1 | **코드 언어 노출** — 영어 필드명·`True`·python dict repr·HTML 원문 | 1-1 전 항목 | 읽으려면 개발 지식 필요 |
| P2 | **대상 식별 불가** — 주문번호만, 고객명 없음 | `주문 #4382` | 매번 주문을 열어 확인 |
| P3 | **before 부재** — "무엇에서" 가 없다 | `'' (으)로 변경` 97건 | 되돌리기·책임 규명 불가 |
| P4 | **행위자 누락** — 주문 변경이 보안 원장에 안 남음 | 1-2 표 | 감시 목표 미달 |
| P5 | **미기록 행위** — 결제확인·시공 시작/완료·AS 시작/완료·도면 업로드/완료/삭제·생산 시작/완료·파일 업로드/삭제·채팅 발송 | 102/172 라우트 | 추적 불가 구간 |
| P6 | **열람 무기록** — 고객 개인정보 화면 조회 흔적 0(파일만 T6/T12) | `access_logs` 파일 전용 | 유출 사고 시 추적 불가 |
| P7 | **노이즈가 신호를 덮음** — 거부 로그가 전체의 32% | 1 표 | 화면 첫 페이지가 거부 로그로 채워짐 |

### 2-1. 이미 있는데 갇혀 있는 자산

- `foms/web/orders/edit.py:274-278` 에 **한글 필드 라벨 맵 + before→after 문장 생성기**가
  이미 있다. 그러나 **그 라우트 안에 지역 변수로 갇혀 있어** `field_update.py`·`regional.py`·
  `status.py` 등 다른 경로는 전부 raw 영어를 쓴다.
- `foms/services/order_event_display.py` 는 **order_events 전용** 한글 표시 SSOT다
  (STAGE·팀·도면상태·승인상태 맵 보유). security_logs 는 이 자산을 안 쓴다.

→ 새 사전을 만드는 게 아니라 **흩어진 표시 규약을 SSOT 로 모아 양쪽에 쓰는 것**이 설계의 핵심.

---

## 3. 설계

### 3-1. 표시 SSOT — `foms/services/audit_message_display.py` (신설)

```
render_audit_line(row, *, order_index) -> str        # 사람 문장 1줄
field_label(field: str) -> str                       # 영문 필드 → 한글 라벨
format_value(field: str, value: Any) -> str          # 값 → 사람 표기
parse_legacy_message(message: str) -> LegacyParts|None   # 과거 자유 텍스트 역파싱
```

- **라벨 맵**: `edit.py` 지역 dict 를 이 모듈로 이관하고 `edit.py` 는 이 모듈을 import 한다
  (중복 사전 금지 — 두 벌이 되면 즉시 어긋난다).
- **값 포맷 규칙**

  | 원본 | 표기 |
  |---|---|
  | `True` / `False`(체크리스트 계열) | `완료` / `해제` |
  | `''`, `None` | `(지움)` |
  | `2026-07-23` | `2026-07-23` (그대로, 이미 사람 표기) |
  | `{'days':'weekday','time':'any'}` | `평일 · 시간무관` |
  | `<div>…</div>텍스트` | 태그 제거 후 60자 요약 + `…` |
  | stage 코드(`DRAWING`) | `STAGE_LABELS` 경유 한글 |

- **주문 식별**: `주문 #4382 (홍길동)` — 렌더 시점에 `order_id` 배치 조회
  (`in_(ids)` 1회, 페이지당 1쿼리, N+1 금지). 삭제된 주문이면 `(주문 삭제됨)`.
- **역파싱**: 과거 24,605행은 재기록이 불가능하므로 **렌더 시점에 정규식으로 역파싱**해
  같은 문장 규격으로 보여준다. 파싱 실패 시 원문을 그대로 노출한다(감사 화면은 값을
  감추지 않는다 — T12 에서 세운 원칙).

**결과 예시**

| 지금 | 개선 후 |
|---|---|
| `지방 주문 #4183의 'regional_construction_info_sent' 상태를 'True'(으)로 변경` | `지방 주문 #4183 (김철수) — 시공정보 발송: 완료로 표시` |
| `주문 #3210의 'as_completed_date' 필드를 ''(으)로 변경` | `주문 #3210 (이영희) — AS 완료일: 2026-07-02 → (지움)` |
| `주문 #4394의 'as_visit_availability' 필드를 '{'days': 'weekday', 'time': 'any'}'(으)로 변경` | `주문 #4394 (박민수) — AS 방문 가능시간: 평일 · 시간무관` |

### 3-2. 기록 보강 (쓰기 시점)

`log_access(...)` 호출부가 구조화 인자를 채우게 한다(T8 인자 규약 재사용).

```python
log_access(
    message,                       # 사람 문장(표시 SSOT 로 생성)
    actor_id,
    action='ORDER_FIELD_UPDATED',
    target_type='order', target_id=order.id,
    detail={'field': field, 'before': before, 'after': after,
            'order_type': '지방'|'자가실측'|'일반',
            'customer_name': order.customer_name},   # 표시용 스냅샷(주문 삭제 후에도 추적)
)
```

- **before 수집**: `setattr` 직전 값을 읽어 담는다. 세 경로 우선 —
  `foms/api/orders/field_update.py`, `foms/api/orders/regional.py`, `foms/api/orders/status.py`.
- **PII 주의**: `customer_name` 만 넣는다(연락처·주소 금지). 기존 혼입(연락처 12.6%·주소
  11.8%)을 늘리지 않는다 — 이월 항목 `security_logs PII 분리`와 충돌하지 않는 최소 범위.

### 3-3. 커버리지 배선

미기록 102개 중 **업무 의미가 있는 것만** 배선한다(무의미한 계산·프리뷰 API 제외).

| 묶음 | 라우트 예 | 기록할 action |
|---|---|---|
| 결제 | `api_payment_confirm` | `PAYMENT_CONFIRMED` |
| 시공 | `api_construction_start/complete` | `CONSTRUCTION_*` |
| AS | `api_as_start/complete/log_delete` | `AS_*` |
| 도면 | `api_drawing_gateway_upload/complete`, `api_upload_blueprint/complete/delete` | `DRAWING_*` |
| 생산 | `api_production_start/complete/uncomplete` | `PRODUCTION_*` |
| 파일 | `api_upload_session(_batch)`, `api_finalize_upload_draft`, 첨부 삭제 | `FILE_UPLOADED`/`FILE_DELETED` |
| 계정·권한 | 이미 T5 로 대부분 기록됨(잔여 점검만) | — |

기준: **"운영자가 나중에 '누가 이거 했어?' 라고 물을 수 있는 행위"만 기록**한다.
계산기 프리뷰·자동저장 draft 같은 것은 제외(원장 도배 방지).

### 3-4. 노이즈 분리 (P7)

- 거부 로그(`ACCESS_DENIED`)는 기본 목록에서 **분리 탭/필터**로 뺀다(T12 의 구 형식 분리와
  같은 방식: 기본 숨김 + 스위치).
- 부수 효과로 실제 운영 문제 1건이 드러난다: **wntm0714 가 30일간 `/trash` 282회 거부**.
  메뉴는 보이는데 권한이 없다는 뜻 — 권한을 주든 메뉴를 숨기든 **업무 차원의 결정**이 필요하다.

### 3-5. 열람 기록 (사용자 결정 보류 — 데이터 먼저)

현재 근거로는 규모를 단정할 수 없다(운영에 조회 계측이 없음). 그래서 **행을 남기지 않는
카운터 모드**를 1주일 돌려 실제 규모를 잰 뒤 결정한다.

- 계측: 주문 상세 조회 시 in-memory 카운터 + 하루 1회 집계 1행만 기록.
- 참고 추정: 주문 변경이 하루 평균 60~90건(피크 189). 열람:변경 비율을 5~10배로 보면
  **하루 300~900건 · 2년 보존 시 24~72만 행** — 지금 `security_logs`(15개월 24,605행)의
  10~30배. 인덱스 있으면 감당 가능하나, **결정은 실측 후**.

---

## 4. 비목표 (이번 범위 아님)

- `security_logs` PII 분리(연락처·주소 마스킹) — 별건 이월.
- `access_logs.additional_data` JSONB 승격 — 별건 이월.
- 운영 승격(T4~T11 마이그레이션) 자체 — 별도 사용자 결정.

---

## 5. 전제·리스크

| # | 항목 | 처리 |
|---|---|---|
| 1 | 운영에 T8 구조화 컬럼 없음 | **P1(표시)는 승격 없이 동작**(렌더 시점 변환). P2·P3 의 구조화 detail 은 승격 후 효과 |
| 2 | 과거 24,605행 재기록 불가 | 역파싱으로 표시만 통일, 실패 시 원문 노출 |
| 3 | 라벨 사전 이중화 | `edit.py` 지역 dict 를 SSOT 로 이관하고 계약 테스트로 이중 정의 금지 |
| 4 | 로그 폭증 | 기록 대상은 "물어볼 수 있는 행위"로 한정, 열람은 계측 후 결정 |
| 5 | 렌더 N+1 | 주문/고객 조회는 페이지당 배치 1회, 계약 테스트로 고정 |
