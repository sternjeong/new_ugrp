"""Analyze Kaggle BGE top-five post hoc extension with two judge files."""

import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
DIR = RESULTS / "bge_top5_extension_v1"
METHODS = ("dense", "dense_plus_frozen_rule")
METRICS = ("fixed_slot_utility", "unrelated_fraction", "any_unrelated")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pid(lab, course):
    return "pair:" + hashlib.sha256((lab + "|" + course).encode()).hexdigest()[:16]


def load(path, ids):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [r["pair_id"] for r in rows] != ids:
        raise ValueError(f"score order/coverage mismatch: {path}")
    if any(type(r["relevance"]) is not int or r["relevance"] not in (0, 1, 2) or type(r["insufficient_evidence"]) is not bool for r in rows):
        raise ValueError(f"invalid scores: {path}")
    return {r["pair_id"]: r for r in rows}


def interval(values):
    rng = random.Random(20261015)
    draws = []
    for _ in range(5000):
        sample = [values[rng.randrange(len(values))] for _ in values]
        draws.append(statistics.mean(sample))
    draws.sort()
    return [draws[125], draws[4874]]


def main():
    output = DIR / "analysis.json"
    if output.exists():
        raise RuntimeError("existing analysis immutable")
    manifest = json.loads((DIR / "manifest.json").read_text(encoding="utf-8"))
    packet_paths = {"old": RESULTS / "holdout_relevance_v1/packet.json",
                    "top1": RESULTS / "bge_top1_relevance_v1/packet.json", "new": DIR / "packet.json"}
    expected_hashes = {"old": "old_packet_sha256", "top1": "top1_packet_sha256", "new": "packet_sha256"}
    packets = {}
    for name, path in packet_paths.items():
        if sha(path) != manifest[expected_hashes[name]]:
            raise ValueError(f"packet hash mismatch: {name}")
        packets[name] = json.loads(path.read_text(encoding="utf-8"))
    ranking_path = RESULTS / "bge_rich_v1/rankings.json"
    if sha(ranking_path) != manifest["gpu_rankings_sha256"]:
        raise ValueError("ranking hash mismatch")
    rankings = {r["lab_id"]: r for r in json.loads(ranking_path.read_text(encoding="utf-8"))}
    if len(rankings) != 136 or set(rankings) != set(packets["old"]["labs"]):
        raise ValueError("lab frame mismatch")
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    selected = set(packets["old"]["selected_component_ids"])
    comps = {r["component_id"]: ["lab:" + aid for aid in r["advisor_ids"]]
             for r in split["assignments"] if r["component_id"] in selected}
    if len(comps) != 112:
        raise ValueError("component frame mismatch")
    report = {"status": "two_judge_posthoc_top5_conditional", "labs": 136, "components": 112,
              "new_pairs": len(packets["new"]["pairs"]), "source_sha256": {"rankings": sha(ranking_path),
              "script": sha(Path(__file__)), **{name + "_packet": sha(path) for name, path in packet_paths.items()}},
              "judge": {}, "limitations": ["extension decided after top-one outcome", "not full-corpus recall or reranker/cutoff validation",
                                         "insufficient evidence removes entire component from paired comparison"]}
    all_ids = {}
    for name, packet in packets.items():
        all_ids[name] = [row["pair_id"] for row in packet["pairs"]]
    if len(set().union(*[set(v) for v in all_ids.values()])) != sum(len(v) for v in all_ids.values()):
        raise ValueError("source score packets overlap")
    for judge in ("a", "b"):
        labels = {}
        for name, folder in (("old", RESULTS / "holdout_relevance_v1"),
                             ("top1", RESULTS / "bge_top1_relevance_v1"), ("new", DIR)):
            score_path = folder / f"scores_{judge}.jsonl"
            labels.update(load(score_path, all_ids[name]))
            report["source_sha256"][f"{name}_scores_{judge}"] = sha(score_path)
        lab_metrics = {}
        missing_labs = {method: 0 for method in METHODS}
        for lab, rank in rankings.items():
            lab_metrics[lab] = {}
            for method in METHODS:
                top = rank[method][:5]
                if len(top) != 5:
                    raise ValueError("short ranking")
                scores = [labels[pid(lab, item["course_id"])] for item in top]
                if any(s["insufficient_evidence"] for s in scores):
                    missing_labs[method] += 1
                    continue
                lab_metrics[lab][method] = {"fixed_slot_utility": sum(s["relevance"] for s in scores) / 10,
                                            "unrelated_fraction": sum(s["relevance"] == 0 for s in scores) / 5,
                                            "any_unrelated": float(any(s["relevance"] == 0 for s in scores))}
        marginal, paired = {}, {}
        for method in METHODS:
            complete = {comp: [lab_metrics[lab][method] for lab in labs]
                        for comp, labs in comps.items() if all(method in lab_metrics[lab] for lab in labs)}
            marginal[method] = {metric: {"components": len(complete),
                                         "mean": statistics.mean(statistics.mean(row[metric] for row in vals) for vals in complete.values()) if complete else None}
                                for metric in METRICS}
        complete_paired = {comp: [lab_metrics[lab] for lab in labs]
                           for comp, labs in comps.items() if all(all(method in lab_metrics[lab] for method in METHODS) for lab in labs)}
        for metric in METRICS:
            diffs = [statistics.mean(row[METHODS[1]][metric] - row[METHODS[0]][metric] for row in vals)
                     for vals in complete_paired.values()]
            paired[metric] = {"components": len(diffs), "hybrid_minus_dense": statistics.mean(diffs) if diffs else None,
                              "component_bootstrap_95": interval(diffs) if diffs else None}
        report["judge"][judge] = {"missing_labs": missing_labs, "marginal": marginal, "paired": paired}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "new_pairs": report["new_pairs"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
