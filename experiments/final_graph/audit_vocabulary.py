"""Measure literal coverage of the old 70-concept vocabulary on final inputs.

This is a candidate-generation audit, not a relevance or factuality score.
Only curated `keywords` are used; loose `query_keywords` are excluded.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def compile_terms(concept: dict) -> list[tuple[str, re.Pattern]]:
    patterns = []
    for term in dict.fromkeys(concept["keywords"]):
        term = term.strip()
        if len(term) < 2:
            continue
        escaped = re.escape(term)
        # English abbreviations should not fire inside other words. Korean
        # morphemes need suffix matches, so do not add word boundaries there.
        if re.fullmatch(r"[A-Za-z0-9 -]+", term):
            escaped = r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])"
        patterns.append((term.casefold(), re.compile(escaped, re.IGNORECASE)))
    return patterns


def hits(text: str, compiled: dict[str, list[tuple[str, re.Pattern]]]) -> set[str]:
    folded = text.casefold()
    return {cid for cid, patterns in compiled.items()
            if any(term in folded and pattern.search(text) for term, pattern in patterns)}


def main() -> None:
    concepts = json.loads((ROOT / "data/concepts.json").read_text(encoding="utf-8"))["concepts"]
    compiled = {c["id"]: compile_terms(c) for c in concepts}
    labs = rows(ROOT / "final_labs.jsonl")
    courses = rows(ROOT / "final_courses.jsonl")
    lab_fields = {
        "keywords": lambda row: "\n".join(row["keywords"] or []),
        "research_intro": lambda row: row["research_intro"] or "",
        "site_titles": lambda row: "\n".join(p["title"] for p in row["site_papers"]),
        "site_abstracts": lambda row: "\n".join(p["abstract"] or "" for p in row["site_papers"]),
        "professor_titles": lambda row: "\n".join(p["title"] for p in row["professor_papers"]),
        "professor_abstracts": lambda row: "\n".join(p["abstract"] or "" for p in row["professor_papers"]),
        "representative_titles": lambda row: "\n".join(p["title"] for p in row["representative_papers"]),
        "representative_abstracts": lambda row: "\n".join(p["abstract"] or "" for p in row["representative_papers"]),
    }
    course_fields = {
        "title": lambda row: row["course_title"],
        "description": lambda row: row["description"],
        "objectives": lambda row: row["Lesson Objectives"],
        "plan": lambda row: row["Lecture progress plan"],
    }

    def summarize(items: list[dict], fields: dict, primary_fields: tuple[str, ...]) -> dict:
        field_hits = {field: [hits(get(row), compiled) for row in items] for field, get in fields.items()}
        union = [set().union(*(field_hits[field][i] for field in fields)) for i in range(len(items))]
        primary_union = [set().union(*(field_hits[field][i] for field in primary_fields)) for i in range(len(items))]
        by_concept = collections.Counter(cid for matched in union for cid in matched)
        return {
            "rows": len(items),
            "primary_fields": list(primary_fields),
            "primary_rows_with_any": sum(bool(matched) for matched in primary_union),
            "rows_with_any": sum(bool(matched) for matched in union),
            "rows_without_any": sum(not matched for matched in union),
            "rows_with_method_term": sum(any(c["kind"] == "method" for c in concepts if c["id"] in matched) for matched in union),
            "rows_with_domain_term": sum(any(c["kind"] == "domain" for c in concepts if c["id"] in matched) for matched in union),
            "by_field": {field: sum(bool(matched) for matched in values) for field, values in field_hits.items()},
            "most_common_concepts": by_concept.most_common(15),
            "unmatched_ids_sample": [items[i]["course_code"] if "course_code" in items[i] else items[i]["advisor_id"]
                                      for i, matched in enumerate(union) if not matched][:30],
        }

    print(json.dumps({"sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in ("final_courses.jsonl", "final_labs.jsonl", "data/concepts.json")},
                      "vocabulary_size": len(concepts),
                      "lab": summarize(labs, lab_fields, ("keywords", "research_intro", "representative_titles", "representative_abstracts")),
                      "course": summarize(courses, course_fields, ("title", "description", "objectives", "plan"))},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
