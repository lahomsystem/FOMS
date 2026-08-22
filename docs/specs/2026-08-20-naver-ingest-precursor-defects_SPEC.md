# 네이버 수집 화면 — UI 개편 선행 결함 수정 (SPEC)

- 작성 2026-08-20 · 브랜치 `session/naver-ingest` · 워크트리 `c:/tmp/foms-s-naver-ingest`
- 상위 설계 정본: `docs/research/2026-08-20-naver-ux/04_설계_결정.md` §구현 전 반드시 처리할 선행 결함
- 감사 근거: 같은 폴더 `03_현화면_감사.md`
- v2 목업(개편 목표 화면): `docs/design/mockups/naver-ingest-workbench-v2.html`
- 원장: `docs/plans/2026-08-20-naver-precursor-defects-ledger.md`

## 목적

UI 개편(탭 4개 통합)을 얹기 **전에**, 그 위에 얹으면 그대로 굳어버리는 데이터·상태 결함을 닫는다.
개편은 화면 배치를 바꾸는 일이고, 이 스펙은 **화면이 읽는 값 자체가 틀린 것**을 바로잡는 일이다.

## 범위

| # | 결함 | 이 스펙 | 비고 |
|---|---|---|---|
| 5 | `.alert` 5초 자동닫힘으로 실행 결과 증발 | 포함 (T1) | triage 는 `ecc484cb` 에서 이미 처리됨 |
| 8 | 페이지 링크에서 `place` 필터가 조용히 풀림 | 포함 (T2) | |
| 4 | 취소·반품 건을 큐에서 못 뺀다 | 포함 (T3) | |
| 1 | 두 화면의 '집' 정의가 다르다 | 포함 (T4) | 묶음키 컬럼 신설 — 사용자 결정 2026-08-20 |
| 2 | 단위 혼선(nav 140건 vs 필터 43집) | 포함 (T5) | T4 의 컬럼에 의존 |
| 7 | 대조표 구조적 불일치 | **제외** | v2 목업의 2단 대조표가 답이라 UI 개편 본체에서 닫는다(사용자 결정) |

## 결함별 사실 관계 (코드 확인 완료)

### #1 집 정의 불일치 — 두 키는 실수가 아니다

```
확인 큐  mapping.group_key(detail) -> (orderId, shipping.tel1, build_address(shipping))
         근거: 분할배송이면 같은 주문번호라도 수취인·주소가 다르다.
               하나로 합치면 남의 주소로 시공을 나가는 사고가 된다.
               foms/services/integrations/naver_commerce/mapping.py:425

이력 표  _history_group_key(link) -> external_order_no or "link:<id>"
         _group_key_col()          -> 같은 규칙의 SQL 식
         근거: 페이지 경계에서 한 집이 쪼개지지 않으려면 SQL 로 셀 수 있어야 한다.
               foms/web/admin/naver_ingest.py:119, 128
```

세밀한 키는 `raw_snapshot`(JSONB) 안의 값을 **파이썬으로 조립**해야 나온다.
그래서 이력이 그 키를 못 쓴 것이고, SQL 로 세려면 값을 **컬럼에 미리 적어 두는 수밖에 없다**.

**결정: 수집 시점에 묶음키를 컬럼으로 기록한다.** 두 화면이 같은 컬럼을 읽으면
정의가 하나가 되고, 이력은 여전히 SQL 로 셀 수 있다.

### #2 단위 혼선

`compute_triage_pending_count` 가 **링크 행**을 센다(= 상품주문 140건).
화면 필터·헤더는 **집**을 센다(43집). 같은 화면에서 두 단위가 병존해 업무량이 3배로 읽힌다.
`foms/services/integrations/naver_commerce/triage_count.py:30`

T4 의 묶음키 컬럼이 생기면 `count(distinct group_key)` 로 단위가 맞는다.

### #4 취소·반품 큐 이탈 불가

`templates/admin/naver_triage.html` 카드 footer 가 배타 분기다.

```jinja
{% if not selected.order_id %}   ← 주문 없음: "주문 만들기" 만
   ...
{% else %}                        ← 주문 있음: 담당자 지정 + "확인 완료"
   ...
{% endif %}
```

취소·반품 건은 주문을 만들 수 없으므로(서버가 400) 영원히 `if` 쪽에 남고,
`확인 완료` 버튼을 만나지 못해 큐에서 빠지지 않는다.

### #5 `.alert` 자동닫힘

`templates/admin/naver_ingest.html:20`
`<div id="naver-run-result" class="alert d-none" role="status"></div>` — `data-foms-no-autodismiss` 없음.
전역 5초 자동 제거가 실행 결과 문구를 지운다.

