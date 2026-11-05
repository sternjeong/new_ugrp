"""Freeze the unlabeled rank-six exposure packet for the feedback gate stress test."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "feedback_rich_v3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pid(lab_id, course_id):
    return "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]


def main():
    if OUT.exists():
        raise RuntimeError("feedback packet already exists")
    old_path = RESULTS / "holdout_relevance_v1/packet.json"
    bge_path = RESULTS / "bge_top1_relevance_v1/packet.json"
    ranking_path = RESULTS / "holdout_relations_v15/rankings.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    bge = json.loads(bge_path.read_text(encoding="utf-8"))
    existing = {item["pair_id"] for packet in (old, bge) for item in packet["pairs"]}
    rank_map = {row["lab_id"]: row for row in json.loads(ranking_path.read_text(encoding="utf-8"))}
    if len(old["labs"]) != 136:
        raise ValueError("expected 136 selected labs")
    all_courses = {"course:" + row["course_code"].strip().upper(): row for row in (json.loads(line) for line in (ROOT / "final_courses.jsonl").read_text(encoding="utf-8").splitlines())}
    pairs = []
    courses = {}
    exposure = []
    for lab_id in sorted(old["labs"]):
        top = rank_map[lab_id]["b0_expanded"][:6]
        if len(top) != 6:
            raise ValueError(f"rank six unavailable {lab_id}")
        removal_index = int.from_bytes(hashlib.sha256(("feedback-v1|" + lab_id).encode()).digest()[:8], "big") % 5
        sixth = top[5]["course_id"]
        pair_id = pid(lab_id, sixth)
        exposure.append({"lab_id": lab_id, "original_top5": [x["course_id"] for x in top[:5]],
                         "removed_position_zero_based": removal_index, "sixth_course_id": sixth,
                         "sixth_pair_id": pair_id, "requires_new_label": pair_id not in existing})
        if pair_id in existing:
            continue
        pairs.append({"pair_id": pair_id, "lab_id": lab_id, "course_id": sixth})
        source = all_courses[sixth]
        courses[sixth] = {"course_title": source.get("course_title") or "",
                          "description": (source.get("description") or "")[:2000],
                          "Lesson Objectives": (source.get("Lesson Objectives") or "")[:2000],
                          "Lecture progress plan": (source.get("Lecture progress plan") or "")[:4000]}
    if len({p["pair_id"] for p in pairs}) != len(pairs):
        raise ValueError("duplicate new pair")
    packet = {"purpose": "blind relevance for newly exposed rank-six pairs only",
              "instructions": "Use the same scale as holdout_relevance_v1: 0=no explainable preparation, 1=indirect useful foundation, 2=direct taught method or tool. Mark insufficient_evidence=true only when the provided source windows do not support a meaningful rating; this is distinct from a supported 0. Topic overlap alone does not prove preparation. Do not open exposure_plan.json or ranking/old score files before labels are frozen. Save JSONL in packet order, keys pair_id, relevance, insufficient_evidence.",
              "labs": {lab_id: old["labs"][lab_id] for lab_id in sorted({p["lab_id"] for p in pairs})},
              "courses": courses, "pairs": pairs}
    OUT.mkdir()
    (OUT / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "exposure_plan.json").write_text(json.dumps(exposure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"new_pairs": len(pairs), "labs": len(exposure), "packet_sha256": sha(OUT / "packet.json"),
                "exposure_plan_sha256": sha(OUT / "exposure_plan.json"),
                "old_packet_sha256": sha(old_path), "bge_packet_sha256": sha(bge_path),
                "ranking_sha256": sha(ranking_path), "script_sha256": sha(Path(__file__))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
