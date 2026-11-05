"""Post-label sensitivity excluding components with judge-B insufficient flags.

This is exploratory and never replaces the preregistered analysis.json.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from analyze_holdout_relevance import PACKET_DIR, RESULTS, component_means, per_lab, read_scores, summarize


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    packet_path = PACKET_DIR / "packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected = [row["pair_id"] for row in packet["pairs"]]
    score_paths = {name: PACKET_DIR / f"scores_{name}.jsonl" for name in ("a", "b")}
    labels = {name: read_scores(path, expected) for name, path in score_paths.items()}
    flagged = {pid for pid, row in labels["b"].items() if row["insufficient_evidence"]}
    affected_labs = {row["lab_id"] for row in packet["pairs"] if row["pair_id"] in flagged}
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    selected_ids = set(packet["selected_component_ids"])
    selected = [row for row in split["assignments"] if row["component_id"] in selected_ids]
    clean = [row for row in selected if all("lab:" + aid not in affected_labs for aid in row["advisor_ids"])]
    ranks_path = RESULTS / "holdout_relations_v15/rankings.json"
    ranks = {row["lab_id"]: row for row in json.loads(ranks_path.read_text(encoding="utf-8"))}
    report = {
        "status": "post_label_exploratory_complete_component_sensitivity",
        "reason": "judge B flagged 21 pairs as insufficient; primary analysis uses their assigned 0/1/2 labels",
        "flagged_pairs": len(flagged),
        "flagged_score_distribution": dict(Counter(str(labels["b"][pid]["relevance"]) for pid in flagged)),
        "affected_labs": len(affected_labs),
        "excluded_components": len(selected) - len(clean),
        "remaining_components": len(clean),
        "judge": {},
        "source_sha256": {"packet": sha(packet_path), "rankings": sha(ranks_path),
                          "scores_a": sha(score_paths["a"]), "scores_b": sha(score_paths["b"]),
                          "primary_analysis": sha(PACKET_DIR / "analysis.json"),
                          "primary_script": sha(Path(__file__).with_name("analyze_holdout_relevance.py")),
                          "sensitivity_script": sha(Path(__file__))},
        "limitation": "Post-label complete-component exclusion changes the target population and can induce selection bias; interpret only as robustness check.",
    }
    for name, scores in labels.items():
        lab_metrics = {lab_id: per_lab(lab_id, ranks[lab_id], scores) for lab_id in packet["labs"]}
        report["judge"][name] = summarize(component_means(clean, lab_metrics))
    out = PACKET_DIR / "insufficient_sensitivity.json"
    if out.exists():
        raise RuntimeError("existing sensitivity output is immutable")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("flagged_pairs", "flagged_score_distribution", "affected_labs", "excluded_components", "remaining_components")}, indent=2))


if __name__ == "__main__":
    main()
