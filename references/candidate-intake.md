# Candidate intake and local context

Read when gathering materials, interviewing a candidate, or resuming a prior session. The purpose is to discover useful experience and turn it into a competitive, truthful resume, not to grade the person or certify proficiency.

## Start with what exists

Ask briefly for the target employment country, workspace, and available materials. Accept any combination of conversation, GitHub, portfolio, previous resume, transcript, coursework, certificates, or project files. No source type is mandatory. Ask for role direction if known; do not require students to know job titles or market terminology before helping them.

The collection phase is independent of a company, JD, or role family. Aim for comprehensive coverage of work, education, courses, projects, research, activities, skills, and accomplishments. A supplied JD does not determine which facts are worth collecting. Keep information even when it does not belong in the current resume. Save a supplied posting for the later matching/drafting phase; do not make the user choose a specialty before establishing their history.

Read supplied materials before asking the user to recite them. Use small groups of questions that build on what you found. A direct user answer can establish a fact; it does not require independent verification. Summarize new information naturally and accept corrections rather than repeating an approval ritual for each field. Keep already confirmed facts across sessions.

Collection is a dialogue, not a single questionnaire or an import-only stage. When a project is described only by its name and technology, follow a concrete example through the person's own actions, decisions, difficulty, verification and deliverable. Choose the next question from their actual reply; do not prewrite a favorable answer. Keep broad intake independent of a JD and avoid mandatory metrics. Later writing or review can return here for a scoped missing detail using [material recovery](material-recovery.md), without repeating known facts or all onboarding sections.

## Incremental material folders

Accept a dedicated folder of mixed materials without asking the user to select every file. Run `scripts/intake_folder.py --workspace WORKSPACE --folder MATERIALS --import` from the skill package (or omit `--import` for inventory only). Workspace `inbox/` or an external materials folder is suitable; managed output trees such as evidence/jobs/runs/history/objects and all their subdirectories are rejected, including resolved aliases. The managed-directory catalog is shared with the content-addressed object store in `scripts/workspace_fs.py`. An ordinary materials subfolder named `objects` outside that managed root is allowed. Symlinks, repository metadata, oversized files and access errors remain explicit in the report.

`evidence/intake.json` indexes folders and original relative paths by content SHA-256, with a retained report per scan under `evidence/intake-scans/`. New/changed bytes are imported once, with pending reading notes for new sources; identical content reuses a retained source after its hash is checked. Changed source versions and missing originals do not delete prior imported copies. The optional `--type` sets a source category for the batch, default `other`; the command does not infer facts or confirm ownership from a filename.

Distinguish the scan change status from `processing`: an unchanged file that is still `not_imported` or `pending_read` remains actionable. Read saved notes for `reviewed` sources and return to originals as needed. A malformed review or modified retained source is an error, not an automatic reread/confirmation. Use native vision for images/PDF pages when supported; the scan imports original bytes without requiring OCR or claiming that a binary file is unreadable to the model. Do not execute imported scripts/repositories.

Complete the prepared reading notes instead of running `prepare-source-review` over an existing note. Then integrate supported/confirmed facts and record user corrections. The source index, notes and archive have separate ownership; reading status alone never promotes a candidate claim.

## Use sources as probes

| Source | Useful follow-ups | Resume opportunity |
| --- | --- | --- |
| Transcript | What did the Python final assignment do? What did you implement? Which embedded-system design or lab earned that result? | Relevant coursework, technical capabilities, design and implementation experience, academic achievement |
| GitHub | Which repositories show substantial work? What parts did you build? Why that architecture? What was difficult? | Projects, technical decisions, implementation and debugging skills |
| Portfolio | Which deliverables were yours? What problem, audience, constraints, and iteration shaped the result? | Design/process work, research, collaboration, finished artifacts |
| Old resume | What is outdated or undersold? What did “helped develop” actually involve? | Stronger ownership language, clearer scope, missing achievements |
| Certificate | What did preparation or assessment involve? Is it current? | Named qualification and relevant practical learning |
| Conversation | What did you build, organize, teach, investigate, or improve? | Experience that has never appeared in a formal resume |

Coursework is real experience. Strong course performance is a positive signal and a productive starting point, not a reason to discount skills. An A in an embedded-systems course can lead to language such as “proficient in embedded system design,” enriched with the actual design, implementation, and debugging work discussed. Do not require a paid role or deployed product to use strong wording. Choose proficiency terms for their meaning in the user's account, rather than applying a blanket prohibition or deriving a universal proficiency level from a letter grade alone.

