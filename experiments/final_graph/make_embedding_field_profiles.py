"""Build field-controlled text inputs for the Kaggle-only embedding ablation."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments/final_graph/results"
OUT = RESULTS / "embedding_field_ablation_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def norm(value):
    text = str(value or "")
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", text)
    text = re.sub(r"\b0\d{1,2}[- ]\d{3,4}[- ]\d{4}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def plain(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "; ".join(norm(v) for v in value if norm(v))
    return norm(value)


def fields(row, paths):
    values = []
    for path in paths:
        value = row
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        rendered = plain(value)
        if rendered:
            values.append(f"{path}: {rendered}")
    text = " | ".join(values)[:1000]
    return [text] if text else []


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "profiles.json"
    if target.exists():
        raise RuntimeError(f"frozen profile already exists: {target}")
    sources = {name: ROOT / name for name in ("final_courses.jsonl", "final_labs.jsonl")}
    subset = json.loads((RESULTS / "complete_subset_v1.json").read_text(encoding="utf-8"))
    packet = json.loads((RESULTS / "holdout_relevance_v1/packet.json").read_text(encoding="utf-8"))
    split = json.loads((RESULTS / "rich_split_v1.json").read_text(encoding="utf-8"))
    assert {name: sha(path) for name, path in sources.items()} == subset["source_hashes"]
    selected_labs = {"lab:" + aid for item in split["assignments"] if item["split"] == "holdout"
                     for aid in item["advisor_ids"]}
    assert set(packet["labs"]) < selected_labs
    course_rows = set(subset["eligible_course_source_rows"])
    out = {"schema_version": "embedding_field_ablation_v1", "labs": [], "courses": []}
    for index, row in enumerate(rows(sources["final_courses.jsonl"]), 1):
        if index not in course_rows:
            continue
        title = norm(row["course_title"])
        core = []
        for label, key in (("설명", "description"), ("진도", "Lecture progress plan")):
            body = norm(row.get(key))[:1000]
            if body:
                core.append(f"과목: {title} | {label}: {body}")
        if not core:
            raise ValueError(f"no course core: {row['course_code']}")
        admin = fields(row, ("credit", "category", "_dept", "_semester", "grading"))
        learning = fields(row, ("prerequisites", "textbooks", "references"))
        out["courses"].append({"id": "course:" + row["course_code"].strip().upper(),
                               "core": core, "admin": admin, "learning_context": learning})
    for row in rows(sources["final_labs.jsonl"]):
        lab_id = "lab:" + row["advisor_id"]
        if lab_id not in selected_labs:
            continue
        core = []
        keywords = plain(row.get("keywords"))
        if keywords:
            core.append("키워드: " + keywords)
        for paper in (row.get("representative_papers") or [])[:5]:
            title, abstract = norm(paper.get("title")), norm(paper.get("abstract"))[:400]
            if title and abstract:
                core.append(f"논문: {title} | {abstract}")
        if not core:
            raise ValueError(f"no lab core: {lab_id}")
        admin = fields(row, ("professor.position", "professor.department", "departments",
                             "centers", "has_lab_site"))
        out["labs"].append({"id": lab_id, "core": core, "admin": admin})
    assert len(out["courses"]) == 941 and len(out["labs"]) == 180
    assert len({x["id"] for x in out["courses"]}) == 941
    assert len({x["id"] for x in out["labs"]}) == 180
    target.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    report = {"source_sha256": {name: sha(path) for name, path in sources.items()},
              "subset_sha256": sha(RESULTS / "complete_subset_v1.json"),
              "packet_sha256": sha(RESULTS / "holdout_relevance_v1/packet.json"),
              "split_sha256": sha(RESULTS / "rich_split_v1.json"),
              "builder_sha256": sha(Path(__file__)), "profiles_sha256": sha(target),
              "counts": {"courses": len(out["courses"]), "labs": len(out["labs"])},
              "chunk_counts": {kind: {field: sum(len(x[field]) for x in out[kind])
                                      for field in (("core", "admin") if kind == "labs" else
                                                    ("core", "admin", "learning_context"))}
                               for kind in ("labs", "courses")}}
    (OUT / "profiles_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
