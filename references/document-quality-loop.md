# Primary-agent writing and bounded document-quality improvement

Use after selecting experiences and presenting the job-match assessment. The job-match score describes fit for the opportunity; the scores here describe the quality of a particular resume version. Rewriting can improve the document without changing the person's underlying job fit. Follow [model-compatibility.md](model-compatibility.md): the same role prompts, JSON records and helper checks apply to Claude/Anthropic, OpenAI and DeepSeek. Model-specific modalities/parameters and host session tools must be checked.

Apply [level calibration](level-calibration.md) to content coverage and substance. A confirmed target-scope gap stays visible even in a well-written document; an unknown relevant detail can return to collection. Stop futile rewriting when no truthful improvement remains, preserve the numeric outcome, and explain the limited draft. The helper does not automatically interpret these semantic distinctions.

## Roles and model allocation

The user's primary agent owns document settings, wording, polishing, and all substantive rewrites. Use the user's chosen high-capability writing model when multiple models are available. Do not assume the current model is objectively the strongest, claim a model switch through a prompt, or silently inherit a cheap scorer's model setting for writing. Respect actual host model selection and the user's existing model/cost authorization.

LaTeX generation, PDF compilation, hashing, text extraction, and page rendering are deterministic script operations. They need no model or LLM API calls. If a layout/language capability is unsupported by the renderer, explain that limit and address it explicitly rather than repeatedly rewriting text to chase scores.

Independent reviewers evaluate the frozen current version, then the primary agent rewrites from their concrete feedback. Default to two review roles:

- **Content reviewer:** factual fidelity, JD coverage, competitive expression, clarity, contribution meaning, and language/document consistency.
- **Visual reviewer:** every page image with native vision, readability, layout, spacing, glyphs, clipping, and the confirmed presentation choices.

An optional **ATS/text reviewer** checks extracted-text readability, structure, chronology, and supported requirement coverage. These are internal quality scores, not a real employer ATS result, hiring probability, or qualification test. Prompts are in `quality-prompts/common.md` plus the selected role file.

## Independent one-shot sessions or sub-agents

Review does not require a persistent agent. A true isolated model session with one supplied task and one structured response is sufficient when the host supports it. Supply the current frozen material, source context, and role rubric; do not supply the writer's reasoning, desired score, or prior round scores. The writer receives the previous feedback; reviewers grade the current artifact.

For a tool-free one-shot session, the host must attach the actual relevant text and page images from packet snapshot paths. Passing local paths alone does not give a model file/vision access. The host computes/verifies the hashes and records the actual attachment/session identity. The model assesses supplied material and echoes the supplied artifact identifiers; it must not claim to have computed file hashes or read unseen images. Use a real sub-agent when reading/vision/tool access requires one. Changing the primary agent's persona is not isolation.

Each role uses a different independent session/agent from the writer and other panel members. A single response per role includes a 0–100 score, summary, and issues with severity, locator, explanation, and actionable suggestion. Visual review names every page and its supplied hash. Save responses using `schemas/quality-review.schema.json`; retain actual execution/model/usage receipts when exposed. Unknown or unavailable information stays unknown, not a made-up zero or an implied successful review.

All concurrent scorer, reviewer-agent, and independent review-session calls count toward `agents.max_concurrent`, excluding the primary writer. Respect route-specific host capacities too. Use `agent-policy --host-worker-capacity N` only with the actual capacity for the selected route; a sub-agent thread cap alone does not describe a separate session API's capacity. Extra reviews queue. Do not introduce another provider, billing account, API key, or larger spend without the user's established authorization.

## Policy and pass conditions

`workspace.json` accepts:

```json
{
  "document_quality": {
    "pass_score": 80,
    "minimum_role_score": 70,
    "max_rewrites": 2,
    "weights": {"content": 0.6, "visual": 0.4},
    "execution": "auto",
    "review_provider": null,
    "review_model": null,
    "visual_provider": null,
    "visual_model": null,
    "max_review_attempts": 2
  }
}
```

These are adjustable product defaults, not hiring-market thresholds. To add ATS review, include its positive weight and rebalance to a sum of 1, for example content 0.4, ATS 0.3, visual 0.3. Content and visual are always required. Model fields refer only to reviewers; null uses host defaults and does not promise a cheaper model. The visual model must support the required images. `auto` uses a supported isolated session or sub-agent; an explicit unavailable route stays pending rather than being silently replaced by a costlier route.

Pass only when the weighted overall score meets `pass_score`, every role meets `minimum_role_score`, every required review is completed, every page was seen, artifact hashes match, and there are no high-severity issues. A high average cannot hide a fabricated claim, broken glyph, or low visual score.

