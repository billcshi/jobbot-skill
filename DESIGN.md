# JobBot Skill design

[中文设计](DESIGN_zh.md) · [Package overview](README.md) · [Agent entrypoint](SKILL.md)

JobBot helps people turn their existing experience into accurate, competitive resumes for specific companies and roles. It runs inside an agent conversation and keeps reusable information in a user-selected local workspace. The user supplies experience, corrects interpretations, and chooses opportunities; the agent reads, probes, organizes, researches, writes, and reviews.

Success means a useful resume that represents the candidate well and remains easy to revise. Source checks support that goal. JobBot does not certify a person's skills, discount student work, or automate application submission.

This is the primary design document. The Chinese counterpart records the same product decisions. Runtime instructions, schemas, and commands remain English; the conversation and resume language follow the user's confirmed settings.

## 1. Comprehensive, reusable intake

Start with the conversation and available resumes, GitHub repositories, portfolios, transcripts, or other materials. Read existing sources before asking questions, and reuse answers already supplied. Collect experience independently of a company or JD, including when the user has supplied one. Do not narrow collection to a role family or discard apparently irrelevant experience. The user need not know their desired occupation yet.

Collect work, education, courses, research, projects, organizations, volunteering, skills, and outcomes, alongside employment preferences. Materials are probes: a Python course can lead to its final assignment, personal contribution, design choices, and implementation. A strong embedded-systems grade can uncover design and debugging experience and support appropriately strong proficiency wording. These questions help articulate experience; they are not an exam.

Academic, personal, and volunteer work can support a competitive resume. Useful evidence includes problem difficulty, design decisions, implementation, and delivered work without requiring a business metric or paid employment. Strengthen expression while preserving what the person actually did. Imported materials are evidence sources, not automatically confirmed candidate facts. Distinguish source ownership, agent interpretation, and the user's account.

```text
materials / conversation
  -> read and identify useful leads
  -> probe personal actions and capabilities
  -> integrate answers and corrections
  -> save reusable facts and unresolved questions
```

Intake is skippable. A returning user can create a second or third resume from the saved archive without another interview or reconfirming unchanged facts. `intake.json` records the last actual user check-in. Around three months is a configurable conversational reminder to ask about progress, not a fact expiry or generation gate. A confirmed no-change answer can refresh it; generating a resume cannot. Missing historical timestamps do not imply stale candidate facts.

See [candidate intake](references/candidate-intake.md) and [career context](references/career-context.md).

## 2. Company and job discovery

After collecting or reusing the broad archive and preferences, find companies and jobs or read a supplied posting. Accept company names, URLs, screenshots, PDFs, and pasted text. A supplied source need not trigger a redundant search. Company leads without known openings remain valid leads; do not invent vacancies.

Use suitable authorized host connectors/APIs, web search and page reading, or browser/computer-use tools. No fixed acquisition channel or mandatory tool sequence is required. If one method is unsuitable, use an accessible alternative or supplied material, respecting the source's access restrictions.

Read screenshots and document pages with actual native vision. OCR is not a required intermediate step. Preserve originals, extracted text, provenance, capture time, and completeness. Blurred, cropped, or missing information stays unknown. Distinguish search snippets, partial captures, and complete JDs.

Use country constraints, preferred cities, relocation conditions, and work modes to guide searches. When role direction is undecided, propose several queries from the broad archive. This later exploration must not shrink intake. Save source success, empty results, partial results, unavailability, and errors separately; an API error is not evidence that no jobs exist. Deduplicate while retaining provenance and search relationships.

The original JobBot's discovery adapters are implementation references, not dependencies or presumed working integrations. The skill currently relies on host discovery tools; its CLI fetches public pages or imports UTF-8 text with original attachments. Standalone discovery API adapters are not implemented. See [company discovery](references/company-discovery.md).

## 3. Candidate knowledge, domain knowledge, and preferences

Candidate knowledge records what the person has done, can describe, and wants. Domain knowledge helps interpret materials and ask useful questions during intake, then research roles and organize expression later. Stable methods live in references; current company requirements and market information are looked up as needed with sources and dates. Research cannot become personal history.

