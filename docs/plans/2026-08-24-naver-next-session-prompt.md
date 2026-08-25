# 다음 세션 프롬프트 — 네이버 워크벤치 (2026-08-24 작성)

아래를 그대로 붙여 넣으면 된다.

---

**C 네이버 워크벤치 — 링크 상한 + 운영 승격 설계.
작업 위치 `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

원장 `docs/plans/2026-08-24-naver-workbench-async-result-ledger.md` 를 아래에서 위로 읽어라.
계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개가 판정 기준).
스펙: `docs/specs/2026-08-24-naver-workbench-async-result_SPEC.md`.

## 지금 상태 (2026-08-24 종료 시점)
- deploy 에 불가역 3종 결과 즉시 반영(폴링 + soft refresh) · nav 뱃지 단일 비행 ·
  벌크 진행률 · 터치 잠금사유까지 올라가 있다.
- 스테이징 실측으로 폴링 실패 경로를 눈으로 확인했다(3초 만에 사유가 새로고침 없이 뜸).
- 게이트는 여전히 **upperkill 단독**(`FOMS_NAVER_WORKBENCH_COHORT=38`).
  railway 링크 디렉토리는 `/c/tmp/foms-devlink`(FOMS-DEV) — 저장소 디렉토리에서 railway 금지.
- claude_master 로 스테이징을 보려면 코호트를 잠시 `38,58` 로 넓히고 **반드시 38 로 원복**한다.

## 1순위 — 링크 상한 (승격 게이트 2, 이번에 보류한 것)

`QUEUE_LINK_FETCH_LIMIT = 250`. 스테이징이 **238링크(73집)** 라 12건 남았다. 닿으면
"상한에 닿아 일부 집이 안 보입니다" 띠가 **상시 발동**한다 — 늘 켜진 경고는 아무도 안 읽고,
정작 진짜로 잘릴 때 못 알아챈다(2026-08-24 에 같은 결함을 이미 한 번 고쳤다).

**그냥 올리면 안 되는 이유**: nav 뱃지 콜드 비용이 링크 수에 비례해 는다.
실측(2026-08-24, 73집): 게이트 OFF 콜드 2.5ms vs **게이트 ON 콜드 113ms**(최악 280ms).
상한을 600 으로 올리면 집 176개 규모에서 콜드가 280ms 대로 간다.

**그래서 순서가 있다**: ① 뱃지 콜드 비용을 낮추고 ② 그 다음 상한을 올린다.

뱃지 비용을 낮추는 것이 왜 간단하지 않은가 — `_workbench_group_count` 는 목록과 **같은
함수**(`_work_groups`)를 쓴다. 취소 표식(`triage_state` JSONB)과 원본 스냅샷을 읽어 거르고
발주확인 전 집을 더하기 때문에 SQL 술어 하나로 세어지지 않는다
(`foms/services/integrations/naver_commerce/triage_count.py` docstring 참조).
바꾸려면 **뱃지 == 탭 숫자 == 칩 '전체'** 계약(계약 §2.4)을 새로 증명해야 한다.

검토할 후보:
- 취소·반품 판정을 컬럼으로 끌어내려 SQL 로 세기(스냅샷 파싱 제거)
- 캐시 TTL 상향(30 → 120초)으로 콜드 빈도 1/4 — 대신 숫자가 최대 2분 낡는다
- 뱃지만 근사치로 두고 화면 숫자와 다를 수 있음을 인정 → **금지**(이 프로젝트가 반복해서
  고쳐 온 "한 화면 두 말" 결함이다)

## 2순위 — 운영 승격 설계 (별건, 사용자 명시 요청 시에만)

**지금 밀면 전 시스템이 죽는다.** 실측 근거는 `docs/plans/2026-08-24-naver-production-promotion-blockers.md`.

세 줄 요약:
1. `orders.as_axis_status` 컬럼이 운영에 없다 → `Order` 조회가 전부 500(대시보드·목록·상세·검색).
2. 운영 stamp `merge_prod_drawq` 의 리비전 파일이 deploy 에서 **삭제**됐다 →
   `alembic upgrade head` 가 "Can't locate revision" 으로 한 줄도 못 돈다.
3. `assort_00`·`notifrole_00` 의 **부모가 바꿔치기**됐다 → 같은 revision 두 계보.

PR #133(`promote/2026-08-21-full`)은 쓸 수 없다 — 운영 head 전제가 `notifrole_00` 인데
지금은 `merge_prod_drawq` 라 머지하면 head 2개가 되고, `naver_link_00` 부모도 deploy 와
달라 제3의 계보가 된다. 3일 낡아 v3·관계축·직접취소·폴링이 전부 빠져 있다.

필요한 것: 운영 실제 head 를 **출발점으로 인정**하는 체인 재설계 → 운영 스냅샷 복제본에서
`upgrade`/`downgrade` 왕복 실증 → **당일 머지**(하루 지나면 head 전제가 또 깨진다).
440 커밋 승격이라 별도 스펙·원장 + 사용자 명시 승인이 필요하다.

## 3순위 — 남은 자잘한 것
- `확인 완료 — 큐에서 빼기` 버튼의 안내 `title` 은 여전히 hover 전용(잠금 사유가 아니라
  설명문이라 상시 문구로 올리면 군더더기가 된다 — 판단 필요).
- nav 뱃지 fail-open 이 실패한 쿼리로 **요청 트랜잭션을 오염**시키는지 미확인
  (`compute_triage_pending_count` 가 예외를 잡지만 rollback 은 안 한다).

## 함정 (실제로 걸린 것만)
- **작업 디렉토리가 조용히 `C:\DEV\FOMS` 로 돌아간다.** 백그라운드 명령이 `cd` 하면
  세션 cwd 가 리셋된다. git 명령 전에 `pwd` 로 확인해라(공유 트리에 커밋하면 사고다).
- 파이썬 heredoc 안의 `\n` 이 실제 줄바꿈으로 바뀌는 경우가 있다 — 문자열에 개행이
  필요하면 `String.fromCharCode(10)`·`chr(10)` 이나 개행 없는 구분자를 써라.
- 백그라운드 python 은 `-u` 없이 파이프로 넘기면 끝날 때까지 출력이 안 보인다.
- `foms_failopen_inventory.json` 줄밀림 diff 는 게이트가 안 보므로 **커밋하지 마라**.
  `foms_order_mutation_writer_inventory.json` 은 반대로 lineno 를 무니 재생성해 커밋한다.
- AI_STATUS 는 푸시할 때마다 충돌한다. deploy(HEAD) 블록을 통째로 채택하고 내 줄만 교체.
  상단 40줄 4000자 예산(`tests/harness/test_hook_log_hygiene.py`).
- JS/CSS 고치면 `templates/admin/naver_workbench.html` 의 `?v` 핀 범프(현재 `20260824i`).
- 없는 `order_id` 를 테스트에 꽂지 마라(로컬 SQLite 는 FK 미강제, CI 는 강제).
- 로컬엔 Redis·Docker·WSL 이 **없다**. enqueue 라우트는 503 으로 정상 실패하므로 폴링의
  성공 경로는 로컬 브라우저로 못 본다 — 스테이징에 가짜 링크(`CLAUDE-TEST-`, 비숫자
  상품주문번호)를 심어 실패 경로로 검증하고 **반드시 삭제**한다.

## 확정 규칙 (다시 묻지 마라)
- 상세는 항상 한 집만. 벌크 대상 ⊆ 화면 목록. 잠금·선택 판정 SSOT 는 서버 `_attach_row_flags`.
- 이력 탭 행에 액션·`data-link-id` 금지. STAFF 응답에 이력 데이터 0.
- 목록 캡은 병합 뒤 한 곳(`WORK_GROUP_LIMIT`)에서만.
- 폴링 경로(`fulfillment-state`·`fulfillment-progress`)는 **판정을 만들지 않는다** —
  화면 판정 SSOT 는 `_pane_context` 하나다.
- 이 화면 새 `font-size` 는 반드시 `calc(Npx * var(--wb-fs, 1))`.
- production push 는 사용자 명시 요청 시에만. 기본 푸시 대상은 항상 `deploy`.

진행 상황은 나한테 매우 상세히 물어봐.
