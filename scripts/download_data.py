"""
Download the USFS wildfire occurrence database into data/ and verify it.

Source: Short, Karen C. 2022. Spatial wildfire occurrence data for the United States,
1992-2020 [FPA_FOD_20221014]. 6th Edition. Fort Collins, CO: Forest Service Research
Data Archive. https://doi.org/10.2737/RDS-2013-0009.6

The SQLite archive is 224,353,394 bytes zipped (214 MiB) and 958,480,384 bytes unzipped.

What the script guarantees:
- the zip is downloaded to a .part file and only renamed when its size equals the
  server's Content-Length; an interrupted download is resumed with a Range request
  (the server supports byte ranges), with 3 attempts and exponential backoff;
- the database is taken from the archive member with the exact expected name, extracted
  to a .part file and renamed once its size matches the archive's record;
- free disk space is checked before the download and before the extraction;
- the extracted file's SHA-256 is compared with data.sha256; on a mismatch the file is
  moved aside as <name>.unverified and the script exits with status 2.

Exit status: 0 done (or nothing to do), 1 download or extraction failed, 2 hash mismatch.
If the automatic download fails, the script prints manual steps instead.
"""
import hashlib
import http.client
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
import zipfile

CATALOG_URL = 'https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.6'
ZIP_URL = ('https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/'
           'RDS-2013-0009.6_Data_Format4_SQLITE.zip')
DB_FILENAME = 'FPA_FOD_20221014.sqlite'
# The archive's members are 'Data/', 'Data/FPA_FOD_20221014.sqlite' and
# 'Data/_variable_descriptions.csv' (read from the zip's central directory, 2026-09-25).
ZIP_MEMBER = 'Data/' + DB_FILENAME

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, 'data')
ZIP_PATH = os.path.join(DATA_DIR, 'RDS-2013-0009.6_Data_Format4_SQLITE.zip')
DB_PATH = os.path.join(DATA_DIR, DB_FILENAME)
SHA256_PATH = os.path.join(REPO_ROOT, 'data.sha256')

USER_AGENT = 'wildfire-analysis/download_data.py (Python urllib; https://github.com/Robyn-Collie/wildfire-analysis)'
TIMEOUT_SECONDS = 60          # socket timeout for connect and for each read
RETRIES = 3
BACKOFF_SECONDS = 2.0         # sleep 2, 4 s between attempts
CHUNK = 1 << 20
DISK_MARGIN = 64 << 20        # keep this much free beyond what is written
EXTRACT_FACTOR = 1.2          # free space required for the extraction, times the member size

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_HASH_MISMATCH = 2


class DownloadError(Exception):
    """A download that did not complete; the .part file is kept for a resume."""


def manual_instructions() -> None:
    print()
    print('Manual download:')
    print(f'  1. Open {CATALOG_URL}')
    print('  2. Download "RDS-2013-0009.6_Data_Format4_SQLITE.zip" (about 214 MB).')
    print(f'  3. Unzip it and move {DB_FILENAME} into the data/ folder of this repo.')
    print('     (Or set the WILDFIRE_DB_PATH environment variable to wherever you put it.)')
    print(f'  4. Check it: sha256sum -c data.sha256 (the expected hash is in data.sha256).')


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def expected_sha256(sha_path: str = SHA256_PATH) -> str:
    """The hash recorded in data.sha256 (sha256sum format: '<hex>  <path>')."""
    with open(sha_path) as f:
        token = f.read().split()[0]
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token.lower()):
        raise ValueError(f'{sha_path} does not start with a SHA-256 hex digest')
    return token.lower()


def ensure_free_space(directory: str, needed: int, what: str) -> None:
    free = shutil.disk_usage(directory).free
    if free < needed + DISK_MARGIN:
        raise RuntimeError(f'Not enough free disk space in {directory} for {what}: '
                           f'need {needed + DISK_MARGIN:,} bytes, have {free:,}.')


def _content_range_total(resp) -> int:
    """Total size from 'Content-Range: bytes start-end/total'."""
    value = resp.headers.get('Content-Range', '')
    try:
        return int(value.rsplit('/', 1)[1])
    except (IndexError, ValueError):
        raise DownloadError(f'Server sent a 206 without a usable Content-Range ({value!r}).')


def _content_range_start(resp) -> int:
    value = resp.headers.get('Content-Range', '')
    try:
        return int(value.split()[1].split('-')[0])
    except (IndexError, ValueError):
        raise DownloadError(f'Server sent a 206 without a usable Content-Range ({value!r}).')


def _progress(done: int, total: int) -> None:
    if total > 0:
        print(f'\r  {min(100, done * 100 // total):3d}%  {done / (1 << 20):8.1f} / {total / (1 << 20):.1f} MiB',
              end='', flush=True)


