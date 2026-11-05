"""Analyze preregistered top-five field ablation after both blind judges finish."""

import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"
VARIANTS = ("core", "lab_admin", "course_admin", "both_admin", "learning_context")


def read(name):
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def sha(name):
    return hashlib.sha256((DIR / name).read_bytes()).hexdigest()


def bootstrap(values, seed):
    rng = random.Random(seed)
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    def percentile(p):
        x = p * (len(draws) - 1)
        lo, hi = int(x), min(int(x) + 1, len(draws) - 1)
        return draws[lo] * (hi - x) + draws[hi] * (x - lo)
    return [percentile(.025), percentile(.975)]


def main():
    packet, frame, key = read("packet.json"), read("frame.json"), read("method_key.json")
    manifest = read("packet_manifest.json")
    assert sha("packet.json") == manifest["packet_sha256"]
    assert sha("method_key.json") == manifest["method_key_sha256"]
    pair_ids = {p["pair_id"] for p in packet["pairs"]}
    assert len(pair_ids) == 327
    lab_component = {lid: item["component_id"] for item in frame["buckets"]["confirm_unused"] for lid in item["lab_ids"]}
    assert len(lab_component) == 28
    exposure = key["exposure"]
    for variant in VARIANTS:
        assert len(exposure[variant]) == 140
        assert all(x["pair_id"] in pair_ids for x in exposure[variant])
    result = {"packet_sha256": sha("packet.json"), "method_key_sha256": sha("method_key.json"),
              "rankings_sha256": sha("rankings.json"), "confirm_components": 18, "confirm_labs": 28,
              "confirm_pairs": 327, "bootstrap": "component resampling; 5000 percentile replicates",
              "judges": {}}
    courses = packet["courses"]
    duplicate_slots = {}
    for variant in VARIANTS:
        lab_courses = defaultdict(list)
        for x in exposure[variant]:
            lab_courses[x["lab_id"]].append(x["course_id"])
        counts = []
        for course_ids in lab_courses.values():
            core_text = [tuple(courses[cid]["core"]) for cid in course_ids]
            counts.append(len(core_text) - len(set(core_text)))
        duplicate_slots[variant] = {"extra_slots": sum(counts), "lab_rows_with_duplicate": sum(x > 0 for x in counts)}
    result["exact_course_core_duplicate_slots"] = duplicate_slots
    by_judge = {}
    for judge in ("a", "b"):
        data = read(f"judge_{judge}.json")
        ratings = data["ratings"]
        assert data["packet_sha256"] == sha("packet.json")
        assert len(ratings) == len(pair_ids) and len({r["pair_id"] for r in ratings}) == len(ratings)
        assert {r["pair_id"] for r in ratings} == pair_ids
        assert all(r["relevance"] in (0, 1, 2) and isinstance(r["insufficient_evidence"], bool) for r in ratings)
        by_judge[judge] = {r["pair_id"]: r for r in ratings}
        variant_component = {}
        variant_stats = {}
        for variant in VARIANTS:
            lab_rows = defaultdict(list)
            for x in exposure[variant]:
                lab_rows[x["lab_id"]].append(by_judge[judge][x["pair_id"]])
            assert len(lab_rows) == 28 and all(len(x) == 5 for x in lab_rows.values())
            comp_rows = defaultdict(list)
            for lab, rr in lab_rows.items():
                if all(not r["insufficient_evidence"] for r in rr):
                    comp_rows[lab_component[lab]].append(sum(r["relevance"] for r in rr) / 10)
                else:
                    comp_rows[lab_component[lab]].append(None)
            complete = {cid: statistics.mean(rows) for cid, rows in comp_rows.items() if all(x is not None for x in rows)}
            variant_component[variant] = complete
            vals = list(complete.values())
            variant_stats[variant] = {"complete_components": len(vals), "utility": statistics.mean(vals) if vals else None,
                                      "utility_ci95": bootstrap(vals, 20261016) if vals else None,
                                      "zero_exposures": sum(r["relevance"] == 0 for rr in lab_rows.values() for r in rr if not r["insufficient_evidence"]),
                                      "judgeable_exposures": sum(not r["insufficient_evidence"] for rr in lab_rows.values() for r in rr),
                                      "labs_with_zero": sum(any(r["relevance"] == 0 and not r["insufficient_evidence"] for r in rr) for rr in lab_rows.values())}
        contrasts = {}
        for variant in VARIANTS[1:]:
            paired = sorted(set(variant_component["core"]) & set(variant_component[variant]))
            delta = [variant_component["core"][cid] - variant_component[variant][cid] for cid in paired]
            contrasts[f"core_minus_{variant}"] = {"paired_components": len(paired), "mean": statistics.mean(delta) if delta else None,
                                                   "ci95": bootstrap(delta, 20261017) if delta else None}
        result["judges"][judge.upper()] = {"rating_counts": dict(Counter(r["relevance"] for r in ratings if not r["insufficient_evidence"])),
                                             "insufficient_pairs": sum(r["insufficient_evidence"] for r in ratings),
                                             "variants": variant_stats, "contrasts": contrasts,
                                             "ratings_sha256": sha(f"judge_{judge}.json")}
    common = sorted(pair_ids)
    result["agreement"] = {"exact": sum(by_judge["a"][p]["relevance"] == by_judge["b"][p]["relevance"] for p in common),
                           "judged_both": sum(not by_judge["a"][p]["insufficient_evidence"] and not by_judge["b"][p]["insufficient_evidence"] for p in common),
                           "polar_0_vs_2": sum({by_judge["a"][p]["relevance"], by_judge["b"][p]["relevance"]} == {0, 2} for p in common)}
    a = result["judges"]["A"]["contrasts"]["core_minus_both_admin"]
    b = result["judges"]["B"]["contrasts"]["core_minus_both_admin"]
    result["confirmatory_threshold_met"] = bool(a["ci95"] and b["ci95"] and a["ci95"][0] > .02 and b["ci95"][0] > .02)
    (DIR / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
