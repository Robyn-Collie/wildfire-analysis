"""Tests for scripts/download_data.py against a local HTTP server (no network).

The server serves one small zip built per test and supports Range requests, so resume,
truncation, Content-Length checks, retries, hash verification, member selection and the
disk-space check are all exercised offline.
"""
import hashlib
import http.server
import io
import os
import random
import shutil
import threading
import zipfile
from pathlib import Path

import pytest

import scripts.download_data as dd

# 200 KB of deterministic, incompressible "database" content, so the zip is big enough to
# cut in the middle.
DB_BYTES = random.Random(20221014).randbytes(200_000)


def make_zip(member: str = dd.ZIP_MEMBER, content: bytes = DB_BYTES, extra=()) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('Data/', '')
        zf.writestr(member, content)
        zf.writestr('Data/_variable_descriptions.csv', 'field,description\n')
        for name, data in extra:
            zf.writestr(name, data)
    return buf.getvalue()


class RangeHandler(http.server.BaseHTTPRequestHandler):
    """Serves `state['body']` at any path, honouring Range; records every request."""
    state = None  # set per test: dict(body=bytes, requests=[], fail_first_after=None, wrong_length=None)

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        st = self.state
        body = st['body']
        st['requests'].append(dict(self.headers))
        # A server with wrong_length set lies consistently about the total size.
        total = st['wrong_length'] if st.get('wrong_length') is not None else len(body)
        rng = self.headers.get('Range')
        if rng:
            start = int(rng.split('=')[1].split('-')[0])
            if start >= len(body):
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{total}')
                self.end_headers()
                return
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{total - 1}/{total}')
            data = body[start:]
        else:
            start = 0
            self.send_response(200)
            data = body
        length = total - start
        self.send_header('Content-Type', 'application/x-zip-compressed')
        self.send_header('Content-Length', str(length))
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        cut = st.get('fail_first_after')
        if cut is not None and len(st['requests']) == 1:
            self.wfile.write(data[:cut])
            self.wfile.flush()
            self.connection.close()  # mid-body disconnect
            return
        self.wfile.write(data)


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')
    monkeypatch.delenv('http_proxy', raising=False)
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    state = {'body': b'', 'requests': []}
    handler = type('H', (RangeHandler,), {'state': state})
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    state['url'] = f'http://127.0.0.1:{httpd.server_address[1]}/archive.zip'
    yield state
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(dd, 'BACKOFF_SECONDS', 0.0)
    data_dir = tmp_path / 'data'
    sha = tmp_path / 'data.sha256'
    sha.write_text(f'{hashlib.sha256(DB_BYTES).hexdigest()}  data/{dd.DB_FILENAME}\n')
    return {'zip': str(data_dir / 'archive.zip'), 'db': str(data_dir / dd.DB_FILENAME), 'sha': str(sha),
            'data_dir': str(data_dir)}


def run(server, paths, **kw):
    kw.setdefault('backoff', 0.0)
    kw.setdefault('timeout', 5)
    return dd.run(zip_url=server['url'], zip_path=paths['zip'], db_path=paths['db'], sha_path=paths['sha'], **kw)


# --------------------------------------------------------------------------- happy path

def test_download_extract_verify(server, paths, capsys):
    server['body'] = make_zip()
    assert run(server, paths) == dd.EXIT_OK
    assert Path(paths['db']).read_bytes() == DB_BYTES
    assert not os.path.exists(paths['zip']), 'the archive is removed after a verified extraction'
    assert not os.path.exists(paths['zip'] + '.part') and not os.path.exists(paths['db'] + '.part')
    assert 'matches data.sha256' in capsys.readouterr().out
    assert len(server['requests']) == 1
    assert 'Range' not in server['requests'][0]


def test_user_agent_and_timeout_are_sent(server, paths, monkeypatch):
    server['body'] = make_zip()
    seen = {}
    real = dd.urllib.request.urlopen

    def spy(req, timeout=None):
        seen['timeout'] = timeout
        return real(req, timeout=timeout)
    monkeypatch.setattr(dd.urllib.request, 'urlopen', spy)
    assert run(server, paths, timeout=17) == dd.EXIT_OK
    assert seen['timeout'] == 17
    assert server['requests'][0]['User-Agent'] == dd.USER_AGENT
    assert 'wildfire-analysis' in dd.USER_AGENT
    assert dd.TIMEOUT_SECONDS > 0 and dd.RETRIES == 3


def test_nothing_to_do_when_db_exists(server, paths, capsys):
    os.makedirs(paths['data_dir'])
    Path(paths['db']).write_bytes(b'x')
    assert run(server, paths) == dd.EXIT_OK
    assert 'Nothing to do' in capsys.readouterr().out
    assert server['requests'] == []


# --------------------------------------------------------------------------- resume and retries

def test_partial_download_is_resumed_with_range(server, paths):
    server['body'] = make_zip()
    os.makedirs(paths['data_dir'])
    cut = 1000
    Path(paths['zip'] + '.part').write_bytes(server['body'][:cut])
    assert run(server, paths) == dd.EXIT_OK
    assert server['requests'][0].get('Range') == f'bytes={cut}-'
    assert Path(paths['db']).read_bytes() == DB_BYTES


