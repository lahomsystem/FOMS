# AS 첨부 표시·전송 순서 (AS-SORT-01) — 스펙

- 작성: 2026-08-19
- 상태: **🟢 승인됨(2026-08-19)** — 구현 완료(로컬, 커밋 전)
- 선행: AS-FRESH-01 (`docs/specs/2026-08-13-as-attachment-freshness_SPEC.md`, T1~T9 구현됨)
- 사용자 결정(2026-08-19):
  1. 순서는 **올리기 전**(미리보기)과 **올린 뒤**(기록 줄 썸네일) **둘 다** 지정한다.
  2. 표면 4곳: ERP 주문 AS 접수 모달 · AS 대시보드 기록 입력창 · 기록 줄 클립 · AS PUSH 확인창.
  3. **채널톡 PUSH는 지정한 순서 그대로 첨부**한다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물

직원이 AS 사진을 1→2→3으로 정해 두면, 회차 차트 썸네일·이미지 뷰어·채널톡 AS방 메시지 첨부가 **같은 1→2→3**으로 나간다. 올린 뒤에도 썸네일을 옮겨 바꿀 수 있고, PUSH 확인창에서 이번 전송만 다른 순서로 보낼 수 있다.

### 1.2 문제

지금은 “순서”가 데이터에 없다. 화면·PUSH는 `OrderAttachment.id` 오름차순을 “업로드 순”으로 가정한다.

세 겹으로 그 가정이 깨진다.

1. **병렬 업로드**: `fomsUploadOrderAttachmentsBatch`는 R2 PUT을 동시에 돌린다(모바일 3 / PC 5). 행은 `attachments/complete`가 **끝나는 순간** INSERT 되므로, 작은 파일이 먼저 끝나면 `id`가 먼저 붙는다. 미리보기 1→2→3이 DB·PUSH에서 2→1→3이 된다.
2. **미리보기에 순서 UI가 없다**: ERP 접수는 삭제만, 대시보드 입력창은 미리보기만, 클립은 고르자마자 업로드.
3. **PUSH가 지정 순서를 버린다**: 확인창이 `attachment_ids: [3,1,2]`를 보내도 서버가 `sorted(explicit_ids)`로 id순 재배열한다.

```python
# foms/api/channel/channel_integration.py (현재)
attachments = [allowed[i] for i in sorted(explicit_ids)]
```

채널톡 transport(`send_group_message` → `dto.files`)는 **배열 순서 = 첨부 순서**다. 순서가 깨지는 곳은 FOMS가 리스트를 다시 정렬하는 지점이지, 채널톡 API가 아니다.

### 1.3 기능 요구사항

1. 올리기 전 미리보기에서 파일 순서를 바꾼다(드래그 + ▲▼). 그 순서가 DB `sort_order`로 저장된다.
2. 올린 뒤 회차 차트 기록 줄 썸네일을 같은 방식으로 바꿔 저장한다.
3. AS PUSH 확인창에서 보낼 파일의 순서를 정하면, 채널톡 메시지 첨부가 **그 배열 순서 그대로**다. 기본값(확인창을 안 만진 경우)은 저장된 `sort_order`다.
4. 상한 20장 절단은 **지정 순서의 앞 20장**을 남긴다. id순으로 다시 잘라서는 안 된다.

### 1.4 예외 / 비목표

- 실측·도면·시공 첨부 UI 순서 지정. 컬럼은 공용이지만 쓰는 표면은 AS만.
- 기존 행의 소급 추정 배정. `sort_order IS NULL`은 `id ASC` 폴백(현재와 동일).
- 채널톡 transport(`dispatch_order_event` / `send_group_message`) 변경. 넘기는 리스트 순서만 고친다.
- as_log JSONB에 파일 목록 복제 금지(AS-FRESH-01과 동일 — 첨부는 tombstone 수명주기가 있다).
- 첨부 모달 갤러리(미결합·이전 첨부)의 드래그 정렬 — 이번 범위 밖. 미결합 파일이 PUSH에 실리면 확인창 순서가 전송 정본이다.

---

## 2. How — 어떻게 만드는가

### 2.1 정본 축 — `order_attachments.sort_order`

```python
sort_order = Column(Integer, nullable=True)  # 작을수록 앞. NULL = 레거시 → id 폴백
```

**정렬 키(전 경로 공용)**: `(sort_order ASC NULLS LAST, id ASC)`.

**UNIQUE를 걸지 않는 이유**: 재정렬 스왑 중간값 충돌, `as_log_id` NULL 그룹, 병렬 INSERT. 동점은 `id`로 푼다.

**JSONB에 안 넣는 이유**: AS-FRESH-01과 같다. 첨부의 진실은 `order_attachments` 한 곳.