Keep hard constraints, soft preferences, and conditional preferences distinct. “Must work in the US” excludes employment in other countries. “Prefer Seattle but willing to relocate” requires relocation conditions such as destinations, role, compensation, support, or timing; it means neither Seattle-only nor unrestricted global employment. Do not invent those conditions.

`preferences.json` stores employment countries, locations, relocation conditions, work modes, compensation preferences, and deal-breakers. Target roles may remain empty. Missing information remains unknown. Screening applies hard constraints first and compares preferences afterward; unknown is not automatically met or violated. Residence, work authorization, and employment country are separate. Document presentation belongs in `market.json`, not the search constraint record.

## 4. Local workspace and freshness

The workspace is user-selected and outside the skill source tree. The shared [storage contract](references/workspace-storage.md) defines ownership and layout; features must not create competing archives. Optional agent-maintained records are created as needed, not as empty scaffolding.

### Every intermediate result is durable

Save all task-relevant work products in the workspace, not only confirmed facts and final PDFs. This includes captures/extractions, questions and relevant user answers, unresolved interpretations, research and JD analysis, constraint/fit judgments, experience mapping and omissions, proposed wording/metrics, every draft, raw worker attempts/errors, reviews and revision notes. Keep concise decision reasons and confirmation status; do not require private internal reasoning or store credentials. Unconfirmed proposals do not become facts.

The primary maintains `runs/<run-id>/run.json` and append-only `events.jsonl` with task/stage state, input bindings, artifact paths/hashes, producer/attempt references, next action and pending questions. Save before handoffs, questions about an output and session end, with checkpoints during long stages. Use the existing owning record/history/snapshot when available; otherwise save unique versions under `runs/<run-id>/artifacts/<stage>/<artifact-id>/`. Retain previous, rejected, partial and failed outputs before replacement. Workers write isolated assigned files and the primary integrates their references.

After interruption, check the saved bindings and continue unfinished work, reusing valid completed results. Missing/stale results are explicit recovery issues; a new session/run does not reset retry budgets. Mutable run status and indexes stay outside frozen document inventories, while substantive changes still invalidate affected reviews. The storage contract specifies the details. These run records are host-agent conventions; current scripts do not create, validate or enforce a universal checkpoint/persistence engine.

```text
<workspace>/
  workspace.json                 Freshness, delegated-work and quality policies
  profile.json                   Confirmed candidate facts
  writing-rules.json             Confirmed scoped style/disclosure instructions
  preferences.json               Search constraints and preferences
  market.json                    Target-country document settings
  onboarding.json                Confirmed sections
  intake.json                    Last user check-in and archive hashes
  runs/<run-id>/
    run.json, events.jsonl        Agent-maintained state and artifact references
    artifacts/<stage>/<artifact-id>/  Other intermediate versions and raw outputs
  evidence/
    manifest.json                Source index, hashes, candidate relationship
    files/                       Imported originals
    github/                      Public account/repository captures
    reviews/<source-id>.json      Summaries, locators, interpretations, questions
    intake.json, intake-scans/    Hash-based folder index and retained scans
  notes/context.md               Optional navigation summary
  companies/<company-id>/         Agent-maintained company records and sources
  discovery/<search-id>/          Agent-maintained search records and diagnostics
  research/<topic>.md             Optional dated market research
  reviews/<scope>/<stage>/<id>/   Stage review packet and report
  scoring/<batch>/<task>/         Isolated scoring output and execution receipts
  jobs/<job-id>/
    job.json, checks.jsonl         Live status and append-only check history
    source.*, jd.txt, jd.json     Captured source and structured JD
    attachments/                 Original images, PDFs, or API captures
    match.json                   Validated job-fit assessment
    selection.json               Agent-maintained experience selection
    quantification.json          Optional pending quantitative proposals
    resume.json, resume.tex, resume.pdf
    render-inputs.json            Template/rule/plan hashes and selected engine
    command-logs/, history/       Render diagnostics and replaced artifact versions
    artifacts.json, audit.json, audit-pages/
    quality-loop.json, quality.json
    quality-rounds/<round-id>/    Frozen inventory, reviews, outcome
  objects/sha256/<prefix>/<hash>  Shared exact input/artifact bytes
```

