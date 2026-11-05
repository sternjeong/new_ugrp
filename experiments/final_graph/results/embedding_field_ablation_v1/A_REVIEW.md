# Independent A review: embedding field ablation

## Verdict

**Accept for the preregistered, narrow descriptive comparison, with one required reporting correction.** The new ratings, frozen exposure mapping, primary utility, component pairing, and A-side bootstrap calculations are internally consistent. The registered core-versus-both-admin threshold is met for A. The report must also publish the preregistered exact-duplicate-slot measure, currently absent from `analysis.json`; the counts below were independently computed from the frozen packet and exposure key.

This does not establish that metadata removal improves recommendations across all eligible labs or for students. It is a comparison on the 18 predeclared unused components and their 28 professor rows, judged from the shared core-text window.

## Integrity and calculation checks

- SHA-256 values for `packet.json`, `method_key.json`, `rankings.json`, and `frame.json` match the frozen packet manifest. The ranking SHA also matches `rankings_manifest.json`.
- The 327 A ratings cover every packet pair exactly once and in packet order. All values are valid; A marked no pair insufficient. Counts are 59 relevance-0, 122 relevance-1, and 146 relevance-2.
- Each of the five variants has 140 exposures (28 rows × 5). I compared every exposure's course and rank against the corresponding frozen ranking: all 700 entries match. The 327-pair packet is the union of these exposures.
- I independently recomputed A's equal-component-weighted utilities from the ratings and exposure key. They exactly match `analysis.json`: core 0.7778; lab-admin 0.6410; course-admin 0.7722; both-admin 0.5660; learning-context 0.7673.
- For the primary paired contrast, the component differences average **+0.2117** (`core − both_admin`) across 18 components. Re-running the declared 5,000-replicate percentile bootstrap with seed 20261017 gives **95% CI [0.1167, 0.3083]**, exactly matching `analysis.json`. A therefore exceeds the preregistered +0.02 lower-bound threshold.
- A's ratings are not fully consistent across identical inputs: I independently found **6 groups** with the same lab ID and identical course-core tuple but different relevance scores. The post hoc sensitivity script harmonizes each such group to either its minimum or maximum A score, enumerates all **64** combinations, and recomputes the primary contrast and component bootstrap. I independently reproduced its range: effect **+0.2028 to +0.2207**, with the lowest 95% interval lower bound **+0.1139**. The registered +0.02 cutoff remains met in every scenario. This checks robustness to one explicit label-consistency correction; it does not determine the correct label. The accompanying audit reports two conflicting identical-text groups for B; I did not independently inspect B's ratings.
- The bootstrap first averages professor rows within a component, then resamples components, as specified. The confirm set has 15 singleton components, two with two rows, and one with nine rows (28 rows total). The large component is correctly one resampling unit under the declared rule, but the effective sample remains only 18 components.
- The shuffled-admin artifact has the SHA recorded in its manifest and contains 180 unique lab rows with top-five rankings. It is explicitly marked `structural_sensitivity_unjudged`; I treated it as a structural-only diagnostic and did not attach or infer quality labels. Across all 180 rows, its top-five overlap averaged 1.07 courses with core and 0.86 with both-admin (out of five). This describes rank sensitivity to shuffled metadata, not recommendation quality or a causal estimate.

`analysis.json` reports that both judges pass the threshold. I did not inspect B's raw ratings, per the review instruction; the bilateral threshold is therefore accepted as the analysis artifact's reported result, while this independent arithmetic check covers A only.

## Preregistered reporting correction

The preregistration names exact repeated course-title-and-education-body slots within a lab's top five as a secondary measure. `analysis.json` does not calculate or report it. Using identical two-chunk course-core strings as the exact title/body match, and counting each occurrence beyond the first within one lab's top five, I obtain:

| Variant | Duplicate slots | Lab rows with a duplicate |
|---|---:|---:|
| core | 14 | 12/28 |
| lab_admin | 17 | 12/28 |
| course_admin | 14 | 12/28 |
| both_admin | 8 | 5/28 |
| learning_context | 16 | 13/28 |

“Lab rows with a duplicate” counts a row once when its five course-core tuples have fewer unique values than entries. Earlier I mistakenly counted duplicated signature groups, which overcounted rows when one row had more than one duplicated group; the corrected counts above match that row-level definition. These are structural counts, not relevance corrections. Keep same-content course codes as separate slots in the already-registered utility, but state that this utility can count repeated identical educational text more than once. The reported duplicate measure helps readers see that effect.

The six A disagreement groups show a separate label-quality limitation: identical lab/course text sometimes received different judgments. Preserve the raw ratings and disclose this. The enumerated min/max harmonization is only a post hoc sensitivity check, not a replacement label set or an extension of the preregistered primary analysis.

## Limits on the conclusion

- The 18 components are the frozen, previously unused remainder, not a newly randomized sample from all 137 holdout components or all 180 eligible lab rows. The intervals describe component variation in this small confirm set; they should not be read as broad population guarantees. The +0.02 cutoff is a preregistered decision rule, not a causal estimate.
- The largest component contains nine professor rows. Component weighting prevents that cluster from dominating, but row-weighted results would answer a different question and should not be substituted post hoc.
- All methods were judged using the same core-text window. This supports a claim about recommendations judged from research and course core text; it does not test whether metadata contains useful research information that was hidden from raters.
- The paired top-five utility is a ranking-quality measure for this candidate universe. It does not measure course enrollment choices, student outcomes, lab fit in practice, or recall of all relevant courses.
- The input variants add chunks and therefore change the number of opportunities for a maximum-cosine match. The preregistered shuffle analysis is a useful mechanism check, but cannot by itself separate content effects from every chunk-count effect.
- The shuffled-admin rankings have no blind relevance packet. Do not use their overlap or rank position as a quality result.
- The 5000 bootstrap repetitions make the resampling computation stable; they do not compensate for only 18 components or nonrandom selection. Present the intervals as the declared component-bootstrap intervals.

## Suggested wording

“On the 18 previously unused shared-evidence components (28 professor rows), and using only the common core-text window for relevance judgments, core-only ranking had higher fixed top-five utility than core plus both administrative-field groups for both judges. For A, the component-paired difference was 0.212 (18 components; 5,000-replicate percentile component-bootstrap 95% interval 0.117 to 0.308); the analysis reports the same threshold criterion passed by B. This is a limited result on the frozen subset and does not establish service-wide or student-level benefit.”

## Specific-noise support audit

I independently recalculated `specific_noise_support_audit.json`; its source hashes and all counts match. In the 28 confirm rows, regexes found one office/room marker, two possible numeric people-count markers, and no nonempty `lab_mates` fields. These are unadjudicated marker counts, not confirmed semantic mentions. Since the embedding variants excluded `lab_mates` and the `research_intro` excerpts containing those markers, and the confirm frame has very few possible office/count signals, this experiment cannot estimate the separate embedding effect of office locations, student counts, or lab-member lists. That is a limitation of feature coverage, not a negative performance finding. The artifact is correctly labeled as a post hoc support audit, not a performance test.
