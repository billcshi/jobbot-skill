# Select and compose multiple experiences from the archive

Use during tailoring, after presenting the reviewed job-match assessment. This stage reuses the detailed archive collected earlier. Its default is retrieval, selection, archive-based deepening, and composition, not another interview. Filter for relevant complementary experiences first, then deepen those entries from stored facts and sources. Only genuinely needed user input triggers a focused follow-up.

## Build an experience portfolio for this job

Read the full profile/source index and current notes first. Retrieve the stored details of promising work, project, research, course, and other experiences before asking the user anything. Read source files when the answer can be recovered there. Previously confirmed facts remain usable without reconfirmation.

Map the JD's important responsibilities and requirements to multiple candidate experiences. Reference the actual JD text/field and the current snapshot hash; do not invent requirement IDs or treat every keyword as a hard requirement. An experience can cover several requirements, and a requirement can be supported by several experiences. Consider transferable evidence as well as exact tools.

Compose a complementary set of experiences rather than choosing only the single closest project or repeating one example throughout the resume. Consider each experience's contribution to relevance, depth, ownership, collaboration, problem solving, and chronology. Give the strongest examples more space; use others to add different useful capabilities. Keep normal chronology within dated sections and choose section emphasis for the document's purpose.

Use multiple genuine experiences when the archive supports them. Do not invent positions, split one project into fictitious separate jobs, or enforce a fixed number if the user has fewer entries. Lack of paid work does not make coursework, research, or personal projects inferior evidence.

For example, an API role might be supported by one project showing API/data design, another showing testing and debugging, and a research or collaborative experience showing analysis and communication. Select this combination only when these facts exist in the archive; the example is not a writing template.

Use [level calibration](level-calibration.md) before assigning emphasis: an entry-level account of implementation is not automatically enough for a target requiring independent design and delivery. Retrieve examples at the target scope and preserve their actual ownership boundaries.

## Record a selection plan

Maintain `jobs/<job-id>/selection.json` as an agent-written tailoring note with:

- profile, preferences, JD, and market hashes; the reviewed match-report path;
- `target_level` with the employer label, interpreted scope, JD/source locators and hash, confidence/ambiguity and core evidence expectations;
- selected experience/fact IDs, their source locations, and the stored details to use for each entry;
- the JD requirements each entry helps address, why it adds value to the set, intended section/order, and relative space or emphasis; identify distinct initiatives within a role without creating new employment records;
- relevant alternatives omitted from this draft and the selection reason;
- unresolved material conflicts and any genuinely necessary user question.

This is a local file convention, not a CLI-validated selection schema. Keep the complete archive intact; only the generated document is selective. Do not store new unsupported facts in a selection note or treat it as candidate evidence.

## Ask only when the archive cannot resolve a necessary issue

Do not start with a fresh project questionnaire. Retrieve existing details first; then ask when missing or contradictory material prevents a convincing, specific account of the main contribution. A truthful but generic alternative does not remove the need for useful clarification. Follow [material recovery](material-recovery.md) for a bounded multi-turn exchange, actual replies, history and resumption. Ask about the missing problem, action, design or validation rather than demanding optional percentages or another full interview.

One narrow exception is user-requested quantitative deepening or confirming a specific newly proposed quantitative statement. In that case, a focused exchange about its meaning/basis is appropriate even when a nonnumeric alternative exists. Follow quantified-claims.md, retrieve existing details first, and allow an immediate skip/nonnumeric fallback. Do not manufacture proposals merely to make every experience trigger another question.

If the user declines or cannot answer, retain the uncertainty and offer supported content as a limited draft when substantive gaps remain. Do not ask the same question again for another job without new reason. Never lead the user toward an invented metric or contribution. A necessary correction/new fact goes back into the reusable profile with its source, not only into the current resume. A short but genuinely sufficient account can proceed normally; sparse material is not automatically sufficient merely because every sentence is true.

Profile changes invalidate existing prepared resume hashes. Save and validate the update first, refresh any affected match assessment/reviews, then prepare the resume plan from the current profile. Review only the affected archive changes; do not restart onboarding.

## Draft and review

### Make the work understandable

For each selected substantial experience, retrieve its problem or purpose, personal contribution, implementation or design choices, and supported outcome or deliverable. Use these as retrieval lenses, not mandatory fields or a questionnaire. A working artifact, tested behavior, class demonstration, or documented workflow can be a meaningful result without a business metric. If central evidence remains too thin after retrieval, record `needs_material` in the selection note and follow material recovery before the first PDF. Do not fill gaps or automatically deliver a shorter generic entry as finished work.

