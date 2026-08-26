# T6 — 채널톡 연동 상태점검이 "워커 못 셈"을 "워커 없음"으로 읽어 503 을 낸다

작업 트리: `c:\tmp\nvfix`.
**너의 파일 경계는 `foms/api/channel/channel_integration.py` 와 그 테스트 둘뿐이다.**
다른 에이전트가 같은 트리의 다른 파일을 동시에 고치고 있다. 경계 밖은 **읽기만** 해라.

## 배경 — 오늘 이미 두 번 고친 같은 뿌리

`get_rq_worker_count` 는 `Worker.count` → `Worker.all` 2단 fallback 이 **둘 다 실패해도 0** 을
돌려준다. 그래서 "워커가 진짜 0대" 와 "Redis 가 일시적으로 못 세게 했다" 가 같은 값이 된다.
ping 은 통했는데 그 직후 Worker 조회만 실패하는 짧은 창이 실재한다.

그래서 `foms/services/jobs/queue.py` 의 `get_rq_runtime_status()` 가 이제
**`worker_count_known`** 을 함께 싣는다. False 면 `worker_count` 의 0 은 **"모른다"** 는 뜻이다.
`_probe_rq_workers` 와 `get_rq_runtime_status` 의 docstring 을 먼저 읽어라.

같은 규율로 이미 고친 자리 둘 — **읽고 같은 모양을 따라라**:
- `foms/web/admin/naver_ingest.py` `naver_ingest_run_now` (확실히 0대일 때만 막는다)
- `foms/services/notifications/push_sender.py` `enqueue_push_for_notification`

## 고칠 것

`foms/api/channel/channel_integration.py:931-950` 근처 `_evaluate_channel_readiness()`:

```python
queue_runtime = get_rq_runtime_status()
queue_state = queue_runtime['state']
rq_worker_count = queue_runtime['worker_count']
...
elif (flags['push'] or flags['webhook']) and rq_worker_count < 1:
    readiness = 'fail'
```

**문제**: `worker_count_known` 을 안 본다. Redis 가 딱 한 번 딸꾹질하면 채널톡 연동이
**고장 난 것처럼**(`fail`, HTTP 503) 보인다 — 실제로는 멀쩡하다.

**고치는 방향**: 확실히 0대일 때만 `fail`. 못 셌으면 그 사실을 **숨기지 말고** 응답에 실어라
(`worker_count` 0 을 그대로 두면 읽는 사람이 "0대"로 오해한다). readiness 등급을 무엇으로
할지(`fail` 아님 / 별도 등급 / 기존 등급 유지 + 필드 추가)는 **네가 이 파일의 기존 등급 체계를
읽고 판단**하고 근거를 보고에 써라 — 여기서 중요한 것은 **"모른다"를 "없다"로 단정하지 않는 것**이다.

## 하지 말 것

- `queue.py` 수정 금지(이미 끝났다). 시그니처·`__all__` 변경 금지 —
  `tests/contracts/runtime/foms_namespace_surface_tests.py` 가 `__all__` 을 정확히 잠근다.
- push_sender·naver_ingest 수정 금지(이미 끝났다).
- 커밋·푸시 금지.

## 완료 기준

```bash
cd /c/tmp/nvfix
python -c "import app; print('APP_OK')"
export PYTHONIOENCODING=utf-8
python -m pytest tests/domains/test_channel_integration_smoke.py -q
```

- 전량 통과
- **신규 단언 2건 이상**:
  ① 못 셌을 때(`worker_count_known=False`) **`fail` 로 떨어지지 않는다** + 모른다는 사실이 응답에 있다
  ② 진짜 0대일 때는 **예전 그대로** `fail` 이다(좁힌 판정이 못을 빼면 안 된다)
- 테스트 docstring 은 한국어로, **왜** 필요한지 적어라

## 보고 형식

변경 파일 · readiness 등급을 무엇으로 정했는지와 근거 · 위 명령의 실제 출력 마지막 줄.