### #8 페이지 링크 필터 유실

라우트는 `place` 를 읽는다(`naver_ingest.py:364`).
템플릿 페이지 링크는 `status` 와 `page` 만 넘긴다(`naver_ingest.html:246, 255`).
`발주확인 전`으로 거른 뒤 2페이지로 가면 필터가 풀린 전체 목록이 나온다.

## 설계

### D1. 묶음키 컬럼 `group_key`

- **모델**: `ExternalOrderLink.group_key = Column(String(200), nullable=True, index=True)`
  - nullable 인 이유: 기존 행이 있고, backfill 전에도 화면이 죽으면 안 된다.
  - 길이 200: `orderId(≤64) + tel(≤20) + 주소(≤120 절단)` 를 구분자로 이은 값.
- **값 규칙**: `mapping.group_key(detail)` 의 3-튜플을 `\x1f`(unit separator)로 이어 정규화한 문자열.
  - 정규화 함수 `mapping.group_key_text(detail) -> str` 를 새로 두고, 기존 `group_key()` 는 그대로 둔다
    (기존 호출부 `promotion.py:500,520` 의 튜플 비교 의미를 바꾸지 않는다).
- **기록 시점**: 수집(upsert) 시 항상. 재수집으로 `raw_snapshot` 이 갱신되면 함께 갱신한다.
- **읽기**: 이력 표의 `_history_group_key` / `_group_key_col()` 이 이 컬럼을 쓴다.
  - **NULL 폴백**: `coalesce(group_key, nullif(external_order_no,''), 'link:'||id)`.
    backfill 전/실패 행이 있어도 예전과 같은 동작으로 떨어질 뿐 화면이 죽지 않는다.
- **마이그레이션**: `navergroup_00_external_order_link_group_key`, `down_revision='naver_relation_00'`(현 head).
  - 컬럼 추가 + 인덱스 `(channel, group_key)` 만 한다. **데이터 이동은 하지 않는다.**
  - 마이그레이션 안에서 `models`·`mapping` 을 import 하지 않는다(상수 동결 원칙 — 과거 마이그레이션 소급 오염 방지).
  - `downgrade()` 는 인덱스·컬럼 drop.
- **backfill**: `scripts/maintenance/backfill_naver_group_key.py` 를 따로 둔다.
  `raw_snapshot` 을 읽어 `mapping.group_key_text` 로 계산해 채운다. 멱등(이미 값이 있으면 건너뜀), `--dry-run` 지원.

### D2. 단위 통일

- `compute_triage_pending_count` → `count(distinct coalesce(group_key, ...))`.
- nav 배지 라벨은 숫자만 유지하되, 화면 헤더는 v2 목업과 같이 **집 + 상품주문 이중 표기**.
- 계약 테스트 `test_naver_nav_entry.py` 가 링크 수 기대값을 갖고 있다 → 집 수 기대값으로 먼저 고친다.

### D3. 취소·반품 확인 완료

카드 footer 배타 분기를 푼다.

- `확인 완료` 버튼은 **분기 밖**(footer 공통 영역)으로 옮긴다 — 주문 유무와 무관하게 항상 있다.
- `주문 만들기` 는 `if not selected.order_id` 유지 + 기존 클레임 잠금(`selected.claim.blocking`) 유지.
- `담당자 지정` 은 `else` 유지(주문이 있어야 지정할 대상이 있다).
- 서버 review 라우트는 이미 주문 없이도 동작한다 — 변경 없음. **템플릿 구조만 바꾼다.**

### D4·D5. 한 줄짜리

- `naver_ingest.html:20` 에 `data-foms-no-autodismiss` 추가.
- 페이지 링크 `url_for(...)` 에 `place=('PENDING' if place_pending else None)` 추가(2곳).

## 하지 않는 것

- 탭 4개 통합·좌우 분할 등 **화면 배치 변경**(= UI 개편 본체).
- 대조표 재설계(#7).
- `mapping.group_key()` 의 기존 튜플 시그니처 변경(호출부 의미 보존).
- 자동 승격·자동 확인 완료 같은 **사람 판단을 대신하는 동작** 추가.

## 완료 정의

1. 새 계약 테스트가 red → 구현 후 green (테스트 우선 — 사용자 결정).
2. `python -m pytest tests/services/integrations/ -q` 전건 통과.
3. `python -c "import app; print('APP_OK')"` 성공.
4. PG 레인에서 마이그레이션 왕복(upgrade→downgrade→upgrade) 통과.
5. `scripts/ops/pre_push_smoke.ps1` exit 0.
6. backfill 스크립트 `--dry-run` 이 로컬 데이터에서 계산 결과를 출력.
