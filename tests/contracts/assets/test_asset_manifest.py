"""내용 해시 자산 URL(``asset_url``) 계약 — 시범: ``templates/orders/partials/erp_order_js.html``.

계획 ``docs/plans/2026-09-29-asset-content-hash-url-plan.md`` §3:
① 한 바이트만 바꿔도 URL 이 바뀐다 ② 내용이 같으면 URL 이 같다(워커·컨테이너가 달라도)
③ 없는 파일은 시험·개발 모드에서 즉시 오류 ④ 렌더된 시범 파일의 37개 URL 이 모두
``?v=<12자리 소문자 16진>`` 이고 실제 파일 내용 해시와 맞다.

기대 해시는 구현을 거치지 않고 hashlib 로 여기서 직접 계산한다(순환 검증 방지).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

import pytest
from flask import Flask, render_template

from foms.services.asset_urls import (
    AssetNotFoundError,
    asset_url,
    clear_asset_url_cache,
)
from tests.support.asset_urls import (
    ASSET_URL_PILOT_TEMPLATE,
    REPO_ROOT,
    STATIC_ROOT,
    expected_asset_version,
)

PILOT_TEMPLATE_NAME = "orders/partials/erp_order_js.html"
PILOT_ASSET_COUNT = 37  # CSS 13 · JS 24 (계획서 §1)
PILOT_IMAGE_COUNT = 4  # 결제 아이콘 — 버전 없는 이미지는 그대로 둔다

_HASH_VERSION = re.compile(r"^[0-9a-f]{12}$")
_ASSET_URL_CALL = re.compile(r"\{\{\s*asset_url\('([^']+)'\)\s*\}\}")
_STATIC_CSS_JS_REF = re.compile(r'(?:href|src)="/static/([^"?]+\.(?:css|js))(?:\?v=([^"]*))?"')
_DATE_PIN_URL_FOR = re.compile(r"url_for\('static',\s*filename='[^']+\.(?:css|js)'\)\s*\}\}\?v=")


def _sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


@pytest.fixture(autouse=True)
def _fresh_asset_cache():
    """시험끼리 프로세스 캐시를 나눠 쓰지 않게 앞뒤로 비운다."""
    clear_asset_url_cache()
    yield
    clear_asset_url_cache()


def _mini_app(static_dir: Path, *, testing: bool = True, debug: bool = False) -> Flask:
    """임시 static 폴더를 가진 최소 Flask 앱(실제 앱 설정과 분리)."""
    app = Flask("asset_manifest_contract", static_folder=str(static_dir))
    app.config["TESTING"] = testing
    app.debug = debug
    return app


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _version_of(url: str) -> str:
    assert "?v=" in url, url
    return url.split("?v=", 1)[1]


# ① 한 바이트 → 다른 URL -------------------------------------------------------------


def test_one_byte_change_changes_url_in_debug(tmp_path: Path) -> None:
    """개발 모드: 파일을 고치면(수정 시각이 바뀌면) 같은 프로세스에서도 새 URL 이 나온다."""
    static_dir = tmp_path / "static"
    target = static_dir / "js" / "demo.js"
    before = b"window.demo = 'a';\n"
    after = b"window.demo = 'b';\n"  # 딱 한 바이트 차이
    assert len(before) == len(after)
    assert sum(x != y for x, y in zip(before, after)) == 1
    _write(target, before)

    app = _mini_app(static_dir, testing=True, debug=True)
    with app.test_request_context("/"):
        url_before = asset_url("js/demo.js")
        stat = os.stat(target)
        _write(target, after)
        # 편집기 저장처럼 수정 시각을 확실히 옮긴다(파일시스템 시각 해상도에 기대지 않는다).
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        url_after = asset_url("js/demo.js")

    assert url_before == f"/static/js/demo.js?v={_sha12(before)}"
    assert url_after == f"/static/js/demo.js?v={_sha12(after)}"
    assert url_before != url_after


def test_one_byte_change_changes_url_on_next_process(tmp_path: Path) -> None:
    """운영: 값은 프로세스 수명 동안 고정되고, 새 프로세스(=새 배포)에서 새 내용 해시가 된다."""
    static_dir = tmp_path / "static"
    target = static_dir / "css" / "demo.css"
    _write(target, b".a{color:red}")

    app = _mini_app(static_dir, testing=False, debug=False)
    with app.test_request_context("/"):
        first = asset_url("css/demo.css")
        _write(target, b".a{color:rex}")
        same_process = asset_url("css/demo.css")
        clear_asset_url_cache()  # 새 컨테이너가 뜬 것과 같다
        next_process = asset_url("css/demo.css")

    assert same_process == first, "운영은 프로세스마다 한 번만 계산해 기억해야 한다"
    assert _version_of(first) == _sha12(b".a{color:red}")
    assert _version_of(next_process) == _sha12(b".a{color:rex}")
    assert next_process != first


# ② 같은 내용 → 같은 URL ------------------------------------------------------------


def test_same_content_gives_same_url_across_static_roots(tmp_path: Path) -> None:
    """두 컨테이너(서로 다른 폴더)라도 내용이 같으면 URL 이 같다 — 워커마다 캐시 칸이 갈리지 않는다."""
    body = b"console.log('same');\n"
    root_a = tmp_path / "a" / "static"
    root_b = tmp_path / "b" / "static"
    _write(root_a / "js" / "same.js", body)
    _write(root_b / "js" / "same.js", body)

    with _mini_app(root_a).test_request_context("/"):
        url_a1 = asset_url("js/same.js")
        url_a2 = asset_url("js/same.js")
    with _mini_app(root_b).test_request_context("/"):
        url_b = asset_url("js/same.js")

    assert url_a1 == url_a2 == url_b == f"/static/js/same.js?v={_sha12(body)}"
    assert _HASH_VERSION.match(_version_of(url_a1))


def test_different_content_gives_different_url_negative_control(tmp_path: Path) -> None:
    """음성 대조: 같은 경로라도 내용이 다르면 URL 이 달라야 한다(②가 '항상 같은 값'으로 통과하는 것 방지)."""
    root_a = tmp_path / "a" / "static"
    root_b = tmp_path / "b" / "static"
    _write(root_a / "js" / "x.js", b"1")
    _write(root_b / "js" / "x.js", b"2")
    with _mini_app(root_a).test_request_context("/"):
        url_a = asset_url("js/x.js")
    with _mini_app(root_b).test_request_context("/"):
        url_b = asset_url("js/x.js")
    assert url_a != url_b


# ③ 없는 파일 ------------------------------------------------------------------------


@pytest.mark.parametrize(("testing", "debug"), [(True, False), (False, True)])
def test_missing_file_raises_in_testing_and_debug(tmp_path: Path, testing: bool, debug: bool) -> None:
    """시험·개발 모드에서는 오타를 그 자리에서 잡는다."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    app = _mini_app(static_dir, testing=testing, debug=debug)
    with app.test_request_context("/"):
        with pytest.raises(AssetNotFoundError):
            asset_url("js/does-not-exist.js")