Review failure/unavailability blocks completion; it is not a low quality score and does not consume a document rewrite. Host orchestration enforces `max_review_attempts` for each role/artifact, including retries, without resetting it under new task IDs. Low scores need actionable findings before rewriting; if findings are absent, clarify review rather than generating a random new draft.

## Missing material returns to collection

The content rubric now allocates 35/100 to experience substance, alongside accuracy 20, role coverage 25, clarity 15 and expression 5. An excellent content score needs concrete evidence, not merely truthful wording. The content prompt caps a substantively underexplained central case at 69 and routes missing material to collection; these rubric judgments and subscore arithmetic are host responsibilities, not automatically measured by the CLI. Overall panel weights and existing configured thresholds stay unchanged.

A completed content report may set `next_action: collect_evidence` only with an actionable medium/high `material_gap` issue. The helper enforces this structural contract and prevents a pass regardless of numeric scores: complete reviews yield `needs_material` when rounds remain or `exhausted` at the limit, retaining `next_action: collect_evidence`. Missing/unavailable reviewers still yield `blocked`, with the collection action retained. During blocked reevaluation the completed collection-request content report is hash-locked to the recorded outcome; filling another role cannot replace or delete that judgment to obtain a pass. Normal noncollection review clarification remains supported. Legacy reports may omit the optional field; `none` and `rewrite` do not override the existing score gates.

Follow [material recovery](material-recovery.md): distinguish unused existing evidence from absent facts, ask bounded focused questions, preserve actual replies and integrate confirmed additions. An insufficient source archive can limit document readiness without judging the candidate. If the primary notices this before rendering, collect first; no extra pre-render panel is required. Save a pending or limited draft instead of presenting it as approved when the user is unavailable or declines.

After a collection-marked round, `--prepare --new-version --reason` requires changed normalized source context, not just revised wording, and consumes the same remaining total round budget. This checks changed inputs, not whether answers genuinely resolve the issue. Update affected profile/source reviews, matching and plan bindings before rendering/review; use the same document identity and retain prior reports. Questions do not consume another document round or reset previous rounds. A new review after exhaustion still needs an explicit additional-budget grant. Verification rejects a passing artifact whose report requests collection.

## Loop and preserved versions

1. The primary agent confirms presentation settings and writes/polishes the plan using selected archive facts and confirmed estimates.
2. Run `render-latex`, `render-pdf`, and `prepare-audit`. These scripts create the exact PDF, text, page images, artifact manifest, and pending audit.
3. Run `document_quality.py --prepare --writer-id ACTUAL_PRIMARY_ID`. It freezes inputs and artifact copies, creates a packet/report paths, and records round 0.
4. Launch permitted independent role sessions/agents, respecting global capacity. Save their responses in the assigned per-role files. Reports are not a shared mutable conversation and reviewers never rewrite the resume.
5. Run `document_quality.py` without `--prepare`. It validates reports, identities, PDF/page hashes, computes the weighted result, and records feedback/outcome. On `needs_material`, return to the collection path above before another draft; do not blindly rewrite the same thin facts.
6. On `rewrite`, the primary reads this round's issues and prior relevant issues, records a concrete change list in `revision-notes.json`, edits the plan or supported layout input, and reruns the deterministic rendering/audit commands. Prepare the next round with `--revision-notes PATH` and the same writer ID. Notes identify `previous_round_id` and changes with `finding_locator`, `action`, and `explanation`. Explain rejected/conflicting suggestions; never invent facts to increase a score or silently lower the frozen policy.
7. On `passed`, the helper deterministically transfers content/visual conclusions into the derived `audit.json`. Run `finalize-audit`; it verifies the passed loop for the current exact artifact and findings before finalizing.
8. On `exhausted`, stop automatic rewriting and give the user clearly labeled drafts, scores, and remaining issues. Do not call a failed draft audited or pretend the last version is best. Preserve all rounds for comparison; a further run requires an explicit user request/new budget, not a silent reset.

With `max_rewrites: 2`, the document starts with three total draft/review rounds: initial draft plus two rewrites. Ordinary continuation requires a previous `rewrite` decision, unchanged source context, changed resume.json/TeX, and revision notes. Regenerating PDF bytes alone cannot obtain another score. Unknown reviews may be completed on the same frozen draft within the host retry budget; archive failed attempt receipts before replacing a role response.

