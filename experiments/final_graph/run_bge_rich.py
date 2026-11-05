"""Archived local BGE-M3 draft; execute bge_rich_kaggle.ipynb on Kaggle GPU.

Uses exactly the 941 eligible courses and the 136 sampled holdout advisor rows.
This is a new bounded-window adaptation of the old bge_m3 notebook, not an
identical rerun of its old profile/topic inputs. Rankings need independent labels.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "bge_rich_v1"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("BGE-M3 GPU inference must run in Kaggle via bge_rich_kaggle.ipynb")
    if OUT.exists():
        raise RuntimeError("existing ranking output is immutable")
    packet_dir = RESULTS / "holdout_relevance_v1"
    packet = json.loads((packet_dir / "packet.json").read_text(encoding="utf-8"))
    eligibility = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    source_hashes = eligibility["source_hashes"]
    for name, digest in source_hashes.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"source changed: {name}")
    selected_labs = set(packet["labs"])
    eligible_courses = set(eligibility["eligible_course_source_rows"])
    courses = [("course:" + row["course_code"].strip().upper(), row)
               for n, row in enumerate(read_jsonl(ROOT / "final_courses.jsonl"), 1)
               if n in eligible_courses]
    labs = [("lab:" + row["advisor_id"], row) for row in read_jsonl(ROOT / "final_labs.jsonl")
            if "lab:" + row["advisor_id"] in selected_labs]
    if len(courses) != 941 or len(labs) != 136:
        raise ValueError("rich frame count mismatch")

    course_chunks, course_owners = [], []
    for course_id, row in courses:
        title = row["course_title"]
        for value in ((row.get("description") or "")[:1000],
                      (row.get("Lecture progress plan") or "")[:1000]):
            if value.strip():
                course_chunks.append(f"{title} | {value}")
                course_owners.append(course_id)
    lab_chunks, lab_owners = [], []
    for lab_id, row in labs:
        intro = (row.get("research_intro") or "")[:1200]
        if intro.strip():
            lab_chunks.append(intro)
            lab_owners.append(lab_id)
        for paper in (row.get("representative_papers") or [])[:5]:
            title = paper.get("title") or ""
            abstract = (paper.get("abstract") or "")[:400]
            if title.strip() and abstract.strip():
                lab_chunks.append(f"{title} | {abstract}")
                lab_owners.append(lab_id)

    model_revision = "5617a9f61b028005a4858fdac845db406aefb181"
    model = SentenceTransformer("BAAI/bge-m3", revision=model_revision, device="cuda")
    model.max_seq_length = 256  # old notebook limit
    cvec = model.encode(course_chunks, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
    lvec = model.encode(lab_chunks, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
    similarity = lvec @ cvec.T
    cindex = {cid: [i for i, owner in enumerate(course_owners) if owner == cid] for cid, _ in courses}
    lindex = {lid: [i for i, owner in enumerate(lab_owners) if owner == lid] for lid, _ in labs}
    rule_rows = {row["lab_id"]: row for row in json.loads(
        (RESULTS / "holdout_relations_v15/rankings.json").read_text(encoding="utf-8"))}
    output = []
    for lab_id, _ in labs:
        rule_scores = {item["course_id"]: item["score"] for item in rule_rows[lab_id]["b1"]}
        items = []
        for course_id, _ in courses:
            dense = float(similarity[np.ix_(lindex[lab_id], cindex[course_id])].max())
            boost = 0.08 if course_id in rule_scores else 0.0
            items.append({"course_id": course_id, "dense_score": round(dense, 6),
                          "rule_boost": boost, "hybrid_score": round(dense + boost, 6)})
        dense_rank = sorted(items, key=lambda x: (-x["dense_score"], x["course_id"]))[:30]
        hybrid_rank = sorted(items, key=lambda x: (-x["hybrid_score"], x["course_id"]))[:30]
        output.append({"lab_id": lab_id, "dense": dense_rank, "dense_plus_frozen_rule": hybrid_rank})
    OUT.mkdir()
    ranking_path = OUT / "rankings.json"
    ranking_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "status": "unjudged_exploratory_ranking", "model": "BAAI/bge-m3", "model_revision": model_revision,
        "model_max_seq_length": 256, "device": "cuda", "course_chunks": len(course_chunks),
        "lab_chunks": len(lab_chunks), "courses": len(courses), "labs": len(labs),
        "source_hashes": source_hashes,
        "packet_sha256": hashlib.sha256((packet_dir / "packet.json").read_bytes()).hexdigest(),
        "frozen_rule_sha256": hashlib.sha256((RESULTS / "frozen_relation_design_v15.json").read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "ranking_sha256": hashlib.sha256(ranking_path.read_bytes()).hexdigest(),
        "scope": "bounded-window adaptation; not old notebook's topic-profile chunks",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
