# Agent scenario evaluations

These are fictional, offline cases for behavior testing. They are not candidate records or evidence of hiring success. Keep every executed case, generated artifact and report in a new external evaluation workspace.

Use the scoped [experience writing and review probes](experience-depth.md) to test archive-based depth, section emphasis, explicit ordering and review calibration without conflating a prompt evaluation with a new production document approval.

Use [multi-turn material recovery](material-recovery.md) for actual executor/candidate message exchanges, adaptive questions, source integration and preserved document budgets. Fully prepared materials and one-shot drafts alone do not test this loop.

```bash
python3 scripts/prepare_scenario.py --workspace /tmp/jobbot-eval-unique/experienced --case experienced
```

Supported cases: `experienced`, `student`, `returning`, `correction`. Preparation never resets a populated workspace. It creates raw materials and a realistic `request.md`; returning/correction also seed an existing confirmed archive. Preparation is not execution, review, or a passed evaluation.

Give a fresh agent only the skill location and that request/material workspace. Use real host tools and identities; record unavailable capabilities honestly. Keep worker outputs, relevant user answers, state, and review reports on disk. An intake-only request stops at the independent intake-review handoff; it does not need a fabricated JD or generated resume to count as useful progress.

Have a separate reviewer inspect sources and actual outputs, then record a verdict, concrete findings, input/output hashes, execution IDs and scope in `evaluation-report.json`. Follow stage-specific review prompts when approving a product stage. Behavioral eval criteria belong to the reviewer, not an answer key supplied to the producer:

| Case | Review the observable behavior |
| --- | --- |
| experienced | Work plus non-work history retained; no metrics/authorization/relocation thresholds invented; persistent wording/exclusion rules kept distinct from search preferences; no repeated answered questions |
| student | Courses, projects, research and activities kept as real independent records; personal contribution distinguished from teammates; course/project relationships retained; no fabricated employer or required metric |
| returning | Existing facts/settings reused; no-change check-in does not rewrite profile or restart onboarding; selection uses the archive and supplied JD; freshness/independent review limits visible |
| correction | Corrected task/units/approximate basis preserved; if calculated, 20 to 12 minutes is about 40% less time, not 40% more throughput; obsolete fact/history retained distinctly; affected bindings refreshed without overwriting historical delivered documents |

For document scenarios, also exercise real rendering and native inspection of all pages. Preserve distinct writer/content/visual identities; if review is unavailable the artifact remains pending. Unit tests use synthetic report/image bytes for bookkeeping and do not establish actual model/visual review.

Automated integration checks in `tests/test_experience_workflow.py` and `tests/test_intake_folder.py` cover structural provenance, actual EN/ZH PDF text extraction where tools exist, rules, compatibility, and hash-based incremental imports. The model scenarios add observable conversation/retrieval judgment; do not treat passing unit tests as passing all agent cases.
