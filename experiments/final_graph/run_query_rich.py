"""CPU lexical query-understanding comparison on frozen rich lab rows.

TF-IDF is a sparse lexical baseline, not GPU-specialized model inference.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/query_understanding"))
from rule_interpreter import interpret  # noqa: E402

RESULTS = ROOT / "experiments/final_graph/results"
TARGET = RESULTS / "query_rich_v3"
NEG_CUE = re.compile(r"싫|별로|관심\s*없|질렸|빼고|제외|말고")
INTERPRETER_HASH = "6f58e3edc44ed104a766d41361a5e837a9c311486ffc0a43234fbc3c962ce3b1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def main() -> None:
    if (TARGET / "rankings.json").exists():
        raise RuntimeError("existing query ranking is immutable")
    if sha(ROOT / "experiments/query_understanding/rule_interpreter.py") != INTERPRETER_HASH:
        raise ValueError("query interpreter changed")
    target_path = TARGET / "query_targets.json"
    target_manifest = json.loads((TARGET / "targets_manifest.json").read_text(encoding="utf-8"))
    if sha(target_path) != target_manifest["query_targets_sha256"]:
        raise ValueError("query text/targets changed")
    diagnostic_path = TARGET / "parser_diagnostic.json"
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    if diagnostic["status"] != "frozen_before_rankings" or diagnostic["query_targets_sha256"] != sha(target_path) or diagnostic["interpreter_sha256"] != INTERPRETER_HASH:
        raise ValueError("parser diagnostic mismatch")
    fixed = json.loads(target_path.read_text(encoding="utf-8"))
    packet = json.loads((RESULTS / "holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))
    lab_ids = sorted(packet["labs"])
    rows = {"lab:" + row["advisor_id"]: row
            for row in (json.loads(line) for line in (ROOT / "final_labs.jsonl").read_text(encoding="utf-8").splitlines())
            if "lab:" + row["advisor_id"] in packet["labs"]}
    if len(lab_ids) != 136 or set(rows) != set(lab_ids):
        raise ValueError("lab frame mismatch")
    docs = []
    for lab_id in lab_ids:
        row = rows[lab_id]
        parts = [(row.get("research_intro") or "")[:1200]]
        for paper in (row.get("representative_papers") or [])[:5]:
            title = paper.get("title") or ""
            abstract = (paper.get("abstract") or "")[:400]
            if title.strip() and abstract.strip():
                parts.append(f"{title} | {abstract}")
        docs.append("\n".join(parts))
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1, sublinear_tf=True)
    matrix = vectorizer.fit_transform(docs)

    def similarities(text: str) -> list[float]:
        return (vectorizer.transform([normalize(text)]) @ matrix.T).toarray()[0].tolist()

    output = []
    for query in fixed["queries"]:
        raw = query["text"]
        parsed = interpret(raw)
        q0_scores = similarities(raw)
        q0 = sorted(({"lab_id": lab_id, "score": round(score, 6)}
                     for lab_id, score in zip(lab_ids, q0_scores)),
                    key=lambda item: (-item["score"], item["lab_id"]))[:5]
        hold = None
        if not parsed["likes"]:
            hold = "no_positive_phrase"
        elif NEG_CUE.search(raw) and not parsed["dislikes"]:
            hold = "negative_cue_unparsed"
        q1 = []
        if hold is None:
            positive = similarities(" ".join(parsed["likes"]))
            negatives = [similarities(phrase) for phrase in parsed["dislikes"]]
            scores = [pos - 0.5 * max((negative[i] for negative in negatives), default=0.0)
                      for i, pos in enumerate(positive)]
            q1 = sorted(({"lab_id": lab_id, "score": round(score, 6)}
                         for lab_id, score in zip(lab_ids, scores)),
                        key=lambda item: (-item["score"], item["lab_id"]))[:5]
        output.append({"query_id": query["id"], "group": query["group"],
                       "parsed_likes": parsed["likes"], "parsed_dislikes": parsed["dislikes"],
                       "q1_abstain_reason": hold, "q0": q0, "q1": q1})
    ranking_path = TARGET / "rankings.json"
    ranking_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": "unjudged_query_rankings", "queries": len(output), "labs": len(lab_ids),
                "query_targets_sha256": sha(target_path),
                "parser_diagnostic_sha256": sha(diagnostic_path),
                "relation_packet_sha256": sha(RESULTS / "holdout_relevance_v1/packet.json"),
                "final_labs_sha256": sha(ROOT / "final_labs.jsonl"),
                "interpreter_sha256": INTERPRETER_HASH,
                "vectorizer": "TfidfVectorizer(char, 2-5, min_df=1, sublinear_tf=True)",
                "features": len(vectorizer.vocabulary_),
                "q1_abstention_count": sum(row["q1_abstain_reason"] is not None for row in output),
                "rankings_sha256": sha(ranking_path), "script_sha256": sha(Path(__file__))}
    (TARGET / "ranking_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
