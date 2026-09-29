"""스토리지 파일 삭제 유예 정책 — 첨부 삭제·전달 취소가 같은 값을 쓴다(2b).

api 레이어(첨부 삭제 라우트·도면 전달 취소 라우트) 양쪽이 이 상수를 맨 위에서 import 한다.
라우트 모듈끼리 서로 import 하지 않게 서비스 쪽에 둔다(레이어 의존 래칫).
"""
from __future__ import annotations

import datetime

__all__ = ["ATTACHMENT_PURGE_GRACE"]

#: tombstone 후 R2 blob 을 실제로 지우기까지의 유예. 이 기간 안에는 복구 API 가 outbox
#: 예약을 취소하고 첨부를 되살릴 수 있다(유예가 지나 worker 가 집어가면 복구 불가).
#: 도면 전달 취소의 회수 파일 삭제 예약도 같은 유예를 쓴다 — 그 안에 다시 쓰이면
#: STORAGE_DELETE 핸들러가 건너뛴다.
ATTACHMENT_PURGE_GRACE = datetime.timedelta(days=7)
