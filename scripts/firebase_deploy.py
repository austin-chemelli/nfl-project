"""Deploy web/dist to Firebase Hosting through the REST API (docs/site.md, M7.5).

    python3 scripts/firebase_deploy.py --dry-run     # list files, hashes and the hosting config
    python3 scripts/firebase_deploy.py               # create version, upload, finalize, release

Auth: an OAuth access token from `gcloud auth print-access-token` (keyless Workload Identity in
GitHub Actions, your gcloud login locally), or $FIREBASE_ACCESS_TOKEN. Stdlib only so CI can run
it without installing the project. Chosen over the Firebase CLI, whose current releases have open
reports of ignoring Workload Identity credentials in CI.

Steps (https://firebase.google.com/docs/hosting/api-deploy): create a version with the hosting
config, populateFiles with the SHA-256 of each gzipped file, upload only the hashes Firebase asks
for, finalize the version, then release it to the live channel.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://firebasehosting.googleapis.com/v1beta1"
ROOT = Path(__file__).resolve().parents[1]
BATCH = 1000  # populateFiles limit per call


def hosting_config(data_origin: str) -> dict:
    """SPA rewrite, long cache for hashed assets, no-cache HTML, and a CSP that only allows data
    fetches from the site itself and the public data bucket."""
    csp = "; ".join(
        [
            "default-src 'self'",
            f"connect-src 'self' {data_origin}",
            "img-src 'self' data:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
        ]
    )
    security = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    return {
        "headers": [
            {"glob": "**", "headers": security},
            {
                "glob": "/assets/**",
                "headers": {"Cache-Control": "public, max-age=31536000, immutable"},
            },
            {"regex": not_prefix_regex("/assets/"), "headers": {"Cache-Control": "no-cache"}},
        ],
        # a missing /assets/ file must 404, not come back as index.html under the immutable header
        "rewrites": [{"regex": not_prefix_regex("/assets/"), "path": "/index.html"}],
        "cleanUrls": False,
        "trailingSlashBehavior": "REMOVE",
    }


def not_prefix_regex(prefix: str) -> str:
    """RE2 (no lookahead) for every path that doesn't start with `prefix`. Header rules match the
    request path before rewrites and Firebase doesn't document which of two matching rules wins,
    so the cache rules are disjoint: SPA routes (/game/x) must never get the immutable header."""
    alts = [f"{re.escape(prefix[:i])}[^{re.escape(prefix[i])}]" for i in range(1, len(prefix))]
    shorter = "|".join(re.escape(prefix[:i]) for i in range(1, len(prefix)))
    return f"^(?:(?:{'|'.join(alts)}).*|{shorter}|)$"


def gzipped_files(dist: Path) -> dict[str, tuple[str, bytes]]:
    """{'/path': (sha256 of gzip bytes, gzip bytes)}. mtime=0 keeps hashes stable across builds."""
    out: dict[str, tuple[str, bytes]] = {}
    for p in sorted(dist.rglob("*")):
        if p.is_file():
            gz = gzip.compress(p.read_bytes(), compresslevel=9, mtime=0)
            out["/" + p.relative_to(dist).as_posix()] = (hashlib.sha256(gz).hexdigest(), gz)
    return out


def access_token() -> str:
    tok = os.environ.get("FIREBASE_ACCESS_TOKEN")
    if tok:
        return tok.strip()
    return subprocess.run(
        ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True
    ).stdout.strip()


class Client:
    def __init__(self, token: str, project: str):
        self.headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": project}

    def call(
        self, method: str, url: str, body: dict | bytes | None = None, ctype: str = ""
    ) -> dict:
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body else None
        headers = dict(self.headers)
        if data is not None:
            headers["Content-Type"] = ctype or "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:800]
            sys.exit(f"{method} {url.split('?')[0]} -> HTTP {e.code}\n{detail}")
        return json.loads(raw) if raw else {}


def deploy(args: argparse.Namespace) -> None:
    dist = Path(args.dist)
    if not (dist / "index.html").exists():
        sys.exit(f"{dist}/index.html not found: run `npm run build` in web/ first")
    files = gzipped_files(dist)
    config = hosting_config(args.data_origin)
    total = sum(len(gz) for _, gz in files.values())
    print(f"{len(files)} files, {total / 1024:.0f} KB gzipped, site {args.site}")
    if args.dry_run:
        for path, (h, gz) in files.items():
            print(f"  {h[:12]}  {len(gz):>8}  {path}")
        print(json.dumps(config, indent=2))
        return

    fb = Client(access_token(), args.project)
    version = fb.call("POST", f"{API}/sites/{args.site}/versions", {"config": config})["name"]
    print(f"created {version}")

    by_path = {path: h for path, (h, _) in files.items()}
    by_hash = {h: gz for h, gz in files.values()}
    needed: set[str] = set()
    upload_url = ""
    paths = list(by_path)
    for i in range(0, len(paths), BATCH):
        chunk = {p: by_path[p] for p in paths[i : i + BATCH]}
        res = fb.call("POST", f"{API}/{version}:populateFiles", {"files": chunk})
        needed |= set(res.get("uploadRequiredHashes", []))
        upload_url = res.get("uploadUrl", upload_url)
    print(f"uploading {len(needed)} new files ({len(files) - len(needed)} already on Firebase)")
    for h in sorted(needed):
        fb.call("POST", f"{upload_url}/{h}", by_hash[h], ctype="application/octet-stream")

    fb.call("PATCH", f"{API}/{version}?update_mask=status", {"status": "FINALIZED"})
    rel = fb.call(
        "POST",
        f"{API}/sites/{args.site}/releases?versionName={version}",
        {"message": args.message[:200]} if args.message else {},
    )
    print(f"released {rel.get('name', '?')} -> https://{args.site}.web.app")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--site", default=os.environ.get("FIREBASE_SITE", "nfl-project-prod"))
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", "nfl-project-prod"))
    ap.add_argument("--dist", default=str(ROOT / "web" / "dist"))
    ap.add_argument("--data-origin", default="https://storage.googleapis.com")
    ap.add_argument("--message", default=os.environ.get("GITHUB_SHA", ""))  # truncated to 200
    ap.add_argument("--dry-run", action="store_true")
    deploy(ap.parse_args())


if __name__ == "__main__":
    main()
