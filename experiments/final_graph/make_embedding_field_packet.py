"""Create a method-blind fresh-label packet for the 18 untouched components."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"
VARIANTS = ("core", "lab_admin", "course_admin", "both_admin", "learning_context")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pid(lab, course):
    return "pair:" + hashlib.sha256((lab + "|" + course).encode()).hexdigest()[:16]


def main():
    packet_path = DIR / "packet.json"
    if packet_path.exists():
        raise RuntimeError("frozen packet already exists")
    frame_path, profiles_path = DIR / "frame.json", DIR / "profiles.json"
    rankings_path = DIR / "rankings.json"
    frame = json.loads(frame_path.read_text(encoding="utf-8"))
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    rankings = json.loads(rankings_path.read_text(encoding="utf-8"))
    labs = {x["id"]: x for x in profiles["labs"]}
    courses = {x["id"]: x for x in profiles["courses"]}
    rankings = {x["lab_id"]: x for x in rankings}
    confirm = frame["buckets"]["confirm_unused"]
    confirm_labs = [lid for item in confirm for lid in item["lab_ids"]]
    assert len(confirm) == 18 and len(confirm_labs) == len(set(confirm_labs)) == 28
    assert set(rankings) == set(labs) and len(courses) == 941
    pairs = {}
    exposure = {v: [] for v in VARIANTS}
    for lab in confirm_labs:
        row = rankings[lab]
        for variant in VARIANTS:
            top = row[variant][:5]
            assert len(top) == 5 and len({x["course_id"] for x in top}) == 5
            for rank, item in enumerate(top, 1):
                course = item["course_id"]
                pair = {"pair_id": pid(lab, course), "lab_id": lab, "course_id": course}
                pairs[pair["pair_id"]] = pair
                exposure[variant].append({"pair_id": pair["pair_id"], "lab_id": lab,
                                          "course_id": course, "rank": rank})
    pair_rows = list(pairs.values())
    random.Random(20261016).shuffle(pair_rows)
    packet = {
        "purpose": "field_ablation_fresh18_core_evidence_only",
        "scale": {"0": "연구 근거로 준비 과목 관련성 없음", "1": "부분적으로 도움 또는 넓은 지식 연결",
                  "2": "연구 방법·도구·핵심 지식의 직접적인 준비 연결"},
        "instructions": "lab/course core 청크만 보고 판정. 같은 주제 단어만으로 직접 준비 연결을 단정하지 말 것. 근거가 부족하면 insufficient_evidence=true. 순위/방법은 보지 말 것.",
        "confirm_component_ids": [x["component_id"] for x in confirm],
        "labs": {lid: {"core": labs[lid]["core"]} for lid in confirm_labs},
        "courses": {cid: {"core": courses[cid]["core"]} for cid in sorted({p["course_id"] for p in pair_rows})},
        "pairs": pair_rows,
    }
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    key_path = DIR / "method_key.json"
    key_path.write_text(json.dumps({"exposure": exposure}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"packet_sha256": sha(packet_path), "method_key_sha256": sha(key_path),
                "rankings_sha256": sha(rankings_path), "frame_sha256": sha(frame_path),
                "profiles_sha256": sha(profiles_path), "builder_sha256": sha(Path(__file__)),
                "confirm_components": len(confirm), "confirm_labs": len(confirm_labs),
                "new_pairs": len(pair_rows),
                "top5_exposures_per_variant": {v: len(rows) for v, rows in exposure.items()}}
    (DIR / "packet_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
