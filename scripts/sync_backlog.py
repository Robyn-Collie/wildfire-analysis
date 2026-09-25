"""
Mirror BACKLOG.md to GitHub issues.

Usage:
    GITHUB_TOKEN=... python scripts/sync_backlog.py            # create or update issues
    GITHUB_TOKEN=... python scripts/sync_backlog.py --dry-run  # print what would change

Each "## Epic N: Title" becomes an issue titled "Epic N: Title" labelled epic:N-<slug>.
Each "### [S-N.M] Title" becomes an issue titled "[S-N.M] Title" labelled with its epic,
its priority (P0/P1/P2) and its type, assigned to milestone N (one milestone per epic).
Stories whose Status starts with "Done" are closed as completed. Issue numbers are written
back into BACKLOG.md as "- Issue: #k" lines. The script is idempotent: it matches existing
issues by title prefix and updates them.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

REPO = 'Robyn-Collie/wildfire-analysis'
API = f'https://api.github.com/repos/{REPO}'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKLOG = os.path.join(ROOT, 'BACKLOG.md')

EPIC_SLUGS = {1: 'reproducibility', 2: 'honest-evaluation', 3: 'weather-and-fuels', 4: 'large-fire-risk',
              5: 'descriptive-in-code', 6: 'conservation-lens', 7: 'communication'}
# Story type labels (the story format has no Type field, so they live here).
TYPES = {
    'S-1.1': 'infra', 'S-1.2': 'infra', 'S-1.3': 'infra', 'S-1.4': 'bug', 'S-1.5': 'docs', 'S-1.6': 'infra',
    'S-1.7': 'infra', 'S-1.8': 'infra',
    'S-2.1': 'method', 'S-2.2': 'method', 'S-2.3': 'method', 'S-2.4': 'docs', 'S-2.5': 'docs', 'S-2.6': 'method',
    'S-2.7': 'docs', 'S-2.8': 'method',
    'S-3.1': 'data', 'S-3.2': 'method', 'S-3.3': 'data', 'S-3.4': 'data', 'S-3.5': 'data',
    'S-4.1': 'method', 'S-4.2': 'method', 'S-4.3': 'docs', 'S-4.4': 'method', 'S-4.5': 'method', 'S-4.6': 'infra',
    'S-5.1': 'method', 'S-5.2': 'data', 'S-5.3': 'method', 'S-5.4': 'docs', 'S-5.5': 'method', 'S-5.6': 'data',
    'S-5.7': 'docs',
    'S-6.1': 'data', 'S-6.2': 'data', 'S-6.3': 'data', 'S-6.4': 'data', 'S-6.5': 'data', 'S-6.6': 'docs',
    'S-7.1': 'docs', 'S-7.2': 'infra', 'S-7.3': 'docs', 'S-7.4': 'docs', 'S-7.5': 'infra', 'S-7.6': 'docs',
    'S-7.7': 'infra',
}


def gh(method, path, body=None):
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if not token:
        sys.exit('Set GITHUB_TOKEN.')
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def parse(text):
    epics, stories = [], []
    epic = None
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^## Epic (\d+): (.+)$', line)
        if m:
            epic = {'n': int(m.group(1)), 'title': m.group(2).strip(), 'body_lines': [], 'line': i}
            epics.append(epic)
            i += 1
            while i < len(lines) and not lines[i].startswith('### ') and not lines[i].startswith('## '):
                epic['body_lines'].append(lines[i])
                i += 1
            continue
        m = re.match(r'^### \[(S-(\d+)\.\d+)\] (.+)$', line)
        if m:
            story = {'id': m.group(1), 'epic': int(m.group(2)), 'title': m.group(3).strip(), 'line': i,
                     'fields': [], 'field_lines': {}}
            i += 1
            while i < len(lines) and lines[i].startswith('- '):
                story['fields'].append(lines[i])
                key = lines[i][2:].split(':', 1)[0].strip()
                story['field_lines'][key] = i
                i += 1
            stories.append(story)
            continue
        i += 1
    return epics, stories


def field(story, key):
    for f in story['fields']:
        if f.startswith(f'- {key}:'):
            return f.split(':', 1)[1].strip()
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    text = open(BACKLOG, encoding='utf-8').read()
    epics, stories = parse(text)
    milestones = {m['title']: m['number'] for m in gh('GET', '/milestones?state=all&per_page=100')}
    existing = {}
    page = 1
    while True:
        batch = gh('GET', f'/issues?state=all&per_page=100&page={page}')
        if not batch:
            break
        for it in batch:
            if 'pull_request' in it:
                continue
            existing[it['title']] = it
            m = re.match(r'^(\[S-\d+\.\d+\]|Epic \d+:)', it['title'])
            if m:
                existing.setdefault(m.group(1), it)
        page += 1

    lines = text.split('\n')
    changes = 0
    epic_numbers = {}
    for e in epics:
        title = f"Epic {e['n']}: {e['title']}"
        body = '\n'.join(e['body_lines']).strip() + '\n\nMirrored from `BACKLOG.md`. Stories are the issues labelled `epic:%d-%s`.' % (e['n'], EPIC_SLUGS[e['n']])
        payload = {'title': title, 'body': body, 'labels': [f"epic:{e['n']}-{EPIC_SLUGS[e['n']]}"],
                   'milestone': milestones.get(title)}
        key = f"Epic {e['n']}:"
        if key in existing:
            num = existing[key]['number']
            if not args.dry_run:
                gh('PATCH', f'/issues/{num}', payload)
        else:
            num = None if args.dry_run else gh('POST', '/issues', payload)['number']
        epic_numbers[e['n']] = num
        print(f'{title} -> #{num}')
        changes += 1

    for s in stories:
        title = f"[{s['id']}] {s['title']}"
        status = field(s, 'Status')
        prio = re.search(r'\bP[012]\b', field(s, 'Priority'))
        labels = [f"epic:{s['epic']}-{EPIC_SLUGS[s['epic']]}", prio.group(0) if prio else 'P1',
                  f"type:{TYPES.get(s['id'], 'method')}"]
        body_fields = [f for f in s['fields'] if not f.startswith('- Issue:')]
        body = '\n'.join(body_fields) + f"\n\nEpic: #{epic_numbers.get(s['epic'])}. Mirrored from `BACKLOG.md` ({s['id']})."
        payload = {'title': title, 'body': body, 'labels': labels,
                   'milestone': milestones.get(f"Epic {s['epic']}: " + next(e['title'] for e in epics if e['n'] == s['epic']))}
        key = f"[{s['id']}]"
        if key in existing:
            num = existing[key]['number']
            if not args.dry_run:
                gh('PATCH', f'/issues/{num}', payload)
        else:
            num = None if args.dry_run else gh('POST', '/issues', payload)['number']
        if num and status.startswith('Done') and not status.startswith('Done (computation)'):
            if not args.dry_run:
                gh('PATCH', f'/issues/{num}', {'state': 'closed', 'state_reason': 'completed'})
        print(f'{title} [{status}] -> #{num}')
        issue_line = f'- Issue: #{num}' if num else '- Issue: (dry run)'
        if 'Issue' in s['field_lines']:
            lines[s['field_lines']['Issue']] = issue_line
        else:
            lines.insert(s['field_lines']['Status'] + 1, issue_line)
            # Shift later line indices.
            for later in stories:
                if later['line'] > s['line']:
                    later['line'] += 1
                    later['field_lines'] = {k: v + 1 for k, v in later['field_lines'].items()}
        changes += 1

    if not args.dry_run:
        open(BACKLOG, 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'{changes} items synced{" (dry run)" if args.dry_run else ""}.')


if __name__ == '__main__':
    main()
