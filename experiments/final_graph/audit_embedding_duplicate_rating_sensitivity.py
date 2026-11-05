"""Post hoc worst-case harmonization of conflicting identical-text ratings."""

import hashlib
import itertools
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"


def read(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def sha(name):
    return hashlib.sha256((DIR / name).read_bytes()).hexdigest()


def component_deltas(scores, exposure, lab_component):
    by_variant = {}
    for variant in ("core", "both_admin"):
        lab = defaultdict(list)
        for row in exposure[variant]:
            lab[row["lab_id"]].append(scores[row["pair_id"]])
        component = defaultdict(list)
        for lid, rr in lab.items():
            component[lab_component[lid]].append(sum(rr) / 10)
        by_variant[variant] = {cid: statistics.mean(v) for cid, v in component.items()}
    return [by_variant["core"][cid] - by_variant["both_admin"][cid] for cid in sorted(by_variant["core"])]


def ci(values):
    rng = random.Random(20261017)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    def quantile(p):
        x = p * (len(samples)-1)
        lo = int(x)
        return samples[lo] * (1 - (x-lo)) + samples[lo+1] * (x-lo)
    return [quantile(.025), quantile(.975)]


def main():
    packet, frame, key = read("packet.json"), read("frame.json"), read("method_key.json")
    lab_component = {lid: x["component_id"] for x in frame["buckets"]["confirm_unused"] for lid in x["lab_ids"]}
    out = {"status": "posthoc_consistency_sensitivity_not_primary", "packet_sha256": sha("packet.json"),
           "analysis_sha256": sha("analysis.json"), "judges": {}}
    for judge in "ab":
        ratings = {r["pair_id"]: r["relevance"] for r in read(f"judge_{judge}.json")["ratings"]}
        groups = defaultdict(list)
        for pair in packet["pairs"]:
            signature = (pair["lab_id"], tuple(packet["courses"][pair["course_id"]]["core"]))
            groups[signature].append(pair["pair_id"])
        conflicts = [ids for ids in groups.values() if len({ratings[x] for x in ids}) > 1]
        scenarios = []
        for choices in itertools.product((0, 1), repeat=len(conflicts)):
            adjusted = ratings.copy()
            for ids, pick_max in zip(conflicts, choices):
                value = (max if pick_max else min)(ratings[x] for x in ids)
                adjusted.update({x: value for x in ids})
            d = component_deltas(adjusted, key["exposure"], lab_component)
            scenarios.append({"choices": list(choices), "effect": statistics.mean(d), "ci95": ci(d)})
        original = component_deltas(ratings, key["exposure"], lab_component)
        out["judges"][judge.upper()] = {
            "conflicting_identical_text_groups": len(conflicts), "scenarios": len(scenarios),
            "original_effect": statistics.mean(original), "original_ci95": ci(original),
            "effect_range": [min(x["effect"] for x in scenarios), max(x["effect"] for x in scenarios)],
            "lowest_ci_lower": min(x["ci95"][0] for x in scenarios),
            "all_scenarios_pass_preregistered_0_02_threshold": all(x["ci95"][0] > .02 for x in scenarios),
            "ratings_sha256": sha(f"judge_{judge}.json")}
    (DIR / "duplicate_rating_sensitivity.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