def test_missing_file_in_production_warns_once_and_returns_bare_url(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """운영: 화면은 떠야 하므로 쿼리 없는 URL + 경고 로그(경로당 한 번)."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    app = _mini_app(static_dir, testing=False, debug=False)
    with caplog.at_level(logging.WARNING, logger="foms.services.asset_urls"):
        with app.test_request_context("/"):
            first = asset_url("js/gone.js")
            second = asset_url("js/gone.js")
    assert first == second == "/static/js/gone.js"
    warnings = [r for r in caplog.records if "js/gone.js" in r.getMessage()]
    assert len(warnings) == 1


def test_directory_and_path_escape_count_as_missing(tmp_path: Path) -> None:
    """폴더 이름이나 static 밖을 가리키는 경로는 해시하지 않는다(없는 파일과 같다)."""
    static_dir = tmp_path / "static"
    (static_dir / "js").mkdir(parents=True)
    _write(tmp_path / "secret.txt", b"not an asset")
    app = _mini_app(static_dir, testing=True)
    with app.test_request_context("/"):
        with pytest.raises(AssetNotFoundError):
            asset_url("js")
        with pytest.raises(AssetNotFoundError):
            asset_url("../secret.txt")


# ④ 시범 템플릿 전수 -----------------------------------------------------------------


def test_asset_url_is_registered_as_jinja_global(app) -> None:
    """실제 앱에 ``mark`` 옆 Jinja 전역으로 등록돼 있다."""
    assert app.jinja_env.globals.get("asset_url") is asset_url
    assert "mark" in app.jinja_env.globals


@pytest.mark.parametrize("rel_path", ["js/orders/erp-share.js", "css/orders/erp-share.css"])
def test_content_hash_url_keeps_one_day_cache_policy(app, client, rel_path: str) -> None:
    """``?v=`` 모양을 지켰으므로 하루 캐시 미들웨어(app_factory)가 그대로 먹는다.

    음성 대조: 같은 파일을 버전 없이 부르면 여전히 ``no-cache`` 다.
    """
    with app.test_request_context("/"):
        url = asset_url(rel_path)
    assert _HASH_VERSION.match(_version_of(url))
    hashed = client.get(url)
    assert hashed.status_code == 200
    assert hashed.headers.get("Cache-Control") == "public, max-age=86400"
    bare = client.get(url.split("?", 1)[0])
    assert bare.status_code == 200
    assert bare.headers.get("Cache-Control") == "no-cache"


def test_pilot_template_source_uses_asset_url_for_every_css_js() -> None:
    """원문: css/js 37개는 전부 ``asset_url`` 이고 손 날짜 핀은 한 개도 안 남았다. 이미지 4개는 그대로."""
    source = (REPO_ROOT / ASSET_URL_PILOT_TEMPLATE).read_text(encoding="utf-8")
    calls = _ASSET_URL_CALL.findall(source)
    assert len(calls) == PILOT_ASSET_COUNT, calls
    assert len(set(calls)) == PILOT_ASSET_COUNT, "같은 자산이 두 번 실렸다"
    assert sum(c.endswith(".css") for c in calls) == 13
    assert sum(c.endswith(".js") for c in calls) == 24
    assert not _DATE_PIN_URL_FOR.search(source), "시범 파일에 손 날짜 핀(?v=)이 남았다"
    assert "?v=" not in source
    images = re.findall(r"url_for\('static', filename='(images/[^']+\.png)'\)", source)
    assert len(images) == PILOT_IMAGE_COUNT, images


def _render_pilot(app) -> str:
    # 조건부 자산(스펙 피커 5 · 오프라인 SW 1 · 인라인 편집 2)까지 전부 렌더되도록 플래그를 켠다.
    with app.test_request_context("/"):
        return render_template(
            PILOT_TEMPLATE_NAME,
            flag_spec_picker=True,
            flag_inline=True,
            flag_offline_sw=True,
        )


def _asset_url_violations(html: str) -> list[str]:
    """렌더 결과에서 '내용 해시가 아닌' css/js URL 을 전부 모은다."""
    problems: list[str] = []
    for rel_path, version in _STATIC_CSS_JS_REF.findall(html):
        if not version:
            problems.append(f"{rel_path}: 버전 없음")
            continue
        if not _HASH_VERSION.match(version):
            problems.append(f"{rel_path}: 해시 모양 아님 ?v={version}")
            continue
        expected = expected_asset_version(rel_path)
        if version != expected:
            problems.append(f"{rel_path}: ?v={version} != 내용 해시 {expected}")
    return problems


def test_rendered_pilot_assets_are_all_content_hash_urls(app) -> None:
    """렌더된 37개 URL 이 모두 ``?v=<12자리 소문자 16진>`` 이고 실제 파일 sha256 앞자리와 같다."""
    html = _render_pilot(app)
    refs = _STATIC_CSS_JS_REF.findall(html)
    assert len(refs) == PILOT_ASSET_COUNT, refs

    source = (REPO_ROOT / ASSET_URL_PILOT_TEMPLATE).read_text(encoding="utf-8")
    assert [path for path, _ in refs] == _ASSET_URL_CALL.findall(source), "렌더 순서·목록이 원문과 다르다"

    for rel_path, version in refs:
        assert _HASH_VERSION.match(version), f"{rel_path}?v={version}"
        on_disk = hashlib.sha256((STATIC_ROOT / rel_path).read_bytes()).hexdigest()
        assert version == on_disk[:12], rel_path

    assert _asset_url_violations(html) == []
    # 이미지 4개는 버전 없이 그대로다.
    assert html.count('.png"') == PILOT_IMAGE_COUNT


def test_violation_checker_catches_date_pin_and_stale_hash_negative_control(app) -> None:
    """음성 대조(모집단 안에서): 실제 렌더 결과의 URL 두 개를 옛 날짜 핀·남의 해시로 바꾸면 정확히 그 둘을 잡는다."""
    html = _render_pilot(app)
    refs = _STATIC_CSS_JS_REF.findall(html)
    (first_path, first_version), (second_path, second_version) = refs[0], refs[1]
    other_version = refs[2][1]
    assert other_version != second_version

    tampered = html.replace(f"{first_path}?v={first_version}", f"{first_path}?v=20260921a", 1)
    tampered = tampered.replace(f"{second_path}?v={second_version}", f"{second_path}?v={other_version}", 1)

    problems = _asset_url_violations(tampered)
    assert len(problems) == 2, problems
    assert problems[0].startswith(f"{first_path}: 해시 모양 아님")
    assert problems[1].startswith(f"{second_path}: ?v={other_version} != 내용 해시")
