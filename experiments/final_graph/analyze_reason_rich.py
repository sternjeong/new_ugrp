"""Analyze blind paired reason-format ratings on the conditional rich subset."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/final_graph/results/reason_rich_v2"
METHODS = ("R0", "R1")
METRICS = ("faithful", "useful", "withhold_insufficient_evidence")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_scores(path: Path, ids: list[str]) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["item_id"] for row in rows] != ids:
        raise ValueError(f"incomplete, duplicate or reordered scores: {path}")
    for row in rows:
        if row["faithful"] not in (0, 1) or row["useful"] not in (0, 1, 2) or not isinstance(row["withhold_insufficient_evidence"], bool):
            raise ValueError(f"invalid rating: {path}")
    return {row["item_id"]: row for row in rows}


def compare(paired: list[tuple[float, float]], seed: int = 20261015) -> dict:
    rng = random.Random(seed)
    diffs = []
    for _ in range(5000):
        sample = [paired[rng.randrange(len(paired))] for _ in paired]
        diffs.append(statistics.mean(b - a for a, b in sample))
    diffs.sort()
    return {"components": len(paired), "R0": statistics.mean(a for a, _ in paired),
            "R1": statistics.mean(b for _, b in paired),
            "paired_mean_difference_R1_minus_R0": statistics.mean(b - a for a, b in paired),
            "paired_component_bootstrap_95": [diffs[125], diffs[4874]]}


def main() -> None:
    packet_path = OUT / "packet.json"
    key_path = OUT / "key.json"
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if sha(packet_path) != manifest["packet_sha256"] or sha(key_path) != manifest["key_sha256"]:
        raise ValueError("packet/key hash mismatch")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    ids = [item["item_id"] for item in packet["items"]]
    if len(ids) != 54 or len(set(ids)) != 54 or set(ids) != set(key):
        raise ValueError("reason packet frame changed")
    pairs = {}
    for item in packet["items"]:
        pairs.setdefault(item["pair_id"], {})[key[item["item_id"]]] = item
    if len(pairs) != 27 or any(set(row) != set(METHODS) for row in pairs.values()):
        raise ValueError("unpaired reason methods")
    scores = {name: read_scores(OUT / f"scores_{name}.jsonl", ids) for name in ("a", "b")}
    report = {"status": "two_judge_conditional_paired_reason_format",
              "pairs": len(pairs), "components": len({row["R0"]["component_id"] for row in pairs.values()}),
              "raw_exact_agreement": {metric: sum(scores["a"][item_id][metric] == scores["b"][item_id][metric]
                                                  for item_id in ids) / len(ids) for metric in METRICS},
              "judge": {},
              "source_sha256": {"packet": sha(packet_path), "key": sha(key_path),
                                "scores_a": sha(OUT / "scores_a.jsonl"), "scores_b": sha(OUT / "scores_b.jsonl"),
                                "script": sha(Path(__file__))},
              "limitations": ["only B1 top-one pairs relevant and sufficient by both prior judges, with valid spans",
                              "same Luna judges previously saw relevance pairs; sentence style may reveal method",
                              "not free-generation/NLI comparison or user comprehension"]}
    if report["components"] != 27:
        raise ValueError("more than one pair per component")
    for name, ratings in scores.items():
        report["judge"][name] = {}
        for metric in METRICS:
            paired = []
            for pair_id in sorted(pairs):
                row = pairs[pair_id]
                values = [ratings[row[method]["item_id"]][metric] for method in METHODS]
                paired.append(tuple(float(value) for value in values))
            report["judge"][name][metric] = compare(paired)
    out = OUT / "analysis.json"
    if out.exists():
        raise RuntimeError("existing analysis is immutable")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
