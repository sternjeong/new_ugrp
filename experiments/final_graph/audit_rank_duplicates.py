"""Measure exact-content crowding without treating candidate groups as aliases."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--methods", default="b0_old,b0_expanded,b1",
                        help="comma-separated ranking keys; defaults to relation methods")
    args = parser.parse_args()
    eligibility = json.loads((ROOT / "experiments/final_graph/results/complete_subset_v1.json").read_text())
    eligible_rows = set(eligibility["eligible_course_source_rows"])
    groups = json.loads((ROOT / "experiments/final_graph/results/course_identity_candidates.json").read_text())
    code_to_group = {}
    for group in groups["groups"]:
        members = [item for item in group["members"] if item["source_row"] in eligible_rows]
        if group["reason"] != "identical_title_and_teaching_text" or len(members) < 2:
            continue
        for item in members:
            code_to_group["course:" + item["course_code"].strip().upper()] = group["content_group_candidate"]
    rows = json.loads(args.rankings.read_text(encoding="utf-8"))
    result = {"status": "candidate_content_crowding_only", "labs": len(rows),
              "eligible_group_rows": len(code_to_group), "method": {}}
    for method in args.methods.split(","):
        count = Counter()
        examples = []
        for row in rows:
            top = row[method][:5]
            keys = [code_to_group.get(item["course_id"], item["course_id"]) for item in top]
            duplicate = len(keys) - len(set(keys))
            if duplicate:
                count["labs_with_duplicate_content_top5"] += 1
                count["duplicate_slots_top5"] += duplicate
                examples.append({"lab_id": row["lab_id"], "courses": [item["course_id"] for item in top]})
        result["method"][method] = {"counts": dict(count), "examples": examples}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