Originals preserve context; reading notes reduce repeated context loading; the profile holds supplied or confirmed facts. Summaries do not replace source bytes, and an old resume does not override a new user correction. Record and resolve conflicts. `workspace-status` checks source hashes and note bindings; `reviewed` means the agent read a source, not that every inference is confirmed. Navigation notes are agent-maintained and not semantically validated by the CLI.

Companies, searches, and jobs are separate records linked by IDs. One company may have many jobs, and several searches may find the same job. `list-jobs` generates a local index rather than requiring another manually synchronized list.

### Job expiry and retained history

Each fetched/imported job has `job.json` with source observation time, last successful verification, local `expires_at`, availability, and an optional source-backed `application_deadline`. Local expiry means recheck; it is not the employer's deadline or proof of closure. Default freshness is seven days via `workspace.json.job_freshness_days`. Saving an old screenshot does not prove the job remains open; its initial availability is unknown.

Before reuse, inspect `list-jobs`, check the current source when needed, and record the result with `record-job-check`. Confirmed open/closed observations update verification/freshness. Inconclusive checks record the attempt without extending freshness or declaring closure. Reading, scoring, or generating a resume cannot refresh job timestamps. Keep expired, closed, and rejected jobs. Legacy jobs without metadata remain unknown rather than receiving invented dates.

Live status is separate from the hash-bound JD/PDF source chain. A status check does not invalidate an old PDF audit; changed JD content requires a new source version and regenerated affected materials. General `snapshots/<snapshot-id>/` and `documents/<document-id>/` migration is planned, not implemented. Keep the current renderer paths and create linked new job records for changed JDs. The quality loop already preserves its own per-round input and artifact copies.

Profile version 3 now supports independent `projects`, `research`, `coursework` and `activities` alongside employment, for professionals and students alike. Each has identified facts/source references; optional `related_ids` connect courses, projects, education and capabilities. Non-employment entries use their own names/organizations/roles rather than invented employers. Resume version 2 selects and renders these entries and binds writing rules; legacy profiles and plans remain readable. Explicit profile upgrades retain prior bytes. See [experience model](references/experience-model.md).

`intake_folder.py` saves hash-based scan reports and an intake index, imports new content once, retains changed/missing-source history and prepares pending reading notes. It does not interpret materials or confirm facts. Dedicated input folders avoid recursively importing managed outputs. `writing-rules.json` separately stores user-confirmed style/disclosure rules scoped to workspace, market or job. Scripts enforce explicit exclusions/phrases; free-form instructions need semantic review. File edits conservatively stale new plan bindings; prior PDFs are preserved. See [writing rules](references/writing-rules.md).

## 5. Responsibilities and independent review

| Component | Responsibility |
| --- | --- |
| `SKILL.md` | Entry, shared constraints, workflow, references loaded as needed |
| `references/` | Intake, discovery, selection, scoring, review protocols and prompts |
| Primary agent | Conversation, archive integration, orchestration, writing and rewrites |
| Scoring worker | Source-backed judgments for one job, written to isolated staging |
| Independent reviewer | Inspect current sources/results and write its own findings |
| Python scripts | File operations, validation, hashes, scoring math, rendering and gates |
| User workspace | Durable candidate information, sources, research and artifacts |

Core commands use the Python standard library. LaTeX and Poppler are optional system tools for PDF generation/audit, unnecessary for intake. The package has no database, Web UI, persistent service, provider SDK, or fixed model client. Scripts establish structural integrity and freshness; semantic fidelity and readability still require real review.

Review the major stages: intake, discovery, screening, tailoring, and document. Each has its own role and common-plus-specific prompt, not a generic request to approve. Earlier stages use the [stage-review protocol](references/stage-review.md) and role briefs under `references/reviewer-prompts/`. The current document route uses the separate scored panel in section 7; its content member also covers tailoring for that version. The legacy combined document-auditor brief remains for older records, not as another required panel member.

