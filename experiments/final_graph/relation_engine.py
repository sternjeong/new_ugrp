"""Draft typed, source-backed lab/course relation rules for the locked pilot.

Only run on the development split until rule code and vocabulary are frozen.
The output contains candidate assertions and rankings, not verified facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = ("final_courses.jsonl", "final_labs.jsonl")
SOURCE_HASHES = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}
BROAD = {"machine_learning", "materials_science", "statistics_probability", "optimization", "quantum",
         "semiconductor_devices", "bioinformatics_molecules", "photonics_optics", "algorithms_theory",
         "software_engineering", "education_technology", "nanomaterials_2d", "circuit_design"}
NAV = {"research", "home", "member", "members", "professor", "news", "publication", "publications",
       "contact", "about", "gallery", "project", "projects", "board", "notice", "introduction", "research areas"}
NOISE = re.compile(r"(?i)\b(email|e-mail|phone|address|alumni|copyright|click here|join us|news|notice|gallery)\b|공지|뉴스|회원|구성원|오시는 길|연락처|채용|\[[^\]]{0,20}(?:신문|일보|뉴스|통신|포커스)\]")
LAB_RESEARCH = re.compile(r"(?i)\b(research|study|studies|investigat\w*|develop\w*|design\w*|fabricat\w*|explor\w*|focus\w*|analy\w*|model\w*)\b|연구|개발|설계|제작|분석|탐구")
LAB_USE = re.compile(r"(?i)\b(us(?:e|es|ing|ed)|utiliz\w*|appl(?:y|ies|ied)|employ\w*|through|via|based on|modulat\w*|train\w*|demonstrat\w*|implement\w*|validat\w*|simulat(?:e|es|ed|ing)|measure\w*)\b|사용|활용|적용|기반|통해|이용")
LAB_DEVELOP = re.compile(r"(?i)\b(develop\w*|design\w*|fabricat\w*|propos\w*|present\w*|introduc\w*|report\w*)\b|개발|설계|제작|제안")
PAPER_OWN = re.compile(r"(?i)\b(we|our|this study|this work|herein|in this paper|the proposed (?:method|approach|model|strategy))\b|본 연구|이 연구|제안한 방법|제안된 방법")
INTRO_OWN = re.compile(r"(?i)\b(we|our|the lab|this lab|our lab|research (?:focus|aim|area|group)|focus(?:es|ed|ing)? on)\b|본 연구실|우리 연구실|저희 연구실|연구실은|연구팀은")
COURSE_LEARN = re.compile(r"(?i)\b(learn|study|studies|teach|cover|understand|practice|acquire|introduce|explore|training)\b|배운|학습|습득|이해|다룬|연습|소개|강의|익힌")
NEGATION = re.compile(r"(?i)\b(not|never|without|lack of|unrelated|no longer)\b|않|아니|제외|없이")


def load_rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines() if line]


def vocabulary(*, legacy: bool = False) -> dict[str, dict]:
    old = json.loads((ROOT / "data/concepts.json").read_text(encoding="utf-8"))["concepts"]
    overlay = json.loads((ROOT / "experiments/final_graph/expanded_concepts_v1.json").read_text(encoding="utf-8"))
    exclusions = {} if legacy else {cid: set(values) for cid, values in overlay["legacy_alias_exclusions"].items()}
    additions = {} if legacy else overlay.get("legacy_alias_additions", {})
    result = {item["id"]: {"id": item["id"], "kind": item["kind"],
                            "aliases": [alias for alias in item["keywords"] if alias not in exclusions.get(item["id"], set())]
                                       + additions.get(item["id"], []),
                            "origin": "old", "broad": item["id"] in BROAD} for item in old}
    for item in ([] if legacy else overlay["concepts"]):
        if item["id"] in result:
            raise ValueError(f"duplicate concept id: {item['id']}")
        result[item["id"]] = {**item, "origin": "expanded", "broad": False}
    for item in result.values():
        patterns = []
        for alias in dict.fromkeys(item["aliases"]):
            alias = alias.strip()
            if len(alias) < 2:
                continue
            pattern = re.escape(alias)
            if re.fullmatch(r"[A-Za-z0-9 -]+", alias):
                pattern = r"(?<![A-Za-z0-9])" + pattern + r"(?![A-Za-z0-9])"
            patterns.append((alias.casefold(), re.compile(pattern, re.IGNORECASE)))
        item["patterns"] = patterns
    return result


def chunks(text: str, *, field: str, limit: int | None = None):
    """Yield source-preserving line/sentence spans, shared by all methods."""
    if limit is not None:
        text = text[:limit]
    pos = 0
    for line in text.splitlines(keepends=True):
        for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", line):
            raw = match.group(0)
            trim = len(raw) - len(raw.lstrip())
            value = raw.strip()
            if not value:
                continue
            if field == "research_intro" and (value.casefold() in NAV or NOISE.search(value)):
                continue
            yield value, (pos + match.start() + trim, pos + match.start() + trim + len(value))
        pos += len(line)


def visible_chunks(text: str, *, field: str, scope: str):
    """Use exactly the method-independent text windows shown to judges."""
    if scope == "intro":
        windows = [(0, min(len(text), 6000))]
        tail_start = max(0, len(text) - 2000)
        if tail_start > windows[0][1]:
            windows.append((tail_start, len(text)))
        elif len(text) > windows[0][1]:
            windows[0] = (0, len(text))
    else:
        limit = {"paper_abstract": 800, "description": 2000,
                 "Lesson Objectives": 2000, "Lecture progress plan": 4000}.get(scope)
        windows = [(0, min(len(text), limit if limit is not None else len(text)))]
    for start, end in windows:
        for segment, (local_start, local_end) in chunks(text[start:end], field=field):
            yield segment, (start + local_start, start + local_end)


def matches(text: str, vocab: dict[str, dict], *, prune_nested: bool = True):
    folded = text.casefold()
    found = []
    for cid, item in vocab.items():
        for alias, pattern in item["patterns"]:
            if alias not in folded:
                continue
            match = pattern.search(text)
            if match:
                found.append((cid, match.group(0), match.span()))
                break
    for cid, alias, span in found:
        if prune_nested and any(other_cid != cid
                                and other_span[0] <= span[0] and span[1] <= other_span[1]
                                and other_span != span
                                for other_cid, _, other_span in found):
            continue
        yield cid, alias, span


def source(name: str, row_no: int, field: str, span: tuple[int, int]) -> dict:
    return {"source_file": name, "source_sha256": SOURCE_HASHES[name], "source_row": row_no,
            "source_field": field, "span": list(span)}


def assertion(owner: str, concept: str, relation: str, text: str, src: dict, *, strength: float, scope: str) -> dict:
    key = json.dumps([owner, concept, relation, src], sort_keys=True, ensure_ascii=False)
    return {"assertion_id": "assertion:" + hashlib.sha256(key.encode()).hexdigest()[:20],
            "subject_id": owner, "predicate": relation, "object_id": "concept:" + concept,
            "evidence_text": text, "source": src, "strength": strength, "evidence_scope": scope,
            "assertion_origin": "rule_inferred", "review_status": "unreviewed"}


def lab_assertions(row: dict, row_no: int, vocab: dict[str, dict], legacy_vocab: dict[str, dict]) -> tuple[list[dict], set[str], set[str]]:
    owner = "lab:" + row["advisor_id"]
    assertions, old_hits, all_hits = [], set(), set()
    fields = [("research_intro", row["research_intro"] or "", "intro")]
    paper_titles = [" ".join((paper.get("title") or "").casefold().split())
                    for paper in row["representative_papers"][:5]]
    for index, paper in enumerate(row["representative_papers"][:5]):
        fields.append((f"representative_papers[{index}].title", paper["title"] or "", "paper_title"))
        fields.append((f"representative_papers[{index}].abstract", paper["abstract"] or "", "paper_abstract"))
    for field, text, scope in fields:
        previous_segment = ""
        for segment, span in visible_chunks(text, field="research_intro" if scope == "intro" else field, scope=scope):
            own_paper_current = bool(PAPER_OWN.search(segment))
            own_paper_context = own_paper_current or bool(PAPER_OWN.search(previous_segment))
            previous_segment = segment
            normalized_segment = " ".join(segment.casefold().split())
            # Scraped introductions sometimes embed a publication list. A
            # title containing "using" is not an independent lab-use claim.
            if scope == "intro" and any(len(title) >= 30 and title in normalized_segment for title in paper_titles):
                continue
            old_hits.update(cid for cid, _, _ in matches(segment, legacy_vocab, prune_nested=False))
            for cid, alias, local_span in matches(segment, vocab):
                item = vocab[cid]
                all_hits.add(cid)
                # A word mention is a retrieval candidate, not a research claim.
                if NEGATION.search(segment):
                    continue
                relation, strength = None, 0.0
                has_lab_action = LAB_USE.search(segment) or LAB_DEVELOP.search(segment)
                if item["kind"] in ("method", "tool") and has_lab_action and (
                    scope == "intro" and INTRO_OWN.search(segment) or
                    scope == "paper_abstract" and own_paper_context):
                    relation = "uses" if LAB_USE.search(segment) else "develops"
                    base = 1.0 if relation == "uses" else 0.8
                    strength = base if scope == "intro" else base * (0.55 if own_paper_current else 0.4)
                elif item["kind"] in ("domain", "problem", "material") and LAB_RESEARCH.search(segment):
                    relation, strength = "studies", 0.85 if scope == "intro" else 0.5
                if relation and scope != "paper_title":
                    assertions.append(assertion(owner, cid, relation, segment,
                                                source("final_labs.jsonl", row_no, field, span),
                                                strength=strength, scope=scope))
    return assertions, old_hits, all_hits


def course_assertions(row: dict, row_no: int, vocab: dict[str, dict], legacy_vocab: dict[str, dict]) -> tuple[list[dict], set[str], set[str]]:
    owner = "course:" + row["course_code"].strip().upper()
    assertions, old_hits, all_hits = [], set(), set()
    fields = (("course_title", row["course_title"]), ("description", row["description"]),
              ("Lesson Objectives", row["Lesson Objectives"]), ("Lecture progress plan", row["Lecture progress plan"]))
    plan_segment_counts = defaultdict(int)
    for segment, _ in visible_chunks(row["Lecture progress plan"] or "", field="Lecture progress plan", scope="Lecture progress plan"):
        if not NEGATION.search(segment):
            for cid, _, _ in matches(segment, vocab):
                plan_segment_counts[cid] += 1
    seen = set()
    for field, text in fields:
        if not text:
            continue
        for segment, span in visible_chunks(text, field=field, scope=field):
            old_hits.update(cid for cid, _, _ in matches(segment, legacy_vocab, prune_nested=False))
            for cid, alias, local_span in matches(segment, vocab):
                all_hits.add(cid)
                if NEGATION.search(segment):
                    continue
                if field == "course_title":
                    strength, coverage = 1.0, "title"
                elif field == "Lecture progress plan":
                    coverage = "repeated_plan_segments" if plan_segment_counts[cid] >= 2 else "single_plan_segment"
                    strength = 0.7 if plan_segment_counts[cid] >= 2 else 0.35
                elif COURSE_LEARN.search(segment):
                    strength, coverage = (0.8 if field == "Lesson Objectives" else 0.65), "learning_statement"
                else:
                    continue
                # Many objectives duplicate descriptions. Keep the stronger
                # source while preserving its exact field-level provenance.
                signature = (cid, re.sub(r"\s+", " ", segment.casefold()))
                if signature in seen:
                    continue
                seen.add(signature)
                entry = assertion(owner, cid, "teaches", segment,
                                  source("final_courses.jsonl", row_no, field, span),
                                  strength=strength, scope=field)
                entry["coverage"] = coverage
                assertions.append(entry)
    return assertions, old_hits, all_hits


def rank(lab: list[dict], courses: dict[str, list[dict]], vocab: dict[str, dict]) -> list[dict]:
    by_lab = defaultdict(list)
    for item in lab:
        if item["predicate"] in ("uses", "develops", "studies"):
            by_lab[item["object_id"]].append(item)
    ranking = []
    for course_id, entries in courses.items():
        by_course = defaultdict(list)
        for item in entries:
            if item["predicate"] == "teaches":
                by_course[item["object_id"]].append(item)
        links = []
        for concept_id in by_lab.keys() & by_course.keys():
            cid = concept_id.removeprefix("concept:")
            concept = vocab[cid]
            if concept["broad"]:
                continue
            la = max(by_lab[concept_id], key=lambda item: item["strength"])
            ca = max(by_course[concept_id], key=lambda item: item["strength"])
            if la["predicate"] == "uses" and concept["kind"] in ("method", "tool"):
                relation, weight = "supports_method" if concept["kind"] == "method" else "supports_tool", 1.0
            elif la["predicate"] == "develops" and concept["kind"] == "method":
                relation, weight = "supports_method_development", 0.8
            else:
                continue
            score = round(weight * la["strength"] * ca["strength"], 4)
            links.append({"relation": relation, "concept_id": cid, "score": score,
                          "lab_assertion_id": la["assertion_id"], "course_assertion_id": ca["assertion_id"]})
        if links:
            links.sort(key=lambda item: (-item["score"], item["concept_id"]))
            # Cap independent-concept contribution; repeated papers/syllabi do
            # not inflate rank merely because they are long.
            score = round(links[0]["score"] + 0.15 * sum(item["score"] for item in links[1:3]), 4)
            ranking.append({"course_id": course_id, "score": score, "links": links})
    ranking.sort(key=lambda item: (-item["score"], item["course_id"]))
    return ranking


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "test", "holdout"), required=True)
    parser.add_argument("--frame", choices=("original", "rich"), default="original")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    split_name = "rich_split_v1.json" if args.frame == "rich" else "split_v1.json"
    if args.frame == "original" and args.split == "holdout":
        parser.error("holdout requires --frame rich")
    if args.frame == "rich" and args.split == "test":
        parser.error("test requires --frame original")
    split_path = ROOT / "experiments/final_graph/results" / split_name
    split_data = json.loads(split_path.read_text(encoding="utf-8"))
    if args.frame == "rich":
        if split_data["source_hashes"] != SOURCE_HASHES:
            raise ValueError("current source hashes do not match frozen rich split")
    elif split_data["source_sha256"] != SOURCE_HASHES["final_labs.jsonl"]:
        raise ValueError("current lab source hash does not match frozen original split")
    allowed = {aid for component in split_data["assignments"] if component["split"] == args.split
               for aid in component["advisor_ids"]}
    vocab = vocabulary()
    legacy_vocab = vocabulary(legacy=True)
    course_rows = load_rows("final_courses.jsonl")
    lab_rows = load_rows("final_labs.jsonl")
    eligible_course_rows = None
    eligibility_sha = None
    if args.frame == "rich":
        eligibility_path = ROOT / "experiments/final_graph/results/complete_subset_v1.json"
        eligibility_sha = hashlib.sha256(eligibility_path.read_bytes()).hexdigest()
        if eligibility_sha != split_data["eligibility_sha256"]:
            raise ValueError("eligibility audit changed since rich split was frozen")
        eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
        eligible_course_rows = set(eligibility["eligible_course_source_rows"])
        if len(eligible_course_rows) != split_data["eligible_course_rows"]:
            raise ValueError("rich course frame count mismatch")
    course_entries, course_old, course_all = {}, {}, {}
    all_assertions = []
    for no, row in enumerate(course_rows, 1):
        if eligible_course_rows is not None and no not in eligible_course_rows:
            continue
        entries, old, all_ = course_assertions(row, no, vocab, legacy_vocab)
        cid = "course:" + row["course_code"].strip().upper()
        course_entries[cid], course_old[cid], course_all[cid] = entries, old, all_
        all_assertions.extend(entries)
    output = []
    for no, row in enumerate(lab_rows, 1):
        if row["advisor_id"] not in allowed:
            continue
        entries, old, all_ = lab_assertions(row, no, vocab, legacy_vocab)
        all_assertions.extend(entries)
        b1 = rank(entries, course_entries, vocab)
        def overlap(course_hits: dict[str, set[str]], lab_hits: set[str]) -> list[dict]:
            scored = []
            for course_id, hits in course_hits.items():
                shared = hits & lab_hits
                if shared:
                    score = round(sum(0.5 if cid in BROAD else 1.0 for cid in shared), 3)
                    scored.append({"course_id": course_id, "score": score, "shared_concepts": sorted(shared)})
            return sorted(scored, key=lambda item: (-item["score"], item["course_id"]))
        output.append({"lab_id": "lab:" + row["advisor_id"], "b0_old": overlap(course_old, old),
                       "b0_expanded": overlap(course_all, all_), "b1": b1})
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "assertions.jsonl").open("w", encoding="utf-8") as stream:
        for item in all_assertions:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    (args.out / "rankings.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"split": args.split, "frame": args.frame, "labs": len(output), "courses": len(course_entries),
                "assertions": len(all_assertions), "source_hashes": SOURCE_HASHES,
                "split_sha256": hashlib.sha256(split_path.read_bytes()).hexdigest(),
                "eligibility_sha256": eligibility_sha,
                "engine_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "legacy_vocabulary_sha256": hashlib.sha256((ROOT / "data/concepts.json").read_bytes()).hexdigest(),
                "vocabulary_sha256": hashlib.sha256((ROOT / "experiments/final_graph/expanded_concepts_v1.json").read_bytes()).hexdigest(),
                "status": "draft_unreviewed"}
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
