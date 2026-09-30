# ATS Guidelines (best practices)

Rules used by the `profile-audit` skill (to find improvements in `workspace/profile/`) and the `cv-tailor` skill (when writing CVs). Each rule has an ID so audit findings can cite it.

Priority:
- **P1 — Parsing:** if it fails, the ATS extracts the data wrong (dates, employer, title) or miscalculates years of experience.
- **P2 — Match and impact:** affects the keyword score or how the recruiter reads it after the filter.
- **P3 — Polish:** style, consistency, redundancy.

## 1. Structure and parsing

- **S1 (P1) — Month/year dates.** Format `MMM YYYY – MMM YYYY` or `MMM YYYY – Present` (abbreviated English months: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec). With only the year, many ATSs assume January or miscalculate tenure. Use the same format across the whole profile.
- **S2 (P1) — One employer per entry.** Each experience entry is one employer with its dates. Multiple employers go in separate entries. For a consultancy or freelance work with several clients, the employer is the consultancy and the clients are named in the bullets or in a `Clients: ...` line.
- **S3 (P1) — Concrete employer name.** No generic names like "Client Projects". For freelancers: trade name + `(Self-employed)` or `Independent Consultant`.
- **S4 (P1) — Recognizable job title.** The real title, in its standard market form (the one someone would search for). If the internal title is unusual, the standard equivalent can be added, without inflating it.
- **S5 (P2) — Location per role.** `City, Country` or `Remote (Country)`. ATSs use it in filters. (The current template does not show it per role; it is still kept in the profile for job portals and forms.)
- **S6 (P1) — Sections with standard headings.** Summary, Skills, Professional Experience, Education, Certifications, Languages, Volunteer Experience. (The ATS template already maps them.)
- **S7 (P1) — Full contact details in the body.** Name, `City, Country`, phone with country code, email and LinkedIn URL. No full street address. Never in a header or footer. (`facts.md`)
- **S8 (P1) — Complete education.** Full degree name (not abbreviated), full institution name (acronym in parentheses), location and graduation date (month/year ideally, year acceptable). Degrees in progress get `Expected MMM YYYY`.
- **S9 (P2) — Certifications.** Official name, issuer, date obtained (month/year). If in progress: `In progress — expected MMM YYYY`. Credential ID or URL if there is one.
- **S10 (P2) — Languages with a standard level.** CEFR (A1–C2) or Native. Certificate and year if any.
- **S11 (P3) — Gaps longer than 6 months.** They do not need explaining in the CV, but it is worth knowing about them so dates do not look like a mistake.

## 2. Keywords and skills

- **K1 (P2) — Acronym and full form.** The first occurrence has both: `Retrieval-Augmented Generation (RAG)`, `Natural Language Processing (NLP)`, `Model Context Protocol (MCP)`. The ATS may search for either.
- **K2 (P2) — Canonical names.** Tools are written the way the vendor or the market writes them: `PyTorch`, `scikit-learn`, `Amazon Web Services (AWS)`, `PostgreSQL`. No vague categories when the tool can be named (e.g. "Cloud Infrastructure" → which provider and which services).
- **K3 (P2) — Skills with evidence in context.** Every important skill in the list should also appear in at least one experience or project bullet. Modern ATSs and recruiters weigh usage in context.
- **K4 (P2) — Level and years.** Many forms ask for years of experience per skill. The profile keeps the level and, where possible, years or period (`2022–present`). No bars or scores in the CV.
- **K5 (P3) — Hard skills in the list, soft skills in the bullets.** "Leadership" or "communication" are shown through achievements, not listed on their own.

## 3. Experience bullets

- **B1 (P2) — Action + what + how + result formula.** `<Verb> <what> using <technology/method>, <measurable result>`.
- **B2 (P2) — Quantify.** %, money, time saved, users, volume (docs, requests), number of clients/projects, team size, countries, budget. Without an exact number, an order of magnitude confirmed by the user (`~`, `10+`). **Never invent numbers.**
- **B3 (P2) — Strong action verb first.** Past tense for past roles, present tense for the current one. No pronouns ("I", "my").
- **B4 (P2) — No absolute or unverifiable claims.** Avoid "eliminate", "guarantee", "always", "zero". Use "reduced X by Y" or "minimized".
- **B5 (P3) — No filler or empty adjectives.** Avoid "prestigious", "complex", "overarching", "fostering a culture of", "synergy". The result speaks for itself.
- **B6 (P3) — No duplicates.** Two bullets in the same role do not say the same thing in different words. Merge or differentiate them.
- **B7 (P3) — Length.** 1–2 lines per bullet (≈ 15–35 words). In the CV: 3–6 bullets for recent roles, 2–3 for roles older than 10 years. (The profile's bank can hold more.)
- **B8 (P2) — Scope and context.** The client's/company's industry, size, type of project. Helps domain matching (e.g. "insurance", "energy", "telecom").

## 4. Summary / Executive Profile

- **U1 (P2) — 3–4 lines.** Target title + years of experience + 3–4 specialties with keywords + one achievement or differentiator.
- **U2 (P3) — No first person or clichés** ("passionate", "results-driven", "team player").

## 5. What the audit does NOT do

- It does not invent data, metrics or dates. If the user does not know or does not want to say, it stays as is and is recorded in `workspace/profile/audit.md`.
- It does not change the meaning of an achievement when rewriting it.
- It does not edit the base CV or the base cover letter without approval.
