"""Extract explicit course prerequisite knowledge candidates from rich courses."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import relation_engine as relations

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/final_graph/results/prerequisite_knowledge_candidates.jsonl"
MANIFEST = ROOT / "experiments/final_graph/results/prerequisite_knowledge_manifest.json"
NEGATED_REQUIRED = re.compile(r"(?i)\bno prerequisites? (?:is|are) required\b|\b(?:not|no)\s+(?:pre-)?(?:required|mandatory|prerequisites?)\b|\bwithout prior\b|\bno prior knowledge\b|필수(?:는|가)?\s*아님|필요하지 않|요구하지 않|선수과목 없음|선수지식 없음")
RECOMMENDED = re.compile(r"(?i)\b(recommend\w*|prefer\w*|helpful|desirable|useful|beneficial)\b|권장|추천|바람직|도움")
MANDATORY = re.compile(r"(?i)\b(mandatory|required|requirement|must have|should have|should know|expected to know)\b|필수|요구")
BOUNDARY = re.compile(r"[\r\n;]|(?<=[.!?])\s+(?=[A-Z가-힣])")


def context(text: str, start: int, end: int) -> tuple[str, tuple[int, int]]:
    cuts = [0]
    for match in BOUNDARY.finditer(text):
        cuts.extend((match.start(), match.end()))
    cuts.append(len(text))
    left = max(cut for cut in cuts if cut <= start)
    right = min(cut for cut in cuts if cut >= end)
    return text[left:right], (left, right)


def qualifier(clause: str) -> str:
    # The qualifier is deliberately coarse. A mention remains unreviewed even
    # when a local signal appears to be explicit.
    negative = bool(NEGATED_REQUIRED.search(clause))
    recommended = bool(RECOMMENDED.search(clause))
    positive_required = bool(MANDATORY.search(NEGATED_REQUIRED.sub("", clause)))
    if recommended and not positive_required:
        return "recommended_candidate"
    if positive_required and not recommended and not negative:
        return "required_candidate"
    if negative and not recommended and not positive_required:
        return "not_required_candidate"
    return "ambiguous_or_unspecified"


def main():
    eligibility = json.loads((ROOT / "experiments/final_graph/results/complete_subset_v1.json").read_text(encoding="utf-8"))
    allowed = set(eligibility["eligible_course_source_rows"])
    vocab = relations.vocabulary()
    course_rows = relations.load_rows("final_courses.jsonl")
    source_hash = hashlib.sha256((ROOT / "final_courses.jsonl").read_bytes()).hexdigest()
    if source_hash != eligibility["source_hashes"]["final_courses.jsonl"]:
        raise ValueError("source changed since eligibility audit")
    counts = Counter()
    literal_occurrences = 0
    with OUT.open("w", encoding="utf-8") as stream:
        for row_no, row in enumerate(course_rows, 1):
            if row_no not in allowed:
                continue
            text = row["prerequisites"] or ""
            if not text.strip():
                continue
            occurrence_spans = set()
            for cid, concept in vocab.items():
                if concept["kind"] == "knowledge":
                    for _, pattern in concept["patterns"]:
                        occurrence_spans.update((cid, match.start(), match.end()) for match in pattern.finditer(text))
            literal_occurrences += len(occurrence_spans)
            for cid, alias, span in relations.matches(text, vocab):
                if vocab[cid]["kind"] != "knowledge":
                    continue
                clause, clause_span = context(text, *span)
                item = {"subject_id": "course:" + row["course_code"].strip().upper(),
                        "predicate": "prerequisite_knowledge_mention", "object_id": "concept:" + cid,
                        "qualifier_candidate": qualifier(clause), "matched_alias": alias,
                        "source": {"source_file": "final_courses.jsonl", "source_sha256": source_hash,
                                   "source_row": row_no, "source_field": "prerequisites", "span": list(span)},
                        "evidence_text": text[span[0]:span[1]], "context_text": clause,
                        "context_span": list(clause_span), "review_status": "unreviewed"}
                stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
                counts[cid] += 1
    summary = {"status": "unreviewed_course_concept_mention_candidates",
               "distinct_course_concept_candidates": sum(counts.values()),
               "literal_knowledge_alias_occurrences": literal_occurrences,
               "concept_counts": dict(counts),
               "source_sha256": source_hash,
               "eligibility_sha256": hashlib.sha256((ROOT / "experiments/final_graph/results/complete_subset_v1.json").read_bytes()).hexdigest(),
               "base_vocabulary_sha256": hashlib.sha256((ROOT / "data/concepts.json").read_bytes()).hexdigest(),
               "overlay_vocabulary_sha256": hashlib.sha256((ROOT / "experiments/final_graph/expanded_concepts_v1.json").read_bytes()).hexdigest(),
               "relation_engine_sha256": hashlib.sha256((ROOT / "experiments/final_graph/relation_engine.py").read_bytes()).hexdigest(),
               "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "output_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest()}
    MANIFEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
