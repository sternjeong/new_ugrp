"""Build blind paired reason-format packet after both relation judges finish."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from validate_relations import value, visible

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "reason_rich_v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label_map(path: Path, expected: list[str]) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [row["pair_id"] for row in rows] != expected:
        raise ValueError(f"judge labels incomplete: {path}")
    return {row["pair_id"]: row for row in rows}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("existing reason packet is immutable")
    packet_path = RESULTS / "holdout_relevance_v1/packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    expected = [row["pair_id"] for row in packet["pairs"]]
    judges = [label_map(RESULTS / f"holdout_relevance_v1/scores_{name}.jsonl", expected)
              for name in ("a", "b")]
    ranks_path = RESULTS / "holdout_relations_v15/rankings.json"
    ranks = {row["lab_id"]: row for row in json.loads(ranks_path.read_text(encoding="utf-8"))}
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    lab_component = {"lab:" + advisor: row["component_id"]
                     for row in split["assignments"]
                     for advisor in row["advisor_ids"]}
    candidates = {}
    excluded = Counter()
    for lab_id in sorted(packet["labs"]):
        top = ranks[lab_id]["b1"][:1]
        if not top:
            excluded["no_b1_top1"] += 1
            continue
        course_id = top[0]["course_id"]
        pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
        if pair_id not in judges[0] or any(j[pair_id]["relevance"] < 1 or
                                            j[pair_id]["insufficient_evidence"] for j in judges):
            excluded["not_relevant_by_both_with_sufficient_evidence"] += 1
            continue
        candidates.setdefault(lab_component[lab_id], []).append((lab_id, course_id, top[0]))
    rng = random.Random(20261014)
    selected = [candidates[component][rng.randrange(len(candidates[component]))]
                for component in sorted(candidates)]
    if len(selected) > 30:
        selected = rng.sample(selected, 30)
    selected.sort(key=lambda item: (lab_component[item[0]], item[0]))

    assertion_path = RESULTS / "holdout_relations_v15/assertions.jsonl"
    source_rows = {}
    for name in ("final_courses.jsonl", "final_labs.jsonl"):
        source_rows[name] = [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines()]
    needed = {link[key] for _, _, top in selected for link in top["links"][:1]
              for key in ("lab_assertion_id", "course_assertion_id")}
    assertions = {}
    for line in assertion_path.open(encoding="utf-8"):
        assertion = json.loads(line)
        if assertion["assertion_id"] in needed:
            assertions[assertion["assertion_id"]] = assertion
    concepts = {}
    for source in (ROOT / "data/concepts.json", ROOT / "experiments/final_graph/expanded_concepts_v1.json"):
        for concept in json.loads(source.read_text(encoding="utf-8"))["concepts"]:
            concepts[concept["id"]] = (concept.get("ko") or concept.get("en") or
                                       concept.get("aliases", [concept["id"]])[0])
    reasons, key = [], {}
    for lab_id, course_id, top in selected:
        link = top["links"][0]
        lab = assertions.get(link["lab_assertion_id"])
        course = assertions.get(link["course_assertion_id"])
        if not lab or not course or lab["object_id"] != course["object_id"]:
            excluded["missing_or_mismatched_assertion"] += 1
            continue
        if lab["predicate"] not in ("uses", "develops") or course["predicate"] != "teaches":
            excluded["invalid_relation_type"] += 1
            continue
        if not lab["evidence_text"].strip() or not course["evidence_text"].strip():
            excluded["empty_evidence"] += 1
            continue
        invalid_span = False
        for assertion in (lab, course):
            src = assertion["source"]
            raw = value(source_rows[src["source_file"]][src["source_row"] - 1], src["source_field"])
            start, end = src["span"]
            if (sha(ROOT / src["source_file"]) != src["source_sha256"] or
                    not (0 <= start < end <= len(raw)) or
                    raw[start:end] != assertion["evidence_text"] or
                    not visible((start, end), src["source_field"], raw)):
                invalid_span = True
                break
        if invalid_span:
            excluded["invalid_evidence_span"] += 1
            continue
        concept_id = link["concept_id"].removeprefix("concept:")
        concept = concepts.get(concept_id, concept_id)
        origin = "연구실 소개" if lab["evidence_scope"] == "intro" else "연구실 목록에 수록된 논문 초록"
        r0 = f"이 과목은 {concept}와 관련된 내용을 다루며, 연구실 자료에도 해당 주제가 나타납니다."
        r1 = (f"{origin}에는 ‘{lab['evidence_text']}’라고 나옵니다. "
              f"과목 자료에는 ‘{course['evidence_text']}’라고 나옵니다. "
              f"두 자료는 {concept} 관련 내용을 다룹니다.")
        pair_id = "pair:" + hashlib.sha256((lab_id + "|" + course_id).encode()).hexdigest()[:16]
        for method, reason in (("R0", r0), ("R1", r1)):
            item_id = "reason:" + hashlib.sha256((pair_id + "|" + method).encode()).hexdigest()[:16]
            reasons.append({"item_id": item_id, "pair_id": pair_id,
                            "lab_id": lab_id, "course_id": course_id,
                            "component_id": lab_component[lab_id],
                            "lab_evidence": lab["evidence_text"],
                            "course_evidence": course["evidence_text"],
                            "lab_source": lab["source"], "course_source": course["source"],
                            "reason": reason})
            key[item_id] = method
    rng.shuffle(reasons)
    OUT.mkdir()
    public = {"purpose": "blind paired reason-format fidelity, conditional on judged relevant B1 top1",
              "instructions": "Judge each reason for faithful 0/1, useful 0/1/2, and whether it should be withheld for insufficient evidence. Use only the quoted source evidence; strong prerequisite claims are unsupported.",
              "items": reasons}
    (OUT / "packet.json").write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": "unjudged_reason_format_packet", "pairs": len(reasons) // 2,
                "items": len(reasons), "candidate_components": len(candidates),
                "excluded": dict(excluded), "random_generator": "Python random.Random Mersenne Twister",
                "packet_sha256": sha(OUT / "packet.json"), "key_sha256": sha(OUT / "key.json"),
                "relation_packet_sha256": sha(packet_path), "rankings_sha256": sha(ranks_path),
                "assertions_sha256": sha(assertion_path), "script_sha256": sha(Path(__file__))}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
