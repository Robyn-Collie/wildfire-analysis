"""Write the archived first site to deploy/archive/, rewritten to be served under /archive/.

The first us-wildfires site (legacy/wildfire-poc/site-v2, an Astro build) links and fetches everything from the
site root ("/data/...", "/_astro/...", "/model.html"). This copies its built output and rewrites those root paths
to "/archive/...", adds a noindex tag and a banner linking to the current site. It is run once, on the built output
that was live, and the result is committed; the point files it copies stay git-ignored (see .gitignore) and are
kept locally in data/archive_v1/ for scripts/deploy.py.

Usage (from the repo root):
    python scripts/archive_v1.py <built dist folder>    # e.g. the wildfire-poc repo's site-v2/dist
"""
from __future__ import annotations

import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(REPO, 'deploy', 'archive')
BINS = os.path.join(REPO, 'data', 'archive_v1')

BANNER = ('<div style="position:sticky;top:0;z-index:1000;background:#7c2d12;color:#fff;font:600 14px/1.4 system-ui,sans-serif;'
          'padding:.55rem 1rem;text-align:center">Archived: the first version of this site (July 2026), kept for the record. '
          '<a href="/" style="color:#fff;text-decoration:underline">The current analysis is here</a>.</div>')


def main(argv: list[str]) -> int:
    src = argv[0]
    shutil.rmtree(DST, ignore_errors=True)
    shutil.copytree(src, DST)
    # Every top-level file or folder of the build, plus the extension-less page names Netlify serves.
    top = {os.path.splitext(n)[0] for n in os.listdir(src)} | {'explore', 'monsters', 'trend', 'seasonality', 'drivers', 'model', 'map', 'methods'}
    seg = '|'.join(re.escape(t) for t in sorted(top, key=len, reverse=True))
    root_path = re.compile(r'(?<=["\'(`])/(?=(?:' + seg + r')(?:[/."\'`)#?]|$)|["\'`)#])')
    n_files = n_paths = 0
    for root, _, files in os.walk(DST):
        for f in files:
            if not f.endswith(('.html', '.js', '.css', '.mjs')):
                continue
            p = os.path.join(root, f)
            with open(p, encoding='utf-8') as fh:
                s = fh.read()
            s, k = root_path.subn('/archive/', s)
            if f.endswith('.html'):
                s = re.sub(r'<head([^>]*)>', r'<head\1><meta name="robots" content="noindex">', s, count=1)
                s = re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + BANNER, s, count=1)
            with open(p, 'w', encoding='utf-8', newline='') as fh:
                fh.write(s)
            n_files += 1
            n_paths += k
    # Keep a local copy of the point files, which git ignores, for scripts/deploy.py.
    os.makedirs(BINS, exist_ok=True)
    for root, _, files in os.walk(os.path.join(DST, 'data')):
        for f in files:
            if f.endswith('.bin'):
                shutil.copy2(os.path.join(root, f), os.path.join(BINS, f))
    print(f'archive written to {DST}: {n_files} text files, {n_paths} root paths rewritten; point files copied to {BINS}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
