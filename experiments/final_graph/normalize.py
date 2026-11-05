"""Build a provenance-preserving staging graph from the final JSONL files.

This is an identity/evidence normalization step, not a relevance model. It never
merges labs by URL or papers by title, and it does not assert a course teaches a
topic merely because a word appears in a syllabus.

Run: python3 experiments/final_graph/normalize.py --out /tmp/final-graph
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "staging-v2"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def full_digest(parts: list[object]) -> str:
    """Length-delimited IDs avoid ambiguous path/offset concatenations."""
    payload = "".join(f"{len(str(part))}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clean(value):
    return value.strip() or None if isinstance(value, str) else value


def rows(name: str):
    path = ROOT / name
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                yield number, json.loads(line), source_hash


def provenance(name: str, number: int, source_hash: str, field: str) -> dict:
    return {
        "source_file": name,
        "source_sha256": source_hash,
        "source_row": number,
        "source_field": field,
        "schema_version": VERSION,
    }


def evidence(evidence_id: str, owner_kind: str, owner_id: str, text: str, field: str, source: dict, **extra) -> dict:
    return {
        "evidence_id": evidence_id,
        "owner_kind": owner_kind,
        "owner_id": owner_id,
        "text": text,
        "field": field,
        "source": source,
        "review_status": "unreviewed",
        **extra,
    }


def paper_identity(paper: dict, source: dict, index: int) -> tuple[str, str]:
    doi = clean(paper.get("doi"))
    openalex = clean(paper.get("openalex_id"))
    if doi:
        return "doi:" + doi.lower().removeprefix("https://doi.org/"), "doi"
    if openalex:
        return "openalex:" + openalex.rsplit("/", 1)[-1], "openalex"
    # Similar-looking titles are only review candidates. No automatic merge.
    return "unresolved:" + digest(f"{source['source_sha256']}:{source['source_row']}:{source['source_field']}:{index}"), "source_occurrence"


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    entities: dict[str, list[dict]] = {key: [] for key in (
        "courses", "offerings", "labs", "advisors", "memberships", "papers", "paper_lab_evidence", "evidence"
    )}
    papers_by_id: dict[str, dict] = {}
    evidence_ids: set[str] = set()
    for row_no, row, source_hash in rows("final_courses.jsonl"):
        code = row["course_code"].strip().upper()
        course_id = "course:" + code
        offering_id = "offering:" + digest(f"{source_hash}:{row_no}")
        src = provenance("final_courses.jsonl", row_no, source_hash, "$row")
        entities["courses"].append({
            "course_id": course_id, "canonical_code": code, "title": clean(row["course_title"]),
            "identity_status": "source_code_unique", "code_aliases": [], "crosslist_group_id": None,
            "source": src,
        })
        entities["offerings"].append({
            "offering_id": offering_id, "course_id": course_id, "semester": clean(row["_semester"]),
            "professor_name": clean(row["professor"]), "department": clean(row["_dept"]),
            "credit_original": clean(row["credit"]), "category": clean(row["category"]), "source": src,
        })
        for field in ("description", "Lesson Objectives", "Lecture progress plan", "prerequisites", "references"):
            value = row[field]
            if not value.strip():
                continue
            # Keep the exact source text: paragraph offsets are positions in this field.
            for match in re.finditer(r"\S[^\r\n]*(?:\r?\n(?!\s*\r?\n)[^\r\n]+)*", value):
                snippet = match.group(0).strip()
                if not snippet:
                    continue
                end = match.start() + len(snippet)
                eid = "evidence:" + full_digest([source_hash, row_no, field, match.start(), end])
                if eid in evidence_ids:
                    raise ValueError(f"duplicate evidence ID: {eid}")
                evidence_ids.add(eid)
                entities["evidence"].append(evidence(
                    eid, "offering", offering_id, snippet, field,
                    provenance("final_courses.jsonl", row_no, source_hash, field),
                    span=[match.start(), end],
                    evidence_role="teaching_candidate" if field in ("description", "Lesson Objectives", "Lecture progress plan") else "context_only",
                ))

    for row_no, row, source_hash in rows("final_labs.jsonl"):
        advisor_id = "advisor:" + row["advisor_id"]
        # One provisional lab per advisor. The three repeated lab_group values
        # remain merge-review candidates rather than automatic shared labs.
        lab_id = "lab:" + row["advisor_id"]
        src = provenance("final_labs.jsonl", row_no, source_hash, "$row")
        person = row["professor"] or {}
        entities["advisors"].append({
            "advisor_id": advisor_id, "name": clean(person.get("name")),
            "department": clean(person.get("department")), "researcher_id": clean(person.get("researcher_id")),
            "identity_status": "source_advisor_id", "source": src,
        })
        entities["labs"].append({
            "lab_id": lab_id, "name": clean(row["lab_name"]) or clean(row["display_name"]),
            "canonical_url": clean(row["lab_url"]), "lab_group_candidate": clean(row["lab_group"]),
            "grouping_status": "unreviewed", "departments": row["departments"], "source": src,
        })
        entities["memberships"].append({
            "lab_id": lab_id, "advisor_id": advisor_id, "role": "source_advisor",
            "review_status": "unreviewed", "source": src,
        })
        intro = row["research_intro"]
        if intro and intro.strip():
            for match in re.finditer(r"\S[^\r\n]*(?:\r?\n(?!\s*\r?\n)[^\r\n]+)*", intro):
                snippet = match.group(0).strip()
                if not snippet:
                    continue
                end = match.start() + len(snippet)
                eid = "evidence:" + full_digest([source_hash, row_no, "research_intro", match.start(), end])
                if eid in evidence_ids:
                    raise ValueError(f"duplicate evidence ID: {eid}")
                evidence_ids.add(eid)
                entities["evidence"].append(evidence(
                    eid, "lab", lab_id, snippet, "research_intro",
                    provenance("final_labs.jsonl", row_no, source_hash, "research_intro"),
                    span=[match.start(), end], evidence_role="research_candidate",
                ))
        for field in ("site_papers", "professor_papers", "representative_papers"):
            for index, paper in enumerate(row[field]):
                paper_src = provenance("final_labs.jsonl", row_no, source_hash, f"{field}[{index}]")
                paper_id, identity_basis = paper_identity(paper, paper_src, index)
                title = clean(paper.get("title"))
                if not title:
                    continue
                if paper_id not in papers_by_id:
                    papers_by_id[paper_id] = {
                        "paper_id": paper_id, "title": title, "year": paper.get("year"),
                        "doi": clean(paper.get("doi")), "openalex_id": clean(paper.get("openalex_id")),
                        "abstract": clean(paper.get("abstract")), "venue": clean(paper.get("venue")),
                        "identity_basis": identity_basis, "source": paper_src,
                    }
                claim_id = "claim:" + full_digest([source_hash, row_no, field, index])
                entities["paper_lab_evidence"].append({
                    "claim_id": claim_id, "source_index": index,
                    "paper_id": paper_id, "lab_id": lab_id, "advisor_id": advisor_id,
                    "source_list": field, "source": paper_src,
                    "verification_status": "unreviewed", "evidence_level": "abstract" if clean(paper.get("abstract")) else "title_only",
                })
                for part in ("title", "abstract"):
                    original = paper.get(part) or ""
                    text = original.strip()
                    if not text:
                        continue
                    path = f"{field}[{index}].{part}"
                    start = original.index(text)
                    end = start + len(text)
                    eid = "evidence:" + full_digest([source_hash, row_no, path, start, end])
                    if eid in evidence_ids:
                        raise ValueError(f"duplicate evidence ID: {eid}")
                    evidence_ids.add(eid)
                    entities["evidence"].append(evidence(
                        eid, "paper_listing", claim_id, text, path,
                        provenance("final_labs.jsonl", row_no, source_hash, path),
                        span=[start, end], evidence_role="research_candidate",
                    ))
    entities["papers"] = list(papers_by_id.values())
    for name, records in entities.items():
        write_jsonl(out / f"{name}.jsonl", records)
    manifest = {
        "schema_version": VERSION,
        "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("final_courses.jsonl", "final_labs.jsonl")},
        "counts": {name: len(records) for name, records in entities.items()},
        "paper_identity_basis": dict(Counter(paper["identity_basis"] for paper in entities["papers"])),
        "limits": ["labs are provisional advisor-level records", "title-based paper duplicates are not merged", "no semantic graph assertions generated", "value_state and typed concept assertions are not yet emitted"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().out), ensure_ascii=False, indent=2))
