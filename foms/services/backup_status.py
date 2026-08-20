"""오프사이트 백업 심박 저장·판독 (RESTORE-GUI-01 F7).

**왜 푸시인가**: 상황판이 백업 보관소를 직접 들여다보려면 웹 앱이 백업 버킷 열쇠나 Railway
계정 토큰을 들고 있어야 한다. 웹 앱이 털렸을 때 백업까지 함께 열리는 구조는 백업의 목적을
지운다. 그래서 백업 쪽(GitHub Actions)이 **성공했을 때만** 서명된 심박을 보내고, 앱은
그 기록만 읽는다 — 앱은 백업 보관소에 대한 어떤 권한도 갖지 않는다.

**침묵 감지**: 실패 메일은 워크플로가 *돌았을 때만* 온다. 스케줄이 꺼지거나 저장소가
비활성화되면 아무 신호도 오지 않는다(2026-08-13~18 실패 6일을 아무도 몰랐던 그 침묵).
상황판은 "마지막 성공 이후 몇 시간"을 계산하므로 **실행되지 않는 상태까지** 빨강으로 잡는다.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import os
from typing import Any

from foms.services.datetime_kst import now_utc_naive
from models import SystemSetting

__all__ = [
    "HEARTBEAT_SETTING_KEY",
    "STALE_AFTER_HOURS",
    "evaluate_backup_status",
    "load_heartbeat",
    "record_heartbeat",
    "verify_heartbeat_signature",
]

#: 심박이 저장되는 설정 키.
HEARTBEAT_SETTING_KEY = "ops.backup.latest"

#: 이 시간을 넘겨 성공이 없으면 빨강. 일 1회(24시간) 주기에 지연 여유를 더한 값이다.
STALE_AFTER_HOURS = 30

#: 서명 헤더(ChannelTalk 웹훅과 같은 방식 — HMAC-SHA256 over raw body).
SIGNATURE_HEADER = "X-FOMS-Backup-Signature"


def _secret() -> str:
    """심박 서명 공유 비밀(미설정이면 빈 문자열 — 그때는 어떤 요청도 통과하지 못한다)."""
    return (os.environ.get("FOMS_BACKUP_HEARTBEAT_SECRET") or "").strip()


def verify_heartbeat_signature(raw_body: bytes, signature: str) -> bool:
    """본문 HMAC 서명을 검증한다.

    비밀이 설정돼 있지 않으면 **항상 거짓**이다 — 미설정을 "인증 없음"으로 열어 두면
    누구나 "백업 정상"을 써넣어 상황판을 속일 수 있다(fail-closed).

    :param raw_body: 요청 원문 바이트.
    :param signature: 요청이 보낸 hex 서명.
    :return: 일치하면 ``True``.
    """
    secret = _secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def record_heartbeat(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """성공 심박을 설정 행에 덮어쓴다(커밋은 호출자 소유).

    최신 1건만 남긴다 — 상황판이 묻는 것은 "마지막 성공이 언제인가" 하나다.

    :param session: DB 세션.
    :param payload: 백업이 보낸 값(``finished_at``·``key``·``size_bytes``·``sha256``·``toc_entries``).
    :return: 저장된 값(수신 시각 ``received_at`` 추가).
    """
    stored = {
        "finished_at": payload.get("finished_at"),
        "key": payload.get("key"),
        "size_bytes": payload.get("size_bytes"),
        "sha256": payload.get("sha256"),
        "toc_entries": payload.get("toc_entries"),
        # 보낸 쪽 시계를 믿지 않기 위해 받은 시각도 함께 남긴다(naive=UTC 규약).
        "received_at": now_utc_naive().isoformat(timespec="seconds"),
    }
    row = session.query(SystemSetting).filter(
        SystemSetting.setting_key == HEARTBEAT_SETTING_KEY
    ).one_or_none()
    if row is None:
        session.add(SystemSetting(
            setting_key=HEARTBEAT_SETTING_KEY,
            setting_value=stored,
            description="오프사이트 백업 마지막 성공 심박(foms-ops-backup 이 보낸다)",
        ))
    else:
        row.setting_value = stored
    return stored


def load_heartbeat(session: Any) -> dict[str, Any] | None:
    """저장된 심박을 읽는다(없으면 ``None``)."""
    row = session.query(SystemSetting).filter(
        SystemSetting.setting_key == HEARTBEAT_SETTING_KEY
    ).one_or_none()
    value = row.setting_value if row else None
    return value if isinstance(value, dict) else None


def _parse(stamp: Any) -> datetime.datetime | None:
    """ISO 문자열을 naive UTC datetime 으로(파싱 실패는 ``None``)."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(stamp.replace("Z", ""))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def evaluate_backup_status(
    heartbeat: dict[str, Any] | None,
    *,
    now: datetime.datetime | None = None,
) -> dict[str, Any]:
    """심박으로 상황판 판정을 만든다.

    심박이 **아예 없는** 경우도 빨강이다 — "한 번도 성공한 적 없음"은 정상이 아니다
    (실제로 2026-08-13~19 가 그 상태였다).

    :param heartbeat: :func:`load_heartbeat` 결과.
    :param now: 판정 기준 시각(테스트 주입용, 기본 현재 UTC).
    :return: ``{'state', 'headline', 'age_hours', 'heartbeat'}``.
        ``state`` 는 ``ok``·``stale``·``missing``.
    """
    now = now or now_utc_naive()
    if not heartbeat:
        return {
            "state": "missing",
            "headline": "성공 기록이 없습니다 — 백업이 한 번도 성공하지 않았거나 심박이 오지 않습니다.",
            "age_hours": None,
            "heartbeat": None,
        }

    # 보낸 쪽 시계보다 받은 시각을 우선한다(외부 시계는 믿지 않는다).
    stamp = _parse(heartbeat.get("received_at")) or _parse(heartbeat.get("finished_at"))
    if stamp is None:
        return {
            "state": "missing",
            "headline": "심박에 시각이 없습니다 — 기록이 손상됐습니다.",
            "age_hours": None,
            "heartbeat": heartbeat,
        }

    age_hours = (now - stamp).total_seconds() / 3600.0
    if age_hours > STALE_AFTER_HOURS:
        return {
            "state": "stale",
            "headline": f"마지막 성공이 {age_hours:.1f}시간 전입니다 (기준 {STALE_AFTER_HOURS}시간).",
            "age_hours": age_hours,
            "heartbeat": heartbeat,
        }
    return {
        "state": "ok",
        "headline": f"마지막 성공 {age_hours:.1f}시간 전.",
        "age_hours": age_hours,
        "heartbeat": heartbeat,
    }
