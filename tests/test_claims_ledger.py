"""The claims-ledger test (backlog S-1.6).

The README tags every computed number with the claim it comes from, as an HTML comment right after
the sentence: ``... 26% of those acres <!-- claim:class_g.alaska_share_of_acres -->``. Experiment
results are tagged ``<!-- exp:E-004 -->``. This test checks that

1. every claim tag names a claim in one of the committed ledgers (``outputs/claims*.json``);
2. the text between the previous tag (or the start of the sentence) and the tag contains at least one
   number that matches a value of that claim at the precision it is written with (shares may be
   written as percentages, acres in millions or thousands, and so on), so editing a tagged number
   by hand, or regenerating the ledger with a different result, fails the test;
3. every experiment tag names an entry heading (``## E-004 ...``) in ``docs/EXPERIMENTS.md``.

It checks the README against the ledger, not the ledger against the data: the ledgers are
regenerated from the data by ``python -m analysis.*``, which CI does not run (no 1 GB download).
Untagged numbers are not checked; the review convention is that every computed number is tagged.
Limits: a segment passes when *any* of its numbers matches the claim, so a sentence that also states a
parameter that happens to equal a value in the claim could hide an edited result. Numbers written as cuts
("top 10%") are skipped for that reason; keep one tagged result per sentence where possible.
"""
import glob
import json
import math
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(REPO, 'README.md')
EXPERIMENTS = os.path.join(REPO, 'docs', 'EXPERIMENTS.md')
TAG = re.compile(r'<!--\s*(claim|exp):([A-Za-z0-9_.\-]+)\s*-->')
NUM = re.compile(r'(?<![A-Za-z0-9_.\-])[+\-−]?\d[\d,]*(?:\.\d+)?(?![\d])')
# Words after a number that scale it (the README writes "3.8 million acres", "+178,000 acres").
SCALES = {'million': 1e6, 'billion': 1e9, 'thousand': 1e3}


def load_ledger() -> dict:
    ledger = {}
    for path in sorted(glob.glob(os.path.join(REPO, 'outputs', 'claims*.json'))):
        with open(path, encoding='utf-8') as f:
            ledger.update(json.load(f))
    return ledger


