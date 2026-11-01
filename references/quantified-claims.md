# Competitive wording and user-confirmed quantitative claims

Use after selecting relevant experiences and retrieving their stored details. The agent can strengthen wording and propose ways to quantify actual work. Keep measurements, calculations, personal estimates, and hypothetical scenarios distinct. User confirmation establishes the user's account; it is not a demand for an independent certificate or a formal benchmark.

## What can be strengthened

Use clearer verbs, more specific technical descriptions, and the most useful scope already supported by the archive. Summarize several real actions into a concise contribution without adding ownership or achievements. Coursework, prototypes, research, and personal tools can all have useful impact.

A hypothetical quantitative scenario may help explain what could be measured, but label it as hypothetical in the local drafting notes. It is not a fact about the candidate and must not be inserted into the confirmed profile or submitted resume merely because it would sound competitive.

| Kind | Basis | Use in final wording |
| --- | --- | --- |
| Measured | Existing logs, benchmarks, records, or the user's account of a measurement | Preserve what was measured and its scope |
| Calculated | Supported before/after values, counts, or durations | Preserve the formula, units, and assumptions in notes |
| User estimate | User's own reasonable recollection/estimate of their work | Use approximate language and suitable precision |
| Hypothetical proposal | An explicit scenario or unconfirmed drafting idea | Keep pending in notes until actual values/basis are supplied or endorsed as the user's genuine estimate |

The user may reasonably estimate an effect without formal tracking. Do not discount such an estimate just because there is no external measurement. However, agreement that a sentence “sounds good” is not confirmation that an invented number reflects the user's experience. Ask about the meaning and basis when needed, rather than silently relabeling an arbitrary figure as measured impact. If the user cannot support a numerical estimate, use the real tool, workflow change, or deliverable without a number.

## Retrieve first, then calculate or confirm

Read the selected experience's existing details and source notes before asking anything. If the archive already contains before/after times or a confirmed estimate, reuse it. Do not repeat a general interview or demand a percentage for every bullet.

If quantification is important to the intended wording but its basis is missing, ask one focused question about what the user actually observed: task duration, frequency, number of manual steps, records processed, users/teammates, or other relevant scope. Let them say “not tracked” or give an approximate range. Do not lead them to a desired percentage chosen for appearance.

When presenting a proposed quantified sentence, explain:

- what improved, for which task/population, and the user's personal contribution;
- baseline and changed value, units, and timeframe where applicable;
- whether it was measured, calculated, estimated, or still hypothetical;
- assumptions and the exact wording the user is being asked to confirm.

Confirm a coherent sentence/claim, not a bare number. A direct user answer or correction can establish the estimate; save its basis and approximate nature with the fact. Do not ask for repetitive confirmations of unchanged material. If the user declines or cannot estimate, continue with supported non-numeric wording rather than blocking the whole resume.

## Calculate the right quantity

For task-time reduction, use `(before - after) / before * 100`. For throughput increase, use `(after - before) / before * 100` with consistent units and task scope and a positive baseline. When the baseline is zero, report the absolute change rather than an undefined percentage. A 50% time reduction is not a 50% throughput increase. Avoid a vague “efficiency” label when the evidence describes a specific time or step reduction. Do not turn local task savings into organization-wide productivity or revenue.

Illustrative scenarios, not candidate facts:

- A task taking about 45 minutes before and 30 afterward supports roughly one-third less task time; it does not establish an exact business-wide gain.
- A task taking 20 minutes before and 10 afterward yields 50% time reduction. Keep 50%; do not change it to 47% merely to look less rounded.

Choose precision to match the basis. Use “about,” a range, or a simple magnitude for approximate recollection. A non-round percentage such as 37% is appropriate when supported, but is not inherently more credible than 30% or 50%. Never pick or perturb a figure to avoid a multiple of ten, or add decimals suggesting a measurement that did not happen. Exact source-supported round figures remain valid. Saved hours, removed manual steps, or delivered functionality may be a better expression than a percentage.

## Local notes, profile updates, and review

Keep optional `jobs/<job-id>/quantification.json` drafting notes identifying the experience, proposed wording, claim kind, source/baseline, units/scope, assumptions, unresolved points, and the user's actual confirmation/correction. This file is agent-maintained, not a CLI-validated candidate-fact store. Hypotheses stay outside canonical profile facts and final resume claims.

Once confirmed with a genuine factual/estimate basis, save reusable facts in the profile with source IDs and retain the basis in source/confirmation notes. If that changes profile hashes, refresh affected assessments/reviews before preparing a new resume plan. The original claim kind and uncertainty must survive rephrasing; approximate estimates must not become measured/exact claims later.

Give the hiring-perspective reviewer the proposed/final wording, relevant stored facts, calculations and user confirmation context. It should preserve strong expression, check the quantitative meaning and precision, and reject unresolved hypotheses presented as actual results. It should not demand external proof for the user's reasonable estimate or force every contribution to have a metric. The current CLI checks structure/references/hashes, not whether a metric is true or its confirmation meaningful; that remains agent/reviewer work.
