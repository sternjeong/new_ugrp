"""Grades of the 50-query panel (original, Qwen re-run, namesake-fix re-run) merged per query and lab."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'experiments/engine_strategies_20261109'


def load():
    queries = json.loads((BASE / 'queries.json').read_text())
    grades, votes = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for q in queries:
        for j in range(1, 6):
            r = json.loads((BASE / 'calls' / f"{q['id']}_j{j}.json").read_text())
            votes[q['id']].append(r['value']['should_recommend'])
            for g in r['value']['grades']:
                grades[q['id']][r['key'][g['label']]].append(g['grade'])
        for folder, field in ((BASE / 'qwen/calls', 'new'), (BASE / 'namesake_fix/calls', 'fresh')):
            for j in range(1, 6):
                path = folder / f"{q['id']}_j{j}.json"
                if path.exists():
                    r = json.loads(path.read_text())
                    for g in r['value']['grades']:
                        if r['key'][g['label']] in r[field]:
                            grades[q['id']][r['key'][g['label']]].append(g['grade'])
    gain = {k: {l: sum(v) / len(v) for l, v in x.items()} for k, x in grades.items()}
    should = {k: sum(v) > len(v) / 2 for k, v in votes.items()}
    controls = {k: v['controls'] for k, v in json.loads((BASE / 'pools.json').read_text()).items()}
    return queries, gain, should, controls