def flatten(value) -> list[float]:
    out = []
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            out.append(float(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            if re.fullmatch(r'\d{4}', str(k)):  # year keys ("2010") are values the prose names
                out.append(float(k))
            out += flatten(v)
    elif isinstance(value, (list, tuple)):
        out.append(float(len(value)))  # "13 zero-record years" is the length of a list
        for v in value:
            out += flatten(v)
    elif isinstance(value, str):
        out += [float(m.replace(',', '')) for m in re.findall(r'\d[\d,]*(?:\.\d+)?', value)]
    return out


def written_numbers(segment: str) -> list[tuple[float, float, bool]]:
    """(value, tolerance, is_percent) for each number written in the segment."""
    out = []
    for m in NUM.finditer(segment):
        before = segment[max(0, m.start() - 6):m.start()].lower()
        if before.rstrip().endswith('top'):  # "top 10%" names a cut, not a result; never evidence
            continue
        tok = m.group(0).replace('−', '-').replace(',', '')
        x = float(tok)
        dec = len(tok.split('.')[1]) if '.' in tok else 0
        if dec:
            tol = 0.5 * 10 ** -dec
        else:  # an integer written as 178000 is rounded to its trailing zeros
            digits = tok.lstrip('+-')
            tz = len(digits) - len(digits.rstrip('0')) if digits.strip('0') else 0
            tol = 0.5 * 10 ** tz if tz else 0.5
        after = segment[m.end():m.end() + 12].lower()
        for word, scale in SCALES.items():
            if after.lstrip().startswith(word):
                x, tol = x * scale, tol * scale
        is_pct = after.startswith('%')
        out.append((x, tol, is_pct))
    return out


def matches(written, values) -> bool:
    for x, tol, is_pct in written:
        for v in values:
            candidates = [v, abs(v)]
            if is_pct or abs(v) <= 1.0:
                candidates += [100 * v, 100 * abs(v)]
            if any(abs(abs(x) - c) <= tol * 1.0000001 for c in candidates):
                return True
    return False


def tagged_segments(text: str):
    """Yield (kind, id, segment) where segment is the text the tag refers to."""
    prev_end = 0
    for m in TAG.finditer(text):
        seg_start = prev_end
        # A tag refers to its own sentence: cut at the last sentence end before it, unless an adjacent
        # tag shares the sentence (then the segment runs back to that tag).
        chunk = text[seg_start:m.start()]
        cut = max(chunk.rfind('. '), chunk.rfind('\n\n'), chunk.rfind(': '))
        if cut > 0 and chunk[cut + 1:].strip():
            chunk = chunk[cut + 1:]
        yield m.group(1), m.group(2), chunk
        # Adjacent tags (two in a row) share the same segment.
        if not text[m.end():m.end() + 6].lstrip().startswith('<!--'):
            prev_end = m.end()


@pytest.fixture(scope='module')
def readme() -> str:
    with open(README, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def ledger() -> dict:
    led = load_ledger()
    if not led:
        pytest.skip('no outputs/claims*.json committed on this branch')
    return led


def test_readme_has_claim_tags(readme):
    assert len(TAG.findall(readme)) >= 20, 'the README should tag its computed numbers'


def test_every_claim_tag_exists(readme, ledger):
    missing = sorted({i for k, i, _ in tagged_segments(readme) if k == 'claim' and i not in ledger})
    assert not missing, f'README cites claims that are in no outputs/claims*.json: {missing}'


def test_every_tagged_number_matches_its_claim(readme, ledger):
    bad = []
    for kind, cid, seg in tagged_segments(readme):
        if kind != 'claim' or cid not in ledger:
            continue
        written = written_numbers(seg)
        if not written:
            continue  # a tag on a qualitative sentence (e.g. a definition) cites without a number
        if not matches(written, flatten(ledger[cid]['value'])):
            bad.append((cid, ' '.join(seg.split())[-160:]))
    assert not bad, 'numbers that do not match their claim:\n' + '\n'.join(f'  {c}: ...{s}' for c, s in bad)


def test_every_experiment_tag_exists(readme):
    with open(EXPERIMENTS, encoding='utf-8') as f:
        headings = set(re.findall(r'^## (E-\d{3})', f.read(), flags=re.M))
    missing = sorted({i for k, i, _ in tagged_segments(readme) if k == 'exp' and i not in headings})
    assert not missing, f'README cites experiments with no entry in docs/EXPERIMENTS.md: {missing}'


def test_a_hand_edited_number_fails():
    """The matcher must reject a number that differs from the claim at the written precision."""
    values = flatten({'kendall_tau': 0.4335, 'kendall_p': 0.000746})
    assert matches(written_numbers('Kendall tau 0.43 (p = 0.0007)'), values)
    assert not matches(written_numbers('Kendall tau 0.53 (p = 0.0009)'), values)
    assert matches(written_numbers('26% of those acres'), flatten(0.2586))
    assert not matches(written_numbers('36% of those acres'), flatten(0.2586))
    assert matches(written_numbers('from 1.9 million to 3.8 million acres'), flatten({'a': 1881680.7, 'b': 3755382.5}))
    assert matches(written_numbers('+178,000 acres per year'), flatten({'theil_sen_slope': 177560.2}))
    assert not matches(written_numbers('+198,000 acres per year'), flatten({'theil_sen_slope': 177560.2}))
    # a cut named in the sentence ("top 10%") is not evidence for the result next to it
    capture = flatten({'rows': [{'top_10pct': 0.741}, {'top_10pct': 0.10}]})
    assert matches(written_numbers('its top 10% of scores held 74% of the fires'), capture)
    assert not matches(written_numbers('its top 10% of scores held 76% of the fires'), capture)
