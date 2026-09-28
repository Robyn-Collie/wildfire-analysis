"""Assemble the folder that is deployed to us-wildfires.netlify.app.

The public site is deployed from a local build, because the map's point files are derived from every record and
are not committed. This puts together, in one folder:

    site/                      the current site (python scripts/build_site.py), including its point files
    deploy/archive/ -> archive/  the first site, served under /archive/ (scripts/archive_v1.py), plus its
                               binary data files from data/archive_v1/
    deploy/_headers, deploy/_redirects, deploy/netlify.toml
                               headers (Netlify's file deploys do not read the root netlify.toml), redirects from the
                               first site's page addresses, and "publish this folder as-is, no build"

and refuses to write it if any git-ignored file the pages need is missing. Deploy the folder it prints with the
Netlify connector (deploy-site on project us-wildfires, run from that folder) or the Netlify CLI:
    netlify deploy --dir <folder> --site 612daec7-fe9f-48a5-8108-a0ab7ed40a10 --prod

Usage (from the repo root):
    python scripts/deploy.py [--out build/deploy]
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, 'site')
DEPLOY = os.path.join(REPO, 'deploy')
ARCHIVE_BINS = os.path.join(REPO, 'data', 'archive_v1')

SITE_POINT_FILES = ['points_c_plus.bin', 'points_a_b.bin']
ARCHIVE_DATA_FILES = ['points-v2.bin', 'explore-cause13.bin', 'monsters.bin', 'pdsi-grid.bin']


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(REPO, 'build', 'deploy'))
    args = ap.parse_args(argv)

    missing = [os.path.join('site', 'data', f) for f in SITE_POINT_FILES if not os.path.exists(os.path.join(SITE, 'data', f))]
    missing += [os.path.join('data', 'archive_v1', f) for f in ARCHIVE_DATA_FILES if not os.path.exists(os.path.join(ARCHIVE_BINS, f))]
    if missing:
        print('Not deploying: these git-ignored files are missing:\n  ' + '\n  '.join(missing), file=sys.stderr)
        print('Run python scripts/build_site.py for the site; see legacy/wildfire-poc/README.md for the archive.', file=sys.stderr)
        return 1

    out = os.path.abspath(args.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(SITE, out)
    shutil.copytree(os.path.join(DEPLOY, 'archive'), os.path.join(out, 'archive'))
    for f in ARCHIVE_DATA_FILES:
        shutil.copy2(os.path.join(ARCHIVE_BINS, f), os.path.join(out, 'archive', 'data', f))
    for f in ('_headers', '_redirects', 'netlify.toml'):
        shutil.copy2(os.path.join(DEPLOY, f), os.path.join(out, f))

    files = [p for p in glob.glob(os.path.join(out, '**', '*'), recursive=True) if os.path.isfile(p)]
    size = sum(os.path.getsize(p) for p in files)
    head = subprocess.run(['git', '-C', REPO, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', REPO, 'status', '--porcelain', '--', 'site', 'deploy'], capture_output=True, text=True).stdout.strip()
    print(f'{len(files)} files, {size / 1e6:.1f} MB, from commit {head}{" with uncommitted changes in site/ or deploy/" if dirty else ""}')
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