For example, after learning what a Python assignment involved, replace “Completed a Python course” with “Developed a Python data-processing tool with CSV ingestion, validation, and summary reporting” when those activities were described. Do not invent a percentage improvement or production usage to make the bullet sound impressive. If there are no measured outcomes, emphasize the problem, implementation, complexity, design choice, or completed deliverable.

A profile URL authorizes useful inspection of public repositories within the request; it need not trigger a question asking the user to select every repo. Use the imported index to inventory the user's work across domains. Inspect it in manageable batches, keeping the remaining sources available for later reading; do not drop projects for lacking overlap with a target JD. Stars and commit counts are not a measure of candidate value. Forks and group projects can contain meaningful personal contributions; ask about those contributions. Record what was actually inspected. README-only inspection cannot be described as verification of the implementation. Do not execute downloaded code to read it.

`import-github` is public and unauthenticated: it does not borrow `GITHUB_TOKEN` or other ambient credentials and rejects private/unclassified repository metadata. Profile imports paginate owned public repositories, defaulting to at most ten 100-entry pages (`--max-pages 1..100`). Read the retained `coverage.json`: a page cap records `complete: false` and the next page; even a complete owned-repository index is not an inventory of contributions to other accounts. Original page responses, the combined index and coverage are hashed together. A fresh capture uses a new explicit `--id`; prior snapshots are retained. API limits or missing README content are acquisition limits, not evidence that the user has no relevant work. Core HTTPS fetching pins validated public IPs to the actual TLS connection, retains certificate/hostname checks, bounds size/redirects, and sends no implicit proxy or cross-origin authentication. Host browser/API tools have their own security contracts.

Each import progressively saves validated public responses and a status/error receipt under `evidence/github-attempts/<source-id>/<attempt-id>/`. A failed later page retains earlier captures for diagnosis or continuation, without publishing an incomplete source in the evidence manifest. Failed/private response validation records the error without retaining unexpected private repository content. Successful sources link their attempt directory; retained partial data is not confirmed candidate evidence. README unavailability is recorded even when the remaining public snapshot can be published.

Read screenshots, transcript images, and visual portfolios directly with the agent model's native vision when available. OCR is not required. Use available host tools to open PDFs, presentations, or web portfolios as needed. The core CLI copies local evidence; it does not interpret a transcript, read arbitrary portfolio URLs, or inspect a complete Git repository. If tools cannot read a source, say what is missing and request a readable excerpt rather than claiming to have read it. Save a useful portfolio page or code excerpt as additional local evidence with its URL/path, access date, and section/commit context before relying on it across sessions. Do not introduce an external image/text processing service as a requirement for this workflow.

## Keep sources, interpretations, and facts distinct

The workspace separates original bytes, agent reading notes, and confirmed profile facts. Separation supports stronger writing without accidentally promoting a guess into a personal claim.

- Import and retain originals with `import-evidence` or `import-github`.
- Run `prepare-source-review --id SOURCE_ID`. Read the files it lists, then fill the JSON review: short summary, observations, promising candidate facts, and questions. Each observation/fact has a locator such as “p. 2, Projects”, “README.md, Architecture”, or an inspected file and line.
- Set `status` to `reviewed` only after reading. This means reading is complete, not that the person has passed a test or every interpretation is confirmed.
- Discuss material ambiguities and personal contributions with the user. A source ownership confirmation applies to their relationship to the source; it does not silently endorse every inference in a generated summary.
- Write confirmed facts into `profile.json` and preferences into `preferences.json`. Preserve facts even if the current job does not use them. Put unsettled interpretations in reading notes, not the profile.

If two sources disagree about a date, grade, title, or contribution, preserve the alternatives and ask a focused question. Do not select whichever looks better. A correction updates the profile and makes affected drafts eligible for redrafting and audit; an old resume is not permanent authority.

Use [experience-model.md](experience-model.md): profile version 3 supports independent projects, research, coursework and activities alongside employment. Save personal actions/results as identified source-backed facts and use `related_ids` for course/project/skill relationships. Version 2 remains readable; explicit upgrades retain old bytes. Do not invent an employer or job title. Record user-confirmed standing style/disclosure instructions using [writing-rules.md](writing-rules.md), independently of search preferences.

## Collect search preferences alongside the full history