Reviewers receive necessary sources, confirmation context, scope, and outputs in independent contexts. They do not edit canonical candidate/job/document files. The primary integrates changes; workers write disjoint staging files. Record real producer/reviewer identities, execution receipts when available, prompt hashes for generic stage packets, input/output inventories, and SHA-256 bindings. A role/persona switch does not create independent execution, and a JSON identity string alone does not prove it occurred.

Reuse unchanged passed stage reviews, including when intake is skipped. An old archive without a review needs review of existing files, not another interview. Changed substantive inputs invalidate affected reviews and downstream results; a no-change check-in timestamp alone does not. Revisions receive new review records, not edited pass/fail history. If necessary independent execution, context, or vision is unavailable, preserve a pending draft. Review does not replace user confirmation or impose a skill-certification test.

Early-stage packets and gates are host-agent responsibilities, not enforced by the CLI. The document-quality helper validates its panel, artifact bindings, scores and rewrite budget, and finalization checks that loop when present.

## 6. Target-market presentation

Employment-country restrictions govern screening. A document's target country also informs language, photo choice, color, length, paper and layout suggestions. Confirm explicit settings in `market.json` before drafting, considering company requirements and user preferences; country conventions are suggestions, not universal rules. Detailed format choices must not delay broad intake.

The bundled layout is authored for JobBot under 0BSD; it does not port the old application's template or vendor third-party template/font/icon files. English and Chinese labels, A4/Letter and ordered sections are implemented. Chinese/CJK text selects a Unicode engine with installed ctex/Fandol; other languages need complete confirmed labels and appropriate font support. External TeX resources retain their licenses. Photo support and alternative layouts remain future work. See [template provenance](references/template-provenance.md).

## 7. From the archive to a tailored resume

```text
comprehensive archive + preferences
  -> discover or read supplied jobs
  -> hard constraints + reviewed match score shown to user
  -> select multiple experiences, deepen from saved details
  -> check material readiness; ask and integrate actual missing details if needed
  -> confirm presentation; primary agent writes/polishes
  -> scripts render LaTeX/PDF and inspection artifacts
  -> independent content/visual panel
       passed    -> finalize exact artifact -> manual handoff
       needs_material -> focused dialogue -> update sources/reviews -> resume same budget
       rewrite   -> primary revises with feedback -> render and review again
       blocked   -> resolve missing review/context on the same draft
       exhausted -> preserve labeled drafts and remaining issues
```

### Job-match assessment before writing

Dedicated `job-match-scorer` workers assess the complete archive, preferences, and JD, then an independent screening reviewer checks their output. Initial weights are role alignment 30%, skills 25%, location/work mode 20%, industry 15%, and experience level 10%. Judge actual tasks and transferable work, not titles or fixed years-of-experience rules. Weights are explicit and configurable.

Score applicable known dimensions from 0 to 1. Calculate a weighted average over scored dimensions, multiplied by 100. Unknown and not-applicable are not zero; show coverage and keep uncertainty visible. No scored dimensions means null score/tier and insufficient information. Tiers are A ≥80, B ≥65, C ≥50, D <50. A proven hard-constraint conflict produces `ineligible` and null score/ tier. Unknown constraints or unverified freshness remain provisional; closed or deadline-passed jobs are not current. This measures opportunity fit, not interview probability or the person's value.

Store the assessment in `match.json` with current input bindings. The primary prepares the seed, workers write isolated judgments, and `job_match.py --import-judgments` validates and publishes the numeric result. Show the reviewed score, tier, strengths, gaps, and unresolved conditions before generation. If the user already requested this resume, continue after explaining the result; low score alone does not require another approval. Do not silently waive a hard constraint. See [job matching](references/job-matching.md).

### Concurrency, attempts, and scoring cost

