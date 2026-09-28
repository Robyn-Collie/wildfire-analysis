"""Digest-deploy a directory to an existing Netlify site.

Usage:  python pipeline/deploy_netlify.py <dir> <site_id>
Token:  NETLIFY_TOKEN env var (source ~/.bashrc first in bash shells).

Netlify file-digest deploy: send {path: sha1}; upload only the shas
Netlify asks for; poll until the deploy is ready.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = "https://api.netlify.com/api/v1"


def req(method: str, url: str, token: str, body: bytes | None = None,
        ctype: str = "application/json"):
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        r.add_header("Content-Type", ctype)
    with urllib.request.urlopen(r, timeout=120) as resp:
        return json.loads(resp.read().decode() or "{}")


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    site_id = sys.argv[2]
    token = os.environ["NETLIFY_TOKEN"]

    files: dict[str, str] = {}
    by_sha: dict[str, list[Path]] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        sha = hashlib.sha1(p.read_bytes()).hexdigest()
        rel = "/" + p.relative_to(root).as_posix()
        files[rel] = sha
        by_sha.setdefault(sha, []).append(p)
    print(f"{len(files)} files, {sum(p.stat().st_size for ps in by_sha.values() for p in ps) / 1e6:.1f} MB")

    dep = req("POST", f"{API}/sites/{site_id}/deploys", token,
              json.dumps({"files": files}).encode())
    deploy_id = dep["id"]
    required = dep.get("required") or []
    print(f"deploy {deploy_id}: {len(required)} files to upload")

    for i, sha in enumerate(required, 1):
        p = by_sha[sha][0]
        rel = "/" + p.relative_to(root).as_posix()
        # path must be URL-encoded per segment
        enc = "/".join(urllib.request.quote(seg) for seg in rel.strip("/").split("/"))
        req("PUT", f"{API}/deploys/{deploy_id}/files/{enc}", token,
            p.read_bytes(), "application/octet-stream")
        if i % 10 == 0 or i == len(required):
            print(f"  uploaded {i}/{len(required)}")

    for _ in range(60):
        state = req("GET", f"{API}/deploys/{deploy_id}", token)
        if state.get("state") == "ready":
            print(f"READY: {state.get('ssl_url') or state.get('url')}")
            return
        if state.get("state") == "error":
            raise SystemExit(f"deploy errored: {state.get('error_message')}")
        time.sleep(3)
    raise SystemExit("timed out waiting for deploy to go ready")


if __name__ == "__main__":
    main()
