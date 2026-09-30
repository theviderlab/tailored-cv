---
name: cv-tailor
description: Tailors the base CV and cover letter to a specific job posting (from a link or pasted text) and generates the PDFs. Use when the user asks to adapt, tailor, customize or generate the CV / cover letter for an application, or shares a link to a job offer. Also use to add skills, achievements or facts to the professional profile (workspace/profile/) or to update the status of an application.
---

# CV Tailor

Tailors the CV and cover letter to a specific job offer and produces PDFs ready to send. Golden rule: **never invent data**. Everything in the CV must come from the profile (`workspace/profile/`) or from an explicit answer the user gave in the conversation.

Talk to the user in their own language. Profile content goes in English; the CV and cover letter go in the language of the job posting.

## Sources

- **Profile (source of truth, grows with use):** `workspace/profile/`. See `workspace/profile/README.md` for what goes in each file and its rules.
  - `skills.md`, `experience.md`, `projects.md`, `education.md`, `stories.md`, `facts.md`, `gaps.md`.
- **Base CV (default selection, up to two pages):** `workspace/cv-base.md`. It is the starting point for format, order and tone; its content can be extended or replaced with anything in the profile.
- **Base cover letter:** `workspace/cover-letter-base.md`. Starting point; alternative blocks live in `stories.md`.
- **Application log:** `workspace/applications.md`.
- **ATS best practices:** `docs/ats-guidelines.md`. Apply them when writing or rewriting bullets, the summary and skills (especially B1–B7, K1, K2). The full profile audit is done by the `profile-audit` skill.

Everything personal lives in `workspace/`, which is in the repo's `.gitignore` (the user may version it separately as their own private repo). Never copy user data outside `workspace/`.

### First run (if `workspace/` does not exist)

1. Copy `workspace.example/` to `workspace/`.
2. Ask the user for their current CV (pasted, or the path to an md/pdf) and use it to fill in `workspace/cv-base.md`, following the markdown contract below, and the files in `workspace/profile/` (experience, skills, education, contact details in `facts.md`). Use `source: initial CV (<YYYY-MM-DD>)`.
3. If they have a cover letter, use it as `workspace/cover-letter-base.md`; otherwise draft a short one from the profile and ask them to approve it.
4. Build the base CV (`npm run cv -- ../workspace/cv-base.md` from `cv/`) to check the build works, and suggest running `profile-audit`.

The base CV and base cover letter **are not edited** unless the user asks. The profile and the log **are edited** during the flow, following the rules below. Each application gets its own files (md and pdf) in its own subfolder, `workspace/output/<company>-<role>/`.

## Markdown contract (required for the build to work)

`cv/build-cv.js` maps the markdown onto a single-column, ATS-optimized HTML template. Section headings must match **exactly** (including capitalization and the `&`):

```
# <Full name>
**<Headline>**

- **Location:** <country>
- **Cell:** <phone>
- **Email:** <email>
- **LinkedIn:** [<text>](<url>)
- **GitHub:** [<text>](<url>)

## Executive Profile
<paragraph>

## Core Competencies & Technical Skills
- **<category>:** <skills>
- ...

## Professional Experience
### <Role> — *<Organization>* (<Dates>)
- **<Label>:** <description>
- ...

### <Role 2> — *<Org 2>* (<Dates 2>)
- ...

## Community Leadership & Tech Advocacy
**<Title> | <Community>** (<Frequency>)
- <bullet>
- ...

## Education & Certifications
- **<Degree>** | <institution> (<year>) — <note>
- ...
```

- The contact lines use `- **Key:** value`. LinkedIn/GitHub take a markdown link; Email/Cell/Location have no link.
- Each experience `###` follows exactly `Role — *Org* (Dates)` (separated by an em dash `—`). Dates use `MMM YYYY – MMM YYYY` or `MMM YYYY – Present` when the profile has the months; if it only has the year, use the year.
- Use `**bold**` for each bullet's label (e.g. `**End-to-End AI Leadership:** ...`).

### Language

