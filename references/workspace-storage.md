# Local workspace storage contract

Read when saving candidate data, company/job leads, source snapshots, or documents. Keep all personal and task data in the external user-selected workspace. The skill package contains instructions, schemas, scripts, and templates only. This contract plans the shared layout before adding more discovery adapters; it does not silently migrate existing user files.

## Persist every intermediate work product

The filesystem is the durable working state for the whole workflow. Save all task-relevant intermediate outputs, including incomplete, rejected, superseded, and failed-attempt results. A chat response, tool transcript, or sub-agent's context is not the only retained copy. Write outputs before handing them to another worker/stage, requesting user input about them, or ending the session. Checkpoint long-running stages after each meaningful result so an interruption does not require repeating completed work.

Save sources/captures, transcriptions, reading notes, candidate interpretations, unresolved questions, relevant user answers/confirmations, research, structured JD analysis, constraints/fit judgments, experience selections, alternative wording and quantitative proposals, every draft, review reports, feedback, revision notes, and final artifacts. Record concise decision reasons sufficient to understand choices. Retain task-relevant tool errors and worker responses, including malformed output, before a retry replaces them. Do not store API keys, authentication headers, credentials, or private internal reasoning.

Use each existing record's owning path below; do not copy canonical profile/JD data into another independently maintained archive. Add an agent-maintained `runs/<run-id>/run.json` to index a workflow execution, with an append-only `events.jsonl`. These files are conventions, not a new CLI command, validated schema, background scheduler, or automatically enforced persistence layer. The host agent must create/update them when work actually occurs.

A run manifest records its schema version, ID, task, timestamps, actual producer identity when available, job IDs, relevant input paths/hashes, stage states, artifact references (path/hash/producer/status), prior attempt references, last completed step, next action, and unresolved user questions. Store additional intermediates with no existing owner under `runs/<run-id>/artifacts/<stage>/<artifact-id>/`; use JSON for structured work, Markdown for readable notes, and original formats for source/raw outputs. Do not precreate empty stage outputs or claim a checkpoint exists before saving it.

| Work product | Owning location |
| --- | --- |
| Sources, extraction, reading notes and proposed candidate facts | `evidence/` and source reviews; extra extraction/answer records in the run artifacts |
| User-confirmed facts and preferences | Canonical profile/preferences; confirmation context in intake/source/run records |
| Queries, result captures, company research and source diagnostics | `discovery/`, `companies/`, `research/` |
| JD text/structure and availability checks | Job source files, `jd.*`, `job.json`, `checks.jsonl` |
| Raw worker attempts, judgments, scores and screening decisions | Isolated `scoring/` attempt files, `match.json`, stage reviews and run artifacts |
| Requirement mapping, selection, omitted alternatives and proposed metrics | `selection.json`, optional `quantification.json`, run artifacts |
| All writing drafts, review feedback and revision notes | Existing quality-round snapshots/reviews plus run artifacts for drafts not captured there |
| Rendering output/diagnostics, final PDF, text, images and audits | Existing job artifact paths, quality-round snapshots and run artifacts |

Files need not be duplicated when a retained source or helper-managed snapshot already owns the exact bytes: reference its path/hash. Before changing or overwriting a work product, retain the prior version using its existing history mechanism or a uniquely named run artifact. This includes pre-render drafts, discarded alternatives and failed review responses, not just completed PDFs. Use distinct IDs for attempts and versions; never overwrite a completed review.

Only the primary agent updates the run manifest and integrates canonical data. Workers write their own assigned files and report their paths/hashes; the primary records them before proceeding. Keep source data and unresolved proposals distinct from confirmed candidate facts. Malformed output may be saved as raw text plus an error record without treating it as valid JSON or a passed stage.

On resume, read the run manifest and referenced records, verify the relevant hashes and review bindings, then continue at the next unfinished action. Reuse valid completed work; refresh only affected results. A stale/missing artifact is an explicit recovery issue, not permission to mark its stage complete. Record partial/blocked/failed states honestly. Retry budgets include previous attempts for the same task/input/rubric version across sessions and run IDs; starting a run does not reset them.

