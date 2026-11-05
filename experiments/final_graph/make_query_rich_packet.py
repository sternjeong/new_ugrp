"""Build method-blind query/lab relevance packet from frozen top-five unions."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/final_graph/results/query_rich_v3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    packet_path = OUT / "packet.json"
    if packet_path.exists():
        raise RuntimeError("packet already exists")
    targets = json.loads((OUT / "query_targets.json").read_text(encoding="utf-8"))
    ranks = json.loads((OUT / "rankings.json").read_text(encoding="utf-8"))
    source_labs = json.loads((ROOT / "experiments/final_graph/results/holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))["labs"]
    queries = {q["id"]: {"text": q["text"], "group": q["group"]} for q in targets["queries"]}
    pair_rows = []
    used_labs = set()
    for rank in ranks:
        query_id = rank["query_id"]
        for lab_id in sorted({item["lab_id"] for method in ("q0", "q1") for item in rank[method]}):
            used_labs.add(lab_id)
            pair_id = "qp:" + hashlib.sha256(f"{query_id}|{lab_id}".encode()).hexdigest()[:16]
            pair_rows.append({"pair_id": pair_id, "query_id": query_id, "lab_id": lab_id})
    labs = {}
    for lab_id in sorted(used_labs):
        lab = source_labs[lab_id]
        labs[lab_id] = {"display_name": lab["display_name"],
                        "research_intro_first_1200": lab["research_intro"]["prefix"][:1200],
                        "representative_papers": [{"title": paper["title"],
                                                   "abstract_first_400": paper["abstract_first_800"][:400]}
                                                  for paper in lab["representative_papers"][:5]]}
    out = {"purpose": "method-blind judgment; judge every pair independently",
           "instructions": "For each query/lab pair, label relevance 0/1/2, violation true/false, insufficient_evidence true/false. Violation means the query's explicitly disliked research topic is substantively studied in intro or representative papers, not a stray word. For ambiguous/positive-only queries violation is false. Do not open query_targets.json or rankings.json while judging. Save JSONL keyed by pair_id with these three fields. If insufficient, still fill other fields but analysis will mark the query-method missing.",
           "queries": queries, "labs": labs, "pairs": pair_rows}
    packet_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"pairs": len(pair_rows), "queries": len(queries), "labs": len(labs),
                "packet_sha256": sha(packet_path), "rankings_sha256": sha(OUT / "rankings.json"),
                "query_targets_sha256": sha(OUT / "query_targets.json"),
                "script_sha256": sha(Path(__file__))}
    (OUT / "packet_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
