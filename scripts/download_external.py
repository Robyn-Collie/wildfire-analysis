"""
Download the external datasets that the conservation-lens analysis joins to the FPA FOD.

Usage (from the repo root):
    python scripts/download_external.py                # download every registered file that is missing
    python scripts/download_external.py --only ics209plus
    python scripts/download_external.py --verify       # re-hash downloaded files against the registry
    python scripts/download_external.py --list

Each registry entry has a name, a landing page, a download URL (or a resolver that asks the
provider's API for the current URL), the expected size in bytes, the SHA-256 recorded after the
first download (None until then), a licence, and a destination folder data/external/<name>/.
Archives are unpacked into that folder. Downloads go to a .part file first and are renamed
only when the size (and hash, when recorded) match. The script never reads or writes
data/FPA_FOD_20221014.sqlite or data/fires.parquet.

The hashes and dates are also recorded in docs/DATA_JOINS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTERNAL_DIR = os.path.join(REPO_ROOT, 'data', 'external')
PROTECTED = {os.path.join(REPO_ROOT, 'data', 'FPA_FOD_20221014.sqlite'),
             os.path.join(REPO_ROOT, 'data', 'fires.parquet')}
USER_AGENT = 'wildfire-analysis/scripts/download_external.py (python-urllib)'


# --------------------------------------------------------------------------- resolvers

def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def resolve_figshare(article_id: int, file_name: str):
    """Return (download_url, size) for one file of a figshare article, via the public API."""
    meta = _get_json(f'https://api.figshare.com/v2/articles/{article_id}')
    for f in meta['files']:
        if f['name'] == file_name:
            return f['download_url'], int(f['size'])
    raise FileNotFoundError(f'{file_name} not listed on figshare article {article_id}')


def resolve_sciencebase(item_id: str, file_name: str):
    """Return (download_url, size) for one file of a ScienceBase item, via the catalog JSON.

    Large ScienceBase files are listed with a 'manager' URL that serves an HTML app, so the
    download goes through the catalog's file/get endpoint with the file name instead.
    """
    meta = _get_json(f'https://www.sciencebase.gov/catalog/item/{item_id}?format=json')
    for f in meta.get('files', []):
        if f['name'] == file_name:
            url = f.get('url') or f.get('downloadUri')
            if str(f.get('pathOnDisk', '')).startswith('__disk__'):
                url = (f'https://www.sciencebase.gov/catalog/file/get/{item_id}?f='
                       + urllib.parse.quote(f['pathOnDisk'], safe=''))
            return url, int(f['size'])
    raise FileNotFoundError(f'{file_name} not listed on ScienceBase item {item_id}')


# --------------------------------------------------------------------------- registry

PADUS_CITATION = ('U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2024, Protected Areas Database of the '
                  'United States (PAD-US) 4.1: U.S. Geological Survey data release, https://doi.org/10.5066/P96WBCHS.')
PADUS_LICENSE = 'USGS data release, public domain (US Government work); not authoritative for regulatory use'

REGISTRY: list[dict] = [
    {
        'name': 'ics209plus',
        'title': 'ICS-209-PLUS 2.0, wildfire tables (1999-2020)',
        'citation': 'St. Denis, L. A., Short, K. C., McConnell, K., Cook, M. C., Mietkiewicz, N. P., Buckland, M., '
                    'and Balch, J. K. (2023). All-hazards dataset mined from the US National Incident Management '
                    'System 1999-2020. figshare. https://doi.org/10.6084/m9.figshare.19858927.v3',
        'landing': 'https://api.figshare.com/v2/articles/19858927',
        'file_name': 'ics209plus-wildfire.zip',
        'resolver': lambda: resolve_figshare(19858927, 'ics209plus-wildfire.zip'),
        'expected_size': 48_717_736,
        'sha256': 'a17c08ede2824e9002fcda112301793c9e59ce1f7ed7eb1e16a762be85ade30f',  # recorded 2026-09-25
        'license': 'CC BY 4.0',
        'unpack': True,
        'delete_archive': False,
    },
    {
        'name': 'padus_national_gdb',
        'title': 'PAD-US 4.1 national file geodatabase (USGS Gap Analysis Project)',
        'citation': PADUS_CITATION,
        'landing': 'https://www.sciencebase.gov/catalog/item/652d4fc5d34e44db0e2ee45e',
        'file_name': 'PADUS4_1Geodatabase.zip',
        'resolver': lambda: resolve_sciencebase('652d4fc5d34e44db0e2ee45e', 'PADUS4_1Geodatabase.zip'),
        'expected_size': 1_523_434_496,
        'sha256': 'PENDING_FIRST_DOWNLOAD',
        'license': PADUS_LICENSE,
        'unpack': True,
        'delete_archive': True,
        'requires_login': ('ScienceBase serves this file from S3 through its File Manager app, which needs a '
                           'Keycloak login (api.sciencebase.gov/graphql answers UNAUTHENTICATED) or a captcha page. '
                           'It cannot be fetched by script. The PAD-US 4.1 state downloads (item '
                           '6759abcfd34edfeb8710a004) are behind the same wall. Use the padus_conus/padus_ak/padus_hi '
                           'entries instead, which the catalog serves directly.'),
    },
    {
        # The "Raster Analysis" zips also contain the PAD-US 4.1 Vector Analysis file geodatabase
        # (PADUS4_1VectorAnalysis_<extent>.gdb): the Combined Fee/Designation/Easement feature class with
        # overlapping designations resolved by GAP status priority. Only the geodatabase is extracted.
        'name': 'padus_conus',
        'title': 'PAD-US 4.1 Raster Analysis, CONUS (contains PADUS4_1VectorAnalysis_CONUS.gdb)',
        'citation': PADUS_CITATION,
        'landing': 'https://www.sciencebase.gov/catalog/item/6759b67ed34edfeb8710a3db',
        'file_name': 'PADUS4_1_Raster_CONUS.zip',
        'resolver': lambda: resolve_sciencebase('6759b67ed34edfeb8710a3db', 'PADUS4_1_Raster_CONUS.zip'),
        'expected_size': 744_032_421,
        'sha256': 'c830855c92f8599dc63413ddbd3044eb7bf3d92dd14a909779e6adcba2d0ba57',  # recorded 2026-09-25
        'license': PADUS_LICENSE,
        'unpack': True,
        'delete_archive': True,
        'extract_only': ('PADUS4_1VectorAnalysis_CONUS.gdb/', 'RasterizationReport', '_Stats.txt'),
    },
    {
        'name': 'padus_ak',
        'title': 'PAD-US 4.1 Raster Analysis, Alaska (contains PADUS4_1VectorAnalysis_AK.gdb)',
        'citation': PADUS_CITATION,
        'landing': 'https://www.sciencebase.gov/catalog/item/6759b67ed34edfeb8710a3db',
        'file_name': 'PADUS4_1_Raster_AK.zip',
        'resolver': lambda: resolve_sciencebase('6759b67ed34edfeb8710a3db', 'PADUS4_1_Raster_AK.zip'),
        'expected_size': 151_544_095,
        'sha256': 'd943e74b36238f973156d06c3e1a6e53896f9bde401535e36d68ec95da0cc618',  # recorded 2026-09-25
        'license': PADUS_LICENSE,
        'unpack': True,
        'delete_archive': True,
        'extract_only': ('PADUS4_1VectorAnalysis_AK.gdb/', 'RasterizationReport', '_Stats.txt'),
    },
    {
        'name': 'padus_hi',
        'title': 'PAD-US 4.1 Raster Analysis, Hawaii (contains PADUS4_1VectorAnalysis_HI.gdb)',
        'citation': PADUS_CITATION,
        'landing': 'https://www.sciencebase.gov/catalog/item/6759b67ed34edfeb8710a3db',
        'file_name': 'PADUS4_1_Raster_HI.zip',
        'resolver': lambda: resolve_sciencebase('6759b67ed34edfeb8710a3db', 'PADUS4_1_Raster_HI.zip'),
        'expected_size': 14_122_874,
        'sha256': 'af99b44bcfbace0a7d763740a7da40bb9a1b2dae4b6f2bec7324cefae8f024f0',  # recorded 2026-09-25
        'license': PADUS_LICENSE,
        'unpack': True,
        'delete_archive': True,
        'extract_only': ('PADUS4_1VectorAnalysis_HI.gdb/', 'RasterizationReport', '_Stats.txt'),
    },
]


# --------------------------------------------------------------------------- helpers

def sha256_of(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _guard(path: str) -> None:
    if os.path.abspath(path) in PROTECTED:
        raise RuntimeError(f'refusing to touch {path}')


def download(url: str, dest: str, expected_size: int | None) -> None:
    """Stream url to dest via dest + '.part', resuming when the server supports ranges."""
    _guard(dest)
    part = dest + '.part'
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {'User-Agent': USER_AGENT}
    if have:
        headers['Range'] = f'bytes={have}-'
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        resumed = r.status == 206
        mode = 'ab' if resumed else 'wb'
        if not resumed:
            have = 0
        total = r.headers.get('Content-Length')
        total = have + int(total) if total else expected_size
        done = have
        with open(part, mode) as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                done += len(b)
                if total:
                    print(f'\r  {done / 1e6:,.0f} / {total / 1e6:,.0f} MB ({done * 100 // total}%)', end='', flush=True)
    print(f'\n  {done / 1e6:,.1f} MB in {time.time() - t0:,.0f} s')
    if expected_size and done != expected_size:
        raise RuntimeError(f'size mismatch: got {done:,} bytes, expected {expected_size:,}')
    os.replace(part, dest)


def unpack(archive: str, dest_dir: str, only: tuple[str, ...] | None = None) -> list[str]:
    """Extract the archive; with ``only``, extract just the members whose name contains one of the patterns."""
    with zipfile.ZipFile(archive) as zf:
        names = [m for m in zf.namelist() if not only or any(p in m for p in only)]
        zf.extractall(dest_dir, members=names)
    return names


def fetch(entry: dict, force: bool = False) -> int:
    dest_dir = os.path.join(EXTERNAL_DIR, entry['name'])
    os.makedirs(dest_dir, exist_ok=True)
    archive = os.path.join(dest_dir, entry['file_name'])
    marker = os.path.join(dest_dir, 'DOWNLOAD.json')
    if os.path.exists(marker) and not force:
        print(f"{entry['name']}: already downloaded (see {os.path.relpath(marker, REPO_ROOT)})")
        return 0
    if entry.get('requires_login'):
        print(f"{entry['name']}: SKIPPED, cannot be fetched by script. {entry['requires_login']}")
        return 0
    url, size = entry['resolver']()
    print(f"{entry['name']}: {url}")
    if size and entry['expected_size'] and size != entry['expected_size']:
        print(f"  warning: provider reports {size:,} bytes, registry expects {entry['expected_size']:,}")
    if not os.path.exists(archive):
        download(url, archive, size or entry['expected_size'])
    digest = sha256_of(archive)
    print(f'  sha256 {digest}')
    if entry['sha256'] != 'PENDING_FIRST_DOWNLOAD' and digest != entry['sha256']:
        print(f"  HASH MISMATCH: registry has {entry['sha256']}")
        return 1
    names = []
    if entry['unpack']:
        print('  unpacking')
        names = unpack(archive, dest_dir, entry.get('extract_only'))
        if entry['delete_archive']:
            os.remove(archive)
            print('  archive deleted after extraction')
    with open(marker, 'w') as f:
        json.dump({'name': entry['name'], 'file_name': entry['file_name'], 'url': url, 'size': os.path.getsize(archive)
                   if os.path.exists(archive) else size, 'sha256': digest, 'license': entry['license'],
                   'downloaded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'members': names[:200],
                   'n_members': len(names)}, f, indent=1)
    return 0


def verify(entry: dict) -> int:
    dest_dir = os.path.join(EXTERNAL_DIR, entry['name'])
    marker = os.path.join(dest_dir, 'DOWNLOAD.json')
    if not os.path.exists(marker):
        print(f"{entry['name']}: not downloaded")
        return 1
    with open(marker) as f:
        rec = json.load(f)
    archive = os.path.join(dest_dir, entry['file_name'])
    if os.path.exists(archive):
        digest = sha256_of(archive)
        ok = digest == entry['sha256'] or entry['sha256'] == 'PENDING_FIRST_DOWNLOAD'
        print(f"{entry['name']}: archive present, sha256 {digest} {'OK' if ok else 'MISMATCH'}")
        return 0 if ok else 1
    ok = rec['sha256'] == entry['sha256']
    print(f"{entry['name']}: archive deleted after extraction; recorded sha256 {rec['sha256']} "
          f"{'matches registry' if ok else 'DOES NOT MATCH registry'}; {rec['n_members']} members extracted")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', help='registry name to fetch (default: all)')
    ap.add_argument('--verify', action='store_true', help='hash downloaded files against the registry')
    ap.add_argument('--list', action='store_true', help='print the registry and exit')
    ap.add_argument('--force', action='store_true', help='re-download even if a DOWNLOAD.json marker exists')
    args = ap.parse_args(argv)
    entries = [e for e in REGISTRY if not args.only or e['name'] == args.only]
    if args.only and not entries:
        print(f'unknown name {args.only}; known: {[e["name"] for e in REGISTRY]}')
        return 2
    if args.list:
        for e in REGISTRY:
            print(f"{e['name']:12s} {e['file_name']:28s} {e['expected_size'] / 1e6:8,.1f} MB  {e['license']}")
        return 0
    rc = 0
    for e in entries:
        rc |= verify(e) if args.verify else fetch(e, force=args.force)
    return rc


if __name__ == '__main__':
    sys.exit(main())
