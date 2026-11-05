"""Map the former 4-department lab IDs (`lab_xxxxxxxxxxxx`) to the current curated lab IDs.

Accounts, reviews and threads created before the 2026-11-04 data switch still carry the old IDs, so
graduates and reviews disappeared from lab pages. A legacy lab maps only when its professor's Korean
name identifies exactly one current lab (homepage URL breaks ties); everything else stays unmapped.

Usage: python3 tools/build_legacy_lab_aliases.py  → writes data/sunwoo/legacy_lab_aliases.json
"""
from collections import defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sunwoo'
LEGACY = DATA / 'legacy' / 'mvp-4dept' / 'labs.jsonl'
OUT = DATA / 'legacy_lab_aliases.json'


def url_key(url):
    return re.sub(r'^https?://(www\.)?|/+$', '', (url or '').strip().lower())


def main():
    current = [json.loads(line) for line in (DATA / 'app_profiles.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    by_name, by_url = defaultdict(list), defaultdict(list)
    for p in current:
        for name in p['professors']:
            if name:
                by_name[name.split(' (')[0].strip()].append(p['lab_id'])
        by_url[url_key(p.get('lab_url'))].append(p['lab_id'])
    aliases, unmapped = {}, {}
    for line in LEGACY.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        lab = json.loads(line)
        name = lab['professor_name'].split(' (')[0].strip()
        candidates = by_name.get(name, [])
        if len(candidates) > 1:
            candidates = [c for c in candidates if c in by_url.get(url_key(lab['lab_url']), [])] or candidates
        if len(candidates) == 1:
            aliases[lab['record_id']] = candidates[0]
        else:
            unmapped[lab['record_id']] = f'{name}: ' + ('현재 정제본에 없음' if not candidates else f'후보 {len(candidates)}곳으로 모호함')
    OUT.write_text(json.dumps({'_about': '이전 4개 학과 연구실 ID → 현재 정제본 연구실 ID. 교수 이름이 정확히 한 곳과 일치할 때만 연결한다. tools/build_legacy_lab_aliases.py로 생성.',
                               'aliases': aliases, 'unmapped': unmapped}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(aliases)}곳 연결, {len(unmapped)}곳 미연결 → {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