Ask what is non-negotiable, preferred, or negotiable, using `schemas/preferences.schema.json`. The user need not know a target job title. Collect these preferences now; apply them when considering jobs later.

- Employment country: distinguish “only the US” from a general preference for the US. Record an explicit restriction as `employment_countries` with `mode: only` and `countries: ["US"]`. Unknown is `unspecified`, not permission to search anywhere. Do not infer restrictions from residence or `market.json`.
- Preferred locations: `locations` records soft preferences such as Seattle. Ask separately whether relocation is acceptable, conditional, or excluded.
- Relocation: ask what would make moving worthwhile: destinations, role, compensation, company characteristics, timing, or relocation support. Record the user's bar in `relocation.conditions`; retain unanswered issues rather than inventing a salary or geographic limit. An empty acceptable-location list is not evidence of worldwide mobility.
- Work modes, compensation, and deal-breakers: preserve the difference between a wish and an absolute minimum or exclusion. State units/currency and scope where relevant; do not silently convert “prefer” into “must.”
- Target roles: record any stated interests, but allow an empty list. Do not run role selection or market-driven filtering as an onboarding requirement.

For example, a user can require US employment, prefer Seattle, and consider other US cities only for a sufficiently attractive role/package. Summarize those three separate choices and ask about the relocation bar. Do not collapse them into “Seattle only” or treat relocation as waiving the country restriction.

These fields capture decisions; the CLI validates their structure but does not yet implement job filtering or ranking. Missing optional fields in an older workspace mean unknown, not a negative preference. Preserve valid existing preferences and ask only about material gaps.

## Resume efficiently in another conversation

Collection is optional when the user already has a usable local profile. For another resume, start with that profile and the new job; do not import the same sources, reread everything, repeat onboarding, or reconfirm unchanged facts.

Run `workspace-status` first. It reports source files, ownership confirmation, review status, integrity errors, onboarding state, and the current profile hash. Read the relevant current reviews, then the confirmed profile and preferences. Open full originals for unresolved details and whenever a draft needs closer support. Never turn a review summary into an independent evidence source.

Optionally maintain `notes/context.md` as a short navigation note containing: current goal, profile SHA-256, relevant source/review paths, open questions, and next useful action. This is agent-written and is not validated by the CLI. Compare its profile hash and referenced source reviews before reusing it. Avoid duplicating the full profile. Update it after meaningful changes, not after every message.

`intake.json` records the most recent user-confirmed information review, with the profile and preference hashes at that time. After initial collection or a brief progress check, run `record-intake-review --summary SUMMARY`. A confirmed “no changes” also counts as a review and does not alter profile facts. Merely opening files, importing a source, or generating a resume does not count.

Use elapsed time to guide a small follow-up, not to discard facts. For example: “We last updated your information about three months ago. Any new projects, coursework, work experience, progress, or changes in preferences?” Ask concrete questions based on known ongoing work when possible. If the user wants to skip updates, use the existing profile and preserve the old review time. Do not mark a skipped or unanswered check-in as completed.

`workspace-status --refresh-after-days N` changes the advisory interval from the default 90 days. Its `suggest_refresh` flag also indicates local profile or preference changes since the recorded review. Neither case blocks resume generation. File-integrity problems still need their own resolution. If no review is recorded, the time is unknown; file modification times are not a substitute for a conversation date. Missing metadata does not force onboarding.

Source reviews are bound to the imported bytes. If `workspace-status` reports an error, inspect and resolve it before using the notes. Import changed material under a new source ID, retaining the old snapshot and notes; do not edit a recorded hash merely to hide staleness. Existing reviews are never silently overwritten by `prepare-source-review`.

## Optional host memory

Local files are sufficient and remain authoritative. Host memory is an optional continuity aid, not a required database or a substitute for provenance. Only offer memory integration when the host actually exposes the capability. No memory API or platform-specific dependency is bundled with this skill.

Ask whether the user wants to read existing career-related memory, save a small continuity note, both, or neither. Reading and writing have separate scopes; agreement to one does not authorize the other. State the exact proposed write before saving it. Prefer a workspace pointer and non-sensitive workflow preferences. Do not copy transcripts, contact information, authorization details, private project material, or full profiles into memory by default. Record consent scope in `notes/context.md` if used; ask again only if scope changes, and honor withdrawal without interrupting local work.

Treat retrieved memories as leads that may be stale. Reconcile them with the user and local profile before adding claims. Do not promise persistence, cross-agent access, or deletion capabilities that the host does not provide.
