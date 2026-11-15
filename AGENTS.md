# AGENTS.md

Context for AI coding agents (Claude Code, OpenCode and others) working in this repository.

## What this project is

tailored-cv is a set of agent skills plus a small Node build. The skills tailor a CV and cover letter to a job posting from the user's professional profile, audit that profile for ATS, and debrief interviews. The build turns markdown into ATS-optimized PDFs with headless Chrome/Edge.

**Golden rule: never invent data.** Everything in a CV or cover letter must come from the user's profile (`workspace/profile/`) or from an explicit answer the user gave. When something is missing, ask.

## Skills

The skills live in `.claude/skills/<name>/SKILL.md`. Read the matching file before acting:

| The user wants to… | Skill |
|---|---|
| Tailor a CV or cover letter to a posting, add facts to the profile, update an application status | `cv-tailor` |
| Review or improve the profile for ATS, without a posting | `profile-audit` |
| Record, transcribe, review or prepare for an interview | `interview` |

## Layout

```
.claude/skills/      Skill instructions (markdown)
cv/                  Markdown → PDF build: build-cv.js, build-cover-letter.js, lib.js, design/, i18n.json
docs/                ATS guidelines (ats-guidelines.md) and README images
tools/               Interview recorder and transcriber (Python, run with uv)
examples/            Fictional demo workspace (Alex Morgan)
workspace.example/   Empty template for a user's workspace
workspace/           The user's private data (git-ignored; may be its own private repo)
```

## Commands

Run from `cv/` (after `npm install`):

```sh
npm run cv -- <path/to/cv.md>                      # CV PDF next to the md; fails above 2 pages
npm run cover -- <path/to/letter.md> [cv.md]       # cover letter PDF; fails if it overflows 1 page
```

Chrome/Edge is found automatically on Windows; elsewhere set `CHROME_PATH`.

## Rules

- **Privacy.** Personal data lives only in `workspace/`. Never copy it anywhere else, never commit it to this repo, and never send it to external services beyond the model itself. Use `examples/alex-morgan/` for anything public.
- **Markdown contract.** CV section headings are fixed English keys (see `cv-tailor`); do not translate or rename them. Translated PDF headings come from `cv/i18n.json`.
- **Base files.** Do not edit `workspace/cv-base.md` or `workspace/cover-letter-base.md` unless the user asks. Each application gets its own folder in `workspace/output/<company>-<role>/`.
- **Design.** Keep the layout single-column and text-only (ATS). Do not edit `cv/design/*.css` unless asked.
- **Language.** Talk to the user in their language. The profile is in English; the CV follows the posting's language.
- **Commits.** Only when the user asks. The pre-commit hook (`git config core.hooksPath .githooks`) blocks personal data; never bypass it.
