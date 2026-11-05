"""Make a blind packet only for BGE top-one pairs absent from relation labels."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"


def main() -> None:
    out = RESULTS / "bge_top1_relevance_v1"
    if out.exists():
        raise RuntimeError("existing packet is immutable")
    original_path = RESULTS / "holdout_relevance_v1/packet.json"
    original = json.loads(original_path.read_text(encoding="utf-8"))
    original_pairs = {(row["lab_id"], row["course_id"]) for row in original["pairs"]}
    rank_path = RESULTS / "bge_rich_v1/rankings.json"
    ranks = json.loads(rank_path.read_text(encoding="utf-8"))
    if len(ranks) != len(original["labs"]) or {row["lab_id"] for row in ranks} != set(original["labs"]):
        raise ValueError("BGE ranking frame does not match the relation packet")
    eligibility = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    eligible_rows = set(eligibility["eligible_course_source_rows"])
    courses = {"course:" + row["course_code"].strip().upper(): row
               for no, line in enumerate((ROOT / "final_courses.jsonl").read_text(encoding="utf-8").splitlines(), 1)
               if no in eligible_rows
               for row in [json.loads(line)]}
    new_pairs, key, packet_courses = [], {}, {}
    for row in ranks:
        lab_id = row["lab_id"]
        choices = {}
        for method in ("dense", "dense_plus_frozen_rule"):
            for rank_position, item in enumerate(row[method][:1], 1):
                choices.setdefault(item["course_id"], {})[method] = rank_position
        for course_id, positions in choices.items():
            if (lab_id, course_id) in original_pairs:
                continue
            course = courses[course_id]
            packet_courses[course_id] = {
                "course_title": course.get("course_title") or "",
                "description": (course.get("description") or "")[:2000],
                "Lesson Objectives": (course.get("Lesson Objectives") or "")[:2000],
                "Lecture progress plan": (course.get("Lecture progress plan") or "")[:4000],
            }
            pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
            new_pairs.append({"pair_id": pair_id, "lab_id": lab_id, "course_id": course_id})
            key[pair_id] = positions
    random.Random(20261015).shuffle(new_pairs)
    packet = {
        "purpose": "method-blind BGE top-one labels not present in the relation top-five packet",
        "scale": original["scale"], "instructions": original["instructions"],
        "selected_component_ids": original["selected_component_ids"],
        "labs": original["labs"], "courses": packet_courses, "pairs": new_pairs,
    }
    out.mkdir()
    packet_path, key_path = out / "packet.json", out / "key.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "status": "unjudged_method_blind", "new_pairs": len(new_pairs),
        "original_packet_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
        "bge_rankings_sha256": hashlib.sha256(rank_path.read_bytes()).hexdigest(),
        "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "key_sha256": hashlib.sha256(key_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