- The markdown `##` headings are **fixed English keys** in every language: they are never translated. The headings shown in the PDF (and the HTML `lang`) come from `cv/i18n.json` according to the document's language.
- If the document is not in English, start it with front matter giving the language (same for the CV and the cover letter):

  ```
  ---
  lang: es
  ---
  ```

  Without front matter, `en` is assumed. `CV_LANG=<code>` in the environment takes precedence over the front matter.
- Available languages: whatever `cv/i18n.json` defines (currently `en`, `es`). To add one, add its block with **all** the keys from `en`; the build fails if the language does not exist and warns if a key is missing.
- In a CV that is not in English, dates use that language's months (e.g. `Feb 2021 – Actualidad`, `Oct 2013 – Ene 2021`), with the same format throughout the document.

## Cover letter contract (required)

`cv/build-cover-letter.js` parses the letter; the name, headline and contact details are taken **automatically from the base CV** (they are not duplicated in the letter). Format of `workspace/output/<company>-<role>/cover-letter-<company>-<role>.md`:

```
<Salutation>

<Paragraph 1>

<Paragraph 2>

...

Best regards,
<Your name>
```

- Paragraphs are separated by a blank line.
- The **first** paragraph is the salutation (e.g. `Dear Hiring Team,`).
- The **last** block is the closing: its first line is the sign-off (`Best regards,`) and the remaining lines are the signature (name).
- Everything in between is body paragraphs.

## Flow

1. **Read the sources:** all of `workspace/profile/`, the base CV, the base cover letter and `workspace/applications.md` (to detect whether the user already applied to that company).

2. **Get the job posting.** If the user gives a link, use the web fetch tool (`WebFetch` in Claude Code, `webfetch` in OpenCode). If the fetch fails (LinkedIn blocks bots, login walls, JS-only pages), ask them to paste the posting text.

3. **Match the posting against the profile.** Extract the posting's requirements (skills, tools, experience, languages, conditions such as city or work mode) and classify them:
   - **In the profile:** can be used directly.
   - **In `gaps.md`:** not used and not asked about. If it is a core requirement, point it out to the user as a gap.
   - **In the profile with `level: ?` or `evidence: ?`**, and the requirement matters in the posting: ask for the detail (one line is enough).
   - **Not recorded anywhere:** ask.

   Ask **all the questions together in a single message**, short and specific. For example:
   > The posting asks for these things I don't have on record:
   > 1. SQL — do you use it? If so, where or how much? (optional)
   > 2. Kubernetes — do you use it?
   > 3. Hybrid work in Madrid — does that work for you?

   If the structured question tool (`AskUserQuestion`) is available and there are only a few yes/no questions, you may use it.

4. **Update the profile with the answers** (before writing the CV):
   - **Yes** → add or complete the entry in the matching file (`skills.md`, `experience.md`, `facts.md`…) using that file's format and `source: application <company>-<role> (<YYYY-MM-DD>)`. A "yes" without detail is enough: it is saved with `level: ?` / `evidence: ?`.
   - **No** → add it to `gaps.md` with the same source format.
   - If the user shares a new achievement, metric or anecdote, save it too (`experience.md` or `stories.md`), even if it is not used in this application.
   - If an answer contradicts something in the profile, update the existing entry (do not duplicate it) and tell the user.
   - Show the user a one-line summary per profile change.

5. **Propose adaptations** of the CV and cover letter for that posting:
   - Start from the base CV and replace or add profile content that fits the offer better (skills, bullets from `experience.md`, blocks from `stories.md`).
   - Reorder or rewrite bullets to prioritize what the offer asks for.
   - Adjust the summary/headline to the role and company.
   - Use ONLY information from the profile or the conversation. If something is missing, ask.
   - Write following `docs/ats-guidelines.md`: acronym and full form on first use, the posting's keywords in the same form the posting uses, no absolute claims, and metrics only if they are in the profile.
   - Keep the CV's two-page limit in mind: adding something usually means removing something else.

