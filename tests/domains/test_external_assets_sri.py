"""밖(CDN)에서 불러오는 스크립트·스타일은 버전 고정 + 무결성(SRI) 표시 (SPEC 2026-10-20-external-scripts-sri).

CDN 파일이 바뀌면(사고·탈취) 브라우저가 그 파일을 막는다. 버전 없는 주소는 그날의 최신판을
받아 와서 해시를 붙일 수 없으므로 금지한다. 키·지역으로 매번 달라지는 서비스 SDK(카카오 지도·
카카오 공유·다음 우편번호)는 SRI 를 붙일 수 없어 목록으로만 예외다.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: SRI 를 붙일 수 없는 서비스 SDK(내용이 키·시점마다 달라진다).
_SERVICE_SDK_HOSTS = ("t1.daumcdn.net", "dapi.kakao.com", "t1.kakaocdn.net")

_SCRIPT = re.compile(r"<script\b[^>]*\bsrc=[\"']((?:https?:)?//[^\"']+)[\"'][^>]*>")
_STYLE = re.compile(r"<link\b(?=[^>]*rel=[\"']stylesheet)[^>]*\bhref=[\"']((?:https?:)?//[^\"']+)[\"'][^>]*>")


def _templates():
    out = subprocess.run(["git", "ls-files", "templates"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout.split()
    for rel in out:
        if rel.endswith(".html"):
            yield rel, (ROOT / rel).read_text(encoding="utf-8")


def _external_tags():
    for rel, text in _templates():
        for pattern in (_SCRIPT, _STYLE):
            for m in pattern.finditer(text):
                yield rel, m.group(0), m.group(1)


def test_found_external_tags():
    # 검색식이 깨져 0 이 되면 아래 검사가 거짓 통과한다(2026-10-20 기준 20개 안팎).
    assert len(list(_external_tags())) >= 15


def test_external_tags_have_integrity():
    missing = [f"{rel}: {url}" for rel, tag, url in _external_tags()
               if not any(h in url for h in _SERVICE_SDK_HOSTS)
               and not ("integrity=" in tag and "crossorigin" in tag)]
    assert not missing, "SRI 없는 외부 스크립트·스타일:\n" + "\n".join(missing)


def test_no_unversioned_cdn_urls():
    loose = [f"{rel}: {url}" for rel, _tag, url in _external_tags()
             if re.search(r"cdn\.jsdelivr\.net/npm/[a-z0-9-]+(/|$)", url)]
    assert not loose, "버전 없는 CDN 주소:\n" + "\n".join(loose)


def test_html2canvas_loaders_set_integrity():
    out = subprocess.run(["git", "grep", "-l", "HTML2CANVAS_SRC", "--", "static/js"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8").stdout.split()
    assert len(out) >= 6
    bad = [rel for rel in out
           if ".integrity = 'sha384-" not in (ROOT / rel).read_text(encoding="utf-8")]
    assert not bad, bad
