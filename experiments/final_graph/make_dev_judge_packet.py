"""Method-blind small development packet for semantic error discovery."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/final_graph/results"


def read(name):
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines()]


def intro_window(value):
    if len(value) <= 8000:
        return value
    return value[:6000] + "\n[원문 중간 생략]\n" + value[-2000:]


def main():
    if (OUT / "dev_judge_scores_a.json").exists() or (OUT / "dev_judge_scores_b.json").exists():
        raise RuntimeError("v1 packet has been judged; do not regenerate or overwrite it")
    rankings = json.loads(Path("/tmp/ugrp-relations-rich-dev/rankings.json").read_text(encoding="utf-8"))
    labs = {"lab:" + r["advisor_id"]: r for r in read("final_labs.jsonl")}
    eligibility = json.loads((OUT / "complete_subset_v1.json").read_text(encoding="utf-8"))
    eligible_rows = set(eligibility["eligible_course_source_rows"])
    courses = {"course:" + r["course_code"].strip().upper(): r
               for number, r in enumerate(read("final_courses.jsonl"), 1) if number in eligible_rows}
    zero = sorted((r for r in rankings if not r["b1"]), key=lambda r: r["lab_id"])
    positive = sorted((r for r in rankings if r["b1"]), key=lambda r: r["lab_id"])
    selected = zero[:2] + positive[:2]
    rng = random.Random(20261014)
    packet_labs, packet_courses, pairs, key = {}, {}, [], {}
    for ranked in selected:
        lab_id = ranked["lab_id"]
        row = labs[lab_id]
        packet_labs[lab_id] = {
            "display_name": row["display_name"],
            "research_intro": intro_window(row["research_intro"] or ""),
            "representative_papers": [{"title": p["title"], "abstract_first_800": (p.get("abstract") or "")[:800]}
                                      for p in row["representative_papers"][:5]]}
        choices = {}
        for method in ("b0_expanded", "b1"):
            for item in ranked[method][:3]:
                choices.setdefault(item["course_id"], set()).add(method)
        all_courses = sorted(courses)
        random_course = rng.choice([cid for cid in all_courses if cid not in choices])
        choices.setdefault(random_course, set()).add("random")
        for course_id in sorted(choices):
            course = courses[course_id]
            packet_courses[course_id] = {"course_title": course["course_title"],
                                         "description": course["description"][:2000],
                                         "Lesson Objectives": course["Lesson Objectives"][:2000],
                                         "Lecture progress plan": course["Lecture progress plan"][:4000]}
            pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
            pairs.append({"pair_id": pair_id, "lab_id": lab_id, "course_id": course_id})
            key[pair_id] = sorted(choices[course_id])
    rng.shuffle(pairs)
    packet = {"purpose": "development error discovery only, not confirmatory performance",
              "scale": "0=no explainable preparation, 1=indirect useful foundation, 2=direct taught method/tool",
              "instructions": "Judge each pair from the provided source text only; do not infer relevance from department or generic topic overlap. Mark insufficient evidence separately.",
              "labs": packet_labs, "courses": packet_courses, "pairs": pairs}
    (OUT / "dev_judge_packet_v1.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "dev_judge_key_v1.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"labs": len(packet_labs), "courses": len(packet_courses), "pairs": len(pairs)}, indent=2))


if __name__ == "__main__":
    main()
