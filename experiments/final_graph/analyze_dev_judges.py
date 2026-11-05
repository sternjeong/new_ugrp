"""Summarize two blinded development judgments; never report as test accuracy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"


def scores(name):
    payload = json.loads((RESULTS / name).read_text(encoding="utf-8"))
    result = {item["pair_id"]: item["relevance"] for item in payload["scores"]}
    if len(result) != len(payload["scores"]):
        raise ValueError(f"duplicate pair ID in {name}")
    if any(value not in (0, 1, 2) for value in result.values()):
        raise ValueError(f"invalid relevance score in {name}")
    return result


def quadratic_kappa(a, b):
    ids = sorted(a)
    observed = sum((a[i] - b[i]) ** 2 for i in ids) / len(ids)
    ca, cb = Counter(a.values()), Counter(b.values())
    expected = sum((i - j) ** 2 * ca[i] * cb[j] for i in range(3) for j in range(3)) / len(ids) ** 2
    return None if not expected else round(1 - observed / expected, 4)


def main():
    packet = json.loads((RESULTS / "dev_judge_packet_v1.json").read_text(encoding="utf-8"))
    key = json.loads((RESULTS / "dev_judge_key_v1.json").read_text(encoding="utf-8"))
    a, b = scores("dev_judge_scores_a.json"), scores("dev_judge_scores_b.json")
    ids = {pair["pair_id"] for pair in packet["pairs"]}
    if set(a) != ids or set(b) != ids or set(key) != ids:
        raise ValueError("packet/key/judgment pair ID mismatch")
    by_method = {}
    for method in ("b0_expanded", "b1", "random"):
        selected = sorted(pair_id for pair_id in ids if method in key[pair_id])
        by_method[method] = {"pairs": len(selected),
                             "judge_a": dict(sorted(Counter(a[i] for i in selected).items())),
                             "judge_b": dict(sorted(Counter(b[i] for i in selected).items())),
                             "unanimous_zero": [i for i in selected if a[i] == b[i] == 0],
                             "unanimous_related": [i for i in selected if a[i] >= 1 and b[i] >= 1]}
    result = {"status": "development_error_discovery_only", "pairs": len(ids),
              "exact_agreement": round(sum(a[i] == b[i] for i in ids) / len(ids), 4),
              "quadratic_weighted_kappa": quadratic_kappa(a, b),
              "disagreements": [{"pair_id": i, "a": a[i], "b": b[i]} for i in sorted(ids) if a[i] != b[i]],
              "method": by_method}
    (RESULTS / "dev_judge_analysis_v1.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
