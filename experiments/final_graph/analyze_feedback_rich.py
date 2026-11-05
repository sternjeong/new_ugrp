"""Analyze a random-position removal and rank-six backfill stress test."""

import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
DIR = RESULTS / "feedback_rich_v3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pair_id(lab, course):
    return "pair:" + hashlib.sha256((lab + "|" + course).encode()).hexdigest()[:16]


def load_scores(path, expected):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["pair_id"] for row in rows] != expected:
        raise ValueError(f"score order/coverage mismatch {path}")
    if any(row["relevance"] not in (0, 1, 2) or type(row["insufficient_evidence"]) is not bool for row in rows):
        raise ValueError(f"invalid scores {path}")
    return {row["pair_id"]: row for row in rows}


def component_interval(values):
    keys = sorted(values)
    rng = random.Random(20261015)
    draws = []
    for _ in range(5000):
        sample = [keys[rng.randrange(len(keys))] for _ in keys]
        draws.append(statistics.mean(values[key] for key in sample))
    draws.sort()
    return [draws[125], draws[4874]]


def main():
    out = DIR / "analysis.json"
    if out.exists():
        raise RuntimeError("analysis immutable")
    manifest = json.loads((DIR / "manifest.json").read_text(encoding="utf-8"))
    for name, key in (("packet.json", "packet_sha256"), ("exposure_plan.json", "exposure_plan_sha256")):
        if sha(DIR / name) != manifest[key]:
            raise ValueError(f"hash mismatch {name}")
    packet = json.loads((DIR / "packet.json").read_text(encoding="utf-8"))
    exposure = json.loads((DIR / "exposure_plan.json").read_text(encoding="utf-8"))
    if len(exposure) != 136 or len(packet["pairs"]) != manifest["new_pairs"]:
        raise ValueError("frame mismatch")
    old = json.loads((RESULTS / "holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))
    bge = json.loads((RESULTS / "bge_top1_relevance_v1/packet.json").read_text(encoding="utf-8"))
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    selected = set(old["selected_component_ids"])
    comps = {row["component_id"]: {"lab:" + aid for aid in row["advisor_ids"]}
             for row in split["assignments"] if row["component_id"] in selected}
    if len(comps) != 112 or {lab for labs in comps.values() for lab in labs} != {row["lab_id"] for row in exposure}:
        raise ValueError("component frame mismatch")
    expected = {"old": [row["pair_id"] for row in old["pairs"]],
                "bge": [row["pair_id"] for row in bge["pairs"]],
                "new": [row["pair_id"] for row in packet["pairs"]]}
    report = {"status": "two_judge_synthetic_removal_stress_test",
              "source_sha256": {"packet": sha(DIR / "packet.json"), "exposure": sha(DIR / "exposure_plan.json"),
                                "script": sha(Path(__file__))},
              "labs": 136, "components": 112,
              "structural": {"g0_backfills_outside_initial_top5": len(exposure),
                             "g1_backfills_outside_initial_top5": 0,
                             "g0_length": 5, "g1_length": 4},
              "judge": {}, "limitations": ["random rank-position removal, not observed user feedback",
                                       "fixed baseline rank-six only; no exploration or response modeling",
                                       "initial and extra labels are independent Luna judgments, not user truth"]}
    for judge in ("a", "b"):
        labels = {}
        for name, folder in (("old", RESULTS / "holdout_relevance_v1"),
                             ("bge", RESULTS / "bge_top1_relevance_v1"), ("new", DIR)):
            scores = load_scores(folder / f"scores_{judge}.jsonl", expected[name])
            if set(labels) & set(scores):
                raise ValueError("duplicate score IDs")
            labels.update(scores)
            report["source_sha256"][f"{name}_scores_{judge}"] = sha(folder / f"scores_{judge}.jsonl")
        lab_values = {}
        missing = 0
        for row in exposure:
            lab = row["lab_id"]
            keep = [course for i, course in enumerate(row["original_top5"]) if i != row["removed_position_zero_based"]]
            s = [labels[pair_id(lab, cid)] for cid in keep + [row["sixth_course_id"]]]
            if any(x["insufficient_evidence"] for x in s):
                missing += 1
                continue
            extra = s[-1]["relevance"]
            lab_values[lab] = {"sixth_unrelated": float(extra == 0), "sixth_core": float(extra == 2),
                               "g0_utility": sum(x["relevance"] for x in s) / 10,
                               "g1_utility": sum(x["relevance"] for x in s[:-1]) / 10,
                               "g0_relevant_count": sum(x["relevance"] >= 1 for x in s),
                               "g1_relevant_count": sum(x["relevance"] >= 1 for x in s[:-1])}
        metrics = {}
        for metric in ("sixth_unrelated", "sixth_core", "g0_utility", "g1_utility", "g0_relevant_count", "g1_relevant_count"):
            by_comp = {}
            for comp, labs in comps.items():
                vals = [lab_values[lab][metric] for lab in labs if lab in lab_values]
                if vals:
                    by_comp[comp] = statistics.mean(vals)
            metrics[metric] = {"evaluable_labs": len(lab_values), "evaluable_components": len(by_comp),
                               "component_mean": statistics.mean(by_comp.values()) if by_comp else None,
                               "component_bootstrap_95": component_interval(by_comp) if by_comp else None}
        report["judge"][judge] = {"missing_labs": missing, "metrics": metrics}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"labs": report["labs"], "judge": {j: x["missing_labs"] for j, x in report["judge"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
