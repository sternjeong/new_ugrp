"""Audit support for the user's student-count and office-location examples.

This is a marker audit, not semantic validation or an embedding-performance test.
No matched text or identifying information is written to the result.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"
PATTERNS = {
    "office_location_marker": r"\b(?:office|room)\b|연구실\s*위치|사무실",
    "people_marker": r"\b(?:members|students|people)\b|대학원생|구성원",
    "possible_numeric_people_marker": (
        r"(?:대학원생|graduate students?|Ph\.?D\.? students?|master.?s students?|연구원|members?)"
        r"\s*(?:[:：]|은|는|약|총|of)?\s*\d{1,3}|\d{1,3}\s*(?:명|students?|members?)"
    ),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    labs_path = ROOT / "final_labs.jsonl"
    frame_path = DIR / "frame.json"
    frame = json.loads(frame_path.read_text(encoding="utf-8"))
    labs = {"lab:" + row["advisor_id"]: row for row in
            (json.loads(line) for line in labs_path.read_text(encoding="utf-8").splitlines())}
    buckets = {k: [lid for component in components for lid in component["lab_ids"]]
               for k, components in frame["buckets"].items()}
    buckets["all_holdout"] = [lid for name in frame["buckets"] for lid in buckets[name]]
    assert len(buckets["all_holdout"]) == len(set(buckets["all_holdout"])) == 180
    report = {"status": "posthoc_regex_support_audit_not_performance_test",
              "source_sha256": {"final_labs.jsonl": sha(labs_path), "frame.json": sha(frame_path),
                                "script": sha(Path(__file__))},
              "meaning": "Regex hits may include false positives and omit true mentions; no text spans were adjudicated.",
              "buckets": {}}
    for name, ids in buckets.items():
        assert all(lid in labs for lid in ids)
        rows = [labs[lid] for lid in ids]
        report["buckets"][name] = {"professor_rows": len(rows),
                                    "nonempty_lab_mates": sum(bool(row["lab_mates"]) for row in rows),
                                    "intro_marker_rows": {key: sum(bool(re.search(pattern, row.get("research_intro") or "", re.I))
                                                              for row in rows) for key, pattern in PATTERNS.items()}}
    (DIR / "specific_noise_support_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
