"""Analyze two blind judge files for Kaggle GPU BGE top-one comparison."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
NEW = RESULTS / "bge_top1_relevance_v1"
OLD = RESULTS / "holdout_relevance_v1"
METHODS = ("dense", "dense_plus_frozen_rule")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scores(path: Path, expected: list[str]) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["pair_id"] for row in rows] != expected:
        raise ValueError(f"incomplete, duplicate, or unordered score file: {path}")
    if any(row["relevance"] not in (0, 1, 2) or not isinstance(row["insufficient_evidence"], bool)
           for row in rows):
        raise ValueError(f"invalid score: {path}")
    return {row["pair_id"]: row for row in rows}


def pair_id(lab_id: str, course_id: str) -> str:
    return "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]


def summary(component_rows: dict[str, dict], metric: str, seed: int = 20261015) -> dict:
    keys = sorted(component_rows)
    pairs = [(component_rows[key][METHODS[0]][metric], component_rows[key][METHODS[1]][metric]) for key in keys]
    rng = random.Random(seed)
    differences = []
    for _ in range(5000):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        differences.append(statistics.mean(b - a for a, b in sample))
    differences.sort()
    return {"components": len(pairs),
            METHODS[0]: statistics.mean(a for a, _ in pairs),
            METHODS[1]: statistics.mean(b for _, b in pairs),
            "paired_difference_hybrid_minus_dense": statistics.mean(b - a for a, b in pairs),
            "paired_component_bootstrap_95": [differences[125], differences[4874]]}


def main() -> None:
    old_packet_path, new_packet_path = OLD / "packet.json", NEW / "packet.json"
    old_packet = json.loads(old_packet_path.read_text(encoding="utf-8"))
    new_packet = json.loads(new_packet_path.read_text(encoding="utf-8"))
    manifest = json.loads((NEW / "manifest.json").read_text(encoding="utf-8"))
    if sha(new_packet_path) != manifest["packet_sha256"] or sha(old_packet_path) != manifest["original_packet_sha256"]:
        raise ValueError("packet hash mismatch")
    old_ids = [row["pair_id"] for row in old_packet["pairs"]]
    new_ids = [row["pair_id"] for row in new_packet["pairs"]]
    if set(old_ids) & set(new_ids):
        raise ValueError("new packet repeats prior labels")
    ranking_path = RESULTS / "bge_rich_v1/rankings.json"
    if sha(ranking_path) != manifest["bge_rankings_sha256"]:
        raise ValueError("GPU ranking hash mismatch")
    ranks = {row["lab_id"]: row for row in json.loads(ranking_path.read_text(encoding="utf-8"))}
    if set(ranks) != set(old_packet["labs"]) or len(ranks) != 136:
        raise ValueError("lab frame mismatch")
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    selected_ids = set(old_packet["selected_component_ids"])
    selected = [row for row in split["assignments"] if row["component_id"] in selected_ids]
    if len(selected) != 112:
        raise ValueError("component frame mismatch")
    labels = {}
    for judge in ("a", "b"):
        old = scores(OLD / f"scores_{judge}.jsonl", old_ids)
        new = scores(NEW / f"scores_{judge}.jsonl", new_ids)
        labels[judge] = {**old, **new}
    report = {"status": "two_judge_conditional_top1_comparison", "new_pairs": len(new_ids),
              "new_pair_raw_exact_agreement": sum(labels["a"][pid]["relevance"] == labels["b"][pid]["relevance"] for pid in new_ids) / len(new_ids),
              "source_sha256": {"old_packet": sha(old_packet_path), "new_packet": sha(new_packet_path),
                                "gpu_rankings": sha(ranking_path), "script": sha(Path(__file__)),
                                **{f"new_scores_{judge}": sha(NEW / f"scores_{judge}.jsonl") for judge in ("a", "b")},
                                **{f"old_scores_{judge}": sha(OLD / f"scores_{judge}.jsonl") for judge in ("a", "b")}},
              "top1_changed_labs": sum(row[METHODS[0]][0]["course_id"] != row[METHODS[1]][0]["course_id"] for row in ranks.values()),
              "judge": {},
              "limitations": ["conditional on rich rows and judged top-one pairs",
                              "not top-three/five quality, recall, cutoff, or reranker validation",
                              "raw judge scores are not adjudicated human truth"]}
    for judge, score_map in labels.items():
        lab_values = {}
        for lab_id, row in ranks.items():
            lab_values[lab_id] = {}
            for method in METHODS:
                pid = pair_id(lab_id, row[method][0]["course_id"])
                if pid not in score_map:
                    raise ValueError(f"unjudged top-one pair: {pid}")
                score = score_map[pid]
                lab_values[lab_id][method] = {
                    "unrelated_top1": float(score["relevance"] == 0),
                    "utility_top1": score["relevance"] / 2,
                    "insufficient_top1": float(score["insufficient_evidence"]),
                }
        component_rows = {}
        for comp in selected:
            rows = [lab_values["lab:" + aid] for aid in comp["advisor_ids"]]
            component_rows[comp["component_id"]] = {
                method: {metric: statistics.mean(row[method][metric] for row in rows)
                         for metric in ("unrelated_top1", "utility_top1", "insufficient_top1")}
                for method in METHODS}
        report["judge"][judge] = {
            metric: summary(component_rows, metric)
            for metric in ("unrelated_top1", "utility_top1", "insufficient_top1")}
    out = NEW / "analysis.json"
    if out.exists():
        raise RuntimeError("existing analysis is immutable")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
