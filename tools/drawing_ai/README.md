# 도면 마법사 그림 종류 분류기 — 다시 가르치기 도구

설계 정본: `docs/plans/2026-10-23-drawing-part-label-feedback-spec.md` §3.5 · §3.7

도면팀이 마법사에서 고친 그림 종류(정면·내부, 입체·도어 …)를 모아 브라우저 분류기(`static/js/drawing/part-head.json`)를 다시 가르친다. 지금 판의 가중치에서 출발하고, 고정 시험 묶음에서 나빠지지 않을 때만 새 판을 낸다.

## 학습 요약으로 가르치기(운영 DB · 그림 없이)

AI 도면팀원 학습 요약(`GET /api/drawing-agent/digest`, 읽기 전용 토큰)에는 브라우저가 낸 그림 특징과 사람 이름표가 있다.
`fetch_digest.py fetch` 로 받고 `fetch_digest.py to-retrain` 으로 바꾸면 아래 3단계 `train` 이 그대로 읽는다 —
collect · embed 를 건너뛴다(운영 DB · 저장소 자격이 필요 없다). 순서 정본: `docs/research/drawing-agent/AGENT.md`.

## 언제 돌리나

- 처음엔 손으로 한 달에 한 번. 고친 기록(사람이 AI 짐작과 다르게 고른 것)이 100건 넘을 때만 가르친다(`train` 이 스스로 멈춘다).
- **운영 DB·저장소를 읽으므로 돌릴 때마다 사용자 허락을 받는다.** DB 는 읽기 전용으로 접속하고, 저장소는 GetObject 만 쓴다.

## 순서

작업 폴더(`<폴더>`)는 저장소 밖(예: 세션 스크래치)에 두고, 다 쓰면 지운다.

1. **collect** — FOMS 파이썬(psycopg·boto3 가 있는 환경)
   ```
   RETRAIN_DB_URL=<운영 DB 주소> R2_ACCOUNT_ID=… R2_ACCESS_KEY_ID=… R2_SECRET_ACCESS_KEY=… R2_BUCKET_NAME=… \
     python tools/drawing_ai/retrain_head.py collect --out <폴더> --expect-host <운영 DB 호스트>
   ```
   - 자격은 환경 변수로만 넘긴다(명령줄·로그에 남기지 않는다). Railway 변수는 저장소 밖 임시 폴더에서 `railway variables --service <서비스> --kv` 로 받아 이 명령의 환경 변수로만 쓰고, 받은 파일은 바로 지운다. 끝나면 링크를 풀고 `railway status` 로 연결이 없는지 본다.
   - 결과: `manifest.jsonl`(그림별 정답·무게·제품 종류), `summary.json`(수·헷갈림 표), `imgs/`(그림, 임시).
   - 로컬 개발 DB 로 시험할 때는 `--local-storage static/uploads`.
2. **embed** — 도구용 가상환경(onnxruntime·numpy·Pillow). FOMS 서버 환경에는 onnxruntime 을 넣지 않는다(numpy 1.26.4 고정과 충돌).
   ```
   <venv 파이썬> tools/drawing_ai/retrain_head.py embed --data <폴더> [--model <받아 둔 model_quantized.onnx>]
   ```
   - 모델은 `part-head.json` 의 주소(Hugging Face 커밋 고정)에서 받고 sha256 을 맞춰 본다.
   - 특징(`features.npy`·`feature_keys.json`)을 쓴 뒤 `imgs/` 를 지운다.
3. **train** — numpy 만(어느 환경이든)
   ```
   python tools/drawing_ai/retrain_head.py train --data <폴더> --out <폴더>/part-head-h2.json
   ```
   - 결과: `report.md`(판 비교표·판정·헷갈림 표), `report.json`, 판정을 통과하면 새 판 파일.
   - 판정: 시험 그림 30장 이상 · 전체와 제품별(10장 이상) 정확도가 지금 판 이상 · 주방은 1%p 이상 오름.
   - 종료 코드: 0 통과 · 2 입력 부족(고친 기록 100건 미만 등) · 3 판정 불통과.
   - 새 분류(탑뷰 · 사이드뷰, 2026-10-28): 지금 판이 모르는 분류는 사람 기록이 `--min-new`(기본 20)장 넘을 때 새 줄로 더한다
     (0 에서 출발 · 처음 치우침은 지금 판의 가장 낮은 값). 모자라면 그 기록은 빼고 다음에 — 장수는 `report.json` `new_counts`.

## 새 판으로 바꾸기

도구는 저장소 파일을 바꾸지 않는다. 판정을 통과한 새 판을 쓰려면 보통 코드 변경으로 한다.

1. 새 판 파일을 `static/js/drawing/part-head.json` 에 덮어쓴다.
2. `templates/drawing/wizard.html` 의 `data-head-url` 핀(`?v=h2-YYYYMMDD`)을 올린다.
3. `tests/domains/test_drawing_part_ai_contract.py` 를 돌리고, 평소처럼 커밋·푸시·스테이징 확인.

## 정답 무게

| 기록 | 무게 |
|---|---|
| 사람이 고르거나 고친 이름표(`src: user`) | 1 |
| 사람이 손대지 않고 전달한 AI 이름표(전달 때 버전 스냅샷에 AI 이름표로 남은 것) | 0.5 |
| 미분류 · 이름표 없음 · 전달하지 않은 AI 이름표 | 쓰지 않음 |

고정 시험 묶음은 주문 번호로 정한 20% 주문의 사람 확인 그림이다. 그 주문의 그림은 가르치는 데 쓰지 않는다.