**회차 컬럼을 안 만드는 이유**: 순서의 스코프는 **같은 기록(`as_log_id`) 안**이다. 회차는 기록의 파생값이다.

기존 인덱스 `ix_order_attachments_as_log_id (order_id, as_log_id)` 유지. 차트는 주문당 1쿼리로 읽고 메모리에서 묶는다(N+1 금지). 그룹 크기가 작아 정렬 전용 인덱스는 두지 않는다.

`serialize_attachment` / `to_dict`에 `sort_order`를 넣는다.

### 2.2 업로드 — 클라이언트가 인덱스를 실어 보낸다

두 등록 경로가 같은 필드명을 받는다.

- `POST /api/orders/<id>/attachments` (form): `sort_order`
- `POST /api/orders/<id>/attachments/complete` (direct R2): JSON `sort_order`

검증 (공용 헬퍼 `parse_attachment_sort_order(raw) -> (ok, value|None, err)`):

| 입력 | 결과 |
|------|------|
| 없음 / `null` / `""` | `None` (레거시·단건 폴백). 서버가 그 `as_log_id` 그룹의 `max(sort_order)+1`을 부여. 그룹이 비었거나 전부 NULL이면 `0` |
| 정수 0..9999 | 그대로 저장 |
| 그 외 | 400 |

배치 업로드는 **반드시** 미리보기 순으로 `0..n-1`을 실어 보낸다. 병렬 PUT을 유지한다 — 순서는 `id`가 아니라 `sort_order`가 담당하므로 동시 완료가 순서를 깨지 않는다.

`fomsUploadOrderAttachmentsBatch`에 `sortOrders?: number[]`(files와 같은 길이)를 추가한다. form/complete 양쪽에 붙인다. 길이가 다르면 클라가 올리지 않고 실패를 드러낸다(조용한 무시 금지).

### 2.3 올린 뒤 재정렬 API

`POST /api/orders/<id>/attachments/reorder`

```json
{ "as_log_id": "al_…", "ids": [12, 7, 9] }
```

- `as_log_id`: 문자열(그 기록) 또는 JSON `null`(미결합 그룹). 생략 금지.
- `ids`: 그 그룹의 **현재 살아 있는** AS 첨부 id 전체 순열. 빠진 id·다른 그룹·다른 주문·tombstone → **400**.
- 권한: 기존 `can_modify_order_attachment`를 목록 전부에 적용. 하나라도 거부면 **403**, 부분 저장 없음.
- 트랜잭션 안에서 `ids[i]` → `sort_order = i`.
- 응답: `{success, attachments: [serialize…]}` 정렬 키 순.

기존 `PATCH .../attachments/<id>`는 `item_index` 전용으로 둔다. 필드 과적 금지.

### 2.4 읽기 경로가 같은 정렬 키를 쓴다

| 경로 | 현재 | 변경 |
|------|------|------|
| 회차 차트 `_as_attachments_by_log_id` | `id.asc()` | `(sort_order ASC NULLS LAST, id ASC)` |
| `select_as_push_attachments` 반환 | id 오름차순(“업로드 순”) | 같은 정렬 키. 상한 절단은 **키 역순으로 최신(큰 sort_order / 큰 id)을 남긴 뒤**, 정방향으로 되돌린다 |
| `GET /api/channel/push-preview` 선택분 | `id` 내림차순 그리드 | **선택분은 전송 기본 순서**(정렬 키 오름차순). 미선택 후보는 그 아래 |
| AS 첨부 갤러리 목록 | `created_at.desc()` | 이번 범위 밖(모달 UX 유지) |

이미지 뷰어(`GlobalImageViewer`)는 DOM 버튼 순서를 따르므로, 차트 썸네일 순서가 곧 뷰어 순서다.

### 2.5 채널톡 PUSH — 지정 순서가 전송 정본

**계약**: `POST /api/channel/push-manual`의 `attachment_ids` 배열 순서 = `dto.files` 순서 = 채널톡에 붙는 순서.

서버는 소속·상한만 검사하고 **재정렬하지 않는다**.

```
explicit_ids 가 있으면:
  1. 소속 재검증(order + category='as' + 살아 있음). 불일치 400.
  2. attachments = [allowed[i] for i in explicit_ids]   # sorted() 금지
  3. apply_attachment_policy = files[:20]               # 앞 20장 = 지정 순서의 앞 20장
없으면:
  select_as_push_attachments 결과(정렬 키 오름차순)
```

확인창 UI:

- 선택된 파일을 **번호(1,2,3…) 붙은 가로 스트립**으로 보여 준다. 이 스트립 순서 = 전송 순서.
- 데스크톱: 드래그. 모든 폭: ▲▼.
- 체크 해제 → 후보 풀로. 다시 체크 → 선택 스트립 **맨 뒤**.
- 21장 이상 선택이면 “앞 20장만 전송”을 스트립 위에 표시하고 21번째부터 흐리게.
- 전송 시 `selectedPushIds()`는 **스트립 DOM 순서**다(지금처럼 `querySelectorAll`이면 스트립이 DOM 정본이어야 한다).

