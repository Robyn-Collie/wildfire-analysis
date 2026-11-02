"""Every page requests its data and asset scripts with a content-hash version (?v=...).

data/ is cached by browsers for a day (deploy/_headers). Without a version that changes with the file's
content, a returning visitor gets the new HTML with yesterday's data/claims.js and the charts come up empty.
Skipped when site/ has not been generated.
"""
import glob
import hashlib
import os
import re

import pytest

from test_claims_ledger import REPO

SITE = os.path.join(REPO, 'site')
REF = re.compile(r'(?:<script src|<link rel="stylesheet" href)="((?:data|assets)/[^"?#]+)(\?v=([0-9a-f]+))?"')


def pages():
    return sorted(glob.glob(os.path.join(SITE, '*.html')))


@pytest.mark.skipif(not pages(), reason='site/ not generated')
def test_data_and_asset_scripts_are_versioned_by_content():
    problems = []
    for path in pages():
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for m in REF.finditer(text):
            rel, version = m.group(1), m.group(3)
            if not rel.endswith(('.js', '.css')):
                continue
            target = os.path.join(SITE, rel)
            if not os.path.exists(target):
                problems.append(f'{os.path.basename(path)}: {rel} does not exist')
                continue
            if version is None:
                problems.append(f'{os.path.basename(path)}: {rel} has no ?v=')
                continue
            with open(target, 'rb') as fh:
                if not hashlib.sha256(fh.read()).hexdigest().startswith(version):
                    problems.append(f'{os.path.basename(path)}: {rel}?v={version} does not match the file')
    assert not problems, '\n'.join(problems[:20])