`agents.max_concurrent` covers all delegated scoring and review calls, including isolated sessions; `agents.scoring.max_concurrent` separately caps scorers. Both default to two, excluding the primary. Respect actual route-specific host capacity and queue excess work. Scoring `max_attempts` defaults to two total attempts per job/input/rubric version, including the first, across retries or new batch IDs. A worker failure is not a low match score.

Optional scoring provider/model/effort settings request an available authorized lower-cost route. Null inherits host defaults and promises no cost reduction. Record actual selection/usage where exposed; never claim a prompt selected a model or silently upgrade cost/provider. Reuse valid results and limit retries; concurrency controls throughput and limits, not proportional cost savings. `agent-policy` validates settings and computes caps; it does not dispatch, count live calls, detect capability, select models, or enforce retry receipts. Those are host responsibilities. See [scoring workers](references/scoring-workers.md).

### Multiple complementary experiences, retrieved from the archive

Filter/select first, then deepen selected entries using existing notes and originals. Choose several genuine experiences that together cover the job's requirements, arranging sections, order, emphasis, and space. Do not repeatedly use one nearest project, invent entries, or impose a fixed minimum count. Save evidence IDs, requirement coverage, reasons, emphasis, and alternatives in agent-maintained `selection.json`. Keep the full reusable archive intact.

Do not restart intake. Ask about material missing/conflicting details when retrieval cannot make the central contribution specific and understandable; a truthful generic fallback does not replace useful dialogue. A focused exception allows user-requested quantification or confirmation of a specific proposed numeric statement even with a nonnumeric fallback. Check saved information first, allow skipping, and do not require metrics for every entry. Save genuine new facts and refresh affected bindings/reviews before preparing the plan. See [experience selection](references/experience-selection.md).

Strengthen wording and distinguish measured values, calculations, genuine user estimates, and hypothetical proposals. A reasonable user estimate needs no formal external proof, but confirmation must establish task, scope, units, meaning and basis rather than whether the number looks attractive. Hypotheses may stay in optional `quantification.json` notes; they cannot become final factual claims without a real basis. Preserve approximate wording and supported round values; do not manufacture 37% to make 30% look measured. Precision follows evidence. See [quantified claims](references/quantified-claims.md).

### Primary-agent writing, deterministic rendering, bounded improvement

The workflow loops back to targeted collection when the main evidence remains too thin to support a convincing account. Initial intake stays comprehensive and independent of a JD; later recovery focuses only on unresolved experiences. The primary retrieves first, asks one to three neutral questions per batch, waits for actual replies and follows up from those answers. Default recovery allowance is two batches per gap across sessions, with further probing only at the user's request. Unknown/refused answers stay unknown; unavailable users leave `awaiting_candidate`, and insufficient material after refusal or exhaustion leaves a limited draft, never an inflated pass. Questions/replies and counters live under `runs/<run-id>/material-followups/`; confirmed additions enter the source-bound reusable profile, retain history, and trigger only affected reviews/matching/bindings. A real information update may update intake time; generating or asking alone does not.

Evidence strength is calibrated to the target job's actual scope, not the candidate's current title or a universal employer ladder. Entry roles may be well supported by concrete implementation/debugging/testing; roles requiring independent component ownership need evidence of decisions and delivery, and broader roles need the specified system or organizational scope. Match scorers explain this in existing dimension reasons; the primary records source-backed `target_level` in `selection.json`, which existing document preparation freezes. Content reviewers independently verify that interpretation and apply it to role coverage and substance: 90+ requires at least 30/35 substance at that scope and no unmet core level expectation. Unknown relevant experience can return to collection; explicitly absent experience is a `level_fit` limitation, not an invitation to repeat questions or invent ownership. Preserve an honest limited/stretch draft and stop futile rewrites without lowering the target or resetting the budget. Numerical thresholds remain unchanged; scope interpretation and these editorial anchors are host/model responsibilities, not a CLI classifier or automatic level-specific cutoff. See [level calibration](references/level-calibration.md).