def test_complete_part_file_is_accepted_via_416(server, paths):
    server['body'] = make_zip()
    os.makedirs(paths['data_dir'])
    Path(paths['zip'] + '.part').write_bytes(server['body'])
    assert run(server, paths) == dd.EXIT_OK
    assert server['requests'][0].get('Range') == f'bytes={len(server["body"])}-'


def test_mid_body_disconnect_is_retried_and_resumed(server, paths, capsys):
    server['body'] = make_zip()
    cut = len(server['body']) // 3
    server['fail_first_after'] = cut
    assert run(server, paths) == dd.EXIT_OK
    assert len(server['requests']) == 2
    assert 'Range' not in server['requests'][0]
    assert server['requests'][1].get('Range') == f'bytes={cut}-', 'the second attempt resumes, not restarts'
    out = capsys.readouterr().out
    assert 'Attempt 1 of 3 failed' in out and 'Retrying' in out
    assert Path(paths['db']).read_bytes() == DB_BYTES


def test_content_length_mismatch_never_renames_part_and_exits_1(server, paths, capsys):
    server['body'] = make_zip()
    server['wrong_length'] = len(server['body']) + 500  # server promises more than it sends
    assert run(server, paths) == dd.EXIT_FAILED
    assert not os.path.exists(paths['zip']), 'a short download must not become the archive'
    assert os.path.exists(paths['zip'] + '.part'), 'the partial file is kept for a resume'
    assert not os.path.exists(paths['db'])
    assert len(server['requests']) == 3, 'three attempts'
    out = capsys.readouterr().out
    assert 'Download incomplete' in out and 'Manual download' in out and '.part' in out


def test_unreachable_server_exits_1_after_retries(paths, capsys, monkeypatch):
    monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')
    # Bind a port and close it so nothing listens there.
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    rc = dd.run(zip_url=f'http://127.0.0.1:{port}/x.zip', zip_path=paths['zip'], db_path=paths['db'],
                sha_path=paths['sha'], backoff=0.0, timeout=2)
    assert rc == dd.EXIT_FAILED
    assert 'failed after 3 attempts' in capsys.readouterr().out


# --------------------------------------------------------------------------- verification

def test_hash_mismatch_exits_2_moves_db_aside_and_prints_both_hashes(server, paths, capsys):
    other = DB_BYTES[:-1] + b'\x00'
    server['body'] = make_zip(content=other)
    assert run(server, paths) == dd.EXIT_HASH_MISMATCH
    assert not os.path.exists(paths['db']), 'a file that fails verification is not left in place'
    assert Path(paths['db'] + '.unverified').read_bytes() == other
    assert os.path.exists(paths['zip']), 'the archive is kept for inspection'
    out = capsys.readouterr().out
    assert hashlib.sha256(DB_BYTES).hexdigest() in out
    assert hashlib.sha256(other).hexdigest() in out
    assert 'MISMATCH' in out


def test_real_data_sha256_file_parses():
    assert len(dd.expected_sha256()) == 64
    assert dd.expected_sha256() == '04f5ab8bff6880a8ee76b4a825a66b5f4db0b800dc5971a919cb743251a965a8'


def test_member_selected_by_exact_name(server, paths, capsys):
    # A .sqlite member with another name (what the old code would have taken) is not accepted.
    server['body'] = make_zip(member='Data/OTHER.sqlite')
    assert run(server, paths) == dd.EXIT_FAILED
    assert not os.path.exists(paths['db'])
    out = capsys.readouterr().out
    assert dd.ZIP_MEMBER in out and 'not found' in out


def test_member_name_matches_the_real_archive_layout():
    assert dd.ZIP_MEMBER == 'Data/FPA_FOD_20221014.sqlite'
    assert dd.DB_FILENAME == os.path.basename(dd.ZIP_MEMBER)


def test_extract_uses_exact_member_even_with_decoy_first(server, paths):
    server['body'] = make_zip(extra=[('Data/AAA_first.sqlite', b'decoy')])
    assert run(server, paths) == dd.EXIT_OK
    assert Path(paths['db']).read_bytes() == DB_BYTES


# --------------------------------------------------------------------------- disk space

def test_insufficient_disk_space_aborts_before_writing(server, paths, capsys, monkeypatch):
    server['body'] = make_zip()
    Usage = shutil.disk_usage(os.getcwd()).__class__
    monkeypatch.setattr(dd.shutil, 'disk_usage', lambda p: Usage(total=1, used=0, free=1000))
    assert run(server, paths) == dd.EXIT_FAILED
    assert not os.path.exists(paths['zip']) and not os.path.exists(paths['db'])
    part = paths['zip'] + '.part'
    assert not os.path.exists(part) or os.path.getsize(part) == 0
    assert 'free disk space' in capsys.readouterr().out


def test_insufficient_disk_space_for_extraction(server, paths, capsys, monkeypatch):
    server['body'] = make_zip()
    Usage = shutil.disk_usage(os.getcwd()).__class__
    real = shutil.disk_usage
    calls = []

    def fake(p):
        calls.append(p)
        return real(p) if len(calls) == 1 else Usage(total=1, used=0, free=0)
    monkeypatch.setattr(dd.shutil, 'disk_usage', fake)
    assert run(server, paths) == dd.EXIT_FAILED
    assert os.path.exists(paths['zip']), 'the archive was downloaded'
    assert not os.path.exists(paths['db']) and not os.path.exists(paths['db'] + '.part')
    assert 'the extraction' in capsys.readouterr().out
