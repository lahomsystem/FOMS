"""공휴일 캐시 파일은 **원자적으로** 만들어져야 한다 (2026-09-06).

왜 이 계약이 있는가
-------------------
`data/holidays_kr_<year>.json` 은 저장소에 없다(`.gitignore:164` — 저장소에는
2025·2026 두 해만 우연히 추적된다). 그래서 CI 는 테스트가 처음 참조하는 연도를
**런타임에 만든다**. 그런데 CI 는 pytest-xdist 를 `-n auto --dist loadfile` 로 돌리고,
워커는 별도 프로세스지만 **파일시스템은 하나**다.

예전 구현은 대상 경로에 곧바로 `open("w")` 했다. 그 호출은 즉시 파일을 비우고
그 다음에 내용을 채운다. 그 사이 창에서 다른 워커가 같은 파일을 읽으면 **빈 문자열**을
파싱해 터진다:

    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

2026-09-05 `0c66f6d61` CI 에서 `test_production_kpi_slim_equals_full` 이 그렇게 1회
빨강이 됐다(같은 커밋 rerun 은 초록). 미래 날짜(`2099-01-01`)를 쓰는 테스트 파일이
셋이라, 세 워커가 같은 파일을 동시에 만들려 든 것이다.

무엇을 고정하는가
-----------------
쓰는 도중 그 경로를 읽는 사람이 보는 것은 **언제나** 둘 중 하나여야 한다:
파일이 아직 없거나, 완결된 JSON. 반쪽 파일은 없어야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from foms.services.common import business_calendar


@pytest.fixture()
def sandbox_data_dir(tmp_path, monkeypatch):
    """`DATA_DIR` 을 임시 경로로 돌린다 — 저장소 `data/` 를 건드리지 않는다."""
    monkeypatch.setattr(business_calendar, "DATA_DIR", tmp_path)
    business_calendar.get_holidays_kr.cache_clear()
    yield tmp_path
    business_calendar.get_holidays_kr.cache_clear()


def _observe_target_during_write(year: int, target: Path) -> list[str]:
    """쓰기가 도는 동안 대상 경로를 훔쳐본 결과.

    Returns:
        관측 목록. ``"absent"``(아직 없음) 또는 ``"valid"``(완결 JSON).
        반쪽 파일을 보면 ``"partial"`` 이 들어간다.
    """
    observed: list[str] = []
    real_dump = json.dump

    def spy_dump(obj, file, **kwargs):
        # **쓰기 한복판**이다. 이 순간 다른 워커가 대상 경로를 읽는다고 치자.
        if not target.exists():
            observed.append("absent")
        else:
            try:
                json.loads(target.read_text(encoding="utf-8"))
                observed.append("valid")
            except json.JSONDecodeError:
                observed.append("partial")
        return real_dump(obj, file, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(json, "dump", spy_dump)
        business_calendar._generate_holidays_kr(year)
    return observed


def test_cache_write_never_exposes_a_half_written_file(sandbox_data_dir):
    """생성 도중에도 대상 경로는 '없거나 완결'이다 — 반쪽 파일이 보이면 안 된다."""
    year = 2099
    target = sandbox_data_dir / f"holidays_kr_{year}.json"

    observed = _observe_target_during_write(year, target)

    assert observed, "쓰기 지점을 못 잡았다 — 계약이 헛돈다"
    assert "partial" not in observed, (
        "쓰기 도중 대상 경로에 반쪽 파일이 보였다 — 다른 xdist 워커가 그것을 읽으면 "
        "JSONDecodeError 로 터진다. 임시 파일에 쓰고 os.replace 로 갈아 끼워라."
    )
    assert target.exists(), "쓰기가 끝났는데 파일이 없다"
    assert json.loads(target.read_text(encoding="utf-8"))["year"] == year


def test_cache_write_leaves_no_temp_file_behind(sandbox_data_dir):
    """임시 파일을 남기지 않는다 — 남으면 다음 런이 그 쓰레기를 계속 본다."""
    year = 2098

    business_calendar._generate_holidays_kr(year)

    leftovers = [path.name for path in sandbox_data_dir.iterdir()
                 if path.name != f"holidays_kr_{year}.json"]
    assert leftovers == [], f"임시 파일이 남았다: {leftovers}"


def test_existing_cache_is_replaced_not_truncated(sandbox_data_dir):
    """이미 있는 캐시를 다시 만들어도 중간에 빈 파일 상태를 거치지 않는다."""
    year = 2097
    target = sandbox_data_dir / f"holidays_kr_{year}.json"
    business_calendar._generate_holidays_kr(year)
    assert target.exists()

    observed = _observe_target_during_write(year, target)

    assert "partial" not in observed, "덮어쓰기가 옛 파일을 먼저 비웠다"
    assert "absent" not in observed, "덮어쓰기 도중 파일이 사라졌다 — 읽는 쪽이 생성으로 떨어진다"


def test_reader_retries_a_locked_file_instead_of_failing(sandbox_data_dir, monkeypatch):
    """교체 중 잠긴 파일은 **다시 읽어** 넘긴다 — Windows `os.replace` 창 대응."""
    year = 2096
    business_calendar._generate_holidays_kr(year)
    target = sandbox_data_dir / f"holidays_kr_{year}.json"
    real_open = Path.open
    calls = {"n": 0}

    def flaky_open(self, *args, **kwargs):
        if self == target:
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError(13, "locked by the replacing process")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)

    dates = business_calendar._load_holidays_json(year)

    assert calls["n"] >= 2, "한 번 막혔는데 다시 읽지 않았다"
    assert dates, "재시도로 읽어낸 값이 비었다"


def test_reader_does_not_swallow_a_permanently_broken_file(sandbox_data_dir, monkeypatch):
    """끝내 못 읽으면 **터진다** — 조용히 빈 값을 주면 공휴일 없이 영업일을 센다."""
    year = 2095
    business_calendar._generate_holidays_kr(year)
    target = sandbox_data_dir / f"holidays_kr_{year}.json"
    real_open = Path.open

    def always_locked(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "locked forever")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", always_locked)
    monkeypatch.setattr(business_calendar.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError):
        business_calendar._load_holidays_json(year)
