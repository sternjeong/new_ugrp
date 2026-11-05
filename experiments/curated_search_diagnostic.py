"""Small, fixed diagnostic set for the 2026-11-05 curated search audit.

These are author-written challenge cases, not independently judged relevance labels.
Run: python3 experiments/curated_search_diagnostic.py
"""
import json
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine


CASES = [
    ("로봇은 싫고 생체 신호 분석이 좋아요", "search", "로봇"),
    ("반도체 소자보다 의료 로봇이 좋아요", "search", "반도체"),
    ("배터리 소재의 수명과 열화를 연구하고 싶어요", "search", None),
    ("양자컴퓨터 연구를 하고 싶어요", "search", None),
    ("의료 영상에서 종양을 찾고 싶어요", "search", None),
    ("컴퓨터 구조가 재밌어요", "search", None),
    ("로봇은 싫고 배터리가 좋아요", "search", "로봇"),
    ("화학은 별로고 신약 개발이 궁금해요", "search", "화학"),
    ("수강신청은 어떻게 하나요", "career", None),
    ("대학원 지원 방법을 알려줘", "career", None),
    ("교수님께 메일을 어떻게 쓰나요", "career", None),
    ("인공지능", "too_broad", None),
    ("공학", "too_broad", None),
    ("asdf", "nonsense", None),
    ("ㅋㅋㅋㅋ", "nonsense", None),
    ("기후 변화와 탄소 포집 연구", "search", None),
    ("고분자 합성 연구를 하고 싶어요", "search", None),
    ("전자회로는 싫고 뇌과학이 좋아요", "search", "전자회로"),
    ("로봇을 좋아하지 않지만 뇌 신호 분석은 좋아요", "search", "로봇"),
    ("인공지능이 싫어요", "need_likes", "인공지능"),
]


def main():
    root = Path(__file__).resolve().parents[1]
    catalog = CuratedCatalog(root / "data/sunwoo")
    engine = CuratedQueryEngine(catalog)  # deliberately tests offline fallback
    rows = []
    for query, expected_intent, negative in CASES:
        result = engine.search(query)
        negatives = result["interpretation"]["dislikes"]
        rows.append({
            "query": query,
            "expected_intent": expected_intent,
            "actual_intent": result["intent"],
            "intent_correct": result["intent"] == expected_intent,
            "negative_cue": negative,
            "negative_extracted": None if negative is None else any(negative in part for part in negatives),
            "result_count": len(result["labs"]),
            "mode": result["mode"],
            "top3": [{"lab_id": lab["id"], "professor": lab["professors"][0]}
                     for lab in result["labs"][:3]],
        })
    summary = {
        "cases": len(rows),
        "intent_correct": sum(row["intent_correct"] for row in rows),
        "negative_cases": sum(row["negative_cue"] is not None for row in rows),
        "negative_extracted": sum(row["negative_extracted"] is True for row in rows),
        "expected_nonsearch_with_results": sum(row["expected_intent"] != "search" and row["result_count"] > 0 for row in rows),
        "catalog_labs": len(catalog.profiles),
        "catalog_courses": len(catalog.courses),
    }
    print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
