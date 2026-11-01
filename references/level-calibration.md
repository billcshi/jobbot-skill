# Calibrate evidence strength to the target role

Use for matching, selection and content review. The bar is the target job's expected work, not the candidate's age, school, current title or self-described seniority. The same clear account may be strong for an entry role and insufficient for a role requiring independent service ownership. Accuracy, provenance and readability never receive a lower standard for junior candidates.

## Establish the actual expectation

Read the JD responsibilities and required/preferred qualifications. Use an employer's supplied or actually inspected level definition when available, with its source/date; do not infer a universal company ladder from SDE1, SDE2, Senior or Staff titles. Years requirements remain explicit job facts, but years alone do not establish scope or independence. Mixed/unclear descriptions stay uncertain rather than defaulting to the easiest or hardest bar.

These are internal starting anchors, not assertions about every employer's leveling system. Apply expectations supported by the target and adjust for role type, such as product backend, research or tooling:

| Target scope | Evidence that can make a strong case | What is insufficient for that scope |
| --- | --- | --- |
| Entry / SDE1-like | Concrete bounded work; personal implementation, debugging, tests and learning from feedback; clear contribution within a team | Tool lists or coursework labels without understandable personal action or checked behavior |
| Independent contributor / SDE2-like | Ownership of a feature/component beyond assigned coding: understanding the problem, justified choices, failure handling, validation and coordinated delivery; operation/maintenance where required | Detailed implementation tasks without evidence of the independence, decisions or lifecycle responsibility requested by the JD |
| Senior-like | Resolving consequential ambiguity, boundaries, alternatives/tradeoffs, reliability/change risks and sustained outcomes; technical guidance or cross-team work when requested | Rebranding bounded implementation as architecture/leadership, or listing scale without personal decisions and consequences |
| Staff / broader technical leadership | Decisions and influence across the employer's specified scope, such as multiple teams/systems, long-term evolution, adoption of technical direction and durable impact | A title, team size or people-management claim without the relevant technical scope and influence |

Coursework, research, volunteering and personal projects can demonstrate applicable decisions and ownership at any level. Context still matters: a thoughtful local tool can show design reasoning without proving production service ownership. Do not require enterprise scale, people management, on-call work or business percentages unless the target requires the corresponding work. Prefer strong grounded examples over more bullets.

## Persist and apply one consistent bar

Scorers derive target scope independently from the supplied JD and describe it in existing `experience_level` and relevant `role_alignment` reasons with source locators. Keep the match schema, weights and A–D tiers; prominent level gaps must remain visible even if location/skills produce a high average. Do not turn every gap into an invented hard eligibility constraint or score an unknown as zero.

Before drafting, record `target_level` in agent-maintained `jobs/<job-id>/selection.json`: original employer title/label, interpreted scope, source locations/JD hash, confidence or ambiguity, and core evidence expectations. This is a host convention, not a new validated schema or automatic classifier. `selection.json`, when present before preparation, is already frozen by the document helper. Reviewers verify its interpretation against the JD; it is task context, not the producer's desired verdict. If absent in legacy material, derive scope from the frozen JD and disclose uncertainty.

Apply scope to the existing content dimensions, particularly relevance/coverage (25) and experience substance (35). A 31–35 substance score requires concrete evidence at the target's required scope and independence. Detailed junior implementation is not automatically excellent evidence for a senior requirement. A 90+ content score still needs at least 30/35 substance and must not conceal an unmet core level expectation. State the target interpretation and supporting/limiting evidence in the review summary. Scores from different targets are not comparable without their level context.

Keep numerical panel thresholds, weights and total round budget unchanged unless explicitly configured before review. The higher bar comes from the evidence needed to earn the score; automatic SDE1/SDE2-specific cutoffs are not implemented. Do not lower the interpretation after failure to obtain a pass. A genuine user-requested target change or source correction needs recorded context changes and refreshed affected matching/reviews, preserving document history and budgets.

## Route the gap correctly

- **Underwritten evidence:** the archive shows the needed decisions/ownership. Retrieve and rewrite; do not re-interview.
- **Unknown relevant experience:** an existing contribution remains unexplained. Ask a neutral, bounded question under [material recovery](material-recovery.md), such as “Which decisions were yours, which were set by others, and what happened after delivery?” A substantive missing-material issue can return `collect_evidence`.
- **Confirmed scope gap:** the candidate explicitly did not perform the requested work. Record it in matching and the content review as `level_fit`; do not repeatedly collect the same nonexistent experience. Explain that wording cannot close it and retain an honestly limited/stretch draft if requested. Do not launch pointless rewrites merely because a failed numeric gate says `rewrite`; preserve the outcome and stop when no truthful improvement is available. Discuss a narrower target only if useful, never silently substitute it.

A known target mismatch is not a judgment of the person and is not itself poor factual writing, but can limit this document's strength for this target. A document audit pass never certifies eligibility or erases match gaps. The helper does not interpret `level_fit`, compute level-dependent subscores or automatically stop futile collection; those decisions and disclosure remain host responsibilities.
