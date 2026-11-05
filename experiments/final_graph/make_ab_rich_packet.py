"""Make position-blind paired presentation cards from frozen reason pilot."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/final_graph/results/reason_rich_v2"
OUT = ROOT / "experiments/final_graph/results/ab_rich_v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise RuntimeError("AB packet already exists")
    src = json.loads((SOURCE / "packet.json").read_text(encoding="utf-8"))
    source_key = json.loads((SOURCE / "key.json").read_text(encoding="utf-8"))
    holdout = json.loads((ROOT / "experiments/final_graph/results/holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))
    grouped = defaultdict(dict)
    for row in src["items"]:
        grouped[row["pair_id"]][source_key[row["item_id"]]] = row
    if len(grouped) != 27 or any(set(v) != {"R0", "R1"} for v in grouped.values()):
        raise ValueError("reason pair frame mismatch")
    cards = []
    key = {}
    for pair_id in sorted(grouped):
        options = grouped[pair_id]
        left_method = "R0" if hashlib.sha256(("ab-rich-v2|" + pair_id).encode()).digest()[0] % 2 == 0 else "R1"
        right_method = "R1" if left_method == "R0" else "R0"
        first = options[left_method]
        cards.append({"card_id": "ab:" + hashlib.sha256(pair_id.encode()).hexdigest()[:16],
                      "lab_id": first["lab_id"], "course_id": first["course_id"],
                      "lab_evidence": first["lab_evidence"], "course_evidence": first["course_evidence"],
                      "lab_context": holdout["labs"][first["lab_id"]],
                      "course_context": holdout["courses"][first["course_id"]],
                      "left_reason": options[left_method]["reason"],
                      "right_reason": options[right_method]["reason"]})
        key[cards[-1]["card_id"]] = {"left": left_method, "right": right_method, "pair_id": pair_id}
    OUT.mkdir()
    packet = {"purpose": "presentation preference pilot; same source pair per card",
              "instructions": "Choose left, right, tie, or neither for which reason better helps understand whether this course supports preparing for the lab. tie=both similarly helpful, neither=both unhelpful. Mark unsupported_left and unsupported_right if each text claims facts not justified by the shown source. Evaluate each card independently. Do not open key.json or prior score files until both judges finish.",
              "cards": cards}
    (OUT / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"cards": len(cards), "packet_sha256": sha(OUT / "packet.json"), "key_sha256": sha(OUT / "key.json"),
                "reason_packet_sha256": sha(SOURCE / "packet.json"), "reason_key_sha256": sha(SOURCE / "key.json"),
                "script_sha256": sha(Path(__file__))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
