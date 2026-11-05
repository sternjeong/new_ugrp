"""Analyze two completed blind label files with component-level inference."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
PACKET_DIR = RESULTS / "holdout_relevance_v1"
METHODS = ("b0_expanded", "b1")
METRICS = ("unrelated_returned", "fill_rate", "empty_rate", "at_least_three",
           "fixed_slot_utility", "union_conditioned_ndcg")


def read_scores(path: Path, expected: list[str]) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [row["pair_id"] for row in rows]
    if ids != expected:
        raise ValueError(f"{path.name}: incomplete, out of order, or duplicated")
    for row in rows:
        if row["relevance"] not in (0, 1, 2) or not isinstance(row["insufficient_evidence"], bool):
            raise ValueError(f"{path.name}: invalid label")
    return {row["pair_id"]: row for row in rows}


def dcg(values: list[int]) -> float:
    return sum((2 ** value - 1) / math.log2(i + 2) for i, value in enumerate(values))


def average(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return statistics.mean(available) if available else None


def per_lab(lab_id: str, rank: dict, labels: dict[str, dict],
            content_groups: dict[str, str] | None = None) -> dict[str, dict]:
    union = {item["course_id"] for method in METHODS for item in rank[method][:5]}
    def label(course_id: str) -> int:
        pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
        return labels[pair_id]["relevance"]
    if content_groups is None:
        ideal_values = [label(course_id) for course_id in union]
    else:
        group_values = {}
        for course_id in union:
            group = content_groups.get(course_id, course_id)
            group_values[group] = max(group_values.get(group, 0), label(course_id))
        ideal_values = list(group_values.values())
    ideal = dcg(sorted(ideal_values, reverse=True)[:5])
    result = {}
    for method in METHODS:
        courses = [item["course_id"] for item in rank[method][:5]]
        if content_groups is not None:
            seen_groups = set()
            kept_positions = []
            for position, course_id in enumerate(courses):
                group = content_groups.get(course_id, course_id)
                if group not in seen_groups:
                    seen_groups.add(group)
                    kept_positions.append(position)
        else:
            kept_positions = list(range(len(courses)))
        # Dropped duplicate slots remain empty at their original positions.
        # Compacting later results upward would silently backfill those slots.
        kept = [courses[position] for position in kept_positions]
        values = [label(course_id) for course_id in kept]
        positioned_values = [label(course_id) if position in kept_positions else 0
                             for position, course_id in enumerate(courses)]
        result[method] = {
            "unrelated_returned": sum(value == 0 for value in values) / len(values) if values else None,
            "fill_rate": len(values) / 5,
            "empty_rate": float(not values),
            "at_least_three": float(len(values) >= 3),
            "fixed_slot_utility": sum(values) / 10,
            "union_conditioned_ndcg": dcg(positioned_values) / ideal if ideal else None,
            "union_has_relevant": bool(ideal),
        }
    return result


def eligible_content_groups() -> dict[str, str]:
    eligible = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    allowed_rows = set(eligible["eligible_course_source_rows"])
    audit = json.loads((RESULTS / "course_identity_candidates.json").read_text(encoding="utf-8"))
    mapping = {}
    for group in audit["groups"]:
        members = [item for item in group["members"] if item["source_row"] in allowed_rows]
        if group["reason"] != "identical_title_and_teaching_text" or len(members) < 2:
            continue
        for member in members:
            mapping["course:" + member["course_code"].strip().upper()] = group["content_group_candidate"]
    return mapping


def component_means(selected: list[dict], lab_metrics: dict[str, dict]) -> dict[str, dict]:
    out = {}
    for component in selected:
        rows = [lab_metrics["lab:" + aid] for aid in component["advisor_ids"]]
        out[component["component_id"]] = {
            method: {metric: average([row[method][metric] for row in rows]) for metric in METRICS}
            for method in METHODS
        }
    return out


def summarize(components: dict[str, dict], seed: int = 20261014) -> dict:
    keys = sorted(components)
    rng = random.Random(seed)
    result = {}
    for metric in METRICS:
        baseline = average([components[key]["b0_expanded"][metric] for key in keys])
        rule = average([components[key]["b1"][metric] for key in keys])
        paired = [(components[key]["b0_expanded"][metric], components[key]["b1"][metric])
                  for key in keys if components[key]["b0_expanded"][metric] is not None
                  and components[key]["b1"][metric] is not None]
        differences = []
        if paired:
            for _ in range(5000):
                sample = [paired[rng.randrange(len(paired))] for _ in paired]
                differences.append(statistics.mean(b - a for a, b in sample))
            differences.sort()
        result[metric] = {
            "b0_expanded": baseline, "b1": rule, "paired_components": len(paired),
            "paired_mean_difference_b1_minus_b0": statistics.mean(b - a for a, b in paired) if paired else None,
            "paired_component_bootstrap_95": [differences[125], differences[4874]] if differences else None,
        }
    return result


def main() -> None:
    packet_path = PACKET_DIR / "packet.json"
    manifest = json.loads((PACKET_DIR / "manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(packet_path.read_bytes()).hexdigest() != manifest["packet_sha256"]:
        raise ValueError("packet changed")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected = [pair["pair_id"] for pair in packet["pairs"]]
    a = read_scores(PACKET_DIR / "scores_a.jsonl", expected)
    b = read_scores(PACKET_DIR / "scores_b.jsonl", expected)
    ranking_path = RESULTS / "holdout_relations_v15/rankings.json"
    if hashlib.sha256(ranking_path.read_bytes()).hexdigest() != manifest["ranking_sha256"]:
        raise ValueError("ranking changed")
    ranks = {row["lab_id"]: row for row in json.loads(ranking_path.read_text(encoding="utf-8"))}
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    selected_ids = set(packet["selected_component_ids"])
    selected = [row for row in split["assignments"] if row["component_id"] in selected_ids]
    if len(selected) != 112 or len(packet["labs"]) != 136:
        raise ValueError("sample frame changed")
    report = {
        "status": "two_judge_descriptive_top5_only", "pairs": len(expected),
        "exact_label_agreement": sum(a[pid]["relevance"] == b[pid]["relevance"] for pid in expected) / len(expected),
        "judge_disagreements": sum(a[pid]["relevance"] != b[pid]["relevance"] for pid in expected),
        "judge": {}, "limitations": [
            "union-conditioned nDCG, not all-941-course nDCG",
            "no recall estimate or complete adoption decision",
            "judge B accidental unscored holdout snippet exposure before labels",
        ],
    }
    content_groups = eligible_content_groups()
    for name, scores in (("a", a), ("b", b)):
        lab_metrics = {lab_id: per_lab(lab_id, ranks[lab_id], scores) for lab_id in packet["labs"]}
        comps = component_means(selected, lab_metrics)
        deduped_labs = {lab_id: per_lab(lab_id, ranks[lab_id], scores, content_groups)
                        for lab_id in packet["labs"]}
        deduped_comps = component_means(selected, deduped_labs)
        sensitivity = {component["component_id"]: comps[component["component_id"]]
                       for component in selected if component["previous_split"] != "test"}
        report["judge"][name] = {
            "insufficient_evidence_pairs": sum(scores[pid]["insufficient_evidence"] for pid in expected),
            "all_selected_components": summarize(comps),
            "exact_content_candidate_sensitivity": {
                "method": "keep first code in each identical-content candidate group within original top five; no backfill; ideal group relevance is maximum judged code relevance",
                "metrics": summarize(deduped_comps),
            },
            "exclude_prior_test_components": {"components": len(sensitivity), "metrics": summarize(sensitivity)},
            "labs_without_relevant_union_item": sum(not metrics["b1"]["union_has_relevant"]
                                                    for metrics in lab_metrics.values()),
        }
    out = PACKET_DIR / "analysis.json"
    if out.exists():
        raise RuntimeError("analysis already exists")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
