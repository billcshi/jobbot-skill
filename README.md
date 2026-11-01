# JobBot Skill

[中文](README_zh.md) · [Design](DESIGN.md) · [中文设计](DESIGN_zh.md) · [Agent instructions](SKILL.md)

A standalone, file-based Agent Skill that helps people build a reusable experience archive, find suitable opportunities, and create accurate, competitive resumes for particular jobs. It runs inside an agent conversation without the original JobBot application, a database, Node.js, or a Web UI.

The workflow supports Claude/Anthropic, OpenAI, DeepSeek, and other capable models through the host's authorized tools. This package supplies portable instructions and local helpers, not provider clients or a model dispatcher.

## Workflow

```text
collect or reuse a comprehensive candidate archive and preferences
  -> find companies/jobs or read user-supplied postings
  -> check hard constraints; show a reviewed job-match assessment
  -> select several complementary experiences from saved information
  -> check material readiness; collect missing details through dialogue when needed
  -> confirm target-market document settings
  -> primary agent writes and polishes an evidence-bound resume
  -> scripts render LaTeX/PDF and inspection artifacts
  -> independent content/visual reviewers score the exact version
       passed: finalize and hand files to the user
       needs_material: focused collection -> update affected records/reviews -> resume
       rewrite: primary revises from feedback, within the budget
       blocked/exhausted: preserve labeled drafts and explain remaining issues
```

Review strength is calibrated to the target role's responsibilities: concrete implementation can support an entry role, while independent ownership roles need stronger decision and delivery evidence. Matching and content review share that scope; unsupported seniority is never added. Numerical pass thresholds remain unchanged, and level interpretation is host-managed. See [level calibration](references/level-calibration.md).

Intake is comprehensive and independent of a JD. Old resumes, GitHub, portfolios, transcripts, and conversation help uncover academic, personal, volunteer, and professional experience. Collect hard country constraints, location preferences, and conditional relocation separately. The user need not have chosen a role. Later filtering does not shrink the reusable archive.

For subsequent resumes, skip intake when saved information is usable. `intake.json` records the last user-confirmed check-in; around three months is an optional progress reminder, not an expiry date. Generating a resume does not refresh it. Local files work without host memory; memory access is opt-in.

All intermediate work products are saved in the external workspace: source captures, notes and analysis, relevant answers/confirmations, selections, drafts, failed attempts, review feedback and revisions. Existing owning files and snapshots retain the content; an agent-maintained `runs/<run-id>/` index records stage state, artifact paths/hashes and next actions for continuation. Save before handoffs and preserve superseded versions. This persistence protocol is carried out by the host agent, not an automatic checkpoint engine in the CLI. See the [storage contract](references/workspace-storage.md).

Discovery uses available host APIs/connectors, search, page reading, or browser/computer-use tools. Users may supply links, screenshots, PDFs, or text. Read images with actual native vision; OCR is not required. Jobs retain sources, attachments and hashes, plus separate local freshness and employer deadlines. The default seven-day local expiry means recheck, not closed. Keep historical jobs and artifacts; failed checks do not extend freshness.

Scoring workers provide source-backed judgments, `job_match.py` calculates score/tier, and an independent screening reviewer checks the assessment before it is shown to the user. Low scores alone do not prevent a requested draft. Primary-agent writing stays separate from optional lower-cost scoring models. Default delegated concurrency is two globally and two for scoring; scheduling, model selection, execution receipts and attempt tracking belong to the host.

The document panel uses independent one-shot sessions or sub-agents. Defaults are overall 80, each required role 70, content/visual weights 60%/40%, and no high-severity issues. The initial draft permits two rewrites by default. Unavailable review is pending, not zero. All pages require visual inspection, and approval binds to the exact PDF SHA-256. Never automate applications or add unsupported candidate claims.

Corrections and requested revisions create linked versions with `document_quality.py --prepare --new-version --reason REASON`; session continuation records the actual new writer through `--handoff`. Both preserve history and share the existing total budget. Exhausted budgets require an explicitly authorized `--grant-rounds N`, never a reset. Content-addressed snapshots reuse identical bytes across rounds. Public GitHub imports use no ambient token and record bounded pagination coverage. See [document lifecycle](references/document-quality-loop.md) and [intake limits](references/candidate-intake.md).

Folder intake rejects managed `objects/` snapshots and their descendants. New-round checks ignore JSON whitespace/key-order changes and refreshed plan-binding hashes alone; exact source/artifact approval hashes remain required.

## Requirements and boundaries

- Python 3.10+; core commands use the standard library.
- A supported TeX engine for PDF generation: pdfLaTeX for ordinary English, XeLaTeX/LuaLaTeX with installed ctex/Fandol for Chinese/CJK text; Poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) for inspection. These are optional for intake.
- A host agent with the reading/search tools needed for the task, actual independent execution for review, and native vision for visual review.

The scripts handle files, provenance, validation, arithmetic, rendering and artifact gates. Agents handle understanding, discovery, writing, and review. The CLI does not launch agents, select models, or enforce early-stage reviews. The document helper does validate its panel and rewrite budget; finalization checks that loop when present. Legacy audits without a loop remain compatible.

New profile version 3 supports work plus independent projects, research, coursework and activities, with linked source-backed facts; version 2 remains readable and has an explicit history-preserving upgrade. New resume version 2 binds persistent writing rules and supports section ordering. Folder intake uses content hashes to reuse unchanged sources and retain changed originals. The original 0BSD template supports English/Chinese headings and no photo; more layouts, task-specific readiness, standalone discovery adapters and general JD/document migration remain planned. `prepare-resume` still requires all onboarding sections confirmed; existing confirmations carry across jobs.

## Reusable experiences, materials and writing rules