Content scoring separates substance (35) from accuracy (20), role coverage (25), clarity (15) and expression (5). The prompt requires at least 30/35 substance for a 90+ content score, and caps a substantively unclear central case at 69 with concrete findings; no metric, paid work or project quota is required. These are editorial anchors, not hiring-market statistics or CLI-computed subscores. A completed content `next_action: collect_evidence` with an actionable medium/high `material_gap` mechanically prevents a pass even at high scores: `needs_material` if rounds remain, `exhausted` at the limit, while missing reviews stay `blocked`. Legacy reports can omit the field. A completed collection-request report is hash-locked while a blocked round waits for other reviewers; replacing it cannot erase the gate. Ordinary noncollection clarification remains supported. Actual questions, readiness detection and answer integration remain host-managed. After real source changes, continue via the same document's `--new-version --reason`; wording-only changes cannot bypass collection, and rounds/history never reset. See [material recovery](references/material-recovery.md).

Writing should expose the substance of the selected work: purpose, personal contribution, implementation choices and supported results or deliverables, where the archive provides them. Related initiatives can be organized within their actual employment entry; complementary course, research and personal projects remain legitimate evidence without a fixed project/bullet quota. Keep Skills compact and allocate space to useful experience before low-value repetition; choose Education/Skills order for the candidate and honor explicit user choices, including requests for more supported project coverage. Record emphasis and omitted alternatives in the selection note. Content review checks underused available evidence, and visual review checks actual space/hierarchy; clean rendering and factual correctness alone do not merit excellent scores. These are host writing/review responsibilities, not automated area/depth checks. The renderer still uses profile skill categories and has no per-document regrouping control. See [experience selection](references/experience-selection.md).

The user's primary agent handles settings, composition, polishing, and substantive rewrites with the chosen high-capability writing model when available. Cheap scorer settings do not select the writer. LaTeX generation, PDF compilation, text extraction, page rendering and hashes use scripts.

Independent content and visual reviewers can use genuinely isolated one-shot sessions or sub-agents. Tool-free sessions need actual frozen text/images, not file paths alone. Use a distinct execution identity for each role and the writer. Reviewers see the current sources/artifact and rubric, without writer reasoning, desired scores or prior scores. An optional ATS/text reviewer can inspect extraction and structure; it is not an employer's actual ATS score.

Defaults are content weight 60%, visual 40%, overall score at least 80, each role at least 70, complete page coverage, and no high-severity issues. Optional ATS changes the configured weights, which must sum to one. Job fit and document quality remain separate. Missing/unavailable review blocks completion without becoming zero or consuming a rewrite. Low scores without actionable findings require review clarification, not random rewriting.

On actionable failure, the primary records concrete revision notes and rewrites, then rerenders and requests fresh reviews. Default `max_rewrites: 2` allows the initial draft plus two revisions. Preserve every round and remaining issues. Do not lower the frozen policy or reset counters to pass; further budget after exhaustion needs an explicit user request. Host-managed `max_review_attempts` defaults to two per role/artifact, separately from document rewrite rounds.

`document_quality.py` freezes inputs/PDF/page copies, validates independent identities and exact hashes, computes gates, requires revision notes, and bounds rounds. On pass it derives content/visual `audit.json` sections; `finalize-audit` verifies that exact passed round when a loop exists. Reports, derived audits and finalization metadata stay outside the frozen artifact inventory to avoid invalidating their own review. Changed sources, plan, PDF or page images cannot inherit the old pass.

Document identity, linked versions, active/contributing writer identities, and total budget are separate. Corrected inputs or requested revisions can supersede any round state with `--new-version --reason`, while retaining old snapshots/reports and consuming the same total budget. Unchanged artifacts/context cannot be resubmitted simply to reroll a score. An actual session change uses `--handoff` with the new identity; all contributing writers remain excluded from review. Only an explicit user-authorized `--grant-rounds` event increases an exhausted budget. New snapshots deduplicate identical bytes across jobs/rounds in read-only content-addressed workspace objects; historical paths stay compatible. This is implemented lifecycle support at the existing renderer paths, not general JD/directory migration.

