"""Validate staging output against the current final source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from normalize import full_digest, paper_identity, provenance

ROOT = Path(__file__).resolve().parents[2]


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate(out: Path) -> dict:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    source_rows = {}
    for name, expected_hash in manifest["sources"].items():
        path = ROOT / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash, name
        source_rows[name] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    data = {name: records(out / f"{name}.jsonl") for name in manifest["counts"]}
    assert {name: len(rows) for name, rows in data.items()} == manifest["counts"]
    for name, items in data.items():
        for item in items:
            source = item["source"]
            assert source["source_file"] in manifest["sources"], name
            assert source["source_sha256"] == manifest["sources"][source["source_file"]], name
            assert source["schema_version"] == manifest["schema_version"], name
            assert 1 <= source["source_row"] <= len(source_rows[source["source_file"]]), name
            if name in {"courses", "offerings", "labs", "advisors", "memberships"}:
                assert source["source_field"] == "$row", name
    ids = {}
    for name, key in (("courses", "course_id"), ("offerings", "offering_id"), ("labs", "lab_id"),
                      ("advisors", "advisor_id"), ("papers", "paper_id"), ("evidence", "evidence_id")):
        ids[name] = {row[key] for row in data[name]}
        assert len(ids[name]) == len(data[name]), name
    for offering in data["offerings"]:
        assert offering["course_id"] in ids["courses"]
    for membership in data["memberships"]:
        assert membership["lab_id"] in ids["labs"]
        assert membership["advisor_id"] in ids["advisors"]
    ids["paper_lab_evidence"] = {row["claim_id"] for row in data["paper_lab_evidence"]}
    assert len(ids["paper_lab_evidence"]) == len(data["paper_lab_evidence"])
    for claim in data["paper_lab_evidence"]:
        assert claim["paper_id"] in ids["papers"]
        assert claim["lab_id"] in ids["labs"]
        assert claim["advisor_id"] in ids["advisors"]
        source = claim["source"]
        assert source["source_file"] == "final_labs.jsonl"
        assert source["source_sha256"] == manifest["sources"]["final_labs.jsonl"]
        match = re.fullmatch(r"(site_papers|professor_papers|representative_papers)\[(\d+)\]", source["source_field"])
        assert match is not None
        field, index = match.group(1), int(match.group(2))
        raw = source_rows["final_labs.jsonl"][source["source_row"] - 1]
        paper = raw[field][index]
        expected_source = provenance("final_labs.jsonl", source["source_row"], source["source_sha256"], source["source_field"])
        expected_id, _ = paper_identity(paper, expected_source, index)
        assert claim["paper_id"] == expected_id
        assert claim["lab_id"] == "lab:" + raw["advisor_id"]
        assert claim["advisor_id"] == "advisor:" + raw["advisor_id"]
        assert claim["source_list"] == field
        assert claim["source_index"] == index
        assert claim["claim_id"] == "claim:" + full_digest([source["source_sha256"], source["source_row"], field, index])
        assert claim["evidence_level"] == ("abstract" if paper.get("abstract") else "title_only")
    for item in data["papers"]:
        source = item["source"]
        assert source["source_file"] == "final_labs.jsonl"
        assert source["source_sha256"] == manifest["sources"]["final_labs.jsonl"]
        match = re.fullmatch(r"(site_papers|professor_papers|representative_papers)\[(\d+)\]", source["source_field"])
        assert match is not None
        raw = source_rows["final_labs.jsonl"][source["source_row"] - 1]
        paper = raw[match.group(1)][int(match.group(2))]
        expected_id, basis = paper_identity(paper, source, int(match.group(2)))
        assert item["paper_id"] == expected_id
        assert item["identity_basis"] == basis
        assert item["title"] == paper["title"].strip()
    checked_spans = 0
    for item in data["evidence"]:
        source = item["source"]
        assert source["schema_version"] == manifest["schema_version"]
        raw = source_rows[source["source_file"]][source["source_row"] - 1]
        value = raw
        for part in source["source_field"].replace("]", "").split("."):
            if "[" in part:
                key, index = part.split("[")
                value = value[key][int(index)]
            else:
                value = value[part]
        start, end = item["span"]
        assert value[start:end] == item["text"], item["evidence_id"]
        assert item["evidence_id"] == "evidence:" + full_digest([source["source_sha256"], source["source_row"], source["source_field"], start, end])
        checked_spans += 1
        owner_table = {"lab": "labs", "offering": "offerings", "paper_listing": "paper_lab_evidence"}[item["owner_kind"]]
        assert item["owner_id"] in ids[owner_table]
    return {"valid": True, "counts": manifest["counts"], "checked_evidence_spans": checked_spans,
            "checked_paper_claims": len(data["paper_lab_evidence"]), "checked_paper_records": len(data["papers"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    print(json.dumps(validate(parser.parse_args().out), ensure_ascii=False, indent=2))