The new-round gate compares normalized JSON inputs (including nested object-key order and whitespace) and exact non-JSON inputs such as TeX. The plan's validated profile/market/JD/writing-rule hash bindings are excluded from its writing identity; formatting a source and refreshing those bindings alone grants no new panel. Array order and string content remain significant. Packets record `effective_input_version: 1` and `effective_input_hashes` alongside the exact file/context hashes. Older packets derive the comparison from their verified frozen snapshots, without changing history. This detects serialization-only edits, not arbitrary semantic equivalence or the usefulness of an edit. Real source facts, selection, wording or layout changes remain eligible under the ordinary rewrite/new-version rules.

Normalization applies only to deciding whether another round is warranted. Existing source/artifact bindings, snapshots, report hashes, PDF approval and finalization remain exact-byte checks. A formatting edit can therefore invalidate the existing exact approval while still being insufficient to request another panel. Preserve or restore the exact reviewed bytes when tidying formatting, or make the actual requested revision; do not transfer approval to changed files.

### Corrections, requested versions and session handoffs

Document identity, version lineage, active writer identity, and total budget are separate. A corrected profile/preferences/JD or a user-requested revision can supersede a pending, blocked, passed or exhausted round: refresh affected archive/plan/render bindings first, then use `--prepare --writer-id ACTUAL_ID --new-version --reason "User's concrete correction or revision request"`. The helper requires changed document or source context and retains previous packets, snapshots, reports, outcomes and version ancestry. Old originals need not be restored to their previous bytes. A new version consumes the existing document's remaining rounds; it never silently resets the count or lowers the frozen thresholds.

After exhaustion, stop automatic retries. Only an explicit user request authorizing additional work permits `--new-version --reason REASON --grant-rounds N`; the positive addition is recorded as a budget event. New run IDs, sessions, or version names alone grant no extra attempts. These options record the host's authorization statement; the CLI cannot establish what the user actually authorized. Source changes still require affected intake/discovery/screening checks before writing. Ordinary same-context rewrites keep the normal feedback-notes requirement; a requested new version records its request reason instead.

When a genuinely different primary session continues writing, run `--handoff --writer-id NEW_ACTUAL_ID --reason REASON` before preparation. This records from/to identities and rounds used without changing the budget, versions or reviews. Use the real new identity; do not impersonate the former writer. Every contributing writer is excluded from review, including writers recorded before a handoff. Handoff alone changes no frozen artifact and does not invalidate a pass; substantive edits require a new review. If a former reviewer becomes a writer, previous independence is no longer sufficient for current verification; obtain a fresh panel for the new version.

Newly confirmed facts go back into the reusable archive and refresh affected input bindings/reviews before another draft. A writing-quality loop must not restart intake or make every bullet require a new percentage. Earlier passed intake/discovery/screening reviews remain reusable where their inputs still apply.

The content panel's inspection of the actual current plan/PDF satisfies the tailoring review for that version as well as document content review. Rendering may run before that inspection because it is deterministic; do not add another identical pre-render content review or a fourth panel-approval agent by default. The panel is the independent document-stage review, not a writer self-review.

## Files and enforcement boundary

Use `jobs/<job-id>/quality-loop.json` for document identity, frozen policy, shared round budget, version ancestry and handoff/budget events. Each `quality-rounds/<round-id>/packet.json` maps original paths and hashes to exact retained bytes; per-role responses remain in `reviews/<role>.json` and each round has `outcome.json`. `quality.json` is a derived view of the current round. New snapshots use workspace-wide content-addressed `objects/sha256/<prefix>/<sha256>` blobs, written read-only and shared across rounds/jobs when bytes are identical. Packets retain original names, byte counts and media types because blob filenames have no extension. Legacy per-round snapshot paths remain readable. Corrupt/missing blobs fail verification; read-only mode is accidental-write protection, not protection against the workspace owner. Do not garbage-collect blobs referenced by retained packets. This avoids copying a large source archive for every round while retaining omitted-evidence access. Canonical renderer paths and general JD snapshot migration are unchanged.

The loop helper does not call models, select the writer's model, compile PDFs, or run a background coordinator. The host performs writing and independent reviews; scripts enforce packet/hash/identity/score/budget rules. Finalization checks the quality loop when one exists; legacy audits without a loop remain compatible. Real independent execution still relies on host receipts, not just an identity string inside a JSON file. `audit.json` and derived outcomes are outside the frozen artifact inventory, so finalization metadata does not cause a self-invalidating review cycle.

Apply [the workspace persistence contract](workspace-storage.md) to work outside the helper's snapshots too. Save pre-render writing alternatives, discarded drafts, render errors, raw malformed/unavailable review responses and attempt receipts before replacement, using uniquely named run artifacts when no owning history exists. Save revision notes as files and index the round/feedback and next action in the run checkpoint. Do not add the mutable run index to the frozen packet inventory or reset review budgets when continuing in another run.
