"""Find exact-content course identity candidates without merging course codes."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("course_title", "description", "Lesson Objectives", "Lecture progress plan")
GENERIC = re.compile(r"논문연구|연구참여|과제연구|세미나|seminar|thesis research|independent research", re.IGNORECASE)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip().casefold()


def main() -> None:
    path = ROOT / "final_courses.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    groups = collections.defaultdict(list)
    for number, row in enumerate(rows, 1):
        key = tuple(normalized(row[field]) for field in FIELDS)
        groups[key].append({"course_code": row["course_code"], "title": row["course_title"],
                            "department": row["_dept"], "semester": row["_semester"], "source_row": number})
    repeated = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        family_id = "content:" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:20]
        repeated.append({"content_group_candidate": family_id,
                         "reason": "title_only_empty_teaching_text" if not any(key[1:]) else
                                   "generic_research_or_seminar" if GENERIC.search(members[0]["title"]) else
                                   "identical_title_and_teaching_text",
                         "members": members, "review_status": "unreviewed"})
    repeated.sort(key=lambda item: (-len(item["members"]), item["content_group_candidate"]))
    result = {"source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "course_rows": len(rows), "unique_codes": len({row["course_code"] for row in rows}),
              "repeated_content_groups": len(repeated),
              "rows_in_repeated_groups": sum(len(item["members"]) for item in repeated),
              "generic_groups": sum(item["reason"] == "generic_research_or_seminar" for item in repeated),
              "title_only_groups": sum(item["reason"] == "title_only_empty_teaching_text" for item in repeated),
              "groups": repeated}
    out = ROOT / "experiments/final_graph/results/course_identity_candidates.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "groups"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
