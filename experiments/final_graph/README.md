# Final JSONL experiments

Inputs are the repository root `final_courses.jsonl` and `final_labs.jsonl`. Neither file is edited by these scripts. The output folders under `results/` are versioned and refuse to overwrite frozen packets or analyses. See `REPRODUCTION_MATRIX.md` for the comparison scope and `docs/analysis/FINAL_DATASET_SCHEMA_V2_DECISION.md` for the proposed evidence contract.

The final two-judge verdict summary is `JUDGE_REVIEWS_2026-10-15.md`. The two-page meeting PDF is `reports/final_dataset_meeting_2026-10-15.pdf` with its source Markdown and SHA-256 manifest beside it. The schema is an accepted target architecture; `concept_sense`, relation assertions, and the service output contract are not yet implemented in the app.

## Reproduction map

| Stage | Code | Result |
|---|---|---|
| Source graph | `normalize.py --out <directory>` then `validate_staging.py --out <directory>` | staging v2 provenance; summary in `results/staging_v2_validation.json` |
| Rich frame | `audit_complete_subset.py`, `make_rich_split.py` | `complete_subset_v1.json`, `rich_split_v1.json` |
| Relation rule | `relation_engine.py`, `make_holdout_relevance_packet.py`, `analyze_holdout_relevance.py` | frozen v15 rankings and two judge scores |
| Kaggle BGE | `make_bge_rich_kaggle_notebook.py`, submit `bge_rich_kaggle.ipynb` with Kaggle GPU, then `import_bge_rich_kaggle.py` | `bge_rich_v1/rankings.json` |
| BGE top one/five | `make_bge_top1_packet.py`, `analyze_bge_top1.py`; `make_bge_top5_extension_packet.py`, `analyze_bge_top5_extension.py` | method-blind new pair labels plus reused identical-pair labels |
| Query challenge | `make_query_targets.py`, `freeze_query_parser_diagnostic.py`, `run_query_rich.py`, `make_query_rich_packet.py`, `analyze_query_rich.py` | v3 authored 60-query frame; CPU sparse TF-IDF only |
| Reasons and presentation | `make_reason_rich_packet.py`, `analyze_reason_rich.py`; `make_ab_rich_packet.py`, `analyze_ab_rich.py` | conditional 27-pair reason and presentation pilots |
| Feedback stress | `make_feedback_rich_packet.py`, `analyze_feedback_rich.py` | v3 random-position removal/rank-six exposure |

Two Luna judges scored each versioned packet separately before its method key/ranking was opened for analysis. Query judges had seen its target file during design review; reason and A/B judges had prior exposure to the same pair/sentence content. Their scores are stored separately. Design and result verdicts are recorded in the dated analysis documents. Earlier discarded packet versions are retained to make pre-label corrections visible.

**GPU-specific BGE encoding is Kaggle GPU only.** The local `run_bge_rich.py` rejects CPU execution; the incomplete earlier CPU attempt produced no ranking used in any analysis. Sparse TF-IDF and JSON/statistical analyses run on CPU because they are not GPU-specialized operations.

The rich-frame n is for a single binary proportion with finite-population correction in the held-out component frame. It is not a power guarantee for paired ranking effects. Source windows, source hashes, label files, and scripts are recorded in each result manifest; post hoc extensions are labeled as such.

> 2026-11-08 정리: 다른 파일이 참조하지 않고 이후 버전으로 대체된 중간 결과(`results/dev_relations_v2·v3·v7·v8·v14`, 폐기된 `feedback_rich_v2`, `dev_duplicate_audit_v3·v7·v8`)를 작업 폴더에서 뺐다. 최종 `dev_relations_v15`와 보고서가 인용하는 결과는 그대로다. 지운 결과는 `git show 9444cff:experiments/final_graph/results/<경로>`로 꺼낼 수 있다.
