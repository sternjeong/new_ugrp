"""Freeze duplicate-evidence components and dev/test groups for the relation pilot."""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261014


def norm_text(value: str | None, *, folded: bool = False) -> str:
    if not value:
        return ""
    result = " ".join(unicodedata.normalize("NFC", value.replace("\r\n", "\n")).split())
    return result.casefold() if folded else result


def norm_url(value: str | None) -> str:
    if not value:
        return ""
    candidate = value.strip()
    parsed = urlsplit(candidate if "://" in candidate else "https://" + candidate)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port and port not in (80, 443):
        host += f":{port}"
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return host + path + ("?" + query if query else "")


def paper_keys(paper: dict) -> list[str]:
    keys = []
    doi = norm_text(paper.get("doi"), folded=True).removeprefix("https://doi.org/")
    if doi:
        keys.append("doi:" + doi)
    openalex = norm_text(paper.get("openalex_id"), folded=True)
    if openalex:
        keys.append("openalex:" + openalex.rsplit("/", 1)[-1])
    title = norm_text(paper.get("title"), folded=True)
    if title:
        keys.append("title:" + title)
    return keys


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def root(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def join(self, left: int, right: int) -> None:
        a, b = self.root(left), self.root(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def allocate(capacities: dict[str, int], target: int, minimum: int) -> dict[str, int]:
    quota = {key: min(minimum, count) for key, count in capacities.items()}
    if sum(quota.values()) > target:
        raise ValueError("minimum quotas exceed sample target")
    remaining = target - sum(quota.values())
    spare = {key: capacities[key] - quota[key] for key in capacities if capacities[key] > quota[key]}
    if remaining > sum(spare.values()):
        raise ValueError("not enough components")
    if not remaining:
        return quota
    total = sum(spare.values())
    ideal = {key: remaining * value / total for key, value in spare.items()}
    for key, value in ideal.items():
        quota[key] += min(spare[key], int(value))
    residual = target - sum(quota.values())
    order = sorted(spare, key=lambda key: (-(ideal[key] - int(ideal[key])), key))
    for key in order:
        if not residual:
            break
        if quota[key] < capacities[key]:
            quota[key] += 1
            residual -= 1
    if residual:
        raise ValueError("largest remainder allocation failed")
    return quota


def main() -> None:
    path = ROOT / "final_labs.jsonl"
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    uf = UnionFind(len(rows))
    owner: dict[str, int] = {}
    for index, row in enumerate(rows):
        keys = set()
        for value in [row.get("lab_group"), row.get("lab_url"), *(item.get("url") for item in row["urls"])]:
            normalized = norm_url(value)
            if normalized:
                keys.add("url:" + normalized)
        intro = norm_text(row.get("research_intro"))
        if intro:
            keys.add("intro:" + hashlib.sha256(intro.encode()).hexdigest())
        for paper in row["representative_papers"]:
            keys.update("paper:" + key for key in paper_keys(paper))
        for key in keys:
            if key in owner:
                uf.join(index, owner[key])
            else:
                owner[key] = index
    components: dict[int, list[int]] = collections.defaultdict(list)
    for index in range(len(rows)):
        components[uf.root(index)].append(index)
    info = []
    for members in components.values():
        ids = sorted(rows[index]["advisor_id"] for index in members)
        departments = []
        for index in members:
            row = rows[index]
            department = (row.get("professor") or {}).get("department") or (row["departments"][0] if row["departments"] else "missing")
            departments.append(department)
        counts = collections.Counter(departments)
        dept = sorted(counts, key=lambda key: (-counts[key], key))[0]
        info.append({"component_id": "component:" + hashlib.sha256("|".join(ids).encode()).hexdigest()[:20],
                     "advisor_ids": ids, "department_stratum": dept})
    by_dept: dict[str, list[dict]] = collections.defaultdict(list)
    for component in info:
        by_dept[component["department_stratum"]].append(component)
    rng = random.Random(SEED)
    for dept in sorted(by_dept):
        by_dept[dept].sort(key=lambda item: item["component_id"])
        rng.shuffle(by_dept[dept])
    test_quota = allocate({key: len(value) for key, value in by_dept.items()}, 60, 2)
    remaining = {key: len(value) - test_quota[key] for key, value in by_dept.items()}
    dev_quota = allocate(remaining, 30, 1)
    for dept, values in by_dept.items():
        for index, component in enumerate(values):
            component["split"] = "test" if index < test_quota[dept] else "dev" if index < test_quota[dept] + dev_quota[dept] else "unused"
    info.sort(key=lambda item: item["component_id"])
    summary = {"seed": SEED, "source_sha256": source_hash, "components": len(info),
               "component_counts": dict(collections.Counter(item["split"] for item in info)),
               "row_counts": dict(collections.Counter(item["split"] for item in info for _ in item["advisor_ids"])),
               "departments": {key: {"available": len(by_dept[key]), "test": test_quota[key], "dev": dev_quota[key]}
                               for key in sorted(by_dept)}, "assignments": info}
    output = ROOT / "experiments/final_graph/results/split_v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "assignments"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
