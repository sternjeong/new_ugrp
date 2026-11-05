"""Reproducible lexical retrieval baseline on the same rich-frame candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "tfidf_rich_v1"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("existing output is immutable")
    packet_path = RESULTS / "holdout_relevance_v1/packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    eligibility = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    for name, digest in eligibility["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"source changed: {name}")
    allowed_course_rows = set(eligibility["eligible_course_source_rows"])
    courses = [("course:" + row["course_code"].strip().upper(), row)
               for no, row in enumerate(read_jsonl(ROOT / "final_courses.jsonl"), 1)
               if no in allowed_course_rows]
    allowed_labs = set(packet["labs"])
    labs = [("lab:" + row["advisor_id"], row) for row in read_jsonl(ROOT / "final_labs.jsonl")
            if "lab:" + row["advisor_id"] in allowed_labs]
    if len(courses) != 941 or len(labs) != 136:
        raise ValueError("frame changed")
    course_texts = [" ".join((row["course_title"], (row.get("description") or "")[:1000],
                              (row.get("Lecture progress plan") or "")[:1000])) for _, row in courses]
    lab_texts = []
    for _, row in labs:
        parts = [(row.get("research_intro") or "")[:1200]]
        parts += [(paper.get("title") or "") + " " + (paper.get("abstract") or "")[:400]
                  for paper in (row.get("representative_papers") or [])[:5]]
        lab_texts.append(" ".join(parts))
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=2,
                                 max_features=200000, sublinear_tf=True, norm="l2")
    matrix = vectorizer.fit_transform(course_texts + lab_texts)
    similarity = (matrix[len(courses):] @ matrix[:len(courses)].T).toarray()
    rule_rows = {row["lab_id"]: row for row in json.loads(
        (RESULTS / "holdout_relations_v15/rankings.json").read_text(encoding="utf-8"))}
    rankings = []
    for lab_index, (lab_id, _) in enumerate(labs):
        rule_hits = {item["course_id"] for item in rule_rows[lab_id]["b1"]}
        entries = []
        for course_index, (course_id, _) in enumerate(courses):
            lexical = float(similarity[lab_index, course_index])
            boost = .08 if course_id in rule_hits else 0.
            entries.append({"course_id": course_id, "lexical_score": round(lexical, 6),
                            "rule_boost": boost, "hybrid_score": round(lexical + boost, 6)})
        rankings.append({
            "lab_id": lab_id,
            "lexical": sorted(entries, key=lambda item: (-item["lexical_score"], item["course_id"]))[:30],
            "lexical_plus_frozen_rule": sorted(entries, key=lambda item: (-item["hybrid_score"], item["course_id"]))[:30],
        })
    OUT.mkdir()
    ranking_path = OUT / "rankings.json"
    ranking_path.write_text(json.dumps(rankings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "status": "unjudged_exploratory_ranking", "method": "character_tfidf_2_to_4",
        "courses": len(courses), "labs": len(labs), "features": len(vectorizer.vocabulary_),
        "source_hashes": eligibility["source_hashes"],
        "packet_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
        "rule_design_sha256": hashlib.sha256((RESULTS / "frozen_relation_design_v15.json").read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ranking_sha256": hashlib.sha256(ranking_path.read_bytes()).hexdigest(),
        "scope": "lexical baseline only; cannot assess quality without new-pair blind labels",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
