"""Freeze the untouched confirmation components before GPU ranking."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "embedding_field_ablation_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    path = OUT / "frame.json"
    if path.exists():
        raise RuntimeError("frozen frame already exists")
    split_path = RESULTS / "rich_split_v1.json"
    packet_path = RESULTS / "holdout_relevance_v1/packet.json"
    split = json.loads(split_path.read_text(encoding="utf-8"))
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    prior = set(packet["selected_component_ids"])
    buckets = {"confirm_unused": [], "explore_prior_packet": [], "explore_prior_test": []}
    for item in split["assignments"]:
        if item["split"] != "holdout":
            continue
        if item["component_id"] in prior:
            bucket = "explore_prior_packet"
        elif item["previous_split"] == "unused":
            bucket = "confirm_unused"
        elif item["previous_split"] == "test":
            bucket = "explore_prior_test"
        else:
            raise ValueError(item)
        buckets[bucket].append({"component_id": item["component_id"],
                                "lab_ids": ["lab:" + aid for aid in item["advisor_ids"]]})
    assert {key: (len(items), sum(len(x["lab_ids"]) for x in items)) for key, items in buckets.items()} == {
        "confirm_unused": (18, 28), "explore_prior_packet": (112, 136), "explore_prior_test": (7, 16)}
    frame = {"status": "frozen_before_embedding_rankings", "split_sha256": sha(split_path),
             "prior_packet_sha256": sha(packet_path), "buckets": buckets}
    path.write_text(json.dumps(frame, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"frame_sha256": sha(path), "split_sha256": sha(split_path),
                "prior_packet_sha256": sha(packet_path), "script_sha256": sha(Path(__file__))}
    (OUT / "frame_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
