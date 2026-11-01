# Persistent, user-confirmed writing rules

Read before drafting/revising, including when reusing an archive. These rules control expression and disclosure, separately from search preferences and facts.

Record an already supplied standing instruction; do not ask the user to approve it again. Explain ambiguities only when they materially affect the document.

```bash
python3 "$SKILL_DIR/scripts/jobbot_skill.py" set-writing-rule \
  --workspace "$WORKSPACE" --id private-project \
  --instruction "Retain this project in my archive but omit it from resumes." \
  --exclude project.private --confirmation "$USER_STATEMENT"
python3 "$SKILL_DIR/scripts/jobbot_skill.py" writing-rules \
  --workspace "$WORKSPACE" --job "$JOB_ID"
```

`writing-rules.json` stores scope (`workspace`, `market`, `job`), target (null, two-letter country, or job ID), instruction, optional repeated `--forbid` phrases and `--exclude` profile evidence IDs, confirmation text/time, and active/retired status. Market scope follows the document's target country, not residence. Use `--scope market --target US` or `--scope job --target JOB_ID` as needed. Retire a rule with the same ID, `--retire`, and a confirmation. Updates/retirement retain previous bytes under `history/writing-rules.json/`.

The agent applies all effective instructions. Scripts enforce explicit forbidden phrases in emitted fields and excluded evidence references; excluding an entry also excludes its stored child facts. Word boundaries prevent a ban on `AI` from matching `maintained`. Free-form style instructions need semantic review; the CLI does not understand every instruction or prove a paraphrase is faithful. Do not use these rules to justify unsupported candidate claims.

Keep excluded/private facts in the archive, outside generated documents. Do not remove dates, employers or facts from the archive merely to satisfy a style rule. Do not put excluded information into user-facing explanations unnecessarily. A draft must not paraphrase an excluded fact and cite another ID to bypass it.

New plans bind the actual writing-rule file hash (or null when absent). A file change requires refreshing the plan and affected review; even unrelated rule edits conservatively stale that binding. Check settings again before rendering. Do not silently rewrite historically delivered PDFs or reset quality-loop budgets. The render manifest and document-review packet retain applicable rule inputs.
