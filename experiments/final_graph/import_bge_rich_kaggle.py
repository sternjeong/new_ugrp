"""Validate and import the Kaggle GPU BGE rankings into immutable experiment results."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    source = args.output_dir.resolve()
    ranking_path = source / "bge_rich_rankings.json"
    manifest_path = source / "bge_rich_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["device"] != "cuda:0" or not manifest["cuda_name"]:
        raise ValueError("Kaggle GPU execution not demonstrated")
    if sha(ranking_path) != manifest["ranking_sha256"]:
        raise ValueError("ranking hash mismatch")
    if sha(RESULTS / "holdout_relevance_v1/packet.json") != manifest["packet_sha256"]:
        raise ValueError("blind packet changed")
    if sha(RESULTS / "holdout_relations_v15/rankings.json") != manifest["rule_rankings_sha256"]:
        raise ValueError("frozen rule rankings changed")
    for filename, digest in manifest["source_hashes"].items():
        if sha(ROOT / filename) != digest:
            raise ValueError(f"source changed: {filename}")
    packet = json.loads((RESULTS / "holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))
    rows = json.loads(ranking_path.read_text(encoding="utf-8"))
    if manifest["courses"] != 941 or manifest["labs"] != 136 or len(rows) != 136:
        raise ValueError("frame count mismatch")
    if {row["lab_id"] for row in rows} != set(packet["labs"]):
        raise ValueError("lab frame mismatch")
    for row in rows:
        for method in ("dense", "dense_plus_frozen_rule"):
            items = row[method]
            ids = [item["course_id"] for item in items]
            if len(items) != 30 or len(set(ids)) != 30:
                raise ValueError("bad top-30 ranking")
            score = "dense_score" if method == "dense" else "hybrid_score"
            if items != sorted(items, key=lambda item: (-item[score], item["course_id"])):
                raise ValueError("ranking order mismatch")
    target = RESULTS / "bge_rich_v1"
    if target.exists():
        raise RuntimeError("existing ranking output is immutable")
    target.mkdir()
    shutil.copy2(ranking_path, target / "rankings.json")
    manifest["kaggle_run_id"] = "20261014-234632-bge-rich-kaggle"
    manifest["import_script_sha256"] = sha(Path(__file__))
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"imported": str(target), "labs": len(rows), "ranking_sha256": manifest["ranking_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