When material is insufficient, the workflow returns to focused multi-turn collection instead of endlessly polishing a thin draft. The host retrieves first, saves questions and actual answers, and updates affected facts/reviews. Content scoring explicitly evaluates experience substance. A valid content `collect_evidence` request mechanically prevents approval (`needs_material`, or `exhausted` at the budget limit); missing reviewers stay `blocked`. Resuming requires changed source context and retains the same round budget. Dialogue/readiness remain host-managed, and declined or unavailable answers leave a clearly limited/pending draft. See [material recovery](references/material-recovery.md).

Tailoring emphasizes concrete contributions, implementation and supported deliverables across complementary experiences. Keep Skills compact and honor the user's section-order choices and requests for more project coverage so stronger project/work evidence receives space. Content reviewers check underused archive material; visual reviewers check the actual allocation and hierarchy. These are host judgments, not automatic depth/area scores or a required project count. The current renderer uses stored skill categories without per-document regrouping. See [experience selection](references/experience-selection.md).

```bash
python3 scripts/intake_folder.py --workspace ~/job-search --folder ~/career-materials --import
python3 scripts/jobbot_skill.py writing-rules --workspace ~/job-search
# Only when extending a legacy v2 profile:
python3 scripts/jobbot_skill.py upgrade-profile --workspace ~/job-search
```

The agent reads pending sources and applies confirmed facts; scanning/importing does not verify ownership or infer personal claims. Use a dedicated materials folder, never managed workspace output directories. Writing rules preserve standing style/disclosure choices separately from search constraints. See [the experience model](references/experience-model.md), [writing rules](references/writing-rules.md) and [scenario evaluations](evals/README.md).

## Start with the agent

Use [SKILL.md](SKILL.md) as the skill entrypoint and choose a workspace outside this source tree. The agent maintains JSON; the user need not edit it. Resolve command paths relative to the installed skill, not the user's workspace. For example, from this repository:

```bash
python3 scripts/jobbot_skill.py init --workspace ~/job-search --country US
python3 scripts/jobbot_skill.py workspace-status --workspace ~/job-search
python3 scripts/jobbot_skill.py --help
```

`--country US` is an example, not a default choice for every user. Keep residence, work authorization, employment-country constraints, and document settings distinct; confirm the latter before drafting. Imported sources and source ownership do not automatically establish every candidate claim.

After intake is collected or reused and a source is selected, acquisition can use `fetch-jd --url URL` or `import-jd --file FILE --source-url LOCATOR`, each with `--workspace`. Imports accept repeatable `--attachment ORIGINAL_FILE` for screenshots/PDFs/API captures; use an honest locator when no URL exists. Then follow the matching, selection and document procedures in the skill.

For a written plan, the rendering/review sequence is:

```bash
JOB_ID=the-job-id
python3 scripts/jobbot_skill.py validate-resume --workspace ~/job-search --job "$JOB_ID"
python3 scripts/jobbot_skill.py render-latex --workspace ~/job-search --job "$JOB_ID"
python3 scripts/jobbot_skill.py render-pdf --workspace ~/job-search --job "$JOB_ID"
python3 scripts/jobbot_skill.py prepare-audit --workspace ~/job-search --job "$JOB_ID"
python3 scripts/document_quality.py --workspace ~/job-search --job "$JOB_ID" \
  --prepare --writer-id ACTUAL_PRIMARY_AGENT_ID
# Host supplies frozen content/images to independent content/visual reviewers.
# Save each role's JSON response at the packet's assigned path.
python3 scripts/document_quality.py --workspace ~/job-search --job "$JOB_ID"
# Follow the outcome. Finalize only after passed:
python3 scripts/jobbot_skill.py finalize-audit --workspace ~/job-search --job "$JOB_ID"
```

The full directory layout and ownership rules live in the [workspace storage contract](references/workspace-storage.md). Candidate data and generated artifacts belong in that external workspace, never this repository.

## Documentation

English is the primary maintained language for runtime instructions, references, schemas and command names. Keep the English/Chinese design and overview aligned; conversation and resume language follow the user's settings.

| Read | Purpose |
| --- | --- |
| [Design](DESIGN.md) / [中文设计](DESIGN_zh.md) | Product decisions, architecture, implemented versus planned work |
| [SKILL.md](SKILL.md) | Agent workflow and references loaded as needed |
| [AGENTS.md](AGENTS.md) | Repository development rules and checks |
| [Storage](references/workspace-storage.md) | Source ownership, layout, freshness and retained versions |
| [Experience model](references/experience-model.md) / [writing rules](references/writing-rules.md) | Typed archive, compatibility, scoped expression and disclosure |
| [Template provenance](references/template-provenance.md) | Original layout and file-specific license handling |
| [Scenario evaluations](evals/README.md) | Fictional cases, preparation versus actual execution/review |
| [Matching](references/job-matching.md) / [workers](references/scoring-workers.md) | Rubric, delegation, concurrency and model policy |
| [Stage reviews](references/stage-review.md) | Independent roles and review packets |
| [Document loop](references/document-quality-loop.md) | Frozen artifacts, scores, feedback and rewrite limits |
| [Model compatibility](references/model-compatibility.md) | Host execution versus model/provider capabilities |

## Development checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/jobbot_skill.py --help
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

The final command uses the installed `skill-creator` validator's actual path. The [scenario suite](evals/README.md) provides reusable fictional cases and evaluation procedures. Save execution reports and generated artifacts in external workspaces; preparation and synthetic bookkeeping tests do not establish real agent or visual review.

## License

Project-authored code and the original resume layout use [0BSD](LICENSE). Externally installed TeX packages/fonts retain their own licenses. See [template provenance and license handling](references/template-provenance.md); no third-party resume template is bundled.
