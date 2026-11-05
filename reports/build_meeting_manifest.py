"""Collect exact local evidence hashes for the dated meeting PDF."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FILES = [
    "final_courses.jsonl", "final_labs.jsonl",
    "docs/analysis/FINAL_DATASET_SCHEMA_V2_DECISION.md",
    "experiments/final_graph/results/complete_subset_v1.json",
    "experiments/final_graph/results/rich_split_v1.json",
    "experiments/final_graph/results/staging_v2_validation.json",
    "experiments/final_graph/results/holdout_relevance_v1/analysis.json",
    "experiments/final_graph/results/bge_top1_relevance_v1/analysis.json",
    "experiments/final_graph/results/bge_top5_extension_v1/analysis.json",
    "experiments/final_graph/results/bge_top5_extension_v1/label_agreement.json",
    "experiments/final_graph/results/bge_top5_extension_v1/duplicate_structure.json",
    "experiments/final_graph/JUDGE_REVIEWS_2026-10-15.md",
    "experiments/final_graph/results/query_rich_v3/analysis.json",
    "experiments/final_graph/results/query_rich_v3/audit_addendum.json",
    "experiments/final_graph/results/reason_rich_v2/analysis.json",
    "experiments/final_graph/results/ab_rich_v2/analysis.json",
    "experiments/final_graph/results/feedback_rich_v3/analysis.json",
    "reports/final_dataset_meeting_2026-10-15.md",
    "reports/report.css",
    "reports/final_dataset_meeting_2026-10-15.pdf",
]


def main():
    missing = [name for name in FILES if not (ROOT / name).exists()]
    if missing:
        raise FileNotFoundError(f"meeting report incomplete; missing: {missing}")
    out = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}
    target = REPORTS / "final_dataset_meeting_2026-10-15_manifest.json"
    target.write_text(json.dumps({"sha256": out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
