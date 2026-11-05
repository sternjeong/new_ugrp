"""Count field availability and possible scrape-noise markers; no model inference."""

import hashlib
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "experiments/final_graph/results/embedding_field_ablation_v1"
LAB_FIELDS = ("research_intro", "admission", "lab_mates", "centers", "keywords", "representative_papers")
COURSE_FIELDS = ("description", "Lecture progress plan", "grading", "course_operation", "other_info",
                 "prerequisites", "textbooks", "references")
MARKERS = {"office_location": r"\b(?:office|room)\b|연구실\s*위치|사무실",
           "people": r"\b(?:members|students|people)\b|대학원생|구성원",
           "news": r"\bnews\b|소식|공지사항",
           "contact": r"\bemail\b|@|연락처|문의"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main():
    out = DIR / "field_presence_audit.json"
    if out.exists():
        raise RuntimeError("audit already frozen")
    frame_path = DIR / "frame.json"
    courses_path = ROOT / "final_courses.jsonl"
    labs_path = ROOT / "final_labs.jsonl"
    frame = json.loads(frame_path.read_text(encoding="utf-8"))
    lab_ids = {lab for items in frame["buckets"].values() for item in items for lab in item["lab_ids"]}
    labs = [r for r in rows(labs_path) if "lab:" + r["advisor_id"] in lab_ids]
    courses = rows(courses_path)
    assert len(labs) == 180 and len(courses) == 1316
    lengths = sorted(len(r.get("research_intro") or "") for r in labs)
    report = {
        "meaning": "regex marker prevalence, not verified irrelevant-content fraction or embedding effect",
        "source_sha256": {"frame": sha(frame_path), "courses": sha(courses_path), "labs": sha(labs_path),
                          "script": sha(Path(__file__))},
        "rows": {"labs": len(labs), "courses": len(courses)},
        "nonempty_fields": {"labs": {f: sum(bool(r.get(f)) for r in labs) for f in LAB_FIELDS},
                            "courses": {f: sum(bool(r.get(f)) for r in courses) for f in COURSE_FIELDS}},
        "research_intro_chars": {"median": statistics.median(lengths),
                                 "p95": lengths[int(.95 * (len(lengths) - 1))]},
        "research_intro_marker_rows": {name: sum(bool(re.search(pattern, r.get("research_intro") or "", re.I))
                                                  for r in labs) for name, pattern in MARKERS.items()},
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
