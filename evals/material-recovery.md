# Multi-turn experience recovery evaluation

This scenario tests conversation, evidence integration and return paths, rather than supplying a fully enriched profile to a writer. It complements the text-only probes in [experience-depth.md](experience-depth.md). Keep candidate data, the private answer bank, all transcripts, generated artifacts and execution receipts outside the skill tree.

## Setup and separation

Prepare a fictional candidate's sparse but truthful materials and a separate, richer candidate-actor answer bank before the executor asks any questions. Hash and retain both. The bank contains actual implementation details, personal/team boundaries, unknown metrics and things the person did not do; it is not an answer key or a list of required resume bullets. Do not modify it to fit the executor's questions or a desired score. A parent agent may play the candidate, but cannot be the executor's independent document reviewer.

Give a fresh primary executor only the skill, candidate workspace, current task and permitted job sources. Keep the actor's bank outside its read scope. Ask it to converse with the actor using genuine host messages and stop dependent work until actual answers arrive. The actor answers only what was asked, using the fixed bank; unknown details remain unknown. Save question and reply bytes, the real message/turn route, and confirmation/correction context. Do not give the producer expected questions, expected scores or reviewer conclusions.

For continuation from a prior delivered document, copy or reuse its history, identity and existing round budget, and record an actual writer handoff. Do not delete quality-loop state to give the scenario fresh attempts. Clearly mark evaluation copies and inherited historical receipts; a copied prior audit is not a new review. Keep real user workspaces untouched.

## Observable behavior

- The executor reads the archive first, identifies specific unknowns, and asks a small batch of neutral questions. Follow-up questions must depend on actual prior replies. A one-shot prompt containing both sides does not count.
- The executor distinguishes broad intake from later focused recovery, avoids repeating answered questions, preserves an “I do not remember” answer and does not suggest favorable numbers/technologies as candidate facts.
- New source-backed facts retain previous profile versions, update only after actual replies, and trigger appropriate scoped intake/matching/screening refreshes before drafting. The archive remains broader than the final resume.
- Material readiness can send the workflow back to collection before a first/revised PDF; do not intentionally create a weak draft just to trigger a review. If a real panel returns `collect_evidence`, preserve its exact report/draft and resume through actual new source context without resetting the document budget.
- Independent content and native visual reviewers assess the final exact artifact. Report the actual outcome, including pending/limited/exhausted states; do not lower thresholds, supply desired verdicts or call additional scoring passes to obtain a particular number.

Run an independent historical-artifact content probe when assessing rubric calibration: supply only the old frozen source/plan/PDF, not prior scores or later candidate answers. Keep this isolated report distinct from the production approval and actual dialogue chronology. It cannot retroactively be described as the trigger of an earlier conversation.

Deterministic tests separately cover high-score collection gating, blocked/missing-review handling, completed-report replacement rejection, exhausted rounds, substantive-context resumption and legacy reports. Synthetic fixtures are not real model judgments or user conversations. Report which branches ran with actual agents, which only ran through scripts, and any untested refusal/no-response paths. A small fictional run is not a hiring-outcome or cross-model benchmark.