Run status, event logs and navigation indexes are mutable operational metadata; do not add them to a frozen document's artifact inventory or make a manifest hash itself. Their updates alone do not invalidate a review. Actual changes to reviewed sources, facts, plans or artifacts still require affected rechecks. Saving task state does not require exporting a full conversation. Preserve the relevant user answers and decisions with their confirmation status. If the host cannot export a tool result, record the inspected content and capture limitation instead of claiming a complete raw snapshot.

## Ownership and layout

```text
<workspace>/
  workspace.json                  Layout/config version and freshness policy
  profile.json                    Reusable, confirmed candidate facts
  writing-rules.json              User-confirmed style/disclosure rules and scope
  preferences.json                Search constraints and negotiable preferences
  market.json                     Current document market/presentation settings
  onboarding.json                 Existing confirmation state
  intake.json                     Last user-confirmed profile/preference review
  runs/<run-id>/
    run.json                      Agent-maintained state and artifact index
    events.jsonl                  Append-only checkpoints, attempts, decisions
    artifacts/<stage>/<artifact-id>/  Other intermediate versions/raw outputs
  evidence/
    manifest.json                 Candidate evidence source index
    files/                        Imported originals
    github/                       Imported public GitHub snapshots
    github-attempts/<id>/<uuid>/   Progressive public captures and failure receipts
    reviews/<source-id>.json       Source-bound reading summaries and questions
    intake.json                   CLI-managed folder/content/source index
    intake-scans/<scan-id>.json    Retained folder scans, omissions and diagnostics
  companies/<company-id>/
    company.json                  Company identity, career URL, source references
    sources/<capture-id>/         Company research source snapshots
  discovery/<search-id>/
    search.json                   Queries, scope, source outcomes, company/job IDs
    sources/<capture-id>/          Search/API/browser snapshots
  jobs/<job-id>/
    job.json                      Live availability, expiry, company reference
    match.json                    Agent judgments and calculated match score
    match-history/                Archived assessments replaced during refresh
    selection.json                Agent-maintained multi-experience selection plan
    quantification.json           Optional proposed metrics, basis and confirmations
    checks.jsonl                  Append-only source-backed check events
    jd.json                       Structured JD bound to the current source
    jd.txt                        Readable JD from the captured source
    source.html or source.txt     Preserved source bytes
    attachments/                  Original screenshot/PDF/API response files
    snapshots/<snapshot-id>/       Planned: retained revisions of the JD/source
    documents/<document-id>/      Planned: versioned resume/TeX/PDF/audit bundles
    resume.json, resume.tex, ...   Current renderer's document paths
    render-inputs.json             Template/rule/plan/input hashes and TeX engine
    command-logs/<id>.json         Rendering/inspection commands, outputs and errors
    history/<filename>/<id>.*      Prior replaced plans/TeX/PDF/text/manifests
    history/audit-pages/<id>/      Previous inspection page images
    quality-loop.json             Document/version/writer history and shared round budget
    quality.json                  Derived latest quality result
    quality-rounds/<round-id>/
      packet.json                  Original-path/hash to retained-blob inventory
      reviews/<role>.json          Independent one-shot/subagent quality responses
      outcome.json                Weighted score, issues, decision, audit sections
  notes/context.md                Optional navigation summary
  objects/sha256/<prefix>/<hash>  Shared exact bytes referenced by quality packets
  research/<topic>.md             Market context with sources and dates
  history/<filename>/<id>.*        Prior upgraded profiles or edited writing rules
  scoring/<batch-id>/
    batch.json                    Policy, job/task IDs, active states and receipts
    <task-id>/packet.json          Frozen scoring seed, sources and assignment
    <task-id>/judgments.json       Isolated scorer output; published after checks
  reviews/<scope-id>/<stage>/<review-id>/
    packet.json                   Task, input/output inventory and SHA-256 hashes
    report.json                   Independent reviewer identity, scope, verdict
```

The root profile/preferences/market names and current job rendering paths remain compatible with the existing CLI. `workspace.json`, candidate evidence, JD files, `job.json`, job checks, folder intake and writing-rule records have CLI support. Profile v3 adds typed non-employment experience; legacy v2 remains readable. Company/search records, their source directories, run checkpoints, and notes are currently agent-maintained conventions; they must be written when those operations produce results. JD revision and document-version directories are the target layout; commands do not yet create or render them. Do not move existing originals or documents to those paths before implementing explicit migration and caller support.