Organize related facts around recognizable work. An inventory API, an ingestion worker, and a reporting automation can be distinct initiatives under one real employer when the archive establishes that relationship. Connect the task, implementation and outcome across concise bullets; do not flatten everything into isolated tool mentions or imply that unrelated facts belong to the same system. Retain the actual employer/title/dates and do not duplicate the same work in a separate Projects section to increase the entry count.

Give a substantial project enough room to explain different contributions when supported. For example, a source-backed scheduling implementation and its tests may deserve separate bullets if each adds useful detail; merely splitting one short fact does not add depth. Compare omitted projects with the weakest included material, and include another project only when it contributes distinct relevant evidence. For experienced candidates, projects within employment count as substantive project work; a personal Projects section is optional. For students, course/research/personal work can carry the main narrative. No universal project or bullet quota applies.

Treat a user's request for more project coverage as an explicit composition preference. Revisit the archive and reclaim weaker summary, skill or routine-duty text for useful project details before dismissing them as optional. Shared technologies alone do not make two experiences redundant: compare their purpose, individual responsibility and deliverables. If the requested expansion is unsupported, explain the specific evidence limit rather than repeating a bullet or inventing another project.

Use active, specific sentences that link the person's action to the actual artifact or behavior. Put the strongest relevant contribution early within each entry while retaining chronology between entries. Keep source locators, confirmation history, and detailed estimation methodology in the evidence records. Preserve material qualifications such as approximate values, team ownership, or prototype context in concise wording; do not repeat defensive disclaimers about absent production users or teammates' work when a truthful heading and precise contribution already establish scope. Do not turn a prototype into a production service by removing necessary context.

### Allocate space to evidence

Decide section order and relative space deliberately in `selection.json`, honoring explicit user instructions. Experience and project substance should normally carry the main narrative; Skills is a compact index of selected relevant capabilities, not a second inventory of the archive. Prefer a few short lines where practical, shorten a repetitive summary, and remove low-value repetition before cutting useful project detail. This is an editorial starting point, not a fixed line/percentage/page-filling gate. More words, more entries, smaller fonts, or invented metrics do not by themselves improve a resume.

Place Education where its relevance and the user's preference warrant it; a requested Education/Skills swap should be implemented in `section_order`, not merely acknowledged. Students may benefit from Education near the top; substantial recent employment may lead for professionals. Do not impose one ordering on all candidates. The current renderer emits one line per selected profile skill category: choose a concise supported skill subset and inspect the actual result. It has no per-document category regrouping control; do not mutate canonical skill categories for one layout, hand-edit generated TeX, or claim that regrouping was performed when it was not.

Before rendering, compare the draft with selected and omitted archive details: what useful action, implementation, deliverable, or complementary project was lost, and what lower-value text could make room for it? Persist the answer and any genuine information/layout limits in the selection note. The content reviewer checks this evidence use; the visual reviewer checks the resulting space and hierarchy. These are host judgments, not automatic CLI checks.

For competitive rewording and optional quantitative proposals, read [quantified-claims.md](quantified-claims.md). Distinguish source-supported measurements/calculations, the user's own approximate estimates, and explicitly hypothetical drafting scenarios. Confirm the meaning/basis of newly proposed quantification before using it as a fact; do not require optional metrics or manipulate digits to make an unsupported number look more plausible.

Use stored details to write specific, competitive bullets, varying emphasis by job without changing the underlying contribution. Keep skills and claims linked to current profile evidence IDs. Missing business metrics need not stop drafting; scope, design choices, implementation, and deliverables can communicate value. Do not trim confirmed facts out of the archive merely to fit page length.

The hiring-perspective reviewer receives the selection note, full archive index and relevant alternatives, JD, match assessment, and resume plan. Review the experience set and coverage as well as individual sentences: an accurate bullet is insufficient if the document overlooks stronger stored experiences or repeats one narrow example unnecessarily. Check that extra user questions were actually necessary, not a substitute for reading the archive.

Use [experience-model.md](experience-model.md) for the implemented typed work, project/research/course/activity collections and resume references. All can be selected and rendered without fictitious employment. Load applicable [writing rules](writing-rules.md) before selection; excluded facts and entries stay in the archive and cannot be used through a different citation. New plans bind the current rule-file hash and can reorder supported sections.