Managed output roots, including `objects/` and its descendants, are excluded from folder intake through a shared directory catalog. New-round eligibility uses normalized JSON content plus exact non-JSON inputs, so whitespace/key-order edits and refreshed plan-binding hashes alone do not grant another panel. Actual source/selection/wording/layout edits remain eligible; normalized hashes are not semantic certification. Exact-byte provenance, PDF/page/report hashes and finalization are unchanged. Older packets derive normalized comparisons from verified snapshots without modifying history.

Core writes reject symlink components and multiply linked regular outputs, use random exclusive atomic replacements, and default newly created helper files/directories to 0600/0700 on POSIX. Existing workspace permissions and external tool outputs are not automatically secured. Public HTTPS fetching pins validated public IPs to the actual TLS socket with certificate/hostname checks and bounded redirects/size. The public GitHub importer uses no ambient credentials, rejects non-public repository metadata, paginates owned repositories with a cap, and retains explicit coverage and original pages. These controls do not sandbox a hostile local workspace owner or establish candidate contribution/market coverage.

GitHub attempts progressively retain validated public responses and status/error receipts in unique attempt directories. A later-page failure preserves earlier captures without publishing an incomplete evidence source; unexpected private content is rejected before retention. Successful sources link the completed attempt. This follows the same partial/failed-work persistence contract as writing and reviews.

This panel covers tailoring and final document review without a duplicate pre-render review or another panel-approval agent. Actual model calls, writer rewrites, concurrency and review retries remain host operations. Legacy audits without a loop stay compatible, but the skill's default workflow uses the panel. See [document-quality loop](references/document-quality-loop.md).

The current `prepare-resume` still requires every onboarding section confirmed; explicitly empty sections are valid where appropriate. Saved confirmations carry across jobs, so returning users can skip intake. Task-specific readiness instead of the all-section gate remains planned; timestamps do not reset it.

## 8. Optional host memory

Local files are sufficient. If memory tools actually exist, offer separately scoped opt-in reading and writing. Prefer a workspace pointer and small continuity notes; show proposed writes rather than copying full transcripts, contact information, authorization details, or the complete profile by default. Reconcile old memory with local records and the user's corrections. Do not promise persistence, cross-device access or deletion beyond host capabilities. No host-specific memory connector is bundled.

## 9. Provider and host compatibility

Support Claude/Anthropic, OpenAI, DeepSeek, and other capable models through a provider-neutral contract. Separate skill tasks/files from host execution tools and from selected-model capabilities. A Codex configuration or one provider's documentation is not a universal runtime requirement.

Provider/model identifiers are opaque strings; defaults may inherit the authorized host choice. Check actual independent execution, modalities, structured output, context limits, effort controls, access and cost. A brand name or API compatibility claim does not establish those capabilities. Missing vision cannot complete visual review; no independent route means pending review. Map parameters through the host and validate responses locally.

Compatibility settings do not authorize sending candidate data to another provider or starting another billed service. Prefer already authorized host integrations; do not collect implicit API keys. Current support covers policy, prompts, local results and validation, not bundled provider network clients, automatic account/capability detection, or a background dispatcher. See [model compatibility](references/model-compatibility.md) for capability checks and official documentation entry points.

## 10. Implementation priorities

1. Preserve the implemented intake notes, provenance, reusable check-ins, local job status/history, scoring imports, portable policy and bounded quality loop.
2. Extend the implemented typed experiences and cross-record links based on real usage; keep work and non-work experience equally reusable.
3. Replace the all-section document-readiness gate with task-based readiness while preserving necessary source and target-market constraints.
4. Improve company/search indexes, source versioning and deduplication; rewrite discovery adapters only where needed and verify their actual behavior.
5. Build on the original bilingual layout with selectable templates, photo support and further localization, preserving explicit asset provenance.
6. Run and extend the [scenario suite](evals/README.md): employed and student intake, returning users, corrections and end-to-end PDF work. Prepared cases are distinct from actual agent execution and independent visual review.

Keep the permanent boundaries: no automated applications, no unsupported candidate claims, external user workspace, no service dependency, untrusted source handling, and visual approval bound to the exact PDF SHA-256. Repository commits, remote creation and pushes require explicit user authorization.
