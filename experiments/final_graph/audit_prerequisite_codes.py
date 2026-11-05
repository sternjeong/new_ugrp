"""Find explicit course-code mentions in eligible course prerequisite fields."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from audit_prerequisite_knowledge import context, qualifier

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}\s?-?\d{3}[A-Z]?(?![A-Za-z0-9])", re.IGNORECASE)


def main():
    eligibility_path = RESULTS / "complete_subset_v1.json"
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    allowed = set(eligibility["eligible_course_source_rows"])
    source_path = ROOT / "final_courses.jsonl"
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if source_hash != eligibility["source_hashes"]["final_courses.jsonl"]:
        raise ValueError("source changed since eligibility audit")
    rows = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()]
    known = {row["course_code"].strip().upper() for row in rows}
    output = RESULTS / "prerequisite_code_candidates.jsonl"
    seen = set()
    occurrences = 0
    with output.open("w", encoding="utf-8") as stream:
        for row_no, row in enumerate(rows, 1):
            if row_no not in allowed:
                continue
            current = row["course_code"].strip().upper()
            field = row["prerequisites"] or ""
            for match in PATTERN.finditer(field):
                code = re.sub(r"[ -]", "", match.group()).upper()
                if code not in known or code == current:
                    continue
                occurrences += 1
                key = (current, code)
                if key in seen:
                    continue
                seen.add(key)
                clause, clause_span = context(field, *match.span())
                item = {"subject_id": "course:" + current, "predicate": "prerequisite_course_code_mention",
                        "object_id": "course:" + code, "qualifier_candidate": qualifier(clause),
                        "source": {"source_file": "final_courses.jsonl", "source_sha256": source_hash,
                                   "source_row": row_no, "source_field": "prerequisites", "span": list(match.span())},
                        "evidence_text": match.group(), "context_text": clause,
                        "context_span": list(clause_span), "review_status": "unreviewed"}
                stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {"status": "unreviewed_prerequisite_field_code_mentions", "source_sha256": source_hash,
                "eligibility_sha256": hashlib.sha256(eligibility_path.read_bytes()).hexdigest(),
                "distinct_course_pairs": len(seen), "literal_occurrences": occurrences,
                "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    (RESULTS / "prerequisite_code_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