def download_once(url: str, part_path: str, timeout: float = TIMEOUT_SECONDS) -> int:
    """
    One attempt: fetch url into part_path, resuming from its current size with a Range
    request. Returns the total size. Raises DownloadError if the file is not complete
    at the end (the partial file is kept so the next attempt can resume).
    """
    have = os.path.getsize(part_path) if os.path.exists(part_path) else 0
    headers = {'User-Agent': USER_AGENT}
    if have:
        headers['Range'] = f'bytes={have}-'
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:
            # Range not satisfiable: either the .part is already complete or it is junk.
            total = None
            try:
                total = int(e.headers.get('Content-Range', '').rsplit('/', 1)[1])
            except (IndexError, ValueError):
                pass
            if total == have:
                return have
            os.remove(part_path)
            raise DownloadError(f'Partial file ({have:,} bytes) did not match the server '
                                f'(total {total}); removed it, will restart.')
        raise

    with resp:
        if resp.status == 206:
            total = _content_range_total(resp)
            start = _content_range_start(resp)
            if start != have:
                raise DownloadError(f'Server resumed at byte {start:,}, expected {have:,}.')
            mode = 'ab'
        elif resp.status == 200:
            length = resp.headers.get('Content-Length')
            if length is None:
                raise DownloadError('Server sent no Content-Length; cannot verify the download.')
            total = int(length)
            if have:
                print(f'\n  Server ignored the Range request; restarting from byte 0.')
            have = 0
            mode = 'wb'
        else:
            raise DownloadError(f'Unexpected HTTP status {resp.status}.')

        ensure_free_space(os.path.dirname(part_path) or '.', total - have, 'the zip download')
        if have:
            print(f'  Resuming at {have:,} of {total:,} bytes.')
        with open(part_path, mode) as f:
            done = have
            _progress(done, total)
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                _progress(done, total)
        print()

    size = os.path.getsize(part_path)
    if size != total:
        raise DownloadError(f'Download incomplete: {size:,} of {total:,} bytes (Content-Length).')
    return total


def download(url: str, dest: str, retries: int = RETRIES, backoff: float = BACKOFF_SECONDS,
             timeout: float = TIMEOUT_SECONDS) -> int:
    """Download url to dest via dest + '.part', with retries and resume. Returns the size."""
    part_path = dest + '.part'
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            total = download_once(url, part_path, timeout=timeout)
            os.replace(part_path, dest)
            return total
        except (DownloadError, urllib.error.URLError, http.client.HTTPException,
                socket.timeout, ConnectionError, TimeoutError) as e:
            last_error = e
            print(f'\n  Attempt {attempt} of {retries} failed: {e}')
            if attempt < retries:
                delay = backoff * (2 ** (attempt - 1))
                print(f'  Retrying in {delay:.0f}s...')
                time.sleep(delay)
    raise DownloadError(f'Download failed after {retries} attempts: {last_error}')


def extract_member(zip_path: str, member: str, dest: str) -> int:
    """Extract exactly `member` from zip_path to dest via dest + '.part'. Returns its size."""
    with zipfile.ZipFile(zip_path) as zf:
        try:
            info = zf.getinfo(member)
        except KeyError:
            raise RuntimeError(f'Archive member {member!r} not found. Members: {zf.namelist()}')
        ensure_free_space(os.path.dirname(dest) or '.', int(EXTRACT_FACTOR * info.file_size), 'the extraction')
        part_path = dest + '.part'
        with zf.open(info) as src, open(part_path, 'wb') as dst:
            shutil.copyfileobj(src, dst, CHUNK)
        size = os.path.getsize(part_path)
        if size != info.file_size:
            os.remove(part_path)
            raise RuntimeError(f'Extracted {size:,} bytes but the archive records {info.file_size:,}.')
        os.replace(part_path, dest)
        return size


def run(zip_url: str = ZIP_URL, zip_path: str = ZIP_PATH, db_path: str = DB_PATH,
        member: str = ZIP_MEMBER, sha_path: str = SHA256_PATH, retries: int = RETRIES,
        backoff: float = BACKOFF_SECONDS, timeout: float = TIMEOUT_SECONDS) -> int:
    data_dir = os.path.dirname(db_path)
    if os.path.exists(db_path):
        print(f'{os.path.basename(db_path)} is already in {data_dir}. Nothing to do.')
        return EXIT_OK

    os.makedirs(data_dir, exist_ok=True)
    expected = expected_sha256(sha_path)

    try:
        if os.path.exists(zip_path):
            print(f'Using the existing archive {zip_path}')
        else:
            print(f'Downloading {zip_url}')
            download(zip_url, zip_path, retries=retries, backoff=backoff, timeout=timeout)

        print(f'Extracting {member} ...')
        extract_member(zip_path, member, db_path)
    except Exception as e:
        print(f'\nAutomatic download failed: {e}')
        if os.path.exists(zip_path + '.part'):
            print(f'  A partial download is kept at {zip_path}.part; run again to resume it.')
        manual_instructions()
        return EXIT_FAILED

    print('Verifying SHA-256 ...')
    actual = sha256_of(db_path)
    if actual != expected:
        unverified = db_path + '.unverified'
        os.replace(db_path, unverified)
        print('SHA-256 MISMATCH. The downloaded database is not the file this repo was built on.')
        print(f'  expected {expected}  ({os.path.relpath(sha_path, REPO_ROOT)})')
        print(f'  actual   {actual}')
        print(f'  The file was moved to {unverified}; the archive is kept at {zip_path}.')
        print('  The archive may have been updated to a new edition; see docs/DATA_VERSION.md.')
        return EXIT_HASH_MISMATCH

    os.remove(zip_path)
    print(f'Done: {os.path.relpath(db_path, REPO_ROOT)} (SHA-256 {actual[:8]}... matches data.sha256)')
    return EXIT_OK


def main() -> int:
    return run()


if __name__ == '__main__':
    sys.exit(main())
