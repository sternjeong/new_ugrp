"""Record frozen interpreter fidelity against declared synthetic query targets."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/query_understanding"))
from rule_interpreter import interpret  # noqa: E402


def main():
    folder = ROOT / "experiments/final_graph/results/query_rich_v3"
    source = folder / "query_targets.json"
    target = folder / "parser_diagnostic.json"
    if target.exists():
        raise RuntimeError("frozen diagnostic already exists")
    data = json.loads(source.read_text(encoding="utf-8"))
    topics = data["topics"]
    rows = []
    for q in data["queries"]:
        parsed = interpret(q["text"])
        checks = {}
        for side, key in (("likes", "positive_targets"), ("dislikes", "negative_targets")):
            checks[side] = []
            for topic in q[key]:
                phrase = topics[topic]["label"]
                exact = phrase in parsed[side]
                embedded = any(phrase in item for item in parsed[side])
                checks[side].append({"topic": topic, "target_phrase": phrase,
                                     "exact_phrase": exact, "embedded_phrase": embedded,
                                     "partial_or_missing": not embedded})
        rows.append({"query_id": q["id"], "group": q["group"], "parsed": parsed,
                     "target_checks": checks})
    out = {"status": "frozen_before_rankings", "query_targets_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
           "interpreter_sha256": hashlib.sha256((ROOT / "experiments/query_understanding/rule_interpreter.py").read_bytes()).hexdigest(),
           "rows": rows, "negative_target_partial_or_missing": sum(any(c["partial_or_missing"] for c in row["target_checks"]["dislikes"]) for row in rows),
           "positive_target_partial_or_missing": sum(any(c["partial_or_missing"] for c in row["target_checks"]["likes"]) for row in rows)}
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out["negative_target_partial_or_missing"], out["positive_target_partial_or_missing"])


if __name__ == "__main__":
    main()
