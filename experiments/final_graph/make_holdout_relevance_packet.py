"""Build a method-blind, pre-label top-five relevance packet."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
SEED = 20261014


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def source_intro(value: str) -> dict:
    if len(value) <= 8000:
        return {"prefix": value, "suffix": ""}
    return {"prefix": value[:6000], "suffix": value[-2000:]}


def main() -> None:
    out = RESULTS / "holdout_relevance_v1"
    if out.exists():
        raise RuntimeError("packet exists; never overwrite a review packet")
    frozen = json.loads((RESULTS / "frozen_relation_design_v15.json").read_text(encoding="utf-8"))
    checks = {
        "engine": ROOT / "experiments/final_graph/relation_engine.py",
        "vocabulary": ROOT / "experiments/final_graph/expanded_concepts_v1.json",
        "legacy_vocabulary": ROOT / "data/concepts.json",
        "split": RESULTS / "rich_split_v1.json",
        "eligibility": RESULTS / "complete_subset_v1.json",
    }
    for key, path in checks.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != frozen["hashes"][key]:
            raise ValueError(f"frozen {key} hash mismatch")
    split = json.loads(checks["split"].read_text(encoding="utf-8"))
    eligible = json.loads(checks["eligibility"].read_text(encoding="utf-8"))
    rankings_path = RESULTS / "holdout_relations_v15/rankings.json"
    ranking = {row["lab_id"]: row for row in json.loads(rankings_path.read_text(encoding="utf-8"))}
    components = [row for row in split["assignments"] if row["split"] == "holdout"]
    if len(components) != 137 or len(ranking) != 180:
        raise ValueError("holdout frame changed")
    chosen = random.Random(SEED).sample(components, 112)
    chosen_ids = {"lab:" + aid for row in chosen for aid in row["advisor_ids"]}
    lab_source = {"lab:" + row["advisor_id"]: row for row in read_jsonl(ROOT / "final_labs.jsonl")}
    allowed_course_rows = set(eligible["eligible_course_source_rows"])
    course_source = {"course:" + row["course_code"].strip().upper(): row
                     for no, row in enumerate(read_jsonl(ROOT / "final_courses.jsonl"), 1)
                     if no in allowed_course_rows}
    labs, courses, pairs, key = {}, {}, [], {}
    for lab_id in sorted(chosen_ids):
        lab = lab_source[lab_id]
        labs[lab_id] = {
            "display_name": lab["display_name"],
            "research_intro": source_intro(lab.get("research_intro") or ""),
            "representative_papers": [
                {"title": paper.get("title") or "", "abstract_first_800": (paper.get("abstract") or "")[:800]}
                for paper in (lab.get("representative_papers") or [])[:5]
            ],
        }
        choices = {}
        for method in ("b0_expanded", "b1"):
            for rank_position, item in enumerate(ranking[lab_id][method][:5], 1):
                choices.setdefault(item["course_id"], {})[method] = rank_position
        for course_id in sorted(choices):
            course = course_source[course_id]
            courses[course_id] = {
                "course_title": course.get("course_title") or "",
                "description": (course.get("description") or "")[:2000],
                "Lesson Objectives": (course.get("Lesson Objectives") or "")[:2000],
                "Lecture progress plan": (course.get("Lecture progress plan") or "")[:4000],
            }
            pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
            pairs.append({"pair_id": pair_id, "lab_id": lab_id, "course_id": course_id})
            key[pair_id] = choices[course_id]
    random.Random(SEED + 1).shuffle(pairs)
    packet = {
        "purpose": "blind relevance labels for sampled holdout top-five candidates",
        "scale": "0=no explainable preparation; 1=indirect useful foundation; 2=direct taught method or tool",
        "instructions": "Judge only from the provided source windows. Generic domain overlap alone is insufficient. Mark insufficient evidence separately. Method identities and ranks are hidden until relevance labels are frozen.",
        "selected_component_ids": sorted(row["component_id"] for row in chosen),
        "labs": labs, "courses": courses, "pairs": pairs,
    }
    out.mkdir()
    packet_path = out / "packet.json"
    key_path = out / "key.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "status": "unjudged_method_blind", "seed": SEED,
        "holdout_components": len(components), "selected_components": len(chosen),
        "selected_lab_rows": len(chosen_ids), "pairs": len(pairs),
        "source_hashes": split["source_hashes"],
        "frozen_design_sha256": hashlib.sha256((RESULTS / "frozen_relation_design_v15.json").read_bytes()).hexdigest(),
        "prereg_amended_sha256": hashlib.sha256((ROOT / "experiments/final_graph/PREREG_RICH_FRAME.md").read_bytes()).hexdigest(),
        "ranking_sha256": hashlib.sha256(rankings_path.read_bytes()).hexdigest(),
        "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "key_sha256": hashlib.sha256(key_path.read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