`document_quality.py` creates round packets under `quality-rounds/` and deduplicates retained bytes in workspace-wide `objects/sha256/<prefix>/<hash>`. Retain blobs for every historical packet; legacy round-local snapshots remain readable. Document ID, linked versions, active/contributing writers, and the total draft budget are distinct fields. Corrections and requested revisions use explicit new-version reasons; session handoffs record actual identities without resetting attempts. This preserves reviewed versions without relocating canonical renderer paths or claiming general JD/document-directory migration is implemented.

`objects/` is managed output, never an intake-material root. The shared directory catalog in [workspace_fs.py](../scripts/workspace_fs.py) is used by folder intake and the object store's directory constant; update it when adding managed roots. Rejected scans of managed directories or their resolved aliases do not change the manifest, reading notes, scan index or object bytes. New-round comparison normalizes JSON separately from exact storage hashes; it never rewrites historical files or weakens current approval bindings.

Core writers reject symlink output components and multiply linked regular output files. On POSIX they walk directories with no-follow descriptors and use random exclusive temporary files plus atomic replacement; append operations also check the opened inode. New helper-created directories use mode 0700 and files 0600; retained content blobs use 0400. Existing workspace permissions are not automatically tightened, and external TeX/Poppler outputs inherit the process umask. These controls prevent the reported link escapes and predictable-temp writes; they do not sandbox a hostile workspace owner who can mutate directories while external tools run. Select a trusted private workspace and do not run imported code. The primary remains the sole canonical writer; these helpers are not a multi-writer transaction coordinator.

Stage-review packets/reports are also agent-maintained; see [stage-review.md](stage-review.md). Each attempt has its own directory and preserves producer/reviewer identities, source/output hashes, verdict, and findings. The CLI does not yet validate or enforce these review records.

The document-loop panel uses `quality-review.schema.json` separately. Its helper validates independent identities, scores, input/PDF/image hashes and rewrite budgets; finalization checks a passed loop when present. Model/session execution and receipts remain host responsibilities, and calls share the global cap.

`scripts/job_match.py` prepares/validates match assessments and calculates their score/tier/coverage. Semantic judgments and user-facing presentation remain host agent responsibilities. `selection.json` is agent-maintained, not a validated canonical profile. Scoring/selection never renew job freshness, and assessments become stale when their profile/preferences/JD/status bindings change.

Scoring batch/task records and runtime model/usage receipts are agent-maintained. Workers only write assigned staging files. `job_match.py --import-judgments` validates the worker's frozen bindings and results before publishing, retains the old canonical assessment in history, and records the imported file hash. Model routing and global concurrency enforcement belong to the host scheduler; `agent-policy` validates configuration and calculates caps, not live dispatch.

Each JSON record carries a schema version. Use JSON for structured records, Markdown for agent-readable summaries, and original formats for sources. Hashes cover original bytes or explicitly identified structured artifacts; timestamps are timezone-aware ISO 8601, stored in UTC for generated records. Render user-facing times in their timezone. Do not infer event dates from file modification time.

## Identity and references

Use IDs in cross-record references, not company display names or job titles. A company can have many postings, and a posting can have many discovery sources. Search records reference company/job IDs rather than copying complete JDs. Keep source URLs and provider posting IDs for deduplication. Similar titles do not establish identical jobs; the same title can have several locations, levels, or requisitions.

Company records contain identity, website/career links, known source snapshots, and observation/review dates. They do not imply there is an open vacancy. A job may initially have `company_id: null`; linking it later changes live metadata, not the captured JD bytes. API/browser data is job research, not candidate evidence in `evidence/manifest.json`.

The eventual canonical job ID should remain stable across source refreshes. Current `fetch-jd` defaults to a URL-derived ID; `import-jd` defaults to a source/text-derived ID, and both reject overwriting an existing job. Use explicit `--job` IDs when organizing known postings. Full stable-identity, multi-snapshot refresh and duplicate reconciliation remain implementation work.

Indexes and summaries are derived views, not alternative sources of truth. `list-jobs` builds an inventory from local job records on demand; do not add a second manually synchronized primary job list. `search.json` records what a specific search found and why it was incomplete; it does not own job status.

