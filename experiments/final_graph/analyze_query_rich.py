"""Analyze frozen query challenge with independent blinded pair judgments."""

import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/query_rich_v3"
METHODS = ("q0", "q1")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boot(diff_by_family):
    families = sorted(diff_by_family)
    if not families:
        return None
    rng = random.Random(20261015)
    values = []
    for _ in range(5000):
        sample = [families[rng.randrange(len(families))] for _ in families]
        vals = [v for family in sample for v in diff_by_family[family]]
        values.append(statistics.mean(vals))
    values.sort()
    return [values[125], values[4874]]


def main():
    out = DIR / "analysis.json"
    if out.exists():
        raise RuntimeError("existing analysis immutable")
    manifest = json.loads((DIR / "packet_manifest.json").read_text(encoding="utf-8"))
    packet_path = DIR / "packet.json"
    if sha(packet_path) != manifest["packet_sha256"]:
        raise ValueError("packet hash mismatch")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    ranks = json.loads((DIR / "rankings.json").read_text(encoding="utf-8"))
    targets = json.loads((DIR / "query_targets.json").read_text(encoding="utf-8"))
    target_by_id = {q["id"]: q for q in targets["queries"]}
    expected = [p["pair_id"] for p in packet["pairs"]]
    pair_by_key = {(p["query_id"], p["lab_id"]): p["pair_id"] for p in packet["pairs"]}
    labels = {}
    for judge in ("a", "b"):
        path = DIR / f"scores_{judge}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if [row["pair_id"] for row in rows] != expected:
            raise ValueError(f"score key/order mismatch {judge}")
        if any(row["relevance"] not in (0, 1, 2) or type(row["violation"]) is not bool or type(row["insufficient_evidence"]) is not bool for row in rows):
            raise ValueError(f"invalid label {judge}")
        labels[judge] = {row["pair_id"]: row for row in rows}
    report = {"status": "two_judge_query_challenge_conditional_analysis",
              "source_sha256": {"packet": sha(packet_path), "rankings": sha(DIR / "rankings.json"),
                                "targets": sha(DIR / "query_targets.json"), "script": sha(Path(__file__)),
                                "scores_a": sha(DIR / "scores_a.jsonl"), "scores_b": sha(DIR / "scores_b.jsonl")},
              "pairs": len(expected), "agreement": {
                  "relevance_exact": sum(labels["a"][pid]["relevance"] == labels["b"][pid]["relevance"] for pid in expected) / len(expected),
                  "violation_exact": sum(labels["a"][pid]["violation"] == labels["b"][pid]["violation"] for pid in expected) / len(expected),
                  "insufficient_exact": sum(labels["a"][pid]["insufficient_evidence"] == labels["b"][pid]["insufficient_evidence"] for pid in expected) / len(expected)},
              "judge": {}, "limitations": ["authored corpus-grounded queries, not representative user traffic",
                "candidate corpus and target examples overlap by design", "only top-five union pairs judged; no full-corpus recall",
                "cluster bootstrap reflects nine authored topic-pair families, not population inference"]}
    for judge, score_map in labels.items():
        by_group = {}
        for group in ("explicit_negative", "positive_only", "ambiguous"):
            qrows = [row for row in ranks if row["group"] == group]
            metrics = {method: defaultdict(list) for method in METHODS}
            per_query = {}
            for row in qrows:
                qid = row["query_id"]
                per_query[qid] = {}
                for method in METHODS:
                    selected = row[method]
                    scores = [score_map[pair_by_key[(qid, item["lab_id"])]] for item in selected]
                    missing = any(s["insufficient_evidence"] for s in scores)
                    vals = {"returned": float(len(selected) == 5),
                            "missing": float(missing),
                            "safety_coverage": float(len(selected) == 5 and not missing and
                                                     not any(s["violation"] for s in scores) and
                                                     any(s["relevance"] >= 1 for s in scores))}
                    if selected and not missing:
                        vals.update({"violation_any": float(any(s["violation"] for s in scores)),
                                     "relevant_fraction": statistics.mean(s["relevance"] >= 1 for s in scores),
                                     "fixed_slot_utility": sum(s["relevance"] for s in scores) / 10})
                    per_query[qid][method] = vals
                    for key, value in vals.items():
                        metrics[method][key].append(value)
            group_report = {"queries": len(qrows), "methods": {}, "paired": {}}
            for method in METHODS:
                group_report["methods"][method] = {key: {"n": len(values), "mean": statistics.mean(values) if values else None}
                                                   for key, values in metrics[method].items()}
            for metric in ("violation_any", "relevant_fraction", "fixed_slot_utility", "safety_coverage"):
                eligible = [qid for qid in per_query if metric in per_query[qid]["q0"] and metric in per_query[qid]["q1"]]
                diffs = [per_query[qid]["q1"][metric] - per_query[qid]["q0"][metric] for qid in eligible]
                result = {"paired_n": len(diffs), "q1_minus_q0": statistics.mean(diffs) if diffs else None}
                if group == "explicit_negative" and diffs:
                    family = defaultdict(list)
                    for qid in eligible:
                        q = target_by_id[qid]
                        key = "|".join(sorted(q["positive_targets"] + q["negative_targets"]))
                        family[key].append(per_query[qid]["q1"][metric] - per_query[qid]["q0"][metric])
                    result["family_cluster_bootstrap_95"] = boot(family)
                    result["families"] = len(family)
                group_report["paired"][metric] = result
            if group == "explicit_negative":
                # Every frozen negative target has a recorded source-paper example in the candidate frame.
                present = sum(all(target in targets["topics"] for target in target_by_id[row["query_id"]]["negative_targets"]) for row in qrows)
                group_report["negative_target_in_candidate_example"] = {"present_queries": present, "absent_queries": len(qrows) - present}
            by_group[group] = group_report
        report["judge"][judge] = by_group
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "pairs": report["pairs"], "agreement": report["agreement"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
