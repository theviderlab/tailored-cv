---
name: profile-audit
description: Audits the professional profile (workspace/profile/) against ATS best practices, finds improvements (dates without months, ambiguous employers, bullets without metrics, acronyms without their full form, duplicates, missing data) and asks the user the questions needed to fill them in. Use when the user asks to review, audit, improve or polish their profile, their source of truth or their CV for ATS, without a specific job posting. To tailor the CV to a posting, use cv-tailor.
---

# Profile Audit

Reviews the whole source of truth (`workspace/profile/`) against `docs/ats-guidelines.md`, finds improvements and resolves them by asking the user. Golden rule (same as `cv-tailor`): **never invent data**. A date, metric, client or level only goes in if the user confirms it.

## Sources

- **Rules:** `docs/ats-guidelines.md`. Every finding cites a rule ID (S1, K1, B2…) and its priority (P1/P2/P3).
- **Profile:** all of `workspace/profile/` (see `workspace/profile/README.md` for each file's rules).
- **Audit state:** `workspace/profile/audit.md`. What is pending, resolved and dismissed from previous audits. **Read it first**: never ask again about anything dismissed or resolved.
- **Base CV:** `workspace/cv-base.md`. Only for the final suggestion (step 7).

If `workspace/` does not exist, follow the "First run" step of `cv-tailor` before auditing.

## Modes

- **Full** (default): the whole profile.
- **Focused:** if the user narrows it down ("only experience", "only dates", "only skills"), audit just that.
- **Continue:** if `audit.md` has pending items and the user says "let's continue" or similar, pick up from there without re-analyzing everything.

## Flow

1. **Read** `ats-guidelines.md`, `audit.md` and all of `workspace/profile/`.

2. **Detect findings.** Go through each file and apply the rules. At minimum:
   - `experience.md`: S1 dates, S2 one employer per entry, S3 concrete employer, S4 job title, S5 location, B1–B8 on every bullet (metrics, verbs, absolutes, filler, duplicates, industry context), K1 acronyms, K3 listed skills that do not appear in any bullet. Also any "To be completed" notes.
   - `education.md`: S8 (full degree name, full institution name, location, dates), S9 certifications (issuer, month/year, in progress or completed), S10 languages.
   - `skills.md`: K2 canonical names and vague categories, K4 `level: ?` and `evidence: ?`, K1 acronyms, K5 standalone soft skills.
   - `projects.md`: dates, role, stack, measurable result, link, B4.
   - `facts.md`: S7 complete contact details (city, country, phone with country code).
   - Cross-file consistency: the same date, title or company name written differently in two places.

   Each finding has a **type**:
   - **Data:** information only the user knows is missing → **question** (e.g. start and end months).
   - **Decision:** there is more than one valid way to structure it → **options** (e.g. split employers or group them under a consultancy).
   - **Wording:** it can be improved with what is already in the profile → **before/after proposal** (e.g. add an acronym's full form, remove "eliminate", merge duplicates). If improving it needs a fact (a metric), it is a **Data** finding first.

3. **Show the summary** before asking: number of findings by priority and by file, and the 3–5 most important ones in one line each. Save the full list in `audit.md` as pending (see format below).

4. **Ask in batches**, from highest to lowest priority (P1 → P2 → P3):
   - Batches of 5 to 8 questions, grouped by entry (e.g. everything about one role together).
   - Short, specific, numbered questions that can be answered in one line. Make clear that "don't know" or "skip" is a valid answer.
     > **Acme Corp (2013 – 2021)**
     > 1. Start and end month? (S1)
     > 2. How many people were on the team, or how many clients/points of sale? (B2)
     > 3. City and country? (S5)
   - For **Decisions** with closed options, use `AskUserQuestion` if available.
   - **Wording** findings go in a separate batch, as a before/after table with the rule ID. The user approves, rejects or edits each one.
   - After each batch, apply the changes (step 5) and ask whether to continue with the next one.

5. **Apply the changes** to the profile:
   - Edit the existing entry, do not duplicate it. Respect each file's format.
   - New data: add `source: ATS audit (<YYYY-MM-DD>)`. If the entry already had a `source:`, keep it and add the new one next to it.
   - Approved rewrites: replace the text and add `revised: ATS audit (<YYYY-MM-DD>)` on the bullet's source line.
   - Splitting or renaming employers: keep all bullets, redistributed according to the user's answer.
   - A metric the user gives approximately is saved approximately (`~30%`, `10+ clients`), never rounded up.
   - "Don't know" or "rather not" → the finding moves to **Dismissed** in `audit.md` with the reason, so it is not asked again.
   - If the user mentions a new achievement, fact or anecdote, save it too (`experience.md`, `stories.md`, `facts.md`).
   - Show a one-line summary per change.

6. **Update `audit.md`**: move what was applied to Resolved, what was rejected to Dismissed, and leave the rest as Pending with the date of the latest session.

7. **Suggest changes to the base CV** (at the end of the session, or when the user stops): list which profile improvements are worth carrying over to `workspace/cv-base.md` (dates with months, corrected employers, rewritten bullets). **Do not edit it without approval.** If approved, edit it following `cv-tailor`'s markdown contract and verify with the build from `cv/`:
   ```
   npm run cv -- ../workspace/cv-base.md
   ```
   The CV must fit in two pages at most. If it goes over, trim and rebuild. (The PDFs are written next to the md in `workspace/`; let the user know.)

## `workspace/profile/audit.md` format

```
## Pending
- [finding-ID] <file> · <entry> · <rule> (<priority>) · <type> — <what is missing or what to improve>

## Resolved
- [finding-ID] <file> · <entry> · <rule> — <what was done> · <YYYY-MM-DD>

## Dismissed
- [finding-ID] <file> · <entry> · <rule> — <reason: doesn't know / rather not / not applicable> · <YYYY-MM-DD>
```

The finding ID is a sequential number (`A1`, `A2`…). IDs are never reused.

## Rules

- Profile content is in English; questions to the user go in the user's language.
- Do not edit the base CV or the base cover letter without explicit approval.
- A rewrite may not change the meaning of an achievement or add scope the user did not confirm.
- If a new practice comes up while updating the ATS rules, propose it as a change to `docs/ats-guidelines.md`; do not apply it silently.
