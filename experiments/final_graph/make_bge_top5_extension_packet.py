"""Build method-blind new pair packet for post hoc BGE top-five extension."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "bge_top5_extension_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise RuntimeError("packet already exists")
    old_path = RESULTS / "holdout_relevance_v1/packet.json"
    top1_path = RESULTS / "bge_top1_relevance_v1/packet.json"
    rank_path = RESULTS / "bge_rich_v1/rankings.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    top1 = json.loads(top1_path.read_text(encoding="utf-8"))
    ranks = json.loads(rank_path.read_text(encoding="utf-8"))
    known = {(p["lab_id"], p["course_id"]) for packet in (old, top1) for p in packet["pairs"]}
    if len(ranks) != 136 or {r["lab_id"] for r in ranks} != set(old["labs"]):
        raise ValueError("ranking frame mismatch")
    eligible = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    eligible_rows = set(eligible["eligible_course_source_rows"])
    courses = {"course:" + row["course_code"].strip().upper(): row
               for no, line in enumerate((ROOT / "final_courses.jsonl").read_text(encoding="utf-8").splitlines(), 1)
               if no in eligible_rows for row in [json.loads(line)]}
    pair_rows, packet_courses = [], {}
    for rank in ranks:
        lab_id = rank["lab_id"]
        choices = {item["course_id"] for method in ("dense", "dense_plus_frozen_rule") for item in rank[method][:5]}
        for course_id in sorted(choices):
            if (lab_id, course_id) in known:
                continue
            course = courses[course_id]
            packet_courses[course_id] = {
                "course_title": course.get("course_title") or "",
                "description": (course.get("description") or "")[:2000],
                "Lesson Objectives": (course.get("Lesson Objectives") or "")[:2000],
                "Lecture progress plan": (course.get("Lecture progress plan") or "")[:4000],
            }
            pair_rows.append({"pair_id": "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16],
                              "lab_id": lab_id, "course_id": course_id})
    random.Random(20261015 + 5).shuffle(pair_rows)
    packet = {"purpose": "post hoc top-five expansion; new method-blind pairs only",
              "scale": old["scale"], "instructions": old["instructions"],
              "selected_component_ids": old["selected_component_ids"],
              "labs": old["labs"], "courses": packet_courses, "pairs": pair_rows}
    OUT.mkdir()
    (OUT / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": "unjudged_posthoc_extension", "new_pairs": len(pair_rows),
                "packet_sha256": sha(OUT / "packet.json"), "old_packet_sha256": sha(old_path),
                "top1_packet_sha256": sha(top1_path), "gpu_rankings_sha256": sha(rank_path),
                "script_sha256": sha(Path(__file__))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
