# Question bank format

The question bank is a living record of the questions the user was **actually** asked across all their interviews, grouped by what each question tests, with how they answered each time and the best answer so far. Its value is preparing the *next* interview, for any company: interviewers repeat the same handful of questions with different wording.

It lives in `workspace/interview-bank/` (git-ignored) and is written in the user's language. Quotes of how a question was asked stay in the interview's language.

## Files

```
workspace/interview-bank/
├── index.md        one row per question group: what /interview prep reads first
├── experience.md   questions about the candidate: background, projects, motivation, behavioral
└── technical.md    questions about knowledge: concepts, system design, hypotheticals, coding
```

- Inside each file, groups sit under `## <theme>` headings. **Themes are not predefined:** they emerge from the user's interviews (e.g. a data engineer's bank grows "Spark" and "data modeling"; an AI engineer's grows "agents" and "RAG"). Reuse an existing theme when it fits; create a new one only when nothing does.
- When a file passes ~600 lines, split it by theme (`technical-<theme>.md`, `experience-<theme>.md`) and update the `File` column of the index. Repeated questions merge into existing groups, so growth should be slow.

## Index (`index.md`)

```markdown
# Question bank

<one paragraph: what this is, maintained by the interview skill>

| ID | Question | File | Type | Stages | JD signals | Asked | Last | Status |
|---|---|---|---|---|---|---|---|---|
| T-003 | How do agents share state without overflowing the context? | technical.md | design | technical | multi-agent, orchestration, context | 1 | ⚠️ 2026-11-13 | fair |

## Interviews included

| Date | Company / role | Stage | Source |
|---|---|---|---|
```

- **ID:** `E-nnn` for experience, `T-nnn` for technical. Stable: never renumber, even after moving a group to another file.
- **Interviews included** lists every interview already merged, so none is processed twice.

## Question group (in `experience.md` / `technical.md`)

```markdown
### T-003 · How do agents share state without overflowing the context?

- **Type:** design · **Stages:** technical · **JD signals:** multi-agent, orchestration, LangGraph, context engineering
- **Status:** fair (last ⚠️ 2026-11-13) · **Asked:** 1×
- **How it was asked:**
  - "<quote or close paraphrase, in the interview's language>" (<company>, <YYYY-MM-DD>)
- **History** (newest first):
  - <YYYY-MM-DD> · <company> · <stage> · ⚠️ · <one line: what was good, what was missing> · [review](<relative path to review.md>)
- **Best answer (~30 s):**
  > "<answer ready to say, in the user's voice>"
- **Key points:** <what any good answer must touch; short concept explanations when the user may lack them>
- **My examples:** <profile facts and projects that anchor the answer>
- **Honesty:** <what must not be claimed, how to frame a gap; omit if nothing applies>
```

### Fields

- **Type:** `concept` (what is X, X vs Y), `design` (how would you build / scale / fix…), `experience` (tell me about a time / a project…), `coding` (live exercise), `motivation` (why this role, why leave…), `screening` (availability, notice, location), `closing` ("any questions for us?"). Salary and logistics stay out of the bank: they belong to each application.
- **Stages:** where it came up or would plausibly come up: `screening`, `technical`, `manager`, `executive`, `case`, `final`.
- **JD signals:** words in a job description that make the question likely: tools, techniques, responsibilities, seniority (e.g. `team lead`, `pre-sales`, `production`, `AWS`). Add signals when a new interview shows another trigger.
- **History:** one line per time it was asked, newest first. Rating:
  - ✅ **good:** answered what was asked, accurate, with a concrete example, reasonable length;
  - ⚠️ **fair:** right direction but incomplete, vague, too long, or missed the best example;
  - ❌ **poor:** did not answer what was asked, wrong, or could not answer;
  - `–` **not rated:** the source (e.g. old notes without a transcript) says the question came up but not how it went. It counts for **Asked**, not for **Status**.
- **Status**, derived from the rated history lines, **the most recent answers weigh most**:
  - `mastered`: the last two ratings are ✅;
  - `good`: the last is ✅;
  - `fair`: the last is ⚠️;
  - `weak`: the last is ❌;
  - `regressed`: the last is worse than the one before (it was ✅ and is now ⚠️ or ❌). Treat it like `weak` when prioritizing;
  - `unrated`: no rated lines yet. Treat it like `fair` when prioritizing.

  A question answered badly once and well later is `good`, not weak: the bank evolves with the user.
- **Best answer:** one answer, kept current, never a pile of versions. When the latest answer was ✅, the user's own answer (condensed, in their words) becomes the best answer, keeping earlier improvements only if they still add something. When it was ⚠️ or ❌, use the better answer from the review. Built only from the profile and the transcripts (golden rule).

## Matching a question to a group

Two questions belong to the same group when they test the **same underlying ability**, even if worded differently: "how do agents share information?" and "how do you keep a multi-agent system's context from overflowing?" are one group; "what is RAG?" (concept) and "walk me through a RAG project you built" (experience) are two. When unsure, prefer merging and add the new wording under **How it was asked**. A follow-up that digs into the same topic is part of the parent question, not a new group.
