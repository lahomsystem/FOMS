# T1 — push 알림이 Redis 일시 오류에 "미보장" 으로 떨어진다

작업 트리: `c:\tmp\nvfix` (여기서만 편집한다)

## 배경 — 이미 고친 같은 뿌리

오늘 `foms/services/jobs/queue.py` 를 고쳤다. 요지:

- `get_rq_worker_count` 는 `Worker.count` → `Worker.all` 2단 fallback 이 **둘 다 실패해도 0** 을
  돌려준다. 그래서 "워커가 진짜 0대" 와 "Redis 가 일시적으로 못 세게 했다" 가 같은 값이 된다.
- ping 은 통했는데 그 직후 Worker 조회만 실패하는 짧은 창이 실재한다.
- 그래서 `_probe_rq_workers(q) -> tuple[int, bool]` 을 만들었고,
  `get_rq_runtime_status()` 가 이제 **`worker_count_known`** 을 함께 싣는다.
  `worker_count_known` 이 False 면 `worker_count` 의 0 은 **"모른다"** 는 뜻이지 "0대" 가 아니다.

`foms/services/jobs/queue.py` 의 `_probe_rq_workers` · `get_rq_runtime_status` docstring 을 먼저 읽어라.

## 고칠 것

`foms/services/notifications/push_sender.py:429-440` 근처:

```python
q = get_rq_queue()
status = get_rq_runtime_status()
if q is None or int(status.get("worker_count", 0) or 0) == 0:
    _mark_queue_unavailable(db, int(notification_id))
    db.commit()
    return {"enqueued": False, "reason": "queue_unavailable"}
```

**문제**: 워커 수를 *못 센* 경우에도 `worker_count == 0` 이라, 큐가 멀쩡한데 알림이
`queue_unavailable` 로 표기되고 **아예 넣어 보지도 않는다**. 사용자에게 갈 알림 하나가
Redis 의 짧은 딸꾹질 때문에 조용히 사라진다.

**고치는 방향** (naver `지금 수집` 라우트와 **같은 규율**):
`worker_count_known` 이 True 이고 `worker_count == 0` 일 때만 "워커 없음" 으로 막는다.
못 셌으면 **막지 않고 그대로 enqueue 한다** — 진짜로 큐가 죽었다면 아래 `q.enqueue` 가
예외를 내고 기존 `except` 가 같은 `queue_unavailable` 로 정확히 처리한다(자기교정).

같은 판정을 쓰는 자리가 더 있는지 `worker_count` 로 grep 해서 확인하고, 있으면 보고에 적어라
(`foms/api/notifications/push.py` 의 진단 응답은 값을 그대로 보여주는 자리라 판정이 아니다 —
거기는 건드리지 말고, 다만 `worker_count_known` 을 함께 실어 주는 게 맞다고 판단하면 그 근거를
보고에 쓰고 실제로 실어라).

## 하지 말 것

- `queue.py` 재수정 금지(이미 끝났다).
- 시그니처·`__all__` 변경 금지 — `tests/contracts/runtime/foms_namespace_surface_tests.py` 가
  `queue.py` 의 `__all__` 을 **정확히** 잠그고 있다.
- 커밋·푸시 금지.

## 완료 기준 (이걸로 판정한다)

```bash
cd /c/tmp/nvfix
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_push_sender.py tests/domains/test_jobs_queue_failopen.py tests/domains/test_channel_integration_smoke.py -q
```

- 위 3개 전량 통과
- **신규 단언 2건 이상**:
  ① 못 셌을 때(`worker_count_known=False`) **enqueue 를 시도한다**(미보장으로 떨어지지 않는다)
  ② 진짜 0대일 때는 **예전 그대로** 미보장이다(좁힌 판정이 못을 빼면 안 된다)
- 테스트 docstring 에 **왜** 이 단언이 필요한지 한국어로 적어라(이 저장소 관례다 — 옆 테스트들을 보라)

## 보고 형식

변경 파일 목록 · 각 파일에서 바꾼 것 1줄 요약 · 위 명령의 실제 출력 마지막 줄 ·
grep 으로 찾은 같은 성질의 다른 자리(있으면).