## Job timestamps and expiry

`job.json` deliberately separates changing status from the hash-bound JD:

| Field | Meaning |
| --- | --- |
| `source_observed_at` | Time this source was fetched/imported; a screenshot import does not prove that the pictured vacancy is currently open |
| `last_verified_at` | Last successful check establishing open/closed status; `null` until checked |
| `expires_at` | Local freshness expiry: after this time the stored information needs rechecking |
| `application_deadline` | Employer-published deadline, or `null` when unknown |
| `deadline_source` | Locator supporting the employer's deadline |
| `availability` | `unknown`, `open`, or `closed`, from the most recent recorded check |

Every newly fetched/imported JD gets a local `expires_at`. `workspace.json` sets `job_freshness_days`, initially 7 days as an adjustable product default, not a claim about job-market behavior. Initial availability is `unknown` even when the local snapshot is fresh. Creating a document or reading files does not reset any of these times. Policy changes affect new imports and successful checks; they do not silently rewrite existing records.

Keep freshness and availability separate. Reaching `expires_at` means stale information, not a closed vacancy. Passing an evidenced deadline and observing an explicit closure are distinct reasons not to present a job as currently actionable. If the employer publishes no deadline, leave it unknown. A source date without timezone/cutoff precision should be retained in source notes; do not invent a precise deadline timestamp.

Run `list-jobs --workspace WORKSPACE` before reusing opportunities. It reports freshness, availability, expiry, and whether a known deadline has passed. It does not browse, prove the source is current, or schedule background checks. An old workspace without `job.json` reports unknown status rather than an invented expiry; the next source-backed check can create the metadata.

To refresh, the agent reads an accessible current source using available tools, then records its conclusion:

```bash
python3 "$SKILL_DIR/scripts/jobbot_skill.py" record-job-check \
  --workspace "$WORKSPACE" --job "$JOB_ID" \
  --availability "$OPEN_CLOSED_OR_UNKNOWN" \
  --source "$CHECK_SOURCE" --summary "$OBSERVED_RESULT"
```

`open` or `closed` updates the verification time and local expiry. `unknown` records an inconclusive attempt without extending freshness or claiming closure. Optional `--deadline` requires `--deadline-source` and a timezone-aware timestamp. Use `--clear-deadline` only when a successful current source check establishes that an earlier recorded cutoff no longer applies; the check event retains why. The command records the agent's observation; it does not perform the network check itself. Check events retain source, time, and result in `checks.jsonl`.

Freshness expiry does not delete a job or invalidate a historically audited document. Recheck expired information before calling it a current opportunity; the user can still request a historical draft, with its status explained. Candidate-profile check-ins are separate, advisory reviews and do not inherit the job expiry policy.

## Revisions, summaries, and retention

Keep original captures and generated audited artifacts traceable. A status check that confirms the same content changes `job.json`/`checks.jsonl`, not the JD hash or an existing PDF audit. If requirements actually change, retain a new source snapshot and regenerate affected materials; do not relabel the old JD/PDF as based on the new description.

Until snapshot/version commands exist, refreshing changed JD content requires a separate job record/explicit new ID; preserve the prior record and link the relationship in discovery notes. Do not overwrite current source files or change a hash just to make old artifacts pass validation. Future migration must retain existing IDs, hashes, source files, and document audit bindings and must not merge or discard ambiguous duplicates automatically.

Summaries point to source IDs, snapshots, and relevant record hashes. Reading them is the default for context efficiency; open originals for details or conflicts. A summary is never the only retained copy of a source.

Closed, stale, rejected, and duplicate records remain local history. Do not automatically delete sources or candidate information when a job expires or is filtered out. No database, daemon, or background scheduler is required. Refresh checks occur when the agent runs the workflow unless the user separately requests scheduling or cleanup.

## Targeted material-recovery records

Use existing operational `runs/<run-id>/material-followups/<gap-id>/` paths for missing-material findings, searched-source notes, question batches, actual replies, status and cross-session counts; no new managed output root is introduced. Keep these outside frozen document inventories. Import confirmed new answers into canonical evidence/profile records before reuse, preserve earlier versions and refresh affected bindings/reviews. A question log alone is not confirmed candidate evidence. See [material recovery](material-recovery.md).
