**C 네이버 후속 4차 — 운영 승격(4건) → T8 배선 완성 → 남은 검증 3건.

작업 위치 `c:\tmp\nvfix` (브랜치 `tmp/naver-fix-20260825`)
원장 `docs/plans/2026-08-26-naver-followup-multiagent-ledger.md` 의 **"3차 세션" 절부터 끝까지**.
T8 설계서 `docs/specs/2026-08-27-naver-return-send_SPEC.md`.

## 지금 상태 (2026-08-27 종료 시점)

- **deploy `a53acb1d`** — **CI 4/4 green** (FOMS CI · Harness CI · PG Lane · perf-gate,
  `gh run list --commit <SHA>` 로 커밋별 전 워크플로 확인).
- **production `14c3fc0e`** — 내 몫은 `aa90b3a1` 까지고 그 위에 **타 세션 채널톡 승격(PR #167)**이 얹혔다.
- 오늘 운영 승격 **3회**: PR **#163**(반품 축·다시 읽기·이전 주문 구분·낱말) ·
  **#164**(확인 완료 게이트·툴팁) · **#165**(운영 승격 CI 구멍).

**운영 CI 구멍이 닫혔다 — 이게 이번에 제일 크다.**
`ci.yml`·`harness-ci.yml` 의 `pull_request.branches` 에 `production` 이 들어갔다.
**다음 승격 PR 부터 본 스위트(5,300+)와 하네스 계약이 붙는다.** 실측 메커니즘:
`pull_request` 는 **head 브랜치**의 워크플로 파일을 쓴다(base 아니다) — 그래서 PR #163·#164 는
체크 2종, #165 는 4종이 붙었다. 켜자마자 `harness` red 1건이 드러나 근본 수정했다.

## 1순위 — 운영 승격 (4건, 코드 3 + 문서)

`git merge-base --is-ancestor <sha> origin/production` 으로 확인한 **운영 미반영분**:

```
9ef4f482  회수지 우편번호 렌더 + '수집됨(생성 전)'·'생성됨' 라벨
deffb9b7  네이버 클레임·앱만료 알림이 휴대폰까지 — 웹푸시 enqueue 배선
320454d7  T8-S1 판매자 반품 접수 본체(가드·화이트리스트·멱등)
394fffce  T8 부분 발송 집에서 미발송 건까지 보내던 결함 수정 (CEO 지적)
```
(`66bed323` guard_policy 테스트 수정은 **SHA 는 다르지만 내용이 이미 운영에 있다** — PR #165 로 갔다.)

**이번 승격은 전과 다르다 — PR 에 본 스위트가 붙는다.** 그래도 승격 트리에서 직접 돌리는 것을
생략하지 마라(cherry-pick 병합이 만든 red 를 지난 두 번 다 그렇게 잡았다):
`APP_OK` · `-k naver` · `tests/contracts tests/domains` · `pre_push_smoke`.

승격 트리 함정(원장·메모리 기록): AI_STATUS 상단 40줄 **4,000자 예산**(병합하면 넘긴다) ·
인벤토리 3종 · 자산 `?v` 핀. 마이그레이션은 이번에도 **0건**.

## 2순위 — T8 배선 완성 (**Q1 이 닫힌 뒤에만**)

서버측 본체는 이미 있다(`fulfillment.request_return` · `client.request_return_product_order` ·
`RETURN_REASONS` · `RETURN_COLLECT_METHOD`). **호출자가 테스트 밖에 0곳**이라 지금은 도달 불가다.

**Q1 (유일한 착수 차단)**: 커머스API센터 → [애플리케이션 관리] → 우리 앱 → [API 그룹] 에서
`주문 판매자` 행을 편다. (a) 리소스 유형이 `모든 리소스 유형` 인가 (b) 이름·설명에 **'반품'이
포함**되는가 (c) 만료일. **사용자가 화면을 봐야 한다.**

Q1 이 열리면 얹을 것 — 설계서 §4 의 R5~R8:
- R5 큐: `enqueue_naver_return` + `run_naver_return_task` (`enqueue_naver_fulfillment:208` 본뜬다)
- R6 라우트: `POST /admin/naver-ingest/<link_id>/return` — **신규 mutation 계약 4종 등재 필수**
  (policy manifest · write guard manifest · audit coverage inventory · 감사 라벨)
- R7 화면: pane 버튼 + **확인 모달 필수**(불가역 · 접수 후 API 정정 불가 · 승인은 사람이)
- R8 진행 표시: `_fulfillment_state.rev` 지문에 `return.requested_at` 추가 — **새 엔드포인트 0**
  (3차 세션에서 R5~R7 과 묶어 미룬 것이다. 빠뜨린 게 아니다)

Q2~Q5(사전조건·`returnReason` 범례·`requestChannel` 실값·업무 규칙)는 설계서 §6 에 있다.

## 3순위 — 남은 검증 3건 (전부 사용자 손이 필요하다)

1. **`railway login`** — 세션 중 인증이 만료됐다. 이것 때문에 **운영 코호트 안 화면 확인**
   (워크벤치가 열리는가 · 다시 읽기 버튼이 보이는가)을 못 했다. 라우트가 사는 것까지만 확인했다
   (없는 경로는 404, 워크벤치 3경로는 로그인으로 302).
2. **웹푸시 실도착** — enqueue 호출까지만 잠갔다. `FOMS_WEB_PUSH_ENABLED` 가 꺼져 있으면
   `flag_off` 로 skip 된다. **켤지 여부는 사용자 판단**이고, 켠 뒤 스테이징에서 1건 실도착 확인이 남는다.
3. **① 반증축 4개** — "열려야 하는 집" 5개 중 1개(link 25)만 확인했다. 나머지
   `link_id` **195·258·311·353**. 코호트를 열 일이 생기면 같이 봐라.

## 셸 함정 (3차 세션에서 실제로 걸렸다)

턴이 새로 시작되면 cwd 가 `c:\DEV\FOMS` 로 **조용히 리셋**된다. 검증이 엉뚱한 트리에서 돌아
**가짜 초록**이 나온다. 매 턴 첫 명령은 `cd /c/tmp/nvfix && pwd && …`.

heredoc 함정도 하나: `<<'PY'` 로 감싸도 **백슬래시가 먹혔다**(`"base\n"` 이 진짜 줄바꿈이 됐다).
긴 파이썬은 Write 도구로 파일에 쓰고 실행해라.

## 규율 (3차 세션이 비싸게 배운 것)

**"전수 확인"이 양성 후보 전수면 전수가 아니다.** 3차 세션에서 두 번 걸렸다:
- ② 반품 진행 줄 검증이 `return` 있는 33건만 돌고 나머지 311건을 안 열어,
  `cancel` 만 있는 **50건에 `반품 진행` 줄이 뜨던 결함**을 못 봤다(CEO 가 잡았다).
- 그걸 배우고도 **내가 쓴 T8 테스트 9건이 전부 집당 1건짜리**라 부분 발송 형태를 한 번도
  안 만들었고, **미발송 건에 불가역 반품이 나가는 결함**을 또 놓쳤다(CEO 가 또 잡았다).

→ 검증 스크립트가 `for x in <후보목록>` 이면 멈춰라. **전체를 돌고 기대값으로 분류**해라:
양성 기대 N / 음성 기대 M / 어긋남. 어긋남 0 까지 출력해야 "전수"다.
**혼합 사례**(한 집에 나간 것과 안 나간 것)를 반드시 만들어라.

**화면 스캔은 실패 경로 문구를 못 본다** — 그 상태를 만들지 않으면 영영 안 보인다.
낱말 치환 완료 판정은 **화면이 아니라 소스**에서 센다(3차 세션 ④ 정정).

서브에이전트 보고는 주장일 뿐 — **diff 직접 확인 + 테스트 직접 실행** 후에만 커밋.
멀티에이전트는 **파일 경계를 브리프에 명시**(3차 세션은 `tasks.py` 독점 / `templates` 독점으로
갈라 겹침 0이었다). 리뷰·설계 결과는 **받는 즉시 원장에**.
공유 워킹트리라 커밋은 항상 `git commit -F <msg> -- <경로>`.

## 알고 있는 사각 (원장 §CEO 리뷰 2차에 전량)

- **웹푸시 중복 방지는 워커 동시성 1 전제다.** `notified_status` 는 알림 row 중복만 막고
  push enqueue 중복은 못 막으며 `_TERMINAL_STATUSES` 에 `PUSH_ATTEMPTED` 가 없다.
  **스케일아웃이 결정 게이트**다.
- **AST 단언은 우회된다** — `"RETURN_" + "DESIGNATED"` 면 통과한다. 심층 방어일 뿐이고
  진짜 보증은 `RETURN_COLLECT_METHOD` 상수 1값 + client 가 그 값만 body 에 싣는 것이다.
- `returnInfo`·`exchange` 블록은 **여전히 미관측**(`return` 33건만 실물). `COLLECTING`·
  `COLLECT_DONE` 진행 중 반품도 못 봤다 — 관측분은 전부 `RETURN_DONE`.
- `returnReason` **전체 범례 미확인** — 목록 밖 코드는 안 보낸다(불가역 경로에서 400 을 받아
  보고 배우지 않는다).
- T8 SPEC 의 "판매자 접수 24/33" 을 업무량 근거로 쓰지 마라 — 그 33건은 접수→완료
  median 60초·min 16초라 **시험 거래로 보인다**.