미리보기 API의 `selected: true` 항목은 이미 정렬 키 순으로 내려서, 확인창을 안 만져도 저장된 순서가 기본 전송이 된다.

provenance `attachment_ids`는 **실제로 나간 순서**를 기록한다(재정렬하지 않은 그 배열의 앞 20).

### 2.6 올리기 전 UI — 공용 미리보기

신규 작은 헬퍼(인라인 300줄 가드): `static/js/cs/as-attachment-order.js`

- 파일 배열을 들고 미리보기(이미지 objectURL / 비이미지는 아이콘).
- 드래그 + ▲▼ + 삭제.
- `getFiles()`가 현재 순서의 `File[]`를 돌려준다.

세 표면이 이 헬퍼만 쓴다. `erp-pro.css` / `foms-as-round-chart.css`에 번호 뱃지·핸들. **인라인 스타일 금지.**

| 표면 | 올리기 전 | 올린 뒤 |
|------|-----------|---------|
| ERP `#asReceiveModal` | 기존 `#as-receive-preview`를 헬퍼로 교체. 삭제 유지 + 순서 | 해당 접수 기록 줄은 AS 대시보드 차트와 동일 부품 |
| 대시보드 `.as-rchart-dock` | 미리보기에 삭제·순서 추가. `change`로 FileList를 통째 교체하지 않고 **추가 merge**(ERP `erpAppendAsReceiveFiles`와 같음) | 기록 줄 썸네일 드래그/▲▼ → reorder API |
| 기록 줄 클립 | 고르자마자 업로드 금지. 그 줄 아래에 스테이징 스트립 + **올리기** 버튼 | 같은 줄 썸네일 재정렬 |
| PUSH 확인창 | (업로드 아님) 선택 스트립 순서 = 전송 | — |

클립 스테이징에서 취소를 누르면 로컬 파일만 버리고 기록은 그대로다.

올린 뒤 썸네일 재정렬은 `can_edit` 표면만. `readonly=1`(지도 카드)은 보기만.

JS 변경 시 `as-dashboard.js` / `erp-order-shared.js` / 신규 헬퍼의 `?v=` 범프 + 핀 전수 grep (AS-FRESH-01 §5와 동일). ERP shell 재실행 대비 헬퍼 바인딩은 `window.__AS_ATTACH_ORDER_BOUND` 싱글톤(G4).

### 2.7 수정 대상 파일

| 파일 | 변경 |
|------|------|
| `models.py` | `OrderAttachment.sort_order` + `to_dict` |
| `migrations/versions/assort_00_attachment_sort_order.py` | 컬럼 추가. `models` live import 없음. `downgrade` 포함. parent = 구현 시점 `alembic heads` |
| `foms/api/files/common.py` | `parse_attachment_sort_order`, serialize에 필드 |
| `foms/api/files/order_routes.py` | form 업로드 수용, **reorder 라우트 신규** |
| `foms/api/files/direct_upload.py` | complete JSON 수용 |
| `foms/web/cs/as_dashboard.py` | `_as_attachments_by_log_id` 정렬 키 |
| `foms/services/channel_as_attachments.py` | 선정 결과 정렬 키. 절단은 최신 보존 규칙 유지 |
| `foms/api/channel/channel_integration.py` | `sorted(explicit_ids)` 제거. preview 선택분 순서. provenance = 전송 순서 |
| `static/js/runtime/upload-progress.js` | 배치에 `sort_order` 전달 |
| `static/js/cs/as-attachment-order.js` | 신규 미리보기/순서 헬퍼 |
| `static/js/cs/as-dashboard.js` | dock merge·클립 스테이징·줄 재정렬·PUSH 스트립 |
| `static/js/orders/erp-order-shared.js` | 접수 미리보기 헬퍼 연결, 배치에 인덱스 |
| `static/css/components/foms-as-round-chart.css` | 번호 뱃지·핸들 (인라인 스타일 금지) |
| `templates/cs/partials/as_round_chart.html` | 썸네일에 `data-attachment-id`, 편집 시에만 핸들 |
| `templates/cs/partials/as_dashboard_body.html` | PUSH 확인창 마크업을 선택 스트립 + 후보 풀로 |
| `templates/orders/partials/erp_order_tab.html` (+ mobile) | 접수 미리보기 훅 클래스 |
| `tests/domains/test_as_log_attachments.py` | 업로드 `sort_order` / 생략 시 max+1 / 잘못된 값 400 |
| `tests/domains/test_channel_as_attachments.py` | 정렬 키·절단이 최신(큰 sort_order) 보존 |
| `tests/domains/test_channel_integration_smoke.py` | **`attachment_ids: [c,a,b]` → files 순서 c,a,b**. 회귀: `sorted()` 재도입 금지 |

