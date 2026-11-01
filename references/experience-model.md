# Reusable experience model

The skill serves working professionals and students. Collect all genuine work, projects, research, coursework, open-source/community and volunteer experience before choosing what belongs on a particular resume.

New workspaces use profile version 3. Version 2 remains readable without silent migration; `upgrade-profile --workspace WORKSPACE` explicitly adds empty new collections, retains the original under `history/profile.json/`, and changes profile bindings. It does not reinterpret old text or invent new facts.

| Profile collection | Entry heading/identity | Resume reference |
| --- | --- | --- |
| `experience` | Existing employer, title, location, dates | `profile_experience_id` |
| `projects` | Name, optional organization/role/location, dates | `profile_project_id` |
| `research` | Name, optional organization/role/location, dates | `profile_research_id` |
| `coursework` | Course name, optional institution/role/location, dates | `profile_course_id` |
| `activities` | Name, optional organization/role/location, dates | `profile_activity_id` |

Each entry has a stable `id`, source IDs and `bullets`: individually identified stored facts with text and source IDs, not necessarily polished resume bullets. Non-employment entries require `name`, `start`, `end`, `source_ids`, `bullets`; unknown dates may be empty strings, not invented dates. Employment keeps the existing employer/title contract. Education and skills retain their own records. IDs are unique across entries and their facts. Optional `related_ids` reference other real profile IDs: a course can link to its project, and a project to a skill or research entry. Do not turn group membership into personal contribution.

Example, only when the user supplied these facts:

```json
{
  "id": "project.sensor",
  "name": "Sensor Logger",
  "organization": "Embedded Systems course",
  "start": "2025",
  "end": "2025",
  "related_ids": ["course.embedded"],
  "source_ids": ["user-confirmed"],
  "bullets": [{"id": "project.sensor.serial", "text": "Implemented serial data collection and debugged timing errors.", "source_ids": ["user-confirmed"]}]
}
```

Keep source locations and confirmation context in reading/run notes. Related facts, detailed context and alternate expressions remain available even when omitted from a resume. `summary_facts` is still useful for cross-experience facts; it is no longer the required workaround for projects/courses/research.

New resume plans use version 2, with all four new collections and a nullable `writing_rules_sha256`. Each selected non-employment claim cites its own entry or at least one of that entry's stored facts; additional supporting IDs may be included. Headings and dates come from the referenced profile record, not free text copied from a JD. Legacy resume version 1 remains readable.

`section_order` may reorder all eight supported sections exactly once; empty sections are not printed. Professionals can lead with work and substantial projects; students/researchers can lead with education, projects or research. The agent chooses based on the purpose and confirmed presentation, without requiring a different profile or fixed number of experiences.
