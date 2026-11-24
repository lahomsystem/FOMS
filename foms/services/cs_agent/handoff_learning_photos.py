"""밤 배우기가 사진 그 자체를 같이 보기 — 고르기 · 받기 · 준비 · 블록(설계서 9.2 · 9.8 — 사장님 11-24 '사진 전체 다 읽고' ·
'직원이 보낸 그림도').

:mod:`.handoff_learning` 이 묶음을 고른 뒤 **그 묶음 상담에만** 부른다(500줄 상한으로 나눴다). 예전에는 그림 읽기가 적어 둔 한
줄 설명만 보냈다 — 이제 그 사진 그 자체도 같이 보내, 직원이 사진을 보고 한 말의 까닭(기둥 · 배관 자리 같은 그 집 구조)을 배우기가
함께 읽는다.

- **고르기**: 그 상담의 채널톡 글(:func:`.full_conversation._pages` — 전체 대화와 같은 글 수 상한)에서 손님 공개 글의 파일과 공개
  직원 글(:attr:`.channel_read.DerivedMessage.is_answer`)의 파일만 모은다. 내부 메모 · 봇 · 기록 글의 파일은 읽지 않는다.
- **손님 사진**: 그림 읽기 표 줄이 얼굴로 버린 줄이거나 얼굴 탓으로 건너뛴 줄이면 받지 않는다(:data:`FACE_SKIPS`). 그 밖(읽음 ·
  꼴 · 상한 탓 건너뜀 · 줄 없음)은 다시 받아 받기 전 거르기 → 받기 → 준비(줄이기 · 얼굴 거르기 다시)를 지난다. 표 줄에 지문
  (sha256)이 있는데 다시 받은 것과 다르면 싣지 않는다(같은 사진인지 모른다).
- **직원 그림**: 표 줄이 없다 — 받기 전 거르기 → 받기 → 준비만.
- **상한**: 상담마다 손님 :data:`CUSTOMER_CAP` · 직원 :data:`STAFF_CAP` 장, 묶음 :data:`BATCH_CAP` 장(손님 사진 먼저 · 새
  사진부터), 긴 변 :data:`LONG_EDGE`. 같은 지문은 묶음에서 한 번만 싣는다(둘째부터는 표시 줄이 같은 번호를 가리킨다).
- **표시 줄**: 실은 사진은 ``▶ 사진 N (손님 · 사진 그 자체를 같이 봄) 설명`` · ``▶ 사진 N (직원 · 사진 그 자체를 같이 봄)``,
  못 실은 손님 사진은 설명이 있으면 예전처럼 ``▶ 사진 N (손님) 설명``. N 은 묶음 전체에서 하나뿐인 번호다. 설명은 그림 읽기
  표에서 :data:`SUMMARY_CHARS` 자까지(직원 화면 줄은 그대로).
- **블록(:meth:`BatchPhotos.pick`)**: 보낼 사례 글에 실제로 들어간 ``▶`` 줄의 번호만 ``사진 N`` 글 + base64 그림 · 문서 블록으로
  낸다(가림으로 빠진 사례 · 앞뒤 창 밖 사진은 나가지 않는다).
- **끄기**: 패널 '그림 읽기'가 끔 · env :data:`ENV` 가 ``0`` · 읽기 도우미 없음 · 전체 대화 끔이면 아무것도 받지 않고 예전 표시
  줄 그대로.
- **실패는 조용히**: 받기 실패 · 시간 넘김 · 준비 실패면 그 사진만 빼고 간다. 뜻밖의 예외도 예전 표시 줄로 돌아간다(배우기는
  멈추지 않는다). 바이트 · 파일 key · 주소 · 글은 로그 · 예외 글 · repr 에 싣지 않는다(수 · 코드만). 저장하지 않는다(메모리만).
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from sqlalchemy import select

from foms.services.cs_agent.full_conversation import _pages, message_cap, talk_on
from foms.services.cs_agent.image_fetch import FetchError, fetch_bytes
from foms.services.cs_agent.image_files import FileRef
from foms.services.cs_agent.image_prep import SKIP_FACE, SKIP_FACE_CHECK, SKIP_SIZE, Prepared, precheck, prepare
from foms.services.cs_agent.image_settings import MODE_OFF, image_mode
from foms.services.cs_agent.image_store import DISCARDED, SKIPPED
from foms.services.cs_agent.image_summaries import row_summary
from models import CsAgentImageRead

logger = logging.getLogger(__name__)

__all__ = [
    "BATCH_CAP", "CUSTOMER_CAP", "ENV", "FACE_SKIPS", "LONG_EDGE", "SEEN", "STAFF_CAP", "SUMMARY_CHARS", "BatchPhotos",
    "batch_photos", "photos_on",
]

#: 급히 끌 때(WORKER env) — ``0`` 이면 사진을 받지 않는다(설명 줄만 — 예전 그대로).
ENV = "FOMS_CS_LEARN_PHOTOS"
CUSTOMER_CAP, STAFF_CAP, BATCH_CAP = 12, 4, 20
#: 그림 긴 변(낮 그림 읽기는 :data:`.image_prep.LONG_EDGE` 그대로 — 밤 배우기는 사진이 많아 작게).
LONG_EDGE = 1568
#: 밤 배우기 사진 줄 설명 자 수(직원 화면 줄 :data:`.image_summaries.LINE_LIMIT` 은 그대로).
SUMMARY_CHARS = 240
#: 묶음 하나 받기 시간 상한 · 파일 하나 받기 시간 상한(초).
FETCH_BUDGET_S, FETCH_TIMEOUT_S = 120.0, 20.0
SEEN = "사진 그 자체를 같이 봄"
#: 손님 사진을 다시 받지 않는 그림 읽기 표 건너뜀 까닭(얼굴).
FACE_SKIPS = frozenset({SKIP_FACE, SKIP_FACE_CHECK})
_CUSTOMER, _STAFF = "손님", "직원"
_SHOWN = re.compile(rf"▶ 사진 (\d+) \((?:{_CUSTOMER}|{_STAFF}) · {SEEN}\)")


def photos_on(cfg: Any) -> bool:
    """사진을 같이 보내나 — 패널 '그림 읽기'가 끔이 아니고 env :data:`ENV` 가 ``0`` 이 아님."""
    return image_mode(cfg) != MODE_OFF and os.environ.get(ENV, "").strip() != "0"


class _Memo:
    """읽기 도우미 겉옷 — 이 부르기 동안 같은 글 목록 쪽은 한 번만 읽는다(사진 고르기와 전체 대화가 같은 쪽을 본다). 파일 서명
    주소는 그대로 넘긴다. 읽은 글은 이 부르기 메모리에만 있고 repr 에 없다."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader
        self._seen: dict[tuple[str, str, tuple[tuple[str, str], ...]], Any] = {}

    def __repr__(self) -> str:
        return f"_Memo(pages={len(self._seen)})"

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)

    def _get(self, brand: str, path: str, params: Mapping[str, Any], bucket: str) -> Any:
        if not path.endswith("/messages"):
            return self._reader._get(brand, path, params, bucket)  # noqa: SLF001 — 같은 패키지 읽기 도우미
        key = (brand, path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
        if key not in self._seen:
            self._seen[key] = self._reader._get(brand, path, params, bucket)  # noqa: SLF001
        return self._seen[key]


@dataclass
class _Pic:
    """사진 하나 — 상담 · 파일 정보 · 직원 그림인가 · 시간 순서 열쇠 · 표 줄(손님만) · 준비 결과 · 지문."""

    chat: str
    ref: FileRef = field(repr=False)
    staff: bool
    key: tuple[Any, str, int] = field(repr=False)
    row: Any = field(default=None, repr=False)
    ready: Optional[Prepared] = field(default=None, repr=False)
    sha: str = field(default="", repr=False)


@dataclass
class BatchPhotos:
    """한 묶음의 사진 — 상담 → (메시지 id → 표시 줄), 전체 대화를 읽을 읽기 도우미(같은 쪽 한 번만), 번호 → 실은 사진, 뺀 수
    (까닭 코드별). 바이트는 repr 에 없다."""

    marks: Mapping[str, Mapping[str, Sequence[str]]] = field(repr=False)
    reader: Any = field(default=None, repr=False)
    items: dict[int, Prepared] = field(default_factory=dict, repr=False)
    skipped: dict[str, int] = field(default_factory=dict)

    def pick(self, blocks: Sequence[Sequence[str]]) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        """보낼 사례 줄에 든 ``▶ 사진 N (… · 사진 그 자체를 같이 봄)`` 번호의 사진만 — (그림 블록, 보낸 수, 뺀 수). 실었지만
        사례 글에 안 들어간 사진(가림으로 빠진 사례 · 앞뒤 창 밖)은 ``not_shown`` 으로 센다."""
        if not self.items:
            return [], 0, dict(self.skipped)
        shown = {int(n) for n in _SHOWN.findall("\n".join(line for block in blocks for line in block))}
        out: list[dict[str, Any]] = []
        for number in sorted(shown & set(self.items)):
            item = self.items[number]
            out.append({"type": "text", "text": f"사진 {number}"})
            out.append({"type": item.kind, "source": {"type": "base64", "media_type": item.media_type,
                                                      "data": base64.standard_b64encode(item.data).decode("ascii")}})
        sent = len(out) // 2
        skipped = Counter(self.skipped)
        if len(self.items) > sent:
            skipped["not_shown"] += len(self.items) - sent
        return out, sent, dict(sorted(skipped.items()))


def _rows(session: Any, brand: str, chats: Sequence[str]) -> dict[tuple[str, str, int], Any]:
    """그 상담들의 그림 읽기 표 줄 — (상담, 메시지 id, 파일 차례) → 줄(상태 · 건너뜀 · 지문 · 결과 · 메시지 id)."""
    t = CsAgentImageRead
    stmt = (select(t.chat_id, t.message_id, t.file_index, t.state, t.skip_code, t.sha256, t.result)
            .where(t.brand == brand, t.chat_id.in_(list(chats))).order_by(t.id))
    return {(str(r.chat_id), str(r.message_id), int(r.file_index)): r for r in session.execute(stmt)}


def _face(row: Any) -> bool:
    """표 줄이 얼굴로 버린 줄 · 얼굴 탓 건너뜀인가."""
    return row is not None and (row.state == DISCARDED or (row.state == SKIPPED and row.skip_code in FACE_SKIPS))


def _gather(reader: Any, brand: str, chats: Sequence[str], cfg: Any,
            rows: Mapping[tuple[str, str, int], Any]) -> dict[str, list[_Pic]]:
    """상담마다 손님 공개 글 · 공개 직원 글의 파일(시간 순 · 글 안 차례). 글을 못 읽은 상담은 빈 목록."""
    out: dict[str, list[_Pic]] = {}
    for chat in chats:
        got = _pages(reader, brand, chat, message_cap(cfg), None, staff_files=True)
        pics: list[_Pic] = []
        for line in sorted(got[0] if got else (), key=lambda one: one.key):
            staff = line.meta.is_answer
            if not (staff or line.meta.is_customer_signal):
                continue
            for ref in line.files:
                row = None if staff else rows.get((chat, ref.message_id, ref.file_index))
                pics.append(_Pic(chat, ref, staff, (*line.key, ref.file_index), row))
        out[chat] = pics
    return out


class _Loader:
    """받기 · 준비 한 묶음 — 상한 · 시간 · 같은 지문을 센다."""

    def __init__(self, reader: Any, brand: str, cfg: Any, transport: Optional[Callable[..., Any]],
                 clock: Callable[[], float]) -> None:
        self.reader, self.brand, self.transport, self.clock = reader, brand, transport, clock
        self.page_cap = int(cfg.get("image_pdf_pages"))
        self.pdf_bytes = int(cfg.get("image_pdf_max_mb")) * 1024 * 1024
        self.deadline = clock() + FETCH_BUDGET_S
        self.skipped: Counter[str] = Counter()
        self.per_chat: Counter[tuple[str, bool]] = Counter()
        self.loaded = 0
        self.shas: set[str] = set()

    def _code(self, pic: _Pic) -> Optional[str]:
        """받기 전에 뺄 까닭(얼굴 줄 · 상한 · 시간) — 없으면 ``None``."""
        if not pic.staff and _face(pic.row):
            return "face"
        if self.per_chat[(pic.chat, pic.staff)] >= (STAFF_CAP if pic.staff else CUSTOMER_CAP):
            return "staff_cap" if pic.staff else "customer_cap"
        if self.loaded >= BATCH_CAP:
            return "batch_cap"
        return "no_time" if self.clock() >= self.deadline else precheck(pic.ref, pdf_max_bytes=self.pdf_bytes)

    def _fetch(self, pic: _Pic) -> Prepared | str:
        """받기 → 준비. 실패면 까닭 코드."""
        try:
            data = fetch_bytes(self.reader, self.brand, pic.chat, pic.ref, transport=self.transport,
                               timeout=max(1.0, min(FETCH_TIMEOUT_S, self.deadline - self.clock())))
        except FetchError as exc:
            return SKIP_SIZE if exc.args == ("too_big",) else "fetch_failed"
        ready = prepare(pic.ref, data, page_cap=self.page_cap, pdf_max_bytes=self.pdf_bytes, long_edge=LONG_EDGE)
        del data
        return ready

    def load(self, pic: _Pic) -> None:
        """사진 하나를 싣거나(``ready`` · ``sha``) 까닭을 센다. 예외는 그 사진만 뺀다(종류 이름만 센다)."""
        code = self._code(pic)
        if code is None:
            try:
                got = self._fetch(pic)
            except Exception as exc:  # noqa: BLE001 — 사진 하나 실패가 배우기를 멈추지 않는다(글 · 바이트는 남기지 않는다)
                got = f"error_{type(exc).__name__}"[:32]
                logger.warning("[CS 넘김 학습] 사진 하나 받기 · 준비 실패 — 그 사진만 뺀다 error=%s", type(exc).__name__)
            if isinstance(got, str):
                code = got
            elif pic.row is not None and pic.row.sha256 and pic.row.sha256 != got.sha256:
                code = "sha_mismatch"
            elif got.sha256 in self.shas:  # 같은 그림 — 한 번만 싣고 표시 줄이 같은 번호를 가리킨다
                pic.sha = got.sha256
                return
            else:
                pic.ready, pic.sha = got, got.sha256
                self.shas.add(got.sha256)
                self.per_chat[(pic.chat, pic.staff)] += 1
                self.loaded += 1
                return
        self.skipped[code] += 1


def _number(by_chat: Mapping[str, list[_Pic]], rows: Mapping[tuple[str, str, int], Any],
            ) -> tuple[dict[str, dict[str, list[str]]], dict[int, Prepared]]:
    """번호 매기기(묶음 전체에서 하나 — 상담 차례 · 대화 순서) → (표시 줄, 번호 → 실은 사진). 대화에 없는 표 줄의 설명은 그
    메시지 id 로 둔다(전체 대화 펴기가 질문 뒤 · 끝에 놓는다)."""
    marks: dict[str, dict[str, list[str]]] = {}
    items: dict[int, Prepared] = {}
    numbers: dict[str, int] = {}
    count = 0
    for chat, pics in by_chat.items():
        mine = marks.setdefault(chat, {})
        seen: set[tuple[str, int]] = set()
        for pic in pics:
            seen.add((pic.ref.message_id, pic.ref.file_index))
            line = row_summary(pic.row, SUMMARY_CHARS) if pic.row is not None else None
            about = f" {line.text}" if line is not None else ""
            if pic.sha:
                if pic.sha not in numbers:
                    count += 1
                    numbers[pic.sha] = count
                if pic.ready is not None:
                    items[numbers[pic.sha]] = pic.ready
                who = _STAFF if pic.staff else _CUSTOMER
                text = f"▶ 사진 {numbers[pic.sha]} ({who} · {SEEN}){about}"
            elif about:
                count += 1
                text = f"▶ 사진 {count} ({_CUSTOMER}){about}"
            else:
                continue
            mine.setdefault(pic.ref.message_id, []).append(text)
        for (row_chat, message, index), row in rows.items():
            line = row_summary(row, SUMMARY_CHARS) if row_chat == chat and (message, index) not in seen else None
            if line is not None:
                count += 1
                mine.setdefault(message, []).append(f"▶ 사진 {count} ({_CUSTOMER}) {line.text}")
    return {chat: lines for chat, lines in marks.items() if lines}, items


def batch_photos(session: Any, reader: Any, cfg: Any, cases: Sequence[Mapping[str, Any]],
                 base: Mapping[str, Mapping[str, Sequence[str]]], *, brand: str,
                 transport: Optional[Callable[..., Any]] = None,
                 clock: Callable[[], float] = time.monotonic) -> BatchPhotos:
    """이번 묶음 상담들의 사진(모듈 설명). 끔 · 읽기 도우미 없음 · 뜻밖의 예외면 ``base``(예전 표시 줄 —
    :func:`.handoff_learning._photo_marks`) 그대로 · 받기 없음. 커밋한다(채널톡 읽기 동안 읽기 트랜잭션을 열어 두지 않는다)."""
    chats = [chat for chat in dict.fromkeys(str(case.get("chat_id") or "") for case in cases) if chat]
    if reader is None or not chats or not talk_on(cfg) or not photos_on(cfg):
        return BatchPhotos(marks=base, reader=reader)
    try:
        rows = _rows(session, brand, chats)
        session.commit()
        memo = _Memo(reader)
        by_chat = _gather(memo, brand, chats, cfg, rows)
        loader = _Loader(memo, brand, cfg, transport, clock)
        firsts = [pic for pics in by_chat.values() for pic in pics]
        for staff in (False, True):  # 손님 사진 먼저 · 새 사진부터
            for pic in sorted((p for p in firsts if p.staff == staff), key=lambda p: p.key, reverse=True):
                loader.load(pic)
        marks, items = _number(by_chat, rows)
    except Exception as exc:  # noqa: BLE001 — 사진이 배우기를 멈추지 않는다(예외 종류만 남긴다)
        session.rollback()
        logger.warning("[CS 넘김 학습] 사진 고르기 실패 — 설명 줄만 error=%s", type(exc).__name__)
        return BatchPhotos(marks=base, reader=reader, skipped={"error": 1})
    logger.info("[CS 넘김 학습] 사진 chats=%d loaded=%d skipped=%s", len(chats), len(items), dict(loader.skipped))
    return BatchPhotos(marks=marks, reader=memo, items=items, skipped=dict(loader.skipped))
