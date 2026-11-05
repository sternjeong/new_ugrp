"""Reproducible structural audit of the two final recommendation inputs.

Run from the repository root: python3 experiments/final_graph/audit_inputs.py
The script only reads source files and prints JSON; redirect output to save a snapshot.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILES = ("final_courses.jsonl", "final_labs.jsonl")


def empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def audit_file(name: str) -> tuple[list[dict], dict]:
    path = ROOT / name
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{name}: non-object JSONL row")
    keys = sorted(set().union(*(row.keys() for row in rows)))
    field_stats = {}
    for key in keys:
        vals = [row.get(key) for row in rows]
        field_stats[key] = {
            "missing_key": sum(key not in row for row in rows),
            "empty": sum(empty(value) for value in vals),
            "types": dict(sorted(collections.Counter(type(value).__name__ for value in vals).items())),
        }
    return rows, {
        "path": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": len(rows),
        "fields": field_stats,
    }


def main() -> None:
    courses, course_report = audit_file(FILES[0])
    labs, lab_report = audit_file(FILES[1])
    codes = collections.Counter(row["course_code"] for row in courses)
    groups = collections.Counter(row["lab_group"] for row in labs if row["lab_group"])
    course_report["identity"] = {
        "unique_codes": len(codes),
        "duplicate_codes": {key: count for key, count in sorted(codes.items()) if count > 1},
        "semesters": dict(sorted(collections.Counter(row["_semester"] for row in courses).items())),
    }
    lab_report["identity"] = {
        "unique_advisor_ids": len({row["advisor_id"] for row in labs}),
        "nonempty_lab_groups": sum(groups.values()),
        "unique_lab_groups": len(groups),
        "repeated_lab_groups": {key: count for key, count in sorted(groups.items()) if count > 1},
    }
    lab_report["papers"] = {}
    for field in ("site_papers", "professor_papers", "representative_papers"):
        papers = [paper for row in labs for paper in row[field]]
        lab_report["papers"][field] = {
            "items": len(papers),
            "with_title": sum(bool(paper.get("title")) for paper in papers),
            "with_abstract": sum(bool(paper.get("abstract")) for paper in papers),
            "with_doi": sum(bool(paper.get("doi")) for paper in papers),
        }
    print(json.dumps({"courses": course_report, "labs": lab_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
