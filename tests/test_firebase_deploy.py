"""The REST deploy script's pure parts: cache-rule regex and stable gzip hashes."""

import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "firebase_deploy", Path(__file__).parents[1] / "scripts" / "firebase_deploy.py"
)
fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fd)


def test_cache_rules_are_disjoint():
    rx = re.compile(fd.not_prefix_regex("/assets/"))
    for path in ["/", "/index.html", "/game/2026_08_CAR_GB", "/a", "/asset", "/assets", "/assetsx/y",
                 "/build", "/favicon.svg", "/as/x"]:  # fmt: skip
        assert rx.match(path), path
    for path in ["/assets/index-abc.js", "/assets/x/y.css"]:
        assert not rx.match(path), path


def test_hashes_are_stable(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.js").write_text("console.log(1)")
    a, b = fd.gzipped_files(tmp_path), fd.gzipped_files(tmp_path)
    assert set(a) == {"/index.html", "/assets/a.js"}
    assert {k: v[0] for k, v in a.items()} == {k: v[0] for k, v in b.items()}


def test_config_shape():
    cfg = fd.hosting_config("https://storage.googleapis.com")
    assert cfg["rewrites"] == [{"regex": fd.not_prefix_regex("/assets/"), "path": "/index.html"}]
    csp = cfg["headers"][0]["headers"]["Content-Security-Policy"]
    assert "connect-src 'self' https://storage.googleapis.com" in csp
