# Assess job match before resume generation

Use after discovery and before experience selection or resume generation. The main agent delegates judgments to dedicated scoring sub-agents using [scoring-workers.md](scoring-workers.md), then validates and publishes results. The screening sub-agent independently checks that assessment. Show the result to the user before spending work on a tailored resume.

## Hard constraints and information quality first

Record each applicable user-stated hard constraint as `met`, `violated`, or `unknown`, with its reason and source. Explicit US-only employment excludes an employment arrangement in another country. A preferred city is not a ban on other cities when the user's relocation conditions permit them. Do not import the old JobBot prompt's fixed US/Canada restriction or its job-title/year rules.

Missing information is not a proven violation. Job freshness, current open status, and published deadlines remain separate from skills fit. Expired or incomplete source information makes the assessment provisional until resolved. Do not manufacture a zero score when a source/tool or evaluation fails.

Use [level calibration](level-calibration.md) to interpret the JD's scope and independence expectations before scoring responsibilities or experience level. Explain the supporting source in the existing dimension reasons. SDE1/SDE2 labels alone do not establish comparable levels across employers. Keep material scope gaps prominent even if other dimensions raise the average; explicit lack of ownership is different from missing details about ownership.

## Transparent job-match rubric

Use the following starting rubric, adapted from the old JobBot scoring prompt. It is a product heuristic, not a probability of an interview or a certification of the candidate. Keep the rubric and weights with the local assessment so comparisons are interpretable. Users may choose different weights.

| Dimension ID | Initial weight | Evaluate from stored evidence |
| --- | --- | --- |
| `role_alignment` | 0.30 | Actual responsibilities and transferable work, not title-string similarity alone |
| `skills` | 0.25 | Relevant demonstrated capabilities and technologies across the archive |
| `location` | 0.20 | Country/city/work-mode preferences and conditional relocation, after hard constraints |
| `industry` | 0.15 | User-stated industry interests and transferable context; not applicable when no such preference exists |
| `experience_level` | 0.10 | The posting's actual scope/requirements against work, research, courses, and projects; no universal title/year threshold |

The agent assigns each dimension a 0–1 value and reason using the same scale: 0 means no supporting alignment in the available evidence, 0.5 partial or transferable alignment, and 1 strong direct alignment. Intermediate values need a concrete explanation. Do not infer inability merely from an old resume's missing keyword. Read the broader archive before declaring a gap.

Use `unknown` when facts are missing and `not_applicable` when the dimension genuinely does not apply; do not turn either into zero. Compute the weighted average over scored dimensions only, then multiply by 100. Report coverage as the scored weight divided by scored-plus-unknown weight; not-applicable weights are excluded. An incomplete assessment must visibly remain provisional even if its partial weighted score is high. No scored dimensions means insufficient information and a null score/tier.

Use A at 80+, B at 65+, C at 50+, D below 50, preserving the old JobBot tier cutoffs on a 0–100 display scale. A proven hard-constraint violation has a separate `ineligible` outcome and null overall score/tier; a high soft match must not conceal that exclusion. Unknown hard constraints stay unresolved.

## Local record and division of work

Store `jobs/<job-id>/match.json`, bound to current profile, preference, JD, and job-status hashes. Keep the rubric, dimension values/statuses, source references, hard-constraint outcomes, strengths, gaps, unresolved questions, total/tier, coverage, and evaluation time. The source expiry does not refresh when scoring.

The scoring sub-agent supplies semantic judgments. `scripts/job_match.py --prepare` prepares the local record; running it without that flag validates its structure, input bindings, evidence IDs, and computes the total/tier and uncertainty state. Use `--verify` when checking an already published/reviewed assessment: it checks current bindings and derived values without writing files, or fails if recalculation is needed. Default recalculation also preserves exact bytes and `scored_at` when the saved derived result is unchanged. Real recalculation or publication retains the prior record in history and changes its bindings for downstream review; tool checks must not refresh timestamps just for being read. It does not call an external model, prove semantic correctness, or verify that the user saw the result. The host's primary agent schedules isolated scoring workers within configured concurrency/model/attempt policy; a different agent reviews their work. No worker edits the shared canonical assessment.

```bash
python3 "$SKILL_DIR/scripts/job_match.py" --workspace "$WORKSPACE" --job "$JOB_ID" --prepare
# Scoring worker fills its isolated copy at JUDGMENTS_PATH.
python3 "$SKILL_DIR/scripts/job_match.py" --workspace "$WORKSPACE" --job "$JOB_ID" \
  --import-judgments "$JUDGMENTS_PATH"
```

The screening reviewer checks source support, weight handling, uncertainty, total/tier consistency, and constraint decisions, independently of the scoring worker. Reviewer approval is about the assessment, not approval or rejection of the person. Keep the passed report linked to the current assessment version.

## Tell the user before drafting

Present the reviewed overall score/tier, whether it is provisional, the strongest matches, major gaps, and any hard-constraint/source-status issue. A short example format is “Match: 72/100, B; provisional because location details remain unknown. Strong API/project evidence; limited evidence for the stated production scope.” This example is illustrative, not an assessment of the actual user.

Give the user a practical recommendation about investing in a draft. A low score alone does not prohibit one. If the user already asked for a resume for that job, show the assessment and continue within that authorization unless an unresolved decision truly needs their input. Do not add a mandatory confirmation click for every score. An explicit hard-constraint conflict must not be silently waived; distinguish a requested historical/stretch draft from a recommendation to pursue an excluded job. Never auto-submit an application.
