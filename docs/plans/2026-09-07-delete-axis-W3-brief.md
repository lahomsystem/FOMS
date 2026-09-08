# W3 — `deleted_at` 백필 도구 (만들기만 한다 · 절대 실행하지 않는다)

계약 원문: `docs/plans/2026-09-07-delete-axis-unify-brief.md`
작업 트리: `c:\tmp\foms-s-s0907-202822` — 모든 명령을 `cd /c/tmp/foms-s-s0907-202822 && pwd && ...` 로 시작.
git 명령 금지. CRLF 보존. 신규 파일 2개만 만든다.

## 절대 경계 (먼저 읽는다)
- **운영·스테이징 DB 에 접속하지 않는다.** `DATABASE_URL` 을 세워 이 도구를 돌리지 않는다.
  조회조차 하지 않는다 — 필요한 실측치는 아래에 이미 있다.
- 검증은 **SQLite 픽스처**(`db_session`)로만 한다.
- hard delete 금지. `status`·`original_status`·`structured_data['delete']` 를 **바꾸지 않는다**.

## 운영 실측 (2026-09-07 읽기전용 조회 — 다시 재지 않는다)
휴지통 308건 = legacy 일괄 삭제 표식 246건 + ISO `T` 형식 28건 + 정본 projection 45건.

## 편집 허용 파일
- `tools/ops/backfill_deleted_at_utc.py` (신규)
- `tests/domains/test_backfill_deleted_at_utc.py` (신규)

## CEO 확정 계약

### 1. 구조·CLI
- 선례를 그대로 따른다: `tools/ops/backfill_as_schedule_links.py`
  (`sys.path.insert` → `from db import engine` → `sessionmaker`, 그리고 **세션 주입 가능한**
  `run_backfill(session, *, apply, journal_path, batch_size)` — 테스트가 SQLite 세션을 넘긴다).
- **기본 dry-run.** `--apply` 가 있어야 쓴다. `--dry-run` 은 명시적 별칭이고 `--apply` 와 동시 지정은
  exit 2. (이 저장소의 다른 도구는 `--execute` 를 쓰지만 여기는 브리프대로 `--apply` 다 —
  docstring 사용법에 그 차이를 한 줄로 적는다.)
- `--journal PATH` (기본 `backfill_deleted_at_utc_<UTC타임스탬프>.jsonl`), `--batch-size`(기본 200),
  `--revert PATH`(되돌리기 모드, `--apply` 와 함께여야 실제로 쓴다).
- 항상 마커별 `scanned / changed / skipped` 요약표를 찍는다.

### 2. 표식 규칙 — 두 마커, 순서가 계약이다
공통 전제: `deleted_at IS NOT NULL` **그리고** `structured_data['delete_backfill']` 가 **없다**.

- **M1 `iso`** — `deleted_at` 에 `T` 가 있다 → **형식만** `%Y-%m-%d %H:%M:%S` 로 정규화.
  **시각은 한 초도 옮기지 않는다.** 컨테이너 TZ 를 모르고, 대조로 쓸 만한 UTC 컬럼도 없다
  (`Order.created_at` 기본값이 `datetime.datetime.now` — models.py:36, 역시 컨테이너 로컬).
  **모르는 값을 옮기지 않는다**가 계약이다. `datetime.fromisoformat` 파싱 실패 행은
  건드리지 않고 `skipped` 로 센다.
  (dry-run 리포트에 `created_at - deleted_at` 분포를 참고용으로 찍는 것까지는 허용한다.
  그 값으로 **자동 판단하지 않는다**.)
- **M2 `legacy_kst`** — `deleted_at` 이 정확히 `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$` 이고
  `status='DELETED'` 이고 `original_status IS NOT NULL` 이고 `structured_data['delete']` 가 없다
  → KST 로 적힌 행이다. **-9시간** 보정.