`dispatch_order_event` / `channel_policy.apply_attachment_policy`는 리스트 앞 20장을 자를 뿐 재정렬하지 않는다 — 손대지 않는다.

### 2.8 의존성·영향

- DB 마이그레이션 필요 (`sort_order` nullable integer).
- AS-FRESH-01 선정 3단(현재 회차 → 미발송 델타 → 최신 N)은 유지. 바뀌는 것은 **선정된 리스트의 정렬**과 **explicit ids 재정렬 금지**뿐.
- `max_attachment_id` 델타 판정은 계속 id 단조성. `sort_order`와 무관(시각 비교 금지 원칙도 유지).
- 신규 `try/except: pass` 없음. failopen 인벤토리 라인시프트가 나면 원격 tip 클린 worktree에서 재생성.

---

## 3. Steps — 실행 단계

승인 후에만 코딩한다.

- [x] **T1** 스키마: `sort_order` + alembic + serialize. 단일 head, upgrade↔downgrade 왕복, `models` live import 없음.
- [x] **T2** 쓰기: form/complete가 `sort_order` 수용. 배치 JS가 인덱스를 양쪽 경로에 실음. 계약 테스트.
- [x] **T3** 재정렬 API + 차트/뷰어가 정렬 키를 읽음. 순열 검증 400/403.
- [x] **T4 채널톡 (우선 출고 가능)**: `sorted(explicit_ids)` 제거. preview 선택분 = 전송 기본 순서. smoke: `[c,a,b]` → files `c,a,b`. `select_as_push_attachments` 정렬 키. **이 태스크만으로도 “확인창에서 정한 순서가 채널톡에 그대로”가 성립한다.**
- [x] **T5** 공용 미리보기 헬퍼 + ERP 접수 + dock merge/삭제/순서 + 클립 스테이징.
- [x] **T6** 기록 줄 썸네일 재정렬(readonly 제외) + PUSH 확인창 번호 스트립·▲▼/드래그.
- [x] **T7** `?v=` 범프, `APP_OK`, 관련 pytest. `pre_push_smoke.ps1` 은 push 직전에.

출고 순서: **T4를 T1과 독립적으로 먼저** 내도 된다(마이그레이션 없음). 확인창 DOM 순서를 `attachment_ids`로 보내기만 하면 채널톡 순서는 즉시 고쳐진다. T1~T3은 회차 차트·기본 선정이 같은 순서를 기억하게 한다. T5~T6은 지정 UX.

---

## 4. 검증 기준

- [x] `python -c "import app; print('APP_OK')"` 성공
- [x] `attachment_ids: [idC, idA, idB]` 수동 PUSH → `dispatch_order_event`에 넘어간 `files` 파일명이 C, A, B (id 오름차순이 아님)
- [x] 같은 3장을 `sort_order` 2,0,1로 저장 → 차트 썸네일·PUSH 기본 선정이 0→1→2 파일 순
- [x] 병렬 업로드(동시성>1) 3장에 `sort_order` 0,1,2 → 저장 후 차트 순서가 미리보기와 동일 (`id`는 뒤섞여도 됨) — 배치는 PUT 병렬 유지, 순서는 `sort_order` 필드
- [x] 클립 스테이징에서 순서 바꾼 뒤 올리기 → 그 기록 줄 순서와 일치 — 클라가 `baseSort`+인덱스를 실음
- [x] 올린 뒤 썸네일 이동 → 새로고침 후에도 유지, 다음 PUSH 기본 순서에 반영 — `POST .../attachments/reorder`
- [x] 21장 선택 → 지정 순서의 앞 20장만 전송, 뒤 1장 탈락
- [x] 레거시 `sort_order IS NULL`만 있는 주문 → 기존과 같이 `id ASC` (회귀 없음)
- [x] readonly 차트에 드래그 핸들 없음
- [x] 인라인 스타일·동기 `<script>` 신규 없음 (perf 가드 G1)

---

## 5. 참고 자료

- 선행 스펙: `docs/specs/2026-08-13-as-attachment-freshness_SPEC.md` (결합 축 `as_log_id`, PUSH 3단 선정, 확인창, provenance)
- 전송: `foms/services/channel_dispatch.py` `apply_attachment_policy` = `files[:20]` (순서 보존)
- 채널톡 payload: `foms/services/channel_client.py` `dto.files`
- 현재 순서 파괴 지점: `foms/api/channel/channel_integration.py` `sorted(explicit_ids)`
- 업로드 병렬: `static/js/runtime/upload-progress.js` `fomsRunLimitedQueue`
- 템플릿: `docs/guides/SPEC_TEMPLATE.md`
