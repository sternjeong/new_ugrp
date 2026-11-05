"""Freeze an evidence-rich conditional evaluation frame before relation labels."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
ORIGINAL_SPLIT_SHA256 = "3733e68764c1d7028e041da7235459ad8c6d7c745989498389217720fa11d4fc"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    eligibility_path = RESULTS / "complete_subset_v1.json"
    original_path = RESULTS / "split_v1.json"
    if sha(original_path) != ORIGINAL_SPLIT_SHA256:
        raise ValueError("original split changed after preregistration")
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    original = json.loads(original_path.read_text(encoding="utf-8"))
    for name, expected in eligibility["source_hashes"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"source changed since eligibility audit: {name}")
    eligible_ids = {item["advisor_id"] for item in eligibility["eligible_labs"]}
    if len(eligible_ids) != eligibility["eligible"]["lab"]:
        raise ValueError("duplicate or missing eligible advisor id")
    course_rows = set(eligibility["course_inspection_sample"]["source_rows"])
    if len(course_rows) != eligibility["course_inspection_sample"]["n"]:
        raise ValueError("duplicate course inspection row")
    assignments = []
    for component in original["assignments"]:
        advisors = sorted(eligible_ids.intersection(component["advisor_ids"]))
        if not advisors:
            continue
        # Previous development components remain development. All other
        # components become held out; this does not relabel by model outcome.
        split = "dev" if component["split"] == "dev" else "holdout"
        assignments.append({"component_id": component["component_id"], "advisor_ids": advisors,
                            "department_stratum": component["department_stratum"],
                            "split": split, "previous_split": component["split"]})
    if {aid for c in assignments for aid in c["advisor_ids"]} != eligible_ids:
        raise ValueError("eligible frame coverage mismatch")
    result = {"version": 1, "status": "frozen_before_relation_labels",
              "eligibility_sha256": sha(eligibility_path), "original_split_sha256": sha(original_path),
              "source_hashes": eligibility["source_hashes"],
              "eligible_course_rows": eligibility["eligible"]["course"],
              "eligible_lab_rows": len(eligible_ids),
              "component_counts": dict(Counter(c["split"] for c in assignments)),
              "lab_row_counts": dict(Counter(c["split"] for c in assignments for _ in c["advisor_ids"])),
              "prior_test_reused_without_text_review": sum(c["previous_split"] == "test" for c in assignments),
              "candidate_universe": "all 941 eligible course rows, not the 273-row schema inspection sample",
              "inference_unit": "shared-evidence component; score each advisor row, average inside component",
              "generalization_scope": "eligible text-rich subset only; no claim for excluded rows",
              "assignments": sorted(assignments, key=lambda c: c["component_id"])}
    output = RESULTS / "rich_split_v1.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "assignments"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
