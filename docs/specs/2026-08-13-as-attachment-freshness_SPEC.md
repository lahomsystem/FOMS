# AS 기록별 첨부 + PUSH 최신성 (AS-FRESH-01) — 스펙

- 작성: 2026-08-13
- 상태: **승인됨(2026-08-13) — T6·T7·T8·T9 구현 완료, T1~T5(스키마·기록별 첨부) 대기**
- 선행: T15 AS 회차 차트(ver7, `as_round_chart.py` / `as_round_chart.html`), CHANNEL-WRITER-01(push metadata 원자 기록)
- 사용자 결정(2026-08-13): 파일 선택 = **자동 + 확인창에서 수정 가능**, PUSH 본문 = **접수 원문 + 현재 회차 기록**

## 1. 문제

### 1.1 채널톡 AS PUSH에 옛 파일이 섞여 나간다 (운영 장애)

[`channel_integration.py:363-372`](../../foms/api/channel/channel_integration.py#L363-L372)

```python
attachments = (db.query(OrderAttachment)
    .filter(OrderAttachment.order_id == order.id,
            OrderAttachment.category == kind_config['category'])   # ← 시점·회차 필터 없음
    .order_by(OrderAttachment.id.asc()).all())                     # ← 오래된 것부터
```
그 뒤 [`channel_policy.py:190-192`](../../foms/services/channel_policy.py#L190-L192) 가 `files[:20]`.

두 겹의 결함이다.

- **혼입**: 그 주문의 `category='as'` 첨부 **전량** 발사. 1차 AS 사진, 3개월 전 사진, 방금 올린
  사진이 한 메시지에 섞인다. 받는 쪽은 무엇이 이번 건인지 구분할 수 없다.
- **최신 탈락**: `id.asc()` + 앞 20개 절단 = **가장 오래된 20장**. AS 첨부가 21장을 넘는 순간
  방금 올린 사진은 **아예 전송되지 않는다**. "최신성 훼손"의 실체는 최신 누락이다.

### 1.2 본문이 접수 원문에서 멈춰 있다

[`channel_as_message.py:110`](../../foms/services/channel_as_message.py#L110) 은 `sd['shipment']['as_content']`
하나만 읽는다. 접수 이후 타임라인에 쌓인 방안·통화·자재 기록은 PUSH에 실리지 않는다.
화면(회차 차트)은 최신인데 나가는 메시지는 접수 시점 그대로다.

### 1.3 기록별 첨부가 구조적으로 불가능하다

`OrderAttachment` 컬럼([`models.py:239-282`](../../models.py#L239-L282))에 as_log 항목·회차와 잇는 축이
없다. 결합 축은 `category='as'` 하나. 업로드 표면 2곳
([`erp-order-shared.js:3040-3069`](../../static/js/orders/erp-order-shared.js#L3040-L3069),
[`as-dashboard.js:2401-2452`](../../static/js/cs/as-dashboard.js#L2401-L2452))도 category만 붙인다.
그래서 "이 기록의 사진"이라는 개념이 데이터에 없고, 1.1의 회차 필터도 걸 수가 없다.

### 1.4 발송 provenance 부재

push 이력 `sd['channeltalk_push_as']` 는 `pushed/message_id/group_id/sent_at/is_modified/change_log`
만 남긴다([`channel_integration.py:200-216`](../../foms/api/channel/channel_integration.py#L200-L216)).
**무엇을 보냈는지**가 없어 "안 보낸 것만" 판정이 불가능하다.

## 2. 목표 / 비목표

**목표**
1. AS 타임라인 기록마다 파일을 붙이고, 그 기록 줄에서 바로 미리보기한다.
2. AS PUSH가 **이번 건의 최신 파일**만 보낸다 — 넘칠 때 잘리는 쪽은 옛 파일이다.
3. PUSH 본문이 접수 원문 + 현재 회차 기록을 담는다.
4. 전송 전 확인창에서 보낼 파일을 눈으로 확인하고 수정할 수 있다.
5. 발송 provenance를 이력에 남겨 재전송 판정 근거로 쓴다.

**비목표**
- 기존 첨부(회차 링크 없음)의 소급 배정 — 추정 배정은 오귀속을 만든다. "이전 첨부"로 남긴다.
- 실측/도면 PUSH 경로 동작 변경 (`push_kind` 분기 안에서만 손댄다).
- `as_content` / `as_log` 이중 SSOT 통합 (§7 후속).
- 채널톡 전송 transport(`dispatch_order_event`) 변경.

## 3. 설계

### 3.1 결합 축 — `order_attachments.as_log_id` (T1)

```python
as_log_id = Column(String(64), nullable=True)   # as_log 항목 id (al_<epoch_ms>_<hex4>)
__table_args__ = (..., Index('ix_order_attachments_as_log_id', 'order_id', 'as_log_id'))
```

**JSONB에 파일 목록을 넣지 않는 이유**: 첨부는 이미 tombstone 수명주기(`deleted_at` + STORAGE_DELETE
outbox)와 전역 가시성 필터를 가진다. as_log 안에 파일 메타를 복제하면 삭제·썸네일 생성 시점에
두 진실이 갈라진다. 또 as_log는 append-only라 사본이 영구 stale이 된다.

**회차 컬럼을 두지 않는 이유**: 회차는 `as_log` 항목의 `round` 파생값이다(`current_as_round` 규약).
비정규화하면 판정 정정 시 드리프트한다. 회차가 필요한 경로(PUSH 필터)는 어차피 `structured_data`
를 이미 로드하므로 `log_id → round` 맵을 메모리에서 만든다.

### 3.2 업로드 경로 (T2)

두 등록 라우트가 `as_log_id` 를 받는다.
- `POST /api/orders/<id>/attachments` (form): `request.form['as_log_id']`
- `POST /api/orders/<id>/attachments/complete` (direct R2): `data['as_log_id']`

검증 (양쪽 공용 헬퍼 `resolve_as_log_ref(db, order, category, raw)`):
1. 빈 값 → `None` (기존 동작 유지).
2. `category != 'as'` 인데 값이 있으면 **400** — 축 오염 차단.
3. `sd['shipment']['as_log']` 에 그 id가 없거나 `deleted is True` → **400**. 임의 문자열 저장 금지.

`serialize_attachment` 응답에 `as_log_id` 포함.

### 3.3 접수 경로 응답 보강 (T3)

`POST /as/register` 는 지금 항목 id를 돌려주지 않는다([`as_orders.py:510-518`](../../foms/api/cs/as_orders.py#L510-L518)).
응답에 `reception_log_id` 추가한다.
- 새로 append했으면 그 항목 id.
- `already_logged` 중복 가드([`as_orders.py:449-452`](../../foms/api/cs/as_orders.py#L449-L452))로
  append를 건너뛴 경우 **직전 동일 본문 reception 항목의 id**. 그래야 무편집 재접수에서 올린
  파일도 결합 대상을 얻는다.

### 3.4 렌더 — 기록 줄 썸네일 (T4)

`build_as_round_chart_view(sd, *, attachments_by_log_id=None)` 로 확장.
호출 라우트([`as_dashboard.py:138,175`](../../foms/web/cs/as_dashboard.py#L138))가 **1쿼리**로
`category='as'` 첨부를 읽어 `log_id → [파일]` 로 묶어 주입한다(N+1 금지 — hot path 규칙).
`decorate_entry` 결과에 `files` 리스트를 얹는다.

템플릿 `render_as_rchart_entry_row` 에 썸네일 스트립 추가:
- 이미지 = 썸네일 카드, 클릭 → 기존 `GlobalImageViewer`(모바일 이미지 뷰어 SSOT).
- 비이미지 = 파일명 칩, 클릭 → 다운로드.
- 편집 가능 표면에서만 행 우측에 `+파일` 버튼(이미 남긴 기록에 나중에 붙이기).
- `as_log_id` 없는 기존 첨부는 **행에 렌더하지 않는다**. 기존 첨부 모달 갤러리가 계속 소유.

지도 카드 인라인 확장은 같은 부품을 공유하므로 `readonly=1` 경로에서도 썸네일은 보이고
`+파일` 버튼만 사라진다.

### 3.5 입력창 첨부 (T5)

quick-add 폼(`.as-rchart-dock`)에 파일 선택 + 제출 전 로컬 미리보기(`URL.createObjectURL`).

제출 순서:
1. `POST /as/log` → `entry.id`
2. `fomsUploadOrderAttachmentsBatch({category:'as', asLogId: entry.id, ...})`
3. `refreshRoundChart(orderId)`

**부분 실패 규약**: 로그는 저장됐고 업로드만 실패한 경우 **로그를 되돌리지 않는다**(as_log는
append-only, 소프트 삭제는 흔적을 남긴다). 해당 행에 "첨부 N건 실패" 표시 + `+파일` 로 재시도.
텍스트는 이미 저장됐으므로 사용자 입력 손실은 없다.

접수 모달도 같은 배선: `register` 응답 `reception_log_id` 를 업로드에 전달.

### 3.6 PUSH 파일 선정 (T6)

`select_as_push_attachments(sd, attachments, prev_push) -> list[OrderAttachment]`
(신규 `foms/services/channel_as_attachments.py`)

```
current_round = current_as_round(sd)
round_of = {entry.id: entry.round for entry in as_log}          # 삭제 항목 제외

1. 현재 회차 = [a for a in atts if round_of.get(a.as_log_id) == current_round]
2. 비었으면 → 미발송분 = [a for a in atts if a.id > prev_push['max_attachment_id']]
3. 비었으면 → 최신 20장 (구주문 최초 PUSH)
→ id 내림차순 정렬 후 상한 20 절단 → 전송 시에는 오름차순(업로드 순)으로 되돌림
```

절단이 **최신 20장을 남긴다**는 점이 1.1의 직접 수정이다. 상한은 기존
`MAX_MANUAL_ATTACHMENTS = 20`(채널톡 정책) 그대로.

`prev_push['max_attachment_id']` 는 이력에 없으면 `0` 으로 간주(구 주문 하위호환).

### 3.7 전송 전 확인창 (T7)

**미리보기 API** `GET /api/channel/push-preview?order_id=<id>&push_kind=as`
→ `{success, text, files:[{id, filename, thumb_url, is_image, selected, log_label}]}`
- `selected` = §3.6 기본 선정 결과.
- 기본 미선택 파일도 **같은 회차 밖 항목까지 최대 40장**까지 함께 내려 사용자가 되살릴 수 있게 한다.
- `log_label` = "1차 · 방안 8/13" 같은 출처 표기(어느 기록의 사진인지 보이게).

**전송** `POST /api/channel/push-manual` 에 `attachment_ids: [int]` 선택 필드 추가.
- 있으면: 그 id만 사용. 서버가 `order_id` + `category='as'` 소속을 재검증(불일치 400), 상한 20 절단.
- 없으면: §3.6 기본 규칙(ERP 주문탭 기존 경로·하위호환).

UI: AS 첨부 모달의 `AS PUSH` 버튼 → 기존 `confirm()` 대신 확인 모달.
본문 미리보기 + 파일 체크박스 그리드 + "선택 N건 전송".

### 3.8 PUSH 본문 (T8)

`build_as_push_text(order)` → `build_as_push_text(order, sd=None)` 로 시공자 줄 + 현재 회차 기록 합류.

```
고객명 : 이성민(용산)
발주사 : 짓다인테리어
시공일 : 6월 11일
주  소 : 서울 용산구 백범로90길 74, 이안용산 103-502
연락처 : 010-9040-5693
                              ← 빈 줄
시공자 - 문정현
                              ← 빈 줄
내용 : 후드 교체 요청 - 유상AS
후드값+시공비=140,000원 안내
로청장 좌측 EP 본드 접착
                              ← 빈 줄
[1차 기록]
- 8/13 방안: 후드 자재 발주 후 방문
- 8/13 통화: 고객 오후만 가능
```

**시공자 줄 규칙** (사용자 지정 2026-08-13):
- 값 SSOT = `sd['shipment']['construction_workers']`(리스트, `_normalize_construction_workers` 정규화 산물).
- 표기 = `시공자 - <이름>`. 콜론이 아니라 하이픈 — 고객정보 5줄(`라벨 : 값`)과 **다른 서식이 의도**다.
  섹션 구분자 역할이라 `_append_line` 을 쓰지 않고 별도로 조립한다.
- 복수면 `, ` 로 이어 붙인다 (`시공자 - 문정현, 김철수`).
- **값이 없으면 줄과 앞뒤 빈 줄을 통째로 생략** — 기존 출력과 바이트 동일.
- 앞뒤 빈 줄 1개씩. 채널톡 렌더에서 `_paragraph_blocks` 가 빈 줄을 문단 경계(nbsp 블록)로
  살리므로([`channel_policy.py:175-186`](../../foms/services/channel_policy.py#L175-L186))
  화면 갭이 그대로 재현된다.

**현재 회차 기록 규칙**:
- 현재 회차(`current_as_round`) 항목만. `system` · `verdict` · `legacy` · 삭제 항목 제외.
- `reception` 제외 — 이미 `내용 :` 줄이 담는다(중복 방지).
- 시간 오름차순, **최대 10건 / 합계 1,000자**. 초과분은 `- 외 N건` 한 줄.
- 본문은 `as_content_html_to_text(already_sanitized=True)` 로 평문화(HTML 유출 금지).
- 현재 회차 기록이 0건이면 `[N차 기록]` 블록 자체를 생략 — 기존 출력과 동일.
- 기존 `_MAX_TEXT_LENGTH` 가드는 합류 **후** 길이로 판정.

### 3.9 발송 provenance (T9)

`_record_push_metadata` 의 `next_push` 에 추가:
```python
'attachment_ids': [int, ...],          # 이번에 보낸 첨부 id
'max_attachment_id': max(ids) or prev  # 단조 증가(다음 델타 판정 기준)
```
`attachment_ids` 는 change_log와 같은 이유로 **최신 1회분만** 보관(누적 금지 — JSONB 폭증).
`max_attachment_id` 만 단조 유지한다.

> **시각 비교 금지**: `OrderAttachment.created_at` default 는 `datetime.datetime.now`(naive **local**)
> 이고 push `sent_at` 은 UTC ISO다. 두 값을 비교하면 로컬 dev에서 9시간 skew가 난다.
> 델타 판정은 **id 단조성**으로만 한다.

## 4. 작업 분해 · 완료 기준

| T | 내용 | 완료 기준(검증 명령) |
|---|---|---|
| T1 | `as_log_id` 컬럼 + 인덱스 + alembic | 단일 head 유지, `upgrade`→`downgrade`→`upgrade` 왕복 성공, `models` live import 없음(상수 동결) |
| T2 | 업로드 2경로 `as_log_id` 수용·검증 | 신규 `tests/domains/test_as_log_attachments.py`: 정상 결합 / 미존재 id 400 / non-as category 400 |
| T3 | `register` 응답 `reception_log_id` | `test_as_log_api.py` 확장: 신규·무편집 재접수 양쪽에서 id 반환 |
| T4 | 뷰 빌더 + 템플릿 썸네일 | `test_as_round_chart.py` 확장: `files` 주입 렌더, 미결합 첨부 비노출, 쿼리 1회(N+1 가드) |
| T5 | quick-add·접수 모달 첨부 배선 | 스테이징 실브라우저: 기록+사진 저장 → 그 줄에 썸네일, 새로고침 후 유지 |
| T6 | PUSH 파일 선정 서비스 | `test_channel_integration_smoke.py` 확장: **21장 → 최신 20장**, 회차 격리, 미발송 델타, 구주문 폴백 |
| T7 | preview API + 확인 모달 | 계약 테스트(응답 스키마·소속 검증 400) + 스테이징 QA |
| T8 | 본문 시공자 줄 + 현재 회차 합류 | `test_channel_as_message.py` 확장: 시공자 유/무(무=기존 출력 바이트 동일)·복수 시공자·앞뒤 빈 줄 보존·합류·캡·회차 격리·기록 0건 생략·HTML 평문화 |
| T9 | provenance 기록 | smoke 확장: 이력 `attachment_ids`/`max_attachment_id`, replay 시 중복 없음 |

전 구간 공통: `python -c "import app; print('APP_OK')"`, `scripts/ops/pre_push_smoke.ps1` exit 0.

**출고 순서**: T6→T8→T9→T7 (운영 버그 선출고, 마이그레이션 불필요) → T1~T5 (스키마 동반).
T6의 1순위 규칙은 T1 이후에야 유효하므로, 선출고분은 2·3순위(미발송 델타 → 최신 N)로 동작한다.
이것만으로도 1.1의 두 결함(혼입·최신 탈락)은 사라진다.

## 5. 리스크

| 리스크 | 대응 |
|---|---|
| 필터 강화 = **덜 보내는** 회귀 | 21장·회차 격리·구주문 폴백 3종 계약 테스트로 하한 고정. 확인창이 최종 방어선 |
| 기존 첨부 회차 미상 | 소급 배정 금지. "이전 첨부"로 모달에만 유지 |
| as_log 항목 삭제 후 첨부 고아 | 첨부는 독립 수명 — 행에서 사라져도 모달 갤러리에 남는다(물리 삭제 아님) |
| `failopen` 인벤토리 라인시프트 CI red | 본 작업은 신규 `try/except` 추가 없음. 불가피하면 원격 tip 클린 worktree에서 인벤토리 재생성 |
| JSONB 폭증 | `attachment_ids` 최신 1회분만, 본문 합류 10건/1,000자 캡 |
| SW 캐시 stale JS | `as-dashboard.js` 변경 시 `?v=` 범프 + 핀 전수 grep |

## 6. 영향 파일

```
models.py                                   # as_log_id 컬럼
migrations/versions/<new>.py                # 신규
foms/api/files/order_routes.py              # form 업로드
foms/api/files/direct_upload.py             # direct 완료
foms/api/cs/as_orders.py                    # register 응답
foms/services/orders/as_round_chart.py      # files 주입
foms/services/channel_as_message.py         # 본문 합류
foms/services/channel_as_attachments.py     # 신규 — 파일 선정
foms/api/channel/channel_integration.py     # 선정 호출·preview·provenance
foms/web/cs/as_dashboard.py                 # 첨부 배치 로드
templates/cs/partials/as_round_chart.html   # 썸네일 스트립
templates/cs/partials/as_dashboard_body.html# 확인 모달
static/js/cs/as-dashboard.js                # 첨부 배선·확인창
static/js/orders/erp-order-shared.js        # 접수 모달 결합
static/css/components/foms-as-round-chart.css
```

## 7. 후속 (본 스펙 밖)

- `as_content` / `as_log` 이중 SSOT 해소 — PUSH 본문이 as_log 최신 reception을 읽게 전환.
- `already_logged` 텍스트 동일성 휴리스틱 → entry id 기반 교체.
- 업로드 표면 2곳의 공용 헬퍼 통합.