- **두 마커는 배타다. 판정은 문자열 모양(T 유무)이 먼저다.**
  함정(반드시 코드 주석으로 남긴다): 초안 정리 경로가 남긴 ISO 행은
  `status='DELETED'` + `original_status='DRAFT'` + delete meta 없음이라, M1 이 고정폭으로 바꿔 놓으면
  **2회차에 M2 에 걸려 9시간이 더 깎인다.** 그래서 바꾼 행마다 표식을 남기고 두 마커 모두
  표식 있는 행을 뺀다.

### 3. 표식(멱등 열쇠) · 되돌리기
- `--apply` 로 바꾼 행마다 `structured_data['delete_backfill']` 를 남긴다:
  `{"tool": "backfill_deleted_at_utc", "marker": "iso"|"legacy_kst", "before": <원문>,
    "after": <새 값>, "at": now_utc_naive().isoformat()}`.
  JSONB 쓰기는 프로젝트 규칙대로 `copy.deepcopy` + `flag_modified`.
  이 키를 읽는 코드는 없다(`read_order_trash` 는 `structured_data['delete']` 만 본다) —
  그래도 워커가 직접 grep 해서 확인하고 보고에 적는다.
- 되돌리기 파일: **JSONL**, 변경 1건당 한 줄
  `{"order_id": int, "marker": str, "before": str, "after": str}`.
  dry-run 도 이 파일을 쓴다(그게 미리보기다). `--revert <file> --apply` 는 그 파일을 읽어
  `before` 를 되돌리고 `delete_backfill` 표식을 지운다.

### 4. 멱등 판정 기준 (이 문장이 완료 조건이다)
같은 DB 에 `--apply` 를 **두 번** 돌리면 2회차는 `changed=0` 이고, 모든 `deleted_at` 값이
1회차 결과와 **문자 그대로 같으며**, 2회차 저널 파일이 0행이다.

## 테스트 `tests/domains/test_backfill_deleted_at_utc.py`
SQLite `db_session` 픽스처. 문서를 읽는 테스트를 만들지 않는다.
1. **M2 보정**: legacy 표식 행(`2026-09-07 17:41:00`, status DELETED, original_status 있음,
   delete meta 없음) → `2026-09-07 08:41:00`.
2. **M1 정규화**: `2026-09-07T08:41:00` → `2026-09-07 08:41:00` (**시각 불변**, 문자열로 확인).
3. **교차 오염 금지(핵심)**: ISO + `status='DELETED'` + `original_status='DRAFT'` 행을 만들고
   `--apply` 를 2회 → 최종 값이 1회차와 같다(9시간이 더 깎이지 않는다).
4. **멱등**: 2회차 `changed=0`, 저널 0행.
5. **음성 대조군 2종**: (a) 정본 projection 행(`structured_data['delete']` 있음 + 고정폭)은
   어느 마커에도 안 걸린다. (b) 파싱 불가 쓰레기 값 행은 `skipped` 로만 세고 값이 안 바뀐다.
6. **dry-run 은 아무것도 안 쓴다**: 값·`structured_data` 불변, 저널만 생긴다.
7. **되돌리기**: `--revert` 뒤 원값 복원 + `delete_backfill` 제거.

## 하지 말 것
- ISO 행의 시각 보정. `--apply` 를 실제 DB 에 실행. `status`/`original_status` 변경.
- `structured_data['delete']` 생성·수정. 새 컬럼·마이그레이션.
- 다른 워커 파일(`order_candidates.py`·`ghost_orders.py`·`listing.py`·`erp_orders_structured.py`·
  `cleanup_order_drafts.py`·`soft_delete.py`) 편집 — 필요하면 고치지 말고 보고에 적는다.

## 완료 기준 (돌릴 명령)
```
cd /c/tmp/foms-s-s0907-202822 && pwd
python tools/ops/backfill_deleted_at_utc.py --help
python -m pytest tests/domains/test_backfill_deleted_at_utc.py -q
python -m pytest tests/domains -q
python -c "import app; print('APP_OK')"
```
보고에 반드시 적을 것: 마커 2종의 정확한 술어, 표식 키 이름, 저널 형식,
멱등을 어떤 테스트가 어떻게 증명했는지, 그리고 **실행하지 않았다는 확인**.