6. **Write the new files** in the application's own subfolder, `workspace/output/<company>-<role>/` (do not touch the base files; create the folder if it does not exist). Never write loose files at the root of `workspace/output/`:
   - `workspace/output/<company>-<role>/cv-<company>-<role>.md`
   - `workspace/output/<company>-<role>/cover-letter-<company>-<role>.md`
   - (company and role as slugs: lowercase, no spaces or accents, separated by `-`. File names keep the slug so the PDFs remain identifiable when sent.)
   - If the folder already exists (same company and role), ask the user whether to overwrite or use a suffix (e.g. `-2`).

7. **Verify before building.** Compare the new file against the base CV and produce a short report:
   - List each substantive change (phrase, fact, number, link, name).
   - For each new fact, state its source (profile file or the user's answer in this conversation).
   - Explicitly flag anything that cannot be traced to the profile or the conversation. If there is anything like that, fix it or ask.
   - Quick ATS check: key acronyms with their full form, the posting's core keywords present in skills and in at least one bullet, consistent date format.

8. **Build the PDFs once the user approves.** When the user confirms, run from `cv/`:

   ```
   npm run cv -- ../workspace/output/<company>-<role>/cv-<company>-<role>.md
   npm run cover -- ../workspace/output/<company>-<role>/cover-letter-<company>-<role>.md
   ```

   If the application is not in English, pass the tailored CV as the second argument to `npm run cover` so the letter's header uses its headline (in the letter's language) instead of the base CV's:

   ```
   npm run cover -- ../workspace/output/<company>-<role>/cover-letter-<company>-<role>.md ../workspace/output/<company>-<role>/cv-<company>-<role>.md
   ```

   Each PDF is created next to its `.md`, inside the application's subfolder. If the CV goes over 2 pages or the letter reports overflow, trim that text and rebuild. Experience blocks are not split across pages: if the first role does not fit on page 1, it jumps whole to page 2 and the CV can reach 3 pages even with space left over. In that case, shorten the summary, the skills or the first role's bullets.

9. **Log the application** in `workspace/applications.md`: add a row at the top with date, company, role, folder, posting link (if any), status `sent` (or `?` if the user has not confirmed sending it) and short notes (e.g. language).

10. **Suggest base CV improvements (optional).** If the log shows something was added in 3 or more recent applications (e.g. SQL or LangChain), or that a base bullet is always removed, suggest in one line that the user update the base CV. Do not edit it without their approval.

## Other uses

- **"Add X to my profile" / "I now know X":** update the matching profile file with `source: conversation (<date>)`, without building a CV.
- **"Update the application status to X":** edit the row in `workspace/applications.md`.
- **"Review / audit / improve my profile for ATS"** (no posting): not this skill's job, use `profile-audit`.
- If step 3 surfaces weak data the posting does not ask about (dates without months, bullets without metrics), do not ask about it now: suggest running `profile-audit` in one line.

## Build notes

- Requires Node (`markdown-it` dependency) and Chrome/Edge installed. Run `npm install` in `cv/` the first time.
- `npm run cv` generates **one ATS-optimized PDF**, `<name>.pdf`, next to the markdown (single column; template `cv/design/template.html` + `style.css`). It uses standard ATS headings in the document's language (defined in `cv/i18n.json`; in English: Summary, Skills, Professional Experience, Education & Certifications, Volunteer Experience) without changing the markdown contract. See "Language".
- **The CV can be up to 2 pages.** If it goes over 2, the build **exits with code 1**: shorten the markdown (trim bullets or rewrite the summary) until it builds cleanly, before delivering the PDF.
- The cover letter build (`npm run cover`) takes its identity from `workspace/cv-base.md`; this can be overridden with `CV_BASE=...` or a second argument.
- If the user wants to inspect the intermediate HTML: `CV_KEEP_HTML=1 npm run cv -- <md>` keeps `cv/design/.tmp_cv.html` (or `.tmp_cover.html` for the letter).
- Styles live in `cv/design/style.css` (CV) and `cv/design/style-cover-letter.css`; do not edit the CSS unless the user asks.
