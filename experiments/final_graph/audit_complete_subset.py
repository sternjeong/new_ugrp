"""Audit an information-rich analysis frame; never mutate the source JSONL."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/final_graph/results/complete_subset_v1.json"
SEED = 20261014


def rows(name):
    path = ROOT / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()], hashlib.sha256(path.read_bytes()).hexdigest()


def length(value):
    return len(re.sub(r"\s+", " ", value or "").strip())


def sample_size(population, error=0.05):
    # 95% Wald planning bound at p=.5 with finite-population correction.
    z2pq = 1.96 ** 2 * 0.25
    return math.ceil(population * z2pq / ((population - 1) * error ** 2 + z2pq))


def main():
    courses, course_hash = rows("final_courses.jsonl")
    labs, lab_hash = rows("final_labs.jsonl")
    good_courses = []
    course_reasons = Counter()
    for number, row in enumerate(courses, 1):
        reasons = []
        if not row["course_code"].strip() or not row["course_title"].strip():
            reasons.append("missing_identity")
        if length(row["description"]) < 100:
            reasons.append("short_description")
        if length(row["Lecture progress plan"]) < 100:
            reasons.append("short_plan")
        if reasons:
            course_reasons.update(reasons)
        else:
            good_courses.append((number, row))
    good_labs = []
    lab_reasons = Counter()
    for number, row in enumerate(labs, 1):
        reasons = []
        if not row["advisor_id"] or not (row["professor"] or {}).get("name"):
            reasons.append("missing_advisor_identity")
        if length(row["research_intro"]) < 200:
            reasons.append("short_research_intro")
        if not any(length(p.get("abstract")) >= 100 and length(p.get("title")) >= 10
                   for p in row["representative_papers"][:5]):
            reasons.append("no_substantive_representative_abstract")
        if reasons:
            lab_reasons.update(reasons)
        else:
            good_labs.append((number, row))
    # This is an inspection sample, not a replacement candidate universe for ranking.
    # The full eligible course frame must be retained when estimating top-k quality.
    n = sample_size(len(good_courses))
    buckets = defaultdict(list)
    for number, row in good_courses:
        buckets[row["_dept"] or "unknown"].append(number)
    rng = random.Random(SEED)
    for values in buckets.values():
        rng.shuffle(values)
    quotas = {dept: n * len(values) / len(good_courses) for dept, values in buckets.items()}
    alloc = {dept: math.floor(q) for dept, q in quotas.items()}
    for dept in sorted(buckets, key=lambda d: (-(quotas[d] - alloc[d]), d))[:n - sum(alloc.values())]:
        alloc[dept] += 1
    course_inspection = sorted(number for dept, values in buckets.items() for number in values[:alloc[dept]])
    lab_components = json.loads((ROOT / "experiments/final_graph/results/split_v1.json").read_text(encoding="utf-8"))["assignments"]
    component_for_advisor = {aid: component["component_id"] for component in lab_components
                             for aid in component["advisor_ids"]}
    selected_labs = [{"source_row": number, "advisor_id": row["advisor_id"],
                      "component_id": component_for_advisor[row["advisor_id"]]}
                     for number, row in good_labs]
    result = {
        "version": 1, "status": "eligibility_audit_not_semantic_quality_verification",
        "source_hashes": {"final_courses.jsonl": course_hash, "final_labs.jsonl": lab_hash},
        "eligibility_rule": {
            "course": "identity + description >=100 normalized characters + lecture plan >=100; objectives are separately audited for duplication and never assumed independent",
            "lab": "advisor name/id + research intro >=200 normalized characters + one of first 5 representative papers with title >=10 and abstract >=100",
            "exclusion_note": "length and presence do not establish factual validity, currentness, or relevance"},
        "population": {"course": len(courses), "lab": len(labs)},
        "eligible": {"course": len(good_courses), "lab": len(good_labs)},
        "eligible_courses_with_objectives_equal_description": sum(
            (row["Lesson Objectives"] or "").strip() == (row["description"] or "").strip()
            for _, row in good_courses),
        "eligible_course_source_rows": [number for number, _ in good_courses],
        "exclusion_reasons_nonexclusive": {"course": dict(course_reasons), "lab": dict(lab_reasons)},
        "course_inspection_sample": {"seed": SEED, "n": n, "source_rows": course_inspection,
                                     "department_counts": dict(sorted(Counter(courses[i-1]["_dept"] for i in course_inspection).items()))},
        "eligible_lab_components": len({item["component_id"] for item in selected_labs}),
        "eligible_labs": selected_labs,
        "hypothetical_srs_row_n_for_one_binary_prevalence_only": sample_size(len(good_labs)),
        "hypothetical_srs_component_n_for_one_binary_prevalence_only": sample_size(len({item["component_id"] for item in selected_labs})),
        "sampling_limit": "The 95% +/-5pp formula applies to a simple random binary proportion only. Shared-evidence clustering, judge disagreement, paired method differences, and subgroup claims need their own uncertainty analysis."
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("eligible_labs", "course_inspection_sample")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
