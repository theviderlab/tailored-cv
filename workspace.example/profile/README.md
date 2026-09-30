# Professional profile (source of truth)

This folder holds **everything** you know and have done. It grows with use: whenever the `cv-tailor` skill asks about something that was not on record and the answer is confirmed, it is added here.

The base CV (`workspace/cv-base.md`) is just **a selection of up to two pages** from this profile. The profile can hold much more than fits in a CV.

| File | What it contains |
|---|---|
| `skills.md` | Technical and management skills, with level and evidence |
| `experience.md` | Achievement bank per role (more bullets than fit in a CV) |
| `projects.md` | Projects, talks, community |
| `education.md` | Degrees, certifications, languages |
| `stories.md` | Reusable anecdotes and arguments for cover letters |
| `facts.md` | Practical data: contact, location, availability, form answers |
| `gaps.md` | What you confirmed you do **not** know or do not want to highlight (so it is not asked again) |
| `audit.md` | ATS audit state (`profile-audit` skill): pending, resolved and dismissed |

The ATS best practices applied to this profile are in `docs/ats-guidelines.md`.

## Rules

- **Nothing goes in without confirmation.** Every new fact comes from an explicit answer by the user.
- **Every new entry records its source**: `source: <application or conversation> (<YYYY-MM-DD>)`.
- Content is in English (the CV's language).
- If a fact changes (e.g. a skill's level goes up), the existing entry is updated, not duplicated.
- If something in `gaps.md` becomes true, it moves to `skills.md`.
- Dates use the `MMM YYYY – MMM YYYY` format (or `– Present`). If only the year is known, the year stays until the audit completes it.
