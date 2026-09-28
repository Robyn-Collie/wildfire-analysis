"""The claims-ledger test for the generated site (backlog S-1.6, extended to site/).

Every number on a site page that opens a definition is a ``<button class="q" data-claim="ID">TEXT</button>``.
This test checks, for every such button in site/*.html, that

1. the claim id exists in a committed ledger (``outputs/claims*.json``);
2. if the button text contains a number, that number matches a value of the claim at the precision it is
   written with (same matcher as the README test, which also accepts a number written in millions or thousands).

It runs on the committed site, so regenerating the ledger without rebuilding the site, or editing a page by hand,
fails. Skipped when site/ has not been generated.
"""
import glob
import html
import os
import re

import pytest

from test_claims_ledger import REPO, flatten, load_ledger, matches, written_numbers

SITE = os.path.join(REPO, 'site')
BUTTON = re.compile(r'<button type="button" class="q" data-claim="([^"]+)">(.*?)</button>', re.S)


def buttons():
    for path in sorted(glob.glob(os.path.join(SITE, '*.html'))):
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for m in BUTTON.finditer(text):
            yield os.path.basename(path), html.unescape(m.group(1)), html.unescape(m.group(2))


@pytest.fixture(scope='module')
def ledger():
    led = load_ledger()
    if not led:
        pytest.skip('no outputs/claims*.json committed on this branch')
    return led


@pytest.fixture(scope='module')
def site_buttons():
    b = list(buttons())
    if not b:
        pytest.skip('site/ has not been generated')
    return b


def test_site_cites_many_claims(site_buttons):
    assert len(site_buttons) >= 500


def test_every_site_claim_exists(site_buttons, ledger):
    missing = sorted({(p, cid) for p, cid, _ in site_buttons if cid not in ledger})
    assert not missing, f'site buttons cite claims in no ledger: {missing[:20]}'


def _matches_any_scale(text: str, values: list[float]) -> bool:
    try:  # "1e-05"
        x = float(text.strip())
        if any(abs(x - v) <= 1e-12 + 1e-6 * abs(v) for v in values):
            return True
    except ValueError:
        pass
    # "105.64M", "3.2K": the site's compact form
    text = re.sub(r'(\d)M\b', r'\1 million', text)
    text = re.sub(r'(\d)K\b', r'\1 thousand', text)
    written = written_numbers(text)
    if matches(written, values):
        return True
    # "2.72 million acres" where the claim itself is stored in millions
    unscaled = written_numbers(re.sub(r'\b(million|thousand|billion)\b', '', text))
    return matches(unscaled, values)


def test_every_site_number_matches_its_claim(site_buttons, ledger):
    bad = []
    for page, cid, text in site_buttons:
        if cid not in ledger or not re.search(r'\d', text):
            continue
        values = flatten(ledger[cid]['value'])
        if isinstance(ledger[cid].get('n'), (int, float)):
            values.append(float(ledger[cid]['n']))  # "n = 2,303,566" cites the claim's own n
        values += [1 - v for v in values if 0 <= v <= 1]  # "known for 53.6%" is one minus the missing share
        if not _matches_any_scale(text, values):
            bad.append(f'{page}: {cid}: {text!r}')
    assert not bad, f'{len(bad)} site numbers do not match their claim:\n' + '\n'.join(bad[:40])


def test_a_hand_edited_site_number_fails():
    assert _matches_any_scale('105.64M', [105_640_123.0])
    assert not _matches_any_scale('106.64M', [105_640_123.0])
    assert _matches_any_scale('2.72 million acres', [2.72])
    assert _matches_any_scale('53.6%', [0.4638, 1 - 0.4638])
    assert not _matches_any_scale('54.6%', [0.4638, 1 - 0.4638])
