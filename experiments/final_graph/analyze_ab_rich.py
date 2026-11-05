"""Summarize small paired reason presentation preference pilot."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/ab_rich_v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = DIR / "analysis.json"
    if output.exists():
        raise RuntimeError("existing analysis immutable")
    manifest = json.loads((DIR / "manifest.json").read_text(encoding="utf-8"))
    if sha(DIR / "packet.json") != manifest["packet_sha256"] or sha(DIR / "key.json") != manifest["key_sha256"]:
        raise ValueError("packet/key hash mismatch")
    packet = json.loads((DIR / "packet.json").read_text(encoding="utf-8"))
    key = json.loads((DIR / "key.json").read_text(encoding="utf-8"))
    expected = [card["card_id"] for card in packet["cards"]]
    if len(expected) != 27 or set(expected) != set(key):
        raise ValueError("card frame mismatch")
    judge_scores = {}
    report = {"status": "two_judge_paired_presentation_pilot", "cards": len(expected),
              "source_sha256": {"packet": sha(DIR / "packet.json"), "key": sha(DIR / "key.json"),
                                "script": sha(Path(__file__))}, "judge": {},
              "limitations": ["same two Luna judges previously saw these reason sentences",
                              "format reveals the likely method despite positional blinding",
                              "not a real-student or top-five list A/B test"]}
    for judge in ("a", "b"):
        path = DIR / f"scores_{judge}.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if [row["card_id"] for row in rows] != expected:
            raise ValueError(f"score coverage/order mismatch {judge}")
        if any(row["choice"] not in ("left", "right", "tie", "neither") or
               type(row["unsupported_left"]) is not bool or type(row["unsupported_right"]) is not bool for row in rows):
            raise ValueError(f"invalid scores {judge}")
        judge_scores[judge] = {r["card_id"]: r for r in rows}
        counts = Counter()
        unsupported = Counter()
        for row in rows:
            card_id = row["card_id"]
            choice = row["choice"]
            counts[key[card_id][choice] if choice in ("left", "right") else choice] += 1
            for side in ("left", "right"):
                unsupported[key[card_id][side]] += int(row["unsupported_" + side])
        report["judge"][judge] = {"choices": dict(counts), "unsupported_claim_flags": dict(unsupported)}
        report["source_sha256"][f"scores_{judge}"] = sha(path)
    report["exact_choice_agreement"] = sum(judge_scores["a"][cid]["choice"] == judge_scores["b"][cid]["choice"] for cid in expected) / len(expected)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "agreement": report["exact_choice_agreement"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
