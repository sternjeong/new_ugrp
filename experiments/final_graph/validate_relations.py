"""Check that every generated relation assertion points to the source text."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELD = re.compile(r"^representative_papers\[(\d+)\]\.(title|abstract)$")


def value(row: dict, path: str) -> str:
    match = FIELD.fullmatch(path)
    if match:
        return row["representative_papers"][int(match.group(1))][match.group(2)] or ""
    return row[path] or ""


def visible(span: tuple[int, int], field: str, text: str) -> bool:
    start, end = span
    if field == "research_intro":
        return end <= min(len(text), 6000) or start >= max(0, len(text) - 2000)
    match = FIELD.fullmatch(field)
    if match:
        return int(match.group(1)) < 5 and (match.group(2) == "title" or end <= 800)
    limit = {"description": 2000, "Lesson Objectives": 2000, "Lecture progress plan": 4000}.get(field)
    return limit is None or end <= limit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    files = {}
    for name in ("final_courses.jsonl", "final_labs.jsonl"):
        path = ROOT / name
        files[name] = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()],
                       hashlib.sha256(path.read_bytes()).hexdigest())
    seen = set()
    counts = {}
    for number, line in enumerate((args.out / "assertions.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        item = json.loads(line)
        if item["assertion_id"] in seen:
            raise ValueError(f"duplicate assertion id at {number}")
        seen.add(item["assertion_id"])
        src = item["source"]
        rows, digest = files[src["source_file"]]
        if digest != src["source_sha256"]:
            raise ValueError(f"source hash mismatch at {number}")
        raw = value(rows[src["source_row"] - 1], src["source_field"])
        start, end = src["span"]
        if not (0 <= start < end <= len(raw)) or raw[start:end] != item["evidence_text"]:
            raise ValueError(f"evidence span mismatch at {number}")
        if not visible((start, end), src["source_field"], raw):
            raise ValueError(f"evidence outside judge packet window at {number}")
        counts[item["predicate"]] = counts.get(item["predicate"], 0) + 1
    result = {"valid": True, "assertions": len(seen), "predicate_counts": counts}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
