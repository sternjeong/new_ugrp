"""Import completed Kaggle GPU rankings after source and device verification."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"
VARIANTS = ("core", "lab_admin", "course_admin", "both_admin", "learning_context")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    source = args.run_dir
    rank_path = source / "embedding_field_rankings.json"
    manifest_path = source / "embedding_field_manifest.json"
    if not rank_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Kaggle outputs missing")
    if (DIR / "rankings.json").exists():
        raise RuntimeError("rankings already imported")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert m["device"].startswith("cuda") and "T4" in m["cuda_name"]
    assert m["model_revision"] == "5617a9f61b028005a4858fdac845db406aefb181"
    assert m["max_seq_length"] == 256 and m["labs"] == 180 and m["courses"] == 941
    assert m["profiles_sha256"] == sha(DIR / "profiles.json")
    assert m["frame_sha256"] == sha(DIR / "frame.json")
    assert m["profiles_manifest_sha256"] == sha(DIR / "profiles_manifest.json")
    assert m["rankings_sha256"] == sha(rank_path)
    rows = json.loads(rank_path.read_text(encoding="utf-8"))
    assert len(rows) == 180 and len({r["lab_id"] for r in rows}) == 180
    for row in rows:
        for variant in VARIANTS:
            items = row[variant]
            assert len(items) == 30
            assert len({x["course_id"] for x in items}) == 30
            assert all(type(x["score"]) in (int, float) for x in items)
    shutil.copyfile(rank_path, DIR / "rankings.json")
    m["kaggle_run_id"] = source.name
    m["imported_rankings_sha256"] = sha(DIR / "rankings.json")
    (DIR / "rankings_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": source.name, "rankings_sha256": m["rankings_sha256"]}))


if __name__ == "__main__":
    main()
